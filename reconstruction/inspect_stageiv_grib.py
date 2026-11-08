#!/usr/bin/env python3
"""Inspect actual NOAA Stage IV CONUS 24-hour GRIB's native metadata.

No conversion to MAP, no assumption of inches/millimeters, and no change to
legacy event timing. Inspect one bounded archive on GitHub-hosted runner.
"""
from __future__ import annotations
import argparse
import gzip
import io
import json
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import rasterio
import requests

MAX_BYTES=12_000_000
BASE="https://water.noaa.gov/resources/downloads/precip/stageIV/{day:%Y/%m/%d}/ncep_stage_iv_source_files_{day:%Y%m%d}.tar"


def inspect(day_label):
    day=datetime.strptime(day_label,"%Y-%m-%d").replace(tzinfo=timezone.utc)
    url=BASE.format(day=day)
    r=requests.get(url,timeout=45,headers={"User-Agent":"River-Basin-Mean-Rainfall StageIV GRIB audit"})
    r.raise_for_status()
    if len(r.content)>MAX_BYTES:
        raise ValueError("Exceeded maximum archive download")
    with tarfile.open(fileobj=io.BytesIO(r.content),mode="r:*") as archive:
        conus=[m for m in archive.getmembers()
               if m.isfile() and m.name.endswith(("_24h.grb.gz","_24h.grb2.gz"))
               and m.name.split("/")[-1].startswith("conus_")]
        if len(conus)!=1:
            raise ValueError("Expected exactly one CONUS 24h source GRIB")
        member=conus[0]
        raw=archive.extractfile(member).read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise ValueError("GRIB member too large")
    uncompressed=gzip.decompress(raw)
    with tempfile.NamedTemporaryFile(suffix=".grib") as f:
        f.write(uncompressed)
        f.flush()
        with rasterio.open(f.name) as ds:
            samples=ds.read(1,masked=True)
            clean=np.asarray(samples.compressed(),dtype="float64")
            data={
                "source_url":url,"source_member":member.name,
                "crs":str(ds.crs),"width":ds.width,"height":ds.height,
                "bands":ds.count,"bounds":list(ds.bounds),
                "pixel_transform":tuple(ds.transform),
                "band1_tags":ds.tags(1),
                "dataset_tags":ds.tags(),
                "band1_masked_pixel_count":int(np.ma.count_masked(samples)),
                "band1_finite_min":float(np.nanmin(clean)) if len(clean) else None,
                "band1_finite_max":float(np.nanmax(clean)) if len(clean) else None,
                "scientific_status":"SOURCE_GRIB_INSPECTED_DAILY_ACCUMULATION_NOT_SIX_HOUR_MAP",
            }
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date",default="2018-12-28")
    p.add_argument("--output",type=Path,default=Path("reconstruction/staging/stageiv_grib_metadata.json"))
    a=p.parse_args()
    result=inspect(a.date)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
