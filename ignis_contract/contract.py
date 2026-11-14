"""Schema loading, structural validation, and the semantic invariants JSON Schema can't express.

Rule of thumb: JSON Schema catches shape errors; check_bundle() catches lies
(SI values that don't match units, dangling references, unflagged junk, fixtures leaking into prod).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache

from jsonschema import Draft202012Validator

from .units import CONTRACT_DIR, UnitError, expected_si, field_spec

SCHEMA_VERSION = "1.0.0"
CONFIDENCE_FLOOR = 0.7  # below this a row cannot be 'accepted'
REL_TOL = 1e-6

# Flags that mean "do not trust without a human". A row carrying any of these cannot be 'accepted'.
BLOCKING_FLAGS = {
    "low_confidence", "ocr_uncertain", "axis_calibration_residual_high", "transcription_unverified",
    "out_of_plausible_range", "duplicate_suspect", "conflicting_source",
}


@dataclass(frozen=True)
class Issue:
    level: str  # "error" | "warning"
    path: str
    msg: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.path}: {self.msg}"


@lru_cache(maxsize=1)
def schema() -> dict:
    return json.loads((CONTRACT_DIR / "ignis.schema.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def validator(kind: str = "Bundle") -> Draft202012Validator:
    s = schema()
    if kind not in s["$defs"]:
        raise KeyError(f"no $defs/{kind}")
    sub = {"$schema": s["$schema"], "$defs": s["$defs"], "$ref": f"#/$defs/{kind}"}
    Draft202012Validator.check_schema(sub)
    return Draft202012Validator(sub)


def schema_errors(obj: dict, kind: str = "Bundle") -> list[Issue]:
    out = []
    for e in sorted(validator(kind).iter_errors(obj), key=lambda e: list(e.absolute_path)):
        path = "/".join(str(p) for p in e.absolute_path) or "<root>"
        out.append(Issue("error", path, e.message))
    return out


# ---- ids -------------------------------------------------------------------------------------

def observation_id(locator: dict, outcome_quantity: str, material_id: str) -> str:
    """Deterministic: same datum re-extracted -> same id (so re-runs upsert, not duplicate).
    Depends only on *where* the datum is and *what* it measures, never on the extracted value."""
    key = json.dumps({"l": locator, "q": outcome_quantity, "m": material_id}, sort_keys=True, separators=(",", ":"))
    return "obs_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


# ---- semantic checks -------------------------------------------------------------------------

def _iter_quantities(obs: dict):
    """Yield (path, field_key, quantity) for every Quantity in an observation."""
    for name, q in obs["conditions"].items():
        if name in ("diluent", "flow_direction", "buoyancy_orientation"):
            continue
        if name == "extra":
            for i, ex in enumerate(q):
                yield f"conditions/extra/{i}", None, ex["quantity"]
            continue
        yield f"conditions/{name}", f"conditions.{name}", q
    for name in ("thickness", "width", "length", "diameter", "area_density"):
        if name in obs["fuel"]:
            yield f"fuel/{name}", f"fuel.{name}", obs["fuel"][name]
    if "value" in obs["outcome"] and obs["outcome"]["quantity"] != "other":
        yield "outcome/value", f"outcomes.{obs['outcome']['quantity']}", obs["outcome"]["value"]


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= REL_TOL * max(abs(a), abs(b), 1e-300)


def _check_quantity(q: dict, field: str | None, path: str, ctx: dict, flags: set, issues: list):
    if q.get("transform") and q["basis"] != "derived":
        issues.append(Issue("error", path, "transform requires basis='derived'"))
    if field is None:  # free-form extra condition: we can only check that the unit parses
        return
    spec = field_spec(field)
    if q["si_unit"] != spec["si_unit"]:
        issues.append(Issue("error", path, f"si_unit {q['si_unit']!r} != canonical {spec['si_unit']!r}"))
        return
    try:
        exp = expected_si(q, field, ctx)
    except UnitError as e:
        issues.append(Issue("error", path, str(e)))
        return
    if not _close(exp, q["si_value"]):
        issues.append(Issue("error", path, f"si_value {q['si_value']} != {exp} recomputed from {q['value']} {q['unit']}"))
        return
    lo, hi = spec.get("hard", [None, None])
    v = q["si_value"]
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        issues.append(Issue("error", path, f"{v} {spec['si_unit']} is physically impossible (hard range {lo}..{hi})"))
        return
    plo, phi = spec.get("plausible", [None, None])
    if ((plo is not None and v < plo) or (phi is not None and v > phi)) and "out_of_plausible_range" not in flags:
        issues.append(Issue("error", path, f"{v} {spec['si_unit']} outside plausible {plo}..{phi}; add flag out_of_plausible_range"))
    u = q.get("uncertainty") or {}
    if "lower_si" in u and "upper_si" in u and u["lower_si"] > u["upper_si"]:
        issues.append(Issue("error", path + "/uncertainty", "lower_si > upper_si"))
    ref = q.get("basis_ref", {}).get("locator")
    if ref is not None and "source_id" in ref and ref["source_id"] not in ctx["_source_ids"]:
        issues.append(Issue("error", path + "/basis_ref", f"unknown source {ref['source_id']!r}"))


def check_observation(obs: dict, idx: dict, production: bool = False) -> list[Issue]:
    issues: list[Issue] = []
    oid = obs["id"]
    p = f"observations/{oid}"
    src = idx["sources"].get(obs["locator"]["source_id"])
    if src is None:
        issues.append(Issue("error", p + "/locator", f"unknown source {obs['locator']['source_id']!r}"))
    elif production and src["kind"] == "synthetic_test":
        issues.append(Issue("error", p, "synthetic test source in a production bundle"))
    if obs["experiment"]["campaign_id"] not in idx["campaigns"]:
        issues.append(Issue("error", p + "/experiment", f"unknown campaign {obs['experiment']['campaign_id']!r}"))
    if obs["fuel"]["material_id"] not in idx["materials"]:
        issues.append(Issue("error", p + "/fuel", f"unknown material {obs['fuel']['material_id']!r}"))

    want = observation_id(obs["locator"], obs["outcome"]["quantity"], obs["fuel"]["material_id"])
    if oid != want:
        issues.append(Issue("error", p, f"id should be {want} (deterministic from locator+quantity+material)"))

    ex, qa = obs["extraction"], obs["qa"]
    flags = set(ex.get("flags", []))
    if qa["status"] == "accepted":
        if ex["confidence"] < CONFIDENCE_FLOOR:
            issues.append(Issue("error", p + "/qa", f"confidence {ex['confidence']} < {CONFIDENCE_FLOOR} cannot be accepted"))
        bad = flags & BLOCKING_FLAGS
        if bad:
            issues.append(Issue("error", p + "/qa", f"blocking flags {sorted(bad)} cannot be accepted (flag it or human_verify)"))
    if qa["status"] == "human_verified" and not ex.get("reviewer"):
        issues.append(Issue("error", p + "/qa", "human_verified requires extraction.reviewer"))
    if qa["status"] in ("flagged", "rejected") and not qa.get("reasons") and not flags:
        issues.append(Issue("error", p + "/qa", f"{qa['status']} without reasons or flags"))

    nominal_used = any(q.get("basis") == "campaign_nominal" for _, _, q in _iter_quantities(obs))
    if nominal_used and "condition_from_campaign_nominal" not in flags:
        issues.append(Issue("warning", p, "uses campaign_nominal values; add flag condition_from_campaign_nominal"))

    ctx = {
        "diluent": obs["conditions"].get("diluent"),
        "pressure_si": obs["conditions"].get("pressure", {}).get("si_value"),
        "_source_ids": idx["sources"],
    }
    for path, field, q in _iter_quantities(obs):
        _check_quantity(q, field, f"{p}/{path}", ctx, flags, issues)
    return issues


def _index(bundle: dict, issues: list) -> dict:
    idx = {}
    for key in ("sources", "campaigns", "materials"):
        d = {}
        for r in bundle[key]:
            if r["id"] in d:
                issues.append(Issue("error", f"{key}/{r['id']}", "duplicate id"))
            d[r["id"]] = r
        idx[key] = d
    return idx


def check_bundle(bundle: dict, production: bool = False) -> list[Issue]:
    """Full validation. Returns issues; the bundle is valid iff no issue has level 'error'."""
    issues = schema_errors(bundle, "Bundle")
    if issues:
        return issues  # semantic checks assume the shape is right
    idx = _index(bundle, issues)
    for c in bundle["campaigns"]:
        for i, ref in enumerate(c["refs"]):
            if ref["source_id"] not in idx["sources"]:
                issues.append(Issue("error", f"campaigns/{c['id']}/refs/{i}", f"unknown source {ref['source_id']!r}"))
        if c.get("parent_id") and c["parent_id"] not in idx["campaigns"]:
            issues.append(Issue("error", f"campaigns/{c['id']}", f"unknown parent {c['parent_id']!r}"))
    for m in bundle["materials"]:
        for name, q in m.get("properties", {}).items():
            _check_quantity(q, f"material_properties.{name}", f"materials/{m['id']}/{name}",
                            {"_source_ids": idx["sources"]}, set(), issues)
    seen = set()
    for obs in bundle["observations"]:
        if obs["id"] in seen:
            issues.append(Issue("error", f"observations/{obs['id']}", "duplicate observation id"))
        seen.add(obs["id"])
        issues.extend(check_observation(obs, idx, production))
    if production:
        for s in bundle["sources"]:
            if s["kind"] == "synthetic_test" or s["id"].startswith("test:"):
                issues.append(Issue("error", f"sources/{s['id']}", "synthetic test source in a production bundle"))
    return issues


def is_valid(issues: list[Issue]) -> bool:
    return not any(i.level == "error" for i in issues)
