"""Regression test on the real pinned figure: counts checked by eye against BASS-II Fig 6.10 overlay review."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _cwd(monkeypatch):
    monkeypatch.chdir(ROOT)


def test_fig6_10_counts_and_calibration():
    from ingest.autodigitize import run
    from ingest.wpd import XYAxes
    p = run("bass2_fig6_10")
    n = {d["name"]: len(d["data"]) for d in p["datasetColl"]}
    assert n["ISS stable flame"] == 27 and n["ISS quench"] == 8
    assert 14 <= n["ISS blowoff"] <= 17          # >= 2 X's hidden behind diamonds are not recoverable
    assert n["Drop Tower blowoff"] == 9 and n["Drop Tower stable flame"] == 13
    ax = XYAxes(p["axesColl"][0])
    assert ax.residual_px < 1
    # minor tick at a = 2 and major y tick 16 % must land on their values (independent of calibration ticks used)
    assert ax.pixel_to_data(317.87, 673.38)[0] == pytest.approx(2.0, rel=0.01)
    assert ax.pixel_to_data(317.87, 673.38)[1] == pytest.approx(16.0, abs=0.02)


def test_saffire5_fig10_counts_and_split_axis():
    from ingest.autodigitize import run
    from ingest.wpd import XYAxes
    p = run("saffire5_fig10")
    n = {d["name"]: len(d["data"]) for d in p["datasetColl"]}
    assert n == {"BASS concurrent 2 cm wide": 5, "BASS concurrent 1 cm wide": 2, "BASS opposed 2 cm wide": 9}
    ax = {a["name"]: XYAxes(a) for a in p["axesColl"]}
    # 20 cm/s ticks on each side (not used for calibration) land on +20
    assert ax["concurrent"].pixel_to_data(311, 430)[0] == pytest.approx(20, abs=0.2)
    assert ax["opposed"].pixel_to_data(718, 546)[0] == pytest.approx(20, abs=0.2)
