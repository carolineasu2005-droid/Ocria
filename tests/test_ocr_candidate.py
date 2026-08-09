import gc
import json
import unittest
import weakref
from unittest.mock import patch

import ocr_candidate

from ocr_candidate import (
    CandidateBuilderFinalizedError,
    CandidateOcrBuilder,
)
from ocr_detector import RuleComparisonResult
from ocr_records import (
    CaptureStatus,
    CaptureType,
    DocumentBuildStatus,
    OcrScreenRecord,
)
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_text import OCRItem


class CandidateOcrBuilderTests(unittest.TestCase):
    def make_item(self, suffix="1"):
        return OCRItem(
            "虚构候选人 {0} C++ C# .NET SLG+X 0-1 2D/3D".format(suffix),
            0.91,
            ((1, 2), (20, 2), (20, 10), (1, 10)),
        )

    def make_builder(self, sequence=1):
        return CandidateOcrBuilder(
            "run-test",
            sequence,
            created_at="2026-07-30T12:00:00+08:00",
            metadata={"candidate_in_batch": sequence},
            aggregation_mode="disabled",
            similarity_mode="disabled",
        )

    def add_screen(
        self,
        builder,
        index,
        capture_type=CaptureType.FORMAL_SCREEN,
        formal=True,
    ):
        return builder.build_screen_record(
            [self.make_item(str(index))],
            capture_type=capture_type,
            is_formal_screen=formal,
            screen_index=index if formal else None,
            captured_at="2026-07-30T12:00:{0:02d}+08:00".format(index),
            exact_hash="{0:064x}".format(index),
        )

    def test_empty_candidate_document_is_explicit(self):
        builder = self.make_builder()

        document = builder.finalize(
            CaptureStatus.EMPTY,
            end_reason="no_ocr_observations",
            completed_at="2026-07-30T12:01:00+08:00",
        )

        self.assertEqual(document.screens, ())
        self.assertEqual(document.capture_summary.actual_screen_count, 0)
        self.assertEqual(document.capture_summary.ocr_attempt_count, 0)
        self.assertIsNone(document.document_text)
        self.assertEqual(document.document_segments, ())
        self.assertEqual(document.document_build_status, DocumentBuildStatus.NOT_ATTEMPTED)

    def test_one_screen_candidate_preserves_raw_evidence(self):
        builder = self.make_builder()
        record = self.add_screen(builder, 1)

        document = builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
        )

        self.assertEqual(document.screens, (record,))
        self.assertEqual(document.capture_summary.actual_screen_count, 1)
        self.assertEqual(document.capture_summary.ocr_attempt_count, 1)
        self.assertEqual(document.capture_summary.end_screen_index, 1)
        self.assertEqual(record.raw_boxes[0].original_index, 0)
        self.assertEqual(record.raw_boxes[0].raw_text, self.make_item().text)

    def test_disabled_mode_never_constructs_aggregator(self):
        with patch("ocr_candidate.CandidateDocumentAggregator") as aggregator:
            builder = self.make_builder()
            record = self.add_screen(builder, 1)
            document = builder.finalize(
                CaptureStatus.COMPLETED, end_reason="existing_flow_completed"
            )
        aggregator.assert_not_called()
        self.assertEqual(record.aggregation_status.value, "not_attempted")
        self.assertEqual(document.document_build_status, DocumentBuildStatus.NOT_ATTEMPTED)

    def test_record_mode_with_only_nonformal_observations_stays_not_attempted(self):
        builder = CandidateOcrBuilder(
            "run-test", 1, candidate_record_id="candidate-r05-nonformal",
            created_at="2026-07-30T12:00:00+08:00", aggregation_mode="record",
        )
        record = builder.build_screen_record(
            (self.make_item("r05-nonformal"),),
            capture_type=CaptureType.LOAD_CHECK, is_formal_screen=False,
            screen_index=None, screen_id="screen-r05-nonformal",
            captured_at="2026-07-30T12:00:01+08:00",
        )
        document = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
        )

        self.assertEqual(record.aggregation_status.value, "not_attempted")
        self.assertEqual(document.document_build_status, DocumentBuildStatus.NOT_ATTEMPTED)
        self.assertIsNone(document.versions["aggregation"])
        self.assertIsNone(document.aggregation_config_digest)

    def test_explicit_record_mode_projects_screen_before_document_finalize(self):
        screen_id = "screen-r05"
        item = self.make_item("r05")
        normalization = normalize_ocr_text((NormalizationBox(
            "{0}:box:0".format(screen_id), item.text, item.box, 0, item.confidence,
        ),))
        builder = CandidateOcrBuilder(
            "run-test", 1, candidate_record_id="candidate-r05",
            created_at="2026-07-30T12:00:00+08:00", aggregation_mode="record",
        )
        record = builder.build_screen_record(
            (item,), capture_type=CaptureType.FORMAL_SCREEN, is_formal_screen=True,
            screen_index=1, screen_id=screen_id,
            captured_at="2026-07-30T12:00:01+08:00", normalization=normalization,
            ocr_min_confidence=0.85,
        )
        document = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed"
        )
        self.assertEqual(record.aggregation_status.value, "completed")
        self.assertEqual(record.new_segment_ids, ("screen-r05:line:0",))
        self.assertEqual(document.document_build_status, DocumentBuildStatus.COMPLETED)
        self.assertEqual(document.versions["aggregation"], "r05-v1")
        self.assertEqual(document.document_text, item.text)

    def test_r05_validation_failure_does_not_half_commit_builder_state(self):
        builder = CandidateOcrBuilder(
            "run-test", 1, candidate_record_id="candidate-r05-atomic",
            aggregation_mode="record", similarity_mode="disabled",
        )

        def build(screen_id, screen_index, text):
            item = OCRItem(
                text, 0.96, ((0, 0), (180, 0), (180, 20), (0, 20)),
            )
            normalization = normalize_ocr_text((NormalizationBox(
                "{0}:box:0".format(screen_id), item.text, item.box, 0,
                item.confidence,
            ),))
            return builder.build_screen_record(
                (item,), capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True, screen_index=screen_index,
                screen_id=screen_id, normalization=normalization,
                ocr_min_confidence=0.85,
            )

        real_projection = ocr_candidate.aggregation_screen_record_fields

        def invalid_projection(record, result, config):
            fields = real_projection(record, result, config)
            if record.screen_id == "r05-failed":
                fields["new_segment_ids"] = ()
            return fields

        seed = build("r05-seed", 1, "第一屏已提交的合成内容")

        with patch(
            "ocr_candidate.aggregation_screen_record_fields",
            side_effect=invalid_projection,
        ):
            with self.assertRaisesRegex(
                ValueError, "aggregation segment classifications",
            ):
                build("r05-failed", 2, "仅用于触发合法的测试校验失败")

        self.assertEqual(builder.retained_screen_count, 1)
        valid = build("r05-valid", 2, "随后成功保存的第二屏合成内容")
        self.assertEqual(valid.attempt_index, 1)
        self.assertEqual(valid.aggregation_status.value, "completed")

        document = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
        )
        self.assertEqual(document.screens, (seed, valid))
        self.assertEqual(document.capture_summary.actual_screen_count, 2)
        self.assertNotIn(
            "r05-failed",
            tuple(
                occurrence.source_screen_id
                for segment in document.document_segments
                for occurrence in segment.source_occurrences
            ),
        )

    def test_r06_projection_failure_does_not_half_commit_context(self):
        builder = CandidateOcrBuilder(
            "run-test", 1, candidate_record_id="candidate-r06-atomic",
            aggregation_mode="record", similarity_mode="record",
        )

        def build(screen_id, screen_index):
            item = OCRItem(
                "合成 R06 原子性内容", 0.96,
                ((0, 0), (180, 0), (180, 20), (0, 20)),
            )
            normalization = normalize_ocr_text((NormalizationBox(
                "{0}:box:0".format(screen_id), item.text, item.box, 0,
                item.confidence,
            ),))
            return builder.build_screen_record(
                (item,), capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True, screen_index=screen_index,
                screen_id=screen_id, normalization=normalization,
                ocr_min_confidence=0.85,
            )

        real_apply = CandidateOcrBuilder._apply_similarity

        def fail_after_evaluation(self, record, **kwargs):
            projected = real_apply(self, record, **kwargs)
            if record.screen_id == "r06-failed":
                raise ValueError("synthetic post-R06 validation failure")
            return projected

        seed = build("r06-seed", 1)

        with patch.object(
            CandidateOcrBuilder, "_apply_similarity",
            new=fail_after_evaluation,
        ):
            with self.assertRaisesRegex(ValueError, "post-R06"):
                build("r06-failed", 2)

        self.assertEqual(builder.retained_screen_count, 1)
        valid = build("r06-valid", 2)
        self.assertEqual(valid.attempt_index, 1)
        self.assertEqual(valid.similarity_result.similarity_status.value, "partial")
        self.assertEqual(valid.similarity_result.reference_screen_id, seed.screen_id)
        self.assertEqual(len(builder._similarity_evaluator._formal), 2)
        self.assertNotIn(
            "r06-failed",
            tuple(screen.screen_id for screen in builder._similarity_evaluator._formal),
        )

        document = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
        )
        self.assertEqual(document.screens, (seed, valid))
        self.assertEqual(document.similarity_summary.screen_count, 2)

    def test_deferred_screen_state_commits_only_after_store_success(self):
        builder = CandidateOcrBuilder(
            "run-test", 1, candidate_record_id="candidate-store-atomic",
            aggregation_mode="record", similarity_mode="record",
        )
        item = self.make_item("pending")
        screen_id = "screen-pending"
        normalization = normalize_ocr_text((NormalizationBox(
            "{0}:box:0".format(screen_id), item.text, item.box, 0,
            item.confidence,
        ),))
        pending = builder.build_screen_record(
            (item,), capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True, screen_index=1, screen_id=screen_id,
            normalization=normalization, ocr_min_confidence=0.85,
            defer_commit=True,
        )

        self.assertEqual(builder.retained_screen_count, 0)
        self.assertTrue(builder.discard_screen_record(pending))
        self.assertEqual(builder.retained_screen_count, 0)

        committed = builder.build_screen_record(
            (item,), capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True, screen_index=1,
            screen_id="screen-committed", normalization=normalize_ocr_text((
                NormalizationBox(
                    "screen-committed:box:0", item.text, item.box, 0,
                    item.confidence,
                ),
            )), ocr_min_confidence=0.85, defer_commit=True,
        )
        builder.commit_screen_record(committed)

        self.assertEqual(committed.attempt_index, 1)
        self.assertEqual(builder.retained_screen_count, 1)

    def test_screen_record_flattens_legacy_shadow_result(self):
        builder = self.make_builder()
        screen_id = "screen-shadow"
        item = self.make_item()
        normalization = normalize_ocr_text((NormalizationBox(
            "{0}:box:0".format(screen_id),
            item.text,
            item.box,
            0,
            item.confidence,
        ),))
        comparison = RuleComparisonResult(
            rule_evaluation_mode="legacy_shadow",
            legacy_match=False,
            r04_match=True,
            comparison_outcome="r04_only",
            legacy_rule_index=None,
            r04_rule_index=1,
        )

        record = builder.build_screen_record(
            [item],
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            screen_index=1,
            captured_at="2026-07-30T12:00:01+08:00",
            screen_id=screen_id,
            normalization=normalization,
            ocr_min_confidence=0.85,
            rule_comparison=comparison,
        )

        self.assertEqual(record.rule_evaluation_mode, "legacy_shadow")
        self.assertFalse(record.legacy_match)
        self.assertTrue(record.r04_match)
        self.assertEqual(record.comparison_outcome, "r04_only")
        self.assertIsNone(record.legacy_rule_index)
        self.assertEqual(record.r04_rule_index, 1)

    def test_r04_result_projects_into_existing_screen_and_candidate_models(self):
        builder = self.make_builder()
        screen_id = "screen-r04"
        items = (
            OCRItem(
                "Unity  2022.3 C++",
                0.91,
                ((0, 0), (100, 0), (100, 20), (0, 20)),
            ),
            OCRItem(
                "Unity  2022.3 C++",
                0.99,
                ((1, 0), (101, 0), (101, 20), (1, 20)),
            ),
        )
        normalization = normalize_ocr_text(tuple(
            NormalizationBox(
                "{0}:box:{1}".format(screen_id, index),
                item.text,
                item.box,
                index,
                item.confidence,
            )
            for index, item in enumerate(items)
        ))

        record = builder.build_screen_record(
            items,
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            screen_index=1,
            captured_at="2026-07-30T12:00:01+08:00",
            screen_id=screen_id,
            normalization=normalization,
            ocr_min_confidence=0.85,
        )
        document = builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
        )

        self.assertEqual(record.raw_text, "\n".join(item.text for item in items))
        self.assertEqual(record.raw_text_length, len(record.raw_text))
        self.assertEqual(record.normalized_text, normalization.normalized_text)
        self.assertEqual(record.comparison_text, normalization.comparison_text)
        self.assertEqual(record.ordered_box_ids, normalization.ordered_box_ids)
        self.assertEqual(record.effective_box_ids, normalization.effective_box_ids)
        self.assertEqual(
            record.suppressed_duplicate_box_ids,
            normalization.suppressed_duplicate_box_ids,
        )
        self.assertEqual(len(record.duplicate_groups), 1)
        self.assertEqual(record.segments[0].segment_id, "screen-r04:line:0")
        self.assertEqual(record.ocr_min_confidence, 0.85)
        self.assertEqual(
            document.versions["normalization"],
            normalization.normalization_version,
        )
        self.assertEqual(document.screens, (record,))
        self.assertIsNone(document.document_text)
        self.assertEqual(
            OcrScreenRecord.from_dict(json.loads(record.to_json())),
            record,
        )

    def test_invalid_mixed_bbox_keeps_raw_box_and_text_in_record(self):
        builder = self.make_builder()
        screen_id = "screen-invalid-bbox"
        item = OCRItem("仍需保留的文字", 0.95, (0, (1, 2), 3, 4))
        normalization = normalize_ocr_text((NormalizationBox(
            "{0}:box:0".format(screen_id),
            item.text,
            item.box,
            0,
            item.confidence,
        ),))

        record = builder.build_screen_record(
            (item,),
            capture_type=CaptureType.LOAD_CHECK,
            is_formal_screen=False,
            screen_index=None,
            captured_at="2026-07-30T12:00:01+08:00",
            screen_id=screen_id,
            normalization=normalization,
            ocr_min_confidence=0.85,
        )
        restored = OcrScreenRecord.from_dict(json.loads(record.to_json()))

        self.assertEqual(restored.raw_boxes[0].raw_text, item.text)
        self.assertEqual(restored.raw_boxes[0].bbox, item.box)
        self.assertEqual(restored.normalization_status.value, "failed")
        self.assertIsNone(restored.normalized_text)
        self.assertIsNone(restored.comparison_text)
        self.assertEqual(restored.raw_text, item.text)

    def test_candidate_normalization_summary_is_recomputed_by_formality_and_state(self):
        builder = self.make_builder()
        completed_id = "summary-completed"
        completed_item = self.make_item("completed")
        completed = normalize_ocr_text((NormalizationBox(
            "{0}:box:0".format(completed_id),
            completed_item.text,
            completed_item.box,
            0,
            completed_item.confidence,
        ),))
        builder.build_screen_record(
            (completed_item,),
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            screen_index=1,
            screen_id=completed_id,
            normalization=completed,
            ocr_min_confidence=0.85,
        )
        failed_id = "summary-failed"
        failed_item = OCRItem("虚构失败框", 0.95, (0, (1, 2), 3, 4))
        failed = normalize_ocr_text((NormalizationBox(
            "{0}:box:0".format(failed_id),
            failed_item.text,
            failed_item.box,
            0,
            failed_item.confidence,
        ),))
        builder.build_screen_record(
            (failed_item,),
            capture_type=CaptureType.LOAD_CHECK,
            is_formal_screen=False,
            screen_index=None,
            screen_id=failed_id,
            normalization=failed,
            ocr_min_confidence=0.85,
        )
        self.add_screen(builder, 2)
        self.add_screen(builder, 3, CaptureType.LOAD_RETRY, formal=False)

        document = builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
        )
        summary = document.normalization_summary

        self.assertEqual(summary.formal_normalization_completed_count, 1)
        self.assertEqual(summary.formal_normalization_failed_count, 0)
        self.assertEqual(summary.formal_normalization_not_attempted_count, 1)
        self.assertEqual(summary.nonformal_normalization_completed_count, 0)
        self.assertEqual(summary.nonformal_normalization_failed_count, 1)
        self.assertEqual(summary.nonformal_normalization_not_attempted_count, 1)
        self.assertEqual(document.versions["normalization"], "r04-v1")

        serialized = document.to_dict()
        serialized["normalization_summary"][
            "formal_normalization_completed_count"
        ] += 1
        with self.assertRaisesRegex(ValueError, "summary"):
            type(document).from_dict(serialized)

    def test_eight_formal_screens_report_completed_with_limit(self):
        builder = self.make_builder()
        for index in range(1, 9):
            self.add_screen(builder, index)

        document = builder.finalize(
            CaptureStatus.COMPLETED_WITH_LIMIT,
            end_reason="max_screen_limit",
        )

        summary = document.capture_summary
        self.assertEqual(summary.actual_screen_count, 8)
        self.assertEqual(summary.ocr_attempt_count, 8)
        self.assertEqual(summary.scroll_attempt_count, 7)
        self.assertEqual(summary.end_screen_index, 8)

    def test_nonformal_retries_count_attempts_without_fake_formal_screens(self):
        builder = self.make_builder()
        initial = self.add_screen(
            builder, 1, CaptureType.LOAD_CHECK, formal=False
        )
        retry_one = self.add_screen(
            builder, 1, CaptureType.LOAD_RETRY, formal=False
        )
        retry_two = self.add_screen(
            builder, 1, CaptureType.LOAD_RETRY, formal=False
        )
        self.add_screen(builder, 1)

        document = builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
        )

        self.assertEqual(
            (initial.attempt_index, retry_one.attempt_index, retry_two.attempt_index),
            (1, 2, 3),
        )
        self.assertIsNone(initial.screen_index)
        self.assertIsNone(initial.raw_boxes[0].screen_index)
        self.assertEqual(document.capture_summary.actual_screen_count, 1)
        self.assertEqual(document.capture_summary.ocr_attempt_count, 4)

    def test_abort_and_interrupt_use_only_abort_reason(self):
        abnormal = self.make_builder(1).finalize(
            CaptureStatus.ABORTED,
            end_reason=None,
            abort_reason="RuntimeError",
        )
        interrupted = self.make_builder(2).finalize(
            CaptureStatus.INTERRUPTED,
            end_reason=None,
            abort_reason="user_interrupted",
        )

        self.assertEqual(abnormal.capture_summary.abort_reason, "RuntimeError")
        self.assertEqual(
            interrupted.capture_summary.abort_reason,
            "user_interrupted",
        )
        self.assertIsNone(abnormal.capture_summary.end_reason)
        self.assertIsNone(interrupted.capture_summary.end_reason)

    def test_finalize_rejects_conflicting_or_misclassified_reasons(self):
        cases = (
            (
                CaptureStatus.COMPLETED,
                "existing_flow_completed",
                "unexpected_abort",
            ),
            (CaptureStatus.ABORTED, "exception", "RuntimeError"),
            (CaptureStatus.INTERRUPTED, None, None),
            (
                CaptureStatus.COMPLETED_WITH_LIMIT,
                "wrong_limit_reason",
                None,
            ),
        )
        for sequence, (status, end_reason, abort_reason) in enumerate(
            cases,
            start=1,
        ):
            with self.subTest(status=status, end_reason=end_reason):
                with self.assertRaises(ValueError):
                    self.make_builder(sequence).finalize(
                        status,
                        end_reason=end_reason,
                        abort_reason=abort_reason,
                    )

    def test_duplicate_finalize_is_controlled_and_rejected(self):
        builder = self.make_builder()
        builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
        )

        with self.assertRaises(CandidateBuilderFinalizedError):
            builder.finalize(
                CaptureStatus.COMPLETED,
                end_reason="existing_flow_completed",
            )

    def test_candidate_ids_are_unique_and_sequence_is_preserved(self):
        first = self.make_builder(1)
        second = self.make_builder(2)

        self.assertNotEqual(first.candidate_record_id, second.candidate_record_id)
        self.assertEqual(first.sequence_number, 1)
        self.assertEqual(second.sequence_number, 2)

    def test_finalize_releases_builder_screen_references(self):
        builder = self.make_builder()
        record = self.add_screen(builder, 1)
        reference = weakref.ref(record)
        document = builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
        )
        self.assertEqual(builder.retained_screen_count, 0)

        del record
        del document
        gc.collect()

        self.assertIsNone(reference())

    def test_finalize_releases_candidate_context_when_document_construction_fails(self):
        builder = CandidateOcrBuilder(
            "run-test", 1, candidate_record_id="finalize-construction-failure",
            aggregation_mode="record", similarity_mode="record",
        )
        self.add_screen(builder, 1)

        with (
            patch("ocr_candidate.CandidateOcrDocument", side_effect=RuntimeError("synthetic")),
            self.assertRaisesRegex(RuntimeError, "synthetic"),
        ):
            builder.finalize(
                CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            )

        self.assertTrue(builder.finalized)
        self.assertEqual(builder.retained_screen_count, 0)
        self.assertIsNone(builder._aggregator)
        self.assertIsNone(builder._similarity_evaluator)

    def test_invalid_naive_timestamps_and_post_finalize_add_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            CandidateOcrBuilder(
                "run-test", 1, created_at="2026-07-30T12:00:00"
            )

        builder = self.make_builder()
        builder.finalize(CaptureStatus.EMPTY, end_reason="no_ocr")
        with self.assertRaises(CandidateBuilderFinalizedError):
            self.add_screen(builder, 1)


if __name__ == "__main__":
    unittest.main()
