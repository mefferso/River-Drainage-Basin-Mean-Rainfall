import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase4BWorkflowContractTests(unittest.TestCase):
    def test_refresh_workflow_is_feature_branch_only_and_validates_before_commit(self):
        workflow = (ROOT / ".github/workflows/phase4b-rfc-reconstruction.yml").read_text()
        self.assertIn("branches: [phase4b/map-basin-reconstruction]", workflow)
        self.assertIn("if: github.ref == 'refs/heads/phase4b/map-basin-reconstruction'", workflow)
        self.assertIn("sha256sum --check", workflow)
        self.assertIn("python scripts/validate_phase4b_outputs.py", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("git push origin HEAD:phase4b/map-basin-reconstruction", workflow)
        self.assertIn("paths-ignore:", workflow)
        self.assertNotIn("refs/heads/main", workflow)

    def test_phase4b_builder_does_not_touch_production_rainfall_or_phase2_data(self):
        builder = (ROOT / "scripts/build_phase4b_rfc_aggregates.py").read_text()
        self.assertIn("candidate_aggregates.geojson", builder)
        self.assertIn("legacy_map_geometry_verified", builder)
        self.assertIn("historical_map_equivalence", builder)
        self.assertNotIn("scripts/update.py", builder)
        self.assertNotIn("Path(\"config/gages.json\").write", builder)
        self.assertGreater(
            builder.rfind('if __name__ == "__main__":'),
            builder.index("def load_rfc_features("),
            "CLI must not execute before runtime functions are defined",
        )

    def test_handoff_keeps_modern_qpe_and_original_rfc_map_distinct(self):
        report = (ROOT / "docs/PHASE4B_HISTORICAL_MAP_RECONSTRUCTION.md").read_text()
        self.assertIn("Modern MRMS MAP is not interchangeable with legacy RFC MAP", report)
        self.assertIn("No Phase 4B geometry is certified", report)
        self.assertIn("original Excel binaries", report)
        self.assertIn("Phase 4C", report)


if __name__ == "__main__":
    unittest.main()
