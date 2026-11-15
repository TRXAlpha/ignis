"""Tools the analyst may call. They read only the exported files (web/public/data), the same numbers the UI shows."""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

DATA = Path("web/public/data")


@lru_cache(maxsize=None)
def _load(name: str) -> dict:
    p = DATA / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _interp(grid: dict, key: str, x: float, y: float) -> float:
    xs, ys, Z = grid["x"], grid["y"], grid[key]
    lx = [math.log10(v) for v in xs]
    t = math.log10(x)
    i = max(0, min(len(lx) - 2, sum(1 for v in lx if v <= t) - 1))
    j = max(0, min(len(ys) - 2, sum(1 for v in ys if v <= y) - 1))
    u = (t - lx[i]) / (lx[i + 1] - lx[i])
    w = (y - ys[j]) / (ys[j + 1] - ys[j])
    return ((1 - u) * (1 - w) * Z[j][i] + u * (1 - w) * Z[j][i + 1] + (1 - u) * w * Z[j + 1][i] + u * w * Z[j + 1][i + 1])


def p_burns(o2_percent: float, stretch_rate_per_s: float | None = None, flow_cm_s: float | None = None) -> dict:
    """P(sustained burning) of a PMMA rod in microgravity. o2_percent is the O2 mole fraction in percent (e.g. 21), NOT pressure. Give stretch rate (1/s) or flow (cm/s, 6.35-mm rod). For habitat atmospheres use the habitats tool."""
    m = _load("model")
    if m.get("status") != "ok":
        return {"status": "insufficient_data", "reason": "no model fitted yet (no digitized flame-state data)"}
    if stretch_rate_per_s is None:
        if flow_cm_s is None:
            return {"error": "give stretch_rate_per_s or flow_cm_s"}
        stretch_rate_per_s = flow_cm_s / 100 / m["flow_conversion"]["u_m_s_per_x"]
    x, y = float(stretch_rate_per_s), float(o2_percent) / 100
    g = m["grid"]
    if not (g["x"][0] <= x <= g["x"][-1] and g["y"][0] <= y <= g["y"][-1]):
        return {"status": "insufficient_data", "reason": "outside the model grid", "stretch_rate_per_s": round(x, 3)}
    pts = m["points"]
    in_data = (min(p["x"] for p in pts) <= x <= max(p["x"] for p in pts)
               and min(p["y"] for p in pts) <= y <= max(p["y"] for p in pts))
    return {"status": "ok" if in_data else "extrapolation", "p_burns": round(_interp(g, "p_burns", x, y), 3),
            "p_sd": round(_interp(g, "p_sd", x, y), 3), "stretch_rate_per_s": round(x, 3), "o2_percent": round(y * 100, 2),
            "model": f'{m["model_id"]}@{m["model_version"]}', "n_points": len(pts)}


def min_o2() -> dict:
    """Lowest O2 % at which the fitted boundary allows burning, with 90 % band, plus the literature comparison lines."""
    m = _load("model")
    if m.get("status") != "ok":
        return {"status": "insufficient_data", "reason": "no model fitted yet"}
    mo = m["min_o2"]
    return {"median_estimate_min_o2_percent": round(mo["p50"] * 100, 2),
            "uncertainty_band_level_percent": 90,
            "uncertainty_band_min_o2_percent": [round(mo["p05"] * 100, 2), round(mo["p95"] * 100, 2)],
            "at_stretch_rate_per_s": round(mo["at_x"], 2),
            "baselines": [{"label": b["label"], "o2_percent": round(b["o2"] * 100, 2), "source": b["ref"]} for b in m["baselines"]]}


def habitats() -> dict:
    """Habitat presets with the model's verdict (status, P(burns) or reason) and their sources."""
    return {"presets": [{"id": h["id"], "name": h["name"], "o2_percent": round(h["conditions"]["o2_mole_fraction"] * 100, 2),
                         "pressure_kpa": round(h["conditions"]["pressure_pa"] / 1000, 1),
                         "status": h["prediction"]["status"], "p_burns": h["prediction"].get("p_burns"),
                         "reason": h["prediction"]["ood"].get("reason"), "refs": h["refs"]}
                        for h in _load("habitats").get("presets", [])]}


def recommendations() -> dict:
    """Next experiments ranked by expected information gain, inside the sourced facility envelope."""
    r = _load("recommendations")
    return {"constraint_set": (r.get("constraint_set") or {}).get("name"),
            "items": [{"rank": i["rank"], "o2_percent": round(i["conditions"]["o2_mole_fraction"] * 100, 2),
                       "flow_cm_s": round(i["conditions"]["flow_velocity_m_s"] * 100, 2), "p_burns": i["p_burns"],
                       "info_gain_nats": i["expected_information_gain_nats"], "why": i["gap"]["description"]}
                      for i in r.get("items", [])]}


def validation() -> dict:
    """Validation results vs the 1g baseline, and stated limitations."""
    v = _load("validation")
    return {k: v.get(k) for k in ("folds", "cv", "summary", "limitations")}


def observation(obs_id: str) -> dict:
    """Full provenance of one observation: source, PDF page, figure/table, quote, extraction, QA."""
    b = _load("bundle")
    for o in b.get("observations", []):
        if o["id"] == obs_id:
            src = next((s for s in b["sources"] if s["id"] == o["locator"]["source_id"]), {})
            return {"observation": o, "source": {"title": src.get("title"), "url": src.get("url")}}
    return {"error": f"no observation {obs_id}"}


def contradictions() -> dict:
    """Consistency checks: literature claims vs data, claims vs claims, conflicting observations (verdict + sources)."""
    return {"items": [{k: c[k] for k in ("verdict", "kind", "title", "detail", "numbers", "refs")}
                      for c in _load("contradictions").get("items", [])]}


def material_screen() -> dict:
    """Per-sample Saffire-II test table: Earth 1g burn vs microgravity burn (raw PSI cells) and the verdict, plus source."""
    s = _load("material_screen")
    return {"source": s.get("source"), "rows": s.get("rows", []), "notes": s.get("notes", [])}


def test_outcomes() -> dict:
    """BASS-II per-test flame outcomes by material and geometry: state counts, O2 where burned vs extinguished, QA split. No quotes."""
    t = _load("test_outcomes")
    groups = []
    for g in t.get("groups", []):
        groups.append({**{k: v for k, v in g.items() if k != "tests"},
                       "tests": [{k: v for k, v in x.items() if k != "quote"} for x in g.get("tests", [])]})
    return {"source": t.get("source"), "o2_summary_basis": t.get("o2_summary_basis"), "groups": groups}


def video_spread() -> dict:
    """Spread rates re-measured from NASA's BASS-II flight stills (PSI), with uncertainty and the claim check."""
    v = _load("video_spread")
    return {"rows": [{k: r.get(k) for k in ("test_id", "spread_mm_s", "spread_mm_s_sd", "spread_mm_s_scale_range",
                                            "confidence", "flags")} for r in v.get("rows", [])],
            "claim_check": v.get("claim_check")}


def data_summary() -> dict:
    """What data the model is built on: counts by campaign, outcome and QA status."""
    b = _load("bundle")
    out: dict = {"n_observations": len(b.get("observations", [])), "by": {}}
    for o in b.get("observations", []):
        k = f'{o["experiment"]["campaign_id"]} | {o["outcome"]["quantity"]} | {o["qa"]["status"]}'
        out["by"][k] = out["by"].get(k, 0) + 1
    out["sources"] = [{"id": s["id"], "title": s["title"]} for s in b.get("sources", [])]
    return out


TOOLS = {f.__name__: f for f in (p_burns, min_o2, habitats, recommendations, validation, observation, contradictions, video_spread,
                                  material_screen, test_outcomes, data_summary)}

SCHEMAS = [
    {"type": "function", "function": {"name": "p_burns", "description": p_burns.__doc__, "parameters": {
        "type": "object", "properties": {"o2_percent": {"type": "number"}, "stretch_rate_per_s": {"type": "number"},
                                         "flow_cm_s": {"type": "number"}}, "required": ["o2_percent"]}}},
    {"type": "function", "function": {"name": "observation", "description": observation.__doc__, "parameters": {
        "type": "object", "properties": {"obs_id": {"type": "string"}}, "required": ["obs_id"]}}},
] + [{"type": "function", "function": {"name": n, "description": TOOLS[n].__doc__,
                                       "parameters": {"type": "object", "properties": {}}}}
     for n in ("min_o2", "habitats", "recommendations", "validation", "contradictions", "material_screen", "test_outcomes", "data_summary")]
