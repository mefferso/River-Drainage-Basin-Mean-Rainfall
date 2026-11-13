#!/usr/bin/env python3
"""Inspect actual NOAA Stage IV archive members without inferring their interval.

Fetch only selected official tar files (2016/2018/2019), enumerate names,
sizes, and checksums; report no QPE MAP or timing that was not demonstrated.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path
import requests

DATES=("2016-03-12","2018-12-28","2019-05-12")
BASE="https://water.noaa.gov/resources/downloads/precip/stageIV/{date:%Y/%m/%d}/ncep_stage_iv_source_files_{date:%Y%m%d}.tar"
MAX_BYTES=12_000_000


def inspect_tar(payload, source_url):
    if len(payload)>MAX_BYTES:
        raise ValueError("Stage IV archive unexpectedly large; refuse unbounded download")
    result=[]
    with tarfile.open(fileobj=io.BytesIO(payload),mode="r:*") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if member.size>MAX_BYTES:
                raise ValueError("Oversized Stage IV archive member")
            stream=archive.extractfile(member)
            if stream is None:
                raise ValueError("Cannot read Stage IV member")
            data=stream.read(MAX_BYTES+1)
            if len(data)!=member.size:
                raise ValueError("Stage IV member size differs from extracted bytes")
            result.append({"member_name":member.name,"size_bytes":member.size,
                           "sha256":hashlib.sha256(data).hexdigest()})
    return {"source_url":source_url,"archive_size_bytes":len(payload),
            "archive_sha256":hashlib.sha256(payload).hexdigest(),
            "archive_members":result,
            "scientific_status":"ARCHIVE_MEMBERS_VERIFIED_ACCUMULATION_INTERVAL_UNVERIFIED"}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=Path("reconstruction/staging/stageiv_member_audit.json"))
    args=p.parse_args()
    report={"schema_version":1,"audits":[]}
    for label in DATES:
        day=datetime.strptime(label,"%Y-%m-%d").replace(tzinfo=timezone.utc)
        url=BASE.format(date=day)
        try:
            response=requests.get(url,timeout=45,headers={"User-Agent":"River-Basin-Mean-Rainfall StageIV source research"})
            response.raise_for_status()
            if len(response.content)>MAX_BYTES:
                raise ValueError("Archive exceeds bounded inspection size")
            entry=inspect_tar(response.content,url)
            entry["date"]=label
            report["audits"].append(entry)
        except (requests.RequestException,ValueError,tarfile.TarError) as exc:
            report["audits"].append({"date":label,"source_url":url,
                                     "scientific_status":"ARCHIVE_INSPECTION_FAILED","error":str(exc)})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    if any(x["scientific_status"]=="ARCHIVE_INSPECTION_FAILED" for x in report["audits"]):
        raise SystemExit("Some historical Stage IV source archives could not be inspected")


if __name__=="__main__":
    main()
