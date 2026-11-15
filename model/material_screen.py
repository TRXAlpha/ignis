"""Per-material microgravity vs 1g comparison table from the Saffire-II (PSI-99) CSV.

Descriptive only: reads data/raw/psi/PSI-99.csv directly (not a model input). Cells are quoted
verbatim; no microgravity observations are emitted (see ingest.curated.psi_saffire2).
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

CSV_PATH = Path("data/raw/psi/PSI-99.csv")

MATERIAL_IDS = {
    "Silicone": "silicone",
    "Cotton-Fiberglass (SIBAL)": "sibal",
    "PMMA": "pmma",
}
MIXED = "PMMA & Nomex"  # sample 2-7: two materials, split into two rows

_LENGTH = re.compile(r"~?\s*(\d+(?:\.\d+)?)\s*cm\b")
_ZERO = re.compile(r"~?\s*0(?:\s|$)")


def burned(cell: str | None) -> bool | None:
    """True for 'Complete' or a positive length, False for '~ 0' / '0', None otherwise."""
    if cell is None:
        return None
    t = cell.strip()
    if t == "Complete":
        return True
    m = _LENGTH.match(t)
    if m:
        return float(m.group(1)) > 0
    if _ZERO.match(t):
        return False
    return None


def _verdict(material_id: str | None, ug: bool | None, g1: bool | None) -> str:
    if material_id is None:
        return "material not stated in table"
    if ug is None or g1 is None:
        return "insufficient"
    if ug and g1:
        return "both burned"
    if not ug and not g1:
        return "neither burned"
    return "1g burned, ug did not" if g1 else "ug burned, 1g did not"


def _row(r: dict, material_id: str | None, ug_text: str, g1_text: str | None,
         note: str | None = None) -> dict:
    ug = burned(ug_text)
    g1 = burned(g1_text)
    return {
        "material_id": material_id,
        "sample": r["Sample Number"],
        "material_raw": r["Material"].strip(),
        "o2_text": r["Percent O2 (Note 1)"].strip(),
        "flow_cm_s": r["Air Flow (cm/s)"].strip(),
        "flow_direction": r["Flow Direction"].strip(),
        "ug_outcome": "burns_sustained" if ug else "self_extinguished" if ug is False else "unknown",
        "ug_cell_raw": r["?-g Burn Length"].strip(),
        "ug_burn_length": ug_text,
        "ug_burned": ug,
        "g1_burn_length": g1_text,
        "g1_burned": g1,
        "g1_spread_rate": r["1-g Spread Rate"].strip(),
        "verdict": _verdict(material_id, ug, g1),
        "note": note,
    }


def notes() -> list[str]:
    """The PSI-99 'Note N' lines (N = 1..4), verbatim from the CSV."""
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        return [r["Sample Number"].strip() for r in csv.DictReader(f)
                if re.match(r"Note [1-4] ", r["Sample Number"])]


def table(bundle: dict | None = None) -> list[dict]:
    """One row per PSI-99 sample (2-x), mixed-material rows split. Blank Material is not inferred."""
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        all_rows = list(csv.DictReader(f))
    note2 = next(r["Sample Number"].strip() for r in all_rows
                 if r["Sample Number"].startswith("Note 2 "))
    out = []
    for r in all_rows:
        if not r["Sample Number"].startswith("2-"):
            continue
        raw_mat = r["Material"].strip()
        ug_cell = r["?-g Burn Length"].strip()
        g1_cell = r["1-g Burn Length"].strip()
        if raw_mat == MIXED:
            # 1-g cells describe only the Nomex portion; PMMA 1-g is unknown.
            pmma_ug, nomex_ug = (p.strip() for p in ug_cell.split("&", 1))
            out.append(_row(r, "pmma", pmma_ug, None, note=note2))
            out.append(_row(r, "nomex", nomex_ug, g1_cell, note=note2))
        elif raw_mat == "":
            out.append(_row(r, None, ug_cell, g1_cell))
        elif raw_mat in MATERIAL_IDS:
            out.append(_row(r, MATERIAL_IDS[raw_mat], ug_cell, g1_cell))
        else:
            raise ValueError(f"unmapped material {raw_mat!r} in sample {r['Sample Number']}")
    return out
