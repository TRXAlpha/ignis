# IGNIS: gravity-aware fire safety intelligence

NASA Space Apps 2026, "Flame in Freefall". Turns published microgravity combustion results into one cited, queryable model.

## Scope (decided 2026-11-14)

Data push is narrowed to **solid thin fuels**: opposed/concurrent **flame spread rate** and the **O2 x flow flammability boundary** (`flame_state`, `extinction_flow_velocity`, `limiting_oxygen_fraction`). Campaign cluster: BASS, BASS-II, Saffire IV-VI, plus drop-tower and 1g ground tests from the same papers. Reason: it is the only outcome where enough campaigns overlap to run leave-one-campaign-out validation. The contract still covers droplets, gas jets and smoke; they are just not being ingested.

## Setup (one path)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Linux/macOS: .venv/bin/python
.venv/Scripts/python -m pytest -q                   # first-run check
.venv/Scripts/python -m ignis_contract validate contract/examples/bundle.synthetic.json
```

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
