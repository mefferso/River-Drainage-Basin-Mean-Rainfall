# River Drainage Basin Mean Rainfall

Interactive near-real-time **NOAA MRMS MultiSensor QPE Pass 1** analysis for selected upstream river-gage watersheds in the WFO New Orleans/Baton Rouge area.

**Dashboard:** https://mefferso.github.io/River-Drainage-Basin-Mean-Rainfall/ (requires GitHub Pages setup).

## Current capabilities

Choose 6, 12, or 24-hour accumulation and click a gage marker or basin outline. The map shows transparent MRMS QPE shading, selected basin geometry, and these separate calculations:

- **Whole-basin mean:** average of all valid basin pixels **including 0 inches**.
- **Wet-area mean:** average of valid pixels **strictly above 0 inches**. If there are no wet cells, this is unavailable, not zero.
- **Wet fraction:** fraction of valid basin area receiving >0 inches.
- **Valid fraction:** portion of covered basin area with usable MRMS values.
- **Maximum:** maximum valid MRMS grid-cell rainfall.

Both means are weighted by latitude-adjusted pixel area and approximate fractional pixel overlap with the basin polygon (3×3 subpixel sampling). MRMS values are converted from millimeters to inches. Invalid and negative-sentinel pixels are omitted, never counted as dry.

## River-gage outlets in first build

USGS **02489500** (Pearl near Bogalusa), **02492000** (Bogue Chitto near Bush), **07375500** (Tangipahoa at Robert), **07378510** (Amite at 4-H Camp). These are initial gages, *not* a complete LMRFC forecast-point inventory. Check upstream polygons against authoritative watershed maps before operational use. The gage dot represents the *outlet* of its upstream watershed, not a headwaters gage.

## Data and pipeline

- MRMS 6/12/24-hour Pass 1 GRIB2: https://mrms.ncep.noaa.gov/2D/
- USGS NLDI upstream polygon: https://api.water.usgs.gov/docs/nldi/basin/
- Python updater: `scripts/update.py` runs hourly via `.github/workflows/update.yml` (approximately :27 UTC).
- Outputs: `data/latest.json`, `data/basins.geojson`, `data/rain_6h.png`, `data/rain_12h.png`, `data/rain_24h.png`.
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
