#!/usr/bin/env python3
"""Bounded Stage IV 24h basin MAP audit, kept separate from hourly event MAP.

Reads official dated NOAA tar/GRIB; checks APCP/units/24-hour accumulation,
intersects native polar stereographic pixels with transformed NLDI polygons,
and weights precipitation by *geodesic* intersected area. No interpolated daily
data are converted to six-hour rainfall and no crest match is declared.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
import math
import tarfile
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import Geod, Transformer
from shapely.geometry import box
from shapely.ops import transform as transform_geom
try:
    from .run_pilots import PILOTS, load_upstream_basins
except ImportError:
    from run_pilots import PILOTS, load_upstream_basins

URL = "https://water.noaa.gov/resources/downloads/precip/stageIV/{date:%Y/%m/%d}/ncep_stage_iv_source_files_{date:%Y%m%d}.tar"
MAX_ARCHIVE_BYTES = 12_000_000
MAX_MEMBER_BYTES = 10_000_000
GEOD = Geod(ellps="WGS84")
ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DATES = ("2016-03-12", "2018-12-28", "2019-05-12")


def read_noaa_daily(day, session=None):
    """Return byte-addressed official native GRIB, with no trusted filename timing."""
    date = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    url = URL.format(date=date)
    sess = session or requests.Session()
    response = sess.get(url, timeout=60, headers={
        "User-Agent": "River-Basin-Mean-Rainfall historical independent QPE audit"
    })
    response.raise_for_status()
    raw_archive = response.content
    if not 0 < len(raw_archive) <= MAX_ARCHIVE_BYTES:
        raise ValueError("Archive outside bounded size")
    with tarfile.open(fileobj=io.BytesIO(raw_archive), mode="r:*") as archive:
        members = [m for m in archive.getmembers() if m.isfile()
                   and m.name.split("/")[-1] in
                   (f"conus_{date:%Y%m%d}_24h.grb.gz",
                    f"conus_{date:%Y%m%d}_24h.grb2.gz")]
        if len(members) != 1:
            raise ValueError("Expected one exact dated CONUS daily GRIB")
        member = members[0]
        if not 0 < member.size <= MAX_MEMBER_BYTES:
            raise ValueError("Unacceptable archive member size")
        compressed = archive.extractfile(member).read(MAX_MEMBER_BYTES + 1)
        if len(compressed) != member.size:
            raise ValueError("Archive member size mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as fh:
        grib = fh.read(30_000_000 + 1)
    if len(grib) > 30_000_000 or grib[:4] != b"GRIB":
        raise ValueError("Invalid or oversized decompressed GRIB")
    return grib, {
        "archive_url": url,
        "archive_sha256": hashlib.sha256(raw_archive).hexdigest(),
        "source_member": member.name,
        "source_member_sha256": hashlib.sha256(compressed).hexdigest(),
        "source_grib_sha256": hashlib.sha256(grib).hexdigest(),
    }


def verify_grib_tags(tags):
    if tags.get("GRIB_ELEMENT") != "APCP":
        raise ValueError("Expected APCP total precipitation")
    if tags.get("GRIB_UNIT") != "[kg/m^2]":
        raise ValueError("Expected GRIB unit kg/m^2 (water equivalent to mm)")
    try:
        duration = int(tags["GRIB_FORECAST_SECONDS"])
        begin = datetime.fromtimestamp(int(tags["GRIB_REF_TIME"]), tz=timezone.utc)
        end = datetime.fromtimestamp(int(tags["GRIB_VALID_TIME"]), tz=timezone.utc)
    except (KeyError, ValueError, OverflowError) as exc:
        raise ValueError("Missing/unreadable GRIB temporal metadata") from exc
    if duration != 86400 or (end-begin) != timedelta(seconds=duration):
        raise ValueError("Not a verified 24-hour accumulation")
    return begin, end


def geodesic_basin_mean(src, basin_lonlat):
    """Sum native-grid precipitation weighted by geodesic clipped cell area.

    Intersections happen in source CRS, after reprojecting basin from WGS84.
    Actual intersection geometry is inverse projected and measured on WGS84,
    avoiding planar-area scale distortions from polar stereographic pixels.
    """
    if src.crs is None or src.crs.is_geographic:
        raise ValueError("Expected native projected Stage IV raster")
    forward = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
    inverse = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
    geom = transform_geom(forward.transform, basin_lonlat)
    if geom.is_empty or not geom.is_valid:
        raise ValueError("Projected basin geometry invalid")
    bounds = box(*src.bounds)
    if not bounds.covers(geom):
        raise ValueError("Stage IV CONUS domain does not cover entire basin")
    win = rasterio.windows.from_bounds(*geom.bounds, transform=src.transform)
    first_col = max(0, int(math.floor(win.col_off))-1)
    last_col = min(src.width, int(math.ceil(win.col_off+win.width))+1)
    first_row = max(0, int(math.floor(win.row_off))-1)
    last_row = min(src.height, int(math.ceil(win.row_off+win.height))+1)
    cells = src.read(1, masked=True)
    total_weight = 0.0
    weighted_rain_mm = 0.0
    contributing = 0
    for row in range(first_row, last_row):
        for col in range(first_col, last_col):
            west, south, east, north = rasterio.transform.array_bounds(
                1, 1, src.window_transform(rasterio.windows.Window(col,row,1,1)))
            intersection = geom.intersection(box(west,south,east,north))
            if intersection.is_empty or intersection.area <= 0:
                continue
            # Enforce complete basin coverage; don't silently drop masked pixels.
            if np.ma.is_masked(cells[row,col]):
                raise ValueError(f"Missing Stage IV precipitation in basin cell ({row},{col})")
            mm = float(cells[row,col])
            if not math.isfinite(mm) or mm < 0:
                raise ValueError(f"Invalid Stage IV precipitation in basin cell ({row},{col})")
            lonlat_intersection = transform_geom(inverse.transform, intersection)
            area_sqm = abs(GEOD.geometry_area_perimeter(lonlat_intersection)[0])
            if not math.isfinite(area_sqm) or area_sqm <= 0:
                raise ValueError("Invalid geodesic area for basin intersection")
            total_weight += area_sqm
            weighted_rain_mm += mm*area_sqm
            contributing += 1
    basin_sqm = abs(GEOD.geometry_area_perimeter(basin_lonlat)[0])
    coverage = total_weight/basin_sqm if basin_sqm else 0.0
    if not (0.995 <= coverage <= 1.005):
        raise ValueError(f"Raster grid failed basin area closure: {coverage:.6f}")
    if contributing == 0:
        raise ValueError("No Stage IV cells contributed to basin")
    return {"map_inches": weighted_rain_mm/total_weight/25.4,
            "map_mm": weighted_rain_mm/total_weight,
            "geodesic_basin_area_sqkm": basin_sqm/1e6,
            "raster_intersection_area_sqkm": total_weight/1e6,
            "geodesic_coverage_fraction": coverage,
            "contributing_pixels": contributing}


def audit_day(day, basins, stage_reader=read_noaa_daily):
    grib, provenance = stage_reader(day)
    with tempfile.NamedTemporaryFile(suffix=".grib") as temp:
        temp.write(grib)
        temp.flush()
        with rasterio.open(temp.name) as src:
            begin, end = verify_grib_tags(src.tags(1))
            report = {
                "date_archive_label": day, "accumulation_start_utc": begin.isoformat(),
                "accumulation_end_utc": end.isoformat(),
                "duration_hours": 24, "native_crs": src.crs.to_wkt(),
                "raster_grid_shape": [src.height,src.width],
                "qpe_product": "NOAA_STAGE_IV_CONUS_APCP_24H",
                "units_source": "kg/m^2_water_equivalent_mm",
                "basins": {}, **provenance
            }
            for nwsli,usgs in PILOTS.items():
                report["basins"][nwsli] = {
                    "usgs_site_id": usgs,
                    **geodesic_basin_mean(src, basins[usgs]),
                    "validation_status": "DAILY_QPE_DIAGNOSTIC_NOT_APPROVED",
                }
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates",nargs="+",default=list(SAMPLE_DATES))
    parser.add_argument("--basins",type=Path,default=ROOT/"historical/2026-10-31_2026-11-01/basins.geojson")
    parser.add_argument("--output",type=Path,default=ROOT/"reconstruction/staging/stageiv_daily_map_audit.json")
    args=parser.parse_args()
    if len(args.dates)>5 or len(args.dates)!=len(set(args.dates)):
        raise ValueError("Use no more than 5 distinct archive days")
    basins=load_upstream_basins(args.basins)
    if set(PILOTS.values())-set(basins):
        raise ValueError("Missing pilot upstream basin")
    output={"schema_version":1,"status":"DAILY_STAGE_IV_QPE_ONLY_NO_CREST_PAIRING",
            "basin_geometry_sha256":hashlib.sha256(args.basins.read_bytes()).hexdigest(),
            "events":[]}
    for day in args.dates:
        output["events"].append(audit_day(day,basins))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,indent=2)+"\n")
    print(json.dumps({
        "status":output["status"],
        "results":[{"date":event["date_archive_label"],
                    "utc_interval":[event["accumulation_start_utc"],event["accumulation_end_utc"]],
                    "map_inches":{n:round(v["map_inches"],5) for n,v in event["basins"].items()},
                    "geodesic_coverage":{n:round(v["geodesic_coverage_fraction"],6) for n,v in event["basins"].items()}}
                   for event in output["events"]]},indent=2))


if __name__=="__main__":
    main()
