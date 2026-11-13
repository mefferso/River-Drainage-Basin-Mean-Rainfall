#!/usr/bin/env python3
"""Fail-closed structural validation for generated Phase 4B deliverables."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

from shapely.geometry import shape

try:
    from scripts.build_phase4b_rfc_aggregates import RFC_ARCHIVE_SHA256, RFC_FIELDS
except ModuleNotFoundError:
    from build_phase4b_rfc_aggregates import RFC_ARCHIVE_SHA256, RFC_FIELDS


def validate(out_dir: Path) -> dict[str, int | str]:
    out_dir = Path(out_dir)
    required = (
        "rfc_feature_inventory.csv", "rfc_single_segments.geojson",
        "topology_snapshot.json", "nldi_responses.json.gz",
        "rfc_relationships.csv", "station_reconciliation.csv",
        "station_reconciliation.json", "candidate_aggregates.geojson",
        "nldi_reference_geometries.geojson", "unresolved_issues.csv",
        "summary.json", "geometry_review.html",
    )
    missing = [name for name in required if not (out_dir / name).is_file()]
    if missing:
        raise ValueError(f"Phase 4B output package is missing files: {missing}")
    with (out_dir / "rfc_feature_inventory.csv").open(encoding="utf-8", newline="") as stream:
        inventory = list(csv.DictReader(stream))
    if len(inventory) != 543:
        raise ValueError(f"Expected 543 RFC feature inventory rows; found {len(inventory)}")
    if any(row.get("source_archive_sha256") != RFC_ARCHIVE_SHA256 for row in inventory):
        raise ValueError("RFC inventory has a missing or unexpected source fingerprint")
    missing_fields = set(RFC_FIELDS) - set(inventory[0])
    if missing_fields:
        raise ValueError(f"RFC inventory is missing source attributes: {sorted(missing_fields)}")
    if "source_geometry_valid" not in inventory[0] or "source_geometry_issue" not in inventory[0]:
        raise ValueError("RFC inventory must flag preserved source geometry defects")

    stations = list(csv.DictReader((out_dir / "station_reconciliation.csv").open(
        encoding="utf-8", newline="")))
    station_ids = [row.get("canonical_nws_id", "") for row in stations]
    if len(stations) != 29 or len(set(station_ids)) != 29 or "" in station_ids:
        raise ValueError("Station reconciliation must have exactly 29 unique canonical IDs")
    station_json = json.loads((out_dir / "station_reconciliation.json").read_text(encoding="utf-8"))
    if len(station_json) != 29 or {
        row.get("canonical_nws_id") for row in station_json
    } != set(station_ids):
        raise ValueError("Station JSON reconciliation does not match the 29 CSV rows")

    source = json.loads((out_dir / "rfc_single_segments.geojson").read_text(encoding="utf-8"))
    candidates = json.loads((out_dir / "candidate_aggregates.geojson").read_text(encoding="utf-8"))
    topology = json.loads((out_dir / "topology_snapshot.json").read_text(encoding="utf-8"))
    response_archive = out_dir / topology["raw_response_archive"]["path"]
    response_bytes = response_archive.read_bytes()
    if hashlib.sha256(response_bytes).hexdigest() != topology["raw_response_archive"]["sha256"]:
        raise ValueError("NLDI raw response archive hash does not match topology snapshot")
    responses = json.loads(gzip.decompress(response_bytes))
    if len(responses) != topology["raw_response_archive"]["response_count"]:
        raise ValueError("NLDI raw response archive count does not match topology snapshot")
    if len(source.get("features", [])) != 543:
        raise ValueError("RFC source GeoJSON must contain all 543 original features")
    source_ids = {str(feature.get("id")) for feature in source["features"]}
    for feature in candidates.get("features", []):
        props = feature.get("properties", {})
        if props.get("legacy_map_geometry_verified") is not False:
            raise ValueError("Candidate geometry cannot claim legacy MAP verification")
        if props.get("historical_map_equivalence") != "NOT_ESTABLISHED":
            raise ValueError("Candidate geometry must retain unresolved MAP equivalence")
        if not shape(feature["geometry"]).is_valid:
            raise ValueError("Candidate GeoJSON contains invalid geometry")
        if not set(props.get("candidate_feature_ids", [])) <= source_ids:
            raise ValueError("Candidate references an RFC component absent from the source set")
    if topology.get("rfc_feature_count") != 543:
        raise ValueError("Topology snapshot does not describe all 543 RFC source nodes")
    if len(topology.get("links", {})) != 543:
        raise ValueError("Topology snapshot must preserve link status for all 543 RFC nodes")
    with (out_dir / "rfc_relationships.csv").open(encoding="utf-8", newline="") as stream:
        relationship_count = sum(1 for _ in csv.DictReader(stream))
    if relationship_count != topology.get("relationship_count"):
        raise ValueError("Relationship CSV count does not match topology snapshot")
    if topology.get("invalid_source_geometry_count", 0) != sum(
        row["source_geometry_valid"].lower() != "true" for row in inventory
    ):
        raise ValueError("Topology snapshot invalid-geometry count does not match inventory")

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    if summary.get("historical_point_count") != 29:
        raise ValueError("Summary does not account for all 29 historical points")
    if summary.get("legacy_map_equivalence_verified_count") != 0:
        raise ValueError("No Phase 4B candidate can be certified as a legacy MAP mask")
    return {
        "rfc_feature_count": len(inventory),
        "historical_point_count": len(stations),
        "candidate_count": len(candidates.get("features", [])),
        "archive_sha256": RFC_ARCHIVE_SHA256,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path, nargs="?", default=Path("reports/phase4b"))
    print(json.dumps(validate(parser.parse_args().out_dir), indent=2, sort_keys=True))
