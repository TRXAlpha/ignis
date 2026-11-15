# Web data files (backend -> frontend)

`python -m model.export` writes these into `web/public/data/`. The frontend only reads them (static site, no server).
Every number shown in the UI must come from these files. Never hardcode data values in the frontend.

## bundle.json
Copy of `data/bundle.json` (contract v1.0.0): `sources[]`, `campaigns[]`, `materials[]`, `observations[]`.
Provenance panel for an observation: `locator` (source_id, page, figure/table, series, point_index, quote),
`extraction` (method, tool, confidence, flags, digitization), `qa.status`. Source URL: `sources[i].url`.

## model.json
```json
{
  "model_id": "ignis-boundary", "model_version": "0.1.0", "material_id": "pmma",
  "description": "string",
  "x": {"name": "stretch_rate", "label": "Stretch rate a", "unit": "1/s", "scale": "log"},
  "y": {"name": "o2_mole_fraction", "label": "O2 mole fraction", "unit": "1"},
  "grid": {"x": [..], "y": [..], "p_burns": [[..]], "p_sd": [[..]]},     // p_burns[j][i] at (x[i], y[j])
  "boundary": {"x": [..], "o2_p50": [..], "o2_p05": [..], "o2_p95": [..]}, // 50% contour + 90% band
  "points": [{"id": "obs_...", "x": 1.2, "y": 0.16, "state": "burns_sustained", "series": "ISS stable flame"}],
  "min_o2": {"p50": 0.135, "p05": 0.13, "p95": 0.14, "at_x": 10.0},
  "baselines": [{"id": "1g-upward-limit", "label": "string", "o2": 0.154, "ref": {Locator}}],
  "flow_conversion": {"note": "string", "u_m_s_per_x": 0.00212}          // flow for the base rod = x * this
}
```
`points` may be empty (no digitized data yet): the UI must show an explicit "no data yet" state, not fake points.

## validation.json
`{"folds": [ValidationFold...], "summary": "string", "limitations": ["string"]}` (contract ValidationFold).

## recommendations.json
`{"constraint_set": ConstraintSet, "items": [Recommendation...]}`; each item additionally has
`"x": number` (stretch rate) and `"p_burns": number` for plotting on the envelope.

## habitats.json
`{"presets": [{...HabitatPreset, "prediction": Prediction}]}` (contract). `prediction.status` can be
`insufficient_data` or `extrapolation`: show that state and `prediction.ood.reason` prominently, never a number.
