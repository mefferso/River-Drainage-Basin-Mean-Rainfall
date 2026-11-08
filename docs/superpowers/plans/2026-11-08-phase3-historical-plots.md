# Phase 3 Historical Plots Implementation Plan

> **For agentic workers:** execute this plan task-by-task with the test-first workflow. Keep each data transformation deterministic and each visible measurement traceable to its Phase 2 `record_id`.

**Goal:** Add interactive, descriptive Tier B MAP-to-crest and crest-to-crest plots beneath the existing rainfall map, using verified crosswalks and the attached Phase 2 observations.

**Architecture:** Preserve the current USGS-ID Leaflet selection state. A deterministic Python build script validates the three Phase 2 JSON sources and emits an exact verified USGS-to-NWSLI lookup, a manifest, and lazy per-point JSON files. A small browser-side SVG plot and sortable event table consume these files without a chart dependency or any MRMS data coupling.

**Tech Stack:** Python 3 standard library, static JSON, vanilla browser JavaScript/SVG, existing Leaflet app, existing Python `unittest` and Node checks.

**Spec:** `docs/superpowers/specs/2026-11-08-phase3-historical-plots-design.md`

## Global Constraints

- Plot only Tier B records from the Phase 2 exports; preserve source values, record IDs, date precision, and provenance.
- Never equate legacy MAP with MRMS Pass 1 or Pass 2; never infer stage timestamps, TC units, lag units, or routing.
- Join a selected dashboard gage only when Phase 2 confirmed and dashboard USGS IDs match exactly.
- Keep `MNLM6` and `CREM6` separate; preserve `WTPM6` as source spelling while resolving canonical `WPTM6`; do not map `KLNM6` to 02481667.
- Preserve existing MRMS calculations, selectors, layers, geometry, and update workflows.
- Do not add dependencies, forecast fits, generated observations, or unverified gage markers.

## Review Focus

- Competing stations sharing a similar name (`MNLM6`/`CREM6`) remain separate: contract test checks gage IDs and per-point record IDs.
- Alias and unsafe joins (`WTPM6`, `KLNM6`) remain provenance-safe and fail closed: crosswalk tests assert exact matching.
- Directional pair axes do not reverse for downstream selection: payload/UI tests assert source X and target Y for `OSYM6__KENL1`, `CLMM6__BXAL1`, and `FLSL1__CUSL1`.
- Unknown numeric/timing values do not become zero or normalized units: contract test verifies nulls and finite coordinates only.
- Rapid changes and MRMS dataset reloads retain the final selected USGS point: UI tests exercise selection token and stable selection.

---

### Task 1: Phase 2 data validator and compiler

**Files:**
- Create: `scripts/build_historical_site_data.py`
- Create: `tests/test_historical_contract.py`
- Create: `historical/relationships/v1/` generated JSON outputs

**Interfaces:**
- `build(source_dir: Path, output_dir: Path) -> dict` validates all source records and writes manifest, crosswalk, and point payload files.
- CLI defaults to the attached files copied into `historical/relationships/v1/source/` and writes deterministic outputs under `historical/relationships/v1/`.

- [ ] Write failing tests for source counts (301/365/29), unique IDs, finite coordinates, exact crosswalk joins, pilot counts (AMIL1 23, CREM6 34, OSYM6→KENL1 34), and special station rules.
- [ ] Run the contract test and confirm failures are due to the missing compiler/outputs.
- [ ] Implement validation and deterministic per-point compilation, indexing each pair at both endpoints while retaining fixed source/target fields.
- [ ] Run contract tests; verify generated totals and data hashes.

### Task 2: Historical browser analysis section

**Files:**
- Create: `historical-ui.js`
- Modify: `index.html`
- Create: `tests/test_historical_ui.cjs`

**Interfaces:**
- `HistoricalUI.create({document, fetch, crosswalkUrl, pointsUrl, onSelection})` initializes event handlers and returns `renderForGage(usgsId)` plus `refresh()`.
- Per-point payloads use `schema_version`, `nws_point_id`, `map_events`, and `crest_relationships` from the compiler.

- [ ] Write failing DOM/syntax tests for verified selection, empty mapping, relationship switching, table sort/export, synchronized point selection, and asynchronous stale-response handling.
- [ ] Run tests and observe expected failures.
- [ ] Implement responsive workspace layout, verified lazy loading/cache, SVG scatterplots, event tables, CSV export, accessible status, and conservative science labels.
- [ ] Run UI tests and existing checks; manually inspect desktop/mobile render if browser runtime is available.

### Task 3: Documentation and release handoff

**Files:**
- Modify: `README.md`
- Create: `historical/relationships/v1/README.md`
- Create: `docs/PHASE3_HANDOFF.md`

- [ ] Document Phase 2 provenance, Tier B rules, exact crosswalk behavior, unresolved science, generated-data refresh, and tests.
- [ ] Record actual build counts, map-supported points, pilot validations, technical entry points, and remaining uncertainties in the handoff.
- [ ] Run the full test suite and build compiler from a clean state; confirm working tree diff and generated data consistency.

### Task 4: GitHub review and deployment

**Files:**
- Feature branch: `phase3/historical-relationships`
- Pull request into `main`

- [ ] Publish the reviewed commit and create a PR describing data lineage and scientific safeguards.
- [ ] Wait for CI and deployment checks; fix failures without weakening tests.
- [ ] Merge only when branch protections and checks permit; confirm the Pages deploy and the published manifest/UI are reachable.
