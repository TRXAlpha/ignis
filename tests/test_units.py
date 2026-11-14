import math

import pytest

from ignis_contract import UnitError, make_quantity, si_of
from ignis_contract.units import o2_mass_to_mole_fraction, o2_partial_pressure_to_mole_fraction


@pytest.mark.parametrize("value,unit,field,expected", [
    (14.7, "psia", "conditions.pressure", 101352.93),
    (1, "atm", "conditions.pressure", 101325.0),
    (8.2, "psi", "conditions.pressure", 56537.01),
    (760, "torr", "conditions.pressure", 101325.0),
    (56.5, "kPa", "conditions.pressure", 56500.0),
    (21, "%", "conditions.o2_mole_fraction", 0.21),
    (34, "vol%", "conditions.o2_mole_fraction", 0.34),
    (0.21, "mole fraction", "conditions.o2_mole_fraction", 0.21),
    (5, "cm/s", "conditions.flow_velocity", 0.05),
    (1.5, "mm/s", "outcomes.flame_spread_rate", 0.0015),
    (0.8, "mm^2/s", "outcomes.burning_rate_constant", 8e-7),
    (1e-6, "g0", "conditions.gravity", 9.80665e-6),
    (1, "g", "conditions.gravity", 9.80665),
    (2, "µg", "conditions.gravity", 1.96133e-5),
    (2, "μg", "conditions.gravity", 1.96133e-5),
    (5, "µg/s", "outcomes.mass_burning_rate", 5e-9),
    (25, "kW/m^2", "conditions.external_heat_flux", 25000.0),
    (25, "degC", "conditions.ambient_temperature", 298.15),
    (0.08, "mm", "fuel.thickness", 8e-5),
    (3.5, "mg/s", "outcomes.mass_burning_rate", 3.5e-6),
])
def test_si_conversion(value, unit, field, expected):
    assert math.isclose(si_of(value, unit, field), expected, rel_tol=1e-6)


@pytest.mark.parametrize("unit,field", [
    ("cm/s", "conditions.pressure"),
    ("kPa", "outcomes.flame_spread_rate"),
    ("psig", "conditions.pressure"),       # gauge pressure needs ambient: refuse rather than guess
    ("furlongs", "conditions.flow_velocity"),
])
def test_bad_units_raise(unit, field):
    with pytest.raises(UnitError):
        si_of(1.0, unit, field)


def test_unknown_field():
    with pytest.raises(UnitError):
        si_of(1, "m", "conditions.nope")


def test_mass_to_mole_fraction_air():
    # air: 23.14 wt% O2 <-> ~20.95 mol% O2
    assert math.isclose(o2_mass_to_mole_fraction(0.2314, "N2"), 0.2085, abs_tol=2e-3)
    assert o2_mass_to_mole_fraction(0, "N2") == 0
    assert o2_mass_to_mole_fraction(1, "N2") == 1
    # He diluent: same mass fraction gives far lower mole fraction
    assert o2_mass_to_mole_fraction(0.23, "He") < 0.05


def test_partial_pressure_transform():
    assert math.isclose(o2_partial_pressure_to_mole_fraction(21.3, 101.3), 21.3 / 101.3)
    with pytest.raises(UnitError):
        o2_partial_pressure_to_mole_fraction(120, 100)


def test_make_quantity_keeps_reported_verbatim():
    q = make_quantity(14.7, "psia", "conditions.pressure")
    assert q["value"] == 14.7 and q["unit"] == "psia" and q["si_unit"] == "Pa" and q["basis"] == "reported"
    assert math.isclose(q["si_value"], 101352.93, rel_tol=1e-6)


def test_make_quantity_with_transform():
    q = make_quantity(3.1, "psia", "conditions.o2_mole_fraction", basis="derived",
                      basis_ref={"formula": "o2_partial_pressure_to_mole_fraction", "inputs": ["conditions.pressure"]},
                      transform="o2_partial_pressure_to_mole_fraction", context={"pressure_si": 56500.0})
    assert q["si_unit"] == "dimensionless"
    assert math.isclose(q["si_value"], 3.1 * 6894.757293168 / 56500.0, rel_tol=1e-9)
