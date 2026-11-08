#!/usr/bin/env python3
"""Source-traceable stage inventory around selected legacy *date leads*.

A day written in a source spreadsheet selects a review interval, NOT a crest
timestamp. Observed maxima here are review candidates only. No row is added
to approved MAP-to-crest data and no source date is reinterpreted.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
try:
    from .river_stage import POINTS, request_stage, time_utc
except ImportError:
    from river_stage import POINTS, request_stage, time_utc

ROOT = Path(__file__).resolve().parents[1]
# 2016 and 2018 provide cross-station legacy leads; 2019 and 2026 sample MNLM6.
TARGET_DATES = ("2016-03-12", "2016-08-13", "2017-04-03", "2017-04-04", "2018-12-28", "2019-04-20", "2019-05-12", "2020-06-08", "2026-10-31")
BEFORE_DAYS = 3
AFTER_DAYS = 6
MAX_SAMPLE_GAP_HOURS = 6


def legacy_leads(source_dir, dates=TARGET_DATES):
    found = []
    for nwsli in POINTS:
        payload = json.loads((Path(source_dir) / f"{nwsli}.json").read_text())
        if payload.get("nws_point_id") != nwsli:
            raise ValueError("Legacy point identity mismatch " + nwsli)
        for row in payload["map_events"]:
            if row.get("event_date") in dates and row.get("quality_tier") == "B":
                found.append({
                    "nwsli": nwsli, "usgs_site_id": POINTS[nwsli],
                    "legacy_record_id": row["record_id"], "legacy_date_lead": row["event_date"],
                    "legacy_map_inches": row.get("map_inches"),
                    "legacy_crest_feet": row.get("crest_feet"),
                    "source_workbook": row.get("source_workbook"),
                    "source_worksheet": row.get("source_worksheet"),
                    "source_row": row.get("source_row"),
                })
    return sorted(found, key=lambda v: (v["legacy_date_lead"], v["nwsli"], v["legacy_record_id"]))


def summarize_window(lead, stage_data, start, end):
    observations = stage_data["observations"]
    times = [time_utc(r["time_utc"]) for r in observations]
    gap_hours = max(((b-a).total_seconds()/3600 for a,b in zip(times,times[1:])), default=None)
    largest = max((r["stage_ft"] for r in observations), default=None)
    maxima = [r for r in observations if r["stage_ft"] == largest] if largest is not None else []
    # Plateau of maximum stage has no independently confirmed single crest time.
    representative = maxima[0] if maxima else None
    flags = ["LEGACY_DATE_NOT_VERIFIED_AS_CREST_DAY", "HISTORICAL_DATUM_NOT_RECONCILED",
             "RAINFALL_EVENT_WINDOW_NOT_DETERMINED", "NO_QPE_MAP_RECONSTRUCTION"]
    if not observations:
        flags.append("NO_INSTANTANEOUS_STAGE_RETURNED")
    if times and (times[0]-start > timedelta(hours=MAX_SAMPLE_GAP_HOURS) or
                  end-times[-1] > timedelta(hours=MAX_SAMPLE_GAP_HOURS)):
        flags.append("EDGE_COVERAGE_INCOMPLETE")
    if gap_hours is not None and gap_hours > MAX_SAMPLE_GAP_HOURS:
        flags.append("INTERNAL_STAGE_GAP_GT_6H")
    if len(maxima) > 1:
        flags.append("TIED_MAXIMUM_STAGE")
    if representative and representative["qualifiers"]:
        flags.append("OBSERVATION_QUALIFIERS_REQUIRE_REVIEW")
    return {
        **lead, "observed_window_start_utc": start.isoformat(),
        "observed_window_end_utc": end.isoformat(),
        "observation_count": len(observations),
        "first_observed_utc": times[0].isoformat() if times else None,
        "last_observed_utc": times[-1].isoformat() if times else None,
        "maximum_sample_gap_hours": round(gap_hours, 3) if gap_hours is not None else None,
        "candidate_max_stage_ft": largest,
        "candidate_max_time_utc": representative["time_utc"] if representative else None,
        "candidate_max_tied_observations": len(maxima),
        "candidate_qualifiers": representative["qualifiers"] if representative else [],
        "usgs_source_url": stage_data["request_url"],
        "retrieved_at_utc": stage_data["retrieved_at_utc"],
        "review_status": "OBSERVED_WINDOW_MAXIMUM_NOT_VERIFIED_EVENT_CREST" if observations else "NO_STAGE_DATA",
        "qc_flags": flags,
    }


def make_inventory(source_dir, request_fn=request_stage, dates=TARGET_DATES):
    leads = legacy_leads(source_dir, dates)
    output = []
    coverage = []
    # Group same station+date; multiple legacy rows cannot multiply stage requests.
    groups = defaultdict(list)
    for row in leads:
        groups[(row["nwsli"], row["legacy_date_lead"])].append(row)
    for (nwsli, date), group in sorted(groups.items(), key=lambda x:x[0]):
        local_day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        # Day labels lack time zone semantics; window is deliberately generous.
        start = local_day - timedelta(days=BEFORE_DAYS)
        end = local_day + timedelta(days=AFTER_DAYS)
        try:
            data = request_fn(POINTS[nwsli], start, end)
            coverage.append({"nwsli":nwsli,"legacy_date_lead":date,
                             "status":"RETRIEVED","observations":len(data["observations"])})
            output.extend(summarize_window(row, data, start, end) for row in group)
        except Exception as exc:
            coverage.append({"nwsli":nwsli, "legacy_date_lead":date,
                             "status":"RETRIEVAL_FAILED","error":str(exc)})
            output.extend({**row,"review_status":"RETRIEVAL_FAILED",
                           "qc_flags":["RETRIEVAL_FAILED_NO_OBSERVED_CREST"],
                           "error":str(exc)} for row in group)
    return {"schema_version":1, "status":"UNVERIFIED_EVENT_LEADS",
            "source_dates_are_only_search_leads":True, "historical_event_pairs_approved":0,
            "source": "USGS instantaneous gauge height 00065 and unchanged Phase 2 legacy metadata",
            "coverage":coverage,"event_leads":output}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-dir",type=Path,default=ROOT/"historical/relationships/v1/points")
    p.add_argument("--output",type=Path,default=ROOT/"reconstruction/staging/legacy_stage_leads.json")
    args=p.parse_args()
    result=make_inventory(args.source_dir)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"leads":len(result["event_leads"]),"retrievals":result["coverage"],
                      "observed_window_maxima": [{k:row.get(k) for k in
                        ("nwsli","legacy_date_lead","legacy_crest_feet","candidate_max_stage_ft",
                         "candidate_max_time_utc","maximum_sample_gap_hours","review_status","qc_flags")}
                         for row in result["event_leads"]],
                      "approved_event_pairs":0,"output":str(args.output)},indent=2))
    if any(x["status"]=="RETRIEVAL_FAILED" for x in result["coverage"]):
        raise SystemExit("Some source observations failed; see saved diagnostics")


if __name__=="__main__":
    main()
