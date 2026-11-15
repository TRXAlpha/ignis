"""Machine digitization of a scatter plot: axis ticks + coloured/shaped markers -> WPD 4 project JSON.

python -m ingest.autodigitize bass2_fig6_10        # writes digitized/bass2_fig6_10.wpd.json + data/figures/<name>.overlay.png

Output is a normal WPD 4 project, so it goes through the same converter and guards as human clicks
(image hash, caption on page, WPD-math recompute) and can be opened in WPD 4 to inspect or correct.
Detection is per-figure config below, not magic:
  - calibration = pixel centres of labelled major ticks (darkness-weighted, sub-pixel), values read from the tick labels
  - filled markers = colour mask -> connected components; fragments split by an overlapping marker are merged;
    components ~k x the single-marker area are split into k by k-means
  - 'x' markers = both +45 and -45 diagonals dark around the centre, ignoring pixels hidden under coloured markers
Overlay PNG draws every detected centre on the figure for review.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pymupdf

FIGS = Path("data/figures")
DIG = Path("digitized")

CONFIG = {
    "bass2_fig6_10": {
        # tick pixel guesses -> refined; values read off the tick labels (log x: 10, 100; linear y: 19, 14 vol%)
        "axes": {"XY": {"log_x": True, "x_ticks": [(726, 10), (1310, 100)], "y_ticks": [(179, 19), (1003, 14)],
                        "x_tick_band": (1152, 1162), "y_tick_band": (141, 150), "x_axis_row": 1167.5, "y_axis_col": 136.5}},
        "plot_box": (290, 1160, 140, 1480),   # rows y0..y1, cols x0..x1 (below the legend, inside the frame)
        "series": {
            "ISS stable flame": {"kind": "filled", "rgb": "blue"},
            "ISS quench": {"kind": "filled", "rgb": "bright_red"},
            "ISS blowoff": {"kind": "x", "half": 13, "min_vis": 0.25, "hidden_behind": "ISS stable flame"},
            "Drop Tower blowoff": {"kind": "plus", "rgb": "plus_purple"},
            "Drop Tower stable flame": {"kind": "filled", "rgb": "tri_green"},
        },
        "occluders": ["blue", "bright_red", "dark_red", "green", "purple"],
    },
    "saffire5_fig10": {
        # one continuous x axis: concurrent flow increases to the LEFT of 0, opposed to the right -> two WPD axes
        "axes": {
            "concurrent": {"log_x": False, "x_ticks": [(209, 30), (413, 10)], "y_ticks": [(199, 0.5), (661, 0.1)],
                           "x_tick_band": (781, 795), "y_tick_band": (197, 206), "x_axis_row": 777, "y_axis_col": 209},
            "opposed": {"log_x": False, "x_ticks": [(615, 10), (1023, 50)], "y_ticks": [(199, 0.5), (661, 0.1)],
                        "x_tick_band": (781, 795), "y_tick_band": (197, 206), "x_axis_row": 777, "y_axis_col": 209},
        },
        "plot_box": (88, 772, 212, 1020),
        "series": {
            "BASS concurrent 2 cm wide": {"kind": "filled", "rgb": "blue", "axes": "concurrent", "box": (88, 690, 212, 505),
                                          "min_px": 150},
            "BASS concurrent 1 cm wide": {"kind": "filled", "rgb": "navy", "axes": "concurrent", "box": (88, 772, 212, 505),
                                          "min_px": 80},
            "BASS opposed 2 cm wide": {"kind": "filled", "rgb": "plus_purple", "axes": "opposed", "box": (350, 772, 512, 1020),
                                       "min_px": 150},
        },
        "occluders": [],
    },
}


def colour_mask(a: np.ndarray, name: str) -> np.ndarray:
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    return {
        "blue": (B > 150) & (R < 60) & (G > 70) & (G < 150),
        "bright_red": (R > 215) & (G < 70) & (B < 70),
        "dark_red": (R > 110) & (R <= 215) & (G < 60) & (B < 60),
        "green": (G > 120) & (G - B > 40) & (R < 160),
        "purple": (B > 160) & (R > 100) & (G < 120),
        "navy": (R < 45) & (G < 70) & (B > 65) & (B < 140),
        "tri_green": (abs(R - 112) < 30) & (abs(G - 173) < 30) & (abs(B - 70) < 35),
        "plus_purple": (R > 80) & (R < 140) & (G > 20) & (G < 80) & (B > 130) & (B < 195),
    }[name]


def _components(mask: np.ndarray) -> list[np.ndarray]:
    H, W = mask.shape
    lab = np.zeros(mask.shape, np.int32)
    out = []
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        lab[y0, x0] = len(out) + 1
        st, pts = [(y0, x0)], []
        while st:
            y, x = st.pop()
            pts.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = y + dy, x + dx
                    if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = len(out) + 1
                        st.append((yy, xx))
        out.append(np.array(pts, float))
    return out


def _kmeans(pts: np.ndarray, k: int, iters: int = 50) -> list[np.ndarray]:
    order = np.argsort(pts[:, 0] + pts[:, 1])
    cent = pts[order[np.linspace(0, len(pts) - 1, k).astype(int)]]
    for _ in range(iters):
        lab = np.argmin(((pts[:, None, :] - cent[None]) ** 2).sum(-1), 1)
        cent = np.array([pts[lab == j].mean(0) if np.any(lab == j) else cent[j] for j in range(k)])
    return [pts[lab == j] for j in range(k)]


def filled_markers(mask: np.ndarray, min_px: int = 15) -> list[tuple[float, float]]:
    comps = [c for c in _components(mask) if len(c) >= min_px]
    if not comps:
        return []
    unit = float(np.median([len(c) for c in comps if len(c) > 150] or [len(c) for c in comps]))
    size = float(np.median([np.ptp(c[:, 0]) + 1 for c in comps if len(c) > 0.8 * unit]))
    # merge fragments (pieces of one marker cut by another marker drawn on top)
    small = [c for c in comps if len(c) < 0.6 * unit]
    big = [c for c in comps if len(c) >= 0.6 * unit]
    groups: list[list[np.ndarray]] = []
    for c in small:
        cy, cx = c.mean(0)
        for g in groups:
            gy, gx = np.concatenate(g).mean(0)
            if abs(gy - cy) < size and abs(gx - cx) < size:
                g.append(c)
                break
        else:
            groups.append([c])
    centres = []
    for c in big:
        k = max(1, int(round(len(c) / unit)))
        for part in (_kmeans(c, k) if k > 1 else [c]):
            centres.append(_bbox_centre(part, size))
    for g in groups:
        centres.append(_bbox_centre(np.concatenate(g), size))
    return centres


def _bbox_centre(c: np.ndarray, size: float) -> tuple[float, float]:
    """Centre from the bounding box; if a side is clipped (occluded) use the intact edge +/- half size."""
    y0, x0 = c.min(0)
    y1, x1 = c.max(0)
    h, w = y1 - y0 + 1, x1 - x0 + 1
    cy = (y0 + y1) / 2 if h >= size - 2 else (y0 + size / 2 - 0.5 if c[:, 0].mean() > (y0 + y1) / 2 else y1 - size / 2 + 0.5)
    cx = (x0 + x1) / 2 if w >= size - 2 else (x0 + size / 2 - 0.5 if c[:, 1].mean() > (x0 + x1) / 2 else x1 - size / 2 + 0.5)
    return float(cx), float(cy)


def x_markers(a: np.ndarray, box, occluders: list[str], half: int, thr: float = 0.9, min_vis: float = 0.5) -> list[tuple[float, float]]:
    y0, y1, x0, x1 = box
    sub = a[y0 - half - 2:y1 + half + 2, x0 - half - 2:x1 + half + 2]
    dark = sub.max(2) < 100
    occ = np.zeros(dark.shape, bool)
    for n in occluders:
        occ |= colour_mask(sub, n)
    dd, oc = dark.copy(), occ.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            dd |= np.roll(np.roll(dark, dy, 0), dx, 1)
            oc |= np.roll(np.roll(occ, dy, 0), dx, 1)
    vis = dd & ~oc
    ks = [k for k in range(-half, half + 1) if abs(k) >= 3]
    n = len(ks)
    score = None
    for sgn in (1, -1):
        d = sum(np.roll(np.roll(vis, -k, 0), -sgn * k, 1).astype(np.int16) for k in ks)
        o = sum(np.roll(np.roll(oc, -k, 0), -sgn * k, 1).astype(np.int16) for k in ks)
        v = n - o
        s = np.where(v >= min_vis * n, d / np.maximum(v, 1), 0.0)
        score = s if score is None else np.minimum(score, s)
    m = half + 2
    score = score[m:-m, m:-m]
    peaks = []
    for c in _components(score >= thr):
        ys, xs = c[:, 0].astype(int), c[:, 1].astype(int)
        w = score[ys, xs]
        peaks.append((float((xs * w).sum() / w.sum()) + x0, float((ys * w).sum() / w.sum()) + y0))
    return peaks


def plus_markers(mask: np.ndarray, min_run: int = 15, half: int = 18) -> list[tuple[float, float]]:
    """'+' markers: each vertical stroke (a run of >= min_run px, a few columns wide) is one marker; the centre row is
    where the horizontal arm through that stroke is widest. Overlapping pluses share arms but not vertical strokes."""
    H, W = mask.shape
    runs = []
    for x in range(W):
        col = mask[:, x]
        ys = np.flatnonzero(np.diff(np.concatenate([[0], col.astype(np.int8), [0]])))
        for y0, y1 in zip(ys[::2], ys[1::2]):
            if y1 - y0 >= min_run:
                runs.append((x, y0, y1 - 1))
    groups: list[list[tuple[int, int, int]]] = []
    for x, y0, y1 in runs:
        for g in groups:
            gx, gy0, gy1 = g[-1]
            if x - gx <= 1 and min(y1, gy1) - max(y0, gy0) > 10:
                g.append((x, y0, y1))
                break
        else:
            groups.append([(x, y0, y1)])
    out = []
    for g in groups:
        cx = float(np.mean([r[0] for r in g]))
        y0, y1 = min(r[1] for r in g), max(r[2] for r in g)
        xi = int(round(cx))
        rows = range(max(0, y0 - 5), min(H, y1 + 6))
        widths = [mask[y, max(0, xi - half):xi + half + 1].sum() for y in rows]
        best = max(widths)
        cy = float(np.mean([y for y, w in zip(rows, widths) if w >= best - 1]))
        out.append((cx, cy))
    return out


def x_behind(a: np.ndarray, centres, r0: int = 11, r1: int = 18, need: int = 3) -> list[tuple[float, float]]:
    """An 'x' drawn exactly under a filled marker only shows its 4 arm tips beyond the marker's diagonal edges.
    Count a hidden 'x' at a marker centre when >= `need` of the 4 diagonal arms are dark between r0 and r1 px."""
    dark = a.max(2) < 100
    H, W = dark.shape
    out = []
    for cx, cy in centres:
        arms = 0
        for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            hits = tot = 0
            for t in range(r0, r1 + 1):
                x, y = int(round(cx + sx * t / 1.4142)), int(round(cy + sy * t / 1.4142))
                if 0 <= x < W and 0 <= y < H:
                    tot += 1
                    hits += bool(dark[max(0, y - 1):y + 2, max(0, x - 1):x + 2].any())
            arms += tot > 0 and hits / tot >= 0.6
        if arms >= need:
            out.append((float(cx), float(cy)))
    return out


def _refine_tick(profile: np.ndarray, guess: int, r: int = 3) -> float:
    i = np.arange(guess - r, guess + r + 1)
    w = profile[i].astype(float)
    return float((w * i).sum() / w.sum())


def run(name: str) -> dict:
    cfg = CONFIG[name]
    img = FIGS / f"{name}.png"
    pm = pymupdf.Pixmap(str(img))
    if pm.alpha:
        pm = pymupdf.Pixmap(pm, 0)
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.height, pm.width, pm.n)[..., :3].astype(int)
    darkness = 255 - a.min(2)
    axes_out = []
    for ax_name, ax in cfg["axes"].items():
        r0, r1 = ax["x_tick_band"]
        c0, c1 = ax["y_tick_band"]
        xp, yp = darkness[r0:r1, :].sum(0), darkness[:, c0:c1].sum(1)
        (gx1, vx1), (gx2, vx2) = ax["x_ticks"]
        (gy1, vy1), (gy2, vy2) = ax["y_ticks"]
        row, col = ax["x_axis_row"], ax["y_axis_col"]
        axes_out.append({"name": ax_name, "type": "XYAxes", "isLogX": ax["log_x"], "isLogY": False, "noRotation": False,
                         "calibrationPoints": [
                             {"px": _refine_tick(xp, gx1), "py": row, "dx": str(vx1), "dy": "0", "dz": None},
                             {"px": _refine_tick(xp, gx2), "py": row, "dx": str(vx2), "dy": "0", "dz": None},
                             {"px": col, "py": _refine_tick(yp, gy1), "dx": "0", "dy": str(vy1), "dz": None},
                             {"px": col, "py": _refine_tick(yp, gy2), "dx": "0", "dy": str(vy2), "dz": None}],
                         "metadata": {"calibrated_by": "ingest.autodigitize tick detection"}})
    y0, y1, x0, x1 = cfg["plot_box"]
    inside = np.zeros(a.shape[:2], bool)
    inside[y0:y1, x0:x1] = True
    datasets, found = [], {}
    for sname, s in cfg["series"].items():
        box_m = inside
        if "box" in s:
            by0, by1, bx0, bx1 = s["box"]
            box_m = np.zeros(a.shape[:2], bool)
            box_m[by0:by1, bx0:bx1] = True
        if s["kind"] == "filled":
            pts = filled_markers(colour_mask(a, s["rgb"]) & box_m, min_px=s.get("min_px", 15))
        elif s["kind"] == "plus":
            pts = plus_markers(colour_mask(a, s["rgb"]) & box_m)
        else:
            pts = x_markers(a, cfg["plot_box"], cfg["occluders"], s["half"], min_vis=s.get("min_vis", 0.5))
            for c in x_behind(a, found.get(s.get("hidden_behind"), [])):
                if all(np.hypot(c[0] - p[0], c[1] - p[1]) > 8 for p in pts):
                    pts.append(c)
        found[sname] = list(pts)
        pts.sort()
        datasets.append({"name": sname, "axesName": s.get("axes", "XY"), "colorRGB": [0, 0, 0, 255], "metadataKeys": [],
                         "data": [{"x": round(x, 2), "y": round(y, 2)} for x, y in pts]})
    return {"version": [4, 2], "axesColl": axes_out, "datasetColl": datasets, "measurementColl": [],
            "ignis": {"tool": "ingest.autodigitize@1 (colour/shape detection, no human clicks)", "image": str(img)}}


def overlay(name: str, project: dict) -> Path:
    img = FIGS / f"{name}.png"
    doc = pymupdf.open()
    pix = pymupdf.Pixmap(str(img))
    page = doc.new_page(width=pix.width, height=pix.height)
    page.insert_image(page.rect, filename=str(img))
    colours = {"ISS stable flame": (0, 0.8, 1), "ISS quench": (1, 0.5, 0), "ISS blowoff": (1, 0, 1),
               "Drop Tower blowoff": (0.9, 0.7, 0), "Drop Tower stable flame": (0, 0.6, 0)}
    for ds in project["datasetColl"]:
        for i, p in enumerate(ds["data"]):
            c = colours.get(ds["name"], (0, 1, 0))
            page.draw_circle((p["x"], p["y"]), 16, color=c, width=2.5)
            page.insert_text((p["x"] + 15, p["y"] - 12), f"{''.join(w[0] for w in ds['name'].split()).upper()}{i}", fontsize=13, color=c)
    for ax in project["axesColl"]:
        for cp in ax["calibrationPoints"]:
            page.draw_circle((cp["px"], cp["py"]), 6, color=(0, 0.7, 0), width=3)
    out = FIGS / f"{name}.overlay.png"
    page.get_pixmap(dpi=72).save(out)
    return out


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    name = (argv or sys.argv[1:])[0]
    proj = run(name)
    out = DIG / f"{name}.wpd.json"
    out.write_text(json.dumps(proj, indent=1), encoding="utf-8")
    ov = overlay(name, proj)
    for ds in proj["datasetColl"]:
        print(f"{ds['name']}: {len(ds['data'])} points")
    print(f"-> {out}\n-> {ov} (review)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
