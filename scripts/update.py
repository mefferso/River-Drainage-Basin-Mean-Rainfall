#!/usr/bin/env python3
"""Hourly MRMS Pass 1 QPE basin analysis. Fail closed on missing geometry or rainfall."""
from __future__ import annotations
import gzip
import io
import json
import logging
import math
import os
import pathlib
import re
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.windows import from_bounds, transform as window_transform
from PIL import Image
import requests
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
GAGES = json.loads((ROOT / "config/gages.json").read_text())
PERIODS = (6, 12, 24)
WET_THRESHOLDS = (0.01, 0.10, 0.25, 0.50, 1.00)
DEFAULT_WET_THRESHOLD = 0.10
# Moderate display bounds cover most of WFO LIX including northern headwaters.
BBOX = (-92.0, 29.1, -88.1, 34.2)  # west, south, east, north
BASE = "https://mrms.ncep.noaa.gov/2D/"
NLDI = "https://api.water.usgs.gov/nldi/linked-data/nwissite/USGS-"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "LIX-basin-mean-rainfall/1.0 (research dashboard)"
LOG = logging.getLogger(__name__)

def atomic_write(path: pathlib.Path, contents: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as f:
        f.write(contents)
        tmp = f.name
    os.replace(tmp, path)

def load_basins():
    """Retain last verified polygon when NLDI is temporarily unavailable."""
    path = DATA / "basins.geojson"
    existing = {}
    if path.exists():
        try:
            existing = {x["properties"]["id"]: x for x in json.loads(path.read_text())["features"]}
        except (KeyError, ValueError, TypeError):
            LOG.warning("Existing basin GeoJSON unreadable")
    features, errors = [], {}
    for gage in GAGES:
        gid = gage["id"]
        try:
            url = NLDI + quote(gid) + "/basin?f=json&splitCatchment=true"
            response = SESSION.get(url, timeout=35)
            if not response.ok:
                LOG.warning("Split-catchment request failed for %s; trying standard NLDI upstream basin", gid)
                response = SESSION.get(NLDI + quote(gid) + "/basin?f=json", timeout=35)
            response.raise_for_status()
            raw = response.json()
            items = raw.get("features", [])
            if not items:
                raise ValueError("NLDI returned no basin polygon")
            geom = shape(items[0]["geometry"])
            if geom.is_empty or not geom.is_valid or geom.area <= 0:
                raise ValueError("NLDI polygon was empty or invalid")
            feature = {"type": "Feature", "properties": {"id": gid, "name": gage["name"]}, "geometry": mapping(geom)}
            existing[gid] = feature
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            errors[gid] = str(exc)
            LOG.warning("NLDI %s: %s", gid, exc)
        if gid in existing:
            features.append(existing[gid])
    collection = {"type": "FeatureCollection", "features": features}
    if features:
        atomic_write(path, json.dumps(collection, separators=(",", ":")))
    return features, errors

def build_reaches(features, gages=GAGES):
    """Incremental contributing polygons: downstream upstream-basin minus immediate upstream outlets.
    Missing upstream delineation is never silently treated as rainfall-free land.
    """
    lookup = {f['properties']['id']: shape(f['geometry']) for f in features}
    reaches, errors = {}, {}
    for g in gages:
        gid = g['id']
        if gid not in lookup:
            errors[gid] = 'No delineated contributing watershed'
            continue
        parents = g.get('upstream_from', [])
        missing = [p for p in parents if p not in lookup]
        if missing:
            errors[gid] = 'Missing required upstream watershed: ' + ', '.join(missing)
            continue
        geom = lookup[gid]
        try:
            reach = geom.difference(unary_union([lookup[p] for p in parents])) if parents else geom
            if reach.is_empty or not reach.is_valid or reach.area <= 0:
                raise ValueError('Empty or invalid incremental reach')
            reaches[gid] = reach
        except (ValueError, Exception) as exc:
            errors[gid] = str(exc)
    return reaches, errors

def fetch_grid(hours: int):
    product = f"MultiSensor_QPE_{hours:02d}H_Pass1"
    url = f"{BASE}{product}/MRMS_{product}.latest.grib2.gz"
    resp = SESSION.get(url, timeout=120)
    resp.raise_for_status()
    if len(resp.content) < 1000:
        raise ValueError("MRMS response unexpectedly small")
    with tempfile.NamedTemporaryFile(suffix=".grib2") as f:
        f.write(gzip.decompress(resp.content))
        f.flush()
        with rasterio.open(f.name) as src:
            if src.crs is None:
                raise ValueError("MRMS GRIB missing coordinate reference system")
            if not src.crs.is_geographic:
                raise ValueError(f"Unexpected MRMS CRS: {src.crs}")
            window = from_bounds(*BBOX, transform=src.transform).round_offsets().round_lengths()
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            values = src.read(1, window=window, masked=True)
            transform = window_transform(window, src.transform)
            tags = src.tags(1)
            all_tags = src.tags()
            # GRIB_VALID_TIME is epoch seconds when supported by GDAL.
            stamp = tags.get("GRIB_VALID_TIME") or all_tags.get("GRIB_VALID_TIME")
            if stamp is None:
                raise ValueError("GRIB_VALID_TIME missing; refuse to label an unknown grid current")
            match = re.search(r"\d{9,12}", str(stamp))
            if not match:
                raise ValueError(f"Unrecognized GRIB_VALID_TIME: {stamp}")
            valid_at = datetime.fromtimestamp(int(match.group()), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    a = np.asarray(values.filled(np.nan), dtype="float64")
    a = np.where(np.ma.getmaskarray(values), np.nan, a)
    # MRMS quantities are mm. Negative sentinels are invalid, not zero.
    a[~np.isfinite(a) | (a < 0)] = np.nan
    a /= 25.4
    return a, transform, valid_at

def cell_areas(transform, height, width):
    """Spherical latitude-adjusted cell areas, square meters, for geographic raster."""
    radius = 6371008.8
    dlon = math.radians(abs(transform.a))
    ys = transform.f + (np.arange(height) + 0.5) * transform.e
    half = math.radians(abs(transform.e)) / 2
    lat = np.radians(ys)
    row_area = radius**2 * dlon * np.abs(np.sin(lat + half) - np.sin(lat - half))
    return np.broadcast_to(row_area[:, None], (height, width))

def area_stats(values, fractional, areas, wet_threshold=DEFAULT_WET_THRESHOLD):
    """Area-weighted QPE statistics; ≥ thresholds are inclusive.

    Whole-basin means include valid zero-precipitation pixels regardless of
    threshold. Missing raster values are never interpreted as dry pixels.
    """
    weights = fractional * areas
    valid = np.isfinite(values) & (weights > 0)
    valid_area = float(weights[valid].sum())
    selected_area = float(weights.sum())
    threshold_stats = {}
    for threshold in WET_THRESHOLDS:
        key = f"{threshold:.2f}"
        wet = valid & (values >= threshold)
        wet_area = float(weights[wet].sum())
        threshold_stats[key] = {
            "wet_mean": float(np.sum(values[wet] * weights[wet]) / wet_area) if wet_area else None,
            "wet_fraction": wet_area / valid_area if valid_area else None,
        }
    key = f"{wet_threshold:.2f}"
    if key not in threshold_stats:
        raise ValueError(f"Unsupported wet-area rainfall threshold: {wet_threshold}")
    selected = threshold_stats[key]
    return dict(
        whole_mean=float(np.sum(values[valid] * weights[valid]) / valid_area) if valid_area else None,
        wet_mean=selected["wet_mean"],
        wet_fraction=selected["wet_fraction"],
        wet_thresholds=threshold_stats,
        valid_fraction=valid_area / selected_area if selected_area else 0.0,
        max_inches=float(np.max(values[valid])) if valid_area else None,
        valid_cells=int(np.count_nonzero(valid)),
    )

def fraction_mask(geometry, out_shape, transform, factor=3):
    """Approximate fractional pixel overlap with 3x supersampling, including edge pixels."""
    high_shape = (out_shape[0] * factor, out_shape[1] * factor)
    from affine import Affine
    high_transform = transform * Affine.scale(1/factor, 1/factor)
    hi = rasterize([(geometry, 1)], out_shape=high_shape, transform=high_transform,
                   fill=0, dtype="uint8")
    return hi.reshape(out_shape[0], factor, out_shape[1], factor).mean(axis=(1, 3))

def image(values, path: pathlib.Path):
    """Render native MRMS grid pixels with the exact Bogue Chitto CREST palette.

    No interpolation, resampling, convolution or smoothing is performed.
    Display cutoff at 0.10 inches does not affect rainfall statistics.
    Pixels are opaque here; Leaflet applies the same 85% layer opacity as CREST.
    """
    bounds = [0.0, 0.10, 0.25, 0.50, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0]
    colors = [(161,170,181), (153,220,224), (82,199,209), (54,173,100),
              (198,204,50), (242,174,50), (246,108,61), (219,48,123),
              (153,39,168), (86,34,170)]
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    visible = np.isfinite(values) & (values >= 0.10)
    idx = np.clip(np.searchsorted(bounds, values[visible], side="right") - 1, 0, len(colors) - 1)
    rgba[visible, :3] = np.asarray(colors, dtype=np.uint8)[idx]
    rgba[visible, 3] = 255
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(path, optimize=True)

def run():
    features, basin_errors = load_basins()
    basin_lookup = {x["properties"]["id"]: shape(x["geometry"]) for x in features}
    reaches, reach_errors = build_reaches(features)
    reach_features = [{"type": "Feature",
                       "properties": {"id": gid, "name": next(g["name"] for g in GAGES if g["id"] == gid)},
                       "geometry": mapping(poly)} for gid, poly in reaches.items()]
    if reach_features:
        atomic_write(DATA / "reaches.geojson", json.dumps(
            {"type": "FeatureCollection", "features": reach_features}, separators=(",", ":")))
    result = {"generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "product": "MRMS MultiSensor QPE Pass 1", "wet_threshold_inches": DEFAULT_WET_THRESHOLD, "wet_threshold_options_inches": WET_THRESHOLDS,
              "gages": GAGES, "periods": {}, "basin_errors": basin_errors, "reach_errors": reach_errors}
    successful = 0
    for hours in PERIODS:
        try:
            values, transform, valid_at = fetch_grid(hours)
            areas = cell_areas(transform, *values.shape)
            entries = {'upstream': {}, 'incremental': {}}
            for mode, geometries in (('upstream', basin_lookup), ('incremental', reaches)):
                for gid, poly in geometries.items():
                    fractions = fraction_mask(poly, values.shape, transform)
                    entries[mode][gid] = area_stats(values, fractions, areas)
            png = f"data/rain_{hours}h.png"
            image(values, ROOT / png)
            result["periods"][str(hours)] = {
                "valid_at": valid_at, "image": png, "bounds": [
                    [transform.f + transform.e * values.shape[0], transform.c],
                    [transform.f, transform.c + transform.a * values.shape[1]]
                ], "basins": entries['upstream'], "incremental": entries['incremental']}
            successful += 1
            LOG.info("%sh QPE %s: %s basins", hours, valid_at, len(entries))
        except Exception as exc:
            LOG.exception("MRMS %sh failed", hours)
            result["periods"][str(hours)] = {"error": str(exc)}
    # Do not overwrite an existing good dashboard with all periods failed.
    if successful == 0:
        raise RuntimeError("All MRMS periods failed; retaining last published data")
    atomic_write(DATA / "latest.json", json.dumps(result, separators=(",", ":"), allow_nan=False))
    return result

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
