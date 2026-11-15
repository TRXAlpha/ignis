"""Saffire-II (PSI-99) experimental table, 1g reference rows only.

SCOPE OVERRIDE (T3 restart): microgravity observations are emitted only if a quoted numeric
g-level for the Saffire/Cygnus environment exists in data/raw/ntrs. No such number exists in
any PDF there (searched for Saffire/Cygnus + acceleration/µg/g-level/microgravity level), so
only the 1g columns are ingested; the microgravity comparison is descriptive only and lives in
model/material_screen.py, which reads the CSV directly.

1g rows: "1-g Burn Length" -> outcome other/burn_length (numbers only; "Complete" is a
qualitative endpoint, not a number, and is NOT emitted as a quantity), "1-g Spread Rate" ->
flame_spread_rate (numeric values only; "Acceleratory"/"0.6 mm/s" etc.). Gravity is 9.80665 m/s2
with basis campaign_nominal (the 1g columns are ground tests by definition of the column names).
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from ignis_contract import make_quantity, observation_id

SRC = "psi:PSI-99"
CSV_PATH = Path("data/raw/psi/PSI-99.csv")
TOOL = "curated-transcription@1 (PSI-99.csv exact cell match)"

# campaign registry ids
CAMP_1G = "saffire-ii-1g-ref"

# (csv column, outcome quantity, quantity_label or None)
COLUMNS = [
    ("1-g Burn Length", "other", "burn_length"),
    ("1-g Spread Rate", "flame_spread_rate", None),
]

MATERIAL_IDS = {
    "Silicone": "silicone",
    "Cotton-Fiberglass (SIBAL)": "sibal",
    "PMMA": "pmma",
}


def _load_rows() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("Sample Number", "").startswith("2-")]


def _num(text: str) -> tuple[float, str] | None:
    """'7.6 cm' -> (7.6, 'cm'); '1.2 mm/s' -> (1.2, 'mm/s'); '~ 0'/'Complete'/'' -> None."""
    t = text.strip().lstrip("~").strip()
    parts = t.split()
    if len(parts) != 2:
        return None
    try:
        return float(parts[0]), parts[1]
    except ValueError:
        return None


def _o2(obs_text: str) -> dict | None:
    """'~ 21.5' or '22.1 to 22.0' -> Quantity (lower bound for a range, with a note)."""
    t = obs_text.strip().lstrip("~").strip()
    if " to " in t:
        lo = t.split(" to ")[0]
        note = f"PSI-99 reports a range ({t}); lower bound used."
    else:
        lo, note = t, None
    try:
        return make_quantity(float(lo), "percent", "conditions.o2_mole_fraction", note=note)
    except ValueError:
        return None


def observations(sources: dict) -> list[dict]:
    assert SRC in sources, f"{SRC} missing from registry/sources.json"
    rows = _load_rows()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out = []
    for r in rows:
        sample = r["Sample Number"]
        mat_raw = r["Material"].strip()
        if mat_raw not in MATERIAL_IDS:  # blank or multi-material rows: skip, listed in report
            continue
        mat = MATERIAL_IDS[mat_raw]
        o2 = _o2(r["Percent O2 (Note 1)"])
        flow = _num(r["Air Flow (cm/s)"])
        if o2 is None or flow is None:
            continue
        flow_q = make_quantity(flow[0], "cm/s", "conditions.flow_velocity")
        conditions = {
            "gravity": make_quantity(1.0, "g", "conditions.gravity", basis="campaign_nominal",
                                     basis_ref={"locator": {"source_id": SRC, "dataset_path": "PSI-99.csv",
                                                            "row": sample, "column": "1-g Burn Length"}},
                                     note="1g ground reference test by definition of the '1-g' column."),
            "o2_mole_fraction": o2,
            "flow_velocity": flow_q,
            "flow_direction": "concurrent" if "Concurrent" in r["Flow Direction"] else "opposed",
            "buoyancy_orientation": "not_applicable",
        }
        for col, quantity, label in COLUMNS:
            parsed = _num(r[col])
            if parsed is None:
                continue  # 'Complete', 'Acceleratory', '~ 0', blanks: qualitative or non-numeric
            value, unit = parsed
            locator = {"source_id": SRC, "dataset_path": "PSI-99.csv", "row": sample, "column": col}
            if quantity == "other":
                # outcomes.other has no canonical unit; make_quantity() cannot be used.
                # Build the Quantity by hand: value+unit verbatim from the cell, SI computed
                # with pint against the cell's own unit. The validator skips quantity='other'
                # values (contract.py:85), so only the schema shape requirements apply.
                import pint as _pint
                from ignis_contract.units import _pint_unit
                si_unit = "m" if unit == "cm" else "m/s"
                si = float(_pint.Quantity(value, _pint_unit(unit)).to(si_unit).magnitude)
                oc = {"quantity": quantity, "quantity_label": label,
                      "value": {"value": value, "unit": unit, "basis": "reported",
                                "si_value": si, "si_unit": si_unit,
                                "note": "value+unit verbatim from the PSI-99.csv cell."}}
            else:
                oc = {"quantity": quantity, "value": make_quantity(
                    value, unit, f"outcomes.{quantity}",
                    note="value+unit verbatim from the PSI-99.csv cell.")}
            out.append({
                "schema_version": "1.0.0",
                "id": observation_id(locator, quantity, mat),
                "locator": locator,
                "experiment": {"campaign_id": CAMP_1G, "platform": "ground_1g", "run_id": sample},
                "fuel": {"material_id": mat, "phase": "solid", "geometry": "sheet"},
                "conditions": conditions,
                "outcome": oc,
                "extraction": {"method": "dataset_file", "tool": TOOL, "model": "glm-5.3-flash",
                               "extracted_at": now, "confidence": 0.9,
                               "flags": ["condition_from_campaign_nominal"]},
                "qa": {"status": "accepted",
                       "reasons": ["value and unit exact CSV cell match in data/raw/psi/PSI-99.csv"]},
            })
    return out
