"""Temporal separation of QPE avoids post-crest inflation and fake sub-hour timing."""
import unittest
from datetime import datetime, timezone
from reconstruction.temporal_oct2026 import split_hourly_by_peak


class TimingTests(unittest.TestCase):
    def test_peak_at_hourly_boundary(self):
        samples=[
            {"valid_end_utc":"2026-11-01T15:00:00+00:00","hourly_upstream_map_inches":1.0},
            {"valid_end_utc":"2026-11-01T16:00:00+00:00","hourly_upstream_map_inches":2.0},
            {"valid_end_utc":"2026-11-01T17:00:00+00:00","hourly_upstream_map_inches":3.0},
        ]
        before,after,crossing=split_hourly_by_peak(
            samples,datetime(2026,11,1,16,tzinfo=timezone.utc))
        self.assertEqual((before,after,crossing),(3.0,3.0,0.0))

    def test_peak_inside_one_rainfall_hour(self):
        samples=[
            {"valid_end_utc":"2026-11-01T15:00:00Z","hourly_upstream_map_inches":1.0},
            {"valid_end_utc":"2026-11-01T16:00:00Z","hourly_upstream_map_inches":2.0},
            {"valid_end_utc":"2026-11-01T17:00:00Z","hourly_upstream_map_inches":3.0},
        ]
        before,after,crossing=split_hourly_by_peak(
            samples,datetime(2026,11,1,15,30,tzinfo=timezone.utc))
        self.assertEqual((before,after,crossing),(1.0,3.0,2.0))

    def test_timezone_offsets_not_local_clock_assumptions(self):
        samples=[{"valid_end_utc":"2026-11-01T16:00:00Z",
                  "hourly_upstream_map_inches":1.0}]
        before,after,crossing=split_hourly_by_peak(
            samples,datetime.fromisoformat("2026-11-01T10:00:00-06:00"))
        self.assertEqual((before,after,crossing),(1.0,0.0,0.0))


if __name__=="__main__":
    unittest.main()
