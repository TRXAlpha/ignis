"""Per-material microgravity vs 1g comparison table from the Saffire-II (PSI-99) CSV.

Descriptive only: reads data/raw/psi/PSI-99.csv directly (not a model input). The microgravity
columns are quoted verbatim as text; no numeric g-level for the Saffire/Cygnus environment exists
in data/raw/ntrs, so no microgravity observations are emitted (see ingest.curated.psi_saffire2).
"""
from __future__ import annotations

import csv
from pathlib import Path

CSV_PATH = Path("data/raw/psi/PSI-99.csv")

MATERIAL_IDS = {
    "Silicone": "silicone",
    "Cotton-Fiberglass (SIBAL)": "sibal",
    "PMMA": "pmma",
    "PMMA & Nomex": "pmma",  # mixed row: PMMA portion is the modeled material; Nomex noted in ug_burn_length
}


def _burned(ug_text: str) -> bool | None:
    """True if the microgravity burn length indicates spread, False if ~ 0, None if unparseable."""
    t = ug_text.strip().lower()
    if t.startswith("~ 0") or "insignificant" in t or t in ("", "n/a"):
        return False
    # '29 cm', '5 cm & 0 (note 2)', '~ 10 cm (note 3)': a positive length with significant damage
    for part in t.replace("&", " ").split():
        try:
            if float(part) > 0:
                return True
        except ValueError:
            continue
    return None


def table(bundle: dict | None = None) -> list[dict]:
    """One row per PSI-99 sample with a mapped material: ug vs 1g burn text and a verdict."""
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("Sample Number", "").startswith("2-")]
    out = []
    for r in rows:
        mat_raw = r["Material"].strip()
        mat = MATERIAL_IDS.get(mat_raw)
        ug_text = r.get("?-g Burn Length", "").strip()
        g1_text = r.get("1-g Burn Length", "").strip()
        spread_text = r.get("1-g Spread Rate", "").strip()
        if mat is None or not ug_text or not g1_text:
            continue
        ug_burn = _burned(ug_text)
        g1_burned = g1_text.lower() not in ("~ 0", "~ 0 (nomex)") and any(
            c.isdigit() for c in g1_text)
        if ug_burn is None:
            verdict = "insufficient data"
        elif ug_burn and not g1_burned:
            verdict = "1g says no burn, ug burned"
        elif g1_burned and not ug_burn:
            verdict = "1g burned, ug did not"
        else:
            verdict = "1g and ug agree"
        out.append({
            "material_id": mat,
            "sample": r["Sample Number"],
            "ug_outcome": ("burns_sustained" if ug_burn else "self_extinguished") if ug_burn is not None
                          else "unknown",
            "ug_burn_length": ug_text,
            "g1_burn_length": g1_text,
            "g1_spread_rate": spread_text,
            "verdict": verdict,
        })
    return out
