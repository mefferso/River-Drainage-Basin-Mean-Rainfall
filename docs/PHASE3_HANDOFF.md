# Phase 3 handoff: historical relationship plots

**Project:** River Basin Mean Rainfall
**Repository:** `mefferso/River-Drainage-Basin-Mean-Rainfall`
**Feature branch:** `phase3/historical-relationships`
**Starting `main` commit inspected:** `bf2648dcd1cd82899045477453da730692361d4e`
**Phase 2 package audit date:** 2026-11-06
**Release state:** Feature implementation committed and pushed; PR #5 is open for the `main` branch. The release result is reflected in the PR and GitHub Pages workflow history.

## 1. What Phase 3 adds

The dashboard retains its existing Leaflet map and rainfall sidebar. A full-width historical analysis panel follows the map in the right-side workspace and moves directly after the map on mobile. Clicking a polygon, marker, or gage dropdown continues to set a USGS ID; the new panel resolves only exact verified crosswalk entries and fetches the matching forecast-point payload lazily. The panel has MAP-to-crest and directional pair selectors, interactive SVG points, hover/focus detail, a sortable event table, row/point selection synchronization, and CSV export.

The chart technology is browser-native SVG; no chart package or backend is required. MRMS data and historical study values remain independent. Period, wet threshold, and area mode changes redraw MRMS only. Switching the MRMS source preserves the selected USGS point when it exists in the selected dataset, then refreshes the historical panel for that same point.

## 2. Data files and actual published counts

Versioned files live in `historical/relationships/v1/`:

- `source/Phase2_MAP_to_Crest_Plot_Ready.json`: source export, 301 records.
- `source/Phase2_Crest_to_Crest_Plot_Ready.json`: source export, 365 records.
- `source/Phase2_Forecast_Point_Crosswalk.json`: source crosswalk, 29 records.
- `crosswalk.json`: 18 exact USGS-to-NWSLI mappings for gages already in `config/gages.json`.
- `manifest.json`: source hashes, source and published counts, schema, and supported points.
- `points/<NWSLI>.json`: 18 lazy per-gage payloads (including empty payloads for mapped points without plot data).

The browser can display **240** MAP-to-crest rows and all **365** crest-to-crest rows in **12** directional relationship groups. All source exports remain available in the versioned source folder, but 61 MAP rows are excluded from default plotting because they have no verified current map gage: 54 GLFM6 rows (no current map marker; geometry review required) and 7 KLNM6 rows (not the existing USGS 02481667 outlet). No new markers are added.

The 15 current map gages with plotted relationships are:

`AMIL1`, `BXAL1`, `CREM6`, `CUSL1`, `DENL1`, `DIBM6`, `FLSL1`, `HOLL1`, `KENL1`, `LNDM6`, `LPOL1`, `MNLM6`, `MONL1`, `OSYM6`, and `ROBL1`.

The exact mapped points CGSL1, CVEL1, and NRBL1 have no eligible row in these exports and receive an informative no-data state. Map gages without an exact approved crosswalk show “No verified historical station match.”

## 3. Phase 2 input fingerprints

| Input | SHA-256 |
|---|---|
| `Phase2_MAP_to_Crest_Plot_Ready.json` | `830cc965e9a3afd7bcd62c328b68a082df60038e84e8af6a511315c9438c67fc` |
| `Phase2_Crest_to_Crest_Plot_Ready.json` | `88cf92527eef23f4ed8d03eb30d126f7b060c1c0e4c5907ffa3e6a4295328a55` |
| `Phase2_Forecast_Point_Crosswalk.json` | `30df8ca7c33046dc771665c73056898fb833587492ca56c843e1325c90ee6b4f` |

The build script pins the source-count baseline at 301 MAP, 365 pairs, and 29 crosswalk records. If reviewed input exports change, update both the expected counts and contract tests in the same reviewed change.

## 4. Pilot validation results

- **AMIL1** (USGS `07375430`): 23 MAP-to-crest observations.
- **CREM6** (USGS `02492343`): 34 MAP-to-crest observations; separate from MNLM6.
- **OSYM6 → KENL1**: 34 paired crests; fixed source/X and target/Y axes are identical when either mapped endpoint is selected.

The contract tests also check CLMM6→BXAL1 and FLSL1→CUSL1 axis interpretations where source worksheet column order differs from the reviewed directional interpretation.

## 5. Technical entry points

- `scripts/build_historical_site_data.py`: deterministic source validator and static payload compiler.
- `historical-ui.js`: verified crosswalk lookup, lazy point fetch/cache, stale-response guard, relationship selection, SVG scatter rendering, accessible sortable table, and CSV export.
- `index.html`: map workspace layout, selection synchronization, dataset selection preservation, and persistent science disclosure.
- `tests/test_historical_contract.py`: source schema/count/provenance, finite value, crosswalk, alias, pilot, and axis checks.
- `tests/test_historical_ui.cjs`: browser-module syntax, exact selection, empty/missing-match states, relationship switching, table sorting, point/table synchronization, export format, and stale-response protection.
- `docs/historical_methodology.md` and `docs/historical_quality_control.md`: implementation and science constraints.

Build generated JSON from the checked-in inputs:

```sh
python scripts/build_historical_site_data.py
python -m unittest discover -s tests -v
node tests/test_historical_ui.cjs
node tests/validate-ui.cjs
```

No new runtime dependency is required. GitHub CI uses Python 3.11 and Node for the existing and new checks.

## 6. Scientific constraints for the next stage

- Historical RFC MAP is not modern MRMS Pass 1, MRMS Pass 2, whole-basin mean, or wet-area mean.
- Tier B is conditional descriptive eligibility, not verification or operational approval. Phase 2 reports zero Tier A.
- A recorded source date label is not proven to be rainfall start/end or crest date.
- Stage values are feet at historical gauge datums that have not been reconciled across sites or time.
- Unknown TC/lag values remain raw source values; no hour/day conversion, interpolation, or period-count multiplier is applied.
- A same-row crest pair does not prove that independently timed peaks were paired or that a routing/travel-time relation exists.
- Do not use station names or proximity as joins. Do not merge MNLM6 with CREM6, alter WTPM6 source spelling, or attach KLNM6 to 02481667.
- Do not add stations or edit MRMS calculations, hourly updater behavior, historical Pass 2 processing, or geometries in this phase.

## 7. Unresolved science and data

The original 25 workbooks were not included in the Phase 2 attachment set, so the original binaries have not been independently re-parsed. The LMRFC legacy MAP method, event selection/window, MAPX meaning, source basin polygons, exact crest date convention, station datum chronology, TC clock, and rainfall period bins remain unresolved. GLFM6 is tidal/backwater-sensitive. Pair records have no independently verified source and target crest timestamps. Future MRMS reconstruction should remain a separate product and must not be added until a reviewed overlap study supports a defined method.

## 8. Existing dashboard and workflow preservation

The existing map/statistics selectors, basin and reach geometry, MRMS 6/12/24-hour products, wet thresholds, marker/polygon interaction, and Pass 2 event data remain intact. The `scripts/update.py` hourly update and `scripts/historical.py` Pass 2 event workflows remain unchanged in processing behavior. The Pages workflow must include the new frontend and `historical/**` in its deployment path filters so future data-only releases publish.

## 9. Release record

- Initial feature implementation commit: `b9516ccf9f030da2d4ae026f91bea1d32635e3ff`.
- Pull request: [#5](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/pull/5), targeting `main` from `phase3/historical-relationships`.
- The initial feature commit's GitHub Actions validation run `42485521960` completed successfully; the latest PR head and checks are available on PR #5.
- Merge SHA and Pages deployment are recorded by the PR and repository Actions. Published dashboard URL: https://mefferso.github.io/River-Drainage-Basin-Mean-Rainfall/.
- Playwright smoke checks passed on desktop and mobile using a Leaflet API stub. The managed browser tunnel could not reach the existing Leaflet CDN, so that smoke check did not validate actual Leaflet tile rendering. The existing MRMS map/statistics tests passed.
- Recommended next step: independently obtain and audit original source workbook binaries and the original LMRFC MAP/crest methodology before any calibration work.
