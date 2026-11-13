"""Unit tests for strict pilot input validation and raster MAP calculation."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from reconstruction.run_pilots import (
    PILOTS, hourly_ends, index_manifest, calculate_map, reconstruct, timestamp
)
from datetime import datetime, timezone


class PilotTests(unittest.TestCase):
    def test_pilot_identity(self):
        self.assertEqual(PILOTS, {"AMIL1": "07375430", "MNLM6": "02492360"})

    def test_hourly_utc_window(self):
        start = timestamp("2026-11-01T05:00:00Z")
        end = timestamp("2026-11-01T08:00:00Z")
        self.assertEqual(len(hourly_ends(start, end)), 3)
        with self.assertRaises(ValueError):
            timestamp("2026-11-01T01:00:00")
        with self.assertRaises(ValueError):
            hourly_ends(end, start)

    def test_incomplete_mixed_and_complete_rainfall(self):
        from shapely.geometry import box
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            t1 = timestamp("2026-11-01T01:00:00Z")
            t2 = timestamp("2026-11-01T02:00:00Z")
            grid = from_origin(-91, 31, 0.1, 0.1)
            for i in (1, 2):
                with rasterio.open(p / f"{i}.tif", "w", driver="GTiff",
                                   width=2, height=2, count=1, dtype="float32",
                                   crs="EPSG:4326", transform=grid,
                                   nodata=-9999) as dst:
                    dst.write(np.full((2, 2), 25.4, dtype="float32"), 1)
            basin = box(-90.99, 30.81, -90.81, 30.99)
            rows = {t1: (p/"1.tif", "MRMS_Pass2", "mm"), t2: (p/"2.tif", "MRMS_Pass2", "mm")}
            value, product = calculate_map(basin, [t1, t2], rows)
            self.assertAlmostEqual(value, 2.0, places=5)
            self.assertEqual(product, "MRMS_Pass2")
            with self.assertRaisesRegex(ValueError, "Missing required QPE"):
                calculate_map(basin, [t1, t2], {t1: rows[t1]})
            with self.assertRaisesRegex(ValueError, "Mixed QPE"):
                calculate_map(basin, [t1, t2], {t1: rows[t1], t2: (p/"2.tif", "StageIV", "mm")})

    def test_end_to_end_two_pilots(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            transform = from_origin(-91, 31, 0.1, 0.1)
            with rasterio.open(p/"qpe.tif", "w", driver="GTiff", width=2, height=2,
                               count=1, dtype="float32", crs="EPSG:4326",
                               transform=transform) as dst:
                dst.write(np.full((2, 2), 25.4, dtype="float32"), 1)
            manifest = p/"manifest.csv"
            manifest.write_text("valid_end_utc,path,product,units\n2026-11-01T01:00:00Z,qpe.tif,MRMS_Pass2,mm\n")
            basin_poly = {"type":"Polygon","coordinates":[[[-90.99,30.99],[-90.81,30.99],[-90.81,30.81],[-90.99,30.81],[-90.99,30.99]]]}
            basins = p/"basins.geojson"
            basins.write_text(json.dumps({"type":"FeatureCollection","features":[
                {"type":"Feature","properties":{"id":v},"geometry":basin_poly}
                for v in PILOTS.values()]}))
            events = p/"events.csv"
            events.write_text("event_id,nwsli,rain_start_utc,rain_end_utc,crest_time_utc,crest_ft\n"
                              "a,AMIL1,2026-11-01T00:00:00Z,2026-11-01T01:00:00Z,2026-11-01T05:00:00Z,12.5\n"
                              "b,MNLM6,2026-11-01T00:00:00Z,2026-11-01T01:00:00Z,2026-11-01T06:00:00Z,14.5\n")
            result = reconstruct(manifest, events, basins)
            self.assertEqual([r["nwsli"] for r in result], ["AMIL1","MNLM6"])
            self.assertTrue(all(abs(r["map_inches"]-1.0)<1e-5 for r in result))
            self.assertTrue(all(r["validation_status"].startswith("PROVISIONAL") for r in result))


if __name__ == "__main__":
    unittest.main()
