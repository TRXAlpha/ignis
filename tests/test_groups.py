"""T4: multi-group fits in model/export.py, tested on SYNTHETIC rows only."""
from __future__ import annotations

import numpy as np
import pytest

from ignis_contract import schema_errors
from model import export as ex


TRUE = np.array([np.log(5.0), np.log(0.4), 0.02, 13.5, np.log(0.25), np.log(0.2)])


def _synth(n=80, seed=1):
    """Half extinction points measured on the true boundary (+noise), half stable flames above it."""
    rng = np.random.default_rng(seed)
    a = 10 ** rng.uniform(0, 2.2, n)
    from model.boundary import boundary
    B = boundary(a[None], TRUE[None])[0]
    y = (np.arange(n) % 2).astype(float)
    x = np.where(y == 0, B + rng.normal(0, 0.2, n), B + rng.uniform(0.1, 3.0, n))
    return a, x, y


def _row(i, a, x, y, material, geometry, flow, x_var, campaign):
    state = "burns_sustained" if y == 1 else "blowoff_extinction"
    return {"id": f"obs_{i:016x}", "campaign": campaign, "series": "s", "state": state,
            "a": a, "x": x / 100, "y": y, "material": material,
            "key": (material, geometry, flow, x_var)}


def _bundle_rows(n1=40, n2=30, n3=5):
    """Two big groups (different geometry, same pmma/concurrent/stretch_rate) + one too-small group."""
    out = []
    i = 0
    for n, geo in ((n1, "rod"), (n2, "sheet")):
        a, x, y = _synth(n, seed=len(out) + 1)
        for aa, xx, yy in zip(a, x, y):
            out.append(_row(i, float(aa), float(xx), yy, "pmma", geo, "concurrent", "stretch_rate",
                            "camp-a" if i % 2 == 0 else "camp-b"))
            i += 1
    a, x, y = _synth(max(n3, 6), seed=9)  # small third group (fabric), same campaign
    for j, (aa, xx, yy) in enumerate(zip(a[:n3], x[:n3], y[:n3])):
        out.append(_row(i, float(aa), float(xx), yy, "sibal", "fabric", "opposed", "flow_velocity", "camp-a"))
        i += 1
    return out


def _bundle(rows):
    return {"observations": [{"qa": {"status": "accepted"}, "outcome": {"quantity": "flame_state", "state": r["state"]},
                              "conditions": {"o2_mole_fraction": {"si_value": r["x"]}, "flow_direction": r["key"][2],
                                             "extra": [{"name": r["key"][3],
                                                        "quantity": {"si_value": r["a"] / 100 if r["key"][3] == "flow_velocity"
                                                                     else r["a"]}}]},
                              "fuel": {"material_id": r["key"][0], "geometry": r["key"][1]},
                              "experiment": {"campaign_id": r["campaign"]},
                              "locator": {"series": r["series"]},
                              "id": r["id"]} for r in rows]}


def test_groups_and_skipped():
    rows = _bundle_rows()
    bundle = _bundle(rows)
    all_rows = ex.flame_rows(bundle)
    assert len(all_rows) == len(rows)
    fitted, skipped = [], []
    for key in sorted({r["key"] for r in all_rows}, key=lambda k: [str(v) for v in k]):
        grows = [r for r in all_rows if r["key"] == key]
        g = ex.fit_group(grows)
        (fitted if g is not None else skipped).append((key, g or grows))
    assert len(fitted) == 2
    assert {g["key"]["geometry"] for _, g in fitted} == {"rod", "sheet"}
    assert all(g["n"] >= 6 and g["laplace_ok"] for _, g in fitted)
    for _, g in fitted:
        assert set(g["min_o2"]) == {"p05", "p50", "p95", "at_x", "min_at_edge"}
        assert set(g["boundary"]) == {"x", "o2_p05", "o2_p50", "o2_p95"}
        assert len(g["boundary"]["x"]) == len(g["boundary"]["o2_p50"]) == 60
        assert {p["state"] for p in g["points"]} <= {"burns_sustained", "blowoff_extinction"}
    assert len(skipped) == 1
    key, grows = skipped[0]
    assert key[0] == "sibal" and len(grows) == 5


def test_group_loco_folds_schema_valid():
    rows = _bundle_rows(n1=40, n2=30, n3=5)
    folds = []
    ex.group_folds(_bundle(rows), folds)
    assert folds, "expected at least one group LOCO fold"
    for fold in folds:
        assert fold["fold_id"].startswith("loco-")
        assert fold["fold_id"].count("-") >= 3  # loco-<group...>-<campaign>
        assert not schema_errors(fold, "ValidationFold"), schema_errors(fold, "ValidationFold")
        assert set(fold["metrics"]) <= {"median_abs_rel_error", "brier"}


def test_flow_velocity_cm_conversion():
    """flow_velocity rows enter in cm/s (SI m/s * 100)."""
    bundle = {"observations": []}
    rows = [_row(0, 12.0, 0.16, 0.0, "sibal", "fabric", "opposed", "flow_velocity", "c1"),
            _row(1, 20.0, 0.17, 1.0, "sibal", "fabric", "opposed", "flow_velocity", "c1")]
    for r in rows:
        bundle["observations"].append({
            "qa": {"status": "accepted"}, "outcome": {"quantity": "flame_state", "state": r["state"]},
            "conditions": {"o2_mole_fraction": {"si_value": r["x"]}, "flow_direction": "opposed",
                           "extra": [{"name": "flow_velocity", "quantity": {"si_value": r["a"] / 100}}]},
            "fuel": {"material_id": "sibal", "geometry": "fabric"},
            "experiment": {"campaign_id": "c1"}, "locator": {}, "id": r["id"]})
    got = ex.flame_rows(bundle)
    assert [r["a"] for r in got] == [12.0, 20.0]


def test_skipped_rows_without_x_var():
    o = {"qa": {"status": "accepted"}, "outcome": {"quantity": "flame_state", "state": "burns_sustained"},
         "conditions": {"o2_mole_fraction": {"si_value": 0.18}, "extra": []},
         "fuel": {"material_id": "pmma", "geometry": "rod"},
         "experiment": {"campaign_id": "c1"}, "locator": {}, "id": "obs_0000000000000001"}
    assert ex.flame_rows({"observations": [o]}) == []


@pytest.mark.parametrize("n,ext,expect", [(6, 2, True), (5, 2, False), (6, 1, False)])
def test_group_thresholds(n, ext, expect):
    a, x, y = _synth(max(n, 8), seed=3)
    rows = [_row(i, float(aa), float(xx), yy, "pmma", "rod", "concurrent", "stretch_rate", "c1")
            for i, (aa, xx, yy) in enumerate(zip(a[:n], x[:n], y[:n]))]
    # force exactly `ext` extinction rows
    for r in rows[: len(rows) - ext]:
        r["y"] = 1.0
    for r in rows[len(rows) - ext:]:
        r["y"] = 0.0
        r["state"] = "blowoff_extinction"
    g = ex.fit_group(rows)
    assert (g is not None) == expect



def test_group_identical_to_primary_gets_no_duplicate_folds():
    b = _bundle(_bundle_rows())
    rod_ids = frozenset(r["id"] for r in ex.flame_rows(b) if r["key"][1] == "rod")
    with_skip, without = [], []
    ex.group_folds(b, with_skip, rod_ids)
    ex.group_folds(b, without)
    assert not any("-rod-" in f["fold_id"] for f in with_skip)
    assert any("-rod-" in f["fold_id"] for f in without)


def test_flow_velocity_read_from_contract_slot():
    o = {"conditions": {"flow_velocity": {"si_value": 0.08}, "extra": []}}
    assert ex.x_of(o) == ("flow_velocity", 8.0)
