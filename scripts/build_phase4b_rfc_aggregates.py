#!/usr/bin/env python3
"""Build traceable, review-only LMRFC basin topology candidates."""
from __future__ import annotations

import csv
import argparse
import gzip
import hashlib
import json
import math
import tarfile
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from pyproj import Transformer

from pyproj import Geod
from shapely.geometry import mapping, shape
from shapely.ops import unary_union


RFC_ARCHIVE_SHA256 = (
    "ffd630cb973edfc70a5dabdeff383593bdcef8d17f697f2e824d6e3c636269bb"
)
RFC_FEATURE_COUNT = 543
RFC_FIELDS = (
    "OBJ_STATUS_",
    "OBJ_IDENTIF",
    "NAME",
    "MIN_X_AXIS_",
    "MAX_X_AXIS_",
    "MIN_Y_AXIS_",
    "MAX_Y_AXIS_",
    "FCSTGROUP",
    "NWSID",
    "AREA",
    "DESCRIPT",
    "TVA_NUM",
)
SQUARE_METERS_PER_SQUARE_MILE = 2_589_988.110336
GEOD = Geod(ellps="WGS84")
NLDI_BASE_URL = "https://api.water.usgs.gov/nldi/linked-data"
MAX_OUTLET_SNAP_METERS = 200.0
WGS84_TO_LOCAL_METERS = Transformer.from_crs(
    "EPSG:4326", "EPSG:5070", always_xy=True
)


@dataclass(frozen=True)
class RfcFeature:
    feature_index: int
    feature_id: str
    properties: dict[str, Any]
    geometry: Any
    outlet: Any
    area_sqmi: float
    geometry_valid: bool = True
    geometry_issue: str = ""


def resolve_outlet_link(
    feature: Any, response: Mapping[str, Any]
) -> dict[str, Any]:
    """Accept an RFC outlet only when NLDI resolves it to a flowline within 200 m."""
    response_payload = {
        key: value
        for key, value in response.items()
        if key not in {"source_url", "retrieved_at"}
    }
    raw_bytes = json.dumps(
        response_payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    response_hash = hashlib.sha256(raw_bytes).hexdigest()
    result = {
        "source_feature_id": str(feature.feature_id),
        "status": "UNRESOLVED",
        "comid": None,
        "measure": None,
        "method": "UNRESOLVED",
        "distance_m": None,
        "outlet_longitude": float(feature.outlet.x),
        "outlet_latitude": float(feature.outlet.y),
        "source_url": response.get("source_url", ""),
        "retrieved_at": response.get("retrieved_at", ""),
        "response_sha256": response_hash,
        "reason": "",
    }
    features = response.get("features")
    if not isinstance(features, list) or len(features) != 1:
        result["reason"] = "NLDI hydrolocation must return exactly one feature"
        return result

    match = features[0]
    properties = match.get("properties") or {}
    reported_method = str(properties.get("method", properties.get("location_method", ""))).upper()
    if "RAINDROP" in reported_method or "TRACE" in reported_method:
        result["reason"] = "NLDI returned a raindrop-trace location, not an accepted flowline snap"
        return result
    raw_comid = properties.get("comid", properties.get("nhdplus_comid"))
    try:
        comid = int(raw_comid)
    except (TypeError, ValueError):
        result["reason"] = "NLDI hydrolocation returned no valid COMID"
        return result

    geometry_json = match.get("geometry")
    try:
        flowline = shape(geometry_json)
        outlet = feature.outlet
        project_to_meters = WGS84_TO_LOCAL_METERS.transform
        from shapely import transform as transform_geometry

        flowline_m = transform_geometry(
            flowline, project_to_meters, interleaved=False
        )
        outlet_m = transform_geometry(
            outlet, project_to_meters, interleaved=False
        )
        distance_m = float(outlet_m.distance(flowline_m))
    except (TypeError, ValueError, KeyError):
        result["reason"] = "NLDI hydrolocation returned invalid flowline geometry"
        return result
    result["distance_m"] = distance_m
    if not math.isfinite(distance_m) or distance_m > MAX_OUTLET_SNAP_METERS:
        result["reason"] = (
            f"Outlet is {distance_m:.1f} m from the returned flowline; "
            "only a snap within 200 m is accepted"
        )
        return result

    measure = properties.get("measure")
    if measure is not None:
        try:
            measure = float(measure)
        except (TypeError, ValueError):
            result["reason"] = "NLDI hydrolocation returned an invalid measure"
            return result
        if not math.isfinite(measure):
            result["reason"] = "NLDI hydrolocation returned an invalid measure"
            return result
    result.update(
        {
            "status": "LINKED",
            "comid": comid,
            "measure": measure,
            "method": "NLDI_SNAP_TO_FLOWLINE",
            "reason": "",
        }
    )
    return result


def build_relationships(
    features: Sequence[RfcFeature],
    links: Mapping[str, Mapping[str, Any]],
    upstream_reach_sets: Mapping[int, set[int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Derive directed RFC outlet relationships from NLDI upstream flowline sets."""
    edges: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    linked: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        link = links.get(feature.feature_id, {})
        if link.get("status") != "LINKED" or link.get("comid") is None:
            issues.append(
                {
                    "feature_id": feature.feature_id,
                    "code": "RFC_OUTLET_UNLINKED",
                    "reason": link.get("reason", "No verified routed COMID"),
                }
            )
            continue
        linked[feature.feature_id] = link
        comid = int(link["comid"])
        if comid not in upstream_reach_sets:
            issues.append(
                {
                    "feature_id": feature.feature_id,
                    "code": "RFC_UPSTREAM_NAV_MISSING",
                    "reason": f"No upstream flowline set for COMID {comid}",
                }
            )

    for upstream_id, upstream_link in linked.items():
        upstream_comid = int(upstream_link["comid"])
        for downstream_id, downstream_link in linked.items():
            if upstream_id == downstream_id:
                continue
            downstream_comid = int(downstream_link["comid"])
            reaches = upstream_reach_sets.get(downstream_comid)
            if reaches is None or upstream_comid not in reaches:
                continue
            if upstream_comid == downstream_comid:
                # Navigation returns a COMID set, not flow order within one reach.
                # Measures are retained for review but do not independently certify direction.
                continue
            edges.append(
                {
                    "upstream_feature_id": upstream_id,
                    "downstream_feature_id": downstream_id,
                    "upstream_comid": upstream_comid,
                    "downstream_comid": downstream_comid,
                    "evidence": "NHDPLUSV2_NLDI_UPSTREAM_FLOWLINES",
                    "downstream_navigation_response_sha256": downstream_link.get(
                        "upstream_response_sha256", ""
                    ),
                }
            )
    return edges, issues


def _response_payload(response: Any, url: str, retrieved_at: str) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("NLDI response is not a JSON object")
    return {**payload, "source_url": url, "retrieved_at": retrieved_at}


def _response_features(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    features = payload.get("features")
    if isinstance(features, list):
        return [feature for feature in features if isinstance(feature, dict)]
    if payload.get("type") == "Feature" and payload.get("geometry"):
        return [payload]
    return []


def fetch_network_cache(
    features: Sequence[RfcFeature],
    cache_dir: Path,
    *,
    refresh: bool = False,
    session: Any = None,
    sleep_seconds: float = 0.1,
) -> dict[str, Any]:
    """Fetch or load a versioned NLDI snapshot; request failures remain explicit."""
    import requests
    from datetime import datetime, timezone
    from urllib.parse import urlencode

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "nldi_network_cache.json"
    if not refresh and cache_path.is_file():
        snapshot = json.loads(cache_path.read_text(encoding="utf-8"))
        if snapshot.get("schema_version") != 1:
            raise ValueError("Unsupported NLDI cache schema version")
        if snapshot.get("rfc_feature_ids") != [feature.feature_id for feature in features]:
            raise ValueError("NLDI cache feature identifiers do not match RFC inventory")
        snapshot["upstream_reach_sets"] = {
            int(comid): {int(reach) for reach in reaches}
            for comid, reaches in snapshot.get("upstream_reach_sets", {}).items()
        }
        return snapshot

    session = session or requests.Session()
    links: dict[str, dict[str, Any]] = {}
    basins: dict[str, dict[str, Any]] = {}
    upstream_sets: dict[int, set[int]] = {}
    failures: list[dict[str, str]] = []
    raw_responses: list[dict[str, Any]] = []

    def get_payload(url: str, subject: str) -> dict[str, Any] | None:
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        try:
            payload = _response_payload(session.get(url, timeout=40), url, retrieved)
            raw_responses.append(payload)
            return payload
        except Exception as exc:  # Preserve errors as auditable unresolved evidence.
            failures.append({"subject": subject, "url": url, "error": str(exc)})
            return None

    # Cache every point result, including failed calls, in the immutable snapshot.
    for feature in features:
        coords = f"POINT({feature.outlet.x:.10f} {feature.outlet.y:.10f})"
        url = f"{NLDI_BASE_URL}/hydrolocation?{urlencode({'f': 'json', 'coords': coords})}"
        payload = get_payload(url, feature.feature_id)
        if payload is None:
            link = {
                "source_feature_id": feature.feature_id,
                "status": "UNRESOLVED", "comid": None, "measure": None,
                "method": "UNRESOLVED", "distance_m": None,
                "outlet_longitude": feature.outlet.x,
                "outlet_latitude": feature.outlet.y,
                "source_url": url, "retrieved_at": "",
                "response_sha256": "", "reason": "NLDI hydrolocation request failed",
            }
        else:
            link = resolve_outlet_link(feature, payload)
        links[feature.feature_id] = link

    comids = sorted({
        int(link["comid"]) for link in links.values()
        if link.get("status") == "LINKED" and link.get("comid") is not None
    })
    for comid in comids:
        nav_url = f"{NLDI_BASE_URL}/comid/{comid}/navigation/UT/flowlines?f=json&distance=9999"
        nav = get_payload(nav_url, str(comid))
        if nav is None:
            continue
        reaches: set[int] = set()
        for item in _response_features(nav):
            props = item.get("properties") or {}
            raw = props.get("comid", props.get("nhdplus_comid"))
            if raw is None:
                raw = str(item.get("id", "")).split(":")[-1]
            try:
                reaches.add(int(raw))
            except (TypeError, ValueError):
                continue
        upstream_sets[comid] = reaches
        response_bytes = json.dumps(
            {key: value for key, value in nav.items() if key not in {"source_url", "retrieved_at"}},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        for link in links.values():
            if link.get("comid") == comid:
                link["upstream_response_sha256"] = hashlib.sha256(response_bytes).hexdigest()

        basin_url = f"{NLDI_BASE_URL}/comid/{comid}/basin?f=json"
        basin_payload = get_payload(basin_url, str(comid))
        if basin_payload is not None:
            basin_features = _response_features(basin_payload)
            if len(basin_features) == 1 and basin_features[0].get("geometry"):
                basin = basin_features[0]
                basin_hash = hashlib.sha256(json.dumps(
                    {key: value for key, value in basin_payload.items()
                     if key not in {"source_url", "retrieved_at"}},
                    sort_keys=True, separators=(",", ":"), allow_nan=False,
                ).encode("utf-8")).hexdigest()
                basins[str(comid)] = {
                    "geometry": basin["geometry"], "source_url": basin_url,
                    "retrieved_at": basin_payload.get("retrieved_at", ""),
                    "response_sha256": basin_hash,
                }
            else:
                failures.append({"subject": str(comid), "url": basin_url,
                                 "error": "NLDI basin response missing one polygon feature"})

    snapshot = {
        "schema_version": 1,
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "USGS NLDI / NHDPlusV2 routed-network proxy",
        "rfc_feature_ids": [feature.feature_id for feature in features],
        "links": links,
        "upstream_reach_sets": upstream_sets,
        "basins": basins,
        "failures": failures,
        "raw_responses": raw_responses,
    }
    stored = {**snapshot, "upstream_reach_sets": {
        str(comid): sorted(reaches) for comid, reaches in upstream_sets.items()
    }}
    cache_path.write_text(
        json.dumps(stored, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return snapshot


def write_network_outputs(
    features: Sequence[RfcFeature],
    links: Mapping[str, Mapping[str, Any]],
    upstream_reach_sets: Mapping[int, set[int]],
    edges: Sequence[Mapping[str, Any]],
    issues: Sequence[Mapping[str, Any]],
    out_dir: Path,
    archive_sha256: str,
    *,
    basins: Mapping[str, Any] | None = None,
    failures: Sequence[Mapping[str, Any]] = (),
    raw_responses: Sequence[Mapping[str, Any]] = (),
) -> None:
    """Write full 543-node status, directed edge evidence, and topology snapshot."""
    out_dir = Path(out_dir)
    write_source_inventory(list(features), out_dir, archive_sha256)
    inventory_path = out_dir / "rfc_feature_inventory.csv"
    with inventory_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    extra = ["outlet_link_status", "outlet_comid", "outlet_measure",
             "outlet_snap_method", "outlet_snap_distance_m", "outlet_link_evidence_sha256",
             "upstream_navigation_evidence_sha256"]
    base_fields = list(rows[0]) if rows else []
    for row in rows:
        link = links.get(row["source_feature_id"], {})
        row.update({
            "outlet_link_status": link.get("status", "UNRESOLVED"),
            "outlet_comid": link.get("comid"),
            "outlet_measure": link.get("measure"),
            "outlet_snap_method": link.get("method", "UNRESOLVED"),
            "outlet_snap_distance_m": link.get("distance_m"),
            "outlet_link_evidence_sha256": link.get("response_sha256", ""),
            "upstream_navigation_evidence_sha256": link.get("upstream_response_sha256", ""),
        })
    with inventory_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=base_fields + extra)
        writer.writeheader()
        writer.writerows(rows)

    relationship_fields = [
        "upstream_feature_id", "downstream_feature_id", "upstream_comid",
        "downstream_comid", "evidence", "downstream_navigation_response_sha256",
    ]
    with (out_dir / "rfc_relationships.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=relationship_fields)
        writer.writeheader()
        writer.writerows(edges)
    response_bytes = json.dumps(
        list(raw_responses), separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    response_archive = gzip.compress(response_bytes, mtime=0)
    response_archive_path = out_dir / "nldi_responses.json.gz"
    response_archive_path.write_bytes(response_archive)
    topology = {
        "schema_version": 1,
        "source": "NOAA 2018 LMRFC source segments + USGS NLDI/NHDPlusV2 proxy",
        "source_archive_sha256": archive_sha256,
        "rfc_feature_count": len(features),
        "invalid_source_geometry_count": sum(
            not getattr(feature, "geometry_valid", True) for feature in features
        ),
        "linked_outlet_count": sum(link.get("status") == "LINKED" for link in links.values()),
        "unresolved_outlet_count": sum(link.get("status") != "LINKED" for link in links.values()),
        "relationship_count": len(edges),
        "unresolved_issue_count": len(issues) + len(failures),
        "links": links,
        "upstream_reach_sets": {str(comid): sorted(reaches)
                                for comid, reaches in upstream_reach_sets.items()},
        "basins": basins or {},
        "issues": list(issues),
        "request_failures": list(failures),
        "raw_response_archive": {
            "path": response_archive_path.name,
            "sha256": hashlib.sha256(response_archive).hexdigest(),
            "response_count": len(raw_responses),
            "compression": "gzip",
        },
    }
    (out_dir / "topology_snapshot.json").write_text(
        json.dumps(topology, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    summary = {key: topology[key] for key in (
        "source_archive_sha256", "rfc_feature_count", "linked_outlet_count",
        "unresolved_outlet_count", "relationship_count", "unresolved_issue_count",
        "invalid_source_geometry_count",
    )}
    summary["connectivity_classification"] = "NHDPLUS_LINKED_PROXY" if edges else "UNRESOLVED"
    summary["legacy_map_geometry_verified"] = False
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _area_sqmi(geometry: Any) -> float:
    if geometry is None or geometry.is_empty:
        return 0.0
    return abs(GEOD.geometry_area_perimeter(geometry)[0]) / SQUARE_METERS_PER_SQUARE_MILE


def compare_geometries(candidate: Any, reference: Any | None) -> dict[str, float] | None:
    """Compare two valid polygons using WGS84 ellipsoidal areas."""
    if reference is None:
        return None
    if (candidate is None or candidate.is_empty or reference.is_empty
            or not candidate.is_valid or not reference.is_valid):
        return None
    candidate_area = _area_sqmi(candidate)
    reference_area = _area_sqmi(reference)
    intersection_area = _area_sqmi(candidate.intersection(reference))
    union_area = _area_sqmi(candidate.union(reference))
    if union_area <= 0 or candidate_area <= 0 or reference_area <= 0:
        return None
    return {
        "candidate_area_sqmi": candidate_area,
        "reference_area_sqmi": reference_area,
        "intersection_sqmi": intersection_area,
        "union_sqmi": union_area,
        "iou_pct": 100.0 * intersection_area / union_area,
        "candidate_coverage_pct": 100.0 * intersection_area / candidate_area,
        "reference_coverage_pct": 100.0 * intersection_area / reference_area,
        "symmetric_difference_sqmi": _area_sqmi(candidate.symmetric_difference(reference)),
    }


def build_station_candidate(
    point: Mapping[str, Any],
    features: Sequence[RfcFeature],
    relationships: Sequence[Mapping[str, Any]],
    links: Mapping[str, Mapping[str, Any]],
    nldi_full: Any | None = None,
    nldi_incremental: Any | None = None,
    *,
    target_basin: Any | None = None,
) -> dict[str, Any]:
    """Build a candidate only with directed reachability and complete outlet coverage."""
    canonical = str(point.get("canonical_nws_id", point.get("nws_point_id", "")))
    result: dict[str, Any] = {
        "canonical_nws_id": canonical,
        "geometry": None,
        "candidate_feature_ids": [],
        "candidate_status": "UNRESOLVED_NO_MATCHING_RFC_FEATURE",
        "connectivity_classification": "UNRESOLVED",
        "connectivity_confidence": "NONE",
        "historical_MAP_confidence": "NONE",
        "legacy_map_geometry_verified": False,
        "historical_map_equivalence": "NOT_ESTABLISHED",
        "candidate_area_sqmi": None,
        "candidate_union_area_sqmi": None,
        "candidate_raw_component_area_sum_sqmi": None,
        "nldi_reference_status": (
            "REFERENCE_AVAILABLE" if nldi_full is not None or nldi_incremental is not None
            else "NO_EXISTING_NLDI_REFERENCE"
        ),
        "full_nldi_metrics": None,
        "incremental_nldi_metrics": None,
        "nldi_full_geometry": nldi_full,
        "nldi_incremental_geometry": nldi_incremental,
        "unresolved_feature_ids": [],
        "reason": "",
    }
    exact = [feature for feature in features
             if str(feature.properties.get("NWSID", "")).strip() == canonical]
    if not exact:
        result["reason"] = "No RFC feature has an exact canonical NWSID attribute"
        return result
    if len(exact) > 1:
        result["candidate_status"] = "WITHHELD_AMBIGUOUS_RFC_MATCH"
        result["reason"] = "Multiple RFC source features have the exact NWSID attribute"
        result["unresolved_feature_ids"] = [feature.feature_id for feature in exact]
        return result
    target = exact[0]
    result["exact_rfc_feature_id"] = target.feature_id
    target_link = links.get(target.feature_id, {})
    if target_link.get("status") != "LINKED" or target_link.get("comid") is None:
        result["candidate_status"] = "WITHHELD_TARGET_OUTLET_UNLINKED"
        result["reason"] = target_link.get("reason", "Target RFC outlet has no verified COMID")
        result["unresolved_feature_ids"] = [target.feature_id]
        return result
    if target_basin is None or target_basin.is_empty or not target_basin.is_valid:
        result["candidate_status"] = "WITHHELD_TARGET_BASIN_ENVELOPE_MISSING"
        result["reason"] = "No valid NLDI routed full-basin geometry is available for completeness checking"
        result["unresolved_feature_ids"] = [target.feature_id]
        return result

    ancestors: dict[str, set[str]] = {feature.feature_id: set() for feature in features}
    for edge in relationships:
        upstream = str(edge["upstream_feature_id"])
        downstream = str(edge["downstream_feature_id"])
        ancestors.setdefault(downstream, set()).add(upstream)
    reachable = {target.feature_id}
    pending = [target.feature_id]
    while pending:
        downstream = pending.pop()
        for upstream in ancestors.get(downstream, set()):
            if upstream not in reachable:
                reachable.add(upstream)
                pending.append(upstream)

    expected = {feature.feature_id for feature in features
                if target_basin.covers(feature.outlet)}
    invalid_expected = {
        feature_id for feature_id in expected
        if links.get(feature_id, {}).get("status") != "LINKED"
        or feature_id not in reachable
    }
    outside_basin = {
        feature_id for feature_id in reachable
        if not target_basin.covers(next(f.outlet for f in features if f.feature_id == feature_id))
    }
    unresolved = sorted(invalid_expected | outside_basin)
    if invalid_expected or outside_basin:
        result["candidate_status"] = "WITHHELD_INCOMPLETE_ROUTED_COVERAGE"
        result["reason"] = (
            "NLDI basin outlet coverage disagrees with routed RFC reachability; "
            "candidate withheld rather than publishing a partial union"
        )
        result["unresolved_feature_ids"] = unresolved
        return result

    component_ids = sorted(reachable)
    component_features = [feature for feature in features if feature.feature_id in reachable]
    invalid_components = [
        feature for feature in component_features
        if not getattr(feature, "geometry_valid", True)
    ]
    if invalid_components:
        result["candidate_status"] = "WITHHELD_INVALID_SOURCE_COMPONENT"
        result["reason"] = (
            "Routed component includes invalid original RFC geometry; "
            "source was preserved without repair"
        )
        result["unresolved_feature_ids"] = sorted(
            feature.feature_id for feature in invalid_components
        )
        return result
    try:
        geometry = unary_union([feature.geometry for feature in component_features])
    except Exception:
        geometry = None
    if geometry is None or geometry.is_empty or not geometry.is_valid:
        result["candidate_status"] = "WITHHELD_INVALID_UNION"
        result["reason"] = "Union of routed RFC source polygons is empty or invalid"
        result["unresolved_feature_ids"] = component_ids
        return result
    result.update({
        "geometry": geometry,
        "candidate_feature_ids": component_ids,
        "candidate_status": "CANDIDATE_COMPLETE_ROUTED_COVERAGE",
        "connectivity_classification": "NHDPLUS_LINKED_PROXY",
        "connectivity_confidence": "MODERATE_ROUTED_NETWORK_PROXY",
        "candidate_area_sqmi": _area_sqmi(geometry),
        "candidate_union_area_sqmi": _area_sqmi(geometry),
        "candidate_raw_component_area_sum_sqmi": sum(f.area_sqmi for f in component_features),
        "full_nldi_metrics": compare_geometries(geometry, nldi_full),
        "incremental_nldi_metrics": compare_geometries(geometry, nldi_incremental),
        "reason": "Complete NHDPlus/NLDI routed candidate; historical MAP mask not verified",
    })
    return result


def write_station_outputs(
    points: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
    out_dir: Path,
) -> None:
    """Write a one-to-one 29-station reconciliation and separate candidate layer."""
    if len(points) != 29:
        raise ValueError(f"Expected exactly 29 historical forecast points, found {len(points)}")
    point_ids = [str(point.get("canonical_nws_id", point.get("nws_point_id", "")))
                 for point in points]
    if len(set(point_ids)) != 29 or "" in point_ids:
        raise ValueError("Historical point crosswalk must have 29 unique canonical IDs")
    by_id = {str(result.get("canonical_nws_id", "")): result for result in results}
    if len(by_id) != len(results) or set(by_id) != set(point_ids):
        raise ValueError("Candidate results must contain exactly one row per crosswalk point")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    metrics_names = ("reference_area_sqmi", "intersection_sqmi",
                     "union_sqmi", "iou_pct", "candidate_coverage_pct",
                     "reference_coverage_pct", "symmetric_difference_sqmi")
    fields = [
        "historical_point_id", "canonical_nws_id", "official_nws_name", "latitude",
        "longitude", "coordinate_source", "usgs_site_id_confirmed",
        "existing_dashboard_usgs_id", "mapping_status", "exact_rfc_feature_id",
        "rfc_source_archive_sha256",
        "candidate_status", "connectivity_classification", "candidate_feature_ids",
        "candidate_area_sqmi", "candidate_union_area_sqmi",
        "candidate_raw_component_area_sum_sqmi", "single_segment_area_sqmi", "nldi_reference_status",
        "full_nldi_reference_area_sqmi", "full_nldi_intersection_sqmi",
        "full_nldi_union_sqmi", "full_nldi_iou_pct", "full_nldi_candidate_coverage_pct",
        "full_nldi_reference_coverage_pct", "full_nldi_symmetric_difference_sqmi",
        "incremental_nldi_reference_area_sqmi", "incremental_nldi_intersection_sqmi",
        "incremental_nldi_union_sqmi", "incremental_nldi_iou_pct",
        "incremental_nldi_candidate_coverage_pct", "incremental_nldi_reference_coverage_pct",
        "incremental_nldi_symmetric_difference_sqmi", "connectivity_confidence",
        "historical_MAP_confidence", "historical_map_equivalence",
        "legacy_map_geometry_verified", "source_reference", "evidence", "uncertainty",
    ]
    reconciliation_json = []
    with (out_dir / "station_reconciliation.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for point in points:
            nwsli = str(point.get("canonical_nws_id", point.get("nws_point_id", "")))
            result = by_id[nwsli]
            full = result.get("full_nldi_metrics") or {}
            inc = result.get("incremental_nldi_metrics") or {}
            exact = result.get("exact_rfc_feature_id", "")
            row = {
                key: point.get(key, "") for key in (
                    "historical_point_id", "canonical_nws_id", "official_nws_name",
                    "latitude", "longitude", "coordinate_source", "usgs_site_id_confirmed",
                    "existing_dashboard_usgs_id", "mapping_status")
            }
            row.update({
                "exact_rfc_feature_id": exact,
                "rfc_source_archive_sha256": result.get("source_archive_sha256", ""),
                "candidate_status": result.get("candidate_status", "UNRESOLVED"),
                "connectivity_classification": result.get("connectivity_classification", "UNRESOLVED"),
                "candidate_feature_ids": ";".join(result.get("candidate_feature_ids", [])),
                "candidate_area_sqmi": result.get("candidate_area_sqmi", ""),
                "candidate_union_area_sqmi": result.get("candidate_union_area_sqmi", ""),
                "candidate_raw_component_area_sum_sqmi": result.get("candidate_raw_component_area_sum_sqmi", ""),
                "single_segment_area_sqmi": result.get("single_segment_area_sqmi", ""),
                "nldi_reference_status": result.get("nldi_reference_status", "NO_EXISTING_NLDI_REFERENCE"),
                "connectivity_confidence": result.get("connectivity_confidence", "NONE"),
                "historical_MAP_confidence": "NONE",
                "historical_map_equivalence": "NOT_ESTABLISHED",
                "legacy_map_geometry_verified": False,
                "source_reference": "NOAA 2018 b_lmrfc.tar.gz; IHABBS first-vertex outlet convention; USGS NLDI/NHDPlusV2 proxy where linked",
                "evidence": ";".join(result.get("candidate_feature_ids", [])),
                "uncertainty": result.get("reason", ""),
            })
            for prefix, metrics in (("full_nldi", full), ("incremental_nldi", inc)):
                for name in metrics_names:
                    row[f"{prefix}_{name}"] = metrics.get(name, "")
            writer.writerow(row)
            reconciliation_json.append({
                **row,
                "candidate_feature_ids": result.get("candidate_feature_ids", []),
            })

    (out_dir / "station_reconciliation.json").write_text(
        json.dumps(reconciliation_json, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    candidate_features = []
    reference_features = []
    issues = []
    for nwsli in point_ids:
        result = by_id[nwsli]
        geometry = result.get("geometry")
        if geometry is not None and not geometry.is_empty:
            candidate_features.append({
                "type": "Feature", "id": nwsli,
                "properties": {
                    "canonical_nws_id": nwsli,
                    "candidate_status": result.get("candidate_status"),
                    "connectivity_classification": result.get("connectivity_classification"),
                    "candidate_feature_ids": result.get("candidate_feature_ids", []),
                    "candidate_union_area_sqmi": result.get("candidate_union_area_sqmi"),
                    "candidate_raw_component_area_sum_sqmi": result.get("candidate_raw_component_area_sum_sqmi"),
                    "historical_map_equivalence": "NOT_ESTABLISHED",
                    "legacy_map_geometry_verified": False,
                    "source": "NOAA_2018_LMRFC_segments_union_using_NHDPlusV2_NLDI_proxy",
                },
                "geometry": mapping(geometry),
            })
        for layer_name, result_key in (
            ("full_upstream", "nldi_full_geometry"),
            ("incremental", "nldi_incremental_geometry"),
        ):
            reference_geometry = result.get(result_key)
            if reference_geometry is not None and not reference_geometry.is_empty:
                reference_features.append({
                    "type": "Feature", "id": f"{nwsli}:{layer_name}",
                    "properties": {
                        "canonical_nws_id": nwsli,
                        "layer": layer_name,
                        "usgs_site_id": result.get("nldi_reference_usgs_id", ""),
                        "reference_status": result.get("nldi_reference_status", ""),
                        "source": "Current repository NLDI geometry; verified Phase 2 same-site join",
                    },
                    "geometry": mapping(reference_geometry),
                })
        if result.get("candidate_status", "").startswith("WITHHELD") or result.get("candidate_status", "").startswith("UNRESOLVED"):
            issues.append({
                "canonical_nws_id": nwsli,
                "candidate_status": result.get("candidate_status", "UNRESOLVED"),
                "unresolved_feature_ids": ";".join(result.get("unresolved_feature_ids", [])),
                "reason": result.get("reason", ""),
            })
    (out_dir / "candidate_aggregates.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "name": "NLDI_routed_RFC_candidates",
                    "features": candidate_features}, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "nldi_reference_geometries.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "name": "verified_NLDI_references",
                    "features": reference_features}, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with (out_dir / "unresolved_issues.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "canonical_nws_id", "candidate_status", "unresolved_feature_ids", "reason"])
        writer.writeheader()
        writer.writerows(issues)


def load_verified_nldi_references(
    points: Sequence[Mapping[str, Any]],
    crosswalk: Sequence[Mapping[str, Any]],
    gages: Sequence[Mapping[str, Any]],
    basin_geojson: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Load current NLDI full/incremental geometries only for exact reviewed joins."""
    full_by_usgs = {
        str(feature.get("properties", {}).get("id")): shape(feature["geometry"])
        for feature in basin_geojson.get("features", [])
        if feature.get("properties", {}).get("id") and feature.get("geometry")
    }
    gages_by_id = {str(gage["id"]): gage for gage in gages}
    verified = {
        str(row["canonical_nws_id"]): str(row["existing_dashboard_usgs_id"])
        for row in crosswalk
        if row.get("canonical_nws_id")
        and row.get("existing_dashboard_usgs_id")
        and row.get("existing_dashboard_usgs_id") == row.get("usgs_site_id_confirmed")
    }
    references = {}
    for point in points:
        nwsli = str(point.get("canonical_nws_id", ""))
        usgs = verified.get(nwsli)
        if not usgs or usgs not in full_by_usgs or usgs not in gages_by_id:
            continue
        full = full_by_usgs[usgs]
        gage = gages_by_id[usgs]
        parents = [str(value) for value in gage.get("upstream_from", [])]
        if any(parent not in full_by_usgs for parent in parents):
            references[nwsli] = {"full": full, "incremental": None, "usgs_site_id": usgs,
                                 "status": "FULL_REFERENCE_ONLY_MISSING_PARENT"}
            continue
        try:
            incremental = full.difference(unary_union([full_by_usgs[parent] for parent in parents])) if parents else full
            if incremental.is_empty or not incremental.is_valid:
                raise ValueError("NLDI incremental reference is empty or invalid")
        except Exception:
            incremental = None
        references[nwsli] = {
            "full": full, "incremental": incremental, "usgs_site_id": usgs,
            "status": "VERIFIED_SAME_SITE_NLDI_REFERENCE",
        }
    return references


def run_reconstruction(
    archive_path: Path,
    cache_dir: Path,
    out_dir: Path,
    crosswalk_path: Path,
    basin_path: Path,
    gages_path: Path,
    *,
    refresh_nldi: bool = False,
    session: Any = None,
    sleep_seconds: float = 0.1,
) -> dict[str, Any]:
    """Build all Phase 4B source, network, station, and summary outputs."""
    archive_sha256 = hashlib.sha256(Path(archive_path).read_bytes()).hexdigest()
    features = load_rfc_features(archive_path, allow_invalid_geometry=True)
    points = json.loads(Path(crosswalk_path).read_text(encoding="utf-8"))
    gages = json.loads(Path(gages_path).read_text(encoding="utf-8"))
    existing_basins = json.loads(Path(basin_path).read_text(encoding="utf-8"))
    if not isinstance(points, list) or len(points) != 29:
        raise ValueError("Phase 2 crosswalk must contain exactly 29 historical points")
    network = fetch_network_cache(
        features, cache_dir, refresh=refresh_nldi, session=session,
        sleep_seconds=sleep_seconds,
    )
    edges, network_issues = build_relationships(
        features, network["links"], network["upstream_reach_sets"]
    )
    for feature in features:
        if not feature.geometry_valid:
            network_issues.append({
                "feature_id": feature.feature_id,
                "code": "RFC_SOURCE_GEOMETRY_INVALID",
                "reason": feature.geometry_issue,
            })
    write_network_outputs(
        features, network["links"], network["upstream_reach_sets"], edges,
        network_issues, out_dir, archive_sha256, basins=network["basins"],
        failures=network.get("failures", []),
        raw_responses=network.get("raw_responses", []),
    )
    references = load_verified_nldi_references(points, points, gages, existing_basins)
    basin_geometries = {
        int(comid): shape(data["geometry"])
        for comid, data in network.get("basins", {}).items()
        if data.get("geometry")
    }
    results = []
    for point in points:
        canonical = str(point["canonical_nws_id"])
        exact = [feature for feature in features
                 if str(feature.properties.get("NWSID", "")).strip() == canonical]
        target_link = network["links"].get(exact[0].feature_id, {}) if len(exact) == 1 else {}
        target_comid = target_link.get("comid") if target_link.get("status") == "LINKED" else None
        reference = references.get(canonical, {})
        result = build_station_candidate(
            point, features, edges, network["links"],
            reference.get("full"), reference.get("incremental"),
            target_basin=basin_geometries.get(int(target_comid)) if target_comid is not None else None,
        )
        if len(exact) == 1:
            result["exact_rfc_feature_id"] = exact[0].feature_id
            result["single_segment_area_sqmi"] = exact[0].area_sqmi
        else:
            result["exact_rfc_feature_id"] = ""
            result["single_segment_area_sqmi"] = None
        result["nldi_reference_status"] = reference.get("status", "NO_EXISTING_NLDI_REFERENCE")
        result["nldi_reference_usgs_id"] = reference.get("usgs_site_id", "")
        result["source_archive_sha256"] = archive_sha256
        results.append(result)
    write_station_outputs(points, results, out_dir)
    issue_path = Path(out_dir) / "unresolved_issues.csv"
    with issue_path.open(encoding="utf-8", newline="") as stream:
        unresolved_rows = list(csv.DictReader(stream))
    with issue_path.open("w", encoding="utf-8", newline="") as stream:
        issue_fields = ["entity_type", "entity_id", "canonical_nws_id",
                        "candidate_status", "unresolved_feature_ids", "reason"]
        writer = csv.DictWriter(stream, fieldnames=issue_fields)
        writer.writeheader()
        for row in unresolved_rows:
            writer.writerow({"entity_type": "HISTORICAL_POINT",
                             "entity_id": row.get("canonical_nws_id", ""), **row})
        for issue in network_issues:
            writer.writerow({
                "entity_type": "RFC_FEATURE", "entity_id": issue.get("feature_id", ""),
                "canonical_nws_id": "", "candidate_status": issue.get("code", "UNRESOLVED"),
                "unresolved_feature_ids": issue.get("feature_id", ""),
                "reason": issue.get("reason", ""),
            })
        for failure in network.get("failures", []):
            writer.writerow({
                "entity_type": "NLDI_REQUEST", "entity_id": failure.get("subject", ""),
                "canonical_nws_id": "", "candidate_status": "NLDI_REQUEST_FAILED",
                "unresolved_feature_ids": "", "reason": failure.get("error", ""),
            })
    summary_path = Path(out_dir) / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update({
        "historical_point_count": len(points),
        "candidate_count": sum(result.get("geometry") is not None for result in results),
        "withheld_or_unresolved_station_count": sum(result.get("geometry") is None for result in results),
        "legacy_map_equivalence_verified_count": 0,
        "invalid_source_geometry_count": sum(not feature.geometry_valid for feature in features),
        "station_status_counts": dict(__import__("collections").Counter(
            result.get("candidate_status", "UNRESOLVED") for result in results
        )),
        "source_archive_sha256": archive_sha256,
        "nldi_reference_source": "Existing Phase 2 verified USGS joins only; current NLDI geometry",
        "warning": "NLDI/NHDPlus topology is a modern routed-network proxy, not proof of legacy MAP geometry.",
    })
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("b_lmrfc.tar.gz"))
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/phase4b"))
    parser.add_argument("--out-dir", type=Path, default=Path("reports/phase4b"))
    parser.add_argument("--crosswalk", type=Path, default=Path(
        "historical/relationships/v1/source/Phase2_Forecast_Point_Crosswalk.json"))
    parser.add_argument("--basins", type=Path, default=Path("data/basins.geojson"))
    parser.add_argument("--gages", type=Path, default=Path("config/gages.json"))
    parser.add_argument("--refresh-nldi", action="store_true")
    args = parser.parse_args()
    summary = run_reconstruction(
        args.archive, args.cache_dir, args.out_dir, args.crosswalk,
        args.basins, args.gages, refresh_nldi=args.refresh_nldi,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


def _plain(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _outlet(geometry: Any) -> Any:
    from shapely.geometry import Point
    from shapely.geometry import MultiPolygon, Polygon

    if isinstance(geometry, Polygon):
        return Point(geometry.exterior.coords[0])
    if isinstance(geometry, MultiPolygon) and geometry.geoms:
        return Point(geometry.geoms[0].exterior.coords[0])
    raise ValueError("RFC feature geometry must be a Polygon or MultiPolygon")


def _safe_extract(archive_path: Path, target: Path) -> Path:
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            candidate = (target / member.name).resolve()
            if (
                not candidate.is_relative_to(target.resolve())
                or member.issym()
                or member.islnk()
            ):
                raise ValueError("Unsafe path or link in NOAA RFC archive")
        archive.extractall(target, filter="data")
    shapefiles = list(target.rglob("*.shp"))
    if len(shapefiles) != 1:
        raise ValueError(f"Expected one NOAA RFC shapefile, found {len(shapefiles)}")
    return shapefiles[0]


def load_rfc_features(
    archive_path: Path,
    *,
    expected_count: int = RFC_FEATURE_COUNT,
    expected_sha256: str | None = RFC_ARCHIVE_SHA256,
    allow_invalid_geometry: bool = False,
) -> list[RfcFeature]:
    """Verify and parse all RFC polygons without discarding source attributes."""
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise FileNotFoundError(f"NOAA RFC archive not found: {archive_path}")
    archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if expected_sha256 is not None and archive_hash != expected_sha256:
        raise ValueError(
            f"NOAA RFC archive SHA-256 mismatch: expected {expected_sha256}, "
            f"received {archive_hash}"
        )

    import geopandas as gpd

    with tempfile.TemporaryDirectory(prefix="phase4b-rfc-") as temp:
        shapefile = _safe_extract(archive_path, Path(temp))
        frame = gpd.read_file(shapefile)
        if frame.crs is None:
            raise ValueError("NOAA RFC shapefile has no declared coordinate system")
        missing_fields = set(RFC_FIELDS) - set(frame.columns)
        if missing_fields:
            raise ValueError(f"RFC shapefile is missing fields: {sorted(missing_fields)}")
        if len(frame) != expected_count:
            raise ValueError(
                f"Expected {expected_count} RFC features, found {len(frame)}"
            )
        frame = frame.to_crs("EPSG:4326")
        features: list[RfcFeature] = []
        seen: set[str] = set()
        for index, row in frame.iterrows():
            geometry = row.geometry
            if geometry is None or geometry.is_empty:
                raise ValueError(f"RFC feature {index} has missing or empty geometry")
            geometry_valid = bool(geometry.is_valid)
            geometry_issue = ""
            if not geometry_valid:
                from shapely.validation import explain_validity
                geometry_issue = explain_validity(geometry)
                if not allow_invalid_geometry:
                    raise ValueError(
                        f"RFC feature {index} has invalid geometry: {geometry_issue}"
                    )
            properties = {field: _plain(row[field]) for field in RFC_FIELDS}
            feature_id = str(properties["OBJ_IDENTIF"]).strip()
            if not feature_id or feature_id in seen:
                raise ValueError(f"Duplicate or blank RFC feature identifier: {feature_id}")
            seen.add(feature_id)
            area_sqmi = abs(GEOD.geometry_area_perimeter(geometry)[0]) / (
                SQUARE_METERS_PER_SQUARE_MILE
            )
            features.append(
                RfcFeature(
                    feature_index=int(index),
                    feature_id=feature_id,
                    properties=properties,
                    geometry=geometry,
                    outlet=_outlet(geometry),
                    area_sqmi=area_sqmi,
                    geometry_valid=geometry_valid,
                    geometry_issue=geometry_issue,
                )
            )
    return features


def write_source_inventory(
    features: list[RfcFeature], out_dir: Path, archive_sha256: str
) -> None:
    """Write the complete source field table and separately versioned polygons."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_feature_index",
        "source_feature_id",
        "source_archive_sha256",
        "source_geometry_valid",
        "source_geometry_issue",
        "outlet_longitude",
        "outlet_latitude",
        "geometry_area_sqmi",
        *RFC_FIELDS,
    ]
    with (out_dir / "rfc_feature_inventory.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for feature in features:
            writer.writerow(
                {
                    "source_feature_index": feature.feature_index,
                    "source_feature_id": feature.feature_id,
                    "source_archive_sha256": archive_sha256,
                    "source_geometry_valid": getattr(feature, "geometry_valid", True),
                    "source_geometry_issue": getattr(feature, "geometry_issue", ""),
                    "outlet_longitude": feature.outlet.x,
                    "outlet_latitude": feature.outlet.y,
                    "geometry_area_sqmi": feature.area_sqmi,
                    **feature.properties,
                }
            )
    collection = {
        "type": "FeatureCollection",
        "name": "NOAA_2018_LMRFC_IHABBS_source_segments",
        "source_archive_sha256": archive_sha256,
        "features": [
            {
                "type": "Feature",
                "id": feature.feature_id,
                "properties": {
                    "source_feature_index": feature.feature_index,
                    "source_feature_id": feature.feature_id,
                    "source_archive_sha256": archive_sha256,
                    "geometry_area_sqmi": feature.area_sqmi,
                    "scientific_status": "UNVERIFIED_LEGACY_MAP_GEOMETRY",
                    "source_geometry_valid": getattr(feature, "geometry_valid", True),
                    "source_geometry_issue": getattr(feature, "geometry_issue", ""),
                    **feature.properties,
                },
                "geometry": mapping(feature.geometry),
            }
            for feature in features
        ],
    }
    (out_dir / "rfc_single_segments.geojson").write_text(
        json.dumps(collection, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
