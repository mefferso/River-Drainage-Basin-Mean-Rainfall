# Phase 4B Historical MAP Basin Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Publish a traceable 543-feature LMRFC basin inventory, topology-supported RFC aggregate candidates for the 29 historical forecast-point IDs where evidence is complete, and a separate GIS review package.

**Architecture:** A deterministic Python builder verifies the NOAA 2018 archive, records NHDPlus/NLDI outlet and topology evidence, and constructs fail-closed relationship and geometry outputs. A standalone GIS review map and methodology report consume only versioned Phase 4B artifacts; the production dashboard calculations and Phase 3 plots remain untouched.

**Tech Stack:** Python 3.11, requests, GeoPandas/Shapely, pyproj, JSON/CSV/GeoJSON, static HTML/Leaflet, Node syntax checks, GitHub Actions.

**Spec:** docs/superpowers/specs/2026-11-08-phase4b-map-basin-design.md

## Global Constraints

- Evaluate exactly the 29 canonical historical NWSLIs from the Phase 2 crosswalk and all 543 NOAA 2018 LMRFC features.
- Preserve all twelve NOAA RFC feature attributes and the archive SHA-256; do not rewrite source geometries.
- Prefer original IHABBS/model topology. Label NHDPlusV2/NLDI relations as a routed-network proxy, not LMRFC model configuration.
- Associate each RFC polygon outlet using the IHABBS first-vertex convention and NLDI snap-to-flowline at no more than 200 m; do not use raindrop-trace fallback.
- Emit no topology edge without an authoritative directed-network result; emit no aggregate geometry if upstream coverage is incomplete.
- Keep RFC source segments, RFC aggregate candidates, and NLDI full/incremental polygons separately versioned.
- Never label a candidate as the legacy MAP mask without source-study geometry evidence. Preserve MNLM6/CREM6, raw WTPM6 provenance/canonical WPTM6, and the unresolved KLNM6 to USGS 02481667 mapping.
- Do not modify MRMS calculations, config/gages.json, Phase 2 data/eligibility, or production Phase 3 plots.
- Do not merge the pull request in this phase.

## File Structure

- Create scripts/build_phase4b_rfc_aggregates.py for NOAA archive validation, NLDI cache refresh, outlet mapping, topology relations, geometry candidates, and spatial metrics.
- Create tests/test_phase4b_rfc_aggregates.py with offline fixtures for source validation, outlet mapping, relation direction, aggregate union, metrics, and fail-closed output.
- Generate reports/phase4b/rfc_feature_inventory.csv, rfc_single_segments.geojson, topology_snapshot.json, rfc_relationships.csv, station_reconciliation.csv, candidate_aggregates.geojson, unresolved_issues.csv, and summary.json.
- Create reports/phase4b/geometry_review.html and tests/test_phase4b_map.cjs for isolated GIS review.
- Create docs/PHASE4B_HISTORICAL_MAP_RECONSTRUCTION.md for scientific method, validation, sources, uncertainty register, and Phase 4C recommendation.
- Create .github/workflows/phase4b-rfc-reconstruction.yml for bounded source refresh, artifact validation, upload, and feature-branch-only generated commits.
- Modify .github/workflows/deploy.yml to include reports/phase4b and the handoff document in deployment paths.
- Modify .github/workflows/ci.yml only as needed to run new offline tests with GeoPandas and pyproj installed.

## Review Focus

1. Missing or changed NOAA archive: absence, hash mismatch, unexpected count/schema, or malformed feature must fail before output. Test in Task 1.
2. Ambiguous outlet-to-COMID link: >200 m, raindrop trace, missing COMID, or conflicting evidence must be unresolved with no network edge. Test in Task 2.
3. Incomplete upstream coverage: a target with an unlinked RFC feature that could contribute must not receive a partial aggregate. Test in Task 3.
4. Nested, overlapping, disjoint, empty, or invalid geometry: metrics must be valid and distinguish union area from raw component area. Test in Task 3.
5. Absent station identity or dashboard geometry: all 29 rows remain represented; no nearby USGS geometry is substituted. Test in Task 3 and Task 4.

---

### Task 1: Verify and inventory all RFC basin source features

**Files:**
- Create: scripts/build_phase4b_rfc_aggregates.py
- Create: tests/test_phase4b_rfc_aggregates.py
- Generate: reports/phase4b/rfc_feature_inventory.csv
- Generate: reports/phase4b/rfc_single_segments.geojson

**Interfaces:**
- load_rfc_features(archive_path: Path) -> list[RfcFeature]; each feature retains source index, all twelve raw attributes, geometry, and WGS84 geodesic area.
- write_source_inventory(features: Sequence[RfcFeature], out_dir: Path, archive_sha256: str) -> None.

- [ ] Step 1: Write failing source-contract tests.

Test test_archive_count_and_all_attributes_are_preserved with a small fixture shapefile. Preserve all fields, feature IDs, nulls, and valid geometry.

Test test_source_fingerprint_and_expected_feature_baseline with injected fixture expectations; require 543 features and production archive SHA-256 ffd630cb973edfc70a5dabdeff383593bdcef8d17f697f2e824d6e3c636269bb.

Test test_inventory_rejects_bad_geometry_or_duplicate_feature_id.

- [ ] Step 2: Run python -m unittest -v tests/test_phase4b_rfc_aggregates.py. Expected: FAIL because source functions are absent.
- [ ] Step 3: Implement the source loader and inventory writer. Read official b_lmrfc.tar.gz, retain raw DBF values, transform geometry to EPSG:4326 only for output, calculate geodesic area, and retain source index/hash.
- [ ] Step 4: Re-run the focused tests; expected: PASS. Production refresh accepts only 543 features and the pinned archive fingerprint.
- [ ] Step 5: Commit the source inventory implementation.

### Task 2: Map outlets and build routed relationships

**Files:**
- Modify: scripts/build_phase4b_rfc_aggregates.py
- Modify: tests/test_phase4b_rfc_aggregates.py
- Generate: reports/phase4b/rfc_relationships.csv
- Generate: reports/phase4b/summary.json

**Interfaces:**
- resolve_outlet_link(feature: RfcFeature, response: Mapping[str, object]) -> OutletLink; retain source coordinate, NLDI method/distance/measure, COMID, retrieval time, URL, and response hash.
- build_relationships(features: Sequence[RfcFeature], links: Mapping[str, OutletLink], upstream_reach_sets: Mapping[int, set[int]]) -> tuple[list[Relationship], list[Issue]].
- fetch_network_cache(features: Sequence[RfcFeature], cache_dir: Path, refresh: bool) -> NetworkCache; retain versioned outlet links, routed upstream sets, response hashes, and target full-basin envelopes in topology_snapshot.json.

- [ ] Step 1: Add failing tests: test_outlet_accepts_snap_at_or_below_200m; test_raindrop_far_snap_and_missing_comid_are_unresolved; test_relationship_direction_uses_only_directed_upstream_membership; test_unlinked_nodes_remain_without_edges.
- [ ] Step 2: Run the focused unittest command; expected: FAIL because response parsing and relationship building are absent.
- [ ] Step 3: Read the first ring coordinate as the IHABBS discharge point. Accept only NLDI snap-to-flowline results within 200 m; cache successes and errors. Build pairwise directed relationships only from NHDPlusV2/NLDI upstream navigation results. For completeness, compare every RFC outlet with the target's NHDPlus-derived upstream-basin envelope; any outlet inside the envelope without a valid routed link blocks that target aggregate. Do not use forecast-group membership, names, polygon intersection, or adjacency as connectivity proof.
- [ ] Step 4: Re-run the focused tests; expected: PASS, with ambiguous links producing no edges.
- [ ] Step 5: Commit the outlet and relationship implementation.

### Task 3: Build candidate geometries and NLDI comparisons

**Files:**
- Modify: scripts/build_phase4b_rfc_aggregates.py
- Modify: tests/test_phase4b_rfc_aggregates.py
- Generate: reports/phase4b/station_reconciliation.csv
- Generate: reports/phase4b/candidate_aggregates.geojson
- Generate: reports/phase4b/unresolved_issues.csv

**Interfaces:**
- build_station_candidate(point: Mapping[str, object], features: Sequence[RfcFeature], relationships: Sequence[Relationship], links: Mapping[str, OutletLink], nldi_full: BaseGeometry | None, nldi_incremental: BaseGeometry | None) -> StationResult.
- compare_geometries(candidate: BaseGeometry, reference: BaseGeometry | None) -> GeometryMetrics | None, reporting geodesic areas, intersection, union, IoU, both coverage fractions, and symmetric-difference area.
- write_station_outputs(points: Sequence[Mapping[str, object]], results: Sequence[StationResult], out_dir: Path) -> None; requires exactly 29 crosswalk rows.

- [ ] Step 1: Add failing tests: test_candidate_unions_only_directed_upstream_components; test_candidate_is_withheld_when_upstream_link_coverage_is_incomplete; test_metrics_are_geodesic_and_bounded; test_all_29_points_are_accounted_with_no_borrowed_nldi; test_candidate_never_claims_legacy_map_equivalence.
- [ ] Step 2: Run the focused unittest command; expected: FAIL because candidate and metric functions are absent.
- [ ] Step 3: Build candidates only from complete directed upstream reachability and a complete target-basin envelope check. Preserve raw component IDs and both raw summed component area and union area. Compare only to existing NLDI polygons for exact Phase 2-verified USGS joins; otherwise state NO_EXISTING_NLDI_REFERENCE. Separate connectivity classification from historical MAP equivalence.
- [ ] Step 4: Re-run focused tests; expected: PASS. Incomplete or invalid candidates have no output geometry and a station-specific issue.
- [ ] Step 5: Commit candidate and reconciliation outputs.

### Task 4: Add an isolated GIS review map

**Files:**
- Create: reports/phase4b/geometry_review.html
- Create: tests/test_phase4b_map.cjs
- Modify: .github/workflows/deploy.yml

- [ ] Step 1: Write failing test_phase4b_map.cjs checks for inline script syntax, all 29 station options, layer path existence, separate source/candidate/NLDI labels, evidence/confidence details, honest missing states, and non-equivalence warning.
- [ ] Step 2: Run node tests/test_phase4b_map.cjs; expected: FAIL because map/test are missing.
- [ ] Step 3: Build a standalone map following the read-only Phase 4A pattern. Show source segments, candidate aggregates, full-upstream and incremental NLDI separately. Do not modify index.html or historical-ui.js. Add Phase 4B report paths to deploy trigger for a later main deployment.
- [ ] Step 4: Re-run node tests/test_phase4b_map.cjs; expected: PASS for syntax, paths, all 29 choices, and warning states.
- [ ] Step 5: Commit review-map files.

### Task 5: Report science, automate refresh, validate, and open PR

**Files:**
- Create: docs/PHASE4B_HISTORICAL_MAP_RECONSTRUCTION.md
- Create: .github/workflows/phase4b-rfc-reconstruction.yml
- Modify: .github/workflows/ci.yml
- Generate: reports/phase4b/summary.json

- [ ] Step 1: Add offline CI and workflow contract tests. The refresh workflow fetches NOAA source, reads cached/versioned NLDI responses, validates outputs, uploads the complete package, and commits generated files only on phase4b/map-basin-reconstruction.
- [ ] Step 2: Run the focused Python and Node tests; expected: FAIL on absent workflow/report assertions.
- [ ] Step 3: Document sources, retrieval dates, hashes, all 543 attributes and relation counts, outcomes for all 29 points, metrics, confidence definitions, unresolved issues, and Phase 4C gates. Inventory the nine workbook filenames, sheets, rows, and hashes retained in Phase 2 JSON metadata; state that original workbook binaries are absent and their mask definitions remain unknown. Do not add an unsupported legacy-equivalence assertion.
- [ ] Step 4: Run full validation:

      python -m compileall -q scripts
      python -m unittest discover -s tests -v
      node tests/validate-ui.cjs
      node tests/test_historical_ui.cjs
      node tests/test_phase4a_map.cjs
      node tests/test_phase4b_map.cjs

Expected: all current and new checks pass. Dispatch the bounded source-refresh workflow on the feature branch. Verify 543 source features, 29 station rows, hashes, unresolved counts, and artifacts before opening the PR.

- [ ] Step 5: Commit final workflow and handoff.
- [ ] Step 6: Push phase4b/map-basin-reconstruction, open a PR to main, provide test/workflow evidence, and leave it unmerged.
