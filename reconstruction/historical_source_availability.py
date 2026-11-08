#!/usr/bin/env python3
"""Probe authoritative USGS and NOAA time-series, daily, peak and crest sources."""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
SITES = {"AMIL1": "07375430", "MNLM6": "02492360"}
LEADS = ("2016-03-12", "2016-08-13", "2017-04-03", "2017-04-04", "2018-12-28",
         "2019-04-20", "2019-05-12", "2020-06-08", "2026-10-31")
USGS = "https://api.waterdata.usgs.gov/ogcapi/v0/collections"
NWPS = "https://api.water.noaa.gov/nwps/v1"


def _request(session, url):
    response = session.get(url, timeout=60, headers={
        "User-Agent": "River-Basin-Mean-Rainfall/0.1 historical source coverage audit",
        "Accept": "application/geo+json, application/json",
    })
    response.raise_for_status()
    return response


def _collection(session, name, params):
    url = f"{USGS}/{name}/items?" + urlencode(params)
    features, pages = [], []
    next_url = url
    for _ in range(50):
        response = _request(session, next_url)
        body = response.json()
        pages.append({"request_url": next_url, "status_code": response.status_code,
                      "returned_features": len(body.get("features", []))})
        features.extend(body.get("features", []))
        link = next((item.get("href") for item in body.get("links", [])
                     if item.get("rel") == "next" and item.get("href")), None)
        if not link:
            break
        next_url = urljoin(next_url, link)
    else:
        raise ValueError(f"Pagination exceeded 50 pages for {name}")
    return {"collection": name, "initial_request_url": url, "page_count": len(pages),
            "features": features, "pages": pages}


def _timestamps(obj, path=""):
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            full = f"{path}.{key}" if path else key
            if isinstance(value, str) and ("time" in key.lower() or "date" in key.lower()):
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if parsed.tzinfo:
                        found.append({"path": full, "utc": parsed.astimezone(timezone.utc).isoformat()})
                except ValueError:
                    pass
            else:
                found.extend(_timestamps(value, full))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_timestamps(value, path))
    return found


def _find_key(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            result = _find_key(value, key)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for value in obj:
            result = _find_key(value, key)
            if result is not None:
                return result
    return None


def _quality_summary(features):
    values = []
    for feature in features:
        props = feature.get("properties", {})
        values.append({k: props.get(k) for k in ("time", "value", "unit_of_measure", "approval_status", "qualifier", "parameter_code", "statistic_id", "time_series_id") if k in props})
    return values


def _peak_summary(features):
    properties = [feature.get("properties", {}) for feature in features]
    codes = {}
    for item in properties:
        code = str(item.get("parameter_code") or "UNKNOWN")
        codes[code] = codes.get(code, 0) + 1
    dates = [str(item.get("time")) for item in properties if item.get("time")]
    return {
        "record_count": len(properties), "records_by_parameter_code": codes,
        "earliest_record_time": min(dates) if dates else None,
        "latest_record_time": max(dates) if dates else None,
        "records": [{k: item.get(k) for k in (
            "monitoring_location_id", "parameter_code", "time", "value", "unit_of_measure",
            "water_year", "qualifier", "approval_status") if k in item}
            for item in properties],
    }


def _crest_quality_summary(records):
    counts = {}
    for record in records:
        code = str(record.get("preliminary") or "UNSPECIFIED")
        counts[code] = counts.get(code, 0) + 1
    return {
        "record_count": len(records), "preliminary_codes": counts,
        "olddatum_true_count": sum(record.get("olddatum") is True for record in records),
        "timestamp_range_utc": [
            min((str(record.get("occurredTime")) for record in records if record.get("occurredTime")), default=None),
            max((str(record.get("occurredTime")) for record in records if record.get("occurredTime")), default=None),
        ],
    }


def _lead_window_overlaps(records, time_field, leads):
    """List source records inside review windows; never equate them to legacy events."""
    matches = []
    for lead in leads:
        day = datetime.strptime(lead, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        start, end = day-timedelta(days=3), day+timedelta(days=6)
        for record in records:
            raw = record.get(time_field)
            if not raw:
                continue
            try:
                at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if at.tzinfo is None:
                    continue
                at = at.astimezone(timezone.utc)
            except ValueError:
                continue
            if start <= at < end:
                matches.append({"legacy_date_lead_only": lead, "source_record": record,
                                "status": "DATE_WINDOW_OVERLAP_NOT_EVENT_MATCH"})
    return matches


def retrieve(session=None, now=None):
    sess = session or requests.Session()
    retrieved = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    stations = {}
    for nwsli, site in SITES.items():
        location = f"USGS-{site}"
        try:
            metadata = _collection(sess, "time-series-metadata", {
                "f": "json", "monitoring_location_id": location, "parameter_code": "00065",
                "limit": 1000, "skipGeometry": "true",
            })
        except Exception as exc:
            metadata = {"collection": "time-series-metadata", "initial_request_url": None,
                        "page_count": 0, "features": [], "pages": [], "error": str(exc)}
        metadata_features = [f for f in metadata["features"]
                             if str(f.get("properties", {}).get("parameter_code")) == "00065"]
        metadata["features"] = metadata_features
        metadata["series_summary"] = [{k: f.get("properties", {}).get(k) for k in (
            "id", "monitoring_location_id", "parameter_code", "parameter_name", "statistic_id",
            "computation_period_identifier", "computation_identifier", "unit_of_measure",
            "begin", "end", "begin_utc", "end_utc", "web_description")}
            for f in metadata_features]

        station = {"nwsli": nwsli, "usgs_site_id": site, "usgs_monitoring_location_id": location,
                   "retrieved_at_utc": retrieved, "usgs_00065_time_series_metadata": metadata}
        stage_samples = {}
        for lead in LEADS:
            day = datetime.strptime(lead, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start, end = day-timedelta(days=3), day+timedelta(days=6)
            interval = f"{start.date().isoformat()}T00:00:00Z/{end.date().isoformat()}T00:00:00Z"
            query = {"f": "json", "monitoring_location_id": location, "parameter_code": "00065",
                     "datetime": interval, "limit": 1000, "skipGeometry": "true"}
            try:
                continuous = _collection(sess, "continuous", query)
            except Exception as exc:
                continuous = {"collection": "continuous", "initial_request_url": None,
                              "page_count": 0, "features": [], "pages": [], "error": str(exc)}
            try:
                daily = _collection(sess, "daily", query)
            except Exception as exc:
                daily = {"collection": "daily", "initial_request_url": None,
                         "page_count": 0, "features": [], "pages": [], "error": str(exc)}
            stage_samples[lead] = {
                "review_window_utc": [start.isoformat(), end.isoformat()],
                "continuous_00065": {**continuous, "values": _quality_summary(continuous["features"])},
                "daily_00065": {**daily, "values": _quality_summary(daily["features"])},
            }

        try:
            peaks = _collection(sess, "peaks", {"f": "json", "monitoring_location_id": location,
                                                  "limit": 1000, "skipGeometry": "true"})
        except Exception as exc:
            peaks = {"collection": "peaks", "initial_request_url": None,
                     "page_count": 0, "features": [], "pages": [], "error": str(exc)}
        peaks["records"] = [{k: f.get("properties", {}).get(k) for k in f.get("properties", {})}
                            for f in peaks["features"]]
        peaks["summary"] = _peak_summary(peaks["features"])
        station["annual_peak_records"] = peaks
        station["daily_and_continuous_stage_review_windows"] = stage_samples

        nwps = {}
        for label, suffix in (("gauge_metadata", ""), ("stageflow", "/stageflow")):
            url = f"{NWPS}/gauges/{nwsli}{suffix}"
            try:
                response = _request(sess, url)
                body = response.json()
                timestamps = _timestamps(body)
                historic = _find_key(body, "historic") if label == "gauge_metadata" else None
                recent = _find_key(body, "recent") if label == "gauge_metadata" else None
                nwps[label] = {
                    "request_url": url, "status_code": response.status_code,
                    "top_level_keys": sorted(body) if isinstance(body, dict) else [],
                    "timestamp_field_count": len(timestamps),
                    "earliest_timestamp_utc": min((x["utc"] for x in timestamps), default=None),
                    "latest_timestamp_utc": max((x["utc"] for x in timestamps), default=None),
                    "historic_crests": historic if isinstance(historic, list) else [],
                    "historic_crest_count": len(historic) if isinstance(historic, list) else 0,
                    "recent_crests": recent if isinstance(recent, list) else [],
                    "recent_crest_count": len(recent) if isinstance(recent, list) else 0,
                    "historic_crest_quality": _crest_quality_summary(historic) if isinstance(historic, list) else None,
                    "recent_crest_quality": _crest_quality_summary(recent) if isinstance(recent, list) else None,
                    "raw_response": body,
                }
            except Exception as exc:
                nwps[label] = {"request_url": url, "error": str(exc)}
        gauge = nwps.get("gauge_metadata", {})
        station["review_window_source_overlaps"] = {
            "legacy_date_leads_are_search_windows_only": True,
            "usgs_annual_peak_record_overlaps": _lead_window_overlaps(
                station["annual_peak_records"].get("records", []), "time", LEADS),
            "nwps_historic_crest_overlaps": _lead_window_overlaps(
                gauge.get("historic_crests", []), "occurredTime", LEADS),
            "nwps_recent_crest_overlaps": _lead_window_overlaps(
                gauge.get("recent_crests", []), "occurredTime", LEADS),
        }
        station["noaa_nwps"] = nwps
        stations[nwsli] = station
    return {
        "schema_version": 1, "generated_at_utc": retrieved,
        "status": "SOURCE_AVAILABILITY_PROBE_NOT_EVENT_VALIDATION",
        "interpretation": [
            "USGS continuous and daily time series are distinct record types; metadata dates indicate series bounds and may include internal gaps.",
            "USGS annual peak-flow records are not a complete inventory of smaller flood events.",
            "NOAA NWPS historical crest records preserve preliminary observed/recorded and olddatum attributes; they require source-level matching before comparison.",
            "Daily values never supply a crest time.",
        ],
        "stations": stations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/phase4d/stage_source_availability.json")
    args = parser.parse_args()
    result = retrieve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    compact = {}
    for nwsli, station in result["stations"].items():
        metadata = station["usgs_00065_time_series_metadata"]["series_summary"]
        compact[nwsli] = {
            "usgs_00065_series_count": len(metadata),
            "usgs_00065_series": metadata,
            "usgs_00065_metadata_error": station["usgs_00065_time_series_metadata"].get("error"),
            "annual_peak_count": len(station["annual_peak_records"]["features"]),
            "annual_peak_summary": station["annual_peak_records"].get("summary"),
            "annual_peak_error": station["annual_peak_records"].get("error"),
            "annual_peak_window_overlap_count": len(station["review_window_source_overlaps"]["usgs_annual_peak_record_overlaps"]),
            "nwps_historic_window_overlap_count": len(station["review_window_source_overlaps"]["nwps_historic_crest_overlaps"]),
            "nwps_recent_window_overlap_count": len(station["review_window_source_overlaps"]["nwps_recent_crest_overlaps"]),
            "review_window_observation_counts": {date: {
                kind: len(stage[kind]["features"]) for kind in ("continuous_00065", "daily_00065")
            } for date, stage in station["daily_and_continuous_stage_review_windows"].items()},
            "review_window_errors": {date: {
                kind: stage[kind].get("error") for kind in ("continuous_00065", "daily_00065")
            } for date, stage in station["daily_and_continuous_stage_review_windows"].items()},
            "nwps": {key: {k: val.get(k) for k in (
                "status_code", "timestamp_field_count", "earliest_timestamp_utc", "latest_timestamp_utc",
                "historic_crest_count", "recent_crest_count", "historic_crest_quality",
                "recent_crest_quality", "error")}
                for key,val in station["noaa_nwps"].items()},
        }
    print(json.dumps({"status": result["status"], "stations": compact, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
