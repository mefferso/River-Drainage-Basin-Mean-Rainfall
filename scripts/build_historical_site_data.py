#!/usr/bin/env python3
"""Validate Phase 2 exports and compile lazy, per-forecast-point site data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import date as date_cls
from pathlib import Path
from typing import Any


EXPECTED_COUNTS = {"map_to_crest": 301, "crest_to_crest": 365, "crosswalk": 29}
SCHEMA_VERSION = "historical-v1"


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _reject_nonfinite(value: Any, location: str) -> None:
    if isinstance(value, float):
        _require(math.isfinite(value), f"{location}: non-finite numeric value")
    elif isinstance(value, dict):
        for key, child in value.items():
            _reject_nonfinite(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_nonfinite(child, f"{location}[{index}]")


def _unique_records(records: list[dict[str, Any]], label: str) -> None:
    ids = [record.get("record_id") for record in records]
    _require(all(isinstance(value, str) and value for value in ids), f"{label}: every row needs a record_id")
    _require(len(ids) == len(set(ids)), f"{label}: duplicate record_id")
    for record in records:
        _require(record.get("quality_tier") == "B", f"{label} {record['record_id']}: non-B row in plot-ready source")
        _require(record.get("date_precision") == "day", f"{label} {record['record_id']}: expected a day-precision Tier B date")
        _require(bool(record.get("source_workbook")) and bool(record.get("source_worksheet")), f"{label} {record['record_id']}: missing source provenance")
        _require(isinstance(record.get("source_row"), int), f"{label} {record['record_id']}: missing source row")
        date = record.get("event_date")
        try:
            valid_date = isinstance(date, str) and date_cls.fromisoformat(date).isoformat() == date
        except (TypeError, ValueError):
            valid_date = False
        _require(valid_date, f"{label} {record['record_id']}: invalid ISO day date label")


def _finite(record: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    for field in fields:
        value = record.get(field)
        _require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value), f"{label} {record.get('record_id')}: {field} must be finite numeric")


def compile_sources(
    map_path: Path,
    pair_path: Path,
    crosswalk_path: Path,
    gages_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Compile exact source rows into per-point JSON without changing any row values."""
    map_rows = read_json(map_path)
    pair_rows = read_json(pair_path)
    crosswalk_rows = read_json(crosswalk_path)
    gages = read_json(gages_path)
    for label, rows in (("MAP", map_rows), ("pair", pair_rows), ("crosswalk", crosswalk_rows)):
        _require(isinstance(rows, list), f"{label}: expected a JSON array")
        _reject_nonfinite(rows, label)
    _require(len(map_rows) == EXPECTED_COUNTS["map_to_crest"], "MAP source count changed; review the Phase 2 baseline before publishing")
    _require(len(pair_rows) == EXPECTED_COUNTS["crest_to_crest"], "pair source count changed; review the Phase 2 baseline before publishing")
    _require(len(crosswalk_rows) == EXPECTED_COUNTS["crosswalk"], "crosswalk source count changed; review the Phase 2 baseline before publishing")
    _unique_records(map_rows, "MAP")
    _unique_records(pair_rows, "pair")
    for row in map_rows:
        _require(row.get("relationship_type") == "map_to_crest", f"MAP {row.get('record_id')}: unexpected relationship type")
        _finite(row, ("map_inches", "crest_feet"), "MAP")
        _require(row.get("nws_point_id") == row.get("historical_point_id"), f"MAP {row['record_id']}: NWS point differs from source point")
        _require(bool(row.get("source_file_sha256")), f"MAP {row['record_id']}: missing source hash")
    for row in pair_rows:
        _require(row.get("relationship_type") == "crest_to_crest", f"pair {row.get('record_id')}: unexpected relationship type")
        _finite(row, ("source_crest_feet", "target_crest_feet"), "pair")
        _require(bool(row.get("relationship_id")), f"pair {row['record_id']}: missing relationship ID")
        _require(bool(row.get("source_point_id_raw")) and bool(row.get("target_point_id_raw")), f"pair {row['record_id']}: missing raw endpoint identifier")
        _require(bool(row.get("source_point_id_nws")) and bool(row.get("target_point_id_nws")), f"pair {row['record_id']}: missing canonical endpoint identifier")
        _require(bool(row.get("source_file_sha256")), f"pair {row['record_id']}: missing source hash")

    configured_ids = {str(gage["id"]) for gage in gages}
    verified: dict[str, dict[str, str]] = {}
    canonical_names: dict[str, str] = {}
    seen_historical_ids: set[str] = set()
    seen_verified_usgs_ids: set[str] = set()
    for row in crosswalk_rows:
        raw_id = row.get("historical_point_id")
        canonical = row.get("canonical_nws_id")
        _require(isinstance(raw_id, str) and raw_id and isinstance(canonical, str) and canonical, "crosswalk: missing station identifiers")
        _require(raw_id not in seen_historical_ids, f"crosswalk: duplicate historical point ID {raw_id}")
        seen_historical_ids.add(raw_id)
        canonical_names[canonical] = row.get("official_nws_name") or canonical
        confirmed = row.get("usgs_site_id_confirmed")
        dashboard_id = row.get("existing_dashboard_usgs_id")
        if confirmed and dashboard_id and confirmed == dashboard_id and dashboard_id in configured_ids:
            _require(canonical not in verified, f"crosswalk: multiple dashboard gages map to {canonical}")
            _require(dashboard_id not in seen_verified_usgs_ids, f"crosswalk: multiple forecast points map to dashboard gage {dashboard_id}")
            seen_verified_usgs_ids.add(dashboard_id)
            verified[canonical] = {
                "usgs_site_id": dashboard_id,
                "nws_point_id": canonical,
                "display_name": row.get("official_nws_name") or canonical,
            }

    point_data: dict[str, dict[str, Any]] = {
        nwsli: {
            "schema_version": SCHEMA_VERSION,
            "nws_point_id": nwsli,
            "map_events": [],
            "crest_relationships": [],
            "quality_policy": "B_historical_descriptive",
            "legacy_method_status": "unverified",
        }
        for nwsli in verified
    }
    point_by_gage = {entry["usgs_site_id"]: nwsli for nwsli, entry in verified.items()}
    excluded_map_by_point: Counter[str] = Counter()
    for row in map_rows:
        nwsli = point_by_gage.get(str(row.get("dashboard_gage_id", "")))
        if nwsli and row.get("nws_point_id") == nwsli:
            point_data[nwsli]["map_events"].append(row)
        else:
            excluded_map_by_point[str(row.get("nws_point_id") or "unknown")] += 1

    pair_groups: dict[str, dict[str, Any]] = {}
    mapped_points = set(point_data)
    for row in pair_rows:
        source_id = row["source_point_id_nws"]
        target_id = row["target_point_id_nws"]
        relationship_id = row["relationship_id"]
        if source_id not in mapped_points and target_id not in mapped_points:
            continue
        group = pair_groups.setdefault(relationship_id, {
            "relationship_id": relationship_id,
            "source_point_id_nws": source_id,
            "target_point_id_nws": target_id,
            "source_point_name": canonical_names.get(source_id, source_id),
            "target_point_name": canonical_names.get(target_id, target_id),
            "records": [],
        })
        _require((group["source_point_id_nws"], group["target_point_id_nws"]) == (source_id, target_id), f"pair {relationship_id}: inconsistent directional endpoints")
        group["records"].append(row)

    for nwsli in point_data:
        point_data[nwsli]["crest_relationships"] = [
            pair_groups[relationship_id]
            for relationship_id in sorted(pair_groups)
            if nwsli in (pair_groups[relationship_id]["source_point_id_nws"], pair_groups[relationship_id]["target_point_id_nws"])
        ]

    output_dir.mkdir(parents=True, exist_ok=True)
    points_dir = output_dir / "points"
    points_dir.mkdir(parents=True, exist_ok=True)
    for nwsli, payload in sorted(point_data.items()):
        write_json(points_dir / f"{nwsli}.json", payload)
    crosswalk_output = sorted(verified.values(), key=lambda entry: entry["usgs_site_id"])
    write_json(output_dir / "crosswalk.json", crosswalk_output)

    published_map_ids = {row["record_id"] for payload in point_data.values() for row in payload["map_events"]}
    published_pair_ids = {row["record_id"] for relation in pair_groups.values() for row in relation["records"]}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_counts": {"map_to_crest": len(map_rows), "crest_to_crest": len(pair_rows), "crosswalk": len(crosswalk_rows)},
        "published_counts": {"map_to_crest": len(published_map_ids), "crest_to_crest": len(published_pair_ids)},
        "excluded_map_records": {
            "no_verified_current_dashboard_gage": sum(excluded_map_by_point.values()),
            "by_historical_point": dict(sorted(excluded_map_by_point.items())),
        },
        "verified_dashboard_crosswalks": len(crosswalk_output),
        "published_relationships": len(pair_groups),
        "published_points": sorted(nwsli for nwsli, payload in point_data.items() if payload["map_events"] or payload["crest_relationships"]),
        "source_sha256": {
            map_path.name: sha256(map_path),
            pair_path.name: sha256(pair_path),
            crosswalk_path.name: sha256(crosswalk_path),
        },
        "crosswalk_file": "crosswalk.json",
        "point_file_pattern": "points/{nws_point_id}.json",
    }
    write_json(output_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    default_dir = root / "historical/relationships/v1"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=default_dir / "source")
    parser.add_argument("--gages", type=Path, default=root / "config/gages.json")
    parser.add_argument("--output-dir", type=Path, default=default_dir)
    args = parser.parse_args()
    manifest = compile_sources(
        args.source_dir / "Phase2_MAP_to_Crest_Plot_Ready.json",
        args.source_dir / "Phase2_Crest_to_Crest_Plot_Ready.json",
        args.source_dir / "Phase2_Forecast_Point_Crosswalk.json",
        args.gages,
        args.output_dir,
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
