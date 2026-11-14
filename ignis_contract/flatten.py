"""Flat, model-facing view of a bundle. This column list IS the model contract.

One row per observation, SI values only, None = not reported (never imputed here).
"""
from __future__ import annotations

FLAT_COLUMNS = [
    "id", "source_id", "campaign_id", "platform", "year", "material_id", "phase", "geometry",
    "thickness_m", "diameter_m",
    "gravity_m_s2", "o2_mole_fraction", "pressure_pa", "diluent", "flow_velocity_m_s", "flow_direction",
    "buoyancy_orientation", "external_heat_flux_w_m2",
    "quantity", "value_si", "si_unit", "lower_si", "upper_si", "sd_si", "state", "time_basis",
    "extraction_method", "confidence", "qa_status", "nominal_condition_fields",
]


def _si(q):
    return None if q is None else q["si_value"]


def _uncertainty_bounds(q):
    if not q or "uncertainty" not in q:
        return None, None, None
    u, v = q["uncertainty"], q["si_value"]
    lo, hi, sd = u.get("lower_si"), u.get("upper_si"), u.get("sd_si")
    if sd is None and u["kind"] == "relative" and "relative" in u:
        sd = abs(v) * u["relative"]
    return lo, hi, sd


def flatten_observation(obs: dict, sources: dict) -> dict:
    c, f, o = obs["conditions"], obs["fuel"], obs["outcome"]
    val = o.get("value")
    lo, hi, sd = _uncertainty_bounds(val)
    src = sources.get(obs["locator"]["source_id"], {})
    nominal = sorted(k for k, q in c.items() if isinstance(q, dict) and q.get("basis") == "campaign_nominal")
    row = {
        "id": obs["id"],
        "source_id": obs["locator"]["source_id"],
        "campaign_id": obs["experiment"]["campaign_id"],
        "platform": obs["experiment"]["platform"],
        "year": obs["experiment"].get("test_year", src.get("year")),
        "material_id": f["material_id"],
        "phase": f["phase"],
        "geometry": f["geometry"],
        "thickness_m": _si(f.get("thickness")),
        "diameter_m": _si(f.get("diameter")),
        "gravity_m_s2": _si(c["gravity"]),
        "o2_mole_fraction": _si(c.get("o2_mole_fraction")),
        "pressure_pa": _si(c.get("pressure")),
        "diluent": c.get("diluent"),
        "flow_velocity_m_s": _si(c.get("flow_velocity")),
        "flow_direction": c.get("flow_direction"),
        "buoyancy_orientation": c.get("buoyancy_orientation"),
        "external_heat_flux_w_m2": _si(c.get("external_heat_flux")),
        "quantity": o["quantity"],
        "value_si": _si(val),
        "si_unit": None if val is None else val["si_unit"],
        "lower_si": lo,
        "upper_si": hi,
        "sd_si": sd,
        "state": o.get("state"),
        "time_basis": o.get("time_basis"),
        "extraction_method": obs["extraction"]["method"],
        "confidence": obs["extraction"]["confidence"],
        "qa_status": obs["qa"]["status"],
        "nominal_condition_fields": ",".join(nominal) or None,
    }
    assert list(row) == FLAT_COLUMNS
    return row


def flatten_bundle(bundle: dict, statuses=("accepted", "human_verified")) -> list[dict]:
    """Default: only rows a model may train on. Pass statuses=None for everything."""
    sources = {s["id"]: s for s in bundle["sources"]}
    return [flatten_observation(o, sources) for o in bundle["observations"]
            if statuses is None or o["qa"]["status"] in statuses]
