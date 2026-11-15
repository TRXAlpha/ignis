"""Synthetic slideshow: a red bar moving a known number of px per still must give that speed back."""
import numpy as np

from model.video_spread import PHOTO, measure_topview


def _slideshow(px_per_still=4.0, n_stills=30, period=18, lateral=20, h=480, w=720):
    y0, y1, x0, x1 = PHOTO
    F = np.zeros((n_stills * period, h, w, 3), np.uint8)
    for s in range(n_stills):
        lead = 60 + px_per_still * s
        f = np.zeros((h, w, 3), np.uint8)
        yc = (y0 + y1) // 2
        f[yc - lateral // 2: yc + lateral // 2, x0 + 30: x0 + int(lead), 0] = 255   # red, R - G = 255
        F[s * period:(s + 1) * period] = f
    return F


def test_recovers_speed_and_scale():
    r = measure_topview(_slideshow(px_per_still=4.0, lateral=20), width_cm=2.0)
    assert r["ok"]
    assert abs(r["front_px_s"] - 4.0) < 0.2
    # 20 px = 2 cm -> 1 mm/px -> 4 mm/s
    assert abs(r["spread_mm_s"] - 4.0) < 0.4


def test_too_few_stills_rejected():
    r = measure_topview(_slideshow(n_stills=5), width_cm=2.0)
    assert not r["ok"]
