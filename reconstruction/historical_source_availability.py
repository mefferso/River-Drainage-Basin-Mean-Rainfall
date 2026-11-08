#!/usr/bin/env python3
"""Retrieve source metadata and sampled stage/peak records without crest inference."""
from __future__ import annotations
import argparse
import csv
import io
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode

import requests

ROOT = Path(__file__).resolve().parents[1]
SITES = {"AMIL1": "07375430", "MNLM6": "02492360"}
LEADS = ("2016-08-13", "2017-04-04", "2018-12-28")
USGS = "https://waterservices.usgs.gov/nwis"
NWPS = "https://api.water.noaa.gov/nwps/v1"


def _request(session, url, *, accept="application/json"):
    response = session.get(url, timeout=60, headers={
        "User-Agent": "River-Basin-Mean-Rainfall/0.1 historical source coverage audit",
        "Accept": accept,
    })
    response.raise_for_status()
    return response


def _query(base, params):
    return base + "?" + urlencode(params)


def _parse_rdb(text):
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    if len(lines) < 2:
        return [], []
    reader = csv.DictReader(io.StringIO("\n".join(line for line in lines if not line.startswith("5s"))), delimiter="\t")
    fields = reader.fieldnames or []
    return fields, list(reader)


def _recursive_dates(obj):
    """Summarize ISO timestamp fields without assuming an API schema."""
    found = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and ("time" in key.lower() or "date" in key.lower()):
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if parsed.tzinfo:
                        found.append(parsed.astimezone(timezone.utc).isoformat())
                except ValueError:
                    pass
            else:
                found.extend(_recursive_dates(value))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_recursive_dates(value))
    return found


def retrieve(session=None, now=None):
    sess = session or requests.Session()
    retrieved = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    stations = {}
    for nwsli, site in SITES.items():
        result = {"usgs_site_id": site, "nwsli": nwsli, "retrieved_at_utc": retrieved}
        # USGS site service series catalog reports the available time-series intervals.
        url = _query(f"{USGS}/site/", {"format": "rdb", "sites": site,
                      "siteOutput": "expanded", "seriesCatalogOutput": "true",
                      "parameterCd": "00065"})
        try:
            response = _request(sess, url, accept="text/tab-separated-values")
            fields, rows = _parse_rdb(response.text)
            result["instantaneous_00065_series_catalog"] = {
                "request_url": url, "status_code": response.status_code,
                "fields": fields, "rows": rows,
                "coverage_start": min((r.get("begin_date", "") for r in rows if r.get("begin_date")), default=None),
                "coverage_end": max((r.get("end_date", "") for r in rows if r.get("end_date")), default=None),
            }
        except Exception as exc:
            result["instantaneous_00065_series_catalog"] = {"request_url": url, "error": str(exc)}

        # Annual peaks are discrete peak-flow records, not an event-complete flood inventory.
        url = _query(f"{USGS}/peak/", {"format": "json", "sites": site})
        try:
            response = _request(sess, url)
            body = response.json()
            series = body.get("value", {}).get("timeSeries", [])
            peak_count = sum(len(group.get("value", []))
                             for item in series for group in item.get("values", []))
            result["annual_peak_records"] = {
                "request_url": url, "status_code": response.status_code,
                "series_count": len(series), "record_count": peak_count,
                "raw_response": body,
            }
        except Exception as exc:
            result["annual_peak_records"] = {"request_url": url, "error": str(exc)}

        result["daily_stage_00065_samples"] = []
        for lead in LEADS:
            day = datetime.strptime(lead, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start, end = (day-timedelta(days=3)).date().isoformat(), (day+timedelta(days=6)).date().isoformat()
            url = _query(f"{USGS}/dv/", {"format": "json", "sites": site, "parameterCd": "00065",
                          "startDT": start, "endDT": end})
            try:
                response = _request(sess, url)
                body = response.json()
                series = body.get("value", {}).get("timeSeries", [])
                result["daily_stage_00065_samples"].append({
                    "date_lead_only": lead, "request_url": url, "status_code": response.status_code,
                    "series": series,
                })
            except Exception as exc:
                result["daily_stage_00065_samples"].append({"date_lead_only": lead, "request_url": url, "error": str(exc)})

        nws = {}
        for label, suffix in (("gauge_metadata", ""), ("stageflow", "/stageflow")):
            url = f"{NWPS}/gauges/{nwsli}{suffix}"
            try:
                response = _request(sess, url)
                body = response.json()
                dates = _recursive_dates(body)
                nws[label] = {
                    "request_url": url, "status_code": response.status_code,
                    "top_level_keys": sorted(body) if isinstance(body, dict) else [],
                    "timestamp_field_count": len(dates), "earliest_timestamp_utc": min(dates) if dates else None,
                    "latest_timestamp_utc": max(dates) if dates else None,
                    "raw_response": body,
                }
            except Exception as exc:
                nws[label] = {"request_url": url, "error": str(exc)}
        result["noaa_nwps"] = nws
        stations[nwsli] = result
    return {
        "schema_version": 1, "generated_at_utc": retrieved,
        "status": "SOURCE_AVAILABILITY_PROBE_NOT_EVENT_VALIDATION",
        "interpretation": [
            "Instantaneous/daily series metadata and samples describe source availability only.",
            "Annual peak-flow records are not a complete inventory of smaller flood events.",
            "NWPS stageflow availability does not establish a historical crest unless a timestamped observed record is returned and checked.",
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
    compact = {nwsli: {
        "iv_series": len(station.get("instantaneous_00065_series_catalog", {}).get("rows", [])),
        "iv_period": [station.get("instantaneous_00065_series_catalog", {}).get("coverage_start"), station.get("instantaneous_00065_series_catalog", {}).get("coverage_end")],
        "annual_peak_records": station.get("annual_peak_records", {}).get("record_count"),
        "nwps": {key: {k: val.get(k) for k in ("status_code", "timestamp_field_count", "earliest_timestamp_utc", "latest_timestamp_utc", "error")} for key,val in station["noaa_nwps"].items()},
    } for nwsli,station in result["stations"].items()}
    print(json.dumps({"status": result["status"], "stations": compact, "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
