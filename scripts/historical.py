#!/usr/bin/env python3
"""One-time Oct 31–Nov 1 2026 MRMS hourly QPE historical experiment.

Local event window: 2026-10-31 00:00 CDT to 2026-11-02 00:00 CST.
This is 49 UTC hours because the November 1 daylight-saving transition repeats 01:00.
Historical 6/12/24-hour totals end at 2026-11-02 06:00 UTC.
"""
from __future__ import annotations

import gzip
import json
import logging
import pathlib
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import boto3
from botocore import UNSIGNED
from botocore.config import Config
import numpy as np
import rasterio
from rasterio.windows import from_bounds, transform as window_transform
from shapely.geometry import shape, mapping

from update import (ROOT, GAGES, BBOX, area_stats, cell_areas,
                    fraction_mask, image, load_basins, build_reaches, atomic_write,
                    WET_THRESHOLDS, DEFAULT_WET_THRESHOLD)

LOG = logging.getLogger("historical")
OUT = ROOT / "historical" / "2026-10-31_2026-11-01"
OUT.mkdir(parents=True, exist_ok=True)
START = datetime(2026, 10, 31, 5, tzinfo=timezone.utc)
END = datetime(2026, 11, 2, 6, tzinfo=timezone.utc)
PRODUCT = "MultiSensor_QPE_01H_Pass2_00.00"
BUCKET = "noaa-mrms-pds"
PREFIX = "CONUS/" + PRODUCT + "/"
S3 = boto3.client("s3", region_name="us-east-1", config=Config(signature_version=UNSIGNED,
                 retries={"max_attempts": 4, "mode": "standard"}, connect_timeout=20, read_timeout=90))

def required_hours():
    n = int((END-START).total_seconds() / 3600)
    return [START + timedelta(hours=i+1) for i in range(n)]

def archive_manifest():
    found = {}
    for day in ("20261031", "20261101", "20261102"):
        paginator = S3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX + day + "/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                match = re.search(r"_(\d{8})-(\d{6})\.grib2\.gz$", key)
                if not match:
                    continue
                stamp = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                if START < stamp <= END and stamp.minute == 0 and stamp.second == 0:
                    found[stamp] = key
    needed = required_hours()
    missing = [d.isoformat() for d in needed if d not in found]
    if missing:
        raise RuntimeError("Archive incomplete; refusing to invent missing MRMS hours: " + ", ".join(missing))
    return [(stamp, found[stamp]) for stamp in needed]

def read_archive_hour(stamp, key):
    payload = S3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tmp:
        tmp.write(gzip.decompress(payload))
        tmp.flush()
        with rasterio.open(tmp.name) as src:
            if src.crs is None or not src.crs.is_geographic:
                raise ValueError("Unexpected archived MRMS grid coordinate system")
            window = from_bounds(*BBOX, transform=src.transform).round_offsets().round_lengths()
            window = window.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            masked = src.read(1, window=window, masked=True)
            transform = window_transform(window, src.transform)
            tagged = src.tags(1).get("GRIB_VALID_TIME") or src.tags().get("GRIB_VALID_TIME")
            if tagged is not None:
                match = re.search(r"\d{9,12}", str(tagged))
                if match:
                    actual = datetime.fromtimestamp(int(match.group()), tz=timezone.utc)
                    if actual != stamp:
                        raise ValueError(f"Archive key time {stamp} conflicts with GRIB valid time {actual}")
    arr = np.asarray(masked.filled(np.nan), dtype="float64")
    arr[~np.isfinite(arr) | (arr < 0)] = np.nan
    arr /= 25.4
    return stamp, arr, transform

def run():
    manifest = archive_manifest()
    LOG.info("Found %s continuous archived Pass 2 hourly QPE files", len(manifest))
    records = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(read_archive_hour, stamp, key): stamp for stamp, key in manifest}
        for future in as_completed(futures):
            stamp, values, transform = future.result()
            records[stamp] = (values, transform)
            LOG.info("Read MRMS %s (%s/%s)", stamp, len(records), len(manifest))
    first = records[manifest[0][0]]
    grid_transform = first[1]
    for stamp, (arr, transform) in records.items():
        if arr.shape != first[0].shape or not np.allclose(tuple(transform), tuple(grid_transform), rtol=0, atol=1e-9):
            raise ValueError(f"Historical MRMS grid geometry changed unexpectedly at {stamp}")
    features, basin_errors = load_basins()
    reaches, reach_errors = build_reaches(features)
    if not features:
        raise RuntimeError("No valid upstream basin polygons")
    atomic_write(OUT / "basins.geojson", json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")))
    reach_features = [{"type": "Feature", "properties": {"id": g["id"], "name": g["name"]},
                       "geometry": mapping(reaches[g["id"]])} for g in GAGES if g["id"] in reaches]
    atomic_write(OUT / "reaches.geojson", json.dumps({"type": "FeatureCollection", "features": reach_features}, separators=(",", ":")))
    g_lookup = {f["properties"]["id"]: shape(f["geometry"]) for f in features}
    weights = cell_areas(grid_transform, *first[0].shape)
    masks = {mode: {gid: fraction_mask(geom, first[0].shape, grid_transform)
                     for gid, geom in geoms.items()}
             for mode, geoms in (("upstream", g_lookup), ("incremental", reaches))}
    accumulated = {}
    expected_counts = {"event": len(manifest), "6": 6, "12": 12, "24": 24}
    for key, count in expected_counts.items():
        subset = [records[t][0] for t, _ in manifest[-count:]]
        cube = np.stack(subset)
        complete = np.all(np.isfinite(cube), axis=0)
        values = np.where(complete, np.sum(np.where(np.isfinite(cube), cube, 0), axis=0), np.nan)
        accumulated[key] = values
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "product": "NOAA MRMS MultiSensor QPE 01H Pass 2 (archived hourly sums)",
        "historical": True, "event_start_utc": START.isoformat(), "event_end_utc": END.isoformat(),
        "hours_in_event": len(manifest), "wet_threshold_inches": DEFAULT_WET_THRESHOLD,
        "wet_threshold_options_inches": WET_THRESHOLDS,
        "gages": GAGES, "basin_errors": basin_errors, "reach_errors": reach_errors, "periods": {}
    }
    for key, values in accumulated.items():
        image_path = "historical/2026-10-31_2026-11-01/rain_" + key + "h.png"
        image(values, ROOT / image_path)
        period = {
            "valid_at": END.isoformat().replace("+00:00", "Z"),
            "image": image_path,
            "hours": expected_counts[key],
            "bounds": [[grid_transform.f + grid_transform.e * values.shape[0], grid_transform.c],
                       [grid_transform.f, grid_transform.c + grid_transform.a * values.shape[1]]],
            "basins": {gid: area_stats(values, mask, weights) for gid, mask in masks["upstream"].items()},
            "incremental": {gid: area_stats(values, mask, weights) for gid, mask in masks["incremental"].items()}
        }
        result["periods"][key] = period
        LOG.info("Computed %s-hour historical accumulation", period["hours"])
    atomic_write(OUT / "latest.json", json.dumps(result, separators=(",", ":"), allow_nan=False))
    return result

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
