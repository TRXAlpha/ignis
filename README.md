# IGNIS: gravity-aware fire safety intelligence

NASA Space Apps 2026, "Flame in Freefall". Turns published microgravity combustion results into one cited, queryable model.

**Live:** https://ignis-flame-one.vercel.app · **Code:** https://github.com/TRXAlpha/ignis

| Piece | Where |
|---|---|
| Data contract + validator | `contract/`, `ignis_contract/` |
| Ingestion (NTRS client, verbatim-checked tables, WPD plot digitization) | `ingest/`, `digitized/`, `registry/` |
| Boundary model, validation, recommender, habitat risk | `model/` (`python -m model.export`) |
| Analyst (local LLM, tool calls only, numeric guard) | `analyst/` |
| Frontend (static, reads `web/public/data/*.json`) | `web/` |

## In plain terms

- **What:** IGNIS turns the results of NASA's fire experiments on the International Space Station into a map that answers
  "will this material keep burning at this much oxygen and airflow, in weightlessness?", with how sure we are, and a link
  from every data point back to the page of the NASA report it came from.
- **Why:** flames behave differently without gravity. Hot air does not rise, so a flame only gets oxygen from fans and air
  currents. Gentle airflow keeps flames alive at oxygen levels where they would go out on Earth. Spacecraft materials are
  still screened with Earth tests, and planned Moon/Mars vehicles use air (lower pressure, more oxygen) where nobody has
  flown fire tests yet.
- **How:** read numbers from report tables and points from report graphs, check every value against the PDF, fit the
  known shape of the burn / goes-out boundary to the flight data with an uncertainty band, score it against the Earth rule
  of thumb, suggest the most informative next experiments, and say "not enough data" for habitats outside what was tested.
- **Result so far:** from 49 ISS points the lowest oxygen level at which acrylic (PMMA) keeps burning is 13.7 % (90 % band
  13.5-14.0 %), well below the 15.4 % the Earth test implies. The report itself says ~13.5 %.

## Scope (decided 2026-11-14)

Data push is narrowed to **solid thin fuels**: opposed/concurrent **flame spread rate** and the **O2 x flow flammability boundary** (`flame_state`, `extinction_flow_velocity`, `limiting_oxygen_fraction`). Campaign cluster: BASS, BASS-II, Saffire IV-VI, plus drop-tower and 1g ground tests from the same papers. Reason: it is the only outcome where enough campaigns overlap to run leave-one-campaign-out validation. The contract still covers droplets, gas jets and smoke; they are just not being ingested.

## Setup (one path)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m pytest -q                   # first-run check
.venv/Scripts/python -m ignis_contract validate contract/examples/bundle.synthetic.json
.venv/Scripts/python -m ingest.fetch_sources                       # every NTRS PDF in registry/, sha256-checked
.venv/Scripts/python -m ingest.build_bundle                        # data/bundle.json (production-validated)
.venv/Scripts/python -m model.export                               # web/public/data/*.json
.venv/Scripts/python -m http.server 8000 --directory web/public    # open http://localhost:8000
```

Analyst (needs a local Ollama model with tool calling, default `gemmaclaude:latest`; set `IGNIS_LLM_MODEL` for another):

```bash
.venv/Scripts/python -m analyst "What is the minimum O2 for PMMA to burn in microgravity?"
.venv/Scripts/python -m analyst --tool habitats                    # no LLM, raw tool output
```

Any number in the analyst's answer that is not in a tool result gets the answer refused (`analyst/__main__.py: unsupported_numbers`).

## Digitizing plots

**Automatic (used for BASS-II Fig 6.10):** `python -m ingest.autodigitize bass2_fig6_10` finds the labelled axis ticks and
the markers by colour/shape, writes a WPD 4 project (`digitized/<name>.wpd.json`) plus an overlay PNG for review, and the
same converter guards apply. Known miss: X markers drawn almost entirely behind a diamond (at least 2 in Fig 6.10) are
not recoverable and are left out rather than guessed.

**By hand (WebPlotDigitizer 4)**, to correct or for figures the detector can't handle:

Most in-scope data is only in figures. A human clicks points; code does the rest and refuses anything it can't verify.

1. Open https://apps.automeris.io/wpd4/ and load the pinned render, e.g. `data/figures/bass2_fig6_10.png`
   (made by `python -m ingest.figures render <source_id> <pdf_page> --name <name> --clip x0,y0,x1,y1`).
2. 2D (X-Y) plot. Calibrate X1, X2 on the x-axis and Y1, Y2 on the y-axis at labelled ticks; tick "log scale"
   if the axis is log. Leave "assume axes are perfectly aligned" unticked. For a split axis (Saffire V Fig 10),
   add one axes per side, named as in the spec (`concurrent`, `opposed`).
3. One dataset per legend entry, named exactly as the series keys in `digitized/<name>.spec.json`.
   Click marker centres. Series marked `skip` in the spec can be left out.
4. File > Save Project > save as `digitized/<name>.tar` (keeps the image, so the hash is checked).
5. `python -m ingest.build_bundle` converts and validates. It fails on: wrong image, values that don't match
   WPD's own calibration, unmapped datasets, caption not on the cited page. Tilted calibration (> 3 px)
   flags the points and keeps them out of the model.

## Data contract v1.0.0 (LOCKED)

| File | What |
|---|---|
| `contract/ignis.schema.json` | JSON Schema 2020-12. Top level = `Bundle`. Also `$defs` for `Prediction`, `Recommendation`, `ValidationFold`, `ConstraintSet`, `HabitatPreset`. |
| `contract/quantities.json` | Canonical SI unit + hard/plausible range for every numeric field. |
| `contract/examples/bundle.synthetic.json` | Valid example. **Synthetic, not NASA data**; fails `--production`. |
| `ignis_contract/` | Normalizer (`make_quantity`), validator (`check_bundle`), model view (`flatten_bundle`, `FLAT_COLUMNS`). |

**Pipeline:** ingestion writes `data/bundle.json` → `python -m ignis_contract validate --production` → model reads `flatten_bundle()` rows → model writes `Prediction`/`ValidationFold`/`Recommendation` JSON → frontend reads all of it.

**Rules the validator enforces:**
- One `Observation` = one outcome, one condition set, one locator (page / figure+point / table+row / dataset path).
- Every number keeps `value`+`unit` verbatim plus `si_value`; the validator recomputes SI with pint and rejects mismatches.
- `basis` is `reported` | `reported_elsewhere` | `campaign_nominal` | `derived`. Anything other than `reported` needs a `basis_ref` (locator or formula). There is no "assumed".
- Absent = not reported. Only `gravity` is required. Never fill a field with a guess.
- `plot_digitized` rows carry axis calibration + pixel + image hash. `table` needs a row, `text` needs a verbatim quote.
- Confidence < 0.7 or any blocking flag → cannot be `accepted`. Outside plausible range → must be flagged. Physically impossible → error.
- IDs are `sha256(locator, quantity, material)`, so re-extraction upserts instead of duplicating.
- `test:` / `synthetic_test` sources fail `--production`.
- `Prediction.status = insufficient_data` → `mean_si` must be null. The UI shows the empty state, never a number.

**Changing the contract:** additive optional fields = minor bump (1.1.0) and tell all streams. Renames, removals, or new required fields = major bump, all three streams agree first. Bump `SchemaVersion` and `SCHEMA_VERSION` together.

**Frontend types:** `npx json-schema-to-typescript contract/ignis.schema.json > web/src/contract.d.ts`.
