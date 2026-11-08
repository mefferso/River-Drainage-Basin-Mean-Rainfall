# River Drainage Basin Mean Rainfall

Interactive near-real-time **NOAA MRMS MultiSensor QPE Pass 1** analysis for selected LIX river-forecast gage catchments in the WFO New Orleans/Baton Rouge area.

**Dashboard:** https://mefferso.github.io/River-Drainage-Basin-Mean-Rainfall/ (requires GitHub Pages setup).

## Current capabilities

Choose 6, 12, or 24-hour accumulation and click a gage marker or basin outline. Change the wet-area threshold to instantly recalculate the reported wet fraction and wet-area mean from precomputed per-threshold values; the shaded MRMS map retains its CREST-matched 0.10-inch display cutoff. Switch between **full upstream watersheds** (cumulative contributing area) and **incremental reaches** (full watershed minus explicitly linked upstream forecast-point watersheds). The map defaults to the incremental geometry, which avoids overlapping nested basins and excludes rainfall downstream of the chosen forecast point. The map shows transparent MRMS QPE shading, selected basin geometry, and these separate calculations:

- **Whole-basin mean:** average of all valid basin pixels **including 0 inches**.
- **Wet-area mean:** average of valid pixels with accumulation **≥ the selected threshold**, default **0.10 inches** (options: 0.01, 0.10, 0.25, 0.50, 1.00 inches). If no cells qualify, this is unavailable, not zero.
- **Wet fraction:** fraction of valid basin area receiving rainfall **≥ the selected threshold**. Grid cells below the threshold still count toward the whole-basin mean; missing cells do not.
- **Valid fraction:** portion of covered basin area with usable MRMS values.
- **Maximum:** maximum valid MRMS grid-cell rainfall.

Both means are weighted by latitude-adjusted pixel area and approximate fractional pixel overlap with the basin polygon (3×3 subpixel sampling). MRMS values are converted from millimeters to inches. Invalid and negative-sentinel pixels are omitted, never counted as dry.

## Forecast-gage inventory and hydrologic boundaries

The initial expansion includes **26 USGS river-gage sites**, cross-checked against LIX River Statement forecast-point names and USGS location records. See `config/gages.json` for exact IDs and the explicit `upstream_from` relationships used to derive incremental reaches. Included networks are Pearl, Bogue Chitto, Tangipahoa, Tickfaw, Natalbany, Tchefuncte, Bogue Falaya, Amite, West/East Hobolochitto, Biloxi, Wolf, Jourdan, Tchoutacabouffa, Escatawpa and Pascagoula.

This is **not a complete LIX-CWA forecast-point crosswalk** yet: additional Amite/Comite, selected Mississippi coastal tributary, and non-USGS gage forecast points require their NWPS IDs and authoritative outlet delineations before inclusion. We intentionally do not substitute an arbitrary nearby USGS station for a known forecast point. Upstream outlet polygons come from USGS NLDI; each incremental reach is computed by subtracting immediate upstream outlet watersheds. If an upstream polygon is unavailable, its incremental reach is marked unavailable rather than silently using the entire watershed. Upstream watershed boundaries are not the same as LMRFC computational subbasins and need operational validation.

## Historical test: October 31–November 1, 2026

Switch the **Dataset** dropdown to the historical event. Its standalone script `scripts/historical.py` uses the public NOAA MRMS AWS archive `s3://noaa-mrms-pds/CONUS/MultiSensor_QPE_01H_Pass2_00.00/YYYYMMDD/`. It reconstructs 49 complete hourly gridded Pass 2 QPE intervals over **2026-10-31 00:00 CDT to 2026-11-02 00:00 CST**, accounting for the November 1 fall-back hour. The output includes a **49-hour event total** and the final 6/12/24-hour accumulations ending November 2 at 06Z, not an arbitrary single daytime frame.

The historical job is one-time via `.github/workflows/historical.yml` (on first merge/push of the script, or manual dispatch). It strictly fails if any archive hour is absent, checks raster grids align and excludes any cell missing data in even one contributing hour. It does **not** mix Pass 2 historical QPE with near-real-time Pass 1. Historical outputs and basin polygons live in `historical/2026-10-31_2026-11-01/`; current-hour statistics live in `data/`. Neither overwrites the other.

Historical output availability must be confirmed from successful workflow logs and committed artifacts; inclusion of the workflow alone does not imply the event was processed.

## Historical rainfall-to-crest relationships

The map now includes a historical analysis section immediately below it. Selecting a map gage loads approved historical relationships independently of the Dataset, accumulation-period, basin-area, and wet-threshold controls. MAP-to-crest records show the legacy study MAP against the source-reported crest; directional crest pairs preserve the Phase 2 source endpoint on X and target endpoint on Y. Each plotted point links to its original record ID and workbook/sheet/row reference. The table sorts by date and numeric fields and can be downloaded as CSV.

The published Phase 2 package includes 301 Tier B MAP-to-crest source records, 365 Tier B crest pairs across 12 relationships, and 29 forecast-point crosswalk entries. Eighteen crosswalks match a configured dashboard USGS gage exactly. Of those, 15 forecast points have at least one published historical relationship. The mapped plot points are AMIL1, BXAL1, CREM6, CUSL1, DENL1, DIBM6, FLSL1, HOLL1, KENL1, LNDM6, LPOL1, MNLM6, MONL1, OSYM6, and ROBL1. The site publishes 240 MAP rows attached to verified current map points and all 365 paired crests. The 61 remaining MAP rows (54 GLFM6 and 7 KLNM6) remain in the source export but are not attached to current map markers: GLFM6 has no existing dashboard marker and its geometry needs review; KLNM6 is not the dashboard's Jourdan gage at USGS 02481667.

All displayed observations are **Tier B historical descriptive records**, not verified or calibrated forecast inputs. Legacy RFC MAP is not interchangeable with modern MRMS whole-basin or wet-area rainfall. Date labels are not guaranteed to be crest dates; original stage datums, MAP method, rainfall periods, TC clock, and some lag units remain unresolved. No fitted equation, interpolation, or operational stage forecast is displayed. `MNLM6` (West Hobolochitto) and `CREM6` (East Hobolochitto) remain distinct. Source spelling `WTPM6` is preserved in pair provenance while the canonical station ID is `WPTM6`.

Versioned source exports, crosswalk subset, manifest, and per-point payloads are under `historical/relationships/v1/`. To refresh these files after a reviewed Phase 2 update, replace the three source JSONs in `historical/relationships/v1/source/`, update the reviewed expected counts in `scripts/build_historical_site_data.py` when the baseline changes, then run:

```sh
python scripts/build_historical_site_data.py
python -m unittest discover -s tests -v
node tests/test_historical_ui.cjs
```

Review `docs/historical_methodology.md`, `docs/historical_quality_control.md`, and `docs/PHASE3_HANDOFF.md` before extending the plotted records. New stations require an authoritative same-outlet mapping and reviewed geometry; matching names or nearby coordinates are insufficient.

## Data and pipeline

- MRMS 6/12/24-hour Pass 1 GRIB2: https://mrms.ncep.noaa.gov/2D/
- USGS NLDI upstream polygon: https://api.water.usgs.gov/docs/nldi/basin/
- Python updater: `scripts/update.py` runs hourly via `.github/workflows/update.yml` (approximately :27 UTC).
- Outputs: `data/latest.json`, `data/basins.geojson`, `data/reaches.geojson`, `data/rain_6h.png`, `data/rain_12h.png`, `data/rain_24h.png`.
- Static Leaflet dashboard: `index.html`, compatible with GitHub Pages.

### First-time setup

1. In GitHub repository **Settings → Actions → General**, ensure Actions are enabled and workflows have read/write repository permission.
2. In **Settings → Pages**, select **GitHub Actions** as the publishing source (the deployment workflow publishes the site).
3. Run **Actions → Update MRMS basin rainfall → Run workflow** to initialize the published data. Check the run logs and confirm basin polygons and products before relying on statistics.

Local use: `pip install -r requirements.txt`, `python scripts/update.py`, `python -m http.server 8000`.

MRMS valid time, not local computation time, is displayed; stale data (>2.5 h old) is flagged. A failed dataset is not silently replaced by zero. If all three MRMS updates fail, the previous published dataset is retained.

### Scientific caution

Wet-area mean measures precipitation concentration, **not equivalent basin-wide water volume**. It is *not* a replacement input for an RFC rainfall-runoff model or a river-stage forecast. This tool does not produce flood forecasts or stage predictions. NLDI uses NHDPlusV2 topology and does not necessarily capture diversions or tidal influences. The dashboard is experimental until a successful live update and basin boundary validation are confirmed.

References: [NSSL MRMS operational products](https://www.nssl.noaa.gov/projects/mrms/operational/tables.php), [USGS NLDI basin API](https://api.water.usgs.gov/docs/nldi/basin/).
