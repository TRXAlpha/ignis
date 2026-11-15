"""v0 (rough on purpose): re-measure flame spread rate from NASA's public BASS-II flight video on PSI.

python -m model.video_spread            # fetch videos, track, write web/public/data/video_spread.json + PNGs

Pipeline per video:
  frames  : ffmpeg -> gray-free RGB raw frames at FPS_SAMPLE (no OpenCV dependency)
  mask    : red flame pixels (R high, R >> G), on-screen-display band at the top ignored
  front   : leading edge = extreme flame pixel along x in the direction the flame centroid moves
  rate    : least-squares slope of front(t) over the middle 60 % of the burning interval, px/s
  scale   : ASSUMPTION (v0): the two bright streaks are the sample edges, so their vertical separation = sample width
            (2 cm from the PSI-25 table). Unverified -> confidence low, flagged in the output.
Compared with the report's claim (PDF p48): for 100-um PMMA in microgravity "the highest spread rate obtained is about 2.2 mm/s".

KNOWN v0 DEFECTS (fix list): scale assumption; fixed thresholds; no perspective / lens correction; edge pixel noise;
no check that the camera did not zoom/pan; only 1 test; frame timing from nominal fps, not the on-screen clock.
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
FPS_SAMPLE = 5.0
OSD_ROWS = 70           # on-screen display text band (time stamp, AIR/FAN readings) at 720x480
CLAIM = {"source_id": "ntrs:20210011385", "page": 48,
         "quote": "For the same fuel thickness, the highest spread rate obtained is about 2.2 mm/s", "value_mm_s": 2.2}

VIDEOS = [  # (PSI accession, file name, version, test id, sample width cm from PSI-25.csv, thickness um)
    ("PSI-25", "PSI-25_Raw Data_BASS_GMT50_SAMPLE_147_TEST_B1.mp4", 2, "B1", 2.0, 100),
]
# Excluded: B3 "Still_Sequence.mp4" is a playback of DSLR stills on the camera review screen (no real time axis).
# FIX LIST: find timed videos for the other 100-um tests (B3, B6, B9, B19, B20 per PSI-25.csv) on PSI.


def fetch(acc: str, name: str, version: int) -> Path:
    out = VID_DIR / name.replace(" ", "_")
    if not out.exists():
        VID_DIR.mkdir(parents=True, exist_ok=True)
        data = _request(presign(acc, name, version))
        out.write_bytes(data.read() if hasattr(data, "read") else data)
    return out


def probe(path: Path) -> tuple[int, int, float]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    w, h, fr = r.stdout.strip().split(",")[:3]
    num, den = fr.split("/")
    return int(w), int(h), float(num) / float(den or 1)


def frames(path: Path, w: int, h: int):
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={FPS_SAMPLE}", "-f", "rawvideo",
                        "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    buf = np.frombuffer(p.stdout, np.uint8)
    n = buf.size // (w * h * 3)
    return buf[: n * w * h * 3].reshape(n, h, w, 3)


def flame_mask(f: np.ndarray) -> np.ndarray:
    R, G, B = (f[..., i].astype(int) for i in range(3))
    m = (R > 120) & (R - G > 50)
    m[:OSD_ROWS] = False
    return m


def track(path: Path) -> dict:
    w, h, _ = probe(path)
    F = frames(path, w, h)
    t, xmax, xmin, cx, sep = [], [], [], [], []
    for i, f in enumerate(F):
        m = flame_mask(f)
        if m.sum() < 30:
            continue
        ys, xs = np.nonzero(m)
        t.append(i / FPS_SAMPLE)
        xmax.append(np.percentile(xs, 99.5))
        xmin.append(np.percentile(xs, 0.5))
        cx.append(xs.mean())
        # two-streak separation: centroid of upper vs lower half of flame rows
        mid = np.median(ys)
        up, lo = ys[ys < mid], ys[ys >= mid]
        if len(up) > 10 and len(lo) > 10:
            sep.append(lo.mean() - up.mean())
    t, xmax, xmin, cx = map(np.array, (t, xmax, xmin, cx))
    if len(t) < 6:
        return {"ok": False, "reason": "flame visible in fewer than 6 sampled frames"}
    direction = 1 if np.polyfit(t, cx, 1)[0] > 0 else -1
    front = xmax if direction > 0 else xmin
    lo_i, hi_i = int(len(t) * 0.2), int(len(t) * 0.8)
    slope, icpt = np.polyfit(t[lo_i:hi_i], front[lo_i:hi_i], 1)
    resid = front[lo_i:hi_i] - (slope * t[lo_i:hi_i] + icpt)
    return {"ok": True, "w": w, "h": h, "n_frames": int(len(F)), "t": t.tolist(), "front_px": front.tolist(),
            "fit": {"slope_px_s": float(abs(slope)), "intercept": float(icpt), "t0": float(t[lo_i]), "t1": float(t[hi_i - 1]),
                    "resid_px_sd": float(resid.std())},
            "streak_sep_px": float(np.median(sep)) if sep else None, "direction": direction,
            "frame_for_figure": int(np.argmin(np.abs(np.arange(len(F)) / FPS_SAMPLE - t[len(t) // 2]))), "_F": F}


def figure(name: str, r: dict, mm_per_px: float | None) -> str:
    """Write a PNG: mid-burn frame with the tracked front line + position-vs-time plot."""
    FIG.mkdir(parents=True, exist_ok=True)
    f = r["_F"][r["frame_for_figure"]]
    h, w = f.shape[:2]
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h + 260)
    pix = pymupdf.Pixmap(pymupdf.csRGB, w, h, np.ascontiguousarray(f).tobytes(), False)
    page.insert_image(pymupdf.Rect(0, 0, w, h), pixmap=pix)
    t, x = np.array(r["t"]), np.array(r["front_px"])
    i = int(np.argmin(np.abs(t - r["frame_for_figure"] / FPS_SAMPLE)))
    page.draw_line((x[i], OSD_ROWS), (x[i], h - 5), color=(0, 1, 0), width=2)
    # plot
    x0, y0, pw, ph = 50, h + 20, w - 80, 200
    page.draw_rect(pymupdf.Rect(x0, y0, x0 + pw, y0 + ph), color=(0.6, 0.6, 0.6), width=0.8)
    tx = lambda v: x0 + (v - t.min()) / max(np.ptp(t), 1e-9) * pw  # noqa: E731
    ty = lambda v: y0 + ph - (v - x.min()) / max(np.ptp(x), 1e-9) * ph  # noqa: E731
    for a, b in zip(t, x):
        page.draw_circle((tx(a), ty(b)), 2, color=(1, 0.3, 0.3), fill=(1, 0.3, 0.3))
    s, c = r["fit"]["slope_px_s"] * r["direction"], r["fit"]["intercept"]
    page.draw_line((tx(r["fit"]["t0"]), ty(s * r["fit"]["t0"] + c)), (tx(r["fit"]["t1"]), ty(s * r["fit"]["t1"] + c)),
                   color=(0, 1, 0), width=2)
    label = f"{name}: front {r['fit']['slope_px_s']:.1f} px/s" + (f" = {r['fit']['slope_px_s'] * mm_per_px:.2f} mm/s (v0 scale)"
                                                                   if mm_per_px else "")
    page.insert_text((x0, y0 + ph + 30), label, fontsize=16, color=(0, 0, 0))
    out = FIG / f"{name}.png"
    page.get_pixmap(dpi=72).save(out)
    return str(out).replace("\\", "/").removeprefix("web/public/")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    for acc, name, ver, test, width_cm, thick_um in VIDEOS:
        path = fetch(acc, name, ver)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        r = track(path)
        row = {"test_id": test, "accession": acc, "file": name, "file_version": ver, "sha256": sha,
               "thickness_um": thick_um, "sample_width_cm": width_cm,
               "source": {"source_id": f"psi:{acc}", "dataset_path": name}}
        if not r["ok"]:
            rows.append({**row, "ok": False, "reason": r["reason"]})
            continue
        mm_per_px = (width_cm * 10 / r["streak_sep_px"]) if r["streak_sep_px"] else None
        rate = r["fit"]["slope_px_s"] * mm_per_px if mm_per_px else None
        rows.append({**row, "ok": True, "spread_px_s": round(r["fit"]["slope_px_s"], 2),
                     "fit_window_s": [round(r["fit"]["t0"], 1), round(r["fit"]["t1"], 1)],
                     "resid_px_sd": round(r["fit"]["resid_px_sd"], 2), "streak_sep_px": r["streak_sep_px"],
                     "mm_per_px": mm_per_px, "spread_mm_s": round(rate, 3) if rate else None,
                     "confidence": "low", "flags": ["scale_from_assumed_streak_separation", "nominal_fps_timing"],
                     "figure": figure(test, r, mm_per_px),
                     "track": {"t_s": [round(v, 2) for v in r["t"]], "front_px": [round(v, 1) for v in r["front_px"]]}})
        print(f"{test}: {r['fit']['slope_px_s']:.2f} px/s, sep {r['streak_sep_px']} px -> {rate} mm/s")
    ok = [r for r in rows if r.get("spread_mm_s")]
    verdict = None
    if ok:
        mx = max(r["spread_mm_s"] for r in ok)
        verdict = {"claim": CLAIM, "max_measured_mm_s": mx,
                   "status": "consistent" if mx <= CLAIM["value_mm_s"] * 1.25 else "tension",
                   "note": "v0 measurement with an unverified scale; treat as a reproducibility probe, not a result."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"version": "v0", "method": __doc__.strip().split("\n\n")[1], "rows": rows,
                               "claim_check": verdict}, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
