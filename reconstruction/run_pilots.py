#!/usr/bin/env python3
"""Strict, opt-in, event-based full-upstream-basin hourly MAP reconstruction.

No network downloads or automatic event inference. Fails closed for incomplete
or mixed-product QPE. Output remains separate from legacy plots.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import numpy as np
import rasterio
from shapely.geometry import shape, box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from update import area_stats, cell_areas, fraction_mask  # noqa: E402

PILOTS = {"AMIL1": "07375430", "MNLM6": "02492360"}
HOUR = timedelta(hours=1)


def timestamp(raw):
    if not raw or not raw.strip():
        raise ValueError("Timestamp required")
    t = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required: " + raw)
    t = t.astimezone(timezone.utc)
    if t.minute or t.second or t.microsecond:
        raise ValueError("QPE/event time must align to whole UTC hour: " + raw)
    return t


def crest_timestamp(raw):
    if not raw or not raw.strip():
        raise ValueError("Crest timestamp required")
    t = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("Timezone-aware crest timestamp required")
    return t.astimezone(timezone.utc)


def read_csv(path, required):
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not set(required).issubset(reader.fieldnames or []):
            raise ValueError(f"{path}: missing columns {sorted(set(required)-set(reader.fieldnames or []))}")
        return list(reader)


def hourly_ends(start, end):
    if start >= end or (end-start).total_seconds() % 3600:
        raise ValueError("Event must have a positive whole-hour window")
    if (end-start) > timedelta(days=30):
        raise ValueError("Event exceeds 30-day safety limit")
    out = []
    t = start + HOUR
    while t <= end:
        out.append(t)
        t += HOUR
    return out


def load_upstream_basins(path):
    geo = json.loads(Path(path).read_text(encoding="utf-8"))
    if geo.get("type") != "FeatureCollection":
        raise ValueError("Expected GeoJSON FeatureCollection")
    basins = {}
    for f in geo.get("features", []):
        site = str(f.get("properties", {}).get("id", ""))
        if site in PILOTS.values():
            geom = shape(f["geometry"])
            if geom.is_empty or not geom.is_valid or geom.area <= 0:
                raise ValueError("Invalid upstream polygon " + site)
            if site in basins:
                raise ValueError("Duplicate upstream polygon " + site)
            basins[site] = geom
    return basins


def index_manifest(path):
    rows = read_csv(path, ("valid_end_utc", "path", "product", "units"))
    inventory = {}
    for row in rows:
        t = timestamp(row["valid_end_utc"])
        if t in inventory:
            raise ValueError("Duplicate hourly raster time " + t.isoformat())
        if row["units"] not in ("mm", "in"):
            raise ValueError("QPE units must be mm or in")
        if not row["product"].strip():
            raise ValueError("Explicit QPE product required")
        raster_path = Path(row["path"])
        if not raster_path.is_absolute():
            raster_path = Path(path).resolve().parent / raster_path
        inventory[t] = (raster_path, row["product"].strip(), row["units"])
    return inventory


def calculate_map(basin, required, inventory):
    missing = [t.isoformat() for t in required if t not in inventory]
    if missing:
        raise ValueError("Missing required QPE hours: " + ", ".join(missing[:8]))
    products = {(inventory[t][1], inventory[t][2]) for t in required}
    if len(products) != 1:
        raise ValueError("Mixed QPE products/units inside one event")
    product, units = next(iter(products))
    transform0 = None
    shape0 = None
    cumulative = None
    for t in required:
        p = inventory[t][0]
        with rasterio.open(p) as src:
            if src.crs is None or not src.crs.is_geographic:
                raise ValueError(f"{p}: expected geographic CRS")
            values = src.read(1, masked=True)
            arr = np.asarray(values.filled(np.nan), dtype="float64")
            arr[np.ma.getmaskarray(values)] = np.nan
            arr[(~np.isfinite(arr)) | (arr < 0)] = np.nan
            if units == "mm":
                arr = arr / 25.4
            if transform0 is None:
                transform0, shape0 = src.transform, arr.shape
                raster_footprint = box(*src.bounds)
                if not raster_footprint.buffer(1e-9).covers(basin):
                    raise ValueError("QPE raster does not cover entire upstream basin")
                fractions = fraction_mask(basin, shape0, transform0)
                areas = cell_areas(transform0, *shape0)
                if float((fractions * areas).sum()) <= 0:
                    raise ValueError("Basin does not overlap QPE grid")
                cumulative = np.zeros(shape0, dtype="float64")
            elif arr.shape != shape0 or not np.allclose(tuple(src.transform), tuple(transform0), atol=1e-9, rtol=0):
                raise ValueError("QPE grids have different geometry")
            # Do not allow missing precipitation within contributing basin.
            if np.any((fractions > 0) & ~np.isfinite(arr)):
                raise ValueError(f"Missing basin QPE pixels at {t.isoformat()}")
            cumulative += np.where(np.isfinite(arr), arr, 0)
    stats = area_stats(cumulative, fractions, areas)
    if not math.isfinite(stats["whole_mean"]) or stats["valid_fraction"] < 0.999999:
        raise ValueError("Incomplete basin QPE coverage")
    return stats["whole_mean"], product


def reconstruct(manifest_path, events_path, basins_path):
    inventory = index_manifest(manifest_path)
    basins = load_upstream_basins(basins_path)
    events = read_csv(events_path, ("event_id", "nwsli", "rain_start_utc", "rain_end_utc", "crest_time_utc", "crest_ft"))
    output, seen = [], set()
    for event in events:
        ident, nwsli = event["event_id"].strip(), event["nwsli"].strip()
        if not ident or ident in seen:
            raise ValueError("Event IDs must be nonempty and unique")
        seen.add(ident)
        if nwsli not in PILOTS:
            raise ValueError("Unsupported pilot forecast point " + nwsli)
        if PILOTS[nwsli] not in basins:
            raise ValueError("Missing full upstream basin for " + nwsli)
        start, end = timestamp(event["rain_start_utc"]), timestamp(event["rain_end_utc"])
        crest_at = crest_timestamp(event["crest_time_utc"])
        if crest_at < start:
            raise ValueError("Crest precedes event rainfall start")
        crest = float(event["crest_ft"])
        if not math.isfinite(crest):
            raise ValueError("Invalid crest stage")
        hours = hourly_ends(start, end)
        map_in, product = calculate_map(basins[PILOTS[nwsli]], hours, inventory)
        output.append({
            "event_id": ident, "nwsli": nwsli, "usgs_site_id": PILOTS[nwsli],
            "rain_start_utc": start.isoformat(), "rain_end_utc": end.isoformat(),
            "crest_time_utc": crest_at.isoformat(), "crest_feet": crest,
            "map_inches": round(map_in, 5), "qpe_product": product,
            "qpe_hour_count": len(hours), "basin_type": "full_upstream_NLDI",
            "rain_window_basis": "explicit_observation_review",
            "crest_basis": "provided_observed_crest_requires_source_review",
            "validation_status": "PROVISIONAL_NOT_SCIENCE_APPROVED",
            "source_class": "independent_reconstruction",
        })
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True)
    p.add_argument("--events", required=True)
    p.add_argument("--basins", default=str(ROOT / "data/basins.geojson"))
    p.add_argument("--output", default=str(ROOT / "reconstruction/results/pilot_events.json"))
    a = p.parse_args()
    result = reconstruct(a.manifest, a.events, a.basins)
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"schema_version": 1, "status": "PROVISIONAL", "events": result}, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(result)} provisional independent events: {out}")


if __name__ == "__main__":
    main()
