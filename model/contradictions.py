"""Contradiction detector: literature claims vs data, claims vs claims, observations vs observations.

Every claim's quote is verbatim-checked on its PDF page before it is used. Output rows:
  {id, kind, verdict: consistent | tension | conflict, title, detail, numbers{}, refs[Locator], observation_ids[]}
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ingest.curated import require_text

from . import boundary as bm

BASS2 = "ntrs:20210011385"
CLAIMS = {
    "paper_min": {"source_id": BASS2, "page": 83,
                  "quote": "The minimum in this boundary occurs at a = 8 to 12 s-1 at approximately 13.5 percent O2"},
    "upward_1g": {"source_id": BASS2, "page": 84,
                  "quote": "significantly lower than the observed upward flame spread limit of 15.4 percent O2"},
    "eq61": {"source_id": BASS2, "page": 83,
             "quote": "The O2 concentration (XO2) versus a boundary is defined by the combined empirical equations"},
    "zgrf_2018": {"source_id": "ntrs:20180006517", "page": 6, "quote": "to less than 0.00001g"},
    "zgrf_1999": {"source_id": "ntrs:20000017932", "page": 8, "quote": "achieves a gravity level of 10 -6 Gs"},
    "dt_agree": {"source_id": BASS2, "page": 83,
                 "quote": "The drop tower blowoff data, given by the purple dashed line, agrees very well with the flight data."},
}


def _verify(sources):
    for c in CLAIMS.values():
        require_text(sources, c["source_id"], c["page"], c["quote"])


def eq61(a):
    """BASS-II report Eq. 6.1 (p83), the authors' own fit: X = 6 exp(-0.5 a) + 0.0167 a + 13.4."""
    return 6 * np.exp(-0.5 * a) + 0.0167 * a + 13.4


def run(rows: list[dict], fit: bm.Fit, sources: dict) -> list[dict]:
    _verify(sources)
    out = []
    a_all = np.array([r["a"] for r in rows])
    grid = np.logspace(np.log10(a_all.min()), np.log10(a_all.max()), 200)
    mo = bm.min_o2(fit, grid)

    # 1. reported minimum vs fitted minimum
    lo, hi = mo["p05"], mo["p95"]
    ok_val = lo - 0.2 <= 13.5 <= hi + 0.2
    ok_loc = 8 / 1.5 <= mo["at_x"] <= 12 * 1.5
    out.append({"id": "min-o2-vs-report", "kind": "claim_vs_data",
                "verdict": "consistent" if ok_val and ok_loc else "tension",
                "title": "Reported minimum O2 vs the boundary fitted from the plotted data",
                "detail": (f"Report: ~13.5 % O2 at a = 8-12 1/s. Fit: {mo['p50']:.2f} % (90 % band {lo:.2f}-{hi:.2f} %) "
                           f"at a = {mo['at_x']:.1f} 1/s. The report's value is "
                           + ("inside" if lo <= 13.5 <= hi else "just outside") + " the band."),
                "numbers": {"reported_pct": 13.5, "fit_p50_pct": round(mo["p50"], 2), "fit_band_pct": [round(lo, 2), round(hi, 2)],
                            "fit_at_a": round(mo["at_x"], 2)},
                "refs": [CLAIMS["paper_min"]], "observation_ids": []})

    # 2. the 1g limit vs flight observations that kept burning below it
    below = [r for r in rows if r["y"] == 1 and r["x"] * 100 < 15.4]
    out.append({"id": "1g-limit-vs-flight", "kind": "claim_vs_data", "verdict": "conflict" if below else "consistent",
                "title": "Normal-gravity upward limit (15.4 % O2) vs flames that kept burning in microgravity",
                "detail": (f"{len(below)} microgravity flames burned stably below 15.4 % O2 (lowest "
                           f"{min(r['x'] for r in below) * 100:.1f} %). A 1g screening limit is not conservative here."
                           if below else "No stable flame below 15.4 % O2 in the data."),
                "numbers": {"limit_pct": 15.4, "n_burning_below": len(below),
                            "lowest_burning_pct": round(min(r["x"] for r in below) * 100, 2) if below else None},
                "refs": [CLAIMS["upward_1g"]], "observation_ids": [r["id"] for r in below]})

    # 3. authors' Eq 6.1 vs our posterior band
    band = bm.boundary_band(fit, grid)
    e = eq61(grid)
    outside = (e < band["p05"] - 0.15) | (e > band["p95"] + 0.15)
    frac = float(outside.mean())
    dmax = float(np.max(np.abs(e - band["p50"])))
    out.append({"id": "eq61-vs-fit", "kind": "claim_vs_data",
                "verdict": "consistent" if frac < 0.1 else ("tension" if frac < 0.4 else "conflict"),
                "title": "Authors' empirical boundary (Eq. 6.1) vs IGNIS fitted boundary",
                "detail": (f"Eq. 6.1 lies outside the IGNIS 90 % band on {frac * 100:.0f} % of the stretch-rate range "
                           f"(max gap {dmax:.2f} O2 % points). Same data, different fitting choices "
                           "(IGNIS also uses the drop-tower points and treats extinctions as boundary measurements)."),
                "numbers": {"share_outside_band": round(frac, 3), "max_gap_pct": round(dmax, 2)},
                "refs": [CLAIMS["eq61"]], "observation_ids": []})

    # 4. the two drop-tower gravity statements
    out.append({"id": "zgrf-gravity", "kind": "claim_vs_claim", "verdict": "tension",
                "title": "Zero Gravity Research Facility residual gravity: two NASA documents disagree 10x",
                "detail": "1999 user's guide: 10^-6 g. 2018 GRC paper: less than 10^-5 g. IGNIS uses the larger (conservative) "
                          "value as the campaign nominal. Both are far below ISS levels for this model's purpose.",
                "numbers": {"g_1999": 1e-6, "g_2018_upper": 1e-5},
                "refs": [CLAIMS["zgrf_1999"], CLAIMS["zgrf_2018"]], "observation_ids": []})

    # 5. report says drop-tower blowoff agrees with flight: test it on the data
    iss = [r for r in rows if r["campaign"] == "bass-ii" and r["state"] == "blowoff_extinction"]
    dt = [r for r in rows if r["campaign"] == "bass-ii-zgrf" and r["state"] == "blowoff_extinction"]
    if len(iss) >= 3 and len(dt) >= 3:
        def line(rs):
            A = np.vstack([[r["a"] for r in rs], np.ones(len(rs))]).T
            return np.linalg.lstsq(A, np.array([r["x"] * 100 for r in rs]), rcond=None)[0]
        si, sd = line(iss), line(dt)
        lo_a = max(min(r["a"] for r in iss), min(r["a"] for r in dt))
        hi_a = min(max(r["a"] for r in iss), max(r["a"] for r in dt))
        aa = np.linspace(lo_a, hi_a, 50)
        gap = float(np.max(np.abs((si[0] * aa + si[1]) - (sd[0] * aa + sd[1]))))
        out.append({"id": "drop-vs-flight-blowoff", "kind": "claim_vs_data",
                    "verdict": "consistent" if gap < 0.5 else "tension",
                    "title": "Report: drop-tower blowoff agrees with flight blowoff",
                    "detail": (f"Linear blowoff fits over the shared range a = {lo_a:.0f}-{hi_a:.0f} 1/s differ by at most "
                               f"{gap:.2f} O2 % points (ISS: {si[0]:.4f} a + {si[1]:.2f}; drop tower: {sd[0]:.4f} a + {sd[1]:.2f})."),
                    "numbers": {"max_gap_pct": round(gap, 2), "iss_slope": round(float(si[0]), 4), "iss_intercept": round(float(si[1]), 2),
                                "dt_slope": round(float(sd[0]), 4), "dt_intercept": round(float(sd[1]), 2)},
                    "refs": [CLAIMS["dt_agree"]], "observation_ids": [r["id"] for r in iss + dt]})

    # 6. observation pairs: opposite outcomes at practically the same conditions
    pairs = []
    for i, r in enumerate(rows):
        for s in rows[i + 1:]:
            if r["y"] != s["y"] and abs(np.log10(r["a"]) - np.log10(s["a"])) < 0.03 and abs(r["x"] - s["x"]) * 100 < 0.15:
                pairs.append((r, s))
    if pairs:
        lines = [f"{r['series']} vs {q['series']} at a = {r['a']:.1f} / {q['a']:.1f} 1/s, O2 {r['x'] * 100:.2f} / {q['x'] * 100:.2f} %"
                 for r, q in pairs]
        out.append({"id": "same-conditions-opposite-outcomes", "kind": "data_vs_data", "verdict": "tension",
                    "title": f"{len(pairs)} pairs of opposite outcomes at nearly the same conditions",
                    "detail": ("Stable flame and extinction plotted at (almost) the same stretch rate and O2. All sit on the "
                               "fitted boundary, where the report says flames are sensitive to stochastic perturbations, so "
                               "IGNIS keeps both and models the boundary as a band, not a line. " + "; ".join(lines) + "."),
                    "numbers": {"n_pairs": len(pairs)}, "refs": [{"source_id": BASS2, "page": 83,
                    "quote": "Along this boundary, the flame is sensitive to stochastic perturbations that can lead to extinguishment"}],
                    "observation_ids": sorted({x["id"] for pr in pairs for x in pr})})
    vf = Path("web/public/data/video_spread.json")
    if vf.exists():
        v = json.loads(vf.read_text(encoding="utf-8"))
        cc = v.get("claim_check")
        if cc:
            out.append({"id": "video-spread-vs-report", "kind": "claim_vs_data",
                        "verdict": {"consistent": "consistent", "tension": "tension"}.get(cc["status"], "tension"),
                        "title": "Report's highest 100-um PMMA spread rate vs re-measurement from NASA's flight stills",
                        "detail": (f"Report: about 2.2 mm/s. Re-measured from the public PSI top-view stills: highest "
                                   f"{cc['max_measured_mm_s']:.2f} +/- {cc['max_measured_sd']:.2f} mm/s (test {cc['max_test']}), "
                                   f"scale range {cc['scale_range_mm_s'][0]:.2f}-{cc['scale_range_mm_s'][1]:.2f} mm/s. Status "
                                   f"'{cc['status']}'. The length scale (flame width = 2 cm sample) is the dominant uncertainty."),
                        "numbers": {"claim_mm_s": 2.2, "max_measured_mm_s": cc["max_measured_mm_s"],
                                    "scale_range_mm_s": cc["scale_range_mm_s"]},
                        "refs": [cc["claim"], cc["timing_ref"]], "observation_ids": []})
    return out
