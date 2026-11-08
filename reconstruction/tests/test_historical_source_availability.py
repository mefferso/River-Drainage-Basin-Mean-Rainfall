import unittest

from reconstruction.historical_source_availability import (
    _crest_quality_summary, _find_key, _peak_summary, _quality_summary, _timestamps,
)


class HistoricalSourceAvailabilityTests(unittest.TestCase):
    def test_timestamp_scan_preserves_utc_order_across_offsets(self):
        body = {"observed": [{"validTime": "2018-12-28T17:15:00Z"}],
                "forecast": [{"validTime": "2018-12-29T00:00:00-06:00"}],
                "other": "not-a-time"}
        self.assertEqual([row["utc"] for row in _timestamps(body)], [
            "2018-12-28T17:15:00+00:00", "2018-12-29T06:00:00+00:00",
        ])

    def test_nwps_historic_crest_record_and_usgs_qualifiers_are_retained(self):
        body = {"flood": {"crests": {"historic": [
            {"occurredTime": "2018-12-28T17:15:00Z", "stage": 19.0,
             "preliminary": "O", "olddatum": False},
        ]}}}
        self.assertEqual(_find_key(body, "historic")[0]["preliminary"], "O")
        self.assertEqual(_crest_quality_summary(_find_key(body, "historic"))["preliminary_codes"], {"O": 1})
        feature = {"properties": {"time": "2016-08-13T04:45:00Z", "value": 29.28,
                                   "unit_of_measure": "ft", "approval_status": "Approved",
                                   "qualifier": "A", "parameter_code": "00065"}}
        self.assertEqual(_quality_summary([feature])[0]["qualifier"], "A")

    def test_peak_records_keep_stage_flow_codes_and_dates(self):
        features = [
            {"properties": {"parameter_code": "00060", "time": "2001-03-01T00:00:00Z", "value": 500}},
            {"properties": {"parameter_code": "00065", "time": "2001-03-01T00:00:00Z", "value": 20}},
        ]
        result = _peak_summary(features)
        self.assertEqual(result["records_by_parameter_code"], {"00060": 1, "00065": 1})
        self.assertEqual(result["record_count"], 2)


if __name__ == "__main__":
    unittest.main()
