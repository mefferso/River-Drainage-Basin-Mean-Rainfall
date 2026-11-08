import unittest
from datetime import datetime, timedelta, timezone

from shapely.geometry import box, Point

from reconstruction.phase4d_reconcile import aggregate_same_qpe_window, compare_geometry


class Phase4DReconciliationTests(unittest.TestCase):
    def test_geodesic_geometry_metrics_compare_both_full_and_incremental(self):
        rfc = box(-91.0, 30.0, -90.0, 31.0)
        upstream = box(-91.0, 30.0, -89.0, 31.0)
        incremental = box(-90.8, 30.0, -90.0, 31.0)
        result = compare_geometry(rfc, upstream, incremental, Point(-90.5, 30.5))
        self.assertTrue(result["outlet_inside_rfc_candidate"])
        self.assertLess(result["upstream"]["iou_percent"], 60)
        self.assertGreater(result["incremental"]["iou_percent"], 70)
        self.assertAlmostEqual(result["upstream"]["symmetric_difference_sqmi"],
                               result["upstream"]["rfc_only_sqmi"] + result["upstream"]["nldi_only_sqmi"], places=5)

    def test_same_qpe_window_is_contiguous_and_reports_geometry_only_difference(self):
        start = datetime(2018, 12, 26, 12, tzinfo=timezone.utc)
        days = [
            {"product": "NOAA_STAGE_IV_CONUS_APCP_24H", "grid_signature": "grid-a", "start_utc": start.isoformat(),
             "end_utc": (start + timedelta(days=1)).isoformat(), "nldi_map_inches": 1.0, "rfc_map_inches": 1.2},
            {"product": "NOAA_STAGE_IV_CONUS_APCP_24H", "grid_signature": "grid-a", "start_utc": (start + timedelta(days=1)).isoformat(),
             "end_utc": (start + timedelta(days=2)).isoformat(), "nldi_map_inches": 2.0, "rfc_map_inches": 2.2},
        ]
        result = aggregate_same_qpe_window(days)
        self.assertEqual(result["duration_hours"], 48)
        self.assertEqual(result["nldi_map_inches"], 3.0)
        self.assertAlmostEqual(result["rfc_map_inches"] - result["nldi_map_inches"], 0.4)
        self.assertEqual(result["product"], days[0]["product"])
        bad = [dict(days[0]), dict(days[1], start_utc=(start + timedelta(days=2)).isoformat(),
                                      end_utc=(start + timedelta(days=3)).isoformat())]
        with self.assertRaisesRegex(ValueError, "contiguous"):
            aggregate_same_qpe_window(bad)


if __name__ == "__main__":
    unittest.main()
