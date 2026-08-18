import json
import unittest
from dataclasses import fields as dataclass_fields, replace
from datetime import datetime, timezone
from pathlib import Path

from ocr_records import (
    DOCUMENT_VERSION,
    DocumentBuildStatus,
    ComparisonClass,
    EffectiveDecision,
    EffectiveNewDecision,
    EffectiveNewStatus,
    OcrSimilarityResult,
    ReferenceSource,
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
    R06_STORAGE_SCHEMA_VERSION,
    RunManifest,
    RunStatus,
    ScreeningProfileBinding,
    SimilarityStatus,
    recompute_similarity_summary,
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
from ocr_similarity import (
    DEFAULT_OCR_SIMILARITY_CONFIG,
    SIMILARITY_CONFIG_VERSION,
    SIMILARITY_VERSION,
    canonical_similarity_config,
    similarity_config_digest,
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

    def test_r07_screen_fields_round_trip_and_r06_reader_defaults_unknown(self):
        screen = replace(
            self.make_screen(),
            dynamic_end_version="r07-v1",
            position_status="same",
            page_change_status="same",
            reference_screen_id="screen-previous",
            is_position_confirmation=True,
            prediction_reason="possible_scroll_bottom",
        )

        restored = OcrScreenRecord.from_dict(json.loads(screen.to_json()))
        self.assertEqual(restored, screen)

        legacy_r06 = screen.to_dict()
        legacy_r06["storage_schema_version"] = R06_STORAGE_SCHEMA_VERSION
        for field_name in (
            "dynamic_end_version",
            "position_status",
            "page_change_status",
            "reference_screen_id",
            "is_position_confirmation",
            "prediction_reason",
        ):
            legacy_r06.pop(field_name, None)
        restored_r06 = OcrScreenRecord.from_dict(legacy_r06)
        self.assertIsNone(restored_r06.dynamic_end_version)
        self.assertIsNone(restored_r06.position_status)
        self.assertIsNone(restored_r06.is_position_confirmation)

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
            dynamic_end_mode="shadow",
            dynamic_end_reason=None,
            scan_slot_count=1,
            normal_scroll_count=0,
            unique_position_count=1,
            ocr_attempt_count=2,
            scroll_retry_count=0,
            focus_restore_count=0,
            first_predicted_end_screen=None,
            first_predicted_end_reason=None,
            prediction_would_miss_content=None,
            prediction_would_miss_rule_match=None,
            prediction_observation_complete=None,
            prediction_evidence_complete=None,
        )

        payload = document.to_dict()
        restored = CandidateOcrDocument.from_dict(json.loads(document.to_json()))

        self.assertEqual(restored, document)
        self.assertIsNone(restored.document_text)
        self.assertEqual(restored.document_segments, ())
        self.assertEqual(restored.document_build_status, DocumentBuildStatus.NOT_ATTEMPTED)
        self.assertEqual(restored.document_version, "r05-document-v1")
        self.assertEqual(
            restored.storage_schema_version, STORAGE_SCHEMA_VERSION
        )
        self.assertEqual(restored.dynamic_end_mode, "shadow")
        self.assertIsNone(restored.dynamic_end_reason)
        self.assertIsNone(restored.prediction_would_miss_content)
        self.assertTrue(
            {
                "screening_profile_id",
                "profile_version",
                "criteria_digest",
                "criteria",
                "criterion_text",
                "screening_profile_binding",
            }.isdisjoint(payload)
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
        binding = ScreeningProfileBinding(
            screening_profile_id="sp_" + "a" * 32,
            profile_version=3,
            criteria_digest="sha256:" + "b" * 64,
        )
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
            dynamic_end_version="r07-v1",
            dynamic_end_mode="shadow",
            dynamic_end_config={"no_new_text_threshold": 2},
            screening_profile_binding=binding,
            data_files={"screens": Path("screens.jsonl")},
        )

        restored = RunManifest.from_dict(json.loads(manifest.to_json()))

        self.assertEqual(restored.status, RunStatus.RUNNING)
        self.assertEqual(restored.data_files, {"screens": "screens.jsonl"})
        self.assertEqual(restored.normalization_version, NORMALIZATION_VERSION)
        self.assertIsNone(restored.aggregation_version)
        self.assertIsNone(restored.similarity_version)
        self.assertEqual(restored.dynamic_end_version, "r07-v1")
        self.assertEqual(restored.dynamic_end_mode, "shadow")
        self.assertEqual(
            restored.dynamic_end_config, {"no_new_text_threshold": 2}
        )
        self.assertEqual(restored.screening_profile_binding, binding)

        legacy = manifest.to_dict()
        legacy.pop("screening_profile_binding")
        self.assertIsNone(
            RunManifest.from_dict(legacy).screening_profile_binding
        )

        partial_binding = manifest.to_dict()
        partial_binding["screening_profile_binding"] = {
            "screening_profile_id": binding.screening_profile_id,
            "profile_version": binding.profile_version,
        }
        with self.assertRaisesRegex(ValueError, "binding"):
            RunManifest.from_dict(partial_binding)

    def test_screening_profile_binding_validation_and_json_round_trip(self):
        binding = ScreeningProfileBinding(
            screening_profile_id="sp_" + "c" * 32,
            profile_version=1,
            criteria_digest="sha256:" + "d" * 64,
        )

        self.assertEqual(
            ScreeningProfileBinding.from_dict(json.loads(binding.to_json())),
            binding,
        )
        cases = (
            {
                "screening_profile_id": "sp_" + "C" * 32,
                "profile_version": 1,
                "criteria_digest": binding.criteria_digest,
            },
            {
                "screening_profile_id": binding.screening_profile_id,
                "profile_version": True,
                "criteria_digest": binding.criteria_digest,
            },
            {
                "screening_profile_id": binding.screening_profile_id,
                "profile_version": 1,
                "criteria_digest": "sha256:" + "D" * 64,
            },
        )
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    ScreeningProfileBinding(**values)

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

    def test_r06_disabled_round_trip_and_nested_projection_contract(self):
        screen = self.make_screen()
        self.assertEqual(screen.storage_schema_version, "1.4.0")
        self.assertIsNone(screen.similarity_result)
        restored = OcrScreenRecord.from_dict(screen.to_dict())
        self.assertEqual(restored, screen)
        with self.assertRaisesRegex(ValueError, "projection"):
            replace(screen, similarity_score=0.0)

        result = OcrSimilarityResult()
        nested = replace(screen, similarity_result=result)
        self.assertEqual(nested.similarity_result, result)
        self.assertEqual(
            tuple(item.name for item in dataclass_fields(OcrSimilarityResult))[:6],
            ("similarity_status", "reference_screen_id", "reference_screen_index", "reference_capture_type", "reference_source", "exact_same"),
        )

    def test_r06_old_schemas_restore_without_similarity(self):
        for version in ("1.0.0", "1.1.0", "1.2.0"):
            data = self.make_screen().to_dict()
            data["storage_schema_version"] = version
            if version == "1.0.0":
                for name in ("normalized_text", "comparison_text", "segments"):
                    data.pop(name, None)
            restored = OcrScreenRecord.from_dict(data)
            self.assertIsNone(restored.similarity_result)

    def test_r06_result_rejects_false_zero_and_invalid_warning(self):
        with self.assertRaises(ValueError):
            OcrSimilarityResult(similarity_score=0.0)
        with self.assertRaises(ValueError):
            OcrSimilarityResult(has_effective_new_text=False)
        with self.assertRaises(ValueError):
            OcrSimilarityResult(warning_codes=("private OCR text",))

    def test_r06_result_validates_frozen_accounting_projection(self):
        result = OcrSimilarityResult(
            similarity_status=SimilarityStatus.PARTIAL,
            comparison_class=ComparisonClass.UNCERTAIN,
            overlap_char_count=3, new_char_count=1, uncertain_char_count=0,
            current_effective_char_count=4, overlap_segment_count=1,
            new_segment_count=1, uncertain_segment_count=0,
            current_effective_segment_count=2, overlap_ratio_numerator=3,
            overlap_ratio_denominator=4, overlap_ratio=0.75,
            new_text_ratio_numerator=1, new_text_ratio_denominator=4,
            new_text_ratio=0.25, uncertain_ratio_numerator=0,
            uncertain_ratio_denominator=4, uncertain_ratio=0.0,
        )
        self.assertEqual(result.current_effective_char_count, 4)
        with self.assertRaises(ValueError):
            OcrSimilarityResult(
                similarity_status=SimilarityStatus.PARTIAL,
                overlap_char_count=1, new_char_count=0, uncertain_char_count=0,
                current_effective_char_count=1, overlap_segment_count=1,
                new_segment_count=0, uncertain_segment_count=0,
                current_effective_segment_count=1, overlap_ratio_numerator=1,
                overlap_ratio_denominator=1, overlap_ratio=1.0,
                new_text_ratio_numerator=0, new_text_ratio_denominator=1,
                new_text_ratio=0.0, uncertain_ratio_numerator=0,
                uncertain_ratio_denominator=1, uncertain_ratio=0.1,
            )

    def test_possible_effective_new_requires_zero_confirmed_and_false_boolean(self):
        decision = EffectiveNewDecision(
            "screen:line:0",
            "uncertain",
            EffectiveDecision.UNCERTAIN,
            "source_uncertain",
            ("r05_uncertain",),
        )
        possible = OcrSimilarityResult(
            similarity_status=SimilarityStatus.PARTIAL,
            effective_new_status=EffectiveNewStatus.POSSIBLE,
            effective_new_decisions=(decision,),
            effective_new_segment_count=0,
            ineffective_new_segment_count=0,
            possible_new_segment_count=1,
            effective_new_char_count=0,
            possible_new_char_count=8,
            has_effective_new_text=False,
            comparison_class=ComparisonClass.UNCERTAIN,
        )

        self.assertFalse(possible.has_effective_new_text)
        self.assertEqual(possible.effective_new_segment_count, 0)
        with self.assertRaisesRegex(ValueError, "confirmed segments"):
            replace(possible, has_effective_new_text=True)

    def test_r06_manifest_record_identity_and_required_keys(self):
        normalization_snapshot = canonical_normalization_config(DEFAULT_OCR_NORMALIZATION_CONFIG)
        config = DEFAULT_OCR_SIMILARITY_CONFIG
        similarity_snapshot = canonical_similarity_config(config)
        manifest = RunManifest(
            run_id="run-r06", started_at="2026-07-30T12:00:00+08:00",
            status=RunStatus.RUNNING, platform="Windows", python_version="3.13",
            data_files={}, normalization_version=NORMALIZATION_VERSION,
            normalization_config_version=DEFAULT_OCR_NORMALIZATION_CONFIG.normalization_config_version,
            normalization_config_digest=normalization_config_digest(normalization_snapshot),
            effective_min_confidence=DEFAULT_OCR_NORMALIZATION_CONFIG.effective_min_confidence,
            normalization_config=normalization_snapshot, rule_evaluation_mode="legacy_shadow",
            similarity_mode="record", similarity_version=SIMILARITY_VERSION,
            similarity_config_version=SIMILARITY_CONFIG_VERSION,
            similarity_config_digest=similarity_config_digest(similarity_snapshot),
            similarity_config=similarity_snapshot,
            business_short_terms_version=config.business_short_terms_version,
            business_short_terms_digest=config.business_short_terms_digest(),
        )
        self.assertEqual(RunManifest.from_dict(manifest.to_dict()), manifest)
        missing = manifest.to_dict()
        missing.pop("similarity_mode")
        with self.assertRaisesRegex(ValueError, "R06 run manifest"):
            RunManifest.from_dict(missing)

    def test_r06_summary_recomputes_frozen_count_partitions(self):
        result = OcrSimilarityResult(
            similarity_status=SimilarityStatus.UNAVAILABLE,
            reference_source=ReferenceSource.EXPLICIT_RECORD,
            effective_new_status=EffectiveNewStatus.UNAVAILABLE,
            comparison_class=ComparisonClass.EMPTY_OR_UNAVAILABLE,
            similarity_version="r06-v1", similarity_config_version="r06-config-v1",
            similarity_config_digest="a" * 64,
            warning_codes=("reference_missing",),
        )
        screen = replace(
            self.make_screen(), similarity_result=result,
            similarity_version="r06-v1",
        )
        summary = recompute_similarity_summary((screen,))
        self.assertEqual(summary.screen_count, 1)
        self.assertEqual(summary.unavailable_screen_count, 1)
        self.assertEqual(summary.empty_or_unavailable_screen_count, 1)
        self.assertEqual(summary.effective_unavailable_screen_count, 1)
        self.assertEqual(summary.warning_count, 1)


if __name__ == "__main__":
    unittest.main()
