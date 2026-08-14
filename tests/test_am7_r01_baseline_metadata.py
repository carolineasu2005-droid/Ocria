"""AM7-R01 baseline/provenance metadata contract tests."""

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "am7" / "baselines" / "AM7-R01-source-baseline.json"
BASELINE_RECORD = ROOT / "docs" / "am7" / "baselines" / "AM7-R01-source-baseline.md"
C02_BEFORE = ROOT / "docs" / "am7" / "acceptance" / "evidence" / "AM7-R01-C02" / "before-configuration.log"

BASELINE_COMMIT = "a7c941989a038d7a998ccee707e14b4fd9125cda"
BASELINE_TREE = "b3ddfa62cf1673ffc59887b06517baacf9c79cd7"
OCRIA_ORIGIN = "https://github.com/carolineasu2005-droid/Ocria.git"
BOSSOCR_UPSTREAM = "https://github.com/carolineasu2005-droid/Boss-OCR.git"


class Am7R01BaselineMetadataTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_source_identity_and_history_preserving_relation_are_frozen(self):
        self.assertEqual(self.data["schema_version"], "am7-source-baseline-v1")
        self.assertEqual(self.data["source"]["commit"], BASELINE_COMMIT)
        self.assertEqual(self.data["source"]["tree"], BASELINE_TREE)
        self.assertEqual(self.data["source"]["tag"], "V1.3.1")
        self.assertEqual(
            self.data["relationship"]["type"],
            "history-preserving-derived-repository",
        )
        self.assertFalse(self.data["relationship"]["automatic_runtime_fallback"])

    def test_c01_confirmation_and_c02_boundary_are_independent(self):
        confirmation = self.data["confirmation"]
        boundary = self.data["repository_boundary"]
        self.assertEqual(confirmation["status"], "confirmed")
        self.assertEqual(boundary["origin_status"], "configured")
        self.assertEqual(boundary["origin_url"], OCRIA_ORIGIN)
        self.assertEqual(boundary["upstream_remote_name"], "bossocr-upstream")
        self.assertEqual(boundary["upstream_fetch_url"], BOSSOCR_UPSTREAM)
        self.assertTrue(boundary["upstream_push_disabled"])

    def test_c01_absent_origin_state_is_preserved_as_historical_evidence(self):
        c01_record = BASELINE_RECORD.read_text(encoding="utf-8")
        before = C02_BEFORE.read_text(encoding="utf-8")
        self.assertIn("origin_status=absent_pending_human", c01_record)
        self.assertIn("origin_url=null", c01_record)
        self.assertIn("error: No such remote 'origin'", before)
        self.assertEqual(self.data["confirmation"]["status"], "confirmed")


if __name__ == "__main__":
    unittest.main()
