# Phase 4B: Historical MAP Basin Reconstruction — Design

**Status:** Proposed for owner review
**Repository baseline:** `main` at `8d4d558`
**Scope:** Build a traceable, review-only RFC basin network inventory and candidate aggregate drainage geometries for the 29 Phase 2 historical forecast-point IDs.

## Intent

Phase 4A compared single 2018 LMRFC IHABBS polygons with the repository's current NLDI full-upstream and incremental polygons. It found 543 RFC polygons, exact NWSLI attributes for 26 historical IDs, and no scientifically approved legacy MAP geometry. Phase 4B will expose the full attribute inventory and test upstream aggregate candidates using documented routing connectivity, while keeping 2018 RFC polygons, constructed candidates, and NLDI polygons as distinct data products. The work is for hydrologic review; it will not backfill or alter any historical MAP/crest observations.

The Phase 2 spreadsheet binaries and the project Master Plan's referenced workbook example are not present in this checkout. The Phase 2 JSON exports preserve workbook/sheet/row provenance for nine MAP source workbooks (301 rows), but do not establish the original mask for any study. Consequently, no Phase 4B class can certify a candidate as the exact historical MAP mask.

## Goals

- Inventory all 543 polygons, preserving every source attribute, source feature identifier, geometry, source archive hash, and source URL.
- Account for every canonical forecast-point ID in the 29-row Phase 2 crosswalk, including IDs lacking coordinates, a matching RFC feature, an approved USGS match, or an existing dashboard basin.
- Seek original IHABBS topology/model relationships first. Where that source is unavailable, use USGS NHDPlusV2/NLDI routed network topology as a separately labeled connectivity proxy, only after RFC polygon outlets have been associated with routed COMIDs and upstream reachability has been checked against the directed network.
- Construct unioned upstream RFC geometry candidates only from explicit verified network reachability. Geographic touching, overlap, name similarity, shared forecast group, or proximity alone never creates an edge.
- Compare source single-segment, aggregate candidate, and NLDI full/incremental geometries with geodesic areas, intersection/union area, IoU, and directed coverage metrics.
- Provide a separate interactive GIS review map and a machine-readable unresolved-issues register.
- Keep every result traceable to evidence and expose confidence about the network link separately from confidence about historical MAP equivalence.

## Non-goals and anti-goals

- No changes to operational MRMS rainfall calculations, current gage configuration, or Phase 3 production historical plots.
- No new or rewritten Phase 2 observations, eligibility decisions, or station crosswalk decisions.
- No use of 2018 polygons as though they were contemporaneous with all historical study periods.
- No claim that NHDPlus-derived aggregates are LMRFC model routing configuration or historical MAP masks.
- No automatic crosswalk from a nearby USGS site; no use of geographic contact or proximity as routing proof.
- No calibration, rainfall reconstruction, or event backfill in this phase.

## Evidence and constraints found

- The Phase 4A audit records 26 exact 2018 `NWSID` matches; `FBFL1`, `LBFL1`, and canonical `WPTM6` have no exact polygon match. It also records 11 IDs without a verified dashboard join and 18 verified dashboard joins.
- The LMRFC shapefile contains `OBJ_STATUS_`, `OBJ_IDENTIF`, `NAME`, `MIN_X_AXIS_`, `MAX_X_AXIS_`, `MIN_Y_AXIS_`, `MAX_Y_AXIS_`, `FCSTGROUP`, `NWSID`, `AREA`, `DESCRIPT`, and `TVA_NUM`. These attributes do not encode upstream/downstream links.
- NOAA IHABBS documentation says basin topology includes upstream/downstream and containment relationships. Its overview says basin outlets/discharge points are used with the flow-direction grid and that the first polygon vertex is at the discharge point. The public shapefile export does not include the full topology database. See [IHABBS overview](https://www.nohrsc.noaa.gov/technology/gis/ihabbs_overview.html), [IHABBS operational notes](https://www.nohrsc.noaa.gov/technology/gis/ihabbs_notes.html), and [NOHRSC RFC basin metadata](https://www.nohrsc.noaa.gov/data/vector/master/rfc_basins_metadata.htm).
- The NLDI exposes upstream navigation based on NHDPlusV2 network connectivity and coordinate hydrolocation. The NHDPlusV2 `PlusFlow` table represents directed flow connections, including some non-geometric connections. See [USGS NLDI navigation](https://api.water.usgs.gov/docs/nldi/navigation/), [USGS NLDI basin and hydrolocation](https://api.water.usgs.gov/docs/nldi/basin/), and the [EPA NHDPlusV2 User Guide](https://www.epa.gov/system/files/documents/2023-04/NHDPlusV2_User_Guide.pdf).
- The LMRFC MAP paper describes a legacy Thiessen-gauge MAP archive used for modeled subbasin calibration and a distinct radar-derived MAPX beginning in 1997. Neither the paper nor Phase 2 JSONs identify which geometry/version each original workbook used. See [LMRFC rainfall area-reduction paper](https://www.weather.gov/media/lmrfc/tech/2016_03_Comparison_Rainfall_Area_Reduction_Factors_Basin_Avg_Precipitation.pdf).

## Approaches considered

1. **Original IHABBS/model topology only.** Best evidence for RFC segment relationships, but the public shapefile lacks topology links and this repository has no model configuration/topology export. This remains the preferred source if an authoritative export can be obtained. It cannot be assumed available for every station.
2. **Hybrid original-topology plus NHDPlus/NLDI proxy (recommended).** Use an authoritative IHABBS/model edge list whenever obtainable. Otherwise, associate IHABBS outlet points with NHDPlus flowlines through the documented NLDI hydrolocation service and use returned NHDPlus network navigation edges to identify routed upstream candidate segments. Mark this as an NHDPlus topology proxy, never as LMRFC routing configuration. Fail closed where the association is ambiguous, absent, too distant, or inconsistent with station evidence.
3. **No aggregate geometry.** Publish the full RFC attribute inventory, the 26 exact single-segment polygons, current NLDI comparisons, and explicit unresolved topology for every point. Safest if no defensible topology source can be acquired, but does not produce the useful review-only candidates requested where evidence allows.

The recommendation is approach 2 because it uses the authoritative RFC graph when available and allows a separate, reproducible hydrologic-network proxy where it is not. Approach 3 is the required fallback per point when association or connectivity evidence fails.

## Proposed evidence and confidence model

Record two independent classifications for each point/candidate:

1. **Connectivity evidence:** `RFC_TOPOLOGY_VERIFIED`, `NHDPLUS_LINKED_PROXY`, or `UNRESOLVED`. The NHDPlus classification requires a routed COMID association for the target and for each included RFC segment, supported by the IHABBS outlet coordinate, stable source feature ID, network response, and distance/association diagnostics. NLDI navigation must return the included upstream flowline set; adjacency alone is never used.
2. **Historical MAP equivalence:** `NOT_ESTABLISHED` for every candidate unless original workbook metadata or dated LMRFC model/MAP configuration identifies the geometry/version used for that MAP series. A high-confidence network proxy is not a high-confidence historical MAP mask.

The candidate algorithm will include only mapped RFC polygons whose outlet COMIDs are confirmed upstream of the target COMID through NHDPlus/NLDI directed navigation. An RFC outlet is the first coordinate of its polygon ring per the IHABBS documentation; that location must resolve by NLDI's snap-to-flowline hydrolocation within the documented 200 m tolerance. Raindrop-trace fallback, farther snaps, missing COMIDs, or conflicting links remain unresolved. Each edge must also be consistent with the full-upstream basin returned by the routed target COMID. This uses a topology-derived basin and network response, not boundary contact or point proximity alone. The complete pairwise relationship inventory covers all 543 RFC nodes; source nodes that fail link checks remain in the node inventory with no invented edges.

For a target station, include the target's RFC polygon and every RFC polygon whose routed outlet is an ancestor of the target outlet. Candidate boundaries are a geometric union of those source polygons; source components and edge evidence are retained in GeoJSON properties or sidecar tables. If source polygons are nested or overlap, the union dissolves overlaps and reports both raw component-area sum and union area. It will not infer incremental model units by polygon subtraction. If the network response or source-node mapping is incomplete for any portion of the target's relevant upstream RFC set, withhold the candidate polygon and record why rather than label a partial union as complete.

## Deliverables and file organization

- `reports/phase4b/rfc_feature_inventory.csv`: all 543 source features, all source attributes, geometry-derived geodesic area, source archive/feature fingerprints, and validation flags.
- `reports/phase4b/rfc_single_segments.geojson`: all 543 source polygons, unchanged geometries with all source fields and explicit `UNVERIFIED_LEGACY_MAP_GEOMETRY` status.
- `reports/phase4b/rfc_relationships.csv`: complete directed upstream/downstream pair inventory among the 543 RFC nodes, with the source and COMID/network evidence for each relationship. Unlinked nodes remain in `rfc_feature_inventory.csv` with a reason and generate no guessed edge.
- `reports/phase4b/station_reconciliation.csv`: exactly 29 rows with point identity, coordinates and coordinate evidence, exact RFC match, dashboard/NLDI geometry availability, source/candidate areas, overlap metrics, evidence references, separate confidence classifications, and unresolved reasons.
- `reports/phase4b/candidate_aggregates.geojson`: one candidate feature per station only where explicit routed reachability and outlet association checks pass; never a fabricated empty polygon.
- `reports/phase4b/unresolved_issues.csv`: all missing/ambiguous target, outlet-link, topology, crosswalk, coordinate, and historical-method evidence issues.
- `reports/phase4b/summary.json`: counts, source fingerprints, source versions/dates, method versions, and validation totals.
- `reports/phase4b/geometry_review.html`: standalone review map that separates source RFC segments, candidate unions, and NLDI full/incremental references, and shows per-layer provenance/confidence.
- `scripts/build_phase4b_rfc_aggregates.py`: deterministic builder from the pinned 2018 archive plus a versioned NHDPlus/NLDI topology extract; supports fixture-based offline tests and a refresh mode that re-fetches sources, checks hashes/version, and writes comparison outputs. Network retrieval is cached and throttled; workflow timeout and per-request errors are explicit.
- `tests/test_phase4b_rfc_aggregates.py` and `tests/test_phase4b_map.cjs`: data-contract, routing, geometry, provenance, coverage, and map-state checks.
- `docs/PHASE4B_HISTORICAL_MAP_RECONSTRUCTION.md`: methods, validation summary, citations, complete results, unresolved issue register, and Phase 4C recommendation.

All 29 IDs must have one reconciliation row. Only existing verified same-site dashboard joins can use existing repository NLDI polygons. Other stations must clearly state that an existing NLDI full/incremental comparison is unavailable; no nearby dashboard basin is borrowed. Missing exact RFC IDs remain represented without a fabricated source single-segment polygon.

## Comparison metrics

Use WGS84 ellipsoidal geodesic area (square miles) for all source and result polygons. For each available candidate versus an available NLDI reference, report:

- candidate, RFC single-segment, NLDI full-upstream, and NLDI incremental area;
- area of intersection and union, IoU = intersection/union;
- candidate coverage of NLDI = intersection/NLDI area;
- NLDI coverage of candidate = intersection/candidate area;
- symmetric difference area and signed area difference.

Report metrics separately against full-upstream and incremental NLDI. Metrics describe spatial agreement only; they do not determine confidence or MAP equivalence.

## Validation gates

- Reproduce the official 2018 LMRFC archive SHA-256 and exactly 543 features; verify all 12 documented attribute names survive losslessly.
- Account for each of the 29 canonical IDs once. Preserve raw `WTPM6` source spelling with canonical `WPTM6`; preserve separate `MNLM6` and `CREM6`; never attach `KLNM6` to USGS `02481667`.
- Every generated network edge must be backed by a downloaded/versioned authoritative routing response or model topology source; every proxy outlet association stores COMID, method, point coordinate, result distance/measure, source URL, retrieval date, and response hash. Candidate relations are emitted only when both mapped outlet COMIDs are connected by the directed upstream navigation result and are consistent with the target full-upstream basin.
- Reject non-finite, invalid, or empty candidate geometries. Candidate area must be at least each included valid component's covered area and no greater than the sum of component areas, within numeric tolerance.
- Recompute all area/intersection/union metrics in tests; test disjoint, nested, overlapping, invalid, and missing geometries.
- Assert unresolved topology yields no aggregate GeoJSON feature and a specific issue row; never fall back to contact/proximity, RFC forecast group membership, or names.
- Keep source single-segment, aggregate candidate, and NLDI geometries as distinct layers and separate output paths.
- The review map has 29 historical choices, honest missing-data states, a working layer legend, and remains isolated from production dashboard assets.
- Run all existing Python and Node tests plus new Phase 4B tests. Do not merge unless all required tests and CI pass. Do not merge during this phase.

## Phase 4C recommendation

Use this Phase 4B package only as a documented geometry-comparison input. Before any MRMS reconstruction, acquire the original workbooks/source methodology and, where possible, historical LMRFC MAP/MAPX configuration or basin masks; establish date/event windows and correct legacy geometry epoch. Keep any MRMS reconstruction as a separately named series with its own geometry/version and rainfall-time method. Pilot no more than two contrasting basins after those gates, compare overlap periods against source MAP records, document differences and missing-data effects, and require hydrologic review before wider backfill. Do not change operational MRMS calculations or Phase 3 plots.
