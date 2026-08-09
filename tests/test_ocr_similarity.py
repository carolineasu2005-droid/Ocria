import os
import subprocess
import sys
import unittest
import gc
import weakref
from dataclasses import replace
from unittest.mock import patch

from ocr_aggregation import (
    CandidateDocumentAggregator,
    ScreenAggregationResult,
    aggregation_screen_record_fields,
)
from ocr_candidate import CandidateOcrBuilder
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_records import (
    AggregationStatus, CaptureStatus, CaptureType, ComparisonClass, EffectiveNewStatus, OcrScreenRecord,
    OcrSimilarityResult,
    ReferenceResolutionStatus, ReferenceSource, SimilarityStatus,
    recompute_similarity_summary,
)
from ocr_similarity import (
    DEFAULT_OCR_SIMILARITY_CONFIG, OcrSimilarityConfig, canonical_similarity_config,
    apply_r05_accounting, compute_r05_accounting,
    CandidateSimilarityEvaluator, apply_effective_new, evaluate_effective_new,
    compare_r03_exact_hash, compute_char_ngram_similarity,
    compute_pair_similarity_signals, compute_simhash_similarity, compute_stable_simhash,
    resolve_reference, similarity_config_digest, similarity_config_from_snapshot,
)
from ocr_text import OCRItem


def make_screen(identifier, index, *, capture_type=CaptureType.FORMAL_SCREEN, formal=True, run_id="run", candidate_id="candidate", attempt=1):
    return OcrScreenRecord(
        run_id=run_id, candidate_record_id=candidate_id, screen_id=identifier,
        screen_index=index, attempt_index=attempt, capture_type=capture_type,
        is_formal_screen=formal, captured_at="2026-08-01T12:00:00+08:00",
        raw_boxes=(), raw_text="",
    )


def make_r04_screen(identifier, index, texts):
    items = tuple(
        OCRItem(text, 0.99, ((0, order * 30), (200, order * 30), (200, order * 30 + 20), (0, order * 30 + 20)))
        for order, text in enumerate(texts)
    )
    boxes = tuple(
        NormalizationBox("{0}:box:{1}".format(identifier, order), item.text, item.box, order, item.confidence)
        for order, item in enumerate(items)
    )
    return CandidateOcrBuilder(
        "run", index, candidate_record_id="candidate",
        aggregation_mode="disabled", similarity_mode="disabled",
    ).build_screen_record(
        items, capture_type=CaptureType.FORMAL_SCREEN, is_formal_screen=True,
        screen_index=index, screen_id=identifier, normalization=normalize_ocr_text(boxes),
        ocr_min_confidence=0.85,
    )


def with_r05_fields(record, result):
    return replace(record, **aggregation_screen_record_fields(record, result))


class SimilarityConfigTests(unittest.TestCase):
    def test_snapshot_round_trip_and_digest_are_stable(self):
        config = DEFAULT_OCR_SIMILARITY_CONFIG
        snapshot = canonical_similarity_config(config)
        self.assertEqual(similarity_config_from_snapshot(snapshot), config)
        self.assertRegex(similarity_config_digest(snapshot), r"^[0-9a-f]{64}$")
        code = (
            "from ocr_similarity import DEFAULT_OCR_SIMILARITY_CONFIG, similarity_config_digest; "
            "print(similarity_config_digest(DEFAULT_OCR_SIMILARITY_CONFIG))"
        )
        environment = dict(os.environ, PYTHONHASHSEED="7")
        output = subprocess.check_output([sys.executable, "-c", code], text=True, env=environment).strip()
        self.assertEqual(output, similarity_config_digest(config))
        self.assertNotEqual(
            similarity_config_digest(config),
            similarity_config_digest(OcrSimilarityConfig(high_similarity_threshold=0.84)),
        )

    def test_config_rejects_invalid_frozen_parameters(self):
        cases = (
            {"ngram_sizes": ()}, {"ngram_sizes": (2, 2), "ngram_weights": (0.5, 0.5)},
            {"ngram_weights": (0.0, 0.0, 0.0)}, {"simhash_bit_count": 32},
            {"high_similarity_threshold": float("nan")}, {"business_short_terms": ()},
            {"ngram_sizes": [2, 3, 4]}, {"max_formal_screens": 9},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    OcrSimilarityConfig(**changes)


class ReferenceResolverTests(unittest.TestCase):
    def test_formal_index_resolution_never_uses_order(self):
        first = make_screen("one", 1)
        current = make_screen("two", 2)
        resolution = resolve_reference(current, {"one": first}, {1: "one"}, explicit_reference_screen_id=None, source_schema_version="1.3.0")
        self.assertEqual(resolution.status, ReferenceResolutionStatus.RESOLVED)
        self.assertEqual(resolution.reference_screen_id, "one")
        self.assertEqual(resolution.reference_source, ReferenceSource.FORMAL_PREVIOUS_INDEX)

    def test_first_formal_and_missing_previous_are_distinct(self):
        first = make_screen("one", 1)
        no_reference = resolve_reference(first, {}, {}, explicit_reference_screen_id=None, source_schema_version="1.3.0")
        missing = resolve_reference(make_screen("three", 3), {}, {}, explicit_reference_screen_id=None, source_schema_version="1.3.0")
        self.assertEqual(no_reference.status, ReferenceResolutionStatus.NO_REFERENCE)
        self.assertEqual(missing.status, ReferenceResolutionStatus.UNAVAILABLE)
        self.assertEqual(missing.warning_codes, ("reference_missing",))

    def test_nonformal_needs_explicit_legal_reference_and_legacy_is_unavailable(self):
        formal = make_screen("formal", 1)
        current = make_screen("confirmation", 1, capture_type=CaptureType.SCROLL_CONFIRMATION, formal=False)
        resolved = resolve_reference(current, {"formal": formal}, {1: "formal"}, explicit_reference_screen_id="formal", source_schema_version="1.3.0")
        legacy = resolve_reference(current, {"formal": formal}, {1: "formal"}, explicit_reference_screen_id=None, source_schema_version="1.2.0")
        self.assertEqual(resolved.status, ReferenceResolutionStatus.RESOLVED)
        self.assertEqual(resolved.reference_source, ReferenceSource.EXPLICIT_RECORD)
        self.assertEqual(legacy.warning_codes, ("legacy_reference_unavailable",))

    def test_r03_adapter_only_compares_persisted_valid_hashes(self):
        left = make_screen("left", 1)
        right = make_screen("right", 2)
        left = left.__class__(**{**left.__dict__, "exact_hash": "a" * 64, "fingerprint_version": "r03-v1"})
        right = right.__class__(**{**right.__dict__, "exact_hash": "a" * 64, "fingerprint_version": "r03-v1"})
        self.assertEqual(compare_r03_exact_hash(left, right), (True, ()))
        bad = right.__class__(**{**right.__dict__, "fingerprint_version": "r03-v2"})
        self.assertEqual(compare_r03_exact_hash(left, bad), (None, ("fingerprint_version_mismatch",)))


class NgramAndSimHashTests(unittest.TestCase):
    def test_multiset_dice_retains_occurrences_and_renormalizes_weights(self):
        score, scores, warnings = compute_char_ngram_similarity("aaaa", "aa")
        by_n = {item.n: item for item in scores}
        self.assertEqual(warnings, ())
        self.assertEqual(by_n[2].left_feature_count, 3)
        self.assertEqual(by_n[2].right_feature_count, 1)
        self.assertEqual(by_n[2].dice_score, 0.5)
        self.assertEqual(score, 0.2 * 0.5)

    def test_text_matrix_and_empty_short_semantics(self):
        pairs = (
            ("普通文本C++", "普通文本C++", 1.0), ("abcdef", "abcxef", None),
            ("前缀新增内容", "内容", None), ("内容后缀新增", "内容", None),
            ("甲乙新增丙丁", "甲乙丙丁", None), ("完全不同甲", "完全不同乙", None),
            ("中文 English SLG+X 0-1 2D/3D 😀", "中文 English SLG+X 0-1 2D/3D 😀", 1.0),
            ("e\u0301", "é", None), ("", "", 1.0), ("", "x", 0.0),
            ("x", "x", 1.0), ("x", "y", 0.0), ("ab", "ab", 1.0),
        )
        for left, right, expected in pairs:
            with self.subTest(left=left, right=right):
                score, _, warnings = compute_char_ngram_similarity(left, right)
                self.assertEqual(warnings, ())
                self.assertTrue(0.0 <= score <= 1.0)
                if expected is not None:
                    self.assertEqual(score, expected)

    def test_length_rejection_never_constructs_ngrams(self):
        too_long = "甲" * 100001
        with patch("ocr_similarity._build_ngram_counter") as counter:
            score, scores, warnings = compute_char_ngram_similarity(too_long, "短")
        self.assertIsNone(score)
        self.assertEqual(scores, ())
        self.assertEqual(warnings, ("comparison_text_too_long",))
        counter.assert_not_called()
        self.assertEqual(compute_char_ngram_similarity("甲" * 100000, "甲" * 100000)[0], 1.0)

    def test_simhash_hamming_golden_and_empty_contract(self):
        self.assertIsNone(compute_stable_simhash(""))
        left_hash, right_hash, distance, score = compute_simhash_similarity("C++ SLG+X", "C++ SLG+X")
        self.assertRegex(left_hash, r"^[0-9a-f]{16}$")
        self.assertEqual(left_hash, right_hash)
        self.assertEqual((distance, score), (0, 1.0))
        self.assertEqual(compute_simhash_similarity("", "x")[2:], (None, None))
        self.assertEqual(compute_stable_simhash("C++"), "09a2fb5099b81c5a")
        self.assertEqual(compute_simhash_similarity("abc", "abd")[2:], (28, 0.5625))

    def test_cross_process_simhash_is_seed_independent(self):
        code = (
            "from ocr_similarity import compute_stable_simhash; "
            "print('|'.join(str(compute_stable_simhash(value)) for value in "
            "('x','C+','中文 C++ C# .NET SLG+X 0-1 2D/3D 😀😀','aaaaaa')))"
        )
        outputs = []
        for seed in (None, "1", "777"):
            environment = dict(os.environ)
            if seed is not None:
                environment["PYTHONHASHSEED"] = seed
            outputs.append(subprocess.check_output([sys.executable, "-c", code], text=True, env=environment).strip())
        self.assertEqual(outputs, [outputs[0]] * len(outputs))

    def test_pair_signals_uses_r03_adapter_without_final_classification(self):
        left = make_screen("left", 1)
        right = make_screen("right", 2)
        left = left.__class__(**{**left.__dict__, "exact_hash": "a" * 64, "fingerprint_version": "r03-v1"})
        right = right.__class__(**{**right.__dict__, "exact_hash": "a" * 64, "fingerprint_version": "r03-v1"})
        signals = compute_pair_similarity_signals(left, right)
        self.assertTrue(signals.exact_same)
        self.assertIsNone(signals.similarity_score)
        self.assertEqual(signals.warning_codes, ("r04_not_completed",))


class R05AccountingTests(unittest.TestCase):
    def _mixed_screen(self):
        aggregator = CandidateDocumentAggregator("run", "candidate")
        current = make_r04_screen("one", 1, ("前序内容" * 8, "新增 C++ 内容 😀" * 8))
        current = with_r05_fields(current, aggregator.add_screen(current))
        first, second = current.segments
        first_chars, second_chars = len(first.comparison_text), len(second.comparison_text)
        # This is a synthetic persisted R05 mixed partition.  Accounting reads
        # only these IDs/projections and intentionally does not inspect evidence.
        object.__setattr__(current, "matched_segment_ids", (first.segment_id,))
        object.__setattr__(current, "new_segment_ids", (second.segment_id,))
        object.__setattr__(current, "uncertain_segment_ids", ())
        object.__setattr__(current, "overlap_char_count", first_chars)
        object.__setattr__(current, "new_text_char_count", second_chars)
        object.__setattr__(current, "uncertain_char_count", 0)
        object.__setattr__(current, "overlap_segment_count", 1)
        object.__setattr__(current, "new_segment_count", 1)
        object.__setattr__(current, "certain_new_segment_count", 1)
        object.__setattr__(current, "uncertain_segment_count", 0)
        return current

    def test_recomputes_r05_partition_counts_and_ratios_without_mutation(self):
        current = self._mixed_screen()
        before = current.to_dict()
        accounting = compute_r05_accounting(current)
        self.assertTrue(accounting.is_verifiable)
        self.assertEqual(current.aggregation_status, AggregationStatus.COMPLETED)
        self.assertEqual(accounting.overlap_segment_count + accounting.new_segment_count + accounting.uncertain_segment_count, len(current.segments))
        self.assertEqual(accounting.overlap_char_count + accounting.new_char_count + accounting.uncertain_char_count, accounting.current_effective_char_count)
        self.assertEqual(accounting.new_char_count + accounting.uncertain_char_count, current.new_text_char_count)
        self.assertAlmostEqual(accounting.overlap_ratio + accounting.new_text_ratio + accounting.uncertain_ratio, 1.0, places=12)
        self.assertEqual(current.to_dict(), before)
        self.assertEqual(
            apply_r05_accounting(OcrSimilarityResult(), accounting).similarity_status,
            SimilarityStatus.PARTIAL,
        )

    def test_zero_denominator_preserves_actual_segment_counts_and_sets_empty_class(self):
        current = make_r04_screen("empty", 1, ())
        aggregator = CandidateDocumentAggregator("run", "candidate")
        current = with_r05_fields(current, aggregator.add_screen(current))
        accounting = compute_r05_accounting(current)
        self.assertTrue(accounting.is_verifiable)
        self.assertEqual(accounting.current_effective_char_count, 0)
        self.assertEqual(accounting.current_effective_segment_count, 0)
        self.assertEqual(accounting.overlap_ratio_denominator, 0)
        self.assertIsNone(accounting.overlap_ratio)
        result = apply_r05_accounting(
            OcrSimilarityResult(similarity_status=SimilarityStatus.COMPLETED), accounting,
        )
        self.assertEqual(result.comparison_class, ComparisonClass.EMPTY_OR_UNAVAILABLE)
        self.assertIn("zero_effective_char_denominator", result.warning_codes)

    def test_invalid_projection_or_partition_fails_open_and_preserves_algorithm_signals(self):
        current = self._mixed_screen()
        object.__setattr__(current, "new_text_char_count", current.new_text_char_count + 1)
        accounting = compute_r05_accounting(current)
        self.assertFalse(accounting.is_verifiable)
        self.assertEqual(accounting.warning_codes, ("r05_projection_mismatch",))
        result = apply_r05_accounting(
            OcrSimilarityResult(similarity_status=SimilarityStatus.COMPLETED, similarity_score=0.75), accounting,
        )
        self.assertEqual(result.similarity_status, SimilarityStatus.PARTIAL)
        self.assertEqual(result.comparison_class, ComparisonClass.UNCERTAIN)
        self.assertEqual(result.similarity_score, 0.75)
        self.assertIsNone(result.overlap_char_count)
        self.assertEqual(result.effective_new_status, EffectiveNewStatus.UNAVAILABLE)

    def test_not_attempted_failed_partial_and_partition_corruption_are_conservative(self):
        raw = make_r04_screen("raw", 1, ("Unicode 😀",))
        self.assertEqual(compute_r05_accounting(raw).warning_codes, ("r05_not_attempted",))
        aggregator = CandidateDocumentAggregator("run", "candidate")
        partial = with_r05_fields(raw, aggregator.add_screen(raw, force_uncertain_warning="formal_screen_out_of_order"))
        self.assertEqual(compute_r05_accounting(partial).warning_codes, ("r05_partial",))
        object.__setattr__(partial, "matched_segment_ids", ("unknown",))
        invalid = compute_r05_accounting(partial)
        self.assertFalse(invalid.is_verifiable)
        self.assertEqual(invalid.warning_codes, ("r05_partial", "segment_partition_invalid"))
        failed = with_r05_fields(raw, aggregator.add_screen(raw))
        object.__setattr__(failed, "aggregation_status", AggregationStatus.FAILED)
        self.assertEqual(compute_r05_accounting(failed).warning_codes, ("r05_failed",))

    def test_interleaved_r05_classification_buckets_are_a_valid_partition(self):
        """Production replay: bucket order is local, not a global screen order."""

        current = make_r04_screen(
            "interleaved", 2,
            ("待确认开头", "已确认新增内容", "待确认结尾"),
        )
        segment_ids = tuple(segment.segment_id for segment in current.segments)
        result = ScreenAggregationResult(
            current.screen_id,
            current.screen_index,
            AggregationStatus.PARTIAL,
            ("historical_context_insufficient",),
            (),
            (),
            matched_segment_ids=(),
            new_segment_ids=(segment_ids[1],),
            uncertain_segment_ids=(segment_ids[0], segment_ids[2]),
        )

        projected = with_r05_fields(current, result)
        accounting = compute_r05_accounting(projected)

        self.assertTrue(accounting.is_verifiable)
        self.assertEqual(accounting.new_segment_count, 1)
        self.assertEqual(accounting.uncertain_segment_count, 2)


class EffectiveNewTests(unittest.TestCase):
    def test_new_decisions_are_ordered_conservative_and_never_emit_split_merge(self):
        aggregator = CandidateDocumentAggregator("run", "candidate")
        current = make_r04_screen("effective", 1, ("C++", "!!!"))
        current = with_r05_fields(current, aggregator.add_screen(current))
        context = CandidateSimilarityEvaluator("run", "candidate")
        context.add_screen(current)
        outcome = evaluate_effective_new(current, context)
        self.assertEqual(tuple(item.segment_id for item in outcome.decisions), tuple(item.segment_id for item in current.segments))
        self.assertIn("short_text_protected", tuple(item.reason_code for item in outcome.decisions))
        self.assertNotIn("split_merge_artifact", tuple(item.reason_code for item in outcome.decisions))

    def test_uncertain_and_illegal_evidence_are_fail_open(self):
        aggregator = CandidateDocumentAggregator("run", "candidate")
        current = make_r04_screen("uncertain", 1, ("文本",))
        current = with_r05_fields(current, aggregator.add_screen(current, force_uncertain_warning="formal_screen_out_of_order"))
        context = CandidateSimilarityEvaluator("run", "candidate")
        outcome = evaluate_effective_new(current, context)
        self.assertEqual(outcome.status, EffectiveNewStatus.POSSIBLE)
        self.assertEqual(outcome.decisions[0].reason_code, "source_uncertain")
        self.assertEqual(outcome.effective_segment_count, 0)
        self.assertEqual(outcome.possible_segment_count, 1)
        self.assertFalse(outcome.has_effective_new_text)


class OnlineR06IntegrationTests(unittest.TestCase):
    def _normalization(self, screen_id, text):
        item = OCRItem(text, 0.95, ((0, 0), (160, 0), (160, 20), (0, 20)))
        result = normalize_ocr_text((NormalizationBox(
            "{0}:box:0".format(screen_id), item.text, item.box, 0, item.confidence,
        ),))
        return item, result

    def test_disabled_short_circuits_before_context_construction(self):
        with patch("ocr_candidate.CandidateSimilarityEvaluator") as evaluator:
            builder = CandidateOcrBuilder(
                "run", 1, candidate_record_id="disabled", similarity_mode="disabled",
            )
            record = builder.build_screen_record(
                (), capture_type=CaptureType.FORMAL_SCREEN, is_formal_screen=True,
                screen_index=1, screen_id="disabled-screen",
            )
            document = builder.finalize(
                CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            )
        evaluator.assert_not_called()
        self.assertIsNone(record.similarity_result)
        self.assertIsNone(document.similarity_summary)

    def test_record_mode_evaluates_once_after_r05_and_summarizes_saved_results(self):
        builder = CandidateOcrBuilder(
            "run", 1, candidate_record_id="record", aggregation_mode="record",
            similarity_mode="record", created_at="2026-08-01T12:00:00+08:00",
        )
        original_evaluate = CandidateSimilarityEvaluator.evaluate
        with patch.object(
            CandidateSimilarityEvaluator,
            "evaluate",
            side_effect=lambda *args, **kwargs: original_evaluate(
                builder._similarity_evaluator, *args, **kwargs
            ),
        ) as evaluate:
            first_item, first_norm = self._normalization("r06-1", "历史 C++ 内容")
            first = builder.build_screen_record(
                (first_item,), capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True, screen_index=1, screen_id="r06-1",
                normalization=first_norm, ocr_min_confidence=0.85,
            )
            second_item, second_norm = self._normalization("r06-2", "历史 C++ 内容 新增")
            second = builder.build_screen_record(
                (second_item,), capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True, screen_index=2, screen_id="r06-2",
                normalization=second_norm, ocr_min_confidence=0.85,
            )
        document = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
        )
        self.assertEqual(evaluate.call_count, 2)
        self.assertEqual(first.similarity_result.similarity_status, SimilarityStatus.NO_REFERENCE)
        self.assertEqual(second.similarity_result.reference_screen_id, "r06-1")
        self.assertEqual(document.similarity_summary.screen_count, 2)
        self.assertEqual(document.screens, (first, second))

    def test_evaluator_exception_is_single_pass_fail_open_and_keeps_r05_projection(self):
        item, normalization = self._normalization("r06-failed", "R06 异常仍保留 R05")
        builder = CandidateOcrBuilder(
            "run", 1, candidate_record_id="failed", aggregation_mode="record",
            similarity_mode="record",
        )
        with patch.object(
            CandidateSimilarityEvaluator, "evaluate", side_effect=RuntimeError("synthetic"),
        ) as evaluate:
            record = builder.build_screen_record(
                (item,), capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True, screen_index=1, screen_id="r06-failed",
                normalization=normalization, ocr_min_confidence=0.85,
            )
        self.assertEqual(evaluate.call_count, 1)
        self.assertEqual(record.aggregation_status, AggregationStatus.COMPLETED)
        self.assertEqual(record.similarity_result.similarity_status, SimilarityStatus.FAILED)
        self.assertEqual(record.similarity_result.warning_codes, ("evaluation_failed",))

    def test_summary_exception_fails_open_without_mutating_saved_screens_or_context(self):
        item, normalization = self._normalization("r06-summary", "R06 summary fallback C++")
        builder = CandidateOcrBuilder(
            "run", 1, candidate_record_id="summary-fallback", aggregation_mode="record",
            similarity_mode="record",
        )
        record = builder.build_screen_record(
            (item,), capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True, screen_index=1, screen_id="r06-summary",
            normalization=normalization, ocr_min_confidence=0.85,
        )
        expected_screen = record
        evaluator = builder._similarity_evaluator
        aggregator = builder._aggregator
        screen_reference = weakref.ref(record)
        evaluator_reference = weakref.ref(evaluator)
        aggregator_reference = weakref.ref(aggregator)

        with (
            self.assertLogs("ocr_candidate", level="WARNING") as logs,
            patch("ocr_candidate.recompute_similarity_summary", side_effect=RuntimeError("injected-summary")) as summary,
        ):
            document = builder.finalize(
                CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            )

        self.assertEqual(summary.call_count, 1)
        self.assertEqual(logs.output, [
            "WARNING:ocr_candidate:event=r06_candidate_summary_failed warning_code=evaluation_failed",
        ])
        self.assertTrue(builder.finalized)
        self.assertEqual(builder.retained_screen_count, 0)
        self.assertIsNone(builder._aggregator)
        self.assertIsNone(builder._similarity_evaluator)
        self.assertEqual(document.screens, (expected_screen,))
        self.assertEqual(document.screens[0].similarity_result, record.similarity_result)
        self.assertEqual(document.similarity_summary, recompute_similarity_summary(document.screens))

        del summary
        del document
        del record
        del expected_screen
        del evaluator
        del aggregator
        gc.collect()

        self.assertIsNone(screen_reference())
        self.assertIsNone(evaluator_reference())
        self.assertIsNone(aggregator_reference())


if __name__ == "__main__":
    unittest.main()
