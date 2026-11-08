"""Conservative evidence-based matching of independently reconstructed vs legacy events.

Legacy date labels are NOT verified crest dates. Default is always unmatched until
reviewed explicit rainfall windows and crest timestamps exist on both records.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import math


def utc(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Source event chronology requires timezone-aware timestamps")
    return parsed.astimezone(timezone.utc)


def verified_times(row, legacy=False):
    if legacy:
        if row.get("chronology_review_status") != "VERIFIED_SOURCE_EVENT_TIMES":
            return None
        first, last, crest = ("verified_rain_start_utc", "verified_rain_end_utc",
                              "verified_crest_time_utc")
    else:
        if row.get("validation_status") != "SCIENCE_APPROVED":
            return None
        first, last, crest = "rain_start_utc", "rain_end_utc", "crest_time_utc"
    times = tuple(utc(row.get(k)) for k in (first, last, crest))
    if any(t is None for t in times) or not times[0] < times[1]:
        return None
    return times


def comparison(legacy, reconstructed, max_crest_offset_hours=6):
    """Return only unique, positive-interval, independently supported matches.

    Only matching NWSLI points are compared. Ambiguous multiple candidates stay
    unmatched. No row is matched on its unverified legacy event_date alone.
    """
    options = defaultdict(list)
    for i, old in enumerate(legacy):
        old_time = verified_times(old, legacy=True)
        if old_time is None:
            continue
        for j, new in enumerate(reconstructed):
            new_time = verified_times(new)
            if new_time is None:
                continue
            nws_old = old.get("nws_point_id") or old.get("nwsli")
            if not nws_old or nws_old != new.get("nwsli"):
                continue
            if not all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k])
                       for row, keys in ((old, ("map_inches", "crest_feet")),
                                         (new, ("map_inches", "crest_feet"))) for k in keys):
                continue
            if abs((old_time[2]-new_time[2]).total_seconds()) > max_crest_offset_hours*3600:
                continue
            overlap = min(old_time[1], new_time[1]) - max(old_time[0], new_time[0])
            if overlap <= timedelta(0):
                continue
            options[i].append(j)
    reverse = defaultdict(list)
    for i, js in options.items():
        for j in js:
            reverse[j].append(i)
    pairs = []
    for i, js in options.items():
        if len(js) != 1 or len(reverse[js[0]]) != 1:
            continue
        j = js[0]
        old, new = legacy[i], reconstructed[j]
        pairs.append({
            "legacy_record_id": old.get("record_id"),
            "reconstructed_event_id": new.get("event_id"),
            "nwsli": new["nwsli"],
            "legacy_map_inches": old["map_inches"],
            "reconstructed_map_inches": new["map_inches"],
            "map_difference_inches": round(new["map_inches"]-old["map_inches"], 5),
            "legacy_crest_feet": old["crest_feet"],
            "reconstructed_crest_feet": new["crest_feet"],
            "chronology_match": "UNIQUE_WITH_VERIFIED_EVENT_WINDOWS_AND_CREST_TIMES",
        })
    return sorted(pairs, key=lambda row: (row["nwsli"], row["legacy_record_id"] or ""))
