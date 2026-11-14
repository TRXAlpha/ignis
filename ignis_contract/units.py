"""Unit normalization. The only place that turns reported value+unit into SI.

Ingestion calls make_quantity(); the validator calls si_of() to re-check every record.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import pint

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"

UREG = pint.UnitRegistry()
UREG.define("psia = psi")
UREG.define("psig_abs_not_supported = [unsupported_gauge]")  # placeholder dimension: psig needs ambient, refuse it

# Spellings seen in combustion papers -> pint expressions. Lowercase keys, exact match after strip().
_ALIASES = {
    "%": "percent", "vol%": "percent", "vol.%": "percent", "% vol": "percent", "%vol": "percent",
    "mol%": "percent", "% v/v": "percent", "v/v%": "percent", "% o2": "percent", "%o2": "percent",
    "": "dimensionless", "-": "dimensionless", "1": "dimensionless", "mole fraction": "dimensionless",
    "mass fraction": "dimensionless", "fraction": "dimensionless", "ppm": "ppm",
    "g": "g0", "g0": "g0", "g_0": "g0", "g-level": "g0", "xg": "g0", "earth g": "g0",
    "psig": "psig_abs_not_supported",
    "torr": "torr", "mmhg": "mmHg", "atm": "atm", "bar": "bar", "kpa": "kPa", "pa": "Pa", "mpa": "MPa",
    "cm/s": "cm/s", "mm/s": "mm/s", "m/s": "m/s",
    "mm^2/s": "mm**2/s", "mm2/s": "mm**2/s", "cm^2/s": "cm**2/s",
    "kw/m^2": "kW/m**2", "kw/m2": "kW/m**2", "w/cm^2": "W/cm**2", "w/cm2": "W/cm**2",
    "°c": "degC", "c": "degC", "degc": "degC", "k": "K",
}
# Note: bare "g" means gravity (g0), never grams, because grams never appear alone as a unit
# for any field in this contract. Mass units always come with "/s" etc.


class UnitError(ValueError):
    pass


@lru_cache(maxsize=1)
def quantities() -> dict:
    return json.loads((CONTRACT_DIR / "quantities.json").read_text(encoding="utf-8"))


def field_spec(field: str) -> dict:
    """field is 'conditions.<name>', 'fuel.<name>', 'outcomes.<name>' or 'material_properties.<name>'."""
    group, _, name = field.partition(".")
    try:
        return quantities()[group][name]
    except KeyError as e:
        raise UnitError(f"unknown field {field!r}") from e


def canonical_unit(field: str) -> str:
    u = field_spec(field)["si_unit"]
    if u is None:
        raise UnitError(f"field {field!r} has no numeric unit")
    return u


def _pint_unit(unit: str) -> str:
    u = unit.strip()
    return _ALIASES.get(u.lower(), u.replace("^", "**"))


def si_of(value: float, unit: str, field: str) -> float:
    """Convert value in reported unit to the field's canonical SI unit. Raises UnitError on mismatch."""
    target = canonical_unit(field)
    try:
        q = UREG.Quantity(value, _pint_unit(unit))
        out = q.to(target.replace("^", "**"))
    except pint.errors.DimensionalityError as e:
        raise UnitError(f"{field}: unit {unit!r} is not convertible to {target!r}") from e
    except (pint.errors.UndefinedUnitError, AttributeError, TypeError, ValueError) as e:
        raise UnitError(f"{field}: cannot parse unit {unit!r}") from e
    v = float(out.magnitude)
    if not math.isfinite(v):
        raise UnitError(f"{field}: non-finite result")
    return v


# ---- transforms (non-unit conversions, basis must be 'derived') -------------------------------

def o2_mass_to_mole_fraction(y: float, diluent: str = "N2") -> float:
    q = quantities()
    if diluent not in q["diluent_molar_mass_kg_mol"]:
        raise UnitError(f"no molar mass for diluent {diluent!r}")
    m_o2 = q["o2_molar_mass_kg_mol"]
    m_d = q["diluent_molar_mass_kg_mol"][diluent]
    if not 0 <= y <= 1:
        raise UnitError("mass fraction outside [0, 1]")
    n_o2, n_d = y / m_o2, (1 - y) / m_d
    return n_o2 / (n_o2 + n_d)


def o2_partial_pressure_to_mole_fraction(p_o2_pa: float, p_total_pa: float) -> float:
    if p_total_pa <= 0:
        raise UnitError("total pressure must be > 0")
    x = p_o2_pa / p_total_pa
    if x > 1:
        raise UnitError("O2 partial pressure exceeds total pressure")
    return x


def apply_transform(name: str, si_value: float, context: dict) -> float:
    """context: {'diluent': str, 'pressure_si': float} taken from the observation's conditions."""
    if name == "o2_mass_to_mole_fraction":
        dil = context.get("diluent") or "N2"
        if dil == "mixed":
            raise UnitError("cannot convert mass->mole fraction with mixed diluent")
        return o2_mass_to_mole_fraction(si_value, dil)
    if name == "o2_partial_pressure_to_mole_fraction":
        if context.get("pressure_si") is None:
            raise UnitError("partial-pressure transform needs conditions.pressure")
        return o2_partial_pressure_to_mole_fraction(si_value, context["pressure_si"])
    raise UnitError(f"unknown transform {name!r}")


# Unit conversion for the transform's *input* is not the output field's unit.
TRANSFORM_INPUT_FIELD = {
    "o2_mass_to_mole_fraction": "conditions.o2_mole_fraction",          # dimensionless in, dimensionless out
    "o2_partial_pressure_to_mole_fraction": "conditions.pressure",      # Pa in, dimensionless out
}


def expected_si(q: dict, field: str, context: dict | None = None) -> float:
    """Recompute the SI value a Quantity dict should carry."""
    t = q.get("transform")
    if t:
        return apply_transform(t, si_of(q["value"], q["unit"], TRANSFORM_INPUT_FIELD[t]), context or {})
    return si_of(q["value"], q["unit"], field)


def make_quantity(value: float, unit: str, field: str, *, basis: str = "reported", basis_ref: dict | None = None,
                  transform: str | None = None, context: dict | None = None, uncertainty: dict | None = None,
                  note: str | None = None) -> dict:
    """Build a contract Quantity. Ingestion code should only ever create quantities through this."""
    q: dict = {"value": float(value), "unit": unit, "basis": basis}
    if transform:
        q["transform"] = transform
    q["si_value"] = expected_si(q, field, context)
    q["si_unit"] = canonical_unit(field)
    if basis_ref is not None:
        q["basis_ref"] = basis_ref
    if uncertainty is not None:
        q["uncertainty"] = uncertainty
    if note:
        q["note"] = note
    return q
