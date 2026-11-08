# Phase 4A — Network-wide LMRFC / NLDI basin geometry reconciliation

**Audit:** 2026-11-08  
**Status:** COMPLETE for source inventory and 2018 RFC-versus-current spatial comparison; **NOT COMPLETE for proving historical Excel MAP basin equivalence.** No historical measurements, operational geometries, MRMS algorithms, or eligibility decisions were changed.

## Scope and reproducible sources

- Historical point inventory: all **29** legacy NWSLI tokens / 29 canonical mappings from Phase 2 crosswalk.
- Current dashboard inventory: all **26** configured USGS gages; **18** have Phase 2-verified same-outlet NWSLI joins, **8** do not.
- NOAA NOHRSC 2018-07-25 LMRFC IHABBS shapefile: **543 polygon features**, source https://www.nohrsc.noaa.gov/data/vector/master/b_lmrfc.tar.gz, SHA-256 `ffd630cb973edfc70a5dabdeff383593bdcef8d17f697f2e824d6e3c636269bb`.
- NOAA shapefile fields include `NWSID`, `NAME`, `FCSTGROUP`, `AREA`, `DESCRIPT`, `OBJ_IDENTIF`. Exactly **26 of 29** historic canonical NWSLIs have an exact `NWSID` polygon.
- **Three absent exact NWSLI polygon matches:** `FBFL1`, `LBFL1`, `WPTM6` (legacy `WTPM6`). An absent match does not prove no appropriate basin exists under another identifier.
- Dashboard polygons: committed `data/basins.geojson` and `data/reaches.geojson`, no geometry edits.
- Output: `network_inventory.csv` (29 historical + 8 dashboard-only = 37 rows); `rfc_candidates.csv` (358 candidate comparisons, including spatial-only dashboard points); `rfc_exact_nwsli_polygons.geojson` (26 provenance-labeled candidate polygons); `summary.json`.

## Dedicated review map

After GitHub Pages deployment, review the standalone read-only map at
https://mefferso.github.io/River-Drainage-Basin-Mean-Rainfall/reports/phase4a/geometry_review.html

The map supports all 29 historical NWSLI point choices and all 26 USGS gage choices, overlays verified-ID RFC candidate polygons, full NLDI basins and incremental reach geometry, and labels dashboard-only RFC matches as spatial-only (never a verified same-outlet historical join). It is intentionally separate from the production rainfall dashboard.

## Geometry methods

All areas computed geodesically on WGS84 with `pyproj.Geod.geometry_area_perimeter`; dimensions in square miles. Intersection/union (IoU) is 100 × area(RFC ∩ NLDI)/area(RFC ∪ NLDI), calculated for both whole upstream and incremental geometry when an exact Phase 2 dashboard join exists. The chosen *leading polygon* is prioritized by exact NWSLI attribute and outlet containment, then spatial IoU; this is a **review candidate**, not an approved hydrologic area. The candidate file retains source NWSID and all attributes.

## Audited, matched historic forecast points (18)

| NWSLI | RFC 2018 polygon mi² | NLDI full mi² | NLDI incremental mi² | RFC/full IoU | RFC/incremental IoU |
|---|---:|---:|---:|---:|---:|
| AMIL1 | 202.3 | 476.1 | 233.1 | 41.1% | 80.8% |
| BXAL1 | 864.7 | 6543.0 | 6543.0 | 12.3% | 12.3% |
| CGSL1 | 71.8 | 71.4 | 71.4 | 90.4% | 90.4% |
| CREM6 | 95.5 | 94.0 | 94.0 | 93.8% | 93.8% |
| CUSL1 | 37.4 | 146.5 | 50.3 | 24.0% | 65.9% |
| CVEL1 | 42.8 | 129.3 | 57.9 | 28.8% | 61.8% |
| DENL1 | 66.8 | 1362.9 | 1362.9 | 4.3% | 4.3% |
| DIBM6 | 208.5 | 208.7 | 208.7 | 94.4% | 94.4% |
| FLSL1 | 98.3 | 96.2 | 96.2 | 85.3% | 85.3% |
| HOLL1 | 44.4 | 251.0 | 30.8 | 9.9% | 54.0% |
| KENL1 | 83.8 | 243.0 | 85.2 | 32.8% | 90.0% |
| LNDM6 | 125.8 | 309.6 | 309.6 | 39.4% | 39.4% |
| LPOL1 | 90.2 | 89.0 | 89.0 | 91.9% | 91.9% |
| MNLM6 | 177.2 | 174.9 | 174.9 | 93.8% | 93.8% |
| MONL1 | 134.6 | 220.2 | 131.3 | 56.4% | 91.8% |
| NRBL1 | 50.9 | 78.7 | 78.7 | 47.8% | 47.8% |
| OSYM6 | 156.1 | 157.8 | 157.8 | 93.2% | 93.2% |
| ROBL1 | 176.8 | 647.9 | 171.9 | 25.6% | 91.7% |

### Interpretation

- KENL1, ROBL1, MONL1 and AMIL1 show notably better agreement between the RFC single segment and the dashboard incremental reach than the dashboard full-upstream drainage. This supports testing a *local model-subbasin* interpretation; it is not proof of the original Excel MAP mask.
- DENL1, BXAL1 and LNDM6 have large single-RFC-segment versus full-NLDI mismatches. Downstream routing areas may aggregate additional upstream segments, but the original aggregation list has not been verified. **Do not treat the RFC single segment as total rainfall contributing to a forecast crest.**
- CREM6, MNLM6, DIBM6, OSYM6, LPOL1 and CGSL1 show high spatial agreement, but even high overlap cannot establish historical MAP product, geometry epoch, or rainfall event window.
- DENL1's dashboard `incremental` equals `full` because its configured upstream link list is empty. This is a **network-definition limitation**, not evidence that no upstream basins exist.
- Some exact-ID RFC polygons do not contain the phase-two outlet coordinates; these need coordinate and model-segmentation review rather than forced correction.

## Eleven historic points without a verified dashboard join

`CLMM6`, `FBFL1`, `GLFM6`, `KLNM6`, `LBFL1`, `LRCL1`, `MAGL1`, `MSVL1`, `TRCL1`, `TYTM6`, and raw `WTPM6`→canonical `WPTM6`.

Eight additional current USGS dashboard gages were audited spatially without inventing a historical forecast-point link: `02492600`, `02491500`, `02492000`, `02481000`, `02481130`, `02481667`, `02480181`, `02479310`. In particular **USGS 02481667 is not approved as KLNM6**, even though its current polygon intersects candidate RFC KLNM6.

## Hydrologic evidence and remaining proof gap

A paper authored by **W. Scott Lincoln, Katie E. Landry-Guyton, and David S. Schlotzhauer (NWS LMRFC)** describes legacy LMRFC gauge-only, **Thiessen polygon, six-hour subbasin MAP** and a distinct radar-derived MAPX archive introduced in 1997. It supports LMRFC *general calibration methods*, not the unit selection/aggregation in these 25 Excel workbooks.

Reference: https://rashms.com/wp-content/uploads/2021/08/2016_03_Comparison_Rainfall_Area_Reduction_Factors_Basin_Avg_Precipitation.pdf

NOHRSC IHABBS source and metadata: https://www.nohrsc.noaa.gov/gisdatasets/ and https://www.nohrsc.noaa.gov/technology/gis/ihabbs_overview.html

**Not verified:** 2018 IHABBS polygon version during legacy study dates (1950 onward); original RFC study `MAP` basin ID or multiple-segment aggregation; exact 6-hour event windows; historical stage datum/crest pairing; whether the spreadsheet's MAP is Thiessen gauge-only, MAPX, or an event-specific adjusted combination. Zero RFC masks scientifically approved for reconstructed historical MAP.

## Read-only safeguards and reproduction

Run `python scripts/audit_rfc_network_geometry.py` after placing the official `b_lmrfc.tar.gz` in the repository root. `.github/workflows/phase4a-rfc-probe.yml` fetches the source in GitHub Actions and runs `python -m unittest -v tests/test_rfc_geometry_audit.py` before publishing versioned reports.

No automatic station joins from names/proximity; no MNLM6/CREM6 merge; no WPTM6/WTPM6 provenance rewrite; no KLNM6→USGS 02481667 match; no retrofit of old measurements or MAP values. Phase 4 event reconstruction remains out of scope.

## Scientific acceptance gates before MAP backfill

1. Retrieve original LMRFC operational basin mapping/configuration or study workbook charts/reference sheets that specify **which basin segment(s)** generated each `MAP` series.
2. Establish **geometry version** and whether upstream or incremental, or an area-weighted union of multiple model segments, was used per historical point.
3. Confirm the original rainfall product and six-hour timing / event-date semantics using source study metadata and, where available, historical LMRFC MAP/MAPX input files.
4. On the same QPE, same time window and same valid-cell treatment, calculate both the modern NLDI and NOAA RFC-basin spatial means to isolate geometry effects.
5. Only then consider new event records, scientifically labeled as separately reconstructed MRMS—not direct legacy replacements.

**Decision:** Network geometry audit and reproducible candidate identification are done. Historical study-specific MAP basin certification remains blocked by unavailable original RFC study configuration; do not substitute a plausible polygon for verified methodology.
