"""T3: Saffire-II (PSI-99) curated module + material screen."""
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


# ---------------------------------------------------------------- curated module

def test_observations_valid_and_only_1g():
    from ignis_contract import check_bundle, is_valid, schema_errors
    from ingest.curated.psi_saffire2 import observations
    obs = observations(_sources())
    assert len(obs) == 3  # 2-2 burn length, 2-4 spread rate, 2-5 spread rate
    for o in obs:
        assert not schema_errors(o, "Observation"), schema_errors(o, "Observation")
        assert o["experiment"]["platform"] == "ground_1g"
        assert o["experiment"]["campaign_id"] == "saffire-ii-1g-ref"
        assert o["conditions"]["gravity"]["si_value"] == pytest.approx(9.80665)
        assert o["locator"]["dataset_path"] == "PSI-99.csv"
        # every emitted value exists verbatim as the CSV cell (value + unit)
        row = o["locator"]["row"]
        cell = _cell(row, o["locator"]["column"])
        q = o["outcome"]["value"]
        assert f"{q['value']:g} {q['unit']}" in f"{cell.strip()}"
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


def _cell(row: str, column: str) -> str:
    import csv as _csv
    with (ROOT / "data/raw/psi/PSI-99.csv").open(encoding="utf-8", newline="") as f:
        for r in _csv.DictReader(f):
            if r.get("Sample Number") == row:
                return r[column]
    raise AssertionError(f"row {row} not found")


def test_nonnumeric_cells_skipped():
    from ingest.curated.psi_saffire2 import observations
    obs = observations(_sources())
    labels = {(o["locator"]["row"], o["locator"]["column"]) for o in obs}
    # 'Complete' (2-1/2-4 burn length), 'Acceleratory' (2-4/2-5 rates), '~ 0' etc. must not appear
    assert ("2-1", "1-g Burn Length") not in labels
    assert ("2-5", "1-g Burn Length") not in labels
    assert ("2-4", "1-g Burn Length") not in labels
    # '1.2 mm/s', '0.6 mm/s' and '7.6 cm' are emitted
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

def test_material_screen_table():
    from model.material_screen import table
    rows = table(None)
    by_sample = {r["sample"]: r for r in rows}
    assert {"2-1", "2-2", "2-5"} <= set(by_sample)
    r = by_sample["2-2"]  # silicone thin: ug ~0, 1g 7.6 cm
    assert r["ug_outcome"] == "self_extinguished"
    assert r["ug_burn_length"] == "~ 0"
    assert r["g1_burn_length"] == "7.6 cm"
    assert r["verdict"] == "1g burned, ug did not"
    assert by_sample["2-1"]["verdict"] == "1g and ug agree"
    assert by_sample["2-3"]["verdict"] == "1g and ug agree"
    assert by_sample["2-5"]["ug_outcome"] == "burns_sustained"
    assert by_sample["2-5"]["ug_burn_length"] == "29 cm"
    # verbatim texts come from the CSV
    for r in rows:
        assert r["g1_spread_rate"] == _cell(r["sample"], "1-g Spread Rate").strip()
