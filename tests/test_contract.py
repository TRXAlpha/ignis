import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ignis_contract import (FLAT_COLUMNS, check_bundle, flatten_bundle, is_valid, make_quantity, observation_id,
                            schema, schema_errors)
from ignis_contract.__main__ import main as cli

from conftest import SRC


def errors(b, production=False):
    return [i for i in check_bundle(b, production) if i.level == "error"]


def reid(o):
    o["id"] = observation_id(o["locator"], o["outcome"]["quantity"], o["fuel"]["material_id"])
    return o


# ---- the schema itself ---------------------------------------------------------------------

def test_schema_is_valid_draft2020():
    Draft202012Validator.check_schema(schema())


def test_fixture_bundle_is_valid(bundle):
    issues = check_bundle(bundle)
    assert is_valid(issues), [str(i) for i in issues]


def test_production_rejects_synthetic(bundle):
    errs = errors(bundle, production=True)
    assert any("synthetic" in e.msg for e in errs)


# ---- provenance ----------------------------------------------------------------------------

def test_locator_must_point_somewhere(bundle):
    bundle["observations"][0]["locator"] = {"source_id": SRC}
    assert errors(bundle)


def test_unknown_source_rejected(bundle):
    o = bundle["observations"][0]
    o["locator"]["source_id"] = "ntrs:999999999"
    reid(o)
    assert any("unknown source" in e.msg for e in errors(bundle))


def test_nonreported_basis_requires_ref(bundle):
    del bundle["observations"][0]["conditions"]["gravity"]["basis_ref"]
    assert errors(bundle)


def test_material_property_requires_ref_even_if_reported(bundle):
    del bundle["materials"][0]["properties"]["density"]["basis_ref"]
    assert errors(bundle)


def test_gravity_is_mandatory(bundle):
    del bundle["observations"][0]["conditions"]["gravity"]
    assert errors(bundle)


def test_plot_digitized_needs_calibration(bundle):
    del bundle["observations"][0]["extraction"]["digitization"]
    assert errors(bundle)


def test_plot_digitized_needs_point_index(bundle):
    o = bundle["observations"][0]
    del o["locator"]["point_index"]
    reid(o)
    assert errors(bundle)


def test_table_needs_row(bundle, make_obs):
    o = make_obs(locator={"source_id": SRC, "table": "2", "page": 6})
    o["extraction"]["method"] = "table"
    del o["extraction"]["digitization"]
    bundle["observations"] = [o]
    assert errors(bundle)
    o["locator"]["row"] = "3"
    reid(o)
    assert not errors(bundle), [str(e) for e in errors(bundle)]


def test_text_needs_quote(bundle, make_obs):
    o = make_obs(locator={"source_id": SRC, "page": 3})
    o["extraction"]["method"] = "text"
    del o["extraction"]["digitization"]
    bundle["observations"] = [o]
    assert errors(bundle)


# ---- numbers can't lie ---------------------------------------------------------------------

def test_tampered_si_value_caught(bundle):
    bundle["observations"][0]["outcome"]["value"]["si_value"] *= 10
    assert any("recomputed" in e.msg for e in errors(bundle))


def test_wrong_canonical_unit_caught(bundle):
    q = bundle["observations"][0]["conditions"]["pressure"]
    q["si_unit"], q["si_value"] = "kPa", q["si_value"] / 1000
    assert any("canonical" in e.msg for e in errors(bundle))


def test_incompatible_unit_caught(bundle):
    q = bundle["observations"][0]["conditions"]["flow_velocity"]
    q["unit"] = "kPa"
    assert errors(bundle)


def test_impossible_value_is_error_even_if_flagged(bundle):
    o = bundle["observations"][0]
    o["conditions"]["o2_mole_fraction"] = make_quantity(130, "%", "conditions.o2_mole_fraction")
    o["extraction"]["flags"].append("out_of_plausible_range")
    o["qa"] = {"status": "flagged"}
    assert any("impossible" in e.msg for e in errors(bundle))


def test_implausible_value_needs_flag(bundle):
    o = bundle["observations"][0]
    o["outcome"]["value"] = make_quantity(900, "mm/s", "outcomes.flame_spread_rate")
    assert any("plausible" in e.msg for e in errors(bundle))
    o["extraction"]["flags"].append("out_of_plausible_range")
    o["qa"] = {"status": "flagged"}
    assert not errors(bundle)


def test_transform_requires_derived_basis(bundle):
    o = bundle["observations"][0]
    q = make_quantity(21.2, "kPa", "conditions.o2_mole_fraction", basis="derived",
                      basis_ref={"formula": "o2_partial_pressure_to_mole_fraction", "inputs": ["conditions.pressure"]},
                      transform="o2_partial_pressure_to_mole_fraction",
                      context={"pressure_si": o["conditions"]["pressure"]["si_value"]})
    o["conditions"]["o2_mole_fraction"] = q
    assert not errors(bundle), [str(e) for e in errors(bundle)]
    q["basis"] = "reported"
    assert any("transform" in e.msg for e in errors(bundle))


# ---- QA gating -----------------------------------------------------------------------------

def test_low_confidence_cannot_be_accepted(bundle):
    bundle["observations"][0]["extraction"]["confidence"] = 0.5
    assert any("confidence" in e.msg for e in errors(bundle))
    bundle["observations"][0]["qa"] = {"status": "flagged", "reasons": ["digitizer unsure"]}
    assert not errors(bundle)


def test_blocking_flag_cannot_be_accepted(bundle):
    bundle["observations"][0]["extraction"]["flags"].append("overlapping_markers")  # non-blocking
    assert not errors(bundle)
    bundle["observations"][0]["extraction"]["flags"].append("ocr_uncertain")       # blocking
    assert any("blocking" in e.msg for e in errors(bundle))


def test_human_verified_needs_reviewer(bundle):
    bundle["observations"][0]["qa"] = {"status": "human_verified"}
    assert errors(bundle)
    bundle["observations"][0]["extraction"]["reviewer"] = "cm"
    assert not errors(bundle)


def test_flagged_needs_reason(bundle):
    o = bundle["observations"][0]
    o["extraction"]["flags"] = []
    o["qa"] = {"status": "flagged"}
    assert any("without reasons" in e.msg for e in errors(bundle))


def test_nominal_without_flag_warns(bundle):
    bundle["observations"][0]["extraction"]["flags"] = []
    issues = check_bundle(bundle)
    assert is_valid(issues) and any(i.level == "warning" for i in issues)


# ---- outcome shape -------------------------------------------------------------------------

def test_flame_state_is_categorical(bundle, make_obs):
    o = make_obs()
    o["outcome"] = {"quantity": "flame_state", "state": "blowoff_extinction"}
    reid(o)
    bundle["observations"] = [o]
    assert not errors(bundle), [str(e) for e in errors(bundle)]
    o["outcome"]["value"] = make_quantity(1, "mm/s", "outcomes.flame_spread_rate")
    assert errors(bundle)


def test_numeric_outcome_needs_value(bundle):
    del bundle["observations"][0]["outcome"]["value"]
    assert errors(bundle)


def test_unknown_field_rejected(bundle):
    bundle["observations"][0]["conditions"]["humidity"] = 0.5
    assert errors(bundle)


# ---- ids -----------------------------------------------------------------------------------

def test_id_is_deterministic_and_value_independent(bundle):
    o = bundle["observations"][0]
    before = o["id"]
    o["outcome"]["value"] = make_quantity(2.0, "mm/s", "outcomes.flame_spread_rate")
    assert reid(o)["id"] == before
    o["locator"]["point_index"] = 1
    assert reid(o)["id"] != before


def test_wrong_id_caught(bundle):
    bundle["observations"][0]["id"] = "obs_" + "f" * 16
    assert any("deterministic" in e.msg for e in errors(bundle))


def test_duplicate_observation_caught(bundle):
    bundle["observations"].append(bundle["observations"][0])
    assert any("duplicate" in e.msg for e in errors(bundle))


# ---- model-facing outputs ------------------------------------------------------------------

def test_flatten(bundle):
    rows = flatten_bundle(bundle)
    assert len(rows) == 1 and list(rows[0]) == FLAT_COLUMNS
    r = rows[0]
    assert r["value_si"] == pytest.approx(0.0015)
    assert r["sd_si"] == pytest.approx(0.00015)
    assert r["flow_velocity_m_s"] == pytest.approx(0.05)
    assert r["nominal_condition_fields"] == "gravity"
    assert r["year"] == 2020


def test_flatten_excludes_untrusted(bundle):
    bundle["observations"][0]["qa"] = {"status": "flagged", "reasons": ["x"]}
    assert flatten_bundle(bundle) == []
    assert len(flatten_bundle(bundle, statuses=None)) == 1


def test_prediction_insufficient_data_has_no_number():
    p = {"model_id": "gp", "model_version": "0", "material_id": "pmma", "outcome_quantity": "flame_spread_rate",
         "conditions": {"gravity_m_s2": 1.62, "o2_mole_fraction": 0.34, "pressure_pa": 56500},
         "status": "insufficient_data", "mean_si": None,
         "ood": {"in_domain": False, "score": 9.1, "method": "mahalanobis"}, "evidence_observation_ids": []}
    assert not schema_errors(p, "Prediction")
    p["mean_si"] = 0.001
    assert schema_errors(p, "Prediction")


def test_prediction_ok_needs_interval():
    p = {"model_id": "gp", "model_version": "0", "material_id": "pmma", "outcome_quantity": "flame_spread_rate",
         "conditions": {"gravity_m_s2": 0}, "status": "ok", "mean_si": 0.001,
         "ood": {"in_domain": True, "score": 0.3, "method": "mahalanobis"}, "evidence_observation_ids": []}
    assert schema_errors(p, "Prediction")
    p["interval"] = {"level": 0.9, "lower_si": 0.0005, "upper_si": 0.002}
    assert not schema_errors(p, "Prediction")


def test_constraint_set_and_preset_need_refs():
    cs = {"id": "iss-msg", "name": "MSG", "platform": "orbital_iss", "ranges": {"flow_velocity_m_s": [0, 0.5]}, "refs": []}
    assert schema_errors(cs, "ConstraintSet")
    hp = {"id": "iss", "name": "ISS", "conditions": {"gravity_m_s2": 0}, "refs": [{"source_id": "web:x", "page": 1}]}
    assert not schema_errors(hp, "HabitatPreset")


def test_cli(tmp_path, bundle, capsys):
    p = tmp_path / "b.json"
    p.write_text(json.dumps(bundle))
    assert cli(["validate", str(p)]) == 0
    assert cli(["validate", str(p), "--production"]) == 1
    assert cli(["flatten", str(p)]) == 0
    out = capsys.readouterr().out
    assert ",".join(FLAT_COLUMNS) in out


def test_example_bundle_in_repo_validates():
    p = Path(__file__).resolve().parent.parent / "contract" / "examples" / "bundle.synthetic.json"
    assert is_valid(check_bundle(json.loads(p.read_text(encoding="utf-8"))))


def test_extra_quantity_si_is_rechecked(bundle):
    """conditions.extra (e.g. stretch rate, the model's x axis) has no canonical field but must still be consistent."""
    from ignis_contract.units import extra_si
    si, unit = extra_si(12.0, "1/s")
    o = bundle["observations"][0]
    o["conditions"]["extra"] = [{"name": "stretch_rate", "quantity": {"value": 12.0, "unit": "1/s", "si_value": si,
                                                                       "si_unit": unit, "basis": "reported"}}]
    assert not errors(bundle), [str(e) for e in errors(bundle)]
    o["conditions"]["extra"][0]["quantity"]["si_value"] = si * 10
    assert any("recomputed" in e.msg for e in errors(bundle))
    o["conditions"]["extra"][0]["quantity"].update(si_value=si, si_unit="kg")
    assert any("si_unit" in e.msg for e in errors(bundle))
