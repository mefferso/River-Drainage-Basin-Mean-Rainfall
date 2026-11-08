# Historical relationships, schema v1

This directory contains the Phase 2 source exports and static JSON used by the Phase 3 dashboard. The source exports are authoritative review inputs; generated point files are the default Tier B browser data.

## Contents

- `source/Phase2_MAP_to_Crest_Plot_Ready.json`: 301 source MAP-to-crest records.
- `source/Phase2_Crest_to_Crest_Plot_Ready.json`: 365 source paired-crest records.
- `source/Phase2_Forecast_Point_Crosswalk.json`: 29 forecast-point identity decisions.
- `crosswalk.json`: 18 exact verified mappings from a configured USGS dashboard gage to canonical NWSLI.
- `manifest.json`: schema, source hashes, source/published counts, and supported points.
- `points/<NWSLI>.json`: per-forecast-point data loaded on demand.

Every plot record retains its source `record_id`, source date and precision, quality tier, values, and source provenance. `map_events` are indexed only where both the source dashboard gage ID and verified crosswalk identify the same configured map point. A paired relationship is indexed under each endpoint that has an exact configured map match, but its source and target fields never change orientation.

The current output contains 240 mapped MAP-to-crest records and all 365 paired-crest records across 12 relationships. Sixty-one MAP rows remain in their original source file but are not displayed: 54 GLFM6 rows have no dashboard marker and need geometry review, and 7 KLNM6 rows have no confirmed same-outlet dashboard gage. The current plot-supporting forecast points are listed in `manifest.json`.

To regenerate point files deterministically, run `python scripts/build_historical_site_data.py`. It validates expected source counts, unique IDs, Tier B/day precision, finite plotted values, source links, canonical station identities, and exact gage matches. New Phase 2 exports require review of the pinned count baseline and contract tests before publishing.

The observations are historical descriptive values. They are not calibrated forecasts and are not equivalent to the current MRMS Pass 1 or historical MRMS Pass 2 measurements. See `docs/historical_methodology.md` and `docs/historical_quality_control.md` for details.
