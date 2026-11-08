# Historical rainfall and crest plot methodology

## Purpose and limits

The Phase 3 analysis panel presents source-reported historical relationships descriptively. MAP-to-crest plots place a legacy study MAP value in inches on X and recorded river crest in feet on Y. Crest-to-crest plots keep the reviewed Phase 2 source endpoint on X and target endpoint on Y. They display observations and source provenance only; they do not estimate a forecast, fit a curve, or infer travel time.

## Source and inclusion

The authoritative inputs are the three Phase 2 JSON exports in `historical/relationships/v1/source/`. They contain 301 Tier B MAP records, 365 Tier B crest pairs, and 29 forecast-point crosswalk decisions. The compiler validates each record and generates a static manifest, exact USGS-to-NWSLI crosswalk, and lazy point payloads. The source records themselves are copied without numeric, date, or identifier edits. `record_id`, source filename hash, workbook, worksheet, and source row remain available.

Only Tier B rows with full day-precision source date labels and finite numeric plot coordinates are compiled. Missing values remain null/unavailable. Month-only cases, competing source versions, ambiguous duplicates, and incomplete pair values are not added to default plots. Source date labels are not claimed as event start, rainfall end, or crest day. Dates are displayed at the precision recorded by the source.

## Station matching

The map's selected state remains a USGS gage ID. A dashboard match exists only when Phase 2 `usgs_site_id_confirmed` equals `existing_dashboard_usgs_id` and that ID is present in `config/gages.json`. No station-name or nearest-coordinate joins are used. Pair observations are indexed at each verified mapped endpoint without reversing source/target axes.

- `MNLM6` and `CREM6` are separate West and East Hobolochitto sites.
- Historical pair spelling `WTPM6` remains in the raw record; `WPTM6` is the canonical station ID for lookup and display.
- `KLNM6` is not matched to dashboard USGS `02481667` at I-10.
- Candidate NWS points without a configured, reviewed same-outlet map gage do not receive markers or historical data on an unrelated marker.

## Scientific interpretation

Legacy RFC MAP is not the dashboard's modern NOAA MRMS whole-area average, wet-area average, or the separate 2026 MRMS Pass 2 event total. The original legacy basin mask, gridding/weighting method, event-window rule, MAP/MAPX semantics, and six-hour rainfall period conventions are not established by the attached files. Historical river-stage datums and datum changes are unverified. A paired row does not provide independently timed crests. TC and lag are shown only as source values and labels; no unit conversion or `periods × 6` calculation is applied.

Every view labels these records Tier B historical descriptive. No Tier A record is available. None of the plots is an operational stage forecast or a calibrated relationship. Users must assess stage datum differences, backwater/tidal effects, and source pairing before making hydrologic inferences.

## Rebuilding and extension

After a reviewed Phase 2 export change, update the source files, expected counts in `scripts/build_historical_site_data.py`, and `tests/test_historical_contract.py` in the same change. Run the compiler and full test suite. A new map station requires a validated outlet identity, a matching crosswalk row, and reviewed geometry; adding a verified USGS alias alone does not authorize creating a dashboard marker.
