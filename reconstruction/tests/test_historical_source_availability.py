import unittest

from reconstruction.historical_source_availability import _find_key, _quality_summary, _timestamps


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
        feature = {"properties": {"time": "2016-08-13T04:45:00Z", "value": 29.28,
                                   "unit_of_measure": "ft", "approval_status": "Approved",
                                   "qualifier": "A", "parameter_code": "00065"}}
        self.assertEqual(_quality_summary([feature])[0]["qualifier"], "A")


if __name__ == "__main__":
    unittest.main()
