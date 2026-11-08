#!/usr/bin/env python3
"""Stage exact archived MRMS Pass 2 hourly QPE for independent MAP calculations.

A narrowly scoped research downloader; never updates the operational dashboard.
MRMS archive keys are checked by UTC valid timestamp. Raw GRIB stays local;
only cropped numeric GeoTIFF and a manifest are emitted.
"""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import pathlib
import re
import tempfile
from datetime import datetime, timedelta, timezone

import boto3
from botocore import UNSIGNED
from botocore.config import Config
import numpy as np
import rasterio
from rasterio.windows import from_bounds, transform as window_transform

from river_stage import time_utc

BUCKET = "noaa-mrms-pds"
PRODUCT = "MultiSensor_QPE_01H_Pass2_00.00"
PREFIX = "CONUS/" + PRODUCT + "/"
BBOX = (-92.0, 29.1, -88.1, 34.2)  # Source repo's LIX coverage


def s3_client():
    return boto3.client("s3", region_name="us-east-1",
                        config=Config(signature_version=UNSIGNED,
                                      connect_timeout=25, read_timeout=90,
                                      retries={"max_attempts": 3, "mode": "standard"}))


def archive_inventory(start, end, client=None):
    if end <= start or (end - start) > timedelta(hours=72):
        raise ValueError("Choose a positive window no greater than 72 hours")
    if start.minute or start.second or end.minute or end.second:
        raise ValueError("Hour-aligned UTC timestamps required")
    client = client or s3_client()
    days = sorted({(start + timedelta(hours=h)).strftime("%Y%m%d")
                   for h in range(int((end-start).total_seconds() // 3600) + 1)})
    available = {}
    pattern = re.compile(r"_(\d{8})-(\d{6})\.grib2\.gz$")
    for day in days:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX + day + "/"):
            for entry in page.get("Contents", []):
                key = entry["Key"]
                match = pattern.search(key)
                if not match:
                    continue
                valid = datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                if start < valid <= end and valid.minute == valid.second == 0:
                    if valid in available:
                        raise ValueError("Duplicate MRMS archive time " + valid.isoformat())
                    available[valid] = {"s3_key": key, "size_bytes": entry.get("Size"),
                                        "source": f"s3://{BUCKET}/{key}"}
    required = [start + timedelta(hours=h+1)
                for h in range(int((end-start).total_seconds() // 3600))]
    missing = [t.isoformat() for t in required if t not in available]
    return {"product": PRODUCT, "bucket": BUCKET,
            "start_utc": start.isoformat(), "end_utc": end.isoformat(),
            "required_hours": len(required), "found_hours": len(required)-len(missing),
            "missing_hours": missing, "entries": [{"valid_end_utc": t.isoformat(), **available[t]}
                                                  for t in required if t in available]}


def download_hour(client, key, output):
    payload = client.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    if len(payload) < 1000:
        raise ValueError("Unexpectedly small compressed MRMS payload")
    with tempfile.NamedTemporaryFile(suffix=".grib2") as f:
        f.write(gzip.decompress(payload))
        f.flush()
        with rasterio.open(f.name) as src:
            if src.crs is None or not src.crs.is_geographic:
                raise ValueError("MRMS GRIB must have geographic CRS")
            win = from_bounds(*BBOX, transform=src.transform).round_offsets().round_lengths()
            win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
            masked = src.read(1, window=win, masked=True)
            arr = np.asarray(masked.filled(np.nan), dtype="float32")
            arr[np.ma.getmaskarray(masked) | ~np.isfinite(arr) | (arr < 0)] = -9999
            transform = window_transform(win, src.transform)
            output.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(output, "w", driver="GTiff", width=arr.shape[1],
                               height=arr.shape[0], count=1, dtype="float32",
                               crs=src.crs, transform=transform, nodata=-9999,
                               compress="deflate") as dst:
                dst.write(arr, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("reconstruction/staging"))
    parser.add_argument("--download", action="store_true", help="Retrieve/convert each source GRIB")
    args = parser.parse_args()
    start, end = time_utc(args.start), time_utc(args.end)
    inventory = archive_inventory(start, end)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out/"archive_inventory.json").write_text(json.dumps(inventory, indent=2)+"\n")
    print(json.dumps({k: inventory[k] for k in ("product","required_hours","found_hours","missing_hours")}, indent=2))
    if inventory["missing_hours"]:
        raise SystemExit("Archive incomplete; refused to stage partial event")
    if args.download:
        client = s3_client()
        with (args.out/"qpe_manifest.csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=["valid_end_utc", "path", "product", "units"])
            writer.writeheader()
            for item in inventory["entries"]:
                at = time_utc(item["valid_end_utc"])
                relative = "rasters/" + at.strftime("%Y%m%d_%H%M%S") + ".tif"
                download_hour(client, item["s3_key"], args.out/relative)
                writer.writerow({"valid_end_utc": item["valid_end_utc"],
                                 "path": relative, "product": PRODUCT, "units": "mm"})
        print(f"Created {len(inventory['entries'])} hourly GeoTIFFs and QPE manifest")


if __name__ == "__main__":
    main()
