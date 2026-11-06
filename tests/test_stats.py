import unittest
import tempfile
from pathlib import Path
from PIL import Image
import numpy as np
from affine import Affine
from shapely.geometry import box
from scripts.update import area_stats, cell_areas, fraction_mask, image

class BasinStatisticsTests(unittest.TestCase):
    def test_zero_rain_is_in_whole_mean_but_not_wet_mean(self):
        rain = np.array([[0., 10.], [0., 10.]])
        area = np.ones_like(rain)
        mask = np.ones_like(rain)
        result = area_stats(rain, mask, area)
        self.assertAlmostEqual(result["whole_mean"], 5)
        self.assertAlmostEqual(result["wet_mean"], 10)
        self.assertAlmostEqual(result["wet_fraction"], .5)
        self.assertEqual(result["valid_cells"], 4)

    def test_missing_is_not_zero(self):
        rain = np.array([[np.nan, 6.], [0., np.nan]])
        result = area_stats(rain, np.ones_like(rain), np.ones_like(rain))
        self.assertAlmostEqual(result["whole_mean"], 3)
        self.assertAlmostEqual(result["wet_mean"], 6)
        self.assertAlmostEqual(result["valid_fraction"], .5)

    def test_no_wet_values_returns_null_wet_mean(self):
        result = area_stats(np.zeros((2, 2)), np.ones((2, 2)), np.ones((2, 2)))
        self.assertEqual(result["whole_mean"], 0)
        self.assertIsNone(result["wet_mean"])
        self.assertEqual(result["wet_fraction"], 0)

    def test_crest_palette_and_unsmoothed_native_pixels(self):
        # Pixels are independently colored; no value interpolation is permitted.
        values = np.array([[0.0, 0.099, 0.10, 0.25, 1.0, 5.0, 12.0, 18.5]])
        expected = [(0, 0, 0, 0), (0, 0, 0, 0),
                    (153, 220, 224, 255), (82, 199, 209, 255),
                    (198, 204, 50, 255), (219, 48, 123, 255),
                    (86, 34, 170, 255), (86, 34, 170, 255)]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "rain.png"
            image(values, path)
            with Image.open(path) as png:
                self.assertEqual(png.size, (8, 1))
                self.assertEqual(list(png.convert("RGBA").getdata()), expected)

    def test_fractional_boundary(self):
        transform = Affine(1, 0, 0, 0, -1, 1)
        fraction = fraction_mask(box(0, 0, .5, 1), (1, 1), transform, factor=10)
        self.assertAlmostEqual(fraction[0, 0], .5)

    def test_cell_area_decreases_poleward(self):
        transform = Affine(.01, 0, -90, 0, -.01, 60)
        areas = cell_areas(transform, 3001, 1)
        self.assertGreater(areas[-1, 0], areas[0, 0])

if __name__ == "__main__":
    unittest.main()
