"""MRMS archive inventory tests use simulated S3 listings, never invented real QPE."""
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
from reconstruction.archive_qpe import archive_inventory


class FakePages:
    def paginate(self, **kwargs):
        day = kwargs["Prefix"].split("/")[-2]
        keys = {
            "20261031": ["CONUS/MultiSensor_QPE_01H_Pass2_00.00/20261031/MRMS_MultiSensor_QPE_01H_Pass2_00.00_20261031-010000.grib2.gz",
                         "CONUS/MultiSensor_QPE_01H_Pass2_00.00/20261031/MRMS_MultiSensor_QPE_01H_Pass2_00.00_20261031-020000.grib2.gz"],
        }
        yield {"Contents": [{"Key": key, "Size": 123456} for key in keys.get(day, [])]}


class QpeTests(unittest.TestCase):
    def test_inventory_complete_and_missing(self):
        client = Mock()
        client.get_paginator.return_value = FakePages()
        a = datetime(2026, 10, 31, tzinfo=timezone.utc)
        from datetime import timedelta
        complete = archive_inventory(a, a+timedelta(hours=2), client)
        self.assertEqual(complete["required_hours"], 2)
        self.assertEqual(complete["found_hours"], 2)
        self.assertEqual(complete["missing_hours"], [])
        missing = archive_inventory(a, a+timedelta(hours=3), client)
        self.assertEqual(missing["found_hours"], 2)
        self.assertEqual(len(missing["missing_hours"]), 1)

    def test_window_validation(self):
        a = datetime(2026, 10, 31, tzinfo=timezone.utc)
        from datetime import timedelta
        with self.assertRaises(ValueError):
            archive_inventory(a, a+timedelta(hours=73), Mock())


if __name__ == "__main__":
    unittest.main()
