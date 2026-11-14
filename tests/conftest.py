"""SYNTHETIC fixtures. Every number here is made up for testing the contract and is tagged
source kind 'synthetic_test' so it can never pass a --production validation."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ignis_contract import make_quantity, observation_id  # noqa: E402

SRC = "test:synthetic-paper"
LOC_REF = {"locator": {"source_id": SRC, "page": 2, "quote": "SYNTHETIC: all tests in air at 1 atm"}}


def _obs(**over):
    locator = over.pop("locator", {"source_id": SRC, "figure": "4", "series": "21% O2", "point_index": 0, "page": 5})
    quantity = over.pop("quantity", "flame_spread_rate")
    material = over.pop("material", "test-sheet")
    o = {
        "schema_version": "1.0.0",
        "id": observation_id(locator, quantity, material),
        "locator": locator,
        "experiment": {"campaign_id": "test-campaign", "platform": "orbital_iss", "facility": "MSG", "test_year": 2020},
        "fuel": {
            "material_id": material, "phase": "solid", "geometry": "sheet",
            "thickness": make_quantity(0.08, "mm", "fuel.thickness"),
        },
        "conditions": {
            "gravity": make_quantity(1e-6, "g0", "conditions.gravity", basis="campaign_nominal", basis_ref=LOC_REF),
            "o2_mole_fraction": make_quantity(21, "%", "conditions.o2_mole_fraction"),
            "pressure": make_quantity(14.7, "psia", "conditions.pressure"),
            "diluent": "N2",
            "flow_velocity": make_quantity(5, "cm/s", "conditions.flow_velocity"),
            "flow_direction": "opposed",
            "buoyancy_orientation": "not_applicable",
        },
        "outcome": {"quantity": quantity, "value": make_quantity(1.5, "mm/s", f"outcomes.{quantity}",
                                                                 uncertainty={"kind": "relative", "relative": 0.1}),
                    "time_basis": "steady"},
        "extraction": {
            "method": "plot_digitized", "tool": "test-digitizer@0", "extracted_at": "2026-11-14T12:00:00Z",
            "confidence": 0.9, "flags": ["condition_from_campaign_nominal"],
            "digitization": {
                "image_sha256": "0" * 64,
                "x_axis": {"scale": "linear", "unit": "cm/s", "points": [{"pixel": 100, "value": 0}, {"pixel": 500, "value": 20}]},
                "y_axis": {"scale": "log10", "unit": "mm/s", "points": [{"pixel": 400, "value": 0.1}, {"pixel": 50, "value": 10}]},
                "pixel": [200, 180], "calibration_residual_px": 0.8, "x_field": "conditions.flow_velocity",
            },
        },
        "qa": {"status": "accepted"},
    }
    o.update(over)
    return o


def _bundle():
    return {
        "schema_version": "1.0.0",
        "generated_at": "2026-11-14T12:00:00Z",
        "sources": [{"id": SRC, "kind": "synthetic_test", "title": "SYNTHETIC TEST FIXTURE - not NASA data",
                     "url": "https://example.invalid/synthetic", "year": 2021}],
        "campaigns": [{"id": "test-campaign", "name": "Synthetic campaign", "agency": "other",
                       "platform": "orbital_iss", "refs": [{"source_id": SRC, "page": 1}]}],
        "materials": [{"id": "test-sheet", "name": "Synthetic sheet", "phase": "solid", "material_class": "cellulosic",
                       "properties": {"density": make_quantity(0.6, "g/cm^3", "material_properties.density",
                                                               basis_ref=LOC_REF)}}],
        "observations": [_obs()],
    }


@pytest.fixture
def bundle():
    return copy.deepcopy(_bundle())


@pytest.fixture
def make_obs():
    return _obs
