# Phase 4B initial evidence report — 2026-11-08

**Status:** scientific event inventory *in progress*; **zero science-approved reconstructed MAP–crest points.**
Both pilot sites remain AMIL1 / USGS 07375430 and MNLM6 / USGS 02492360 (West Hobolochitto).

## Independent USGS instantaneous-stage review

Actual 00065 gauge-height observations were retrieved through GitHub Actions over nine-day review windows (legacy date lead minus three days to plus six days). The legacy date is **not** assumed to be a crest time. The number reported as an observed maximum is the largest available sample anywhere in that review window; multiple crests and stage qualifiers have not been fully adjudicated.

See [11-window source retrieval and results](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42513224763) and the `phase4b-stage-lead-inventory` artifact. Values below are unverified stage comparisons, not approved event matching:

| Station | Legacy source date lead | Legacy crest (ft) | Observed review-window maximum (ft) | Observed minus legacy (ft) | Sample time (UTC) |
|---|---|---:|---:|---:|---|
| AMIL1 | 2016-03-12 | 24.70 | 24.73 | +0.03 | 2016-03-11 20:45 |
| AMIL1 | 2016-08-13 | 26.20 | 29.28 | **+3.08** | 2016-08-13 04:45 |
| AMIL1 | 2017-04-04 | 17.80 | 11.64 | **-6.16** | 2017-04-04 05:30 |
| AMIL1 | 2018-12-28 | 19.00 | 18.98 | -0.02 | 2018-12-28 17:15 |
| AMIL1 | 2019-04-20 | 13.50 | 13.51 | +0.01 | 2019-04-19 23:15 |
| MNLM6 | 2016-03-12 | 22.50 | 22.62 | +0.12 | 2016-03-12 13:30 |
| MNLM6 | 2017-04-03 | 15.40 | 15.43 | +0.03 | 2017-04-04 02:00 |
| MNLM6 | 2018-12-28 | 19.70 | 19.72 | +0.02 | 2018-12-29 18:45 |
| MNLM6 | 2019-05-12 | 23.00 | 22.97 | -0.03 | 2019-05-12 14:00 |
| MNLM6 | 2020-06-08 | 15.20 | 15.26 | +0.06 | 2020-06-08 19:45 |
| MNLM6 | 2026-10-31 | 18.10 | 18.01 | -0.09 | 2026-11-01 16:00 |

**Priority discrepancies:** AMIL1 August 2016 and April 2017. Do not auto-match these events or infer a datum offset from the differences. The window maximum may represent a different event or peak; the original source crest/date semantics, QC, hydrograph and gauge datum timeline require inspection. Some observed values carry qualifiers; source processing does not interpret them as final-approved readings. Missing individual stage samples and plateau maxima remain possible.

## Historical precipitation availability

[Official Stage IV and MRMS sample coverage audit](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42513039930):
- For the **three sampled 48-hour windows** in 2016, 2018 and 2019, the specific NOAA S3 `MultiSensor_QPE_01H_Pass2_00.00` inventory yielded **0/48** hours each. This does **not** prove no other MRMS or archived rainfall product exists for those dates.
- NOAA dated Stage IV **daily source tar archives** for 2016-03-12, 2018-12-28 and 2019-05-12 responded HTTP 200. The guessed daily GeoTIFF paths returned 404 and must not be cited as archived products.

[Source tar contents verified](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42513139220):
- 2016-03-12: `conus_20160312_24h.grb.gz`.
- 2018-12-28: `conus_20181228_24h.grb.gz` (plus Alaska/Puerto Rico members).
- 2019-05-12: `conus_20190512_24h.grb.gz` (plus Alaska/Puerto Rico members).
- SHA-256 fingerprints of every exact source member were preserved in the uploaded JSON artifact.

[Actual 2018-12-28 Stage IV CONUS GRIB metadata inspected](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42513277388):
- Native polar stereographic projection, **1121 × 881 grid**, nominal **4,763 m** pixel spacing.
- Band 1 GRIB element `APCP`, unit `kg/m²`, `GRIB_FORECAST_SECONDS=86400`, with separate reference/valid times. This is a **24-hour** product, **not** a six-hour MAP measurement.
- Masked cells must not be interpreted as dry cells. Historical independent daily accumulation results require reprojection/area-weighting validation and precise 12Z-to-12Z interval accounting.

NOAA's [precipitation data access documentation](https://water.noaa.gov/about/precipitation-data-access) distinguishes historical Stage IV source data, Stage III and daily accumulations. The [USGS Stage IV archive catalog](https://water.usgs.gov/catalog/datasets/8e72f0f7-f97c-4b39-8bcf-3a7ff1d772a8/) describes hourly Stage IV data back to 2002, but **this repository has not yet independently retrieved and decoded historical hourly Stage IV data from that archive**.

## Rainfall–stage science gates

1. Review the archived stage hydrographs, per-observation qualifiers, site datum history and peaks that may occur outside the date-lead window. Resolve AMIL1 August 2016 and April 2017 differences first.
2. Establish rainfall episode windows from QPE/time series and hydrology; do not adjust rainfall durations until they resemble historical spreadsheet MAP.
3. Acquire hourly Stage IV (if actually obtainable and validated) for historical 2016–2019 cases; alternatively calculate a separate **daily** estimate from 24h products and clearly label timing limitations.
4. Verify historical LMRFC basin outlines and distinguish whole-upstream NLDI MAP from original RFC MAP.
5. Keep the website's `SCIENCE_APPROVED` reconstructed-event gate disabled until event-level evidence and method reviews support it.

The existing 2026-10-31 49h MRMS Pass 2 reproduction for both stations remains verified only **as a rainfall calculation over the same frozen NLDI polygons**. It is not proof that historical LMRFC MAP or its associated crest is equivalent.


## October 2026 rainfall timing versus USGS stage (provisional)

An independent diagnostic downloaded all 49 original MRMS Pass 2 hours again, calculated full-upstream basin hourly precipitation, and retrieved USGS 00065 samples around the case:
[successful GitHub-hosted calculation](https://github.com/mefferso/River-Drainage-Basin-Mean-Rainfall/actions/runs/42513583015).

| Pilot | Window maximum stage | Candidate UTC time | Event MAP | Rainfall before maximum | Rainfall after maximum |
|---|---:|---|---:|---:|---:|
| AMIL1 | 5.11 ft | 2026-11-01 15:45 | 0.352643 in | 0.345028 in | 0.007616 in |
| MNLM6 | 18.01 ft | 2026-11-01 16:00 | 6.878852 in | 6.878766 in | 0.000086 in |

For AMIL1, the candidate stage maximum is **not necessarily a flood crest** and one clock hour partially overlaps the peak timestamp, although its QPE contribution was zero at displayed precision. The stage maxima and rainfall windows are not yet approved as corresponding hydrological events.

**Important interpretation for MNLM6:** although the existing 49h accumulation ends 14 hours *after* the observed stage-window maximum, only **0.000086 in** of the calculated basin MAP fell after that maximum. Thus, this particular event's 49h total is not materially inflated by post-peak rain. This does *not* reconcile the existing legacy 2026-10-31 MNLM6 MAP **5.1 in** with the independently reproduced whole-NLDI-basin MRMS Pass 2 MAP **6.878852 in**, a difference of **+1.778852 in** (MRMS minus legacy). Investigate original RFC basin geometry, rainfall-window semantics, QPE product algorithms and event record provenance before drawing conclusions.

A key remaining requirement is to inspect the full hourly rainfall/stage evolution and separately establish the storm rainfall onset and end rather than approving the fixed 49h period by assumption.
