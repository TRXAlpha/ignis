"""BASS-II Summary Report (NASA/TM-20210011385), Table 2.1, 'Experiment' column only.

Computation and Theory columns are model output, not measurements: deliberately not ingested.
PDF page numbers are 1-based physical pages (Table 2.1 is printed page 28 = PDF page 36).
"""
from __future__ import annotations

from datetime import datetime, timezone

from ignis_contract import make_quantity, observation_id

from . import require_text

SRC = "ntrs:20210011385"
PIMS = "ntrs:20030067701"
TOOL = "curated-transcription@1 (pymupdf text layer, verbatim-checked)"

ISS_G_REF = {"locator": {"source_id": PIMS, "page": 45,
                         "quote": "magnitudes expected to be on the order of 2 µg or less"}}


def iss_gravity(sources: dict) -> dict:
    require_text(sources, PIMS, 45, "The quasi-steady regime is comprised of accelerations with frequency content below 0.01 Hz",
                 "magnitudes expected to be on the order of 2 µg or less")
    return make_quantity(2, "µg", "conditions.gravity", basis="campaign_nominal", basis_ref=ISS_G_REF,
                         note="Upper bound for the ISS quasi-steady environment (PIMS Increment-4/5, 2001-2002); "
                              "BASS-II flew later, so treat as order of magnitude.")


def observations(sources: dict) -> list[dict]:
    caption = "COMPARISON OF EXTINCTION VELOCITY Vg,cr FOR THIN POLYMETHYLMETHACRYLATE AT 1 atm"
    require_text(sources, SRC, 36, caption, "Experiment", "Computation")
    g = iss_gravity(sources)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    rows = [("21", 21, 10, 5), ("16", 16, 30, 5)]  # (row label, O2 %, Vg,cr mm/s, +/- mm/s)
    out = []
    for row, o2, v, pm in rows:
        # Adjacent cells in the text layer: "<O2> <exp>±<pm>" proves the value belongs to that O2 row.
        require_text(sources, SRC, 36, f"{o2} {v}±{pm}")
        locator = {"source_id": SRC, "page": 36, "table": "2.1", "row": row, "column": "Experiment",
                   "quote": f"{caption} | O2 {o2} percent | Experiment {v}±{pm} mm/s"}
        out.append({
            "schema_version": "1.0.0",
            "id": observation_id(locator, "extinction_flow_velocity", "pmma"),
            "locator": locator,
            "experiment": {"campaign_id": "bass-ii", "platform": "orbital_iss",
                           "facility": "Microgravity Science Glovebox (MSG)"},
            "fuel": {"material_id": "pmma", "phase": "solid", "geometry": "sheet"},
            "conditions": {
                "gravity": g,
                "o2_mole_fraction": make_quantity(o2, "percent", "conditions.o2_mole_fraction"),
                "pressure": make_quantity(1, "atm", "conditions.pressure"),
                "flow_direction": "opposed",
                "buoyancy_orientation": "not_applicable",
            },
            "outcome": {
                "quantity": "extinction_flow_velocity",
                "value": make_quantity(v, "mm/s", "outcomes.extinction_flow_velocity", uncertainty={
                    "kind": "half_width", "lower_si": (v - pm) / 1000, "upper_si": (v + pm) / 1000,
                    "reported_text": f"{v}±{pm}"}),
                "time_basis": "at_extinction",
            },
            "extraction": {"method": "table", "tool": TOOL, "model": "claude-opus-5-5", "extracted_at": now,
                           "confidence": 0.9, "flags": ["condition_from_campaign_nominal"]},
            "qa": {"status": "accepted",
                   "reasons": ["value, row label and caption matched verbatim in PDF text layer"]},
        })
    return out


# Geometry 'sheet': section 2.2 studies thin PMMA sheets (e.g. p30 '100-µm-thick PMMA sheet').
# Thickness omitted on purpose: Table 2.1 pools four thicknesses (p31: extinction velocity independent of thickness).
