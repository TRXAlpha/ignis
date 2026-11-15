# IGNIS: submission deliverables

NASA Space Apps 2026, challenge "Flame in Freefall: SI-Powered Fire Safety Insights from Microgravity Combustion Data".
**Live:** https://ignis-ai.study · **Code:** https://github.com/TRXAlpha/ignis

All numbers below come from `web/public/data/*.json` (model `ignis-boundary` 0.1.0, export of 2026-11-15) or from a
quoted NASA PDF page. Re-check after any re-export.

## Key numbers

| Quantity | Value | Source |
|---|---|---|
| Observations in bundle | 158 (all accepted; 66 per-test rows carry an explicit extinction or burn statement) from 13 sources: NTRS reports + 5 NASA PSI experimental tables (CC0, DOIs) | bundle.json |
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
| Spread rate re-measured from NASA flight stills (100-um PMMA) | B1 2.71 +/- 0.10, B3 4.23 +/- 0.31 mm/s vs report 'about 2.2' -> TENSION (scale unresolved) | video_spread.json |
| ISS cabin (14.7 psia, 21 % O2) | P(burns) ~100 %, flagged extrapolation (above tested 13.5-18 % O2) | habitats.json |
| Exploration 8.2 psia / 34 %, lunar and Mars lander 10.2 psia / 26.5 % | INSUFFICIENT DATA (pressure / partial gravity outside any flight data) | habitats.json |

## Demo video

The full script (30 s main cut, 75 s extended cut, shot list, recording checklist and number sources) is in
[`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

## Deck outline (7 slides + 1 optional)

1. **IGNIS: an AI that learns where flames stop burning in orbit.** Flame in Freefall: SI-Powered Fire Safety Insights. Live URL, repo.
2. **Problem.** Flames in orbit get oxygen only from airflow. Weak ventilation keeps them alive where they die on
   Earth. Materials are still screened with 1g tests; Artemis-era cabins plan 8.2 psia / 34 % O2 with no flight fire data.
3. **The AI pipeline.** Eight stages: LLM agents read and extract (Read), a verbatim gate blocks hallucinated values
   (Verify), Bayesian machine learning learns the boundary (Learn), cross-platform validation (Test), computer vision on
   flight imagery (See), automated claim checking (Reason), active learning for experiments (Decide), and a tool-calling
   AI analyst with a numeric guard (Ask).
4. **What the AI learned.** From 158 traced observations (NASA reports + 5 PSI raw tables): PMMA keeps burning in orbit
   down to 13.6 % O2 (13.4-13.9 %), below the 15.4 % Earth limit, matching the report's ~13.5 % independently.
5. **Validation.** Leave-one-campaign-out both ways (ISS and drop tower) and 5-fold CV, always against the 1g rule.
   Boundary error 2.0 % vs 2.7 % and 4.3 % vs 6.2 %; Brier 0.05 vs 0.44 and 0.03 vs 0.64; 94 % coverage of a 90 % interval.
6. **AI reasoning, experiments, habitats.** Contradiction detector: 1g limit CONFLICT (24 flames below it), Eq. 6.1 vs fit
   TENSION, two NASA docs disagree 10x on drop-tower g. Recommender: 5 tests by information gain inside the sourced
   BASS-II envelope (0-55 cm/s, 13.6-22.2 % O2). Habitats: ISS P(burns) ~100 % (flagged extrapolation); exploration and lander atmospheres INSUFFICIENT DATA.
7. **AI on raw NASA data.** LLM agents joined PSI experimental tables (BASS, BASS-II, Saffire I-III) to the report's per-test notes: 66 flight
   tests by material, and Saffire-II's orbit-vs-1g comparison, where the 1g test is conservative for silicone but not for PMMA.
8. **Ask the AI, and its limits.** Live analyst runs: answers only through tools; invented numbers are refused.
   Limits: one material (PMMA), cabin pressure only, gravity as campaign nominal, at least 2 blowoff points
   hidden behind other markers not recovered. Next: more campaigns (Saffire VI, ACME), reduced-pressure tests, other materials.

## Project page text

IGNIS is an AI system that turns NASA's microgravity fire experiments into fire-safety insight you can check. It answers
a practical question for spacecraft: at a given oxygen level and airflow, does a material keep burning in weightlessness,
and how sure are we?

**Why it matters.** Without gravity, hot gas does not rise, so a flame lives on ventilation alone. Gentle airflow can keep
a flame burning at oxygen levels where it would go out on Earth. Spacecraft materials are still screened with normal-gravity
tests, and future exploration vehicles plan lower-pressure, oxygen-richer cabins where no flight fire data exists.

**How the AI works.** Language-model agents read NASA reports and raw PSI datasets and extract every test result; a
verification gate checks each value word for word against its source page, so nothing hallucinated survives. A
physics-shaped Bayesian machine-learning model learns the burn / go-out boundary with an uncertainty band and is validated
across platforms against the Earth rule. Computer vision re-measures flame spread from NASA's flight imagery, automated
reasoning tests the reports' own claims, active learning proposes the most informative next experiments, and a
tool-calling AI analyst answers questions without being able to invent numbers.

**Finding.** PMMA rods burned in microgravity down to about 13.6 % O2, well below the 15.4 % normal-gravity upward
limit: a 1g screen is not conservative for weakly ventilated spaces.

**Tools.** LLM agents (Claude, local models via Ollama), Python (numpy, pint, jsonschema, PyMuPDF, ffmpeg), JSON Schema data
contract, WebPlotDigitizer 4 project format, Plotly, Vercel.

**Limits.** One material, cabin pressure only, campaign-nominal gravity, digitized (not raw) data.
