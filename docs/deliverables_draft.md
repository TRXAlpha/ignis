# IGNIS deliverables draft (NASA Space Apps 2026, "Flame in Freefall")

Model numbers below come from `web/public/data/*.json` (model 0.1.0, 49 points machine-digitized from BASS-II Fig 6.10, 5-fold within-campaign CV). Re-check them after any re-export.

## 1. 30 s demo video

Voice-over, ~75 words total:

- 0.0-4.0 s: "Microgravity changes where flames stop burning. NASA flew the tests, but the results live in PDFs."
- 4.0-9.0 s: "IGNIS turns those pages into one cited model. Every data point traces back to a PDF page."
- 9.0-15.0 s: "The model gives a probability of burning, with uncertainty, not a guess."
- 15.0-21.0 s: "It flags where data is missing and proposes the next experiments with the highest information gain."
- 21.0-27.0 s: "For Artemis-era atmospheres, no flight data exists. IGNIS says so instead of making a number up."
- 27.0-30.0 s: "IGNIS. Fire safety you can check."

Shot list:

| Shot | Time | On screen |
|---|---|---|
| 1 | 0-4 s | Envelope 3D view: P(burns) surface over O2 x stretch rate, rotating slowly. Boundary 50% contour and 90% band visible. |
| 2 | 4-9 s | Click a point in the envelope. Provenance panel slides in: NASA BASS-II report, page 84, Figure 6.10, image hash, digitization method. |
| 3 | 9-15 s | Split view: model band vs 1g upward limit baseline (15.4 % O2, BASS-II report p84) drawn as a flat line. Placeholder 0.11 vs 0.64. |
| 4 | 15-21 s | Recommended next experiments list, each plotted as a marker on the envelope within the MSG facility range (flow 0-55 cm/s, O2 13.6-22.2 %). |
| 5 | 21-27 s | Habitat cards: ISS cabin, exploration 8.2 psia / 34 % O2, lunar and Mars lander 10.2 psia / 26.5 % O2. Cards show INSUFFICIENT DATA with the reason text, never a number. |
| 6 | 27-30 s | Logo, repo URL. |

## 2. 7-slide deck outline

Slide 1. Title: IGNIS, gravity-aware fire safety intelligence
- NASA Space Apps 2026, "Flame in Freefall"
- One cited model from published microgravity combustion data
- Team, date

Slide 2. Problem
- Flammability limits in microgravity are not intuitive from 1g rules
- Results are scattered across reports, mostly as figures in PDFs
- Engineers need a boundary with stated uncertainty, not a single number

Slide 3. Data
- NASA BASS-II ISS flight data, PMMA rods in the MSG flow duct
- Every point traceable to a PDF page, figure, series, and point index
- Points machine-detected from hash-pinned figure renders, saved as a WebPlotDigitizer project; the pipeline rejects unverifiable points
- Only accepted and human-verified observations enter the model (49 (27 stable, 8 quench, 14 blowoff) points)

Slide 4. Method
- Physics-form Bayesian boundary: quenching branch (exponential at low stretch) plus blowoff branch (linear at high stretch), the BASS-II functional form
- Parameters fitted to the observations, not copied from the paper
- Laplace approximation propagates parameter uncertainty into a 90% band

Slide 5. Validation
- Within-campaign 5-fold CV now; leave-one-campaign-out runs automatically once a second campaign has flame-state data
- Baseline: normal-gravity practice, burns iff O2 >= 15.4 % (1g upward limit, BASS-II report p84)
- Held-out boundary error 0.57 vs 1.09 O2 % points (1g rule); stable flames predicted burning 89 % vs 33 %; Brier 0.11 vs 0.64
- 91 % of held-out extinctions fall inside the 90 % interval (calibrated)
- Limitations stated in the export: gravity is a campaign nominal, pressure not reported for the rod tests

Slide 6. Recommender and habitat risk
- Recommender: information gain over the BASS-II MSG envelope (flow 0-55 cm/s, O2 13.6-22.2 %, BASS-II p72)
- Top-ranked conditions shown on the envelope with predicted P(burns)
- Habitat risk: ISS 14.7 psia / 21 % O2 has flight data; exploration atmosphere 8.2 psia / 34 % O2 and landers 10.2 psia / 26.5 % O2 have none, so the UI shows INSUFFICIENT DATA, never a number

Slide 7. Next steps
- Digitize the Saffire V figure (split-axis spec ready) and drop-tower series once g-level is sourced
- Add materials beyond PMMA
- More campaigns to make leave-one-campaign-out validation meaningful
- Pressure measurements to widen the domain of validity

## 3. Project page text (~250 words)

IGNIS turns published NASA microgravity combustion results into one cited, queryable model of where flames stop burning. It answers a concrete question for spacecraft fire safety: at a given oxygen fraction and flow stretch rate, does a thin solid fuel sustain burning in microgravity, and how confident are we?

Why it matters. Fire safety rules for spacecraft are still anchored to normal-gravity limits, and exploration missions plan atmospheres (8.2 psia / 34 % O2 in transit, 10.2 psia / 26.5 % O2 landers) where no microgravity flammability data exists. IGNIS makes that gap explicit instead of hiding it behind a number.

How it works. Most in-scope data exists only as figures. We render the figures from the NASA PDFs with pinned hashes, detect axis ticks and markers automatically (the output is a WebPlotDigitizer project anyone can open and correct), and a converter validates every point against the source page, axis calibration, and image hash before it enters a strict data contract. A physics-form Bayesian model (quenching plus blowoff branches, the BASS-II functional form) is fitted to the binary burn outcomes; a Laplace approximation gives a 90% uncertainty band. Validation runs against the 1g upward-spread limit of 15.4 % O2 (BASS-II report p84). A recommender picks the next experiments by expected information gain inside the BASS-II MSG facility envelope.

Tools: Python, numpy, JSON Schema, WebPlotDigitizer 4, pint, a static web frontend.

Honest limitations: one material (PMMA) and one campaign so far, gravity is a campaign nominal rather than measured per test, pressure was not reported for the rod tests, and habitat predictions outside the tested domain are shown as insufficient data, never as numbers.

## 4. Key numbers

From `web/public/data/` (export of 2026-11-15).

| Quantity | Value | Where it comes from |
|---|---|---|
| Digitized flame-state points used | 49 (27 stable, 8 quench, 14 blowoff) | model.json `points` |
| Minimum O2 for burning, median | 13.7 % O2 | model.json `min_o2.p50` |
| Minimum O2 90% band | 13.5-14.0 % O2 | model.json `min_o2.p05` / `p95` |
| Brier, model | 0.11 | validation.json folds / cv |
| Brier, 1g baseline | 0.64 | validation.json folds / cv |
| Held-out boundary RMSE, model vs 1g rule | 0.57 vs 1.09 O2 % points | validation.json cv |
| Held-out stable flames predicted burning | 89 % vs 33 % | validation.json cv |
| ISS habitat P(burns) | ~100 %, flagged extrapolation (21 % O2 is above the tested 13.5-18 %) | habitats.json `iss-cabin` prediction |
| Exploration habitat (8.2 psia / 34 % O2) | INSUFFICIENT DATA | habitats.json, prediction status |
| Lander habitats (10.2 psia / 26.5 % O2) | INSUFFICIENT DATA | habitats.json, prediction status |
| 1g upward-spread limit (sourced) | 15.4 % O2 | BASS-II report p84 |
| BASS-II reported boundary minimum (sourced) | ~13.5 % O2 at a = 8-12 1/s | BASS-II report p83 |
| BASS-II MSG facility ranges (sourced) | flow 0-55 cm/s, O2 13.6-22.2 % | BASS-II report p72 |
