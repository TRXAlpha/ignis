# IGNIS: submission deliverables

NASA Space Apps 2026, challenge "Flame in Freefall".
**Live:** https://ignis-flame-one.vercel.app · **Code:** https://github.com/TRXAlpha/ignis

All numbers below come from `web/public/data/*.json` (model `ignis-boundary` 0.1.0, export of 2026-11-15) or from a
quoted NASA PDF page. Re-check after any re-export.

## Key numbers

| Quantity | Value | Source |
|---|---|---|
| Observations in bundle | 158 (115 accepted, 43 flagged) from 13 sources: NTRS reports + 5 NASA PSI experimental tables (CC0, DOIs) | bundle.json |
| BASS-II flight tests with recorded outcome | 66 (6 material/geometry groups); outcome quoted from the report, O2 from the PSI-25 table | test_outcomes.json |
| Saffire-II, same material in orbit vs 1g | silicone: 3 of 4 samples burned in 1g but not in orbit (20 cm/s, ~22 % O2); SIBAL and PMMA burned in both | material_screen.json, PSI-99 |
| Flame-state points | 49 ISS (27 stable, 8 quench, 14 blowoff) + 22 drop tower (13 stable, 9 blowoff) | BASS-II report Fig 6.10, p84 |
| Minimum O2 for burning (fit) | 13.6 % (90 % band 13.4-13.9 %) at a = 9.9 1/s | model.json |
| Same, as stated by the report | ~13.5 % at a = 8-12 1/s | BASS-II report p83 |
| Normal-gravity upward limit | 15.4 % O2 | BASS-II report p84 |
| Microgravity flames burning below that limit | 24 (lowest 13.6 %) | contradictions.json |
| Leave-one-campaign-out, train ISS, test drop tower | boundary error 2.0 % vs 2.7 % (1g rule); Brier 0.05 vs 0.44 | validation.json |
| Leave-one-campaign-out, train drop tower, test ISS | boundary error 4.3 % vs 6.2 %; Brier 0.03 vs 0.64 | validation.json |
| 5-fold CV, held-out boundary RMSE | 0.57 vs 1.00 O2 % points (1g rule) | validation.json |
| 5-fold CV, held-out stable flames predicted burning | 90 % vs 40 % | validation.json |
| 90 % interval coverage of held-out extinctions | 94 % | validation.json |
| ISS cabin (14.7 psia, 21 % O2) | P(burns) ~100 %, flagged extrapolation (above tested 13.5-18 % O2) | habitats.json |
| Exploration 8.2 psia / 34 %, lunar and Mars lander 10.2 psia / 26.5 % | INSUFFICIENT DATA (pressure / partial gravity outside any flight data) | habitats.json |

## 30 s demo video

Voice-over (about 75 words):

| Time | Voice-over | On screen |
|---|---|---|
| 0-4 s | "NASA has flown fire experiments on the Space Station. The results are locked in PDFs." | BASS-II report page with Fig 6.10 |
| 4-9 s | "IGNIS reads them, and every point links back to its page." | Envelope 2D view; click a blowoff point; provenance panel shows PDF page 84, figure, pixel, image hash |
| 9-15 s | "The model learns where flames go out, with a band, not a guess." | Boundary curve with 90 % band; callout: minimum 13.6 % O2 |
| 15-20 s | "Earth tests say 15.4 % oxygen is safe. In orbit, 24 flames kept burning below that." | Dashed 15.4 % line; Consistency checks card marked CONFLICT |
| 20-25 s | "Trained on the ISS, it predicts drop-tower tests better than the Earth rule." | Validation table, model vs 1g rule |
| 25-30 s | "For Moon and Mars air, no flight data exists. IGNIS says so." | Habitat cards: INSUFFICIENT DATA; next-experiment stars on the envelope |

Shot list: 1 report PDF (2 s), 2 envelope 3D rotating (2 s), 3 click point to provenance (5 s), 4 2D boundary + band
(6 s), 5 consistency card (5 s), 6 validation table (5 s), 7 habitat cards + recommendations (5 s).

## Deck outline (7 slides + 1 optional)

1. **IGNIS: fire safety from NASA microgravity flight data.** Space Apps 2026, Flame in Freefall. Live URL, repo.
2. **Problem.** Flames in orbit get oxygen only from airflow. Weak ventilation keeps them alive where they die on
   Earth. Materials are still screened with 1g tests; Artemis-era cabins plan 8.2 psia / 34 % O2 with no flight fire data.
3. **Data.** BASS-II on the ISS plus its 5.18 s drop-tower tests, Saffire V summary. 89 observations, each with PDF page,
   figure, series, point index, image hash. Tables are verbatim-checked against PDF text; figures are machine-digitized
   (ticks + markers) into WebPlotDigitizer projects anyone can reopen. Gravity levels sourced per platform.
4. **Model.** Boundary with the physical shape (quench branch at low stretch, blowoff branch at high stretch). Extinctions
   are boundary measurements, stable flames constrain the burning side. Bayesian (Laplace) band. Minimum O2 13.6 %
   (13.4-13.9 %), matching the report's ~13.5 % independently.
5. **Validation.** Leave-one-campaign-out both ways (ISS and drop tower) and 5-fold CV, always against the 1g rule.
   Boundary error 2.0 % vs 2.7 % and 4.3 % vs 6.2 %; Brier 0.05 vs 0.44 and 0.03 vs 0.64; 94 % coverage of a 90 % interval.
6. **Consistency, experiments, habitats.** Contradiction detector: 1g limit CONFLICT (24 flames below it), Eq. 6.1 vs fit
   TENSION, two NASA docs disagree 10x on drop-tower g. Recommender: 5 tests by information gain inside the sourced
   BASS-II envelope (0-55 cm/s, 13.6-22.2 % O2). Habitats: ISS P(burns) ~100 % (flagged extrapolation); exploration and lander atmospheres INSUFFICIENT DATA.
7. **Raw NASA data.** PSI experimental tables (BASS, BASS-II, Saffire I-III) joined to the report's per-test notes: 66 flight
   tests by material, and Saffire-II's orbit-vs-1g comparison, where the 1g test is conservative for silicone but not for PMMA.
8. **Limits and next steps.** One material (PMMA), cabin pressure only, gravity as campaign nominal, at least 2 blowoff points
   hidden behind other markers not recovered. Next: more campaigns (Saffire VI, ACME), reduced-pressure tests, other materials.

## Project page text

IGNIS turns NASA's published microgravity fire experiments into one model you can check. It answers a practical
question for spacecraft fire safety: at a given oxygen level and airflow, does a solid material keep burning in
weightlessness, and how sure are we?

**Why it matters.** Without gravity, hot gas does not rise, so a flame lives on ventilation alone. Gentle airflow can keep
a flame burning at oxygen levels where it would go out on Earth. Spacecraft materials are still screened with normal-gravity
tests, and future exploration vehicles plan lower-pressure, oxygen-richer cabins where no flight fire data exists.

**How it works.** IGNIS pulls NASA reports from the NASA Technical Reports Server, checks every table value against the
PDF text, and machine-digitizes figures from hash-pinned renders, so each of its 89 observations links to a page, figure
and pixel. A physics-shaped Bayesian model learns the burn / no-burn boundary from ISS and drop-tower data and reports an
uncertainty band. It is validated leave-one-campaign-out against the 1g rule, which it beats in both directions. A
contradiction detector tests the papers' own claims against the data, a recommender proposes the most informative next
tests inside real hardware limits, and a habitat view says "insufficient data" where nobody has flown.

**Finding.** Thin PMMA rods burned in microgravity down to about 13.6 % O2, well below the 15.4 % normal-gravity upward
limit: a 1g screen is not conservative for weakly ventilated spaces.

**Tools.** Python (numpy, pint, jsonschema, PyMuPDF), JSON Schema data contract, WebPlotDigitizer 4 project format,
Plotly, Vercel, a local LLM analyst (Ollama) that may only answer through tool calls.

**Limits.** One material, cabin pressure only, campaign-nominal gravity, digitized (not raw) data.
