import unittest

from reconstruction.summarize_historical_source_coverage import summarize


class SourceCoverageSummaryTests(unittest.TestCase):
    def test_summary_preserves_series_coverage_provenance_and_qualifiers(self):
        payload = {
            "schema_version": 1, "generated_at_utc": "2026-11-08T20:19:11Z",
            "status": "SOURCE_AVAILABILITY_PROBE_NOT_EVENT_VALIDATION",
            "interpretation": ["Daily values never supply a crest time."],
            "stations": {
                "AMIL1": {
                    "usgs_site_id": "07375430", "retrieved_at_utc": "2026-11-08T20:19:11Z",
                    "usgs_00065_time_series_metadata": {
                        "initial_request_url": "https://example.test/metadata",
                        "series_summary": [{"id": "instant", "computation_period_identifier": "Points",
                                            "computation_identifier": "Instantaneous", "begin_utc": "2007-10-01T06:00:00+00:00",
                                            "end_utc": "2026-11-08T06:00:00+00:00"}],
                    },
                    "annual_peak_records": {"initial_request_url": "https://example.test/peaks",
                                             "summary": {"record_count": 1, "records_by_parameter_code": {"00065": 1},
                                                         "earliest_record_time": "2018-12-28", "latest_record_time": "2018-12-28"}},
                    "daily_and_continuous_stage_review_windows": {
                        "2018-12-28": {
                            "continuous_00065": {"initial_request_url": "https://example.test/continuous",
                                "coverage": {"instant": {"observation_count": 2, "first_time": "2018-12-28T00:00:00+00:00",
                                                           "last_time": "2018-12-28T00:15:00+00:00", "largest_sample_gap_hours": 0.25}},
                                "features": [{"properties": {"time": "2018-12-28T00:15:00+00:00", "value": "19.25",
                                    "approval_status": "Approved", "qualifier": "A", "time_series_id": "instant"}}],
                                "values": [{"time_series_id": "instant", "approval_status": "Approved", "qualifier": "A"}]},
                            "daily_00065": {"initial_request_url": "https://example.test/daily", "coverage": {}, "features": []},
                        }
                    },
                    "noaa_nwps": {
                        "gauge_metadata": {"request_url": "https://example.test/gauge", "status_code": 200,
                            "historic_crest_count": 1, "historic_crest_quality": {"timestamp_range_utc": ["2018-12-28T00:00:00Z", "2018-12-28T00:00:00Z"],
                                "preliminary_codes": {"O": 1}, "olddatum_true_count": 0},
                            "raw_response": {"datums": {"vertical": {"value": []}}, "timeZone": "CST6CDT"}},
                        "stageflow": {"request_url": "https://example.test/stageflow", "status_code": 200,
                            "timestamp_field_count": 2, "earliest_timestamp_utc": "2026-11-01T00:00:00Z", "latest_timestamp_utc": "2026-11-02T00:00:00Z"},
                    },
                    "review_window_source_overlaps": {"legacy_date_leads_are_search_windows_only": True},
                }
            },
        }
        result = summarize(payload)
        station = result["stations"]["AMIL1"]
        self.assertEqual(station["usgs_series"][0]["begin_utc"], "2007-10-01T06:00:00+00:00")
        row = next(row for row in result["csv_rows"] if row["source_type"] == "continuous")
        self.assertEqual(row["observation_count"], 2)
        self.assertEqual(row["largest_sample_gap_hours"], 0.25)
        self.assertEqual(row["approval_status_codes"], "Approved")
        self.assertEqual(row["qualifier_codes"], "A")
        self.assertEqual(row["source_url"], "https://example.test/continuous")
        maximum = station["windows"]["2018-12-28"]["continuous_window_maximum_candidate"]
        self.assertEqual(maximum["value_ft"], 19.25)
        self.assertEqual(maximum["time_utc"], "2018-12-28T00:15:00+00:00")
        self.assertEqual(maximum["status"], "WINDOW_MAXIMUM_NOT_VERIFIED_FLOOD_CREST")
        candidate_row = next(row for row in result["csv_rows"] if row["source_type"] == "continuous_window_maximum_candidate")
        self.assertEqual(candidate_row["approval_status_codes"], "Approved")
        self.assertEqual(candidate_row["qualifier_codes"], "A")
        self.assertEqual(station["nwps"]["gauge_metadata"]["quality"]["preliminary_codes"], {"O": 1})
        self.assertEqual(station["nwps"]["gauge_metadata"]["station_metadata"]["datums"], {"vertical": {"value": []}})


if __name__ == "__main__":
    unittest.main()
