"""WebPlotDigitizer 4 project -> contract `plot_digitized` observations.

Inputs per figure, in digitized/:
  <name>.spec.json   written by us: source locator, which axis feeds which contract field, per-series metadata
  <name>.tar | .json the human's WPD 4 export (File > Save Project), digitized on data/figures/<name>.png

Guards (any failure raises DigitizationError, which fails the bundle build):
  - the figure PNG matches the spec's image_sha256, and the image inside a WPD .tar matches it too
  - every number we emit is recomputed from WPD's raw pixels + calibration (WPD v4.7 XYAxes math,
    app/javascript/core/axes/xy.js) and must agree with the value WPD itself exported
  - every WPD dataset is either mapped in the spec or explicitly skipped (no silently dropped series)
  - require_text snippets (caption etc.) must appear verbatim on the cited PDF page

calibration_residual_px = how far the calibration pairs depart from a horizontal x-axis / vertical y-axis.
Our renders are never rotated, so a large value means a mis-clicked calibration point -> blocking flag.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from ignis_contract import make_quantity, observation_id
from ignis_contract.units import UnitError, extra_si

from .curated import require_text

TOOL = "WebPlotDigitizer 4 (human clicks) + ingest.wpd@1"
RESIDUAL_PX_MAX = 3.0
REL_TOL = 1e-6
DEFAULT_CONFIDENCE = 0.8


class DigitizationError(AssertionError):
    pass


# ---- WPD project I/O --------------------------------------------------------------------------

def load_project(path: Path) -> tuple[dict, dict[str, bytes]]:
    """Return (wpd json, {image name: bytes}). Accepts WPD 4 .tar (wpd.json + images) or a bare .json."""
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8")), {}
    with tarfile.open(path) as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        js = [m for m in members if m.name.endswith("/wpd.json") or m.name == "wpd.json"]
        if len(js) != 1:
            raise DigitizationError(f"{path}: expected one wpd.json in tar, found {len(js)}")
        data = json.loads(tf.extractfile(js[0]).read().decode("utf-8"))
        images = {Path(m.name).name: tf.extractfile(m).read() for m in members if not m.name.endswith(".json")}
    return data, images


def _same_image(a: bytes, b: bytes) -> bool:
    if hashlib.sha256(a).digest() == hashlib.sha256(b).digest():
        return True
    import pymupdf  # fall back to decoded pixels in case the browser re-encoded the PNG
    try:
        pa, pb = pymupdf.Pixmap(io.BytesIO(a).getvalue()), pymupdf.Pixmap(io.BytesIO(b).getvalue())
    except Exception:  # noqa: BLE001 - undecodable means not the same image
        return False
    if (pa.width, pa.height) != (pb.width, pb.height):
        return False
    if pa.n != pb.n:
        pa, pb = pymupdf.Pixmap(pymupdf.csRGB, pa), pymupdf.Pixmap(pymupdf.csRGB, pb)
        if pa.alpha:
            pa = pymupdf.Pixmap(pa, 0)
        if pb.alpha:
            pb = pymupdf.Pixmap(pb, 0)
    return pa.samples == pb.samples


# ---- XY axes (port of WPD 4.7 XYAxes) ---------------------------------------------------------

class XYAxes:
    def __init__(self, ax: dict):
        if ax.get("type") != "XYAxes":
            raise DigitizationError(f"axes {ax.get('name')!r}: only XYAxes supported, got {ax.get('type')!r}")
        cps = ax.get("calibrationPoints") or []
        if len(cps) != 4:
            raise DigitizationError(f"axes {ax.get('name')!r}: need 4 calibration points, got {len(cps)}")
        self.name = ax["name"]
        self.log_x, self.log_y = bool(ax.get("isLogX")), bool(ax.get("isLogY"))
        if ax.get("noRotation"):
            raise DigitizationError(f"axes {self.name!r}: 'assume no rotation' is not supported; untick it in WPD")
        self.cp = cps
        p1, p2, p3, p4 = cps
        self.x_pts = [(float(p1["px"]), float(p1["dx"])), (float(p2["px"]), float(p2["dx"]))]
        self.y_pts = [(float(p3["py"]), float(p3["dy"])), (float(p4["py"]), float(p4["dy"]))]
        xmin, xmax, ymin, ymax = float(p1["dx"]), float(p2["dx"]), float(p3["dy"]), float(p4["dy"])
        self.neg_x = self.log_x and xmin < 0 and xmax < 0
        self.neg_y = self.log_y and ymin < 0 and ymax < 0
        if self.log_x:
            xmin, xmax = math.log10(abs(xmin)), math.log10(abs(xmax))
        if self.log_y:
            ymin, ymax = math.log10(abs(ymin)), math.log10(abs(ymax))
        x1, y1, x2, y2 = (float(p1["px"]), float(p1["py"]), float(p2["px"]), float(p2["py"]))
        x3, y3, x4, y4 = (float(p3["px"]), float(p3["py"]), float(p4["px"]), float(p4["py"]))
        # a_mat = dat_mat * inv(pix_mat), row-major 2x2, exactly as WPD
        d = [xmin - xmax, 0.0, 0.0, ymin - ymax]
        p = [x1 - x2, x3 - x4, y1 - y2, y3 - y4]
        det = p[0] * p[3] - p[1] * p[2]
        if abs(det) < 1e-12:
            raise DigitizationError(f"axes {self.name!r}: degenerate calibration (collinear points)")
        pinv = [p[3] / det, -p[1] / det, -p[2] / det, p[0] / det]
        self.a = [d[0] * pinv[0] + d[1] * pinv[2], d[0] * pinv[1] + d[1] * pinv[3],
                  d[2] * pinv[0] + d[3] * pinv[2], d[2] * pinv[1] + d[3] * pinv[3]]
        self.c = [xmin - self.a[0] * x1 - self.a[1] * y1, ymin - self.a[2] * x3 - self.a[3] * y3]
        self.residual_px = max(abs(y1 - y2), abs(x3 - x4))

    def pixel_to_data(self, px: float, py: float) -> tuple[float, float]:
        xf = self.a[0] * px + self.a[1] * py + self.c[0]
        yf = self.a[2] * px + self.a[3] * py + self.c[1]
        if self.log_x:
            xf = -(10 ** xf) if self.neg_x else 10 ** xf
        if self.log_y:
            yf = -(10 ** yf) if self.neg_y else 10 ** yf
        return xf, yf

    def calibration(self, axis: str, unit: str) -> dict:
        pts = self.x_pts if axis == "x" else self.y_pts
        log = self.log_x if axis == "x" else self.log_y
        return {"scale": "log10" if log else "linear", "unit": unit,
                "points": [{"pixel": px, "value": v} for px, v in pts]}


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= REL_TOL * max(abs(a), abs(b), 1e-12)


# ---- spec -> observations ---------------------------------------------------------------------

def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def extra_quantity(value: float, unit: str, basis: str = "reported", basis_ref: dict | None = None,
                   note: str | None = None) -> dict:
    """Quantity for a free-form conditions.extra entry (no canonical field): SI = pint base units."""
    try:
        si, si_unit = extra_si(value, unit)
    except UnitError as e:
        raise DigitizationError(str(e)) from e
    out = {"value": float(value), "unit": unit, "si_value": si, "si_unit": si_unit, "basis": basis}
    if basis_ref:
        out["basis_ref"] = basis_ref
    if note:
        out["note"] = note
    return out


def _quantity(spec_q, field: str, sources: dict) -> dict:
    """Spec quantity: '@iss_nominal' token, or {value, unit, basis?, basis_ref?, note?}."""
    if spec_q == "@iss_nominal":
        from .curated.bass2_report import iss_gravity
        return iss_gravity(sources)
    if not isinstance(spec_q, dict):
        raise DigitizationError(f"{field}: bad quantity spec {spec_q!r}")
    if field.startswith("conditions.extra."):
        return extra_quantity(spec_q["value"], spec_q["unit"], spec_q.get("basis", "reported"), spec_q.get("basis_ref"))
    return make_quantity(spec_q["value"], spec_q["unit"], field, basis=spec_q.get("basis", "reported"),
                         basis_ref=spec_q.get("basis_ref"), note=spec_q.get("note"))


def _place(obs: dict, field: str, q: dict) -> None:
    """Route a quantity to its slot: conditions.<k>, conditions.extra.<slug>, fuel.<k>, outcomes.<quantity>."""
    head, _, rest = field.partition(".")
    if head == "conditions" and rest.startswith("extra."):
        name = rest.split(".", 1)[1]
        obs["conditions"].setdefault("extra", [])
        obs["conditions"]["extra"] = [e for e in obs["conditions"]["extra"] if e["name"] != name]
        obs["conditions"]["extra"].append({"name": name, "quantity": q})
    elif head == "conditions":
        obs["conditions"][rest] = q
    elif head == "fuel":
        obs["fuel"][rest] = q
    elif head == "outcomes":
        if obs["outcome"].get("quantity") not in (None, rest):
            raise DigitizationError(f"axis feeds outcomes.{rest} but series outcome is {obs['outcome']['quantity']!r}")
        obs["outcome"]["quantity"] = rest
        obs["outcome"]["value"] = q
    else:
        raise DigitizationError(f"unroutable field {field!r}")


def observations_from(spec: dict, project: dict, images: dict[str, bytes], sources: dict,
                      root: Path = Path(".")) -> list[dict]:
    name = spec["name"]
    img_path = root / spec["image"]
    img = img_path.read_bytes()
    if hashlib.sha256(img).hexdigest() != spec["image_sha256"]:
        raise DigitizationError(f"{name}: {img_path} does not match spec image_sha256 (re-rendered?)")
    if images and not any(_same_image(img, b) for b in images.values()):
        raise DigitizationError(f"{name}: image inside the WPD project is not {img_path}; digitize the rendered PNG")

    src, page = spec["source_id"], spec["page"]
    require_text(sources, src, page, *spec.get("require_text", []))
    for ref in spec.get("require_text_elsewhere", []):  # provenance for spec-level metadata (geometry, flow, ...)
        require_text(sources, ref.get("source_id", src), ref["page"], *ref["snippets"])
    axes = {a["name"]: XYAxes(a) for a in project.get("axesColl", [])}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    series_specs = spec["series"]
    auto = (project.get("ignis") or {}).get("tool")  # set by ingest.autodigitize: machine detection, no clicks
    tool = f"{auto} + ingest.wpd@1" if auto else TOOL
    how = ("machine-detected (tick + marker detection) on hash-pinned figure render, overlay reviewed; "
           "values recomputed from calibration; caption verbatim on page") if auto else (
           "human-clicked in WPD on hash-pinned figure render; values recomputed from WPD "
           "calibration and matched WPD's export; caption verbatim on page")
    out: list[dict] = []

    for ds in project.get("datasetColl", []):
        sname = ds["name"]
        if sname not in series_specs:
            raise DigitizationError(f"{name}: WPD dataset {sname!r} not in spec series {sorted(series_specs)}")
        ss = series_specs[sname]
        if "skip" in ss:
            continue
        ax = axes.get(ds.get("axesName"))
        if ax is None:
            raise DigitizationError(f"{name}/{sname}: dataset not attached to known axes")
        ax_spec = spec["axes"].get(ax.name)
        if ax_spec is None:
            raise DigitizationError(f"{name}: WPD axes {ax.name!r} not in spec axes {sorted(spec['axes'])}")
        tmpl = _merge(_merge(spec.get("base", {}), ax_spec.get("base", {})), ss)
        label = tmpl.pop("label", sname)

        for i, pt in enumerate(ds.get("data", [])):
            xv, yv = ax.pixel_to_data(float(pt["x"]), float(pt["y"]))
            wv = pt.get("value")
            if wv is not None and not (_close(xv, float(wv[0])) and _close(yv, float(wv[1]))):
                raise DigitizationError(f"{name}/{sname}[{i}]: recomputed ({xv}, {yv}) != WPD value {wv}")
            flags = set(tmpl.get("flags", []))
            if ax.log_x or ax.log_y:
                flags.add("value_from_log_axis")
            if ax.residual_px > RESIDUAL_PX_MAX:
                flags.add("axis_calibration_residual_high")

            locator = {"source_id": src, "page": page, "figure": spec["figure"], "series": label, "point_index": i}
            if spec.get("panel"):
                locator["panel"] = spec["panel"]
            if spec.get("quote"):
                locator["quote"] = spec["quote"][:400]

            obs = {"schema_version": "1.0.0", "locator": locator,
                   "experiment": copy.deepcopy(tmpl["experiment"]), "fuel": copy.deepcopy(tmpl["fuel"]),
                   "conditions": {}, "outcome": copy.deepcopy(tmpl.get("outcome", {}))}
            for k, v in tmpl.get("conditions", {}).items():
                if k in ("diluent", "flow_direction", "buoyancy_orientation"):
                    obs["conditions"][k] = v
                else:
                    _place(obs, f"conditions.{k}", _quantity(v, f"conditions.{k}", sources))
            for k, v in tmpl.get("fuel_quantities", {}).items():
                _place(obs, f"fuel.{k}", _quantity(v, f"fuel.{k}", sources))
            for axis, val in (("x", xv), ("y", yv)):
                a = ax_spec[axis]
                f = a["field"]
                q = (extra_quantity(val, a["unit"], note=a.get("note")) if f.startswith("conditions.extra.")
                     else make_quantity(val, a["unit"], f, note=a.get("note")))
                _place(obs, f, q)
            if "gravity" not in obs["conditions"]:
                raise DigitizationError(f"{name}/{sname}: no gravity (required); set conditions.gravity in spec")

            blocking = flags & {"axis_calibration_residual_high", "low_confidence", "overlapping_markers"}
            obs["id"] = observation_id(locator, obs["outcome"]["quantity"], obs["fuel"]["material_id"])
            obs["extraction"] = {
                "method": "plot_digitized", "tool": tool, "extracted_at": now,
                "confidence": float(tmpl.get("confidence", 0.75 if auto else DEFAULT_CONFIDENCE)),
                "flags": sorted(flags),
                "digitization": {
                    "image_sha256": spec["image_sha256"],
                    "x_axis": ax.calibration("x", ax_spec["x"]["unit"]),
                    "y_axis": ax.calibration("y", ax_spec["y"]["unit"]),
                    "pixel": [float(pt["x"]), float(pt["y"])],
                    "calibration_residual_px": round(ax.residual_px, 3),
                    "x_field": ax_spec["x"]["field"],
                    "marker": label,
                },
            }
            obs["qa"] = ({"status": "flagged", "reasons": [f"blocking flags: {sorted(blocking)}"]} if blocking else
                         {"status": "accepted", "reasons": [how]})
            out.append(obs)
    return out


def load_spec(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def project_for(spec_path: Path) -> Path | None:
    stem = spec_path.name.removesuffix(".spec.json")
    for ext in (".tar", ".wpd.json"):
        p = spec_path.with_name(stem + ext)
        if p.exists():
            return p
    return None
