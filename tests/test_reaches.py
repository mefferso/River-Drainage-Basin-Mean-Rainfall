import sys
import unittest
from pathlib import Path
from datetime import timedelta
from shapely.geometry import box, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update import build_reaches
from historical import START, END, required_hours


class ReachDelineationTests(unittest.TestCase):
    def test_downstream_reach_excludes_upstream_area(self):
        features = [
            {"properties": {"id": "up"}, "geometry": mapping(box(0, 0, 1, 2))},
            {"properties": {"id": "down"}, "geometry": mapping(box(0, 0, 2, 2))},
        ]
        gages = [
            {"id": "up", "upstream_from": []},
            {"id": "down", "upstream_from": ["up"]},
        ]
        reaches, errors = build_reaches(features, gages)
        self.assertFalse(errors)
        self.assertAlmostEqual(reaches["up"].area, 2)
        self.assertAlmostEqual(reaches["down"].area, 2)
        self.assertFalse(reaches["down"].intersects(reaches["up"].buffer(-0.01)))

    def test_missing_upstream_polygon_fails_closed(self):
        features = [{"properties": {"id": "down"}, "geometry": mapping(box(0, 0, 2, 2))}]
        reaches, errors = build_reaches(features, [{"id": "down", "upstream_from": ["missing"]}])
        self.assertNotIn("down", reaches)
        self.assertIn("down", errors)

    def test_central_dst_fall_back_is_49_hours(self):
        self.assertEqual(int((END - START) / timedelta(hours=1)), 49)
        hours = required_hours()
        self.assertEqual(len(hours), 49)
        self.assertEqual(hours[0], START + timedelta(hours=1))
        self.assertEqual(hours[-1], END)


if __name__ == "__main__":
    unittest.main()
