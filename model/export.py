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


def boundary_points(bundle: dict):
    rows = []
    for o in bundle["observations"]:
        if o["qa"]["status"] not in ("accepted", "human_verified") or o["outcome"]["quantity"] != "flame_state":
            continue
        st = o["outcome"]["state"]
        extra = {e["name"]: e["quantity"]["si_value"] for e in o["conditions"].get("extra", [])}
        if st not in STATES_BURN | STATES_EXT or "stretch_rate" not in extra or "o2_mole_fraction" not in o["conditions"]:
            continue
        rows.append({"id": o["id"], "campaign": o["experiment"]["campaign_id"], "series": o["locator"].get("series"),
                     "state": st, "a": extra["stretch_rate"], "x": o["conditions"]["o2_mole_fraction"]["si_value"],
                     "y": 1.0 if st in STATES_BURN else 0.0, "material": o["fuel"]["material_id"]})
    return rows


def _arr(rows, k):
    return np.array([r[k] for r in rows], float)


def _metrics(p, y):
    p = np.clip(p, 1e-3, 1 - 1e-3)
    return {"brier": float(np.mean((p - y) ** 2)),
            "nlpd": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))}


def baseline_1g(x_frac):
    """1g practice: 'burns iff O2 >= upward limit'. Soft 0.02/0.98 so NLPD stays finite."""
    return np.where(x_frac * 100 >= 15.4, 0.98, 0.02)


def validate(rows, sources):
    folds, cv = [], []
    camps = sorted({r["campaign"] for r in rows})
    for c in camps if len(camps) > 1 else []:
        tr, te = [r for r in rows if r["campaign"] != c], [r for r in rows if r["campaign"] == c]
        if len(tr) < 8 or not te:
            continue
        f = bm.fit(_arr(tr, "a"), _arr(tr, "x") * 100, _arr(tr, "y"))
        p = bm.predict(f, _arr(te, "a"), _arr(te, "x") * 100)[0]
        y = _arr(te, "y")
        folds.append({"model_id": MODEL_ID, "model_version": VERSION, "fold_id": f"loco-{c}",
                      "held_out_campaign_id": c, "outcome_quantity": "flame_state", "n_train": len(tr),
                      "n_test": len(te), "metrics": _metrics(p, y), "baseline": _metrics(baseline_1g(_arr(te, "x")), y)})
    # within-data 5-fold CV (not leave-one-campaign-out; reported separately, never as a ValidationFold)
    if len(rows) >= 15:
        rng = np.random.default_rng(0)
        idx = rng.permutation(len(rows))
        P, Y, X = [], [], []
        for k in range(5):
            te_i = set(idx[k::5].tolist())
            tr = [r for i, r in enumerate(rows) if i not in te_i]
            te = [r for i, r in enumerate(rows) if i in te_i]
            f = bm.fit(_arr(tr, "a"), _arr(tr, "x") * 100, _arr(tr, "y"))
            P.append(bm.predict(f, _arr(te, "a"), _arr(te, "x") * 100)[0]); Y.append(_arr(te, "y")); X.append(_arr(te, "x"))
        P, Y, X = map(np.concatenate, (P, Y, X))
        cv = [{"kind": "5-fold random CV (same campaign)", "n": int(len(Y)), "metrics": _metrics(P, Y),
               "baseline": _metrics(baseline_1g(X), Y), "accuracy": float(np.mean((P > 0.5) == Y)),
               "baseline_accuracy": float(np.mean((baseline_1g(X) > 0.5) == Y))}]
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
    a_c = np.logspace(np.log10(0.3), np.log10(0.55 / U_PER_A), 90)
    x_c = np.linspace(13.6, 22.2, 87)
    A, X = np.meshgrid(a_c, x_c)
    _, sd, ps = bm.predict(f, A.ravel(), X.ravel())
    mi = bm.mutual_information(ps)
    pm = ps.mean(0)
    la, xs = np.log10(_arr(rows, "a")), _arr(rows, "x") * 100
    items, taken = [], []
    for i in np.argsort(-mi):
        a, x = A.ravel()[i], X.ravel()[i]
        if any(abs(np.log10(a) - np.log10(ta)) < 0.25 and abs(x - tx) < 0.8 for ta, tx in taken):
            continue
        taken.append((a, x))
        d = np.hypot((la - np.log10(a)) / 0.5, (xs - x) / 1.0)
        near = [rows[j]["id"] for j in np.argsort(d)[:3]]
        items.append({"rank": len(items) + 1, "constraint_set_id": cs["id"], "material_id": "pmma",
                      "conditions": {"gravity_m_s2": ISS_G, "o2_mole_fraction": round(x / 100, 4),
                                     "flow_velocity_m_s": round(float(a * U_PER_A), 5), "flow_direction": "concurrent"},
                      "outcome_quantity": "flame_state", "expected_information_gain_nats": round(float(mi[i]), 4),
                      "n_burns": 1, "model_version": VERSION,
                      "gap": {"description": f"Boundary most uncertain here: P(burns) = {pm[i]:.2f} +/- {sd[i]:.2f}"
                                             f" for the 6.35-mm rod (a = {a:.2g} 1/s).",
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
    a_grid = np.logspace(np.log10(_arr(rows, "a").min()), np.log10(_arr(rows, "a").max()), 120)
    out = []
    for h in presets:
        c = h["conditions"]
        x = c.get("o2_mole_fraction")
        base = {"model_id": MODEL_ID, "model_version": VERSION, "material_id": "pmma", "outcome_quantity": "flame_state",
                "conditions": c, "evidence_observation_ids": [r["id"] for r in rows][:50]}
        p_kpa = c.get("pressure_pa", 0) / 1000
        g = c.get("gravity_m_s2", 0)
        if g > 1e-3:
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
        rec, hab = {"constraint_set": None, "items": []}, {"presets": []}
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
        val["summary"] = (f"Fitted on {len(rows)} ISS flame-state points. Minimum O2 for burning: "
                          f"{mo['p50']:.1f} % (90 % band {mo['p05']:.1f}-{mo['p95']:.1f} %) at a = {mo['at_x']:.2g} 1/s; "
                          "the BASS-II report states ~13.5 % at a = 8-12 1/s. Normal-gravity practice uses 15.4 %.")
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
    for name, obj in (("model", model), ("validation", val), ("recommendations", rec), ("habitats", hab)):
        (OUT / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}: {len(rows)} boundary points, status={model['status']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
