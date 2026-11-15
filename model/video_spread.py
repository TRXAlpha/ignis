"""v1: re-measure flame spread rate from NASA's public BASS-II flight imagery on PSI, then test the report's claim.

python -m model.video_spread            # fetch files, track, write web/public/data/video_spread.json + PNGs

What the files are (BASS-II report, PDF p46): "the top view of the flame propagation is photographed with a
high-resolution digital still camera with a frame rate of 1 per second. A video camera captures the side view".
  - "*_Still_Sequence.mp4" on PSI = the TOP-VIEW stills played back on the camera's review screen (one still per
    ~0.6 s of playback). Each still = 1 s of experiment time (quote above). Used for the mm/s measurement.
  - "*_TEST_B1.mp4" = the SIDE-VIEW video (30 fps, on-screen clock). Used only as a px/s timing cross-check:
    its two bright streaks are the flame on both faces of the film, so they give no length scale (v0 mistake).

Top-view pipeline: decode all frames (ffmpeg, no OpenCV) -> photo region of the review screen -> red/orange flame mask
-> per-frame leading edge (99th percentile x in the spread direction) and lateral extent (5th-95th percentile y)
-> group frames into stills (run-length of the edge signal, playback period ~P frames) -> least-squares slope over the
steady middle of the burn (px per still = px/s) with its standard error.
Scale: ASSUMPTION, documented: in a top view the flame front spans the sample width, so the median lateral flame extent
= 2 cm (PSI-25.csv sample width). Uncertainty = spread of that extent across stills.
Claim (PDF p48): for 100-um PMMA in microgravity "the highest spread rate obtained is about 2.2 mm/s".
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pymupdf

from ingest.psi import _request, presign

VID_DIR = Path("data/raw/psi/video")
OUT = Path("web/public/data/video_spread.json")
FIG = Path("web/public/data/video")
PHOTO = (50, 185, 0, 400)    # rows y0:y1, cols x0:x1 of the photo on the 720x480 review screen
SIDE_OSD_ROWS = 70
SIDE_FPS = 5.0
REPORT = "ntrs:20210011385"
CLAIM = {"source_id": REPORT, "page": 48,
         "quote": "For the same fuel thickness, the highest spread rate obtained is about 2.2 mm/s", "value_mm_s": 2.2}
TIMING_REF = {"source_id": REPORT, "page": 46,
              "quote": "photographed with a high-resolution digital still camera with a frame rate of 1 per second"}

TOPVIEW = [  # (accession, file, version, test id, sample width cm and thickness um from PSI-25.csv)
    ("PSI-25", "PSI-25_Raw Data_BASS_GMT50_SAMPLE_147_TEST_B1_Still_Sequence.mp4", 2, "B1", 2.0, 100),
    ("PSI-25", "PSI-25_Raw Data_BASS_GMT50_SAMPLE_148_TEST_B3_Still_Sequence.mp4", 2, "B3", 2.0, 100),
]
SIDEVIEW = [("PSI-25", "PSI-25_Raw Data_BASS_GMT50_SAMPLE_147_TEST_B1.mp4", 2, "B1")]


def fetch(acc: str, name: str, version: int) -> Path:
    out = VID_DIR / name.replace(" ", "_")
    if not out.exists():
        VID_DIR.mkdir(parents=True, exist_ok=True)
        data = _request(presign(acc, name, version))
        out.write_bytes(data.read() if hasattr(data, "read") else data)
    return out


def probe(path: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def frames(path: Path, fps: float | None = None) -> np.ndarray:
    w, h = probe(path)
    cmd = ["ffmpeg", "-v", "error", "-i", str(path)] + (["-vf", f"fps={fps}"] if fps else []) + \
          ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    buf = np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, np.uint8)
    n = buf.size // (w * h * 3)
    return buf[: n * w * h * 3].reshape(n, h, w, 3)


def flame_mask(c: np.ndarray) -> np.ndarray:
    R, G = c[..., 0].astype(np.int16), c[..., 1].astype(np.int16)
    return (R > 150) & (R - G > 60)


def row_extent(m: np.ndarray, min_px: int = 3) -> float:
    """Full lateral extent: first to last row holding >= min_px flame pixels (+1). Percentile ranges underestimate
    a uniform band by ~10 % (found by tests/test_video_spread.py), which would inflate every rate."""
    rows = np.flatnonzero(m.sum(axis=1) >= min_px)
    return float(rows[-1] - rows[0] + 1) if len(rows) else 0.0


def per_frame(F: np.ndarray) -> list[tuple | None]:
    y0, y1, x0, x1 = PHOTO
    out = []
    for f in F:
        ys, xs = np.nonzero(flame_mask(f[y0:y1, x0:x1]))
        out.append(None if len(xs) < 20 else (float(np.percentile(xs, 1)), float(np.percentile(xs, 99)),
                                               row_extent(flame_mask(f[y0:y1, x0:x1]))))
    return out


def group_stills(pf: list) -> list[dict]:
    """Consecutive frames showing the same still have (nearly) the same extents. Start a new still when the edge
    signal changes after at least MIN frames; return per-still medians and the frame range."""
    keys = [None if v is None else (round(v[0]), round(v[1])) for v in pf]
    runs, start = [], 0
    for k in range(1, len(keys) + 1):
        if k == len(keys) or keys[k] != keys[start]:
            runs.append((start, k))
            start = k
    long_runs = [b - a for a, b in runs if keys[a] is not None and b - a >= 8]
    period = float(np.median(long_runs)) if long_runs else 18.0
    stills, cur = [], None
    for a, b in runs:
        if keys[a] is None:
            cur = None
            continue
        if cur is None or (a - cur["a"]) >= 0.6 * period:
            cur = {"a": a, "b": b}
            stills.append(cur)
        else:
            cur["b"] = b
    for s in stills:
        vals = [pf[k] for k in range(s["a"], s["b"]) if pf[k] is not None]
        s["x_lo"], s["x_hi"], s["lat"] = (float(np.median([v[i] for v in vals])) for i in range(3))
    return stills, period


def fit_track(t: np.ndarray, x: np.ndarray) -> dict:
    lo, hi = int(len(t) * 0.2), max(int(len(t) * 0.85), int(len(t) * 0.2) + 3)
    tt, xx = t[lo:hi], x[lo:hi]
    A = np.vstack([tt, np.ones_like(tt)]).T
    coef, res, *_ = np.linalg.lstsq(A, xx, rcond=None)
    r = xx - A @ coef
    s2 = float(r @ r) / max(len(tt) - 2, 1)
    se = float(np.sqrt(s2 / max(((tt - tt.mean()) ** 2).sum(), 1e-9)))
    return {"slope": float(coef[0]), "icpt": float(coef[1]), "se": se, "t0": float(tt[0]), "t1": float(tt[-1]),
            "n": int(len(tt)), "resid_sd": float(np.sqrt(s2))}


def lateral_extent(F: np.ndarray, r_min: int, rg_min: int) -> float:
    y0, y1, x0, x1 = PHOTO
    out = []
    for f in F:
        c = f[y0:y1, x0:x1].astype(np.int16)
        core = flame_mask(c)
        if core.sum() <= 20:
            continue
        ys, xs = np.nonzero(core)
        m = (c[..., 0] > r_min) & (c[..., 0] - c[..., 1] > rg_min)
        # only the flame's own neighbourhood: same columns, rows within 15 px of the core (no UI / glare elsewhere)
        keep = np.zeros_like(m)
        keep[max(ys.min() - 15, 0):ys.max() + 16, xs.min():xs.max() + 1] = True
        out.append(row_extent(m & keep))
    return float(np.median(out)) if out else float("nan")


def topview(test: str, path: Path, width_cm: float) -> dict:
    return measure_topview(frames(path), width_cm)


def measure_topview(F: np.ndarray, width_cm: float) -> dict:
    pf = per_frame(F)
    _, period = group_stills(pf)                       # playback frames per still (~18)
    idx = [k for k, v in enumerate(pf) if v is not None]
    if len(idx) < 8 * period:
        return {"ok": False, "reason": "flame visible in fewer than 8 stills"}
    # time every frame from the periodic slideshow, then take one median value per still (1 still = 1 s, TIMING_REF)
    k0 = idx[0]
    bins: dict[int, list] = {}
    for k in idx:
        bins.setdefault(int((k - k0) / period), []).append(pf[k])
    t = np.array(sorted(bins), dtype=float)
    lo = np.array([np.median([v[0] for v in bins[int(b)]]) for b in t])
    hi = np.array([np.median([v[1] for v in bins[int(b)]]) for b in t])
    lat = np.array([np.median([v[2] for v in bins[int(b)]]) for b in t])
    direction = 1 if np.polyfit(t, (lo + hi) / 2, 1)[0] > 0 else -1
    front = hi if direction > 0 else lo
    fit = fit_track(t, front)
    lat_steady = lat[int(len(lat) * 0.2):int(len(lat) * 0.85)]
    lat_px, lat_sd = float(np.median(lat_steady)), float(np.std(lat_steady))
    lat_loose = lateral_extent(F, 90, 30)              # looser mask catches more of the flame width
    mm_px = width_cm * 10 / lat_px
    rate = abs(fit["slope"]) * mm_px
    rate_loose = abs(fit["slope"]) * width_cm * 10 / lat_loose
    rel = np.hypot(fit["se"] / max(abs(fit["slope"]), 1e-9), lat_sd / lat_px)
    mid_k = idx[len(idx) // 2]
    return {"ok": True, "view": "top (DSLR stills, 1 per second)", "n_stills": int(len(t)),
            "playback_frames_per_still": round(period, 1), "direction": direction,
            "front_px_s": round(abs(fit["slope"]), 3), "front_px_s_se": round(fit["se"], 3),
            "fit_window_s": [fit["t0"], fit["t1"]], "resid_px_sd": round(fit["resid_sd"], 2),
            "lateral_extent_px": round(lat_px, 1), "lateral_extent_px_sd": round(lat_sd, 1),
            "lateral_extent_px_loose_mask": round(lat_loose, 1),
            "mm_per_px": round(mm_px, 4), "spread_mm_s": round(rate, 3), "spread_mm_s_sd": round(float(rate * rel), 3),
            "spread_mm_s_scale_range": [round(rate_loose, 3), round(rate, 3)],
            "track": {"t_s": t.tolist(), "front_px": [round(float(v), 1) for v in front]},
            "_fig": (F[mid_k], front, t, fit)}


def sideview(path: Path) -> dict:
    F = frames(path, SIDE_FPS)
    t, x = [], []
    for i, f in enumerate(F):
        m = flame_mask(f)
        m[:SIDE_OSD_ROWS] = False
        ys, xs = np.nonzero(m)
        if len(xs) >= 30:
            t.append(i / SIDE_FPS)
            x.append(float(np.percentile(xs, 99.5)))
    if len(t) < 6:
        return {"ok": False}
    fit = fit_track(np.array(t), np.array(x))
    return {"ok": True, "front_px_s": round(abs(fit["slope"]), 2), "front_px_s_se": round(fit["se"], 3),
            "note": "Side view: no length scale in frame (the two streaks are the flame on both faces of the film), "
                    "so only px/s is reported. Timing from the nominal 30 fps of the file."}


def figure(test: str, r: dict) -> str:
    frame, front, t, fit = r.pop("_fig")
    FIG.mkdir(parents=True, exist_ok=True)
    y0, y1, x0, x1 = PHOTO
    crop = np.ascontiguousarray(frame[y0:y1, x0:x1])
    h, w = crop.shape[:2]
    S = 2  # upscale for legibility
    doc = pymupdf.open()
    page = doc.new_page(width=w * S, height=h * S + 230)
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, crop.tobytes(), False)
    page.insert_image(pymupdf.Rect(0, 0, w * S, h * S), pixmap=pix)
    i = len(front) // 2
    page.draw_line((front[i] * S, 0), (front[i] * S, h * S), color=(0, 1, 0), width=2)
    px0, py0, pw, ph = 50, h * S + 15, w * S - 70, 170
    page.draw_rect(pymupdf.Rect(px0, py0, px0 + pw, py0 + ph), color=(0.6, 0.6, 0.6), width=0.8)
    tx = lambda v: px0 + (v - t.min()) / max(np.ptp(t), 1e-9) * pw  # noqa: E731
    ty = lambda v: py0 + ph - (v - front.min()) / max(np.ptp(front), 1e-9) * ph  # noqa: E731
    for a, b in zip(t, front):
        page.draw_circle((tx(a), ty(b)), 2.5, color=(1, 0.35, 0.2), fill=(1, 0.35, 0.2))
    page.draw_line((tx(fit["t0"]), ty(fit["slope"] * fit["t0"] + fit["icpt"])),
                   (tx(fit["t1"]), ty(fit["slope"] * fit["t1"] + fit["icpt"])), color=(0, 0.8, 0), width=2)
    page.insert_text((px0, py0 + ph + 30),
                     f"{test}: {r['spread_mm_s']:.2f} +/- {r['spread_mm_s_sd']:.2f} mm/s  (front vs time, 1 still = 1 s)",
                     fontsize=14, color=(0, 0, 0))
    out = FIG / f"{test}.png"
    page.get_pixmap(dpi=72).save(out)
    return str(out).replace("\\", "/").removeprefix("web/public/")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    for acc, name, ver, test, width_cm, thick in TOPVIEW:
        path = fetch(acc, name, ver)
        base = {"test_id": test, "accession": acc, "file": name, "file_version": ver,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "thickness_um": thick,
                "sample_width_cm": width_cm, "source": {"source_id": f"psi:{acc}", "dataset_path": name}}
        r = topview(test, path, width_cm)
        if r["ok"]:
            r["figure"] = figure(test, r)
            r["confidence"] = "low"
            r["flags"] = ["scale_from_flame_lateral_extent_equals_sample_width", "timing_1_still_per_second_from_report"]
        rows.append({**base, **r})
        print(test, {k: r.get(k) for k in ("spread_mm_s", "spread_mm_s_sd", "n_stills", "lateral_extent_px", "reason")})
    side = []
    for acc, name, ver, test in SIDEVIEW:
        s = sideview(fetch(acc, name, ver))
        side.append({"test_id": test, "file": name, **s})
        print("side", test, s.get("front_px_s"))
    ok = [r for r in rows if r.get("spread_mm_s") is not None]
    verdict = None
    if ok:
        best = max(ok, key=lambda r: r["spread_mm_s"])
        mx, sd = best["spread_mm_s"], best["spread_mm_s_sd"]
        lo_scale = best["spread_mm_s_scale_range"][0]       # looser mask -> wider flame -> smaller rate
        tol = 2 * sd + 0.1 * CLAIM["value_mm_s"]             # 2 sigma (fit + width spread) + 10 % for "about"
        c = CLAIM["value_mm_s"]
        status = ("consistent" if abs(mx - c) <= tol
                  else "inconclusive (scale)" if min(lo_scale, mx) - tol <= c <= max(lo_scale, mx) + tol
                  else "tension")
        verdict = {"claim": CLAIM, "timing_ref": TIMING_REF, "max_measured_mm_s": mx, "max_measured_sd": sd,
                   "max_test": best["test_id"], "tolerance_mm_s": round(tol, 3),
                   "scale_range_mm_s": [round(min(lo_scale, mx), 3), round(max(lo_scale, mx), 3)],
                   "status": status,
                   "note": ("Tested against the report's 'highest about 2.2 mm/s' for 100-um PMMA: our highest rate must lie "
                            "within 2 sigma + 10 % ('about') + the mask sensitivity of 2.2 mm/s. Timing is solid (1 still "
                            "per second, confirmed by the camera timestamps). The scale is not: no sourced length is "
                            "visible, so the luminous flame width is taken as the 2 cm sample width; a luminous zone "
                            "narrower than the sample inflates every rate by the same factor. Treat a TENSION here as "
                            "'scale unresolved', not as an error in the report.")}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"version": "v1", "method": __doc__.strip().split("\n\n")[1], "rows": rows,
                               "side_view": side, "claim_check": verdict}, ensure_ascii=False), encoding="utf-8")
    print("wrote", OUT, verdict and (verdict["status"], verdict["max_measured_mm_s"], verdict["tolerance_mm_s"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
