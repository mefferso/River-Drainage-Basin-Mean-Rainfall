# Phase 3 historical data quality control

## Phase 2 source baseline

| Input | Records | Disposition |
|---|---:|---|
| MAP-to-crest plot-ready JSON | 301 | Tier B descriptive candidates |
| Crest-to-crest plot-ready JSON | 365 | Tier B descriptive pairs |
| Forecast-point crosswalk JSON | 29 | Reviewed station identities and restrictions |
| Current configured dashboard gages | 26 | Existing map locations only |
| Exact verified dashboard crosswalk subset | 18 | IDs must match the current map configuration |

Phase 2 reports zero Tier A, 666 Tier B, 632 Tier C, and one Tier D among the full source master. The 301/365 plot-ready exports contain Tier B only. The original 25 source workbook binaries were not included in Phase 2; internal snapshot reconciliation is not independent re-import verification.

| Tier | Phase 2 meaning | Phase 3 default plot |
|---|---|---|
| A | Original binary/cell extraction and critical station, datum, unit, event, and pairing definitions verified sufficiently for explicit study use. | None available. |
| B | Credible finite relationship values, canonical NOAA point, day-level source date, and no known competing version or conflicting same-sheet record; still conditional and descriptive. | Included when the forecast point has an exact approved map crosswalk. |
| C | Provisional/review records such as month-only multi-station cases, competing versions, duplicate conflicts, or incomplete/ambiguous fields. | Excluded. |
| D | Required paired numeric value is missing and no defensible substitute exists. | Excluded. |

## Compiler checks

`scripts/build_historical_site_data.py` fails closed if input counts differ from the reviewed baseline, record IDs repeat, required provenance is missing, a source date is not a valid day-level ISO date, any row is not Tier B, plot coordinates are missing/non-finite, source endpoint IDs are absent, crosswalk historical IDs repeat, or a verified USGS ID is ambiguous. It retains source JSON records exactly in generated payloads and writes source SHA-256 values to `manifest.json`.

The generator maps 240 MAP rows to current verified map points. It leaves 61 source MAP rows out of default plots: 54 GLFM6 rows because there is no existing dashboard marker and station geometry needs review; and 7 KLNM6 rows because no same-outlet match to the map's 02481667 has been established. All 365 eligible paired-crest rows appear in at least one payload, across 12 relationships, and maintain their fixed source-to-target order.

The 15 points with at least one plotted relationship are AMIL1, BXAL1, CREM6, CUSL1, DENL1, DIBM6, FLSL1, HOLL1, KENL1, LNDM6, LPOL1, MNLM6, MONL1, OSYM6, and ROBL1. The three additional exact current map crosswalks without eligible exported plot records are CGSL1, CVEL1, and NRBL1. Other configured gages show the no-verified-match state.

## Pilot checks

- AMIL1, USGS 07375430: 23 MAP-to-crest observations.
- CREM6, USGS 02492343: 34 MAP-to-crest observations; no MNLM6 records are attached.
- OSYM6 to KENL1: 34 crest pairs. Selecting either endpoint retains OSYM6 as X/source and KENL1 as Y/target.

Contract tests also check the reviewed axis reversals for CLMM6→BXAL1 and FLSL1→CUSL1, raw WTPM6 provenance under canonical WPTM6, and denial of an unrelated KLNM6 join.

## Remaining scientific uncertainty

- No independent parse of the 25 original Excel workbooks was possible from the provided package.
- No original LMRFC MAP method, event-window definition, original basin geometry, or MAPX definition has been verified.
- Source event date semantics, historical gage datums, and datum changes are unresolved.
- TC clock start/end and several lag-unit interpretations remain unverified; source values are not normalized.
- Crest-pair rows lack independently verified timestamps; their pairing does not establish routing or travel time.
- GLFM6 is tidal/backwater-sensitive; existing map geometries are not validated as legacy RFC subbasins.

Any quality-tier change needs a reviewed decision and repeatable source evidence. Do not infer a new mapping, deduplicate on date alone, substitute MAPX for MAP, or add a fitted forecast curve.
