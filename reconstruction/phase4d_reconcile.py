#!/usr/bin/env python3
"""Compare exact-attribute NOAA LMRFC polygon candidates and NLDI basins.

The NOAA feature's exact NWSLI is only a candidate label; spatial containment,
area overlap, and event-method identity are reported separately. Daily Stage IV
APCP is compared across geometries without changing product or 12Z-12Z windows.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import rasterio
from pyproj import Geod, Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as transform_geom

from reconstruction.run_pilots import PILOTS
from reconstruction.river_stage import crest_candidates, request_stage, time_utc
from reconstruction.stageiv_daily_map import geodesic_basin_mean, read_noaa_daily, verify_grib_tags

ROOT = Path(__file__).resolve().parents[1]
GEOD = Geod(ellps="WGS84")
SQMI_TO_SQM = 2_589_988.110336
STAGE_WINDOWS = {
    "2016-08-13": {"nwsli": "AMIL1", "legacy_crest_ft": 26.2},
    "2017-04-04": {"nwsli": "AMIL1", "legacy_crest_ft": 17.8},
}


def _area_sqmi(geom) -> float:
    if geom.is_empty or not geom.is_valid:
        raise ValueError("Geometry must be nonempty and valid")
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / SQMI_TO_SQM


def compare_geometry(rfc_candidate, nldi_upstream, nldi_incremental, outlet) -> dict:
    """Calculate geodesic areas, IoU, symmetric differences, and offsets."""
    metrics = {"outlet_inside_rfc_candidate": bool(rfc_candidate.covers(outlet))}
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)
    to_metric = lambda g: transform_geom(transformer.transform, g)
    projected_outlet = to_metric(outlet)
    projected_rfc = to_metric(rfc_candidate)
    metrics["outlet_to_rfc_boundary_km"] = round(projected_rfc.boundary.distance(projected_outlet) / 1000, 4)
    for label, basin in (("upstream", nldi_upstream), ("incremental", nldi_incremental)):
        inter = rfc_candidate.intersection(basin)
        rfc_area, nldi_area, inter_area = _area_sqmi(rfc_candidate), _area_sqmi(basin), _area_sqmi(inter)
        union_area = rfc_area + nldi_area - inter_area
        projected_basin = to_metric(basin)
        distance_m = projected_rfc.centroid.distance(projected_basin.centroid)
        hausdorff_m = projected_rfc.boundary.hausdorff_distance(projected_basin.boundary)
        metrics[label] = {
            "rfc_candidate_area_sqmi": round(rfc_area, 6),
            "nldi_area_sqmi": round(nldi_area, 6),
            "intersection_sqmi": round(inter_area, 6),
            "union_sqmi": round(union_area, 6),
            "symmetric_difference_sqmi": round(max(0, rfc_area + nldi_area - 2 * inter_area), 6),
            "rfc_only_sqmi": round(max(0, rfc_area - inter_area), 6),
            "nldi_only_sqmi": round(max(0, nldi_area - inter_area), 6),
            "iou_percent": round(inter_area / union_area * 100, 4) if union_area else None,
            "rfc_fraction_in_nldi_percent": round(inter_area / rfc_area * 100, 4) if rfc_area else None,
            "nldi_fraction_in_rfc_percent": round(inter_area / nldi_area * 100, 4) if nldi_area else None,
            "centroid_offset_km_epsg5070": round(distance_m / 1000, 4),
            "boundary_hausdorff_km_epsg5070": round(hausdorff_m / 1000, 4),
        }
    return metrics


def _parse_time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("QPE interval timestamps must include a UTC offset")
    return dt.astimezone(timezone.utc)


def aggregate_same_qpe_window(daily_records: list[dict]) -> dict:
    """Sum contiguous 24-hour daily MAPs from one product/grid, without relabeling."""
    if not daily_records:
        raise ValueError("At least one daily Stage IV result is required")
    ordered = sorted(daily_records, key=lambda item: _parse_time(item["start_utc"]))
    product_set = {item.get("product") for item in ordered}
    grid_set = {item.get("grid_signature") for item in ordered}
    if len(product_set) != 1 or not next(iter(product_set)):
        raise ValueError("A same-product QPE window is required")
    if len(grid_set) != 1 or not next(iter(grid_set)):
        raise ValueError("A single verified Stage IV grid is required")
    for index, item in enumerate(ordered):
        start, end = _parse_time(item["start_utc"]), _parse_time(item["end_utc"])
        if end - start != timedelta(hours=24):
            raise ValueError("Each source accumulation must be exactly 24 hours")
        if index and _parse_time(ordered[index - 1]["end_utc"]) != start:
            raise ValueError("Stage IV daily intervals must be contiguous")
        if any(not isinstance(item.get(k), (int, float)) or not math.isfinite(item[k])
               for k in ("nldi_map_inches", "rfc_map_inches")):
            raise ValueError("Both geometry MAP values are required for every day")
    nldi = sum(item["nldi_map_inches"] for item in ordered)
    rfc = sum(item["rfc_map_inches"] for item in ordered)
    start, end = _parse_time(ordered[0]["start_utc"]), _parse_time(ordered[-1]["end_utc"])
    return {
        "product": next(iter(product_set)), "grid_signature": next(iter(grid_set)),
        "start_utc": start.isoformat(), "end_utc": end.isoformat(),
        "duration_hours": int((end - start).total_seconds() // 3600),
        "daily_interval_count": len(ordered), "nldi_map_inches": round(nldi, 8),
        "rfc_map_inches": round(rfc, 8),
        "rfc_minus_nldi_inches": round(rfc - nldi, 8),
        "rfc_minus_nldi_percent_of_nldi": round((rfc - nldi) / nldi * 100, 4) if nldi else None,
        "periods": ordered,
    }


def _load_geo(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("type") != "FeatureCollection":
        raise ValueError(f"Expected FeatureCollection in {path}")
    return data


def geometry_inventory(rfc_path: Path, upstream_path: Path, reaches_path: Path,
                       config_path: Path, phase4a_summary: Path) -> dict:
    rfc_data, upstream_data, reach_data = map(_load_geo, (rfc_path, upstream_path, reaches_path))
    rfc = {}
    for feature in rfc_data["features"]:
        lid = feature.get("properties", {}).get("nwsli")
        if lid:
            if lid in rfc:
                raise ValueError(f"Multiple exact RFC NWSLI features for {lid}")
            rfc[lid] = feature
    upstream = {str(f["properties"].get("id")): shape(f["geometry"]) for f in upstream_data["features"]}
    reaches = {str(f["properties"].get("id")): shape(f["geometry"]) for f in reach_data["features"]}
    config = json.loads(config_path.read_text(encoding="utf-8"))
    gages = {str(g["id"]): g for g in config}
    summary = json.loads(phase4a_summary.read_text(encoding="utf-8"))
    rows = {}
    for nwsli, site in PILOTS.items():
        feature = rfc.get(nwsli)
        if not feature or site not in upstream or site not in reaches:
            raise ValueError(f"Missing exact RFC candidate or NLDI geometry for {nwsli}")
        props = feature["properties"]
        geom = shape(feature["geometry"])
        point = Point(float(gages[site]["lon"]), float(gages[site]["lat"]))
        rows[nwsli] = {
            "usgs_site_id": site, "nwsli_attribute": nwsli,
            "rfc_feature_index": props.get("rfc_index"), "rfc_feature_name": props.get("rfc_name"),
            "rfc_forecast_group": props.get("rfc_fcstgroup"),
            "rfc_attributes_area_sqmi": props.get("area_sqmi"),
            "candidate_status": "EXACT_NWSLI_ATTRIBUTE_UNVERIFIED_HISTORICAL_MAP_BOUNDARY",
            "geometry_comparison": compare_geometry(geom, upstream[site], reaches[site], point),
        }
    return {
        "source": {
            "archive_url": "https://www.nohrsc.noaa.gov/data/vector/master/b_lmrfc.tar.gz",
            "archive_sha256": summary.get("archive_sha256"),
            "feature_count": summary.get("rfc_features"),
            "fields": summary.get("rfc_fields"),
            "derived_asset": str(rfc_path.resolve().relative_to(ROOT.resolve())),
            "coordinate_reference_system": "EPSG:4326 (RFC polygons were reprojected to WGS84 for GeoJSON export)",
        },
        "geometry_method": "WGS84 ellipsoidal geodesic area for RFC, full NLDI and incremental NLDI; EPSG:5070 for boundary and centroid offsets",
        "stations": rows,
    }


def stageiv_geometry_audit(dates: list[str], geometries: dict, nwsli: str, site_id: str,
                           source_reader=read_noaa_daily) -> dict:
    records = []
    reference_grid = None
    for date in dates:
        grib, provenance = source_reader(date)
        with tempfile.NamedTemporaryFile(suffix=".grib") as temp:
            temp.write(grib); temp.flush()
            with rasterio.open(temp.name) as src:
                start, end = verify_grib_tags(src.tags(1))
                signature = hashlib.sha256((src.crs.to_wkt() + repr(tuple(src.transform)) +
                                              repr((src.height, src.width))).encode()).hexdigest()
                if reference_grid is None:
                    reference_grid = signature
                elif signature != reference_grid:
                    raise ValueError("Stage IV source grid changed during the comparison window")
                maps = {name: geodesic_basin_mean(src, geom)["map_inches"]
                        for name, geom in geometries.items()}
                records.append({
                    "archive_label": date, "start_utc": start.isoformat(), "end_utc": end.isoformat(),
                    "duration_hours": int((end - start).total_seconds() // 3600),
                    "product": "NOAA_STAGE_IV_CONUS_APCP_24H", "grid_signature": signature,
                    "nldi_map_inches": maps["nldi"], "rfc_map_inches": maps["rfc"],
                    "source_provenance": provenance,
                })
    aggregate = aggregate_same_qpe_window(records)
    aggregate["station"] = nwsli
    aggregate["usgs_site_id"] = site_id
    return aggregate


def stage_discrepancy_audit(output_path: Path) -> dict:
    windows = []
    for date, meta in STAGE_WINDOWS.items():
        day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        start, end = day - timedelta(days=3), day + timedelta(days=6)
        site = PILOTS[meta["nwsli"]]
        data = request_stage(site, start, end)
        peaks = crest_candidates(data["observations"], min_stage_ft=None, separation_hours=6)
        observed = data["observations"]
        windows.append({
            "nwsli": meta["nwsli"], "usgs_site_id": site,
            "legacy_date_label_only": date, "legacy_crest_ft_unverified": meta["legacy_crest_ft"],
            "window_start_utc": start.isoformat(), "window_end_utc": end.isoformat(),
            "retrieved_at_utc": data["retrieved_at_utc"], "source_url": data["request_url"],
            "series_metadata": data["series_metadata"], "observation_count": len(observed),
            "first_observed_utc": observed[0]["time_utc"] if observed else None,
            "last_observed_utc": observed[-1]["time_utc"] if observed else None,
            "largest_sample_gap_hours": max(((time_utc(b["time_utc"])-time_utc(a["time_utc"])).total_seconds()/3600
                                              for a,b in zip(observed,observed[1:])), default=None),
            "observations": observed, "local_peak_candidates_6h_separation": peaks,
            "status": "HYDROGRAPH_REVIEW_REQUIRED_NOT_VERIFIED_CREST",
        })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({"schema_version": 1, "windows": windows}, indent=2) + "\n", encoding="utf-8")
    return {"window_count": len(windows), "observation_counts": {w["legacy_date_label_only"]: w["observation_count"] for w in windows}}


def run(args) -> dict:
    geometry = geometry_inventory(args.rfc, args.upstream, args.reaches, args.gages, args.phase4a_summary)
    upstream_data = _load_geo(args.upstream)
    rfc_data = _load_geo(args.rfc)
    rfc_geoms = {f["properties"]["nwsli"]: shape(f["geometry"]) for f in rfc_data["features"] if f.get("properties", {}).get("nwsli") in PILOTS}
    nldi_geoms = {str(f["properties"].get("id")): shape(f["geometry"]) for f in upstream_data["features"]}
    qpe = {nwsli: stageiv_geometry_audit(args.dates, {"nldi": nldi_geoms[site], "rfc": rfc_geoms[nwsli]}, nwsli, site)
           for nwsli, site in PILOTS.items()}
    stage_path = args.output.parent / "amil1_hydrograph_discrepancy_windows.json"
    stage_summary = stage_discrepancy_audit(stage_path) if args.retrieve_stage else {"status": "NOT_RUN"}
    result = {
        "schema_version": 1, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "GEOMETRY_CANDIDATES_AND_DAILY_STAGE_IV_COMPARISON_NOT_SCIENCE_APPROVED",
        "geometry": geometry, "qpe_same_product_same_window": qpe,
        "stage_discrepancy_retrieval": stage_summary,
        "scientific_limits": [
            "Exact RFC NWSLI attribute match does not establish historical MAP mask identity.",
            "Daily Stage IV 24h APCP is not six-hour/hourly rainfall and does not prove event onset or cessation.",
            "USGS window maxima and local peaks are source observations/candidates; neither is promoted to a validated flood crest.",
            "Stage datum changes and original spreadsheet binaries/definitions remain outside these data unless separately resolved.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dates", nargs="+", default=["2018-12-27", "2018-12-28"])
    parser.add_argument("--rfc", type=Path, default=ROOT / "reports/phase4a/rfc_exact_nwsli_polygons.geojson")
    parser.add_argument("--upstream", type=Path, default=ROOT / "historical/2026-10-31_2026-11-01/basins.geojson")
    parser.add_argument("--reaches", type=Path, default=ROOT / "data/reaches.geojson")
    parser.add_argument("--gages", type=Path, default=ROOT / "config/gages.json")
    parser.add_argument("--phase4a-summary", type=Path, default=ROOT / "reports/phase4a/summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/phase4d/phase4d_data_audit.json")
    parser.add_argument("--retrieve-stage", action="store_true")
    result = run(parser.parse_args())
    print(json.dumps({"status": result["status"], "geometry_stations": list(result["geometry"]["stations"]),
                      "stageiv_windows": {k: {"start_utc": v["start_utc"], "end_utc": v["end_utc"],
                                                     "nldi_map_inches": v["nldi_map_inches"],
                                                     "rfc_map_inches": v["rfc_map_inches"]}
                                           for k,v in result["qpe_same_product_same_window"].items()}}, indent=2))


if __name__ == "__main__":
    main()
