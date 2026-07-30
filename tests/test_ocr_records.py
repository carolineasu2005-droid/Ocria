import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ocr_records import (
    DOCUMENT_VERSION,
    NOT_IMPLEMENTED,
    STORAGE_SCHEMA_VERSION,
    CandidateOcrDocument,
    CaptureStatus,
    CaptureSummary,
    CaptureType,
    OcrBox,
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
            exact_hash="a" * 64,
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
        self.assertEqual(restored.processing_status, ProcessingStatus.RAW_ONLY)

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
                "normalization": None,
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
                    (STORAGE_SCHEMA_VERSION,),
                )

    def test_manifest_round_trip_converts_paths_and_enum(self):
        manifest = RunManifest(
            run_id="run-1",
            started_at="2026-07-30T12:00:00+08:00",
            status=RunStatus.RUNNING,
            platform="Windows",
            python_version="3.13.5",
            action_mode="favorite",
            max_screen_count=8,
            data_files={"screens": Path("screens.jsonl")},
        )

        restored = RunManifest.from_dict(json.loads(manifest.to_json()))

        self.assertEqual(restored.status, RunStatus.RUNNING)
        self.assertEqual(restored.data_files, {"screens": "screens.jsonl"})
        self.assertIsNone(restored.normalization_version)
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


if __name__ == "__main__":
    unittest.main()
