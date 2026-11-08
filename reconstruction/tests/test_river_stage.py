"""Offline river stage retrieval and candidate-identification tests."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from reconstruction.river_stage import POINTS, time_utc, request_stage, crest_candidates


class StageTests(unittest.TestCase):
    def test_identity_and_timezone(self):
        self.assertEqual(POINTS["AMIL1"], "07375430")
        self.assertEqual(POINTS["MNLM6"], "02492360")
        self.assertEqual(time_utc("2026-11-01T01:00:00-05:00").hour, 6)
        with self.assertRaises(ValueError):
            time_utc("2026-11-01T01:00:00")

    def test_real_usgs_schema_parser(self):
        response = Mock()
        response.json.return_value = {"value": {"timeSeries": [{
            "sourceInfo": {"siteName": "Test", "siteCode": [{"value": "07375430"}]},
            "variable": {"variableCode": [{"value": "00065"}],
                         "unit": {"unitCode": "ft"}},
            "values": [{"value": [
                {"dateTime": "2026-11-01T00:00:00.000-05:00",
                 "value": "12.25", "qualifiers": ["P"]},
                {"dateTime": "2026-11-01T01:00:00.000-05:00",
                 "value": "-999999", "qualifiers": []}]}]
        }]}}
        sess = Mock()
        sess.get.return_value = response
        result = request_stage(
            "07375430", time_utc("2026-11-01T04:00:00Z"),
            time_utc("2026-11-01T08:00:00Z"), sess
        )
        self.assertEqual(len(result["observations"]), 1)
        self.assertEqual(result["observations"][0]["stage_ft"], 12.25)
        self.assertEqual(result["observations"][0]["time_utc"], "2026-11-01T05:00:00+00:00")
        self.assertEqual(result["observations"][0]["qualifiers"], ["P"])

    def test_peaks_are_not_automatically_verified(self):
        stages = [3, 5, 7, 5, 3]
        obs = [{"time_utc": f"2026-11-01T0{i}:00:00+00:00",
                "stage_ft": stage, "site_id": "07375430",
                "source_url": "https://example.invalid", "qualifiers": []}
               for i, stage in enumerate(stages)]
        result = crest_candidates(obs)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["candidate_stage_ft"], 7)
        self.assertEqual(result[0]["status"], "CANDIDATE_UNVERIFIED")
        obs[3]["time_utc"] = "2026-11-02T03:00:00+00:00"
        self.assertEqual(len(crest_candidates(obs)), 0)

    def test_missing_stage_units_rejected(self):
        response = Mock()
        response.json.return_value = {"value": {"timeSeries": [{
            "sourceInfo": {"siteCode": [{"value": "07375430"}]},
            "variable": {"variableCode": [{"value": "00065"}],
                         "unit": {"unitCode": "m"}},
            "values": []}]}}
        sess = Mock()
        sess.get.return_value = response
        with self.assertRaises(ValueError):
            request_stage("07375430", time_utc("2026-11-01T00:00:00Z"),
                          time_utc("2026-11-02T00:00:00Z"), sess)


if __name__ == "__main__":
    unittest.main()
