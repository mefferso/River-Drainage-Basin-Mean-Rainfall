"""Selected legacy day labels are only leads, never observed crests."""
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from reconstruction.event_inventory import legacy_leads, make_inventory, summarize_window


class InventoryTests(unittest.TestCase):
    def test_actual_repository_legacy_coverage(self):
        source = Path("historical/relationships/v1/points")
        rows = legacy_leads(source)
        self.assertTrue(any(r["nwsli"]=="AMIL1" and r["legacy_date_lead"]=="2016-03-12" for r in rows))
        self.assertTrue(any(r["nwsli"]=="MNLM6" and r["legacy_date_lead"]=="2026-10-31" for r in rows))
        self.assertTrue(all("legacy_record_id" in r for r in rows))

    def test_stage_window_maximum_never_approved(self):
        start=datetime(2019,5,9,tzinfo=timezone.utc)
        end=start+timedelta(days=9)
        observations=[
            {"time_utc":"2019-05-13T01:00:00+00:00","stage_ft":11.0,"qualifiers":[]},
            {"time_utc":"2019-05-13T01:15:00+00:00","stage_ft":17.0,"qualifiers":["P"]},
            {"time_utc":"2019-05-13T01:30:00+00:00","stage_ft":13.0,"qualifiers":[]}]
        data={"observations":observations,"request_url":"https://waterservices.usgs.gov/test",
              "retrieved_at_utc":"2026-11-08T00:00:00+00:00"}
        sample=summarize_window({"nwsli":"MNLM6","legacy_date_lead":"2019-05-12"},data,start,end)
        self.assertEqual(sample["candidate_max_stage_ft"],17.0)
        self.assertEqual(sample["review_status"],"OBSERVED_WINDOW_MAXIMUM_NOT_VERIFIED_EVENT_CREST")
        self.assertIn("EDGE_COVERAGE_INCOMPLETE",sample["qc_flags"])
        self.assertIn("OBSERVATION_QUALIFIERS_REQUIRE_REVIEW",sample["qc_flags"])

    def test_mock_inventory_is_never_an_approved_event(self):
        def fake(site,start,end):
            return {"request_url":"https://waterservices.usgs.gov/example",
                    "retrieved_at_utc":"2026-11-08T00:00:00+00:00",
                    "observations":[{"time_utc":start.isoformat(),"stage_ft":10.2,
                                     "qualifiers":[]}]}
        result=make_inventory(Path("historical/relationships/v1/points"),
                              request_fn=fake,dates=("2016-03-12",))
        self.assertEqual(result["historical_event_pairs_approved"],0)
        self.assertTrue(all(x["review_status"]!="SCIENCE_APPROVED" for x in result["event_leads"]))
        self.assertTrue(len(result["event_leads"])>=2)


if __name__=="__main__":
    unittest.main()
