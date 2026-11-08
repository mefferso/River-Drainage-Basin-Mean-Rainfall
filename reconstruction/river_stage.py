#!/usr/bin/env python3
"""Retrieve real USGS stage observations for AMIL1/MNLM6; never infer unavailable data.

USGS Water Services JSON uses UTC timestamps with explicit offsets.
This deliberately does not infer a crest from daily statistics or legacy dates.
"""
from __future__ import annotations
import argparse
import csv
import json
import math
import os
import pathlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode
import requests

POINTS = {"AMIL1": "07375430", "MNLM6": "02492360"}
BASE = "https://waterservices.usgs.gov/nwis/iv/"
USER_AGENT = "River-Basin-Mean-Rainfall/0.1 (scientific research; github.com/mefferso/River-Drainage-Basin-Mean-Rainfall)"


def time_utc(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc)


def request_stage(site_id, start, end, session=None):
    """Return parsed hourly/subhourly stage series with provenance, or raise."""
    if not start < end:
        raise ValueError("Start must precede end")
    if end - start > timedelta(days=120):
        raise ValueError("Request at most 120 days per call")
    params = {
        "format": "json", "sites": site_id, "parameterCd": "00065",
        "startDT": start.isoformat(timespec="seconds"),
        "endDT": end.isoformat(timespec="seconds"),
        "siteStatus": "all",
    }
    sess = session or requests.Session()
    url = BASE + "?" + urlencode(params)
    response = sess.get(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=45)
    response.raise_for_status()
    doc = response.json()
    records, series_metadata = [], []
    for series in doc.get("value", {}).get("timeSeries", []):
        var = series.get("variable", {})
        if str(var.get("variableCode", [{}])[0].get("value")) != "00065":
            continue
        site = series.get("sourceInfo", {})
        units = var.get("unit", {}).get("unitCode")
        if units != "ft":
            raise ValueError("Unsupported or missing USGS stage units: " + str(units))
        code = str(site.get("siteCode", [{}])[0].get("value", ""))
        if code != site_id:
            raise ValueError("USGS response site mismatch")
        series_metadata.append({
            "site_id": code, "variable": "00065",
            "site_name": site.get("siteName"), "units": units,
            "site_property": site.get("geoLocation"),
            "series_name": series.get("name"),
        })
        for group in series.get("values", []):
            for item in group.get("value", []):
                try:
                    stage = float(item["value"])
                except (KeyError, ValueError, TypeError):
                    continue
                if not math.isfinite(stage) or stage <= -999:
                    continue
                at = time_utc(item["dateTime"])
                if not start <= at <= end:
                    continue
                records.append({
                    "time_utc": at.isoformat(), "stage_ft": stage,
                    "qualifiers": item.get("qualifiers", []),
                    "source": "USGS NWIS instantaneous values, parameter 00065",
                    "site_id": site_id, "source_url": url,
                })
    deduplicated = {}
    for r in records:
        key = (r["time_utc"], r["stage_ft"])
        deduplicated[key] = r
    records = sorted(deduplicated.values(), key=lambda r: (r["time_utc"], r["stage_ft"]))
    return {"site_id": site_id, "request_url": url,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "series_metadata": series_metadata, "observations": records}


def crest_candidates(observations, min_stage_ft=None, separation_hours=6,
                     min_prominence_ft=0.10):
    """Return provisional local crest candidates with conservative ripple grouping.

    Adjacent local maxima within ``separation_hours`` are grouped only when the
    observed valley between them is shallower than ``min_prominence_ft`` below
    the lower peak. A deeper valley keeps both potential crests. Neighbors more
    than six hours away are never used to assert a local peak. Gaps, qualifiers,
    and source provenance remain review concerns; this does not verify events.
    """
    obs = sorted(observations, key=lambda r: r["time_utc"])
    peaks = []
    for i in range(1, len(obs) - 1):
        before, current, after = obs[i-1], obs[i], obs[i+1]
        h = current["stage_ft"]
        if (h >= before["stage_ft"] and h > after["stage_ft"] and
                (min_stage_ft is None or h >= min_stage_ft)):
            left = time_utc(before["time_utc"])
            middle = time_utc(current["time_utc"])
            right = time_utc(after["time_utc"])
            if max((middle-left).total_seconds(), (right-middle).total_seconds()) > 21600:
                continue
            peaks.append(current)
    peaks = sorted(peaks, key=lambda r: r["time_utc"])
    clusters = []
    for peak in peaks:
        if not clusters:
            clusters.append([peak])
            continue
        previous = clusters[-1][-1]
        separation = (time_utc(peak["time_utc"])-time_utc(previous["time_utc"])).total_seconds()/3600
        valley = [item["stage_ft"] for item in obs
                  if time_utc(previous["time_utc"]) < time_utc(item["time_utc"]) < time_utc(peak["time_utc"])]
        shallow_ripple = bool(valley) and min(previous["stage_ft"], peak["stage_ft"]) - min(valley) < min_prominence_ft
        if separation < separation_hours and shallow_ripple:
            if peak["stage_ft"] >= clusters[-1][-1]["stage_ft"]:
                clusters[-1][-1] = peak
        else:
            clusters.append([peak])
    selected = [cluster[-1] for cluster in clusters]
    return sorted([{
        "site_id": p["site_id"], "candidate_time_utc": p["time_utc"],
        "candidate_stage_ft": p["stage_ft"], "qualifiers": p["qualifiers"],
        "source_url": p["source_url"], "status": "CANDIDATE_UNVERIFIED",
        "minimum_peak_separation_hours": separation_hours,
        "minimum_prominence_ft": min_prominence_ft,
        "note": "Local maximum candidate after shallow-ripple grouping; not a verified flood crest",
    } for p in selected], key=lambda r: r["candidate_time_utc"])


def run(start, end, output):
    result = {
        "schema_version": 1, "requested_start_utc": start.isoformat(),
        "requested_end_utc": end.isoformat(),
        "coverage_status": {}, "candidate_crests": [], "observations": [],
        "scientific_status": "UNVERIFIED_STAGE_CANDIDATES",
    }
    for nwsli, site in POINTS.items():
        try:
            dataset = request_stage(site, start, end)
            count = len(dataset["observations"])
            result["coverage_status"][nwsli] = {
                "usgs_site": site, "request_url": dataset["request_url"],
                "retrieved_at_utc": dataset["retrieved_at_utc"],
                "observation_count": count,
                "first_utc": dataset["observations"][0]["time_utc"] if count else None,
                "last_utc": dataset["observations"][-1]["time_utc"] if count else None,
                "status": "OBSERVATIONS_RETRIEVED" if count else "NO_OBSERVATIONS_RETURNED",
                "datum_history": "NOT_VERIFIED",
            }
            for obs in dataset["observations"]:
                result["observations"].append({"nwsli": nwsli, **obs})
            for candidate in crest_candidates(dataset["observations"]):
                result["candidate_crests"].append({"nwsli": nwsli, **candidate})
        except (requests.RequestException, ValueError, KeyError) as exc:
            result["coverage_status"][nwsli] = {
                "usgs_site": site, "status": "RETRIEVAL_ERROR", "error": str(exc),
                "datum_history": "NOT_VERIFIED",
            }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "coverage_status": result["coverage_status"],
        "candidate_counts": {k: sum(c["nwsli"] == k for c in result["candidate_crests"]) for k in POINTS},
        "output": str(output),
    }, indent=2))
    if all(v["status"] == "RETRIEVAL_ERROR" for v in result["coverage_status"].values()):
        raise SystemExit("Both USGS requests failed; report saved; no observations invented")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="UTC ISO 8601 with offset")
    parser.add_argument("--end", required=True, help="UTC ISO 8601 with offset")
    parser.add_argument("--output", type=pathlib.Path, default=pathlib.Path("reconstruction/results/stage_probe.json"))
    args = parser.parse_args()
    run(time_utc(args.start), time_utc(args.end), args.output)


if __name__ == "__main__":
    main()
