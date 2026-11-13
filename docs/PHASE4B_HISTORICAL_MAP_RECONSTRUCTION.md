# Phase 4B — Historical MAP basin reconstruction

## Scope and conclusion

This phase inventories the NOAA 2018 Lower Mississippi RFC (LMRFC) IHABBS basin network and tests whether directed subbasin relationships can support review-only aggregate candidates for the 29 historical forecast-point identifiers. It does not edit the Phase 2 observations or eligibility decisions, Phase 3 plots, the production rainfall calculations, or configured gages.

**Modern MRMS MAP is not interchangeable with legacy RFC MAP.**

The NOAA shapefile is a dated 2018 geometry snapshot; it does not establish which basin version was used by older MAP studies. The public shapefile does not include the IHABBS containment/upstream/downstream topology tables. The reproducible fallback uses outlet snapping and directed USGS NHDPlusV2/NLDI navigation as a **modern routed-network proxy**. It is never represented as the LMRFC model routing configuration. Even a complete routed union remains a candidate accumulation geometry, not an identified historical MAP mask.

The NLDI proxy is accepted only after the documented first-ring-vertex outlet convention and a returned flowline snap no farther than 200 m. A target candidate is withheld unless its RFC target outlet is routed, a full-upstream NLDI basin is available, and every RFC outlet inside that basin envelope has a linked COMID reachable through the directed relationship table. Boundary contact, names, forecast groups, or polygon proximity do not create network edges. Same-COMID ordering is not inferred from measure values alone.

## Reproducible artifacts

Run `python scripts/build_phase4b_rfc_aggregates.py --archive b_lmrfc.tar.gz --refresh-nldi` after obtaining the official source archive. The builder verifies the exact archive SHA-256 and 543-feature count, preserves all source DBF attributes, records NLDI responses and errors in a versioned cache, and writes the package under `reports/phase4b/`.

The official 2018 archive contains a topologically invalid source polygon (the first encountered is source feature index 30). The production refresh preserves original coordinates and records each geometry validity explanation in the inventory, GeoJSON, topology snapshot, and unresolved register. Defects are never silently repaired. Any aggregate whose routed components include an invalid feature is withheld. The general source loader remains strict by default; only the pinned production refresh opts into preserving and flagging the authentic source defects.

| Artifact | Contents |
| --- | --- |
| `rfc_feature_inventory.csv` | One row per RFC segment, all twelve original attributes, source fingerprint, outlet, geodesic area, link status and evidence hashes. |
| `rfc_single_segments.geojson` | Original 2018 segments as a distinct, unverified layer. |
| `topology_snapshot.json` and `nldi_responses.json.gz` | Outlet links, directed NLDI reach sets, target basin geometries, response hashes, retrieval times, unresolved requests, and the compressed raw response bundle. |
| `rfc_relationships.csv` | Pairwise directed RFC segment relationships supported by NLDI upstream flowline membership. |
| `station_reconciliation.csv` and `.json` | Exactly 29 crosswalk rows, geometry availability, area/overlap metrics, source references and uncertainties. |
| `candidate_aggregates.geojson` | Complete-coverage routed unions only; source component IDs remain attached. |
| `nldi_reference_geometries.geojson` | Current full-upstream and incremental references for exact same-site Phase 2-verified dashboard joins only. |
| `unresolved_issues.csv` | Withheld candidates and incomplete/ambiguous evidence. |
| `summary.json` | Feature, network, candidate, station status and unresolved counts. |
| `geometry_review.html` | Separate interactive review map. |

All area values use the WGS84 ellipsoid and are reported in square miles. Candidate comparisons report intersection, union, IoU, candidate coverage, reference coverage, and symmetric-difference area. These describe spatial similarity; they are not a MAP equivalence test. RFC source segments, RFC routed candidates, current NLDI full basins, and NLDI incremental reaches remain separate products.

## Source and version evidence

- NOAA NOHRSC, [2018 LMRFC basin archive](https://www.nohrsc.noaa.gov/data/vector/master/b_lmrfc.tar.gz), also recorded in the Phase 4A handoff as SHA-256 `ffd630cb973edfc70a5dabdeff383593bdcef8d17f697f2e824d6e3c636269bb`. Expected feature count: 543. The builder fails on a different fingerprint, count, missing source attributes, invalid geometry, or duplicate feature ID.
- NOAA, [IHABBS overview](https://www.nohrsc.noaa.gov/technology/gis/ihabbs_overview.html), [operational notes](https://www.nohrsc.noaa.gov/technology/gis/ihabbs_notes.html), and [RFC basin metadata](https://www.nohrsc.noaa.gov/data/vector/master/rfc_basins_metadata.htm). IHABBS basin topology includes containment and upstream/downstream relationships. The public shapefile export is not the topology database. The first polygon vertex is treated as the outlet under the documented IHABBS convention.
- USGS, [NLDI navigation](https://api.water.usgs.gov/docs/nldi/navigation/) and [basin/hydrolocation](https://api.water.usgs.gov/docs/nldi/basin/). NLDI provides directed NHDPlusV2 flowline navigation and hydrolocation. A failed/ambiguous request or snap beyond 200 m remains unresolved; raindrop-trace fallback is not accepted.
- EPA, [NHDPlusV2 User Guide](https://www.epa.gov/system/files/documents/2023-04/NHDPlusV2_User_Guide.pdf), for directed network connectivity and non-geometric flow connections.
- Phase 2 source crosswalk and plot-ready JSON exports in `historical/relationships/v1/source/`; Phase 4A polygon and station audit under `reports/phase4a/` and `docs/PHASE4A_NETWORK_BASIN_GEOMETRY_HANDOFF.md`.

The Phase 2 JSON preserves source spreadsheet metadata for 21 workbook files (9 MAP-to-crest sources and 12 crest-to-crest sources). Workbook name, worksheet, source row, and binary SHA-256 are retained per observation. The original Excel binaries and source basin masks are absent from the repository, so these metadata cannot identify the rainfall aggregation mask.

| Workbook | Sheet | Preserved rows | Binary SHA-256 in Phase 2 JSON |
| --- | --- | ---: | --- |
| `AMIL1_MAP_crest.xls` | Sheet1 | 23 | `dd5f52a8465d2c6be43c67bcd3b8da8e0af76dfc3f25d2e97b63eeeff1b74d0f` |
| `AMIL1_ROBL1_crest_crest.xls` | Sheet2 | 10 | `b515e734c2a334455f36abdbc82bbe650bf4b78e4ca602e6b654bb1458dae6e9` |
| `CLMM6_BXAL1_crest_crest.xls` | Sheet1 | 47 | `68b0f5aadbed6f8d2cbaaa5c3dec2ad1042c6d7ee4285634d08824ce2c54b42e` |
| `CREM6_MAP_crest.xlsx` | Sheet1 | 34 | `507fadf13ccc13eea374f37ee4407726f14284a60783f92e6bc7261132574324` |
| `FLSL1_CUSL1_crest_crest.xls` | Sheet3 | 39 | `69f77bb312cac93654b51cdd2a650605f706b9d4ff626c119f20e4e04282f54d` |
| `GLFM6_MAP_crest.xlsx` | Sheet1 | 54 | `50b2a7369bdc307ec293edca04dc4ecd59c4c480c16b11cc9b1c59d50351fe15` |
| `HOLL1_MAP_crest.xls` | Sheet2 | 41 | `9a65ce88f6a6d45a0c00b2a2c607bec63d38ba8866bc6a1fddd73615410413b9` |
| `KENL1_AMIL1_crest_crest.xls` | Sheet1 | 22 | `108be238a3a9c89e99f1f4d3c63a699c46957e7b142f7ef6db9a88269e0aa70b` |
| `KENL1_ROBL1_crest_crest.xlsx` | Sheet2 | 31 | `cfa4bd2ad57ec610937a6918d8ee42c97f0d8993a4ffd72fd70530f5f2812893` |
| `KENL1_map.xls` | Sheet1 | 32 | `f3e1efbf964cc0f0d09be8cd65f0612dfa02e492f317f6d45ad28fca97b83121` |
| `KLNM6_MAP_crest.xls` | Sheet1 | 7 | `2fc21626bf3a7416079a2daf4da8dc3ab272ae77686a02f200e43de8f28b6ddd` |
| `LNDM6_MAP_crest.xls` | Sheet1 | 37 | `e17757afb096d705410597694131d8465a38bad45ebe064ecc6082e113ae5c2c` |
| `LNDM6_crest_GLFM6.xls` | Sheet1 | 45 | `21e8b799a2f0abb1257d3c1fb558d07653eeb0dec044e94476986a54b09779ab` |
| `LPOL1_MAP_crest.xls` | graph | 38 | `0fd15a89c78a95beffd4aab6a3f4b445141a09c584a8f1fdee2677a68f1e0b51` |
| `LPOL1_MONL1_crest_crest.xls` | Sheet2 | 38 | `f517c4a171c42be87a965cefce26cef91a7174ac2941550a620bc3cb55286464` |
| `MAGL1_DENL1_ crest_crest.xls` | Sheet2 | 13 | `e5a97a3257455e9e96079ada47df9d25aa98097cf3bbf16eecb46cb35f7a7855` |
| `MNLM6_MAP_crest.xls` | Sheet1 | 48 | `85d58d8f7a4f7cd0ec4a60b5c58fe903ac13ef5bbc5cf1447e972947df24c201` |
| `MONL1_HOLL1_crest.xls` | Sheet2 | 34 | `7fdc8270fc6cd2c80528b9e90ac683f39c2e463b5ec5b3e752896cc46687f595` |
| `MONL1_map.xls` | Sheet1 | 28 | `f338ce98936bd02c73345d3b4545e4aff24cabf1e8ea8c9b0374fd7fe1e8e2a9` |
| `OSYM6_KENL1_crest.xls` | Sheet1 | 34 | `433319729cc8ac4251bdc7d69a6f122ee404ac54f2870c51baa748720594d6e1` |
| `WTPM6_DIBM6_Crest.xls` | Sheet1 | 11 | `51e8986fc4a40abacf66859d63cdc7e81032db88290f7624c5665ae922b4b658` |

## Historical point reconciliation and unresolved register

All 29 canonical NWSLIs are represented once in the reconciliation. Exact 2018 `NWSID` matches are associated with source `OBJ_IDENTIF` values; unmatched IDs are retained without a fabricated single-segment geometry. The Phase 4A result established exact attributes for 26 of 29 IDs. `FBFL1`, `LBFL1`, and canonical `WPTM6` have no exact attribute match in that snapshot; this does not prove that no appropriate basin exists under another identifier.

NLDI comparison geometry is included only where the Phase 2 crosswalk confirms the same USGS site and that site has a current repository basin. No nearest or merely overlapping dashboard gage is borrowed. `MNLM6` and `CREM6` remain separate. Raw `WTPM6` provenance remains attached to canonical `WPTM6`. `KLNM6` is not assigned to USGS `02481667`.

The machine-readable `unresolved_issues.csv` and `summary.json` are the run-specific issue register. Expected uncertainty classes include:

- No public IHABBS/model routing tables or versioned RFC aggregation definitions in the repository.
- Older historical periods may predate or differ from the 2018 basin geometry.
- NHDPlusV2/NLDI may differ from RFC-specific flow direction, segmentation, diversions, or operational topology.
- Outlet points may be missing, outside the snap tolerance, ambiguous, or affected by changes to the modern flowline network.
- A routed outlet may be absent from NLDI's target basin geometry or present there without a directed reach path; either conflict blocks the aggregate.
- Present-day NLDI polygons and model gage definitions may not represent the historical period or the original rainfall gauges.
- Original spreadsheet files and mask/area definitions remain unavailable. Geometric resemblance cannot fill this evidence gap.

**No Phase 4B geometry is certified as the original historical MAP mask.** Candidate confidence describes only current network-link completeness. Historical MAP confidence remains `NONE` until an original study/model basin definition is recovered.

## Validation and Phase 4C recommendation

Offline tests cover the pinned archive contract, source-field preservation, invalid/duplicate feature rejection, outlet snap threshold, directed relationship direction, cache reuse, incomplete-coverage withholding, geodesic comparisons, one-to-one 29-station output, and the invariant that candidate status never verifies MAP equivalence. CI also runs existing dashboard and Phase 3 tests. The workflow refreshes NOAA and NLDI evidence on a branch, runs validation, saves the package as an artifact, and commits generated outputs only to `phase4b/map-basin-reconstruction`.

Phase 4C should first obtain the historical RFC model configuration or IHABBS topology/containment export for the study period and the original spreadsheet binaries or preserved metadata identifying each MAP basin/area. Compare each candidate against those period-correct sources before using it in any historical rainfall reconstruction. Only after the geometry and temporal aggregation are documented should an event reconstruction compare the original RFC gauge-based MAP to modern MRMS over the same period and mask. Keep those rainfall products separate, preserve the Phase 2 values and Phase 2 eligibility decisions, and report any changed interpretation as new research output.
