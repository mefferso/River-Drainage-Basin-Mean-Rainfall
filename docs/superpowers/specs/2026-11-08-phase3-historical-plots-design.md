# Phase 3 Historical Plots Design

## Intent

Add a static historical analysis section directly under the existing rainfall map. Selecting a verified dashboard USGS gage loads only the approved Phase 2 historical relationships for that NWS forecast point, while the existing MRMS map and controls remain the primary interface.

## Goals

- Plot all eligible Tier B Phase 2 MAP-to-crest and crest-to-crest records for verified mapped forecast points.
- Keep plots descriptive, show source provenance and quality disclosures, and connect chart points to sortable/exportable source rows.
- Preserve existing map selection behavior and work at desktop and mobile sizes.
- Publish data as versioned static JSON with lazy point-file loading.

## Non-goals and anti-goals

- No new event backfill, automated crest detection, or hourly historical append.
- No MRMS-to-legacy MAP substitution, fitted forecast relationship, imputed date/value/unit, inferred crest timestamp, or station-name/nearest-site join.
- No new map markers or edits to rainfall calculations or the update workflows.

## Constraints

- Existing `state.selected` is a USGS site identifier and `select(gid)` coordinates map rendering.
- Only crosswalk rows with `usgs_site_id_confirmed == existing_dashboard_usgs_id == selected gage` authorize a dashboard join.
- `MNLM6` and `CREM6` stay separate; `WTPM6` stays source provenance for canonical `WPTM6`; `KLNM6` cannot inherit the I-10 map location.
- The Phase 2 exports contain 301 MAP-to-crest rows, 365 crest pairs, and 29 forecast-point records; all 666 plotted rows are Tier B and date precision is preserved.

## Approaches

1. **Static JSON plus vanilla SVG (chosen):** deterministic compiler emits one lazy JSON payload per verified point and directional pair. No dependency or third-party chart bundle; adequate for these small collections.
2. **Plotly bundle:** richer built-in interactions but increases page weight and library surface for roughly 20–50 points per relationship.
3. **Pre-rendered charts:** lightweight static images but do not support synchronized selection, sorting, or accessible touch interaction.

## Behavior and implementation calls

- Add a workspace beside the existing sidebar; on mobile, show map then historical analysis, with the sidebar below them.
- Match gage IDs exactly through the crosswalk, fetch point data on selection, cache successful fetches, and ignore stale responses.
- Default to MAP-to-crest when present, else the first directional crest pair. Register pair data at both endpoints without swapping its source X/target Y order.
- Render labeled SVG points with hover/focus details, a sortable accessible table, table/chart row synchronization, relationship selectors, CSV download, and explicit loading/empty/error states.
- Use raw TC/lag only as source text with unverified-unit labeling; nulls remain unavailable.
- Caption Tier B values as historical descriptive only; identify provisional legacy MAP, unverified original stage datum/date semantics, and separation from current MRMS products.

## Left to implementation

- Exact DOM and CSS names, deterministic JSON formatting, and sort implementation.
- Runtime and CI verification of currently available browser/test tooling.
- GitHub branch/PR/merge/deployment completion subject to connected repository permissions and checks.
