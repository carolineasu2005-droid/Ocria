import copy
import gc
import statistics
import time
import tracemalloc
import unittest
from dataclasses import FrozenInstanceError, replace
from unittest.mock import patch

import ocr_aggregation

from ocr_aggregation import (
    AGGREGATION_CONFIG_VERSION,
    AGGREGATION_VERSION,
    DEFAULT_OCR_AGGREGATION_CONFIG,
    AggregationInvariantError,
    ExactBoundaryMatch,
    FuzzyGroupScore,
    FuzzyBoundaryCandidate,
    FuzzyBoundaryMatch,
    CandidateDocumentAggregator,
    CandidateAggregationFinalizeConflictError,
    HistoricalSequenceIndex,
    OcrAggregationConfig,
    R04SegmentAdapterError,
    apply_exact_boundary_occurrences,
    apply_fuzzy_boundary_occurrences,
    adapt_r04_screen_segments,
    aggregation_char_count,
    aggregation_config_digest,
    aggregation_config_snapshot,
    build_document_text,
    document_segment_id,
    find_exact_boundary_overlap,
    find_fuzzy_boundary_overlap,
    classify_historical_duplicates,
    fuzzy_content_char_count,
    fuzzy_unmatched_content_count,
    enumerate_fuzzy_tilings,
    score_fuzzy_group,
    match_id,
    restore_aggregation_config,
)
from ocr_candidate import CandidateOcrBuilder
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_records import (
    AGGREGATION_WARNING_CODES,
    AggregationDuplicateRisk,
    AggregationMatchType,
    AggregationOccurrenceRole,
    CaptureType,
    CaptureStatus,
    NormalizationStatus,
    OcrDocumentSegment,
    OcrSegmentMatchEvidence,
    OcrSourceOccurrence,
)
from ocr_text import OCRItem


class AggregationFixtureMixin:
    def make_screen(
        self, texts=("首行 Python", "第二行 C++"), *, screen_id="screen-1",
        screen_index=1,
    ):
        items = tuple(
            OCRItem(
                text,
                0.99,
                ((0, index * 30), (200, index * 30), (200, index * 30 + 20), (0, index * 30 + 20)),
            )
            for index, text in enumerate(texts)
        )
        boxes = tuple(
            NormalizationBox(
                "{0}:box:{1}".format(screen_id, index),
                item.text,
                item.box,
                index,
                item.confidence,
            )
            for index, item in enumerate(items)
        )
        normalization = normalize_ocr_text(boxes)
        return CandidateOcrBuilder("run-1", 1, candidate_record_id="candidate-1").build_screen_record(
            items,
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            screen_index=screen_index,
            screen_id=screen_id,
            normalization=normalization,
            ocr_min_confidence=0.85,
        )

    def origin(self, *, order=0, screen_id="screen-1", screen_index=1):
        return OcrSourceOccurrence(
            occurrence_order=order,
            source_screen_id=screen_id,
            source_screen_index=screen_index,
            source_segment_ids=("{0}:line:0".format(screen_id),),
            source_ocr_box_ids=("{0}:box:0".format(screen_id),),
            occurrence_role=AggregationOccurrenceRole.ORIGIN,
            match_id=None,
        )

    def document(self, *, order=0, text="显示正文", occurrences=None):
        from ocr_normalization import build_comparison_text

        comparison = build_comparison_text(text)
        return OcrDocumentSegment(
            document_segment_id=document_segment_id(order),
            order=order,
            normalized_text=text,
            comparison_text=comparison,
            comparison_char_count=len(comparison),
            source_occurrences=(self.origin(),) if occurrences is None else occurrences,
        )


class AggregationConfigTests(unittest.TestCase):
    def test_default_snapshot_restore_and_digest_are_stable(self):
        snapshot = aggregation_config_snapshot()
        self.assertEqual(snapshot["aggregation_version"], AGGREGATION_VERSION)
        self.assertEqual(snapshot["aggregation_config_version"], AGGREGATION_CONFIG_VERSION)
        self.assertEqual(restore_aggregation_config(snapshot), DEFAULT_OCR_AGGREGATION_CONFIG)
        self.assertEqual(len(aggregation_config_digest(snapshot)), 64)
        self.assertTrue(aggregation_config_digest(snapshot).islower())
        self.assertEqual(
            {aggregation_config_digest(DEFAULT_OCR_AGGREGATION_CONFIG) for _ in range(100)},
            {aggregation_config_digest(snapshot)},
        )

    def test_snapshot_rejects_missing_extra_and_digest_drift(self):
        snapshot = aggregation_config_snapshot()
        missing = dict(snapshot)
        missing.pop("max_screen_segments")
        extra = dict(snapshot, unexpected=1)
        drift = dict(snapshot, fuzzy_similarity_threshold=0.93)
        for value in (missing, extra):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    restore_aggregation_config(value)
        self.assertNotEqual(aggregation_config_digest(snapshot), aggregation_config_digest(drift))

    def test_config_rejects_bool_nonfinite_and_invalid_boundaries(self):
        cases = (
            {"max_screen_segments": True},
            {"fuzzy_similarity_threshold": float("nan")},
            {"fuzzy_uncertain_similarity_floor": float("inf")},
            {"fuzzy_uncertain_similarity_floor": 0.95},
            {"fuzzy_max_combined_segments": 2},
            {"historical_max_segment_count": 1},
            {"max_formal_screen_count": 0},
        )
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    OcrAggregationConfig(**change)
        self.assertEqual(OcrAggregationConfig(fuzzy_similarity_threshold=1.0).fuzzy_similarity_threshold, 1.0)
        self.assertEqual(OcrAggregationConfig(fuzzy_uncertain_similarity_floor=0.0).fuzzy_uncertain_similarity_floor, 0.0)


class AggregationRecordTests(AggregationFixtureMixin, unittest.TestCase):
    def test_frozen_document_and_occurrence_validate_identity_and_text(self):
        document = self.document()
        self.assertEqual(document.document_segment_id, "document:segment:0")
        with self.assertRaises(FrozenInstanceError):
            document.order = 1
        with self.assertRaises(ValueError):
            replace(document, document_segment_id="document:segment:1")
        with self.assertRaises(ValueError):
            replace(document, comparison_text="not-r04")
        with self.assertRaises(ValueError):
            replace(document, source_occurrences=(replace(self.origin(), occurrence_order=1),))

    def test_exact_and_fuzzy_evidence_contracts(self):
        exact = OcrSegmentMatchEvidence(
            match_id=match_id(1, 0),
            match_type=AggregationMatchType.ADJACENT_EXACT,
            current_screen_id="screen-1",
            current_screen_index=1,
            current_segment_ids=("screen-1:line:0",),
            current_ocr_box_ids=("screen-1:box:0",),
            matched_document_segment_ids=("document:segment:0",),
            score=None,
            exact_basis="adjacent_boundary",
            risk=AggregationDuplicateRisk.NONE,
            warning_codes=(),
        )
        fuzzy = replace(
            exact,
            match_id=match_id(1, 1),
            match_type=AggregationMatchType.ADJACENT_FUZZY_1_1,
            score=0.94,
            exact_basis=None,
            risk=AggregationDuplicateRisk.LOW,
        )
        self.assertEqual(exact.score, None)
        self.assertEqual(fuzzy.score, 0.94)
        bad_cases = (
            dict(exact.__dict__, score=1.0),
            dict(fuzzy.__dict__, score=1.01),
            dict(fuzzy.__dict__, exact_basis="wrong"),
            dict(exact.__dict__, warning_codes=("not-a-code",)),
            dict(exact.__dict__, risk=AggregationDuplicateRisk.ELEVATED),
        )
        for value in bad_cases:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    OcrSegmentMatchEvidence(**value)
        self.assertIn("finalize_failed", AGGREGATION_WARNING_CODES)

    def test_matched_occurrence_requires_matching_id_and_unique_sources(self):
        with self.assertRaises(ValueError):
            replace(self.origin(), occurrence_role=AggregationOccurrenceRole.MATCHED)
        with self.assertRaises(ValueError):
            replace(self.origin(), source_segment_ids=("screen-1:line:0", "screen-1:line:0"))
        matched = replace(
            self.origin(),
            occurrence_role=AggregationOccurrenceRole.MATCHED,
            match_id=match_id(1, 0),
        )
        self.assertEqual(matched.match_id, "match:1:0")


class R04SegmentAdapterTests(AggregationFixtureMixin, unittest.TestCase):
    def test_adapter_returns_original_segments_for_single_multi_and_unicode_lines(self):
        record = self.make_screen(("中文ＡＢＣ", "C++ / .NET 特殊符号！"))
        adapted = adapt_r04_screen_segments(record)
        self.assertIs(adapted, record.segments)
        self.assertEqual(tuple(segment.order for segment in adapted), (0, 1))
        self.assertEqual(adapted[0].ocr_box_ids, ("screen-1:box:0",))

    def test_adapter_preserves_one_line_multiple_box_source_order(self):
        record = self.make_screen(("Python", "C++"))
        # Both boxes share a line when their geometry is intentionally equal.
        items = (
            OCRItem("Python", 0.99, ((0, 0), (100, 0), (100, 20), (0, 20))),
            OCRItem("C++", 0.99, ((105, 0), (200, 0), (200, 20), (105, 20))),
        )
        boxes = tuple(NormalizationBox("screen-2:box:{0}".format(i), item.text, item.box, i, item.confidence) for i, item in enumerate(items))
        same_line = CandidateOcrBuilder("run-1", 1, candidate_record_id="candidate-1").build_screen_record(
            items, capture_type=CaptureType.FORMAL_SCREEN, is_formal_screen=True,
            screen_index=1, screen_id="screen-2", normalization=normalize_ocr_text(boxes),
            ocr_min_confidence=0.85,
        )
        adapted = adapt_r04_screen_segments(same_line)
        self.assertEqual(len(adapted), 1)
        self.assertEqual(adapted[0].ocr_box_ids, ("screen-2:box:0", "screen-2:box:1"))
        self.assertEqual(record.segments[0].segment_id, "screen-1:line:0")

    def test_adapter_handles_completed_empty_screen_and_rejects_r04_unavailable(self):
        empty = self.make_screen(())
        self.assertEqual(adapt_r04_screen_segments(empty), ())
        failed = copy.copy(empty)
        object.__setattr__(failed, "normalization_status", NormalizationStatus.FAILED)
        not_attempted = copy.copy(empty)
        object.__setattr__(not_attempted, "normalization_status", NormalizationStatus.NOT_ATTEMPTED)
        for value, expected in ((failed, "r04_not_completed"), (not_attempted, "r04_not_attempted")):
            with self.subTest(expected=expected):
                with self.assertRaises(R04SegmentAdapterError) as caught:
                    adapt_r04_screen_segments(value)
                self.assertEqual(str(caught.exception), expected)

    def test_adapter_rejects_invalid_r04_mapping_without_mutating_input(self):
        record = self.make_screen()
        original_ids = tuple(box.box_id for box in record.raw_boxes)
        cases = []
        for changed_segment in (
            replace(record.segments[0], segment_id="wrong"),
            replace(record.segments[0], order=2),
            replace(record.segments[0], ocr_box_ids=("missing",)),
            replace(record.segments[0], comparison_text="wrong"),
            replace(
                record.segments[0],
                comparison_text=record.segments[0].comparison_text + " ",
            ),
        ):
            invalid = copy.copy(record)
            object.__setattr__(invalid, "segments", (changed_segment, *record.segments[1:]))
            cases.append(invalid)
        for value in cases:
            with self.subTest(value=value.segments[0]):
                with self.assertRaises(R04SegmentAdapterError):
                    adapt_r04_screen_segments(value)
        self.assertEqual(tuple(box.box_id for box in record.raw_boxes), original_ids)
        self.assertEqual(record.segments, adapt_r04_screen_segments(record))

    def test_adapter_performance_and_memory_on_256_prebuilt_segments(self):
        record = self.make_screen(tuple("line {0} 适配性能".format(i) for i in range(256)), screen_id="screen-perf")
        for _ in range(10):
            adapt_r04_screen_segments(record)
        durations = []
        for _ in range(60):
            started = time.perf_counter()
            adapt_r04_screen_segments(record)
            durations.append((time.perf_counter() - started) * 1000)
        p95 = statistics.quantiles(durations, n=20)[18]
        tracemalloc.start()
        adapt_r04_screen_segments(record)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLessEqual(p95, 5.0)
        self.assertLessEqual(peak, 4 * 1024 * 1024)


class DocumentProjectionTests(AggregationFixtureMixin, unittest.TestCase):
    def test_document_text_empty_single_multi_and_deterministic(self):
        one = self.document(order=0, text="第一段")
        two = self.document(order=1, text="第二段")
        self.assertEqual(build_document_text(()), "")
        self.assertEqual(build_document_text((one,)), "第一段")
        self.assertEqual(build_document_text((one, two)), "第一段\n第二段")
        self.assertFalse(build_document_text((one, two)).endswith("\n"))
        self.assertEqual({build_document_text((one, two)) for _ in range(100)}, {"第一段\n第二段"})

    def test_document_text_rejects_order_and_empty_text_without_global_deduplication(self):
        one = self.document(order=0, text="同文")
        same_text_different_id = self.document(order=1, text="同文")
        self.assertEqual(build_document_text((one, same_text_different_id)), "同文\n同文")
        with self.assertRaises(AggregationInvariantError):
            build_document_text((same_text_different_id, one))
        empty = object.__new__(OcrDocumentSegment)
        object.__setattr__(empty, "document_segment_id", "document:segment:0")
        object.__setattr__(empty, "order", 0)
        object.__setattr__(empty, "normalized_text", "")
        with self.assertRaises(AggregationInvariantError):
            build_document_text((empty,))

    def test_character_count_never_renormalizes_r04_comparison_text(self):
        self.assertEqual(aggregation_char_count("中文abc+"), 6)
        with self.assertRaises(AggregationInvariantError):
            aggregation_char_count("has space")
        with self.assertRaises(AggregationInvariantError):
            aggregation_char_count(None)


class ExactBoundaryOverlapTests(AggregationFixtureMixin, unittest.TestCase):
    @staticmethod
    def text(label, length=12):
        return (label + "_" + ("x" * length))

    def documents(self, texts):
        return tuple(self.document(order=index, text=text) for index, text in enumerate(texts))

    def current(self, texts, *, screen_id="screen-2"):
        return self.make_screen(tuple(texts), screen_id=screen_id).segments

    def test_no_overlap_all_new_and_empty_screen(self):
        document = self.documents((self.text("doc-a"), self.text("doc-b")))
        current = self.current((self.text("cur-a"), self.text("cur-b")))
        result = find_exact_boundary_overlap(document, current)
        self.assertFalse(result.accepted)
        self.assertEqual(result.remaining_current_segment_ids, tuple(item.segment_id for item in current))
        self.assertEqual(result.uncertain_current_segment_ids, ())
        self.assertEqual(find_exact_boundary_overlap(document, ()).remaining_current_segment_ids, ())

    def test_partial_large_and_complete_screen_overlap_are_longest_first(self):
        a, b, c, d = tuple(self.text(label) for label in ("a", "b", "c", "d"))
        document = self.documents((a, b, c))
        partial = self.current((b, c, d))
        result = find_exact_boundary_overlap(document, partial)
        self.assertTrue(result.accepted)
        self.assertEqual(result.matched_current_segment_ids, tuple(item.segment_id for item in partial[:2]))
        self.assertEqual(result.remaining_current_segment_ids, (partial[2].segment_id,))
        self.assertEqual(result.exact_basis, "comparison_sequence_equal")
        complete = self.current((a, b, c), screen_id="screen-3")
        full = find_exact_boundary_overlap(document, complete)
        self.assertEqual(len(full.matched_current_segment_ids), 3)
        self.assertEqual(full.remaining_current_segment_ids, ())

    def test_only_tail_head_is_compared_not_document_or_current_middle(self):
        a, b, c, d = tuple(self.text(label) for label in ("a", "b", "c", "d"))
        document = self.documents((a, b, c))
        current_middle = self.current((d, b, c))
        self.assertFalse(find_exact_boundary_overlap(document, current_middle).accepted)
        document_middle = self.documents((a, b, c))
        current = self.current((a, d))
        self.assertFalse(find_exact_boundary_overlap(document_middle, current).accepted)
        reversed_current = self.current((c, b), screen_id="screen-4")
        self.assertFalse(find_exact_boundary_overlap(document, reversed_current).accepted)

    def test_short_exact_prefix_is_uncertain_and_not_suppressed(self):
        title = "短标题"
        document = self.documents((self.text("prefix"), title))
        current = self.current((title, self.text("new")))
        result = find_exact_boundary_overlap(document, current)
        self.assertFalse(result.accepted)
        self.assertEqual(result.uncertain_current_segment_ids, (current[0].segment_id,))
        self.assertEqual(result.remaining_current_segment_ids, tuple(item.segment_id for item in current))
        self.assertEqual(result.match_evidence, ())

    def test_normal_thresholds_23_24_and_short_8_9(self):
        one = "a" * 12
        twenty_three = "b" * 11
        twenty_four = "b" * 12
        document_23 = self.documents((one, twenty_three))
        current_23 = self.current((one, twenty_three))
        rejected = find_exact_boundary_overlap(document_23, current_23)
        self.assertFalse(rejected.accepted)
        self.assertEqual(len(rejected.uncertain_current_segment_ids), 2)
        accepted = find_exact_boundary_overlap(self.documents((one, twenty_four)), self.current((one, twenty_four), screen_id="screen-3"))
        self.assertTrue(accepted.accepted)
        short_document = self.documents(("a" * 8, "b" * 8, "c" * 8))
        short_current = self.current(("a" * 8, "b" * 8, "c" * 8), screen_id="screen-4")
        self.assertFalse(find_exact_boundary_overlap(short_document, short_current).accepted)
        nine = "n" * 9
        nine_document = self.documents((nine, nine + "1", nine + "2"))
        nine_current = self.current((nine, nine + "1", nine + "2"), screen_id="screen-5")
        self.assertTrue(find_exact_boundary_overlap(nine_document, nine_current).accepted)

    def test_single_full_screen_exception_is_exactly_48_characters(self):
        for length, accepted, basis in (
            (47, False, None),
            (48, True, "single_full_screen_equal"),
        ):
            with self.subTest(length=length):
                text = "z" * length
                result = find_exact_boundary_overlap(
                    self.documents((text,)),
                    self.current((text,), screen_id="screen-{0}".format(length)),
                )
                self.assertEqual(result.accepted, accepted)
                self.assertEqual(result.exact_basis, basis)

    def test_exact_evidence_and_occurrences_are_one_to_one_and_immutable(self):
        a, b = self.text("a"), self.text("b")
        document = self.documents((a, b))
        current = self.current((a, b))
        result = find_exact_boundary_overlap(document, current)
        evidence = result.match_evidence[0]
        self.assertEqual(evidence.match_type, AggregationMatchType.ADJACENT_EXACT)
        self.assertIsNone(evidence.score)
        self.assertEqual(evidence.exact_basis, "comparison_sequence_equal")
        self.assertEqual(len(result.occurrence_mappings), 2)
        updated = apply_exact_boundary_occurrences(document, result)
        self.assertEqual([len(item.source_occurrences) for item in updated], [2, 2])
        self.assertEqual([len(item.source_occurrences) for item in document], [1, 1])
        self.assertEqual(updated[0].source_occurrences[-1].match_id, "match:1:0")

    def test_same_text_at_different_document_positions_remains_position_specific(self):
        repeated = self.text("same")
        document = self.documents((repeated, self.text("middle"), repeated, self.text("tail")))
        current = self.current((repeated, self.text("tail")))
        result = find_exact_boundary_overlap(document, current)
        self.assertEqual(result.matched_document_segment_ids, ("document:segment:2", "document:segment:3"))

    def test_seventh_and_eighth_screen_style_new_tail_is_retained_and_deterministic(self):
        a, b, new = self.text("a"), self.text("b"), self.text("new")
        document = self.documents((a, b))
        current = self.current((a, b, new), screen_id="screen-8")
        expected = find_exact_boundary_overlap(document, current)
        self.assertEqual(expected.remaining_current_segment_ids, (current[2].segment_id,))
        self.assertEqual(
            {find_exact_boundary_overlap(document, current) for _ in range(100)},
            {expected},
        )

    def test_256_segment_exact_boundary_performance(self):
        texts = tuple(self.text("segment{0}".format(index), 10) for index in range(256))
        document = self.documents(texts)
        current = self.current(texts, screen_id="screen-256")
        for _ in range(10):
            find_exact_boundary_overlap(document, current)
        durations = []
        for _ in range(60):
            started = time.perf_counter()
            result = find_exact_boundary_overlap(document, current)
            durations.append((time.perf_counter() - started) * 1000)
        self.assertTrue(result.accepted)
        self.assertLessEqual(statistics.quantiles(durations, n=20)[18], 20.0)


class FuzzyBoundaryOverlapTests(AggregationFixtureMixin, unittest.TestCase):
    def documents(self, texts):
        return tuple(self.document(order=index, text=text) for index, text in enumerate(texts))

    def current(self, texts, *, screen_id="screen-fuzzy"):
        return self.make_screen(tuple(texts), screen_id=screen_id).segments

    @staticmethod
    def changed(text, position=-1, replacement="z"):
        if position < 0:
            position += len(text)
        return text[:position] + replacement + text[position + 1:]

    @staticmethod
    def unique_text(seed, length=50):
        return "".join(chr(0x4E00 + seed * 600 + index) for index in range(length))

    def test_content_and_unmatched_helpers_exclude_artificial_lf(self):
        self.assertEqual(fuzzy_content_char_count("ab\ncd"), 4)
        self.assertEqual(fuzzy_unmatched_content_count("ab\ncd", ((1, 4),)), 2)
        with self.assertRaises(AggregationInvariantError):
            fuzzy_unmatched_content_count("abc", ((2, 1),))

    def test_tilings_allow_only_the_three_group_shapes_and_are_monotonic(self):
        tilings = enumerate_fuzzy_tilings(2, 2)
        self.assertTrue(tilings)
        self.assertTrue(all(shape in ((1, 1), (1, 2), (2, 1)) for path in tilings for shape in path))
        self.assertNotIn(((2, 2),), tilings)
        with self.assertRaises(AggregationInvariantError):
            enumerate_fuzzy_tilings(0, 1)

    def test_score_thresholds_unmatched_and_character_bounds(self):
        base = self.unique_text(1)
        at_94 = self.changed(base, -1, "Q")
        group_94 = score_fuzzy_group(self.documents((base,)), self.current((at_94,)))
        self.assertGreaterEqual(group_94.score, 0.94)
        self.assertTrue(group_94.is_accepted)
        at_88 = base[:-6] + "UVWXYZ"
        group_88 = score_fuzzy_group(self.documents((base,)), self.current((at_88,), screen_id="screen-88"))
        self.assertGreaterEqual(group_88.score, 0.88)
        self.assertLess(group_88.score, 0.94)
        self.assertTrue(group_88.is_gray)
        unmatched_2 = score_fuzzy_group(
            self.documents((base[:-2] + "XY",)),
            self.current((base[:-2] + "UV",), screen_id="screen-unmatched-2"),
        )
        self.assertLessEqual(unmatched_2.left_unmatched_chars, 2)
        self.assertLessEqual(unmatched_2.right_unmatched_chars, 2)
        unmatched_3 = score_fuzzy_group(
            self.documents((base[:-3] + "XYZ",)),
            self.current((base[:-3] + "UVW",), screen_id="screen-unmatched-3"),
        )
        self.assertEqual(unmatched_3.left_unmatched_chars, 3)
        self.assertEqual(unmatched_3.right_unmatched_chars, 3)
        self.assertTrue(unmatched_3.is_gray)
        too_short = score_fuzzy_group(self.documents((self.unique_text(2, 31),)), self.current((self.changed(self.unique_text(2, 31), -1, "b"),), screen_id="screen-short"))
        self.assertFalse(too_short.is_accepted)
        within_limit = score_fuzzy_group(self.documents(("a" * 512,)), self.current(("a" * 511 + "b",), screen_id="screen-512"))
        self.assertTrue(within_limit.is_accepted)
        over_limit = score_fuzzy_group(self.documents(("a" * 513,)), self.current(("a" * 512 + "b",), screen_id="screen-513"))
        self.assertTrue(over_limit.is_gray)

    def test_1_to_1_fuzzy_evidence_and_occurrence_are_pure(self):
        document_text = self.unique_text(3, 60)
        current_text = self.changed(document_text, -1, "x")
        document = self.documents((document_text,))
        current = self.current((current_text,))
        result = find_fuzzy_boundary_overlap(document, current)
        self.assertTrue(result.accepted)
        self.assertEqual(result.match_evidence[0].match_type, AggregationMatchType.ADJACENT_FUZZY_1_1)
        self.assertGreaterEqual(result.match_evidence[0].score, 0.94)
        updated = apply_fuzzy_boundary_occurrences(document, result)
        self.assertEqual(len(document[0].source_occurrences), 1)
        self.assertEqual(len(updated[0].source_occurrences), 2)

    def test_1_to_2_and_2_to_1_preserve_group_source_mapping(self):
        left, right = "A" * 40, "B" * 40
        document_one = self.documents((left + right,))
        current_two = self.current((left, right), screen_id="screen-1-to-2")
        one_to_two = find_fuzzy_boundary_overlap(document_one, current_two)
        self.assertTrue(one_to_two.accepted)
        self.assertEqual(one_to_two.match_evidence[0].match_type, AggregationMatchType.ADJACENT_FUZZY_1_2)
        self.assertEqual(len(one_to_two.occurrence_mappings[0].occurrence.source_segment_ids), 2)
        document_two = self.documents((left, right))
        current_one = self.current((left + right,), screen_id="screen-2-to-1")
        two_to_one = find_fuzzy_boundary_overlap(document_two, current_one)
        self.assertTrue(two_to_one.accepted)
        self.assertEqual(two_to_one.match_evidence[0].match_type, AggregationMatchType.ADJACENT_FUZZY_2_1)
        self.assertEqual(len(two_to_one.occurrence_mappings), 2)
        self.assertEqual(
            {item.occurrence.match_id for item in two_to_one.occurrence_mappings},
            {"match:1:0"},
        )

    def test_exact_equal_single_group_never_bypasses_exact_protection(self):
        text = "x" * 64
        document = self.documents((text,))
        current = self.current((text,), screen_id="screen-exact-protected")
        exact = find_exact_boundary_overlap(document, current)
        fuzzy = find_fuzzy_boundary_overlap(document, current)
        self.assertTrue(exact.accepted)
        self.assertFalse(fuzzy.accepted)
        self.assertEqual(fuzzy.uncertain_current_segment_ids, (current[0].segment_id,))

    def test_gray_and_low_similarity_keep_or_leave_current_prefix(self):
        base = self.unique_text(4)
        document = self.documents((base[:-6] + "UVWXYZ",))
        gray_current = self.current((base[:-3] + "XYZ",), screen_id="screen-gray")
        gray = find_fuzzy_boundary_overlap(document, gray_current)
        self.assertFalse(gray.accepted)
        self.assertEqual(gray.uncertain_current_segment_ids, (gray_current[0].segment_id,))
        low_current = self.current(("q" * 50,), screen_id="screen-low")
        low = find_fuzzy_boundary_overlap(document, low_current)
        self.assertEqual(low.uncertain_current_segment_ids, ())

    def test_proven_low_multiset_bound_skips_exact_matcher_without_changing_result(self):
        document = self.documents((self.unique_text(5),))
        current = self.current(
            (self.unique_text(15),),
            screen_id="screen-fast-reject",
        )
        with patch(
            "ocr_aggregation.SequenceMatcher",
            side_effect=AssertionError("exact matcher should not be needed"),
        ):
            result = find_fuzzy_boundary_overlap(document, current)
        self.assertFalse(result.accepted)
        self.assertEqual(result.uncertain_current_segment_ids, ())
        self.assertEqual(
            result.remaining_current_segment_ids,
            (current[0].segment_id,),
        )

    def test_tail_head_limits_and_candidate_limit_fail_open(self):
        document_texts = tuple(self.unique_text(index + 10, 44) for index in range(5))
        changed_texts = tuple(self.changed(value, -1, "b") for value in document_texts)
        result = find_fuzzy_boundary_overlap(
            self.documents(document_texts),
            self.current(changed_texts[1:] + (self.unique_text(99, 44),), screen_id="screen-five"),
        )
        self.assertEqual(len(result.matched_current_segment_ids), 4)
        self.assertEqual(len(result.remaining_current_segment_ids), 1)
        limited_config = OcrAggregationConfig(fuzzy_candidate_limit=1)
        limited = find_fuzzy_boundary_overlap(
            self.documents(document_texts[:2]),
            self.current(changed_texts[:2], screen_id="screen-limit"),
            limited_config,
        )
        self.assertTrue(limited.candidate_limit_exceeded)
        self.assertEqual(len(limited.uncertain_current_segment_ids), 2)

    def test_no_2_to_2_or_general_group_is_scored(self):
        values = ("a" * 40, "b" * 40)
        with self.assertRaises(AggregationInvariantError):
            score_fuzzy_group(self.documents(values), self.current(values, screen_id="screen-2x2"))
        with self.assertRaises(AggregationInvariantError):
            score_fuzzy_group(self.documents(values + ("c" * 40,)), self.current(values, screen_id="screen-3x2"))

    def test_score_tie_within_epsilon_is_ambiguous_without_shape_tiebreak(self):
        group = FuzzyGroupScore(
            shape=(1, 1), left_text="a" * 40, right_text="b" * 40,
            left_content_chars=40, right_content_chars=40, score=0.95,
            left_unmatched_chars=1, right_unmatched_chars=1,
            exact_equal_protected=False, is_accepted=True, is_gray=False,
        )
        first = FuzzyBoundaryCandidate(
            shapes=((1, 1),), document_segment_ids=("document:segment:0",),
            current_segment_ids=("screen-tie:line:0",), groups=(group,),
            document_content_chars=40, current_content_chars=40, weighted_score=0.950,
        )
        close = replace(first, shapes=((1, 2),), weighted_score=0.946)
        far = replace(first, shapes=((2, 1),), weighted_score=0.944)
        best, ties = ocr_aggregation._fuzzy_tie_candidates(
            (first, close), DEFAULT_OCR_AGGREGATION_CONFIG
        )
        self.assertEqual(best, first)
        self.assertEqual(ties, (close,))
        _, no_ties = ocr_aggregation._fuzzy_tie_candidates(
            (first, far), DEFAULT_OCR_AGGREGATION_CONFIG
        )
        self.assertEqual(no_ties, ())

    def test_fuzzy_result_is_deterministic_and_does_not_modify_input(self):
        text = self.unique_text(20, 60)
        document = self.documents((text,))
        current = self.current((self.changed(text, -1, "z"),), screen_id="screen-deterministic")
        expected = find_fuzzy_boundary_overlap(document, current)
        self.assertEqual(
            {find_fuzzy_boundary_overlap(document, current) for _ in range(100)},
            {expected},
        )
        self.assertEqual(len(document[0].source_occurrences), 1)
        self.assertEqual(current[0].normalized_text, self.changed(text, -1, "z"))

    def test_fuzzy_pressure_performance(self):
        document_texts = tuple(self.unique_text(index + 30, 54) for index in range(4))
        current_texts = tuple(self.changed(value, -1, "b") for value in document_texts)
        document = self.documents(document_texts)
        current = self.current(current_texts, screen_id="screen-fuzzy-performance")
        for _ in range(10):
            find_fuzzy_boundary_overlap(document, current)
        durations = []
        for _ in range(40):
            started = time.perf_counter()
            find_fuzzy_boundary_overlap(document, current)
            durations.append((time.perf_counter() - started) * 1000)
        self.assertLessEqual(statistics.quantiles(durations, n=20)[18], 50.0)


class HistoricalAndAggregatorTests(AggregationFixtureMixin, unittest.TestCase):
    def test_segment_limit_keeps_all_valid_segments_uncertain_without_matching(self):
        for count, exceeds_limit in ((255, False), (256, False), (257, True), (300, True)):
            with self.subTest(count=count):
                texts = tuple("segment {:03d} content long enough".format(index) for index in range(count))
                source = self.make_screen(texts, screen_id="screen-limit-{}".format(count))
                before = copy.deepcopy(source)
                aggregator = CandidateDocumentAggregator("run-1", "candidate-1")
                with patch("ocr_aggregation._find_exact_boundary_overlap_validated") as exact, \
                        patch("ocr_aggregation._find_fuzzy_boundary_overlap_validated") as fuzzy, \
                        patch("ocr_aggregation._classify_historical_duplicates_validated") as historical:
                    if exceeds_limit:
                        result = aggregator.add_screen(source)
                        exact.assert_not_called()
                        fuzzy.assert_not_called()
                        historical.assert_not_called()
                    else:
                        exact.side_effect = lambda document, current, config, identity: ocr_aggregation.ExactBoundaryMatch(
                            (), (), tuple(item.segment_id for item in current), (), None, (), ()
                        )
                        fuzzy.side_effect = lambda document, current, config, identity: ocr_aggregation.FuzzyBoundaryMatch(
                            (), (), tuple(item.segment_id for item in current), (), (), ()
                        )
                        historical.side_effect = lambda *args, **kwargs: ocr_aggregation.HistoricalDuplicateClassification(
                            (), (), tuple(item.segment_id for item in args[1]), (), (), (), ()
                        )
                        result = aggregator.add_screen(source)
                        self.assertTrue(exact.called)
                built = aggregator.finalize(CaptureStatus.COMPLETED)
                self.assertEqual(source, before)
                if exceeds_limit:
                    self.assertEqual(result.status.value, "partial")
                    self.assertEqual(result.matched_segment_ids, ())
                    self.assertEqual(result.new_segment_ids, ())
                    self.assertEqual(result.uncertain_segment_ids, tuple(
                        item.segment_id for item in source.segments
                    ))
                    self.assertEqual(result.warning_codes, ("screen_segment_limit_exceeded",))
                    self.assertEqual(built.document_build_status.value, "partial")
                    self.assertEqual(built.aggregation_duplicate_risk, AggregationDuplicateRisk.ELEVATED)
                    self.assertEqual(len(built.document_segments), count)
                    self.assertNotIn("segment_mapping_invalid", built.aggregation_warning_codes)
                else:
                    self.assertNotIn("screen_segment_limit_exceeded", result.warning_codes)

    def test_matching_stage_exceptions_fail_open_and_skip_later_stages(self):
        first = self.make_screen(
            ("first stage segment has enough content" * 2,),
            screen_id="screen-stage-first", screen_index=1,
        )

        exact_aggregator = CandidateDocumentAggregator("run-1", "candidate-1")
        with patch("ocr_aggregation._find_exact_boundary_overlap_validated", side_effect=RuntimeError), \
                patch("ocr_aggregation._find_fuzzy_boundary_overlap_validated") as fuzzy, \
                patch("ocr_aggregation._classify_historical_duplicates_validated") as historical:
            exact_result = exact_aggregator.add_screen(first)
        self.assertEqual(exact_result.status.value, "partial")
        self.assertEqual(exact_result.warning_codes, ("exact_stage_failed",))
        self.assertEqual(exact_result.uncertain_segment_ids, ("screen-stage-first:line:0",))
        fuzzy.assert_not_called(); historical.assert_not_called()

        fuzzy_aggregator = CandidateDocumentAggregator("run-1", "candidate-1")
        fuzzy_aggregator.add_screen(first)
        fuzzy_screen = self.make_screen(
            ("first stage segment has enough content" * 2 + "z",),
            screen_id="screen-stage-fuzzy", screen_index=2,
        )
        with patch("ocr_aggregation._find_fuzzy_boundary_overlap_validated", side_effect=RuntimeError), \
                patch("ocr_aggregation._classify_historical_duplicates_validated") as historical:
            fuzzy_result = fuzzy_aggregator.add_screen(fuzzy_screen)
        self.assertEqual(fuzzy_result.status.value, "partial")
        self.assertEqual(fuzzy_result.warning_codes, ("fuzzy_stage_failed",))
        self.assertEqual(fuzzy_result.uncertain_segment_ids, ("screen-stage-fuzzy:line:0",))
        historical.assert_not_called()

        history_aggregator = CandidateDocumentAggregator("run-1", "candidate-1")
        first_exact = self.make_screen(
            ("exact prefix alpha long enough" * 2, "exact prefix beta long enough" * 2),
            screen_id="screen-stage-history-1", screen_index=1,
        )
        second_exact = self.make_screen(
            ("exact prefix alpha long enough" * 2, "exact prefix beta long enough" * 2,
             "remaining history content long enough" * 2),
            screen_id="screen-stage-history-2", screen_index=2,
        )
        history_aggregator.add_screen(first_exact)
        with patch("ocr_aggregation._classify_historical_duplicates_validated", side_effect=RuntimeError):
            history_result = history_aggregator.add_screen(second_exact)
        built = history_aggregator.finalize(CaptureStatus.COMPLETED)
        self.assertEqual(history_result.status.value, "partial")
        self.assertEqual(history_result.warning_codes, ("historical_stage_failed",))
        self.assertEqual(history_result.matched_segment_ids, (
            "screen-stage-history-2:line:0", "screen-stage-history-2:line:1",
        ))
        self.assertEqual(history_result.uncertain_segment_ids, ("screen-stage-history-2:line:2",))
        self.assertEqual(built.document_build_status.value, "partial")
        self.assertEqual(built.aggregation_duplicate_risk, AggregationDuplicateRisk.ELEVATED)

    def test_exact_then_historical_keeps_per_screen_match_ids_unique(self):
        first = self.make_screen(
            (
                "Anchor Alpha detailed 00001", "Repeat Bravo detailed 00002",
                "Repeat Charlie detailed 00003", "Anchor Delta detailed 00004",
                "Boundary Echo detailed 00005", "Boundary Foxtrot detailed 00006",
            ),
            screen_id="screen-exact-history-1", screen_index=1,
        )
        second = self.make_screen(
            (
                "Boundary Echo detailed 00005", "Boundary Foxtrot detailed 00006",
                "Anchor Alpha detailed 00001", "Repeat Bravo detailed 00002",
                "Repeat Charlie detailed 00003", "Anchor Delta detailed 00004",
            ),
            screen_id="screen-exact-history-2", screen_index=2,
        )
        aggregator = CandidateDocumentAggregator("run-1", "candidate-1")
        aggregator.add_screen(first)
        result = aggregator.add_screen(second)

        self.assertEqual(
            tuple(item.match_type for item in result.match_evidence),
            (AggregationMatchType.ADJACENT_EXACT, AggregationMatchType.HISTORICAL_EXACT),
        )
        self.assertEqual(
            tuple(item.match_id for item in result.match_evidence),
            ("match:2:0", "match:2:1"),
        )
        self.assertEqual(len({item.match_id for item in result.match_evidence}), 2)
        self.assertNotIn("historical_stage_failed", result.warning_codes)

    def test_historical_unique_span_requires_both_external_anchors(self):
        values = ("前置锚点内容足够长" * 3, "重复职责甲内容足够长" * 3,
                  "重复职责乙内容足够长" * 3, "后置锚点内容足够长" * 3)
        document = tuple(self.document(order=index, text=text, occurrences=(self.origin(screen_id="old", screen_index=1),))
                         for index, text in enumerate(values))
        index = HistoricalSequenceIndex()
        index.add_document_segments(document)
        current = adapt_r04_screen_segments(self.make_screen(values, screen_id="new"))
        result = classify_historical_duplicates(document, current, index)
        self.assertEqual(result.matched_current_segment_ids, ("new:line:1", "new:line:2"))
        self.assertEqual(result.match_evidence[0].match_type, AggregationMatchType.HISTORICAL_EXACT)
        insufficient_current = adapt_r04_screen_segments(self.make_screen(values[1:], screen_id="short"))
        insufficient = classify_historical_duplicates(document, insufficient_current, index)
        self.assertFalse(insufficient.accepted)
        self.assertIn("historical_context_insufficient", insufficient.warning_codes)

    def test_historical_multi_source_and_duplicate_locations_fail_open(self):
        values = ("锚点之前足够长内容" * 3, "重复内容第一行" * 4,
                  "重复内容第二行" * 4, "锚点之后足够长内容" * 3,
                  "另一个前锚足够长内容" * 3, "重复内容第一行" * 4,
                  "重复内容第二行" * 4, "另一个后锚足够长内容" * 3)
        document = tuple(self.document(order=index, text=text, occurrences=(self.origin(screen_id="old", screen_index=1),))
                         for index, text in enumerate(values))
        index = HistoricalSequenceIndex(); index.add_document_segments(document)
        current = adapt_r04_screen_segments(self.make_screen(values[:4], screen_id="new"))
        ambiguous = classify_historical_duplicates(document, current, index)
        self.assertFalse(ambiguous.accepted)
        self.assertIn("historical_duplicate_ambiguous", ambiguous.warning_codes)

    def test_candidate_aggregator_lifecycle_is_candidate_local_and_idempotent(self):
        first = self.make_screen(("职位名称足够长" * 4, "Python工程经验足够长" * 3), screen_id="screen-a")
        second = self.make_screen(("Python工程经验足够长" * 3, "新增项目经历足够长" * 3), screen_id="screen-b")
        second = replace(second, screen_index=2, segments=tuple(
            replace(segment, screen_index=2, segment_id="screen-b:line:{0}".format(segment.order))
            for segment in second.segments))
        aggregator = CandidateDocumentAggregator("run-1", "candidate-1")
        aggregator.add_screen(first)
        aggregator.add_screen(second)
        result = aggregator.finalize(CaptureStatus.COMPLETED)
        self.assertEqual(result.document_build_status.value, "partial")
        self.assertIn("新增项目经历", result.document_text)
        self.assertEqual(aggregator.finalize(CaptureStatus.COMPLETED), result)
        with self.assertRaises(CandidateAggregationFinalizeConflictError):
            aggregator.finalize(CaptureStatus.ABORTED)
        with self.assertRaises(Exception):
            aggregator.add_screen(first)

    def test_aggregator_preserves_uncertain_for_out_of_order_and_empty_completed(self):
        screen = self.make_screen(("一段可靠新内容" * 4,), screen_id="screen-late")
        screen = replace(screen, screen_index=2, segments=tuple(
            replace(item, screen_index=2, segment_id="screen-late:line:{0}".format(item.order))
            for item in screen.segments))
        aggregator = CandidateDocumentAggregator("run-1", "candidate-1")
        added = aggregator.add_screen(screen)
        self.assertEqual(added.status.value, "partial")
        result = aggregator.finalize(CaptureStatus.INTERRUPTED)
        self.assertEqual(result.document_build_status.value, "partial")
        self.assertEqual(len(result.document_segments), 1)


class AggregationBenchmarkContractTests(unittest.TestCase):
    def test_inclusive_p95_has_a_frozen_known_vector(self):
        from tests import benchmark_r05_aggregation as benchmark

        self.assertEqual(benchmark.percentile_95(tuple(range(1, 26))), 23.8)
        with self.assertRaises(ValueError):
            benchmark.percentile_95(())
        with self.assertRaises(ValueError):
            benchmark.percentile_95((1.0,))

    def test_measurement_counts_calls_and_restores_gc_state(self):
        from tests import benchmark_r05_aggregation as benchmark

        calls = []
        before = gc.isenabled()

        def operation():
            calls.append(gc.isenabled())
            return ("stable",)

        measured = benchmark._measure(operation, runs=2)
        self.assertEqual(
            len(calls),
            benchmark.WARMUP_RUNS + benchmark.REFERENCE_RUNS + 2 + 1,
        )
        self.assertEqual(gc.isenabled(), before)
        self.assertTrue(measured["deterministic"])
        self.assertTrue(all(value is False for value in calls[:-1]))

    def test_contract_unique_fixture_and_record_comparison_are_fair(self):
        from tests import benchmark_r05_aggregation as benchmark

        records = benchmark._make_records(benchmark._unique_series(64))
        before = copy.deepcopy(records)
        scenario = benchmark.Scenario(
            "unit_unique",
            records,
            contract="all_unique",
        )
        diagnostic = benchmark._diagnose(scenario)
        self.assertTrue(diagnostic["contract_ok"])
        self.assertEqual(diagnostic["input_screen_segment_count"], 8 * 64)
        self.assertEqual(diagnostic["document_segment_count"], 8 * 64)
        self.assertEqual(diagnostic["matched_segment_count"], 0)
        self.assertEqual(diagnostic["uncertain_segment_count"], 0)
        self.assertTrue(benchmark._record_semantics_equal(records))
        self.assertEqual(benchmark._record_run(records), benchmark._record_run(records))
        self.assertEqual(records, before)


if __name__ == "__main__":
    unittest.main()
