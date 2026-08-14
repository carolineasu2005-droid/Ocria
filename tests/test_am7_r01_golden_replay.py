"""Strict, offline AM7-R01 synthetic Golden replay contract."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import unittest

from ocr_replay import (
    load_ocr_run,
    replay_candidate_aggregation,
    replay_candidate_similarity,
    replay_dynamic_end,
    replay_screen_normalization,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "am7_r01" / "golden_replay_v1"

APPROVED_SYNTHETIC_TEXT = {
    "Synthetic Candidate 001", "Skill Alpha", "Skill Beta", "Python", "SQL", "Unity",
    "Data Analysis", "Automation Testing", "Requirement Analysis", "Project Planning",
    "Documentation", "Synthetic Project Orion", "Synthetic Project Vega", "Short A", "Short B",
}

def plain(value):
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_dict"):
        return plain(value.to_dict())
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def canonical(value):
    return json.dumps(plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def text_digest(value):
    return sha256(value.encode("utf-8")).hexdigest()


def profile_screen(record, replayed):
    return {
        "screen_id": record.screen_id,
        "stored_canonical_json_sha256": digest(record),
        "exact_hash": record.exact_hash,
        "normalization": {
            "status": plain(record.normalization_status),
            "normalized_text_sha256": text_digest(replayed.normalized.normalized_text),
            "config_digest": record.normalization_config_digest,
        },
        "aggregation": {
            "status": plain(record.aggregation_status),
            "matched_segment_ids": list(record.matched_segment_ids),
            "new_segment_ids": list(record.new_segment_ids),
            "uncertain_segment_ids": list(record.uncertain_segment_ids),
        },
        "similarity": {
            "status": plain(record.similarity_result.similarity_status) if record.similarity_result else None,
            "comparison_class": plain(record.similarity_result.comparison_class) if record.similarity_result else None,
            "effective_new_status": plain(record.similarity_result.effective_new_status) if record.similarity_result else None,
            "result_sha256": digest(record.similarity_result) if record.similarity_result else None,
        },
        "position": {
            "status": record.position_status,
            "page_change_status": record.page_change_status,
            "reference_screen_id": record.reference_screen_id,
            "is_position_confirmation": record.is_position_confirmation,
        },
    }


class Am7R01GoldenReplayTests(unittest.TestCase):
    def setUp(self):
        self.expected = json.loads((FIXTURE / "expected-summary.json").read_text(encoding="utf-8"))
        self.replay = load_ocr_run(FIXTURE, strict=True)

    def test_fixture_text_is_explicitly_limited_to_the_human_approved_pool(self):
        self.assertEqual(set(self.expected["synthetic_text_inventory"]), APPROVED_SYNTHETIC_TEXT)
        observed = set()
        for screen in self.replay.screens:
            observed.update(box.raw_text for box in screen.raw_boxes)
        self.assertTrue(observed.issubset(APPROVED_SYNTHETIC_TEXT))
        self.assertTrue((FIXTURE / "README.md").is_file())

    def test_strict_load_and_frozen_expected_replay_are_exactly_equivalent(self):
        self.assertEqual(self.replay.issues, [])
        candidate = self.replay.candidates[0]
        r04 = [
            replay_screen_normalization(screen, manifest=self.replay.manifest, strict=True)
            for screen in self.replay.screens
        ]
        r05 = replay_candidate_aggregation(candidate, self.replay.manifest, strict=True)
        r06 = replay_candidate_similarity(candidate, self.replay.manifest, strict=True)
        r07_candidate = self.replay.candidates[1]
        r07 = replay_dynamic_end(r07_candidate)
        actual = {
            "schema": "am7-golden-replay-summary-v1",
            "fixture_id": "synthetic-golden-replay-v1",
            "strict_reader": {"issue_count": len(self.replay.issues), "result": "PASS"},
            "record_counts": {
                "screens": len(self.replay.screens),
                "candidates": len(self.replay.candidates),
                "errors": len(self.replay.errors),
            },
            "manifest": {
                "storage_schema_version": self.replay.manifest.storage_schema_version,
                "normalization_config_digest": self.replay.manifest.normalization_config_digest,
                "aggregation_config_digest": self.replay.manifest.aggregation_config_digest,
                "similarity_config_digest": self.replay.manifest.similarity_config_digest,
                "dynamic_end_version": self.replay.manifest.dynamic_end_version,
            },
            "screen_order": [record.screen_id for record in self.replay.screens],
            "screens": [profile_screen(record, result) for record, result in zip(self.replay.screens, r04)],
            "candidate": {
                "candidate_record_id": candidate.candidate_record_id,
                "canonical_json_sha256": digest(candidate),
                "document_text_sha256": text_digest(candidate.document_text or ""),
                "r05_rebuilt_canonical_json_sha256": digest(r05.rebuilt),
                "r05_issue_count": len(r05.issues),
                "r06_rebuilt_canonical_json_sha256": digest(r06.rebuilt),
                "r06_issue_count": len(r06.issues),
            },
            "r07_candidate": {
                "candidate_record_id": r07_candidate.candidate_record_id,
                "canonical_json_sha256": digest(r07_candidate),
                "r07": plain(r07),
            },
            "synthetic_text_inventory": self.expected["synthetic_text_inventory"],
        }
        actual["replay_canonical_sha256"] = digest(actual)
        actual["fixture_file_sha256"] = {
            name: sha256((FIXTURE / name).read_bytes()).hexdigest()
            for name in ("run.json", "screens.jsonl", "candidates.jsonl", "errors.jsonl")
        }
        self.assertEqual(actual, self.expected)
        self.assertTrue(r07.no_new_text_candidate)
        self.assertEqual(r07.consecutive_no_new_count, 2)
        self.assertEqual(r07.offline_bottom_status, "possible_scroll_bottom")


if __name__ == "__main__":
    unittest.main()
