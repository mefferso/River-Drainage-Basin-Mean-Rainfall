#!/usr/bin/env python3
"""Build compact source-coverage JSON/CSV from a historical retrieval payload."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo


def summarize(payload):
    rows = []
    stations = {}
    for nwsli, station in payload["stations"].items():
        station_result = {
            "usgs_site_id": station["usgs_site_id"],
            "retrieved_at_utc": station["retrieved_at_utc"],
            "usgs_metadata_url": station["usgs_00065_time_series_metadata"].get("initial_request_url"),
            "usgs_series": station["usgs_00065_time_series_metadata"].get("series_summary", []),
            "annual_peaks": station["annual_peak_records"].get("summary", {}),
            "windows": {},
            "nwps": {},
            "source_overlaps": station.get("review_window_source_overlaps", {}),
        }
        for series in station_result["usgs_series"]:
            rows.append(_row(nwsli, station, "series_metadata", "", series.get("id"),
                             series.get("computation_period_identifier"),
                             series.get("computation_identifier"), series.get("begin_utc"),
                             series.get("end_utc"), None, None,
                             station["usgs_00065_time_series_metadata"].get("initial_request_url"),
                             station["usgs_00065_time_series_metadata"].get("error")))

        peak_summary = station_result["annual_peaks"]
        rows.append(_row(nwsli, station, "annual_peaks", "", "", "Water Year", "Peak records",
                         peak_summary.get("earliest_record_time"), peak_summary.get("latest_record_time"),
                         peak_summary.get("record_count"), None,
                         station["annual_peak_records"].get("initial_request_url"),
                         station["annual_peak_records"].get("error"),
                         details={"parameter_counts": peak_summary.get("records_by_parameter_code", {})}))

        for lead, window in station["daily_and_continuous_stage_review_windows"].items():
            station_result["windows"][lead] = {}
            for collection_key, collection_name in (("continuous_00065", "continuous"), ("daily_00065", "daily")):
                collection = window[collection_key]
                values = collection.get("values", [])
                approval_codes = sorted({str(x.get("approval_status")) for x in values if x.get("approval_status")})
                qualifier_codes = sorted({str(x.get("qualifier")) for x in values if x.get("qualifier") is not None})
                coverage = collection.get("coverage", {})
                rows_for_kind = []
                if coverage:
                    for series_id, item in coverage.items():
                        matching = [x for x in values if str(x.get("time_series_id") or x.get("statistic_id") or "unspecified") == str(series_id)]
                        row = _row(nwsli, station, collection_name, lead, series_id, "", "",
                                   item.get("first_time"), item.get("last_time"),
                                   item.get("observation_count"), item.get("largest_sample_gap_hours"),
                                   collection.get("initial_request_url"), collection.get("error"),
                                   approval_codes=sorted({str(x.get("approval_status")) for x in matching if x.get("approval_status")}),
                                   qualifier_codes=sorted({str(x.get("qualifier")) for x in matching if x.get("qualifier") is not None}))
                        rows.append(row)
                        rows_for_kind.append(row)
                else:
                    row = _row(nwsli, station, collection_name, lead, "", "", "", None, None,
                               len(collection.get("features", [])), None, collection.get("initial_request_url"),
                               collection.get("error"), approval_codes=approval_codes,
                               qualifier_codes=qualifier_codes)
                    rows.append(row)
                    rows_for_kind.append(row)
                station_result["windows"][lead][collection_name] = rows_for_kind
            continuous = window["continuous_00065"]
            samples = continuous.get("features", [])
            maximum = None
            if samples:
                feature = max(samples, key=lambda item: float(item.get("properties", {}).get("value", "-inf")))
                props = feature.get("properties", {})
                raw_time = props.get("time")
                local_time = None
                if raw_time:
                    instant = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
                    local_time = instant.astimezone(ZoneInfo("America/Chicago")).isoformat()
                maximum = {
                    "value_ft": float(props["value"]), "time_utc": raw_time,
                    "time_central": local_time, "approval_status": props.get("approval_status"),
                    "qualifier": props.get("qualifier"), "time_series_id": props.get("time_series_id"),
                    "source_url": continuous.get("initial_request_url"),
                    "status": "WINDOW_MAXIMUM_NOT_VERIFIED_FLOOD_CREST",
                }
                rows.append(_row(nwsli, station, "continuous_window_maximum_candidate", lead,
                                 props.get("time_series_id"), "Points", "Window maximum sample",
                                 raw_time, raw_time, 1, None, continuous.get("initial_request_url"),
                                 continuous.get("error"), approval_codes=[str(props.get("approval_status"))] if props.get("approval_status") else [],
                                 qualifier_codes=[str(props.get("qualifier"))] if props.get("qualifier") is not None else [],
                                 details=maximum))
            station_result["windows"][lead]["continuous_window_maximum_candidate"] = maximum

        for endpoint, item in station["noaa_nwps"].items():
            if endpoint == "gauge_metadata":
                count = item.get("historic_crest_count", 0)
                quality = item.get("historic_crest_quality") or {}
                start, end = (quality.get("timestamp_range_utc") or [None, None])
                details = {"preliminary_codes": quality.get("preliminary_codes", {}),
                           "olddatum_true_count": quality.get("olddatum_true_count")}
            else:
                count = item.get("timestamp_field_count", 0)
                start, end = item.get("earliest_timestamp_utc"), item.get("latest_timestamp_utc")
                details = {"note": "NWPS stageflow payload is current observation/forecast range, not long-term historical coverage."}
            station_result["nwps"][endpoint] = {
                "url": item.get("request_url"), "status_code": item.get("status_code"),
                "record_count": count, "start_utc": start, "end_utc": end,
                "quality": details, "error": item.get("error"),
            }
            if endpoint == "gauge_metadata":
                station_result["nwps"][endpoint]["station_metadata"] = {
                    key: item.get("raw_response", {}).get(key)
                    for key in ("timeZone", "datums", "usgsId", "name", "description")
                    if key in item.get("raw_response", {})
                }
            rows.append(_row(nwsli, station, f"nwps_{endpoint}", "", "", "", "",
                             start, end, count, None, item.get("request_url"), item.get("error"),
                             details=details))
        stations[nwsli] = station_result

    return {
        "schema_version": 1,
        "generated_at_utc": payload.get("generated_at_utc"),
        "status": payload.get("status"),
        "source_run_id": payload.get("source_run_id"),
        "source_artifact_id": payload.get("source_artifact_id"),
        "interpretation": payload.get("interpretation", []),
        "stations": stations,
        "csv_rows": rows,
    }


def _row(nwsli, station, source_type, lead, series_id, period, statistic,
         start, end, count, gap, url, error, *, approval_codes=None,
         qualifier_codes=None, details=None):
    return {
        "station": nwsli, "usgs_site_id": station["usgs_site_id"],
        "source_type": source_type, "legacy_date_lead_only": lead,
        "series_id": series_id, "period": period, "statistic": statistic,
        "start_utc": start, "end_utc": end, "observation_count": count,
        "largest_sample_gap_hours": gap,
        "approval_status_codes": ";".join(approval_codes or []),
        "qualifier_codes": ";".join(qualifier_codes or []),
        "source_url": url, "error": error,
        "details": json.dumps(details or {}, sort_keys=True, separators=(",", ":")),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Raw stage_source_availability.json retrieval")
    parser.add_argument("--json", type=Path, default=Path("reports/phase4d/stage_source_coverage.json"))
    parser.add_argument("--csv", type=Path, default=Path("reports/phase4d/stage_source_coverage.csv"))
    parser.add_argument("--source-run-id", type=int)
    parser.add_argument("--source-artifact-id", type=int)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if args.source_run_id is not None:
        payload["source_run_id"] = args.source_run_id
    if args.source_artifact_id is not None:
        payload["source_artifact_id"] = args.source_artifact_id
    result = summarize(payload)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps({k: v for k, v in result.items() if k != "csv_rows"}, indent=2) + "\n", encoding="utf-8")
    fields = list(result["csv_rows"][0])
    with args.csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(result["csv_rows"])


if __name__ == "__main__":
    main()
