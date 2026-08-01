import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from ocr_records import (
    DOCUMENT_VERSION,
    NOT_IMPLEMENTED,
    STORAGE_SCHEMA_VERSION,
    SUPPORTED_STORAGE_SCHEMA_VERSIONS,
    CandidateOcrDocument,
    CaptureStatus,
    CaptureSummary,
    CaptureType,
    LEGACY_STORAGE_SCHEMA_VERSION,
    NormalizationStatus,
    OcrBox,
    OcrLineMapping,
    OcrScreenRecord,
    OcrTextSegment,
    ProcessingStatus,
    RecordVersionError,
    RunManifest,
    RunStatus,
    json_dumps,
    timezone_iso,
    to_json_compatible,
)
from ocr_normalization import (
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NORMALIZATION_VERSION,
    canonical_normalization_config,
    normalization_config_digest,
)


class OcrRecordModelTests(unittest.TestCase):
    def make_screen(self):
        raw_values = (
            "中文 Python C++ C# .NET",
            "SLG+X 0-1 2D/3D & <tag>",
        )
        boxes = tuple(
            OcrBox(
                box_id="box-{0}".format(index),
                raw_text=text,
                confidence=None if index == 1 else 0.987,
                bbox=((1, 2), (30.5, 2), (30.5, 18), (1, 18)),
                original_index=index,
                screen_index=1,
            )
            for index, text in enumerate(raw_values)
        )
        config = DEFAULT_OCR_NORMALIZATION_CONFIG
        snapshot = canonical_normalization_config(config)
        normalized_text = "\n".join(raw_values)
        return OcrScreenRecord(
            run_id="run-中文",
            candidate_record_id="candidate-1",
            screen_id="screen-1",
            screen_index=1,
            attempt_index=1,
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            captured_at="2026-07-30T12:00:00+08:00",
            raw_boxes=boxes,
            raw_text="\n".join(raw_values),
            normalized_text=normalized_text,
            normalized_text_length=len(normalized_text),
            comparison_text=normalized_text.lower().replace(" ", ""),
            comparison_text_length=len(normalized_text.lower().replace(" ", "")),
            segments=(OcrTextSegment(
                segment_id="screen-1:line:0",
                screen_index=1,
                order=0,
                normalized_text=normalized_text,
                comparison_text=normalized_text.lower().replace(" ", ""),
                ocr_box_ids=("box-0", "box-1"),
                char_count=len(normalized_text),
                processing_status=ProcessingStatus.NORMALIZED,
            ),),
            ordered_box_ids=("box-0", "box-1"),
            effective_box_ids=("box-0", "box-1"),
            line_mapping=(
                OcrLineMapping("box-0", 0),
                OcrLineMapping("box-1", 0),
            ),
            deduplicated_box_count=2,
            processing_status=ProcessingStatus.NORMALIZED,
            normalization_status=NormalizationStatus.COMPLETED,
            normalization_version=NORMALIZATION_VERSION,
            normalization_config_version=config.normalization_config_version,
            normalization_config_digest=normalization_config_digest(snapshot),
            effective_min_confidence=config.effective_min_confidence,
            confidence_threshold_source="run_manifest",
            duplicate_gray_pair_count=0,
            eligible_box_count=2,
            low_confidence_box_count=0,
            empty_normalized_box_count=0,
            exact_hash="a" * 64,
            fingerprint_version="r03-v1",
            rule_evaluation_mode="legacy_shadow",
            legacy_match=True,
            r04_match=False,
            comparison_outcome="legacy_only",
            legacy_rule_index=0,
            r04_rule_index=None,
        )

    def test_screen_round_trip_preserves_raw_text_bbox_enum_and_nulls(self):
        screen = self.make_screen()
        encoded = screen.to_json()
        restored = OcrScreenRecord.from_dict(json.loads(encoded))

        self.assertEqual(restored, screen)
        self.assertIn("中文 Python C++ C# .NET", encoded)
        self.assertNotIn("\\u4e2d", encoded)
        self.assertIsNone(restored.raw_boxes[1].confidence)
        self.assertEqual(
            restored.raw_boxes[0].bbox,
            ((1, 2), (30.5, 2), (30.5, 18), (1, 18)),
        )
        self.assertEqual(restored.capture_type, CaptureType.FORMAL_SCREEN)
        self.assertEqual(restored.processing_status, ProcessingStatus.NORMALIZED)
        self.assertEqual(restored.rule_evaluation_mode, "legacy_shadow")
        self.assertTrue(restored.legacy_match)
        self.assertFalse(restored.r04_match)
        self.assertEqual(restored.comparison_outcome, "legacy_only")
        self.assertEqual(restored.legacy_rule_index, 0)
        self.assertIsNone(restored.r04_rule_index)

    def test_raw_text_is_not_normalized_or_modified(self):
        raw_text = "  C++\tC#\n.NET  SLG+X 0-1 2D/3D  "
        box = OcrBox("box", raw_text, 0.9, None, 0, None)

        restored = OcrBox.from_dict(json.loads(box.to_json()))

        self.assertEqual(restored.raw_text, raw_text)

    def test_segment_defaults_are_explicitly_not_implemented(self):
        segment = OcrTextSegment(segment_id="segment-1", screen_index=1)

        self.assertIsNone(segment.normalized_text)
        self.assertIsNone(segment.comparison_text)
        self.assertIsNone(segment.char_count)
        self.assertEqual(segment.ocr_box_ids, ())
        self.assertEqual(
            segment.processing_status, ProcessingStatus.NOT_IMPLEMENTED
        )

    def test_candidate_document_round_trip_has_no_fake_aggregation(self):
        screen = self.make_screen()
        summary = CaptureSummary(
            actual_screen_count=1,
            ocr_attempt_count=2,
            scroll_attempt_count=0,
            scroll_retry_count=0,
            end_screen_index=1,
            capture_status=CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
            abort_reason=None,
        )
        document = CandidateOcrDocument(
            run_id=screen.run_id,
            candidate_record_id=screen.candidate_record_id,
            sequence_number=1,
            created_at="2026-07-30T12:00:00+08:00",
            completed_at="2026-07-30T12:01:00+08:00",
            capture_status=CaptureStatus.COMPLETED,
            screens=(screen,),
            capture_summary=summary,
            versions={
                "normalization": NORMALIZATION_VERSION,
                "aggregation": None,
                "similarity": None,
                "dynamic_end": None,
            },
            metadata={"source": "虚构测试"},
        )

        restored = CandidateOcrDocument.from_dict(
            json.loads(document.to_json())
        )

        self.assertEqual(restored, document)
        self.assertIsNone(restored.document_text)
        self.assertEqual(restored.document_segments, ())
        self.assertEqual(restored.document_build_status, NOT_IMPLEMENTED)
        self.assertEqual(restored.document_version, DOCUMENT_VERSION)
        self.assertEqual(
            restored.storage_schema_version, STORAGE_SCHEMA_VERSION
        )

    def test_unknown_additive_fields_are_ignored_during_restore(self):
        data = self.make_screen().to_dict()
        data["future_top_level"] = {"new": True}
        data["raw_boxes"][0]["future_box_field"] = "kept by future reader"

        restored = OcrScreenRecord.from_dict(data)

        self.assertEqual(restored.raw_boxes[0].raw_text, "中文 Python C++ C# .NET")
        self.assertFalse(hasattr(restored, "future_top_level"))

    def test_legacy_1_0_screen_without_r04_fields_restores_as_not_attempted(self):
        data = self.make_screen().to_dict()
        data["storage_schema_version"] = LEGACY_STORAGE_SCHEMA_VERSION
        for field_name in (
            "raw_text_source",
            "raw_text_length",
            "normalized_text_length",
            "comparison_text_length",
            "ordered_box_ids",
            "effective_box_ids",
            "excluded_empty_box_ids",
            "suppressed_duplicate_box_ids",
            "line_mapping",
            "deduplicated_box_count",
            "duplicate_groups",
            "normalization_status",
            "normalization_warnings",
            "normalization_error_type",
            "normalization_config_version",
            "normalization_config_digest",
            "effective_min_confidence",
            "confidence_threshold_source",
            "duplicate_gray_pair_count",
            "eligible_box_count",
            "low_confidence_box_count",
            "empty_normalized_box_count",
            "ocr_min_confidence",
        ):
            data.pop(field_name, None)

        restored = OcrScreenRecord.from_dict(data)

        self.assertEqual(
            restored.storage_schema_version,
            LEGACY_STORAGE_SCHEMA_VERSION,
        )
        self.assertEqual(
            restored.normalization_status,
            NormalizationStatus.NOT_ATTEMPTED,
        )
        self.assertEqual(restored.ordered_box_ids, ())
        self.assertEqual(restored.duplicate_groups, ())
        self.assertIsNone(restored.ocr_min_confidence)

    def test_direct_restore_rejects_missing_invalid_and_future_versions(self):
        cases = (
            (None, "MissingVersionError", None),
            (7, "InvalidVersionTypeError", "<int>"),
            ("99.0.0", "UnsupportedVersionError", "99.0.0"),
        )
        for value, error_type, actual in cases:
            data = self.make_screen().to_dict()
            if value is None:
                data.pop("storage_schema_version")
            else:
                data["storage_schema_version"] = value
            with self.subTest(value=value):
                with self.assertRaises(RecordVersionError) as caught:
                    OcrScreenRecord.from_dict(data)
                self.assertEqual(caught.exception.error_type, error_type)
                self.assertEqual(caught.exception.actual_version, actual)
                self.assertEqual(
                    caught.exception.supported_versions,
                    SUPPORTED_STORAGE_SCHEMA_VERSIONS,
                )

    def test_manifest_round_trip_converts_paths_and_enum(self):
        config = DEFAULT_OCR_NORMALIZATION_CONFIG
        snapshot = canonical_normalization_config(config)
        manifest = RunManifest(
            run_id="run-1",
            started_at="2026-07-30T12:00:00+08:00",
            status=RunStatus.RUNNING,
            platform="Windows",
            python_version="3.13.5",
            action_mode="favorite",
            max_screen_count=8,
            normalization_version=NORMALIZATION_VERSION,
            normalization_config_version=config.normalization_config_version,
            normalization_config_digest=normalization_config_digest(snapshot),
            effective_min_confidence=config.effective_min_confidence,
            normalization_config=snapshot,
            rule_evaluation_mode="legacy_shadow",
            data_files={"screens": Path("screens.jsonl")},
        )

        restored = RunManifest.from_dict(json.loads(manifest.to_json()))

        self.assertEqual(restored.status, RunStatus.RUNNING)
        self.assertEqual(restored.data_files, {"screens": "screens.jsonl"})
        self.assertEqual(restored.normalization_version, NORMALIZATION_VERSION)
        self.assertIsNone(restored.aggregation_version)
        self.assertIsNone(restored.similarity_version)
        self.assertIsNone(restored.dynamic_end_version)

    def test_recursive_conversion_supports_datetime_path_tuple_and_optional(self):
        value = {
            "when": datetime(2026, 7, 30, 4, 0, tzinfo=timezone.utc),
            "path": Path("data") / "ocr_runs",
            "enum": CaptureType.LOAD_RETRY,
            "tuple": (1, None, "中文"),
        }

        converted = to_json_compatible(value)

        self.assertEqual(converted["when"], "2026-07-30T04:00:00+00:00")
        self.assertEqual(converted["path"], str(Path("data") / "ocr_runs"))
        self.assertEqual(converted["enum"], "load_retry")
        self.assertEqual(converted["tuple"], [1, None, "中文"])

    def test_naive_datetime_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            timezone_iso(datetime(2026, 7, 30, 12, 0))

    def test_unsupported_value_is_rejected_before_json_serialization(self):
        with self.assertRaisesRegex(TypeError, "unsupported JSON value type"):
            json_dumps({"bad": object()})

    def test_new_schema_accepts_only_three_normalization_states(self):
        data = self.make_screen().to_dict()
        data["normalization_status"] = "partial"

        with self.assertRaises(ValueError):
            OcrScreenRecord.from_dict(data)

        self.assertEqual(
            {item.value for item in NormalizationStatus},
            {"not_attempted", "completed", "failed"},
        )

    def test_new_schema_rejects_illegal_status_field_combinations(self):
        completed = self.make_screen()
        cases = (
            {"processing_status": ProcessingStatus.RAW_ONLY},
            {"normalized_text": None},
            {"normalization_error_type": "SyntheticError"},
            {
                "normalization_status": NormalizationStatus.NOT_ATTEMPTED,
                "processing_status": ProcessingStatus.RAW_ONLY,
            },
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(completed, **changes)

    def test_new_schema_rejects_missing_segment_source_box(self):
        screen = self.make_screen()
        bad_segment = replace(
            screen.segments[0],
            ocr_box_ids=("missing-box",),
        )

        with self.assertRaisesRegex(ValueError, "segment"):
            replace(screen, segments=(bad_segment,))

    def test_manifest_rejects_noncanonical_digest(self):
        config = DEFAULT_OCR_NORMALIZATION_CONFIG
        snapshot = canonical_normalization_config(config)

        with self.assertRaisesRegex(ValueError, "digest"):
            RunManifest(
                run_id="run-bad",
                started_at="2026-07-30T12:00:00+08:00",
                status=RunStatus.RUNNING,
                platform="Windows",
                python_version="3.13.5",
                data_files={},
                normalization_version=NORMALIZATION_VERSION,
                normalization_config_version=config.normalization_config_version,
                normalization_config_digest="0" * 64,
                effective_min_confidence=config.effective_min_confidence,
                normalization_config=snapshot,
                rule_evaluation_mode="legacy_shadow",
            )

    def test_manifest_rejects_incomplete_config_snapshot(self):
        snapshot = canonical_normalization_config(
            DEFAULT_OCR_NORMALIZATION_CONFIG
        )
        snapshot.pop("duplicate_gray_size_similarity")

        with self.assertRaisesRegex(ValueError, "config is invalid"):
            RunManifest(
                run_id="run-incomplete-config",
                started_at="2026-07-30T12:00:00+08:00",
                status=RunStatus.RUNNING,
                platform="Windows",
                python_version="3.13.5",
                data_files={},
                normalization_version=NORMALIZATION_VERSION,
                normalization_config_version=(
                    DEFAULT_OCR_NORMALIZATION_CONFIG.normalization_config_version
                ),
                normalization_config=snapshot,
                normalization_config_digest=normalization_config_digest(
                    snapshot
                ),
                effective_min_confidence=(
                    DEFAULT_OCR_NORMALIZATION_CONFIG.effective_min_confidence
                ),
                rule_evaluation_mode="legacy_shadow",
            )


if __name__ == "__main__":
    unittest.main()
