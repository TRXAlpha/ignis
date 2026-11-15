"""T3/T3b: Saffire-II (PSI-99) curated module + material screen."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(
    not (ROOT / "data/raw/psi/PSI-99.csv").exists(), reason="PSI-99.csv not downloaded")


@pytest.fixture(autouse=True)
def _cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _sources():
    return {s["id"]: s for s in json.loads(
        (ROOT / "registry/sources.json").read_text(encoding="utf-8"))}


def _cell(row: str, column: str) -> str:
    import csv as _csv
    with (ROOT / "data/raw/psi/PSI-99.csv").open(encoding="utf-8", newline="") as f:
        for r in _csv.DictReader(f):
            if r.get("Sample Number") == row:
                return r[column]
    raise AssertionError(f"row {row} not found")


# ---------------------------------------------------------------- curated module

def test_observations_valid_and_only_1g():
    from ignis_contract import check_bundle, is_valid, schema_errors
    from ingest.curated.psi_saffire2 import observations
    obs = observations(_sources())
    assert len(obs) == 3  # 2-2 burn length, 2-2 spread rate, 2-4 spread rate
    for o in obs:
        assert not schema_errors(o, "Observation"), schema_errors(o, "Observation")
        assert o["experiment"]["platform"] == "ground_1g"
        assert o["experiment"]["campaign_id"] == "saffire-ii-1g-ref"
        assert o["conditions"]["gravity"]["si_value"] == pytest.approx(9.80665)
        assert o["locator"]["dataset_path"] == "PSI-99.csv"
    # microgravity rows are not emitted (no sourced g-level)
    assert all("orbital" not in o["experiment"]["platform"] for o in obs)
    # full-bundle check with only these observations added on top of a minimal registry index
    bundle = {
        "schema_version": "1.0.0", "generated_at": "2026-11-15T00:00:00+00:00",
        "sources": json.loads((ROOT / "registry/sources.json").read_text(encoding="utf-8")),
        "campaigns": json.loads((ROOT / "registry/campaigns.json").read_text(encoding="utf-8")),
        "materials": json.loads((ROOT / "registry/materials.json").read_text(encoding="utf-8")),
        "observations": obs,
    }
    assert is_valid(check_bundle(bundle, production=True)), [str(i) for i in check_bundle(bundle)]


def test_every_observation_matches_its_csv_cell_exactly():
    """Locator (row, column) is read by name from the CSV; the emitted value+unit must equal that cell."""
    from ingest.curated.psi_saffire2 import observations
    obs = observations(_sources())
    assert obs
    for o in obs:
        loc = o["locator"]
        parts = _cell(loc["row"], loc["column"]).split()
        q = o["outcome"]["value"]
        assert len(parts) == 2, (loc, parts)
        assert float(parts[0]) == q["value"], (loc, parts, q)
        assert parts[1] == q["unit"], (loc, parts, q)
    by = {(o["locator"]["row"], o["locator"]["column"]): o["outcome"]["value"] for o in obs}
    assert by[("2-2", "1-g Spread Rate")]["value"] == 1.2
    assert by[("2-2", "1-g Spread Rate")]["unit"] == "mm/s"
    assert by[("2-4", "1-g Spread Rate")]["value"] == 0.6
    assert not any(o["locator"]["row"] == "2-5" for o in obs)  # 2-5 1-g cells: 'Complete', 'Acceleratory'


def test_nonnumeric_cells_skipped():
    from ingest.curated.psi_saffire2 import observations
    obs = observations(_sources())
    labels = {(o["locator"]["row"], o["locator"]["column"]) for o in obs}
    # 'Complete' (2-1/2-4 burn length), 'Acceleratory' (2-4/2-5 rates), '~ 0' etc. must not appear
    assert ("2-1", "1-g Burn Length") not in labels
    assert ("2-5", "1-g Burn Length") not in labels
    assert ("2-4", "1-g Burn Length") not in labels
    # '1.2 mm/s' (row 2-2), '0.6 mm/s' (row 2-4) and '7.6 cm' (row 2-2) are emitted
    assert ("2-2", "1-g Burn Length") in labels
    assert ("2-2", "1-g Spread Rate") in labels
    assert ("2-4", "1-g Spread Rate") in labels
    # 2-5's 1-g Spread Rate cell is 'Acceleratory' (qualitative): not emitted
    assert ("2-5", "1-g Spread Rate") not in labels


def test_campaigns_registered():
    camps = {c["id"] for c in json.loads(
        (ROOT / "registry/campaigns.json").read_text(encoding="utf-8"))}
    assert {"saffire-ii", "saffire-ii-1g-ref"} <= camps


# ---------------------------------------------------------------- material screen

EXPECTED_VERDICTS = {
    ("2-1", "silicone"): "1g burned, ug did not",
    ("2-2", "silicone"): "1g burned, ug did not",
    ("2-3", "silicone"): "neither burned",
    ("2-4", "silicone"): "1g burned, ug did not",
    ("2-5", "sibal"): "both burned",
    ("2-6", None): "material not stated in table",
    ("2-7", "pmma"): "insufficient",
    ("2-7", "nomex"): "neither burned",
    ("2-8", "pmma"): "both burned",
    ("2-9", None): "material not stated in table",
}


def test_burned_cell_rules():
    from model.material_screen import burned
    assert burned("Complete") is True
    assert burned("29 cm") is True
    assert burned("~ 10 cm (note 3)") is True
    assert burned("7.6 cm") is True
    assert burned("~ 0") is False
    assert burned("0") is False
    assert burned("0 (note 2)") is False
    assert burned("~ 0 (Nomex)") is False
    assert burned("n/a (Nomex)") is None
    assert burned("Note 4") is None
    assert burned("") is None


def test_material_screen_verdicts():
    from model.material_screen import table
    rows = table(None)
    got = {(r["sample"], r["material_id"]): r["verdict"] for r in rows}
    assert got == EXPECTED_VERDICTS
    by = {(r["sample"], r["material_id"]): r for r in rows}
    r = by[("2-2", "silicone")]
    assert r["ug_outcome"] == "self_extinguished"
    assert r["ug_burn_length"] == "~ 0"
    assert r["g1_burn_length"] == "7.6 cm"
    assert by[("2-5", "sibal")]["ug_outcome"] == "burns_sustained"
    assert by[("2-5", "sibal")]["ug_burn_length"] == "29 cm"
    # blank Material rows are not inferred
    assert by[("2-6", None)]["material_raw"] == ""
    assert by[("2-9", None)]["material_raw"] == ""
    # mixed row: Note 2 quoted verbatim on both halves; Nomex ug is the '& 0' part
    note2 = "The PMMA portion was completely consumed but the Nomex was not ignited."
    assert note2 in by[("2-7", "pmma")]["note"]
    assert note2 in by[("2-7", "nomex")]["note"]
    assert by[("2-7", "pmma")]["ug_burn_length"] == "5 cm"
    assert by[("2-7", "pmma")]["g1_burned"] is None
    assert by[("2-7", "nomex")]["ug_burn_length"] == "0 (note 2)"
    assert by[("2-7", "nomex")]["g1_burn_length"] == "~ 0 (Nomex)"
    # verbatim texts come from the CSV, on every row
    for r in rows:
        assert r["g1_spread_rate"] == _cell(r["sample"], "1-g Spread Rate").strip()
        assert r["o2_text"] == _cell(r["sample"], "Percent O2 (Note 1)").strip()
        assert r["flow_cm_s"] == _cell(r["sample"], "Air Flow (cm/s)").strip()
        assert r["flow_direction"] == _cell(r["sample"], "Flow Direction").strip()
        assert r["ug_cell_raw"] == _cell(r["sample"], "?-g Burn Length").strip()


def test_nomex_registered():
    mats = {m["id"] for m in json.loads(
        (ROOT / "registry/materials.json").read_text(encoding="utf-8"))}
    assert "nomex" in mats


def test_notes_are_verbatim_csv_lines():
    from model.material_screen import notes
    n = notes()
    assert [x.split()[1] for x in n] == ["1", "2", "3", "4"]
    assert n[1] == "Note 2 The PMMA portion was completely consumed but the Nomex was not ignited."
