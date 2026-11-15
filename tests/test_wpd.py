import io
import json
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "data/raw/ntrs/20210011385.pdf"
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="source PDFs not downloaded")


@pytest.fixture(autouse=True)
def _cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def _reg(name):
    return json.loads((ROOT / f"registry/{name}.json").read_text(encoding="utf-8"))


def _spec():
    return json.loads((ROOT / "digitized/bass2_fig6_10.spec.json").read_text(encoding="utf-8"))


def _cal(tilt=0.0):
    # log x: px 100 -> a=1, px 1100 -> a=100 ; linear y: py 900 -> 13 %, py 100 -> 19 %
    return [{"px": 100, "py": 900, "dx": "1", "dy": "0"}, {"px": 1100, "py": 900 + tilt, "dx": "100", "dy": "0"},
            {"px": 50, "py": 900, "dx": "0", "dy": "13"}, {"px": 50, "py": 100, "dx": "0", "dy": "19"}]


def _project(points, name="ISS stable flame", tilt=0.0, value=None):
    data = [{"x": x, "y": y, **({"value": value} if value else {})} for x, y in points]
    return {"version": [4, 2],
            "axesColl": [{"name": "XY", "type": "XYAxes", "isLogX": True, "isLogY": False, "noRotation": False,
                          "calibrationPoints": _cal(tilt)}],
            "datasetColl": [{"name": name, "axesName": "XY", "data": data}], "measurementColl": []}


def _convert(project, images=None, spec=None):
    from ingest.wpd import observations_from
    sources = {s["id"]: s for s in _reg("sources")}
    return observations_from(spec or _spec(), project, images or {}, sources)


def _bundle(obs):
    return {"schema_version": "1.0.0", "generated_at": "2026-11-15T00:00:00+00:00", "sources": _reg("sources"),
            "campaigns": _reg("campaigns"), "materials": _reg("materials"), "observations": obs}


def test_hand_checked_values_and_production_valid():
    from ignis_contract import check_bundle, is_valid
    obs = _convert(_project([(600, 500)], value=[10.0, 16.0]))   # log midpoint -> a=10, y midpoint -> 16 %
    o = obs[0]
    assert o["conditions"]["o2_mole_fraction"]["si_value"] == pytest.approx(0.16)
    ex = o["conditions"]["extra"][0]
    assert ex["name"] == "stretch_rate" and ex["quantity"]["si_value"] == pytest.approx(10.0)
    assert o["outcome"] == {"quantity": "flame_state", "state": "burns_sustained", "time_basis": "steady"}
    assert "value_from_log_axis" in o["extraction"]["flags"] and o["qa"]["status"] == "accepted"
    assert o["locator"]["series"] == "ISS stable flame" and o["locator"]["point_index"] == 0
    issues = check_bundle(_bundle(obs), production=True)
    assert is_valid(issues), [str(i) for i in issues]


def test_wpd_value_disagreement_rejected():
    from ingest.wpd import DigitizationError
    with pytest.raises(DigitizationError, match="recomputed"):
        _convert(_project([(600, 500)], value=[12.0, 16.0]))


def test_unmapped_dataset_rejected_and_series_overrides_apply():
    from ingest.wpd import DigitizationError
    with pytest.raises(DigitizationError, match="not in spec series"):
        _convert(_project([(600, 500)], name="Default Dataset"))
    dt = _convert(_project([(600, 500)], name="Drop Tower blowoff"))[0]
    assert dt["experiment"]["platform"] == "drop_tower" and dt["conditions"]["gravity"]["basis"] == "campaign_nominal"


def test_tilted_calibration_flags_point():
    o = _convert(_project([(600, 500)], tilt=8.0))[0]
    assert "axis_calibration_residual_high" in o["extraction"]["flags"]
    assert o["qa"]["status"] == "flagged"


def test_image_pinning():
    from ingest.wpd import DigitizationError, load_project
    png = (ROOT / "data/figures/bass2_fig6_10.png").read_bytes()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in (("p/wpd.json", json.dumps(_project([(600, 500)])).encode()), ("p/fig.png", png)):
            ti = tarfile.TarInfo(name); ti.size = len(data); tf.addfile(ti, io.BytesIO(data))
    tmp = ROOT / "data/_test_wpd.tar"
    tmp.write_bytes(buf.getvalue())
    try:
        proj, images = load_project(tmp)
        assert len(_convert(proj, images)) == 1
        with pytest.raises(DigitizationError, match="image inside the WPD project"):
            _convert(proj, {"other.png": (ROOT / "data/figures/saffire5_fig10.png").read_bytes()})
    finally:
        tmp.unlink()
    bad = _spec(); bad["image_sha256"] = "0" * 64
    with pytest.raises(DigitizationError, match="does not match"):
        _convert(_project([(600, 500)]), spec=bad)


def test_saffire_spec_text_checks_pass():
    from ingest.wpd import observations_from
    spec = json.loads((ROOT / "digitized/saffire5_fig10.spec.json").read_text(encoding="utf-8"))
    sources = {s["id"]: s for s in _reg("sources")}
    proj = {"axesColl": [{"name": "opposed", "type": "XYAxes", "calibrationPoints":
                          [{"px": 0, "py": 0, "dx": "0", "dy": "0"}, {"px": 500, "py": 0, "dx": "50", "dy": "0"},
                           {"px": 0, "py": 600, "dx": "0", "dy": "0"}, {"px": 0, "py": 0, "dx": "0", "dy": "0.6"}]}],
            "datasetColl": [{"name": "BASS opposed 2 cm wide", "axesName": "opposed", "data": [{"x": 200, "y": 450}]}]}
    o = observations_from(spec, proj, {}, sources)[0]
    assert o["conditions"]["flow_velocity"]["value"] == pytest.approx(20.0)
    assert o["outcome"]["value"]["value"] == pytest.approx(0.15)
    assert o["conditions"]["flow_direction"] == "opposed" and o["fuel"]["width"]["si_value"] == pytest.approx(0.02)
