#!/usr/bin/env python3
"""Diagnostic hourly basin MAP versus observed river-stage maxima, Oct–Nov 2026.

Not a published MAP-to-crest event. Splits hourly basin precipitation before/
after an unverified observed stage maximum; the hour straddling the peak is
neither allocated before nor after to avoid inventing subhour precipitation.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
import rasterio

try:
    from .river_stage import POINTS, time_utc, request_stage
    from .run_pilots import index_manifest, load_upstream_basins, hourly_ends
except ImportError:
    from river_stage import POINTS, time_utc, request_stage
    from run_pilots import index_manifest, load_upstream_basins, hourly_ends

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from update import area_stats, cell_areas, fraction_mask  # noqa: E402


def split_hourly_by_peak(hourly, peak_at):
    """Partition hourly QPE strictly by valid-end UTC intervals, preserving straddle."""
    before=after=crossing=0.0
    for row in hourly:
        t=time_utc(row["valid_end_utc"])
        rain=row["hourly_upstream_map_inches"]
        if t<=peak_at:
            before+=rain
        elif t-timedelta(hours=1)>=peak_at:
            after+=rain
        else:
            crossing+=rain
    return before,after,crossing


def diagnostic(manifest_path, basins_path, reference_path, stage_request=request_stage):
    previous=json.loads(Path(reference_path).read_text())
    start=time_utc(previous["event_start_utc"])
    end=time_utc(previous["event_end_utc"])
    inventory=index_manifest(manifest_path)
    expected=hourly_ends(start,end)
    if len(expected)!=49:
        raise ValueError("Expected precisely 49 hourly accumulation intervals")
    missing=[t.isoformat() for t in expected if t not in inventory]
    if missing:
        raise ValueError("Missing original 49-hour QPE source intervals: "+str(missing[:5]))
    basins=load_upstream_basins(basins_path)
    first_path=inventory[expected[0]][0]
    with rasterio.open(first_path) as src:
        if not src.crs or not src.crs.is_geographic:
            raise ValueError("Expected archive conversion to geographic grid")
        grid_transform=src.transform
        grid_shape=(src.height,src.width)
    areas=cell_areas(grid_transform,*grid_shape)
    weights={nwsli: fraction_mask(basins[site],grid_shape,grid_transform)
             for nwsli,site in POINTS.items()}
    hourly={nwsli:[] for nwsli in POINTS}
    for valid_at in expected:
        path, product, units=inventory[valid_at]
        if product!="MultiSensor_QPE_01H_Pass2_00.00" or units!="mm":
            raise ValueError("Unexpected product/units for original archive")
        with rasterio.open(path) as ds:
            if ds.crs is None or not ds.crs.is_geographic or ds.shape!=grid_shape or ds.transform!=grid_transform:
                raise ValueError("Inconsistent hourly grid")
            sample=ds.read(1,masked=True)
        arr=np.asarray(sample.filled(np.nan),dtype="float64")
        arr[np.ma.getmaskarray(sample) | ~np.isfinite(arr) | (arr<0)]=np.nan
        arr/=25.4
        for nwsli,frac in weights.items():
            stat=area_stats(arr,frac,areas)
            if stat["valid_fraction"]<0.999999 or stat["whole_mean"] is None:
                raise ValueError("Missing precipitation within full basin")
            hourly[nwsli].append({"valid_end_utc":valid_at.isoformat(),
                                  "hourly_upstream_map_inches":stat["whole_mean"]})
    results={}
    for nwsli,site in POINTS.items():
        stage=stage_request(site,start-timedelta(days=2),end+timedelta(days=2))
        observations=stage["observations"]
        if not observations:
            results[nwsli]={"status":"NO_USGS_STAGE_OBSERVATIONS"}
            continue
        top=max(r["stage_ft"] for r in observations)
        tied=[r for r in observations if r["stage_ft"]==top]
        peak=tied[0]
        peak_at=time_utc(peak["time_utc"])
        before,after,crossing=split_hourly_by_peak(hourly[nwsli],peak_at)
        total=before+after+crossing
        reference=previous["periods"]["event"]["basins"][site]["whole_mean"]
        if abs(total-reference)>0.0001:
            raise ValueError(f"Hourly MAP vs stored 49h mean differs: {nwsli}")
        results[nwsli]={
            "status":"PROVISIONAL_STAGE_TIMING_DIAGNOSTIC_NOT_APPROVED",
            "usgs_site_id":site,"observed_window_max_stage_ft":top,
            "candidate_max_time_utc":peak_at.isoformat(),
            "tied_maximum_samples":len(tied),"candidate_observation_qualifiers":peak["qualifiers"],
            "stage_source_url":stage["request_url"],
            "whole_event_49h_map_inches":round(total,6),
            "rainfall_before_candidate_peak_inches":round(before,6),
            "rainfall_after_candidate_peak_inches":round(after,6),
            "rainfall_overlapping_candidate_peak_hour_inches":round(crossing,6),
            "fraction_of_event_rainfall_after_peak":round(after/total,5) if total else None,
            "scientific_limits":[
                "Nine-day USGS peak is an unreviewed window maximum",
                "Event rainfall window inherited from Oct 2026 MRMS case study, not independently selected",
                "24h and six-hour legacy MAP semantics remain unverified",
                "Stage datum and event association not approved",
            ],
            "hourly_upstream_map":hourly[nwsli],
        }
    return {"schema_version":1,"event":"2026-10-31_2026-11-01",
            "qpe_product":"MultiSensor_QPE_01H_Pass2_00.00",
            "rain_start_utc":start.isoformat(),"rain_end_utc":end.isoformat(),
            "status":"REVIEW_ONLY_DO_NOT_PLOT_AS_VALIDATED",
            "pilot_results":results}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",required=True)
    p.add_argument("--basins",default="historical/2026-10-31_2026-11-01/basins.geojson")
    p.add_argument("--reference",default="historical/2026-10-31_2026-11-01/latest.json")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    report=diagnostic(a.manifest,a.basins,a.reference)
    dest=Path(a.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"event":report["event"],"status":report["status"],
                      "summaries":{k:{p:v.get(p) for p in (
                        "observed_window_max_stage_ft","candidate_max_time_utc",
                        "whole_event_49h_map_inches","rainfall_before_candidate_peak_inches",
                        "rainfall_after_candidate_peak_inches",
                        "rainfall_overlapping_candidate_peak_hour_inches",
                        "fraction_of_event_rainfall_after_peak","status")}
                          for k,v in report["pilot_results"].items()}},indent=2))


if __name__=="__main__":
    main()
