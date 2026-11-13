#!/usr/bin/env python3
"""Bounded official archive availability probe for historical pilot events.

Does not assume that HTTP page reachability implies archived QPE coverage.
MRMS is tested by listing exact hourly archive keys; NOAA Stage IV is
probed by exact dated archive file HEAD requests. Downloads are not performed.
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
try:
    from .archive_qpe import archive_inventory
except ImportError:
    from archive_qpe import archive_inventory

WINDOWS = [
    ("2016-03-12", "2016-03-10T00:00:00Z", "2016-03-12T00:00:00Z"),
    ("2018-12-28", "2018-12-26T00:00:00Z", "2018-12-28T00:00:00Z"),
    ("2019-05-12", "2019-05-10T00:00:00Z", "2019-05-12T00:00:00Z"),
]
NOAA_STAGEIV_DAILY = "https://water.noaa.gov/resources/downloads/precip/stageIV/{date:%Y/%m/%d}/ncep_stage_iv_source_files_{date:%Y%m%d}.tar"
NOAA_DAILY_QPE = "https://water.noaa.gov/resources/downloads/precip/{date:%Y/%m/%d}/nws_precip_1day_{date:%Y%m%d}_conus.tif"


def utc(iso):
    return datetime.fromisoformat(iso.replace("Z","+00:00")).astimezone(timezone.utc)


def url_probe(url, session=None):
    sess = session or requests.Session()
    try:
        response = sess.head(url, allow_redirects=True, timeout=25,
                             headers={"User-Agent":"River-Basin-Mean-Rainfall/0.1 historical data research"})
        return {"url":url,"http_status":response.status_code,
                "content_length_header":response.headers.get("content-length"),
                "content_type":response.headers.get("content-type"),
                "status":"ENDPOINT_EXISTS" if response.ok else "NOT_CONFIRMED_AVAILABLE"}
    except requests.RequestException as exc:
        return {"url":url,"status":"REQUEST_FAILED","error":str(exc)}


def collect():
    results=[]
    for label,start_iso,end_iso in WINDOWS:
        start,end=utc(start_iso),utc(end_iso)
        item={"legacy_date_lead":label,"mrms_sample_start_utc":start.isoformat(),
              "mrms_sample_end_utc":end.isoformat()}
        try:
            inv=archive_inventory(start,end)
            item["mrms_pass2"]={
                "product":inv["product"],"required_hours":inv["required_hours"],
                "found_hours":inv["found_hours"],"missing_hours_count":len(inv["missing_hours"]),
                "status":"COMPLETE" if not inv["missing_hours"] else "INCOMPLETE_OR_NOT_ARCHIVED",
            }
        except Exception as exc:
            item["mrms_pass2"]={"status":"INVENTORY_ERROR","error":str(exc)}
        dt=datetime.strptime(label,"%Y-%m-%d").replace(tzinfo=timezone.utc)
        item["noaa_stageiv_daily_source_tar"]=url_probe(NOAA_STAGEIV_DAILY.format(date=dt))
        item["noaa_stageiv_1day_geotiff"]=url_probe(NOAA_DAILY_QPE.format(date=dt))
        item["scientific_status"]="AVAILABILITY_ONLY_NO_EVENT_MAP_COMPUTED"
        results.append(item)
    return {"schema_version":1,"results":results,
            "notes":["MRMS 48-hour sample only; no complete-event claim",
                     "Stage IV HEAD checks are not decoded/verified precipitation",
                     "Event rainfall start/end still need hydrometeorological review"]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=Path("reconstruction/staging/historical_qpe_coverage.json"))
    args=p.parse_args()
    result=collect()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
