"""Model tests on SYNTHETIC data only (known truth). Real data never appears in these tests."""
import numpy as np

from model.boundary import boundary, fit, min_o2, mutual_information, predict

TRUE = np.array([np.log(5.0), np.log(0.4), 0.02, 13.5, np.log(0.25), np.log(0.2)])


def _synth(n=120, seed=1):
    """Half extinction points measured on the true boundary (+noise), half stable flames on the burning side."""
    rng = np.random.default_rng(seed)
    a = 10 ** rng.uniform(0, 2.2, n)
    B = boundary(a[None], TRUE[None])[0]
    y = (np.arange(n) % 2).astype(float)
    x = np.where(y == 0, B + rng.normal(0, np.exp(TRUE[5]), n), B + rng.uniform(0.1, 3.0, n))
    return a, x, y


def test_recovers_boundary_and_min_o2():
    a, x, y = _synth()
    f = fit(a, x, y)
    assert f.converged
    grid = np.logspace(0, 2.2, 200)
    true_min = boundary(grid[None], TRUE[None])[0].min()
    m = min_o2(f, grid)
    assert m["p05"] - 0.3 <= true_min <= m["p95"] + 0.3
    est = boundary(grid[None], f.theta[None])[0]
    assert np.max(np.abs(est - boundary(grid[None], TRUE[None])[0])) < 0.8


def test_uncertainty_shrinks_with_data_and_info_gain_peaks_on_boundary():
    a, x, y = _synth(30)
    a2, x2, y2 = _synth(300, seed=2)
    pts_a, pts_x = np.array([10.0]), np.array([14.0])
    sd_small = predict(fit(a, x, y), pts_a, pts_x)[1][0]
    sd_big = predict(fit(a2, x2, y2), pts_a, pts_x)[1][0]
    assert sd_big < sd_small
    f = fit(a2, x2, y2)
    b = boundary(np.array([[10.0]]), f.theta[None])[0, 0]
    _, _, ps = predict(f, np.array([10.0, 10.0]), np.array([b, 19.0]))
    mi = mutual_information(ps)
    assert mi[0] > mi[1]


def _rows(n=80, camps=("c1",)):
    a, x, y = _synth(n)
    return [{"id": f"obs_{i:016x}", "campaign": camps[i % len(camps)], "series": "s", "state": "burns_sustained" if yy else
             "blowoff_extinction", "a": aa, "x": xx / 100, "y": yy, "material": "pmma"} for i, (aa, xx, yy) in enumerate(zip(a, x, y))]


def test_export_pieces_schema_valid_and_honest_about_single_campaign():
    from ignis_contract import schema_errors
    from model import export as ex
    rows = _rows()
    f = fit(np.array([r["a"] for r in rows]), np.array([r["x"] for r in rows]) * 100, np.array([r["y"] for r in rows]))
    val = ex.validate(rows, {})
    assert val["folds"] == [] and val["cv"] and "not possible" in val["limitations"][0]
    val2 = ex.validate(_rows(camps=("c1", "c2")), {})
    assert len(val2["folds"]) == 2
    for fold in val2["folds"]:
        assert not schema_errors(fold, "ValidationFold")
    rec = ex.recommend(f, rows)
    assert len(rec["items"]) == 5 and not schema_errors(rec["constraint_set"], "ConstraintSet")
    for it in rec["items"]:
        assert not schema_errors({k: v for k, v in it.items() if k not in ("x", "p_burns")}, "Recommendation")
        assert 0.136 <= it["conditions"]["o2_mole_fraction"] <= 0.222
        assert 0 < it["conditions"]["flow_velocity_m_s"] <= 0.55


def test_habitat_domain_is_the_tested_o2_range(monkeypatch, tmp_path):
    """ISS cabin air (21 % O2) is inside what BASS-II tested (13.6-22.2 %), even though the plotted limit points stop lower."""
    import json
    from model import export as ex
    rows = _rows()
    f = fit(np.array([r["a"] for r in rows]), np.array([r["x"] for r in rows]) * 100, np.array([r["y"] for r in rows]))
    ref = [{"source_id": "web:x", "quote": "q"}]
    presets = [{"id": "cabin", "name": "Cabin", "refs": ref,
                "conditions": {"gravity_m_s2": 2e-5, "o2_mole_fraction": 0.21, "pressure_pa": 101325.0}},
               {"id": "rich", "name": "Rich", "refs": ref,
                "conditions": {"gravity_m_s2": 2e-5, "o2_mole_fraction": 0.30, "pressure_pa": 101325.0}},
               {"id": "moon", "name": "Moon", "refs": ref,
                "conditions": {"gravity_m_s2": 1.62, "o2_mole_fraction": 0.21, "pressure_pa": 101325.0}}]
    p = tmp_path / "habitats.json"
    p.write_text(json.dumps(presets), encoding="utf-8")
    monkeypatch.setattr(ex, "HABITATS", p)
    monkeypatch.setattr(ex, "schema_errors", lambda *a, **k: [])
    got = {h["id"]: h["prediction"]["status"] for h in ex.habitats(f, rows)["presets"]}
    assert got == {"cabin": "ok", "rich": "extrapolation", "moon": "insufficient_data"}
