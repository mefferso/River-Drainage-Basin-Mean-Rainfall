import csv
import hashlib
import gzip
import json
import tarfile
import tempfile
import unittest
import warnings
from types import SimpleNamespace
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

RFC_FIELDS = {
    "OBJ_STATUS_": 0,
    "OBJ_IDENTIF": 410,
    "NAME": "AMIL1",
    "MIN_X_AXIS_": -90.62,
    "MAX_X_AXIS_": -90.32,
    "MIN_Y_AXIS_": 30.72,
    "MAX_Y_AXIS_": 31.12,
    "FCSTGROUP": "FGAMCOLA",
    "NWSID": "AMIL1",
    "AREA": 202.288590316,
    "DESCRIPT": "TANGIPAHOA/AMITE",
    "TVA_NUM": -999,
}


def load_rfc_features(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import load_rfc_features as load
    except ModuleNotFoundError as exc:
        raise AssertionError("Phase 4B source loader is not implemented") from exc
    return load(*args, **kwargs)


def write_source_inventory(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import write_source_inventory as write
    except ModuleNotFoundError as exc:
        raise AssertionError("Phase 4B source inventory writer is not implemented") from exc
    return write(*args, **kwargs)


def resolve_outlet_link(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import resolve_outlet_link as resolve
    except (ImportError, AttributeError) as exc:
        raise AssertionError("Phase 4B outlet resolver is not implemented") from exc
    return resolve(*args, **kwargs)


def build_relationships(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import build_relationships as build
    except (ImportError, AttributeError) as exc:
        raise AssertionError("Phase 4B relation builder is not implemented") from exc
    return build(*args, **kwargs)


def write_network_outputs(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import write_network_outputs as write
    except (ImportError, AttributeError) as exc:
        raise AssertionError("Phase 4B network output writer is not implemented") from exc
    return write(*args, **kwargs)


def fetch_network_cache(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import fetch_network_cache as fetch
    except (ImportError, AttributeError) as exc:
        raise AssertionError("Phase 4B network cache fetcher is not implemented") from exc
    return fetch(*args, **kwargs)


def build_station_candidate(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import build_station_candidate as build
    except (ImportError, AttributeError) as exc:
        raise AssertionError("Phase 4B station candidate builder is not implemented") from exc
    return build(*args, **kwargs)


def compare_geometries(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import compare_geometries as compare
    except (ImportError, AttributeError) as exc:
        raise AssertionError("Phase 4B geometry metrics are not implemented") from exc
    return compare(*args, **kwargs)


def write_station_outputs(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import write_station_outputs as write
    except (ImportError, AttributeError) as exc:
        raise AssertionError("Phase 4B station output writer is not implemented") from exc
    return write(*args, **kwargs)


def load_verified_nldi_references(*args, **kwargs):
    try:
        from scripts.build_phase4b_rfc_aggregates import load_verified_nldi_references as load
    except (ImportError, AttributeError) as exc:
        raise AssertionError("Phase 4B verified NLDI reference loader is not implemented") from exc
    return load(*args, **kwargs)


def make_archive(directory: Path, features: list[dict]) -> Path:
    frame = gpd.GeoDataFrame(
        features,
        geometry=[
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
            if feature.pop("_valid", True)
            else Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
            for feature in features
        ],
        crs="EPSG:4326",
    )
    shapefile = directory / "b_lmrfc.shp"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        frame.to_file(shapefile, driver="ESRI Shapefile", index=False)
    # The NOAA 2018 DBF uses several 11-byte field names. GDAL writes the
    # usual ten-character aliases, so restore the source DBF descriptors.
    dbf = directory / "b_lmrfc.dbf"
    with dbf.open("r+b") as stream:
        stream.seek(32)
        for index, name in enumerate(RFC_FIELDS):
            stream.seek(32 + index * 32)
            stream.write(name.encode("ascii").ljust(11, b"\x00"))
    archive = directory / "b_lmrfc.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(directory.glob("b_lmrfc.*")):
            if path != archive:
                tar.add(path, arcname=path.name)
    return archive


class RfcSourceInventoryTests(unittest.TestCase):
    def test_archive_count_and_all_attributes_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = make_archive(root, [dict(RFC_FIELDS)])
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            features = load_rfc_features(
                archive, expected_count=1, expected_sha256=digest
            )

            self.assertEqual(len(features), 1)
            feature = features[0]
            self.assertEqual(feature.properties, RFC_FIELDS)
            self.assertEqual(feature.feature_id, "410")
            self.assertAlmostEqual(feature.area_sqmi, 4752.45, delta=0.1)
            self.assertTrue(feature.geometry.is_valid)
            self.assertEqual(feature.outlet.x, 0.0)
            self.assertEqual(feature.outlet.y, 0.0)

    def test_production_archive_baseline_rejects_a_nonproduction_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = make_archive(Path(temp), [dict(RFC_FIELDS)])
            with self.assertRaisesRegex(ValueError, "(?i)sha-256 mismatch|543"):
                load_rfc_features(archive)

    def test_inventory_rejects_bad_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = make_archive(
                Path(temp), [{**RFC_FIELDS, "_valid": False}]
            )
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "invalid"):
                load_rfc_features(
                    archive, expected_count=1, expected_sha256=digest
                )

    def test_source_defect_can_be_preserved_and_flagged_without_repair(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = make_archive(root, [{**RFC_FIELDS, "_valid": False}])
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            features = load_rfc_features(
                archive, expected_count=1, expected_sha256=digest,
                allow_invalid_geometry=True,
            )
            self.assertFalse(features[0].geometry_valid)
            self.assertTrue(features[0].geometry_issue)
            self.assertFalse(features[0].geometry.is_valid)
            write_source_inventory(features, root / "out", digest)
            with (root / "out/rfc_feature_inventory.csv").open(newline="") as stream:
                inventory = list(csv.DictReader(stream))
            self.assertEqual(inventory[0]["source_geometry_valid"], "False")
            self.assertTrue(inventory[0]["source_geometry_issue"])

    def test_inventory_rejects_duplicate_feature_id(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = make_archive(
                Path(temp),
                [dict(RFC_FIELDS), {**RFC_FIELDS, "NWSID": "OSYM6"}],
            )
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "(?i)duplicate"):
                load_rfc_features(
                    archive, expected_count=2, expected_sha256=digest
                )

    def test_inventory_outputs_all_raw_fields_and_source_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = make_archive(root, [dict(RFC_FIELDS)])
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            features = load_rfc_features(
                archive, expected_count=1, expected_sha256=digest
            )
            output = root / "out"
            write_source_inventory(features, output, digest)

            with (output / "rfc_feature_inventory.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["OBJ_IDENTIF"], "410")
            self.assertEqual(rows[0]["NWSID"], "AMIL1")
            self.assertEqual(rows[0]["source_archive_sha256"], digest)
            geojson = json.loads(
                (output / "rfc_single_segments.geojson").read_text()
            )
            self.assertEqual(len(geojson["features"]), 1)
            self.assertEqual(
                geojson["features"][0]["properties"]["scientific_status"],
                "UNVERIFIED_LEGACY_MAP_GEOMETRY",
            )
            for name, expected in RFC_FIELDS.items():
                self.assertEqual(
                    geojson["features"][0]["properties"][name], expected
                )


class RfcNetworkRelationshipTests(unittest.TestCase):
    outlet = (-90.4842587, 30.7290747)

    def feature(self, feature_id: str, coordinate=None):
        coordinate = coordinate or self.outlet
        from shapely.geometry import Point

        return SimpleNamespace(
            feature_id=feature_id,
            outlet=Point(coordinate),
        )

    def response(self, offset_y: float = 0.0005, *, comid=101):
        lon, lat = self.outlet
        return {
            "source_url": "https://api.water.usgs.gov/nldi/linked-data/hydrolocation",
            "retrieved_at": "2026-11-08T00:00:00Z",
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [lon - 0.01, lat + offset_y],
                            [lon + 0.01, lat + offset_y],
                        ],
                    },
                    "properties": {"comid": comid, "measure": 54.2},
                }
            ],
        }

    def test_outlet_accepts_snap_at_or_below_200m(self):
        link = resolve_outlet_link(self.feature("410"), self.response())

        self.assertEqual(link["status"], "LINKED")
        self.assertEqual(link["comid"], 101)
        self.assertEqual(link["method"], "NLDI_SNAP_TO_FLOWLINE")
        self.assertLessEqual(link["distance_m"], 200)
        self.assertEqual(link["measure"], 54.2)
        self.assertEqual(len(link["response_sha256"]), 64)

    def test_raindrop_far_snap_and_missing_comid_are_unresolved(self):
        far = resolve_outlet_link(
            self.feature("410"), self.response(offset_y=0.01)
        )
        missing = resolve_outlet_link(
            self.feature("411"), self.response(comid=None)
        )

        self.assertEqual(far["status"], "UNRESOLVED")
        self.assertEqual(far["comid"], None)
        self.assertIn("200", far["reason"])
        self.assertEqual(missing["status"], "UNRESOLVED")
        self.assertEqual(missing["comid"], None)

        raindrop_response = self.response()
        raindrop_response["features"][0]["properties"]["method"] = "RAINDROP_TRACE"
        raindrop = resolve_outlet_link(self.feature("412"), raindrop_response)
        self.assertEqual(raindrop["status"], "UNRESOLVED")
        self.assertIn("raindrop", raindrop["reason"].lower())

    def test_relationship_direction_uses_only_directed_upstream_membership(self):
        features = [self.feature("upstream"), self.feature("target")]
        links = {
            "upstream": {"status": "LINKED", "comid": 11},
            "target": {"status": "LINKED", "comid": 22},
        }
        edges, issues = build_relationships(
            features, links, {22: {11}, 11: set()}
        )
        reversed_edges, _ = build_relationships(
            features, links, {22: set(), 11: {22}}
        )

        self.assertEqual(
            [(edge["upstream_feature_id"], edge["downstream_feature_id"])
             for edge in edges],
            [("upstream", "target")],
        )
        self.assertEqual(
            [(edge["upstream_feature_id"], edge["downstream_feature_id"])
             for edge in reversed_edges],
            [("target", "upstream")],
        )
        self.assertEqual(issues, [])

    def test_unlinked_nodes_remain_without_edges(self):
        features = [self.feature("linked"), self.feature("unlinked")]
        links = {
            "linked": {"status": "LINKED", "comid": 11},
            "unlinked": {"status": "UNRESOLVED", "comid": None,
                         "reason": "no COMID"},
        }

        edges, issues = build_relationships(features, links, {11: set()})

        self.assertEqual(edges, [])
        self.assertEqual(
            [(issue["feature_id"], issue["code"]) for issue in issues],
            [("unlinked", "RFC_OUTLET_UNLINKED")],
        )

    def test_network_outputs_preserve_all_nodes_and_relationship_evidence(self):
        from shapely.geometry import Point
        upstream = SimpleNamespace(
            feature_id="upstream",
            feature_index=0,
            properties={"NWSID": "UP", "OBJ_IDENTIF": 1},
            area_sqmi=12.5,
            outlet=Point(self.outlet),
            geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
        )
        target = SimpleNamespace(
            feature_id="target",
            feature_index=1,
            properties={"NWSID": "DOWN", "OBJ_IDENTIF": 2},
            area_sqmi=30.0,
            outlet=Point(self.outlet),
            geometry=Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]),
        )
        links = {
            "upstream": {
                "status": "LINKED", "comid": 11, "measure": 30.0,
                "method": "NLDI_SNAP_TO_FLOWLINE", "distance_m": 12.0,
                "response_sha256": "a" * 64,
            },
            "target": {
                "status": "LINKED", "comid": 22, "measure": 80.0,
                "method": "NLDI_SNAP_TO_FLOWLINE", "distance_m": 8.0,
                "response_sha256": "b" * 64,
            },
        }
        edges = [{
            "upstream_feature_id": "upstream",
            "downstream_feature_id": "target",
            "upstream_comid": 11,
            "downstream_comid": 22,
            "evidence": "NHDPLUSV2_NLDI_UPSTREAM_FLOWLINES",
            "downstream_navigation_response_sha256": "c" * 64,
        }]

        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            write_network_outputs(
                [upstream, target],
                links,
                {11: set(), 22: {11}},
                edges,
                [],
                out,
                "d" * 64,
            )

            with (out / "rfc_relationships.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                relations = list(csv.DictReader(stream))
            self.assertEqual(len(relations), 1)
            self.assertEqual(relations[0]["upstream_feature_id"], "upstream")
            self.assertEqual(
                relations[0]["downstream_navigation_response_sha256"], "c" * 64
            )
            with (out / "rfc_feature_inventory.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                nodes = list(csv.DictReader(stream))
            self.assertEqual(len(nodes), 2)
            self.assertEqual(
                [node["outlet_link_status"] for node in nodes], ["LINKED", "LINKED"]
            )
            snapshot = json.loads((out / "topology_snapshot.json").read_text())
            self.assertEqual(snapshot["source_archive_sha256"], "d" * 64)
            self.assertEqual(snapshot["rfc_feature_count"], 2)
            self.assertEqual(snapshot["relationship_count"], 1)
            self.assertEqual(snapshot["unresolved_issue_count"], 0)
            archive = out / snapshot["raw_response_archive"]["path"]
            self.assertEqual(json.loads(gzip.decompress(archive.read_bytes())), [])

    def test_network_cache_fetches_directed_navigation_and_reuses_snapshot(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload
            def raise_for_status(self):
                return None
            def json(self):
                return self.payload

        class FakeSession:
            def __init__(self):
                self.calls = []
            def get(self, url, timeout):
                self.calls.append(url)
                if "hydrolocation" in url:
                    return FakeResponse(self.response())
                if "/navigation/UT/flowlines" in url:
                    return FakeResponse({
                        "type": "FeatureCollection",
                        "features": [{"id": "nhdplusv2:101", "properties": {"comid": 101}}],
                    })
                if "/basin" in url:
                    return FakeResponse({
                        "type": "FeatureCollection",
                        "features": [{
                            "type": "Feature",
                            "geometry": {"type": "Polygon", "coordinates": [[
                                [-91, 30], [-90, 30], [-90, 31], [-91, 31], [-91, 30]
                            ]]},
                            "properties": {"comid": 101},
                        }],
                    })
                raise AssertionError(url)
            @staticmethod
            def response():
                lon, lat = RfcNetworkRelationshipTests.outlet
                return {
                    "type": "FeatureCollection",
                    "features": [{
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": [
                            [lon - 0.01, lat + 0.0005], [lon + 0.01, lat + 0.0005]
                        ]},
                        "properties": {"comid": 101, "measure": 54.2},
                    }],
                }

        feature = self.feature("410")
        with tempfile.TemporaryDirectory() as temp:
            session = FakeSession()
            first = fetch_network_cache(
                [feature], Path(temp), refresh=True, session=session,
                sleep_seconds=0,
            )
            self.assertEqual(len(session.calls), 3)
            self.assertIn("/navigation/UT/flowlines", " ".join(session.calls))
            self.assertEqual(first["links"]["410"]["status"], "LINKED")
            self.assertEqual(first["upstream_reach_sets"], {101: {101}})
            self.assertIn("101", first["basins"])

            no_network = FakeSession()
            cached = fetch_network_cache(
                [feature], Path(temp), refresh=False, session=no_network,
                sleep_seconds=0,
            )
            self.assertEqual(no_network.calls, [])
            self.assertEqual(cached, first)


class RfcCandidateTests(unittest.TestCase):
    def feature(self, feature_id, nwsid, x0, x1, outlet):
        from shapely.geometry import Point
        return SimpleNamespace(
            feature_id=feature_id, feature_index=int(feature_id),
            properties={"NWSID": nwsid, "OBJ_IDENTIF": feature_id},
            geometry=Polygon([(x0, 0), (x1, 0), (x1, 1), (x0, 1), (x0, 0)]),
            outlet=Point(outlet), area_sqmi=(x1 - x0) * 100,
            geometry_valid=True, geometry_issue="",
        )

    def test_candidate_unions_only_directed_upstream_components(self):
        upstream = self.feature("1", "UP", 0, 1, (0.5, 0.5))
        target = self.feature("2", "TARGET", 1, 2, (1.5, 0.5))
        unrelated = self.feature("3", "OTHER", 4, 5, (4.5, 0.5))
        result = build_station_candidate(
            {"canonical_nws_id": "TARGET"}, [upstream, target, unrelated],
            [{"upstream_feature_id": "1", "downstream_feature_id": "2"}],
            {"1": {"status": "LINKED", "comid": 11},
             "2": {"status": "LINKED", "comid": 22},
             "3": {"status": "LINKED", "comid": 33}},
            target_basin=Polygon([(0, -1), (3, -1), (3, 2), (0, 2), (0, -1)]),
        )
        self.assertEqual(result["candidate_feature_ids"], ["1", "2"])
        self.assertEqual(result["connectivity_classification"], "NHDPLUS_LINKED_PROXY")
        self.assertGreater(result["candidate_union_area_sqmi"], 0)
        self.assertEqual(result["candidate_raw_component_area_sum_sqmi"], 200)
        self.assertFalse(result["legacy_map_geometry_verified"])

    def test_candidate_is_withheld_when_upstream_link_coverage_is_incomplete(self):
        target = self.feature("2", "TARGET", 1, 2, (1.5, 0.5))
        unresolved = self.feature("3", "NOID", 2, 3, (2.5, 0.5))
        result = build_station_candidate(
            {"canonical_nws_id": "TARGET"}, [target, unresolved], [],
            {"2": {"status": "LINKED", "comid": 22},
             "3": {"status": "UNRESOLVED", "comid": None}},
            target_basin=Polygon([(0, -1), (4, -1), (4, 2), (0, 2), (0, -1)]),
        )
        self.assertIsNone(result["geometry"])
        self.assertEqual(result["candidate_status"], "WITHHELD_INCOMPLETE_ROUTED_COVERAGE")
        self.assertIn("3", result["unresolved_feature_ids"])

    def test_candidate_is_withheld_for_invalid_original_rfc_component(self):
        upstream = self.feature("1", "UP", 0, 1, (0.5, 0.5))
        upstream.geometry_valid = False
        upstream.geometry_issue = "Self-intersection"
        target = self.feature("2", "TARGET", 1, 2, (1.5, 0.5))
        result = build_station_candidate(
            {"canonical_nws_id": "TARGET"}, [upstream, target],
            [{"upstream_feature_id": "1", "downstream_feature_id": "2"}],
            {"1": {"status": "LINKED", "comid": 11},
             "2": {"status": "LINKED", "comid": 22}},
            target_basin=Polygon([(0, -1), (3, -1), (3, 2), (0, 2), (0, -1)]),
        )
        self.assertIsNone(result["geometry"])
        self.assertEqual(result["candidate_status"], "WITHHELD_INVALID_SOURCE_COMPONENT")

    def test_metrics_are_geodesic_and_bounded(self):
        first = Polygon([(-91, 30), (-90, 30), (-90, 31), (-91, 31), (-91, 30)])
        second = Polygon([(-90.5, 30), (-89.5, 30), (-89.5, 31), (-90.5, 31), (-90.5, 30)])
        metrics = compare_geometries(first, second)
        self.assertGreater(metrics["intersection_sqmi"], 0)
        self.assertGreater(metrics["union_sqmi"], metrics["intersection_sqmi"])
        for key in ("iou_pct", "candidate_coverage_pct", "reference_coverage_pct"):
            self.assertGreaterEqual(metrics[key], 0)
            self.assertLessEqual(metrics[key], 100)

    def test_all_29_points_are_accounted_with_no_borrowed_nldi(self):
        points = [{"historical_point_id": f"P{i}", "canonical_nws_id": f"P{i}"}
                  for i in range(29)]
        results = [{
            "canonical_nws_id": point["canonical_nws_id"],
            "geometry": None, "candidate_feature_ids": [],
            "candidate_status": "UNRESOLVED_NO_MATCHING_RFC_FEATURE",
            "connectivity_classification": "UNRESOLVED",
            "legacy_map_geometry_verified": False,
            "full_nldi_metrics": None, "incremental_nldi_metrics": None,
            "nldi_reference_status": "NO_EXISTING_NLDI_REFERENCE",
            "unresolved_feature_ids": [], "reason": "fixture",
        } for point in points]
        with tempfile.TemporaryDirectory() as temp:
            write_station_outputs(points, results, Path(temp))
            with (Path(temp) / "station_reconciliation.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                rows = list(csv.DictReader(stream))
            candidates = json.loads((Path(temp) / "candidate_aggregates.geojson").read_text())
            self.assertEqual(len(rows), 29)
            self.assertTrue(all(row["nldi_reference_status"] == "NO_EXISTING_NLDI_REFERENCE" for row in rows))
            self.assertEqual(candidates["features"], [])

    def test_candidate_never_claims_legacy_map_equivalence(self):
        result = build_station_candidate(
            {"canonical_nws_id": "MISSING"}, [], [], {}, target_basin=None
        )
        self.assertFalse(result["legacy_map_geometry_verified"])
        self.assertEqual(result["historical_map_equivalence"], "NOT_ESTABLISHED")

    def test_nldi_references_require_same_site_verified_crosswalk(self):
        basins = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"id": "A"},
             "geometry": {"type": "Polygon", "coordinates": [[
                 [0, 0], [1, 0], [1, 1], [0, 1], [0, 0]
             ]]}},
            {"type": "Feature", "properties": {"id": "NEARBY"},
             "geometry": {"type": "Polygon", "coordinates": [[
                 [1, 0], [2, 0], [2, 1], [1, 1], [1, 0]
             ]]}},
        ]}
        points = [{"canonical_nws_id": "VERIFIED"}, {"canonical_nws_id": "UNRESOLVED"}]
        crosswalk = [
            {"canonical_nws_id": "VERIFIED", "existing_dashboard_usgs_id": "A",
             "usgs_site_id_confirmed": "A"},
            {"canonical_nws_id": "UNRESOLVED", "existing_dashboard_usgs_id": "NEARBY",
             "usgs_site_id_confirmed": "OTHER"},
        ]
        gages = [{"id": "A", "upstream_from": []},
                 {"id": "NEARBY", "upstream_from": []}]
        references = load_verified_nldi_references(points, crosswalk, gages, basins)
        self.assertEqual(set(references), {"VERIFIED"})
        self.assertEqual(references["VERIFIED"]["status"], "VERIFIED_SAME_SITE_NLDI_REFERENCE")


if __name__ == "__main__":
    unittest.main()
