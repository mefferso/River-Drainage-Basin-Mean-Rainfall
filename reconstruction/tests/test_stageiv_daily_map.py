"""Synthetic raster science tests for independent daily Stage IV MAP weighting."""
import unittest
import tempfile
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin
from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform as project_geometry

from reconstruction.stageiv_daily_map import geodesic_basin_mean, verify_grib_tags


class StageIVTests(unittest.TestCase):
    def test_grib_interval_and_units(self):
        tags={"GRIB_ELEMENT":"APCP","GRIB_UNIT":"[kg/m^2]",
              "GRIB_FORECAST_SECONDS":"86400",
              "GRIB_REF_TIME":"1545912000",
              "GRIB_VALID_TIME":"1545998400"}
        start,end=verify_grib_tags(tags)
        self.assertEqual((end-start).total_seconds(),86400)
        with self.assertRaises(ValueError):
            verify_grib_tags({**tags,"GRIB_UNIT":"[in]"})
        with self.assertRaises(ValueError):
            verify_grib_tags({**tags,"GRIB_FORECAST_SECONDS":"21600"})

    def test_projected_geodesic_weights_zero_and_missing(self):
        crs="EPSG:3857"
        xform=from_origin(-10100000,3900000,5000,5000)
        pixel_geom=box(*rasterio.transform.array_bounds(1,1,xform))
        inverse=Transformer.from_crs(crs,"EPSG:4326",always_xy=True)
        basin=project_geometry(inverse.transform,pixel_geom)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"synthetic.tif"
            with rasterio.open(p,"w",driver="GTiff",height=3,width=3,count=1,
                               dtype="float32",crs=crs,transform=xform,nodata=-9999) as dst:
                dst.write(np.full((3,3),25.4,dtype="float32"),1)
            with rasterio.open(p) as ds:
                value=geodesic_basin_mean(ds,basin)
                self.assertAlmostEqual(value["map_inches"],1.0,places=4)
                self.assertTrue(0.995 <= value["geodesic_coverage_fraction"] <=1.005)
            with rasterio.open(p,"r+") as dst:
                a=dst.read(1)
                a[0,0]=-9999
                dst.write(a,1)
            with rasterio.open(p) as ds:
                with self.assertRaisesRegex(ValueError,"Missing Stage IV precipitation"):
                    geodesic_basin_mean(ds,basin)


if __name__=="__main__":
    unittest.main()
