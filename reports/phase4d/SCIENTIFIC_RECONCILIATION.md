# Phase 4D scientific reconciliation

**Status as of 2026-11-08:** source observations and historical daily QPE have been retrieved in GitHub Actions; event matches and historical RFC MAP masks remain unapproved. The Phase 4D source workflow completed successfully twice, including native-grid geometry comparisons and full instantaneous anomaly-window retrievals. The second run reports shared and nonshared basin rainfall diagnostics.

## Evidence, units, and limits

The distinctions below are deliberate: the spreadsheet date is a search lead; the USGS value is an observed sample; a window maximum is not automatically a flood crest; and an exact RFC attribute is not proof of a historical rainfall mask.

| Evidence | Result | Provenance and qualification |
|---|---|---|
| NOAA LMRFC archive | 543 features; 26 exact NWSLI attribute features | [NOHRSC archive](https://www.nohrsc.noaa.gov/data/vector/master/b_lmrfc.tar.gz), SHA-256 `ffd630cb973edfc70a5dabdeff383593bdcef8d17f697f2e824d6e3c636269bb`; Phase 4D retrieval 2026-11-08 19:55:27 UTC. The source shapefile CRS is EPSG:4326; exported comparison geometries remain EPSG:4326. |
| Exact attribute matching | AMIL1 `NWSID=AMIL1`, feature 359, `TANGIPAHOA/AMITE`; MNLM6 `NWSID=MNLM6`, feature 370, `W.HOBOLO- @ MCNEIL` | Fields include `NWSID`, `DESCRIPT`, `FCSTGROUP`, and `AREA`. These matches are unverified candidates; Phase 4A approved zero legacy MAP masks. |
| USGS/NWPS historical stage availability | Actual USGS time-series metadata, 9 date neighborhoods per station (each queried in continuous and daily 00065), USGS peak records and NOAA NWPS crest records retrieved | [Latest Phase 4D Actions run](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42520685369), [full raw source artifact 13633585578](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42520685369/artifacts/13633585578). Retrieval time 2026-11-08 20:33:34 UTC. Compact [`stage_source_coverage.json`](stage_source_coverage.json) and [`stage_source_coverage.csv`](stage_source_coverage.csv) were generated from that raw response by `reconstruction/summarize_historical_source_coverage.py`; see [historical-source retrieval code](../../reconstruction/historical_source_availability.py). These are availability checks, not verified events. |
| NOAA Stage IV QPE | Actual APCP CONUS GRIB, 24-hour native accumulation, 12Z-to-12Z periods | [Five-day Dec 2018 run](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42514324970), artifact 13630611671. Product units are kg/m² (liquid-water equivalent); basin MAP uses native-grid intersections weighted by WGS84 geodesic area. This is daily 24-hour data, not hourly or six-hour MAP. |

## Geometry comparison

The source geometry was independently compared against both the current NLDI full-upstream basin and its incremental reach. Areas and overlap use WGS84 ellipsoidal geodesic area. Centroid and Hausdorff distances use EPSG:5070. Areas below are square miles. The geometry inventory is in [`geometry_inventory.json`](geometry_inventory.json).

| Pilot | RFC candidate area | NLDI full area | Full intersection | Full IoU | NLDI incremental area | Incremental intersection | Incremental IoU | RFC contains gauge? |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| AMIL1 | 202.288590 | 476.084057 | 197.660659 | 41.1183% | 233.136099 | 194.583192 | 80.7931% | No |
| MNLM6 | 177.242818 | 174.929187 | 170.465658 | 93.8138% | 174.929187 | 170.465658 | 93.8138% | Yes |

For AMIL1, the RFC candidate has 4.627931 sq mi RFC-only and 278.423398 sq mi NLDI-only against the full upstream basin; against the incremental reach it has 7.705398 sq mi RFC-only and 38.552906 sq mi NLDI-only. The candidate is much closer to the incremental reach by IoU, but it does not contain the gauge point and cannot be identified as the legacy MAP mask from its name alone. Centroid offsets are 13.5973 km (full) and 1.5602 km (incremental); boundary Hausdorff offsets are 28.2113 km and 8.6172 km.

For MNLM6, the RFC candidate and NLDI full basin overlap by 170.465658 sq mi, with 6.777160 sq mi RFC-only and 4.463529 sq mi NLDI-only. The candidate contains the gauge point; centroid offset is 0.3960 km and boundary Hausdorff offset is 1.4953 km. These close matches still do not establish the historical MAP method or polygon version.

## December 2018 precipitation and stage

The saved legacy rows label **2018-12-28** and contain AMIL1 4.70 inches / crest 19.00 feet and MNLM6 4.60 inches / crest 19.70 feet. Spreadsheet fields are not time-resolved: AMIL1 `TC` is null and `Periods` is 23 (unit/convention unverified); MNLM6 `TC` is 30 (unit unverified) and `Periods` is 3 (the six-hour-count interpretation is unverified). Neither row establishes an onset, end, or that the date is the crest date. Source rows are AMIL1_MAP_crest.xls row 25 and MNLM6_MAP_crest.xls row 37.

Actual Stage IV daily MAP over the *illustrative fixed* 2018-12-26 12Z to 2018-12-28 12Z interval is AMIL1 4.38437 inches and MNLM6 4.67518 inches. Relative to the spreadsheet values this is -0.31563 and +0.07518 inches, respectively. It does not establish the legacy accumulation window or product equivalence.

The five actual daily products ending 12Z were:

| End UTC | AMIL1 MAP (in) | MNLM6 MAP (in) |
|---|---:|---:|
| 2018-12-26 12Z | 0.00266 | 0.00000 |
| 2018-12-27 12Z | 0.15713 | 0.23481 |
| 2018-12-28 12Z | 4.22724 | 4.44037 |
| 2018-12-29 12Z | 0.00000 | 0.00000 |
| 2018-12-30 12Z | 0.22144 | 0.32116 |

Stage-window maxima from actual USGS samples were AMIL1 18.98 ft at 2018-12-28 17:15Z and MNLM6 19.72 ft at 2018-12-29 18:45Z. The latter occurs on the day after the legacy date label; both are still review-window maxima, not independently adjudicated crests. The 2018-12-29 12Z daily QPE product was zero in both current NLDI basins. The 2018-12-30 12Z product includes later rain and is not appended to this event. Daily intervals cannot resolve within-day onset or cessation.

The Phase 4D GitHub Actions run retrieved the official daily GRIBs and calculated both geometry MAPs using identical QPE grids and intervals, without resampling:

| Pilot | Existing NLDI full basin | Exact-attribute RFC candidate | Candidate minus NLDI | Difference relative to NLDI |
|---|---:|---:|---:|---:|
| AMIL1 | 4.38437744 in | 4.96101221 in | +0.57663477 in | +13.1520% |
| MNLM6 | 4.67518080 in | 4.66863778 in | -0.00654301 in | -0.1400% |

Run [42517415066](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42517415066), artifact `phase4d-scientific-reconciliation` (13631453084), contains the native grid signature, exact valid intervals, per-day MAPs, GRIB checks, geometry source provenance, and retrieved anomaly hydrographs. The component results were repeated in [run 42517779447](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42517779447), artifact 13631314104. The two-day window is exactly 2018-12-26 12Z through 2018-12-28 12Z for both pilots. The comparison shows that candidate-mask geometry alone can materially change AMIL1 MAP; for MNLM6 the two masks yield nearly equal values in this particular window. It does not show that either candidate equals the historical operational MAP mask.

The second Phase 4D run also calculated the same Stage IV accumulations over the common and nonshared polygon regions. These component values are rainfall depth summed over the two daily products for each region; they are not volume contributions:

| Pilot | Shared region | RFC candidate-only region | NLDI-only region |
|---|---:|---:|---:|
| AMIL1 | 4.95763671 in | 5.10519340 in | 3.97740550 in |
| MNLM6 | 4.66888763 in | 4.66234755 in | 4.91552074 in |

The AMIL1 difference is consistent with the small RFC-only area having higher mean rain than the large NLDI-only region during this storm window. MNLM6's nonshared region depths are also close. These values describe spatial distribution on the mask differences but cannot prove either boundary's historical use. The local execution environment cannot access NOAA through its network proxy. Do not interpret a candidate geometry comparison as historical-method reconciliation.

## AMIL1 stage discrepancies

| Date lead | Spreadsheet crest | Actual USGS window maximum | Sample UTC | Difference |
|---|---:|---:|---|---:|
| 2016-08-13 | 26.20 ft | 29.28 ft | 2016-08-13 04:45Z | +3.08 ft |
| 2017-04-04 | 17.80 ft | 11.64 ft | 2017-04-04 05:30Z | -6.16 ft |

These are measured values reported by the Phase 4B source audit and independently reproduced in Phase 4D retrievals. The broader USGS 00065 anomaly-window query returned 861 samples in each 9-day interval: 2016-08-10 00:00Z through 2016-08-18 23:00Z and 2017-04-01 00:00Z through 2017-04-09 23:00Z, with a maximum sample interval of 15 minutes. The NWIS instantaneous-value source assigned raw qualifier `A` to the 29.28 ft sample at 2016-08-13 04:45Z and 11.64 ft sample at 2017-04-04 05:30Z. The USGS OGC continuous API records at the same times and values returned in the final source artifact have no qualifier value. Both source records are preserved separately; neither code adjudicates datum consistency, legacy source meaning, or flood-event identity. No datum offset or source error has been inferred. Full source hydrographs, timestamps, qualifiers, metadata, retrieval time and source URLs are in artifacts 13631453084 (run 42517415066) and 13632502088 (run 42519457827). The code lists local sample maxima at least six hours apart for review; those points remain provisional and the short separation may retain multiple fluctuations. A full hydrograph, dated datum history, source worksheet interpretation, and event association must be reviewed before identifying the cause.

The compact inventory in [`stage_event_leads.csv`](stage_event_leads.csv) and [`stage_event_leads.json`](stage_event_leads.json) reports 11 actual sample-window maxima. It deliberately records **0 confirmed flood crests**. Central-time strings are conversions of source UTC timestamps through `America/Chicago`; DST is therefore handled per date. Qualifier adjudication is not represented by the compact summary.

## Historical coverage and event-identification logic

The Phase 4D retrieval checked the USGS OGC API metadata and nine fixed date-lead neighborhoods (each lead date −3 days to +6 days) at each pilot. Continuous and daily 00065 are separate collections. Of these 18 site/window queries, 17 returned continuous observations; AMIL1's 2020-06-08 query returned none. The 17 query-window maxima are retained individually in `stage_source_coverage.json` and labelled `WINDOW_MAXIMUM_NOT_VERIFIED_FLOOD_CREST`. These windows overlap, so they are not 17 separate events. Actual OGC metadata reported these series bounds:

| Station | USGS 00065 series metadata | Metadata bounds UTC | USGS annual peak records |
|---|---|---|---|
| AMIL1 | Daily min/mean/max; instantaneous points; water-year max-at-event-time stage | Daily 1998-03-31 to 2026-11-06; instantaneous 2007-10-01 to 2026-11-08; annual stage 1949-05-04 to 2025-05-08 | 59 total: 43 stage (`00065`), 16 flow (`00060`), 1949-05-04 to 2025-05-08 |
| MNLM6 | Daily mean; instantaneous points; water-year max-at-event-time stage | Daily 1996-09-30 to 2026-11-06; instantaneous 2007-10-01 to 2026-11-08; annual stage 1916-07-05 to 2024-04-11 | 120 total: 61 stage (`00065`), 59 flow (`00060`), 1916-07-05 to 2024-04-11 |

The metadata bounds show that instantaneous readings are not a complete period-of-record archive: both reported point series begin in October 2007, while older annual stage records extend to 1916 (MNLM6) or 1949 (AMIL1). Metadata bounds are not proof of gap-free coverage. In the nine sampled windows, MNLM6 returned 865 instantaneous observations in each window, with an apparent 15-minute sample interval; its largest within-window gap was 15 minutes. AMIL1 returned 806–865 observations in eight windows, with largest gaps from 15 minutes to 5 hours. The AMIL1 2020-06-08 neighborhood returned zero continuous and zero daily records with no request error. Daily values were incomplete for AMIL1's 2016-03-12 and 2016-08-13 neighborhoods (8 values in each of three daily statistics versus 10 dates queried); other sampled AMIL1 windows returned 10 values in each statistic. MNLM6 returned 10 daily means for each sampled neighborhood. These counts describe only requested windows. The 2026-10/Nov samples were marked `Provisional`; historical window observations were `Approved`. The current OGC window-maximum records had no raw qualifier value; the independent earlier anomaly-hydrograph retrieval recorded raw `A` qualifiers on AMIL1's 2016-08-13 and 2017-04-04 maxima. The separate source series and qualifiers remain distinct in the downloaded artifacts.

USGS annual peaks are discrete annual maxima, not an inventory of all flood events. Their actual raw qualifier codes are retained in the source JSON. AMIL1 has `GHNOTASSCPKQ` on 24 records, `ESTIMATED` on 10 flow peaks, `DATUMCHANGE` plus `GHNOTASSCPKQ` on two stage peaks (1999-01-31 and 2004-05-16), and older partial-date/minimum qualifiers. MNLM6 has 118 records without a peak qualifier and two older partial-date/minimum qualifiers. These flags establish datum-change notations in two AMIL1 peak records, but not the effective dates, magnitude, or datum history needed to normalize the time series. NOAA NWPS metadata returned 33 AMIL1 historic crests (32 `O`, 1 `R`; 1998-10-07 through 2021-08-30 02:45Z) and 93 MNLM6 historic crests (89 `O`, 3 `P`, 1 `R`; 1916-07-05 through 2026-06-20 17:45Z). All returned NWPS crest rows have `olddatum=false`; this flag does not establish that gauge datum never changed. NWPS station metadata lists no vertical datum value for AMIL1 and lists NGVD29 elevation 55.64 ft for MNLM6, but neither response supplies a dated datum-change history. Annual peak qualifiers and NWPS datum attributes are evidence to review, not a complete datum reconciliation.

The legacy dates were used only as search-window centers; none were used to choose events or match stage peaks. The source-independent overlap audit found zero USGS annual-peak records within the tested lead windows, and four NWPS historic records per station within those broad windows. Each NWPS row is explicitly marked `DATE_WINDOW_OVERLAP_NOT_EVENT_MATCH`. For example, MNLM6's historic NWPS record is 19.72 ft at 2018-12-29 12:45Z (`O`), later than the 2018-12-28 legacy label; AMIL1's 29.28 ft NWPS record is 2016-08-12 04:45Z (`R`). These timestamps and stages are source observations, not independently validated legacy event associations. Daily values have date-level precision and were not used to infer a crest time.

The full raw data, source URLs, request timestamps, approval and qualifier fields, and per-series gap summaries are in latest artifact 13633585578. The condensed CSV/JSON are reproducible from that raw payload. The event-lead inventory in [`stage_event_leads.csv`](stage_event_leads.csv) contains 11 legacy-window maxima (5 AMIL1, 6 MNLM6); it records **0 confirmed observed flood crests** and **0 confirmed event pairs**. The separate crest detector in `reconstruction/river_stage.py` is a reproducible candidate generator, not a substitute for a datum audit or hydrologic review.

Candidate extraction is reproducible in `reconstruction/river_stage.py`: sort actual samples; accept a sample as a local-maximum candidate only when it is no lower than its preceding valid sample and strictly higher than the next; require neighboring samples within six hours; group peaks less than six hours apart only when the observed valley is less than 0.10 ft below the lower peak; retain both peaks when the valley is deeper; preserve source qualifiers and timestamps; and mark each result `CANDIDATE_UNVERIFIED`. The 0.10 ft ripple threshold is a documented review heuristic, not a hydrologic event threshold. This reduces short-term duplicate ripples while preserving sharper multiple peaks, but cannot establish event independence. Long gaps, qualified readings, plateaus, datum discontinuities, or uncertain multi-peak associations need manual review. Confirmed observed crest count remains zero.

The Phase 4B historical product sample found no MRMS Pass 2 hourly objects for the three sampled 48-hour windows, while official NOAA Stage IV daily archives were actually retrieved for sampled 2016, 2018, and 2019 dates. This is product/date-specific sampled coverage, not proof of total archive unavailability. The repository has not verified a historical six-hour rainfall reconstruction; daily Stage IV has not been converted into six-hour values.

## Remaining work and recommendation

1. Obtain dated USGS gage-height datum histories, especially to interpret AMIL1's two `DATUMCHANGE`-qualified annual peaks, and check any published datum shifts against the legacy stage source.
2. Retrieve broader historical instantaneous hydrographs without selecting windows from legacy dates; use event separation and continuity checks on observed stage itself, then review candidate flood crests with multiple peaks preserved when association is uncertain.
3. Determine the original RFC MAP basin definition and version from source methodology or archived operational configuration. Do not substitute an attribute match, full NLDI watershed, or incremental reach for it.
4. Investigate actual hourly Stage IV access and verify its valid times before use. Keep 24-hour Stage IV, hourly Stage IV, and MRMS products separate.
5. Backfill legacy-date neighborhoods plus independently discovered observed floods only after verifying stage, rain-period, geometry, and source provenance. Keep every uncertain event provisional.

No reconstructed MAP-to-crest points are science-approved or published by this work. The dashboard's reconstructed source control remains disabled unless an event record explicitly passes its `SCIENCE_APPROVED` gate.
