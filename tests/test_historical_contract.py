import json
import math
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.build_historical_site_data import compile_sources


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "historical/relationships/v1/source"


class HistoricalDataContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tempdir.name)
        cls.manifest = compile_sources(
            SOURCE / "Phase2_MAP_to_Crest_Plot_Ready.json",
            SOURCE / "Phase2_Crest_to_Crest_Plot_Ready.json",
            SOURCE / "Phase2_Forecast_Point_Crosswalk.json",
            ROOT / "config/gages.json",
            cls.out,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def payload(self, nwsli):
        return json.loads((self.out / "points" / f"{nwsli}.json").read_text())

    def test_source_counts_and_plot_ready_record_ids_are_preserved(self):
        source_map = json.loads((SOURCE / "Phase2_MAP_to_Crest_Plot_Ready.json").read_text())
        source_pairs = json.loads((SOURCE / "Phase2_Crest_to_Crest_Plot_Ready.json").read_text())
        self.assertEqual(self.manifest["source_counts"], {"map_to_crest": 301, "crest_to_crest": 365, "crosswalk": 29})
        self.assertEqual(len({r["record_id"] for r in source_map}), 301)
        self.assertEqual(len({r["record_id"] for r in source_pairs}), 365)
        self.assertEqual({r["quality_tier"] for r in source_map + source_pairs}, {"B"})
        self.assertEqual(self.manifest["published_counts"]["map_to_crest"], 240)
        self.assertEqual(self.manifest["published_counts"]["crest_to_crest"], 365)
        self.assertEqual(self.manifest["verified_dashboard_crosswalks"], 18)
        self.assertEqual(self.manifest["published_relationships"], 12)
        self.assertEqual(len(self.manifest["published_points"]), 15)
        self.assertEqual(self.manifest["excluded_map_records"], {"no_verified_current_dashboard_gage": 61, "by_historical_point": {"GLFM6": 54, "KLNM6": 7}})
        compiled_map = [r for path in (self.out / "points").glob("*.json") for r in json.loads(path.read_text())["map_events"]]
        compiled_pairs = {}
        for path in (self.out / "points").glob("*.json"):
            for relationship in json.loads(path.read_text())["crest_relationships"]:
                for record in relationship["records"]:
                    compiled_pairs[record["record_id"]] = record
        self.assertEqual({r["record_id"] for r in compiled_map}, {r["record_id"] for r in source_map if r["dashboard_gage_id"] in {"02492343", "02492360", "07375800", "02481510", "07375300", "07375960", "07375430"}})
        self.assertNotIn("GLFM6", {r["nws_point_id"] for r in compiled_map})
        self.assertNotIn("KLNM6", {r["nws_point_id"] for r in compiled_map})
        source_by_id = {r["record_id"]: r for r in source_map}
        self.assertTrue(all(source_by_id[r["record_id"]] == r for r in compiled_map))
        self.assertEqual(set(compiled_pairs), {r["record_id"] for r in source_pairs})
        self.assertTrue(all({r["record_id"]: r for r in source_pairs}[key] == value for key, value in compiled_pairs.items()))

    def test_pilot_counts_and_directional_axes(self):
        amite = self.payload("AMIL1")
        east_hobolochitto = self.payload("CREM6")
        osyka = self.payload("OSYM6")
        self.assertEqual(len(amite["map_events"]), 23)
        self.assertEqual(len(east_hobolochitto["map_events"]), 34)
        pair = next(r for r in osyka["crest_relationships"] if r["relationship_id"] == "OSYM6__KENL1")
        self.assertEqual(len(pair["records"]), 34)
        self.assertEqual((pair["source_point_id_nws"], pair["target_point_id_nws"]), ("OSYM6", "KENL1"))
        kentwood_pair = next(r for r in self.payload("KENL1")["crest_relationships"] if r["relationship_id"] == "OSYM6__KENL1")
        self.assertEqual((kentwood_pair["source_point_id_nws"], kentwood_pair["target_point_id_nws"]), ("OSYM6", "KENL1"))
        self.assertEqual([r["record_id"] for r in pair["records"]], [r["record_id"] for r in kentwood_pair["records"]])

    def test_magnolia_denham_phase2_approved_count_and_identity(self):
        source_pairs = json.loads((SOURCE / "Phase2_Crest_to_Crest_Plot_Ready.json").read_text())
        approved = [record for record in source_pairs if record["relationship_id"] == "MAGL1__DENL1"]
        denham = self.payload("DENL1")
        published = next(rel for rel in denham["crest_relationships"] if rel["relationship_id"] == "MAGL1__DENL1")["records"]
        self.assertEqual(len(approved), 13)
        self.assertEqual(len(published), 13)
        self.assertEqual({r["record_id"] for r in approved}, {r["record_id"] for r in published})
        self.assertEqual({r["quality_tier"] for r in published}, {"B"})
        self.assertEqual(len([r for r in published if r["event_date"] == "2003-02-03"]), 0)

    def test_verified_crosswalk_and_station_aliases_fail_closed(self):
        crosswalk = json.loads((self.out / "crosswalk.json").read_text())
        by_usgs = {r["usgs_site_id"]: r["nws_point_id"] for r in crosswalk}
        self.assertEqual(len(crosswalk), 18)
        self.assertEqual(by_usgs["02492360"], "MNLM6")
        self.assertEqual(by_usgs["02492343"], "CREM6")
        self.assertNotEqual(by_usgs["02492360"], by_usgs["02492343"])
        self.assertNotIn("02481667", by_usgs)
        self.assertNotIn("WPTM6", by_usgs.values())
        alias = next(r for r in self.payload("DIBM6")["crest_relationships"] if r["relationship_id"] == "WTPM6__DIBM6")
        self.assertEqual(alias["source_point_id_nws"], "WPTM6")
        self.assertTrue(any(r["source_point_id_raw"] == "WTPM6" for r in alias["records"]))

    def test_reversed_workbook_columns_keep_reviewed_source_target_order(self):
        for nwsli, relation_id, source_id, target_id in [
            ("BXAL1", "CLMM6__BXAL1", "CLMM6", "BXAL1"),
            ("CUSL1", "FLSL1__CUSL1", "FLSL1", "CUSL1"),
        ]:
            relation = next(r for r in self.payload(nwsli)["crest_relationships"] if r["relationship_id"] == relation_id)
            self.assertEqual((relation["source_point_id_nws"], relation["target_point_id_nws"]), (source_id, target_id))

    def test_missing_values_and_date_precision_are_not_reinterpreted(self):
        original = json.loads((SOURCE / "Phase2_MAP_to_Crest_Plot_Ready.json").read_text())
        compiled = [r for path in (self.out / "points").glob("*.json") for r in json.loads(path.read_text())["map_events"]]
        for record in compiled:
            self.assertEqual(record["date_precision"], "day")
            self.assertRegex(record["event_date"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertTrue(math.isfinite(record["map_inches"]))
            self.assertTrue(math.isfinite(record["crest_feet"]))
        self.assertTrue(any(r["tc_hours_confirmed"] is None for r in original))
        self.assertTrue(any(r["tc_hours_confirmed"] is None for r in compiled))

    def test_compiler_rejects_nonfinite_coordinates_duplicate_ids_and_ambiguous_matches(self):
        def run_with(map_rows=None, crosswalk_rows=None, label="case"):
            folder = Path(tempfile.mkdtemp())
            try:
                map_path = folder / "map.json"
                pair_path = folder / "pairs.json"
                crosswalk_path = folder / "crosswalk.json"
                map_path.write_text(json.dumps(map_rows if map_rows is not None else json.loads((SOURCE / "Phase2_MAP_to_Crest_Plot_Ready.json").read_text())))
                pair_path.write_text((SOURCE / "Phase2_Crest_to_Crest_Plot_Ready.json").read_text())
                crosswalk_path.write_text(json.dumps(crosswalk_rows if crosswalk_rows is not None else json.loads((SOURCE / "Phase2_Forecast_Point_Crosswalk.json").read_text())))
                return compile_sources(map_path, pair_path, crosswalk_path, ROOT / "config/gages.json", folder / label)
            finally:
                import shutil
                shutil.rmtree(folder)

        bad_map = json.loads((SOURCE / "Phase2_MAP_to_Crest_Plot_Ready.json").read_text())
        bad_map[0]["map_inches"] = float("inf")
        with self.assertRaisesRegex(ValueError, "non-finite numeric"):
            run_with(map_rows=bad_map, label="infinite")

        duplicate_map = json.loads((SOURCE / "Phase2_MAP_to_Crest_Plot_Ready.json").read_text())
        duplicate_map[1]["record_id"] = duplicate_map[0]["record_id"]
        with self.assertRaisesRegex(ValueError, "duplicate record_id"):
            run_with(map_rows=duplicate_map, label="duplicate")

        ambiguous = json.loads((SOURCE / "Phase2_Forecast_Point_Crosswalk.json").read_text())
        ambiguous[1]["usgs_site_id_confirmed"] = ambiguous[0]["usgs_site_id_confirmed"]
        ambiguous[1]["existing_dashboard_usgs_id"] = ambiguous[0]["existing_dashboard_usgs_id"]
        with self.assertRaisesRegex(ValueError, "multiple forecast points map to dashboard gage"):
            run_with(crosswalk_rows=ambiguous, label="ambiguous")

        bad_coordinates = json.loads((SOURCE / "Phase2_Forecast_Point_Crosswalk.json").read_text())
        bad_coordinates[0]["latitude"] = float("nan")
        with self.assertRaisesRegex(ValueError, "non-finite numeric"):
            run_with(crosswalk_rows=bad_coordinates, label="bad-coordinate")


if __name__ == "__main__":
    unittest.main()
