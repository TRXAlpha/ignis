"""Fit the boundary model on data/bundle.json and write the frontend files (docs/web_data.md).

python -m model.export            # -> web/public/data/{bundle,model,validation,recommendations,habitats}.json

Only accepted / human_verified observations are used. Every literature number shown next to the model
(1g limit, paper's minimum, facility ranges, rod radius) is verbatim-checked against its PDF page here.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np

from ignis_contract import check_bundle, is_valid, schema_errors
from ingest.curated import require_text

from . import boundary as bm
from . import contradictions as cx
from . import material_screen as ms

BUNDLE = Path("data/bundle.json")
OUT = Path("web/public/data")
HABITATS = Path("registry/habitats.json")
MODEL_ID, VERSION = "ignis-boundary", "0.1.0"
BASS2 = "ntrs:20210011385"
STATES_BURN = {"burns_sustained"}
STATES_EXT = {"blowoff_extinction", "quench_extinction", "radiative_extinction", "self_extinguished"}
ISS_G = 2e-6 * 9.80665  # same campaign-nominal as the observations (PIMS p45, upper bound)

# literature numbers, each checked verbatim on its page at export time
REFS = {
    "upward_1g": (84, "significantly lower than the observed upward flame spread limit of", "15.4 percent O2"),
    "paper_min": (83, "The minimum in this boundary occurs at a = 8 to 12 s-1 at approximately 13.5 percent O2"),
    "ro": (83, "normalized to the base rod radius (ro = 0.318 cm)"),
    "flow": (72, "A small flow duct was used to create 0- to 55-cm/s flows past the three sizes"),
    "o2": (72, "was varied from 13.6 to 22.2 percent"),
}
RO_M = 0.00318
U_PER_A = RO_M / 1.5  # a = (3/2) U / r at r = ro  ->  U = a ro / 1.5


def loc(key: str) -> dict:
    page, *snips = REFS[key]
    return {"source_id": BASS2, "page": page, "quote": " ".join(snips)}


def x_of(o: dict):
    """(x_var, x value) for a flame-state row: stretch rate (1/s) or flow velocity (cm/s), else None."""
    extra = {e["name"]: e["quantity"]["si_value"] for e in o["conditions"].get("extra", [])}
    if "stretch_rate" in extra:
        return "stretch_rate", extra["stretch_rate"]
    fv = o["conditions"].get("flow_velocity")  # contract slot (Quantity); extra kept for older rows/tests
    if fv is not None:
        return "flow_velocity", fv["si_value"] * 100  # SI m/s -> cm/s
    if "flow_velocity" in extra:
        return "flow_velocity", extra["flow_velocity"] * 100
    return None, None


def flame_rows(bundle: dict) -> list[dict]:
    """All usable flame-state rows with their group key (material_id, geometry, flow_direction, x_var)."""
    rows = []
    for o in bundle["observations"]:
        if o["qa"]["status"] not in ("accepted", "human_verified") or o["outcome"]["quantity"] != "flame_state":
            continue
        st = o["outcome"]["state"]
        if st not in STATES_BURN | STATES_EXT or "o2_mole_fraction" not in o["conditions"]:
            continue
        xv, xval = x_of(o)
        if xv is None:
            continue
        mat = o["fuel"].get("material_id")
        geo = o["fuel"].get("geometry")
        flow = o["conditions"].get("flow_direction")
        rows.append({"id": o["id"], "campaign": o["experiment"]["campaign_id"], "series": o["locator"].get("series"),
                     "state": st, "a": xval, "x": o["conditions"]["o2_mole_fraction"]["si_value"],
                     "y": 1.0 if st in STATES_BURN else 0.0, "material": mat,
                     "key": (mat, geo, flow, xv)})
    return rows


def boundary_points(bundle: dict):
    return [r for r in flame_rows(bundle) if r["key"][3] == "stretch_rate"]


def _arr(rows, k):
    return np.array([r[k] for r in rows], float)


def _scores(f, te):
    """Held-out scores. Extinction points: where is the boundary (O2 %)? Stable flames: is the point on the burning side?"""
    a, x, y = _arr(te, "a"), _arr(te, "x") * 100, _arr(te, "y")
    out, base = {}, {}
    ext, st = y == 0, y == 1
    if ext.any():
        B = bm.boundary(a[ext][None, :], f.samples(1000))
        pred = np.median(B, 0)
        lo, hi = np.percentile(B, 5, 0), np.percentile(B, 95, 0)
        sig = np.exp(f.theta[5])
        out["median_abs_rel_error"] = float(np.median(np.abs(pred - x[ext]) / x[ext]))
        out["rmse_o2_pct"] = float(np.sqrt(np.mean((pred - x[ext]) ** 2)))
        # predictive interval for a new extinction measurement = boundary band widened by measurement scatter
        out["coverage90_ext"] = float(np.mean((x[ext] >= lo - 1.645 * sig) & (x[ext] <= hi + 1.645 * sig)))
        base["median_abs_rel_error"] = float(np.median(np.abs(15.4 - x[ext]) / x[ext]))
        base["rmse_o2_pct"] = float(np.sqrt(np.mean((15.4 - x[ext]) ** 2)))
    if st.any():
        p = np.clip(bm.predict(f, a[st], x[st])[0], 1e-3, 1 - 1e-3)
        out["brier"] = float(np.mean((p - 1) ** 2))
        out["acc_stable"] = float(np.mean(p > 0.5))
        pb = np.where(x[st] >= 15.4, 0.98, 0.02)
        base["brier"] = float(np.mean((pb - 1) ** 2))
        base["acc_stable"] = float(np.mean(pb > 0.5))
    return out, base, int(ext.sum()), int(st.sum())


SCHEMA_METRICS = ("median_abs_rel_error", "brier")


def fit_group(rows: list[dict]) -> dict | None:
    """Fit one group; returns the model.json['groups'] entry or None with (reason) if it does not qualify."""
    n_ext, n_burn = sum(r["y"] == 0 for r in rows), sum(r["y"] == 1 for r in rows)
    mat, geo, flow, xv = rows[0]["key"]
    key = {"material_id": mat, "geometry": geo, "flow_direction": flow, "x_var": xv}
    if len(rows) < 6 or n_ext < 2 or n_burn < 1:
        return None
    f = bm.fit(_arr(rows, "a"), _arr(rows, "x") * 100, _arr(rows, "y"))
    a_lo, a_hi = float(_arr(rows, "a").min()), float(_arr(rows, "a").max())
    gx = np.logspace(np.log10(a_lo), np.log10(a_hi), 60)
    band = bm.boundary_band(f, gx)
    mo = bm.min_o2(f, gx)
    at_edge = not (gx[1] < mo["at_x"] < gx[-2])  # argmin at the first/last grid point -> edge of data range
    by_camp = {}
    for r in rows:
        by_camp[r["campaign"]] = by_camp.get(r["campaign"], 0) + 1
    return {"key": key, "n": len(rows), "n_by_campaign": by_camp,
            "min_o2": {**{k: round(v / 100, 5) for k, v in mo.items() if k != "at_x"},
                       "at_x": round(mo["at_x"], 4), "min_at_edge": at_edge},
            "boundary": {"x": [round(v, 5) for v in gx],
                         **{f"o2_{k}": [round(float(v) / 100, 5) for v in vals] for k, vals in band.items()}},
            "points": [{"id": r["id"], "x": round(float(r["a"]), 5), "y": round(float(r["x"]), 5),
                        "state": r["state"], "campaign": r["campaign"]} for r in rows],
            "laplace_ok": bool(f.converged)}


def group_folds(bundle: dict, folds: list, skip_ids: frozenset = frozenset()) -> None:
    """Leave-one-campaign-out per qualifying group (>= 2 campaigns), appended to validation folds.
    Groups whose rows are exactly the primary fit's rows are skipped (their folds already exist)."""
    groups = {}
    for r in flame_rows(bundle):
        groups.setdefault(r["key"], []).append(r)
    for key, rows in sorted(groups.items(), key=lambda kv: [str(v) for v in kv[0]]):
        camps = sorted({r["campaign"] for r in rows})
        if len(camps) < 2 or frozenset(r["id"] for r in rows) == skip_ids:
            continue
        mat, geo, flow, xv = key
        label = "-".join(str(v) for v in key)
        for c in camps:
            tr, te = [r for r in rows if r["campaign"] != c], [r for r in rows if r["campaign"] == c]
            if len(tr) < 8 or not te:
                continue
            f = bm.fit(_arr(tr, "a"), _arr(tr, "x") * 100, _arr(tr, "y"))
            m, b, _, _ = _scores(f, te)
            folds.append({"model_id": MODEL_ID, "model_version": VERSION, "fold_id": f"loco-{label}-{c}",
                          "held_out_campaign_id": c, "outcome_quantity": "flame_state", "n_train": len(tr),
                          "n_test": len(te), "metrics": {k: m[k] for k in SCHEMA_METRICS if k in m},
                          "baseline": {k: b[k] for k in SCHEMA_METRICS if k in b}})


def validate(rows, sources):
    folds, cv = [], []
    camps = sorted({r["campaign"] for r in rows})
    for c in camps if len(camps) > 1 else []:
        tr, te = [r for r in rows if r["campaign"] != c], [r for r in rows if r["campaign"] == c]
        if len(tr) < 8 or not te:
            continue
        f = bm.fit(_arr(tr, "a"), _arr(tr, "x") * 100, _arr(tr, "y"))
        m, b, _, _ = _scores(f, te)
        folds.append({"model_id": MODEL_ID, "model_version": VERSION, "fold_id": f"loco-{c}",
                      "held_out_campaign_id": c, "outcome_quantity": "flame_state", "n_train": len(tr),
                      "n_test": len(te), "metrics": {k: m[k] for k in SCHEMA_METRICS if k in m},
                      "baseline": {k: b[k] for k in SCHEMA_METRICS if k in b}})
    # within-data 5-fold CV (not leave-one-campaign-out; reported separately, never as a ValidationFold)
    if len(rows) >= 15:
        rng = np.random.default_rng(0)
        idx = rng.permutation(len(rows))
        M, Bs, W = [], [], []
        for k in range(5):
            te_i = set(idx[k::5].tolist())
            tr = [r for i, r in enumerate(rows) if i not in te_i]
            te = [r for i, r in enumerate(rows) if i in te_i]
            f = bm.fit(_arr(tr, "a"), _arr(tr, "x") * 100, _arr(tr, "y"))
            m, b, ne, ns = _scores(f, te)
            M.append(m); Bs.append(b); W.append({"median_abs_rel_error": ne, "rmse_o2_pct": ne, "coverage90_ext": ne,
                                                 "brier": ns, "acc_stable": ns})
        avg = lambda D: {k: float(np.average([d[k] for d in D if k in d], weights=[w[k] for d, w in zip(D, W) if k in d]))
                         for k in sorted({k for d in D for k in d})}  # noqa: E731
        cv = [{"kind": "5-fold random CV (same campaign)", "n": len(rows), "metrics": avg(M), "baseline": avg(Bs),
               "notes": {"rmse_o2_pct": "held-out extinction points: predicted vs observed boundary O2 (% points)",
                         "coverage90_ext": "share of held-out extinction points inside the 90 % predictive interval",
                         "brier": "held-out stable flames, P(burns) vs 1",
                         "acc_stable": "held-out stable flames predicted burning (p > 0.5)"}}]
    lim = []
    if len(camps) < 2:
        lim.append("Only one campaign has flame-state data, so leave-one-campaign-out validation is not possible yet. "
                   "The 5-fold CV below is within-campaign and optimistic.")
    lim.append("Baseline = normal-gravity practice: material burns iff O2 >= 15.4 % (upward limit, BASS-II report p84).")
    lim.append("Gravity is a campaign nominal (ISS quasi-steady, <= 2 micro-g, 2001-2002 PIMS data), not measured per test.")
    lim.append("Pressure was not reported for the rod tests; the model is only valid at the cabin pressure they ran at.")
    return {"folds": folds, "cv": cv, "summary": "", "limitations": lim}


def recommend(f, rows, top=5):
    cs = {"id": "bass-ii-msg-rods", "name": "BASS-II flow duct in the ISS Microgravity Science Glovebox (rods)",
          "platform": "orbital_iss", "facility": "Microgravity Science Glovebox (MSG)",
          "ranges": {"o2_mole_fraction": [0.136, 0.222], "flow_velocity_m_s": [0.0, 0.55]},
          "materials": ["pmma"], "refs": [loc("flow"), loc("o2")]}
    a_hi = min(0.55 / U_PER_A, 1.2 * _arr(rows, "a").max())  # facility limit, but no far extrapolation past the data
    a_c = np.logspace(np.log10(_arr(rows, "a").min()), np.log10(a_hi), 90)
    x_c = np.linspace(13.6, 22.2, 87)
    A, X = np.meshgrid(a_c, x_c)
    _, sd, ps = bm.predict(f, A.ravel(), X.ravel())
    mi = bm.mutual_information(ps)
    pm = ps.mean(0)
    la, xs = np.log10(_arr(rows, "a")), _arr(rows, "x") * 100
    items, taken = [], []
    for i in np.argsort(-mi):
        a, x = A.ravel()[i], X.ravel()[i]
        if any(abs(np.log10(a) - np.log10(ta)) < 0.25 for ta, tx in taken):  # spread across flow
            continue
        taken.append((a, x))
        d = np.hypot((la - np.log10(a)) / 0.5, (xs - x) / 1.0)
        near = [rows[j]["id"] for j in np.argsort(d)[:3]]
        items.append({"rank": len(items) + 1, "constraint_set_id": cs["id"], "material_id": "pmma",
                      "conditions": {"gravity_m_s2": ISS_G, "o2_mole_fraction": round(x / 100, 4),
                                     "flow_velocity_m_s": round(float(a * U_PER_A), 5), "flow_direction": "concurrent"},
                      "outcome_quantity": "flame_state", "expected_information_gain_nats": round(float(mi[i]), 4),
                      "n_burns": 1, "model_version": VERSION,
                      "gap": {"description": (f"Boundary most uncertain here: P(burns) = {pm[i]:.2f} +/- {sd[i]:.2f}"
                                              f" for the 6.35-mm rod (a = {a:.1f} 1/s)." if a < 10 else
                                              f"Boundary most uncertain here: P(burns) = {pm[i]:.2f} +/- {sd[i]:.2f}"
                                              f" for the 6.35-mm rod (a = {a:.0f} 1/s)."),
                              "predictive_sd_before": round(float(sd[i]), 4), "nearest_observation_ids": near},
                      "x": float(a), "p_burns": round(float(pm[i]), 4)})
        if len(items) == top:
            break
    return {"constraint_set": cs, "items": items}


def habitats(f, rows, sources=None):
    if not HABITATS.exists():
        return {"presets": [], "note": "No sourced habitat presets yet."}
    presets = json.loads(HABITATS.read_text(encoding="utf-8"))
    for h in presets:  # every preset is sourced and every NTRS quote is on its page
        errs = schema_errors(h, "HabitatPreset")
        assert not errs, [str(e) for e in errs]
        for r in h["refs"]:
            if sources is not None and r["source_id"].startswith("ntrs:"):
                require_text(sources, r["source_id"], r["page"], r["quote"])
    xs = _arr(rows, "x")
    a_grid = np.logspace(np.log10(_arr(rows, "a").min()), np.log10(_arr(rows, "a").max()), 120) if rows else None
    out = []
    for h in presets:
        c = h["conditions"]
        x = c.get("o2_mole_fraction")
        base = {"model_id": MODEL_ID, "model_version": VERSION, "material_id": "pmma", "outcome_quantity": "flame_state",
                "conditions": c, "evidence_observation_ids": [r["id"] for r in rows][:50]}
        p_kpa = c.get("pressure_pa", 0) / 1000
        g = c.get("gravity_m_s2", 0)
        if f is None:
            pred = {**base, "status": "insufficient_data", "mean_si": None, "p_burns": None,
                    "ood": {"in_domain": False, "score": 1.0, "method": "no model",
                            "reason": "No flame-state observations digitized yet, so there is no model to query."}}
        elif g > 1e-3:
            pred = {**base, "status": "insufficient_data", "mean_si": None, "p_burns": None,
                    "ood": {"in_domain": False, "score": 1.0, "method": "gravity/pressure domain check",
                            "reason": f"Partial gravity ({g:.2g} m/s2) at {p_kpa:.1f} kPa: buoyant flow returns and the "
                                      "model only knows microgravity at cabin pressure. No flight data exists here."}}
        elif x is None or not (95 <= p_kpa <= 105):
            pred = {**base, "status": "insufficient_data", "mean_si": None, "p_burns": None,
                    "ood": {"in_domain": False, "score": 1.0, "method": "pressure/O2 domain check",
                            "reason": f"Total pressure {p_kpa:.1f} kPa is outside the tested cabin pressure (~101 kPa). "
                                      "Flammability limits shift with pressure; no flight data here."}}
        else:
            pb = bm.predict(f, a_grid, np.full_like(a_grid, x * 100))[0]
            worst = float(pb.max())
            inside = xs.min() <= x <= xs.max()
            pred = {**base, "status": "ok" if inside else "extrapolation", "p_burns": round(worst, 4),
                    "ood": {"in_domain": bool(inside), "score": 0.0 if inside else 1.0, "method": "O2 range of data",
                            "reason": ("Worst case over the tested ventilation range (stretch "
                                       f"{a_grid.min():.2g}-{a_grid.max():.3g} 1/s). Assumes ~101 kPa as in the rod tests.")
                            if inside else f"O2 {x * 100:.1f} % is outside the tested {xs.min() * 100:.1f}-{xs.max() * 100:.1f} %."}}
        out.append({**h, "prediction": pred})
    return {"presets": out}


def test_outcomes(bundle: dict) -> dict:
    """BASS-II per-test flame outcomes (ingest.curated.bass2_tests), grouped by material and geometry.
    Independent of the boundary fit. O2 summaries use accepted rows only; flagged rows are listed but not summarised."""
    mats = {m["id"]: m["name"] for m in bundle["materials"]}
    groups: dict = {}
    for o in bundle["observations"]:
        ex, loc_ = o["experiment"], o["locator"]
        if (loc_["source_id"] != BASS2 or o["extraction"]["method"] != "text" or ex["campaign_id"] != "bass-ii"
                or "run_id" not in ex or o["outcome"]["quantity"] != "flame_state"):
            continue
        flow = o["conditions"].get("flow_velocity")
        groups.setdefault((o["fuel"]["material_id"], o["fuel"]["geometry"]), []).append({
            "obs_id": o["id"], "test_id": ex["run_id"], "state": o["outcome"]["state"],
            "o2_pct": o["conditions"]["o2_mole_fraction"]["value"],
            "flow_cm_s": round(flow["si_value"] * 100, 3) if flow else None,
            "qa_status": o["qa"]["status"], "page": loc_["page"], "quote": loc_["quote"]})
    out = []
    for (mid, geom), tests in sorted(groups.items()):
        acc = [t for t in tests if t["qa_status"] == "accepted"]
        counts: dict = {}
        for t in tests:
            counts[t["state"]] = counts.get(t["state"], 0) + 1
        ext = [t["o2_pct"] for t in acc if t["state"] in STATES_EXT]
        out.append({"material_id": mid, "material_name": mats.get(mid, mid), "geometry": geom,
                    "n": len(tests), "n_accepted": len(acc), "n_flagged": len(tests) - len(acc),
                    "counts_by_state": dict(sorted(counts.items())),
                    "burned_o2_pct": sorted(t["o2_pct"] for t in acc if t["state"] in STATES_BURN),
                    "extinguished_o2_pct": [min(ext), max(ext)] if ext else None,
                    "tests": sorted(tests, key=lambda t: t["test_id"])})
    return {"source": {"report": BASS2, "table": "psi:PSI-25"}, "o2_summary_basis": "accepted rows only", "groups": out}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bundle = json.loads(BUNDLE.read_text(encoding="utf-8"))
    sources = {s["id"]: s for s in bundle["sources"]}
    if not is_valid(check_bundle(bundle, production=True)):
        print("bundle invalid; run python -m ingest.build_bundle", file=sys.stderr)
        return 1
    for page, *snips in REFS.values():
        require_text(sources, BASS2, page, *snips)
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(BUNDLE, OUT / "bundle.json")
    src = next(s for s in bundle["sources"] if s["id"] == "psi:PSI-99")
    screen = {"source": {k: src.get(k) for k in ("id", "doi", "url", "title")},
              "rows": ms.table(bundle), "notes": ms.notes()}
    (OUT / "material_screen.json").write_text(json.dumps(screen, ensure_ascii=False), encoding="utf-8")
    (OUT / "test_outcomes.json").write_text(json.dumps(test_outcomes(bundle), ensure_ascii=False), encoding="utf-8")
    rows = boundary_points(bundle)
    baselines = [{"id": "1g-upward-limit", "label": "1g upward-spread limit (15.4 % O2)", "o2": 0.154, "ref": loc("upward_1g")},
                 {"id": "paper-min", "label": "BASS-II reported minimum (~13.5 % O2)", "o2": 0.135, "ref": loc("paper_min")}]
    model = {"model_id": MODEL_ID, "model_version": VERSION, "material_id": "pmma",
             "description": bm.__doc__.strip().split("\n\n")[0],
             "x": {"name": "stretch_rate", "label": "Stretch rate a", "unit": "1/s", "scale": "log"},
             "y": {"name": "o2_mole_fraction", "label": "O2 mole fraction", "unit": "1"},
             "points": [{"id": r["id"], "x": r["a"], "y": r["x"], "state": r["state"], "series": r["series"]} for r in rows],
             "baselines": baselines,
             "flow_conversion": {"note": "Flow velocity for the base 6.35-mm rod (ro = 0.318 cm): U = a ro / 1.5",
                                 "u_m_s_per_x": U_PER_A, "ref": loc("ro")},
             "grid": None, "boundary": None, "min_o2": None, "status": "no_data"}
    if len(rows) < 8 or len({r["y"] for r in rows}) < 2:
        print(f"only {len(rows)} usable flame-state points: writing no-data model files", file=sys.stderr)
        val = {"folds": [], "cv": [], "summary": "No flame-state data digitized yet.", "limitations": []}
        con = []
        rec, hab = {"constraint_set": None, "items": []}, habitats(None, rows, sources)
    else:
        f = bm.fit(_arr(rows, "a"), _arr(rows, "x") * 100, _arr(rows, "y"))
        gx = np.logspace(np.log10(_arr(rows, "a").min() / 1.5), np.log10(_arr(rows, "a").max() * 1.5), 80)
        gy = np.linspace(12.5, 22.5, 60)
        GX, GY = np.meshgrid(gx, gy)
        pm, sd, _ = bm.predict(f, GX.ravel(), GY.ravel())
        band = bm.boundary_band(f, gx)
        mo = bm.min_o2(f, gx)
        model.update(status="ok", fit={"theta_map": dict(zip(bm.PARAMS, map(float, f.theta))), "n": f.n,
                                       "laplace_ok": f.converged},
                     grid={"x": gx.tolist(), "y": (gy / 100).tolist(), "p_burns": pm.reshape(GX.shape).round(4).tolist(),
                           "p_sd": sd.reshape(GX.shape).round(4).tolist()},
                     boundary={"x": gx.tolist(), **{f"o2_{k}": (v / 100).round(5).tolist() for k, v in band.items()}},
                     min_o2={k: (v / 100 if k != "at_x" else v) for k, v in mo.items()})
        val = validate(rows, sources)
        # multi-group fits: (material, geometry, flow_direction, x_var) with >= 6 rows, 2 ext, 1 burn
        all_rows = flame_rows(bundle)
        model["groups"], groups_skipped = [], []
        primary_ids = frozenset(r["id"] for r in rows)
        for key, grows in sorted(((k, [r for r in all_rows if r["key"] == k]) for k in {r["key"] for r in all_rows}),
                                 key=lambda kv: [str(v) for v in kv[0]]):
            if frozenset(r["id"] for r in grows) == primary_ids:
                continue  # identical to the primary fit: shown as "Primary fit", not twice
            g = fit_group(grows)
            if g is None:
                n_ext, n_burn = sum(r["y"] == 0 for r in grows), sum(r["y"] == 1 for r in grows)
                why = (f"only {len(grows)} rows (need >= 6)" if len(grows) < 6
                       else f"only {n_ext} extinction rows (need >= 2)" if n_ext < 2
                       else f"only {n_burn} burning rows (need >= 1)")
                groups_skipped.append({**{f"key_{k}": v for k, v in dict(zip(("material_id", "geometry", "flow_direction", "x_var"), key)).items()},
                                       "n": len(grows), "reason": why})
                continue
            g["label"] = " / ".join(str(v) for v in key if v is not None)
            model["groups"].append(g)
        model["groups_skipped"] = groups_skipped
        group_folds(bundle, val["folds"], primary_ids)
        for fold in val["folds"]:
            assert not schema_errors(fold, "ValidationFold"), schema_errors(fold, "ValidationFold")
        by = {}
        for r in rows:
            by[r["campaign"]] = by.get(r["campaign"], 0) + 1
        camps = {c["id"]: c["name"] for c in bundle["campaigns"]}
        val["summary"] = (f"Fitted on {len(rows)} flame-state points ("
                          + ", ".join(f"{n} from {camps.get(c, c)}" for c, n in sorted(by.items())) + "). Minimum O2 for burning: "
                          f"{mo['p50']:.1f} % (90 % band {mo['p05']:.1f}-{mo['p95']:.1f} %) at a = {mo['at_x']:.2g} 1/s; "
                          "the BASS-II report states ~13.5 % at a = 8-12 1/s. Normal-gravity practice uses 15.4 %.")
        con = cx.run(rows, f, sources)
        rec = recommend(f, rows)
        hab = habitats(f, rows, sources)
        for fold in val["folds"]:
            assert not schema_errors(fold, "ValidationFold"), schema_errors(fold, "ValidationFold")
        for it in rec["items"]:
            core = {k: v for k, v in it.items() if k not in ("x", "p_burns")}
            assert not schema_errors(core, "Recommendation"), schema_errors(core, "Recommendation")
        assert not schema_errors(rec["constraint_set"], "ConstraintSet")
        for h in hab["presets"]:
            assert not schema_errors(h["prediction"], "Prediction"), schema_errors(h["prediction"], "Prediction")
    for name, obj in (("model", model), ("validation", val), ("recommendations", rec), ("habitats", hab),
                      ("contradictions", {"items": con})):
        (OUT / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}: {len(rows)} boundary points, status={model['status']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
