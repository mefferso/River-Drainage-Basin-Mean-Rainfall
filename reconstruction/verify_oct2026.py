#!/usr/bin/env python3
"""Independently reproduce the existing 49h MRMS Pass2 basin MAP totals.

This is a rainfall-only diagnostic, not an approved MAP-to-crest relationship.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
from run_pilots import PILOTS, timestamp, hourly_ends, index_manifest, load_upstream_basins, calculate_map


def reproduce(manifest_path, basins_path, historical_json):
    reference = json.loads(Path(historical_json).read_text())
    start = timestamp(reference["event_start_utc"])
    end = timestamp(reference["event_end_utc"])
    inventory = index_manifest(manifest_path)
    basins = load_upstream_basins(basins_path)
    hours = hourly_ends(start, end)
    if len(hours) != 49:
        raise ValueError("Expected exactly 49 UTC hours for Oct31-Nov2 event")
    result = {
        "event": "2026-10-31_2026-11-01",
        "event_start_utc": start.isoformat(), "event_end_utc": end.isoformat(),
        "input_manifest_sha256": hashlib.sha256(Path(manifest_path).read_bytes()).hexdigest(),
        "basin_geometry_sha256": hashlib.sha256(Path(basins_path).read_bytes()).hexdigest(),
        "input_reference_sha256": hashlib.sha256(Path(historical_json).read_bytes()).hexdigest(),
        "record_type": "RAINFALL_ONLY_REPRODUCTION_NO_CREST_MATCH",
        "qpe_hour_count": len(hours), "pilot_results": {},
    }
    for nwsli, usgs in PILOTS.items():
        if usgs not in basins:
            raise ValueError("Missing basin for " + nwsli)
        observed, product = calculate_map(basins[usgs], hours, inventory)
        previous = reference["periods"]["event"]["basins"][usgs]["whole_mean"]
        if not math.isfinite(previous):
            raise ValueError("Existing reference is not finite")
        result["pilot_results"][nwsli] = {
            "usgs_site_id": usgs, "qpe_product": product,
            "independently_calculated_map_inches": round(observed, 7),
            "previous_inherited_map_inches": round(previous, 7),
            "difference_inches": round(observed-previous, 7),
            "comparison_status": "REPRODUCED_WITH_FROZEN_EVENT_BASINS",
            "scientific_status": "RAINFALL_ONLY_NO_VERIFIED_CREST",
        }
    return result


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True)
    p.add_argument("--basins", default="historical/2026-10-31_2026-11-01/basins.geojson")
    p.add_argument("--reference", default="historical/2026-10-31_2026-11-01/latest.json")
    p.add_argument("--output", required=True)
    a=p.parse_args()
    results=reproduce(a.manifest, a.basins, a.reference)
    out=Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results,indent=2)+"\n")
    print(json.dumps(results,indent=2))
