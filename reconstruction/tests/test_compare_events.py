"""Never turn unverified legacy dates into observed crest matches."""
import unittest
from reconstruction.compare_events import comparison

LEGACY={
    "record_id":"legacy_1","nws_point_id":"MNLM6",
    "event_date":"2026-11-01","map_inches":4.0,"crest_feet":12.0,
}
NEW={
    "event_id":"new_1","nwsli":"MNLM6","map_inches":4.8,"crest_feet":12.0,
    "validation_status":"SCIENCE_APPROVED",
    "rain_start_utc":"2026-10-31T05:00:00Z",
    "rain_end_utc":"2026-11-02T06:00:00Z",
    "crest_time_utc":"2026-11-02T16:00:00Z",
}

class ComparisonTests(unittest.TestCase):
    def test_unverified_legacy_date_never_matched(self):
        self.assertEqual(comparison([LEGACY],[NEW]),[])

    def test_provisional_reconstruction_never_matched(self):
        verified={**LEGACY,**{
            "chronology_review_status":"VERIFIED_SOURCE_EVENT_TIMES",
            "verified_rain_start_utc":"2026-10-31T05:00:00Z",
            "verified_rain_end_utc":"2026-11-02T06:00:00Z",
            "verified_crest_time_utc":"2026-11-02T16:00:00Z",
        }}
        self.assertEqual(comparison([verified],[{**NEW,"validation_status":"PROVISIONAL"}]),[])

    def test_unique_evidence_backed_match(self):
        verified={**LEGACY,**{
            "chronology_review_status":"VERIFIED_SOURCE_EVENT_TIMES",
            "verified_rain_start_utc":"2026-10-31T05:00:00Z",
            "verified_rain_end_utc":"2026-11-02T06:00:00Z",
            "verified_crest_time_utc":"2026-11-02T16:00:00Z",
        }}
        matches=comparison([verified],[NEW])
        self.assertEqual(len(matches),1)
        self.assertAlmostEqual(matches[0]["map_difference_inches"],0.8)
        self.assertEqual(comparison([verified],[NEW,{**NEW,"event_id":"duplicate"}]),[])

    def test_no_cross_station_join(self):
        verified={**LEGACY,**{
            "chronology_review_status":"VERIFIED_SOURCE_EVENT_TIMES",
            "verified_rain_start_utc":"2026-10-31T05:00:00Z",
            "verified_rain_end_utc":"2026-11-02T06:00:00Z",
            "verified_crest_time_utc":"2026-11-02T16:00:00Z",
        }}
        self.assertEqual(comparison([verified],[{**NEW,"nwsli":"AMIL1"}]),[])

if __name__=="__main__":
    unittest.main()
