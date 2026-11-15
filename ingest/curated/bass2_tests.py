"""BASS-II per-test flame outcomes (BASS-II Summary Report, Appendix A test matrices).

Input: registry/bass2_test_outcomes.json (one row per test whose appendix observation states the outcome;
every quote is verified against the PDF page text here, and again by the build).
O2 per test: data/raw/psi/PSI-25.csv, column "Calibrated final O2 % by vol", matched by "Test #".
Rows whose CSV O2 cell is not a plain number are skipped. Gravity: bass2_report.iss_gravity (ISS nominal).

Flow: final_flow_cm_s is set only where the appendix text gives an explicit cm/s value tied to the extinction.
Pot / fan numbers are potentiometer settings, never velocities.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from ignis_contract import make_quantity, observation_id

from . import require_text
from .bass2_report import iss_gravity

SRC = "ntrs:20210011385"
PSI_SRC = "psi:PSI-25"
PSI_CSV = Path("data/raw/psi/PSI-25.csv")
OUTCOMES = Path("registry/bass2_test_outcomes.json")
TOOL = "curated-transcription@1 (appendix text, verbatim-checked; PSI-25.csv exact cell match)"
MODEL = "claude-haiku-5-5"
CAMPAIGN = "bass-ii"
EXTINCTION_STATES = {"blowoff_extinction", "quench_extinction", "self_extinguished"}
# Extinction-mechanism calls that rest on wording interpretation (not an explicit "quench"/"blew out"): flagged for review.
INTERPRETED = {"self_extinguished", "quench_extinction"}


def _psi_o2(rows: dict[str, dict], test_id: str) -> float | None:
    cell = rows.get(test_id, {}).get("Calibrated final O2 % by vol", "").strip()
    try:
        return float(cell)
    except ValueError:
        return None  # "none", "", or other non-numeric cell: skip the test


def _psi_basis(test_id: str, column: str) -> dict:
    return {"locator": {"source_id": PSI_SRC, "dataset_path": PSI_CSV.name, "row": test_id, "column": column}}


def observations(sources: dict) -> list[dict]:
    assert SRC in sources and PSI_SRC in sources, "required sources missing from registry/sources.json"
    outcomes = json.loads(OUTCOMES.read_text(encoding="utf-8"))
    with PSI_CSV.open(encoding="utf-8-sig", newline="") as f:
        psi = {r["Test #"].strip(): r for r in csv.DictReader(f)}
    g = iss_gravity(sources)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    out = []
    for t in outcomes:
        tid = t["test_id"]
        require_text(sources, SRC, t["page"], t["quote"])
        if t["flow_quote"] is not None:
            require_text(sources, SRC, t["page"], t["flow_quote"])
        o2 = _psi_o2(psi, tid)
        if o2 is None:
            continue

        mat = t["material_id"]
        fuel = {"material_id": mat, "phase": "solid", "geometry": t["geometry"]}
        csv_mat = psi[tid]["Fuel Sample Material"]
        if t["thickness_mm"] is not None:
            fuel["thickness"] = make_quantity(
                t["thickness_mm"], "mm", "fuel.thickness", basis="reported_elsewhere",
                basis_ref=_psi_basis(tid, "Fuel Sample Material"),
                note=f"PSI-25 cell {csv_mat.strip()!r}; micron values converted to mm")
        if t["width_cm"] is not None:
            fuel["width"] = make_quantity(
                t["width_cm"], "cm", "fuel.width", basis="reported_elsewhere",
                basis_ref=_psi_basis(tid, "Fuel Sample Material"))

        conditions = {
            "gravity": g,
            "o2_mole_fraction": make_quantity(
                o2, "percent", "conditions.o2_mole_fraction", basis="reported_elsewhere",
                basis_ref=_psi_basis(tid, "Calibrated final O2 % by vol")),
        }
        if t["flow_direction"]:
            conditions["flow_direction"] = t["flow_direction"]
        if t["final_flow_cm_s"] is not None:
            conditions["flow_velocity"] = make_quantity(t["final_flow_cm_s"], "cm/s", "conditions.flow_velocity")

        # Table-like row key keeps observation ids unique when two tests share a quote (e.g. B10/B11/B13).
        locator = {"source_id": SRC, "page": t["page"], "quote": t["quote"],
                   "table": "Appendix A test matrices", "row": tid}
        state = t["state"]
        outcome = {"quantity": "flame_state", "state": state}
        if state in EXTINCTION_STATES:
            outcome["time_basis"] = "at_extinction"
        interpreted = state in INTERPRETED
        out.append({
            "schema_version": "1.0.0",
            "id": observation_id(locator, "flame_state", mat),
            "locator": locator,
            "experiment": {"campaign_id": CAMPAIGN, "platform": "orbital_iss",
                           "facility": "Microgravity Science Glovebox (MSG)", "run_id": tid},
            "fuel": fuel,
            "conditions": conditions,
            "outcome": outcome,
            "extraction": {"method": "text", "tool": TOOL, "model": MODEL, "extracted_at": now,
                           "confidence": 0.75 if interpreted else 0.9,
                           "flags": ["condition_from_campaign_nominal"]},
            "qa": {"status": "flagged" if interpreted else "accepted",
                   "reasons": [t["rationale"], "quote verified on PDF page text",
                               "O2 from PSI-25.csv exact cell match"]
                   + (["extinction mechanism inferred from wording, not an explicit quench/blowoff term"]
                      if interpreted else [])},
        })
    return out
