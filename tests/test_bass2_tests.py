import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "data/raw/ntrs/20210011385.pdf"
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="source PDFs not downloaded")

STATES = {"burns_sustained", "blowoff_extinction", "quench_extinction", "radiative_extinction",
          "self_extinguished", "no_ignition"}


@pytest.fixture(autouse=True)
def _cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _sources():
    return {s["id"]: s for s in json.loads((ROOT / "registry/sources.json").read_text(encoding="utf-8"))}


def _outcomes():
    return json.loads((ROOT / "registry/bass2_test_outcomes.json").read_text(encoding="utf-8"))


def _materials():
    return {m["id"] for m in json.loads((ROOT / "registry/materials.json").read_text(encoding="utf-8"))}


def test_every_quote_is_on_its_pdf_page():
    from ingest.curated import require_text
    src = _sources()
    rows = _outcomes()
    assert len(rows) >= 50
    for r in rows:
        require_text(src, "ntrs:20210011385", r["page"], r["quote"])
        if r["flow_quote"] is not None:
            require_text(src, "ntrs:20210011385", r["page"], r["flow_quote"])


def test_registry_fields_are_consistent():
    ids = set()
    psi = {r["Test #"].strip(): r for r in csv.DictReader(open(ROOT / "data/raw/psi/PSI-25.csv", encoding="utf-8-sig"))}
    for r in _outcomes():
        assert r["test_id"] not in ids
        ids.add(r["test_id"])
        assert r["state"] in STATES
        assert r["material_id"] in _materials()
        # O2 must be a plain number in the PSI table for every classified test
        float(psi[r["test_id"]]["Calibrated final O2 % by vol"])
        # a flow number is only allowed when the quoted text says cm/s (pot values are not velocities)
        if r["final_flow_cm_s"] is not None:
            assert "cm/s" in r["flow_quote"]
        else:
            assert r["flow_quote"] is None


def test_observations_are_schema_valid_and_unique():
    from ignis_contract import schema_errors
    from ingest.curated.bass2_tests import observations
    obs = observations(_sources())
    assert len(obs) == len(_outcomes())
    assert len({o["id"] for o in obs}) == len(obs)
    for o in obs:
        assert schema_errors(o, "Observation") == [], o["id"]
        assert o["outcome"]["quantity"] == "flame_state"
        assert "value" not in o["outcome"]
        assert o["conditions"]["o2_mole_fraction"]["basis"] == "reported_elsewhere"


def test_flow_velocity_only_where_stated():
    from ingest.curated.bass2_tests import observations
    obs = observations(_sources())
    with_flow = [o for o in obs if "flow_velocity" in o["conditions"]]
    assert with_flow, "expected at least one explicit cm/s extinction flow"
    for o in with_flow:
        assert o["conditions"]["flow_velocity"]["unit"] == "cm/s"
        assert o["conditions"]["flow_velocity"]["basis"] == "reported"


def test_non_numeric_o2_is_skipped():
    from ingest.curated.bass2_tests import _psi_o2
    rows = {"F3": {"Calibrated final O2 % by vol": "none"}, "B1": {"Calibrated final O2 % by vol": "22.2"}}
    assert _psi_o2(rows, "F3") is None
    assert _psi_o2(rows, "B1") == 22.2


def test_bundle_builds_production_valid():
    from ignis_contract import check_bundle, is_valid
    from ingest.build_bundle import build
    b = build()
    issues = check_bundle(b, production=True)
    assert is_valid(issues), [str(i) for i in issues]
