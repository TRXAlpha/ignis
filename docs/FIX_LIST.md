# Fix list (for the final hours)

Ordered by impact on credibility. Each item: what is wrong, how to see it, what done looks like.

## Flight-video re-measurement (`model/video_spread.py`, site section "Re-measured from NASA flight video", beta v0)

1. **Scale is an assumption.** mm/px comes from the vertical gap between the two flame streaks, assumed to be the 2 cm
   sample width. Unverified: the streaks may be the flame on both faces of the film seen at an angle, not the sample edges.
   Done = scale from a sourced dimension visible in the frame (sample holder / igniter size from the BASS-II hardware
   description, or a calibration frame on PSI), quoted and verified like every other number.
2. **Result disagrees with the report.** B1 gives 3.36 mm/s vs "the highest spread rate obtained is about 2.2 mm/s"
   (p48). Probably fix 1. Do not "fix" by tuning until it matches; fix the scale, then report whatever comes out.
3. **One test only.** B3 on PSI is a "Still_Sequence" (DSLR review-screen playback, no time axis) and was excluded.
   Find timed videos for the other 100-um tests (B3, B6, B9, B19, B20 in PSI-25.csv) via the PSI file list.
4. **Timing from nominal fps.** The on-screen clock (HH:MM:SS) is burned into each frame; use it to check the fps
   assumption (frames dropped/duplicated would bias the rate).
5. **Fixed thresholds** (R > 120, R - G > 50, OSD band = top 70 rows) tuned on one video. Make them per-video or adaptive.
6. **Claim-check rule is arbitrary** (consistent if <= 1.25 x 2.2 mm/s). Replace with the measurement's own uncertainty
   (fit residual + scale uncertainty) vs the claim.
7. **No tests.** Add a synthetic-video test (moving bright bar at a known px/s) for `track()`.
8. **Not wired into contradictions / analyst / README / DELIVERABLES.** Once 1-2 are fixed, add a contradiction item,
   an analyst tool, a README coverage row and a deck line.
9. **Video files are not in fetch_sources** (they are fetched on demand into data/raw/psi/video, sha256 recorded in the
   output). Decide whether they are registry sources.

## Found in the audit

10. **Duplicate validation folds.** `validation.json` has the two leave-one-campaign-out folds twice (primary fit and the
    identical pmma/rod/concurrent/stretch_rate group); the site shows both. Skip group folds identical to the primary.
11. **Only one fitted group.** Of 66 BASS-II per-test rows only 9 have an explicit extinction flow in cm/s, so no other
    material gets a boundary. The selector shows a single group. Either hide it until there are >= 2 groups or say why.
12. **43 flagged per-test rows** (quench vs self-extinguished from wording). Review a sample by hand against the PDF and
    promote or fix them.
13. **`tools/` is committed** with scratch scripts (appendix_dump.py, quote_check.py). Keep appendix_rows.py (needed to
    regenerate), drop or document the rest.
14. **Wording:** DELIVERABLES says "Thin PMMA rods" (rods are not thin); README novelty lines should mention the video
    probe only once it is fixed.
