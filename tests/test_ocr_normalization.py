import copy
from dataclasses import replace
import random
import statistics
import string
import time
import tracemalloc
import unicodedata
import unittest
from unittest.mock import patch

import numpy as np

import ocr_normalization
from ocr_detector import sha256_normalized_text
from ocr_normalization import (
    BBOX_EMPTY,
    BBOX_INVALID_FLAT_COUNT,
    BBOX_INVALID_NUMBER,
    BBOX_INVALID_POINT,
    BBOX_INVALID_TYPE,
    BBOX_MISSING,
    BBOX_MIXED_FORMAT,
    BBOX_NEGATIVE_SIZE,
    BBOX_NON_FINITE,
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NormalizationBox,
    OcrGeometryError,
    OcrNormalizationConfig,
    adapt_bbox_geometry,
    build_reading_order,
    canonical_normalization_config,
    normalization_config_digest,
    normalization_config_from_snapshot,
)
from ocr_records import (
    CaptureType,
    LEGACY_STORAGE_SCHEMA_VERSION,
    OcrBox,
    OcrScreenRecord,
    ProcessingStatus,
    R04_STORAGE_SCHEMA_VERSION,
    STORAGE_SCHEMA_VERSION,
)


class OcrGeometryAdapterTests(unittest.TestCase):
    def test_flat_ltrb_derives_all_geometry_without_changing_input(self):
        bbox = [10, 20, 50, 60]
        original = copy.deepcopy(bbox)

        geometry = adapt_bbox_geometry(bbox)

        self.assertEqual(geometry.source_shape, "ltrb")
        self.assertEqual(
            (
                geometry.x_min,
                geometry.y_min,
                geometry.x_max,
                geometry.y_max,
                geometry.center_x,
                geometry.center_y,
                geometry.width,
                geometry.height,
            ),
            (10.0, 20.0, 50.0, 60.0, 30.0, 40.0, 40.0, 40.0),
        )
        self.assertEqual(bbox, original)

    def test_one_three_rotated_four_and_many_point_polygons_are_lossless(self):
        cases = (
            ("one", [[7, 9]], (7.0, 9.0, 7.0, 9.0)),
            ("three", [[0, 5], [10, 0], [12, 8]], (0.0, 0.0, 12.0, 8.0)),
            (
                "rotated-four",
                [[10, 0], [20, 5], [15, 15], [5, 10]],
                (5.0, 0.0, 20.0, 15.0),
            ),
            (
                "five",
                [[0, 3], [2, 0], [8, 1], [10, 7], [3, 9]],
                (0.0, 0.0, 10.0, 9.0),
            ),
        )
        for name, values, expected in cases:
            for bbox in (copy.deepcopy(values), np.asarray(values, dtype=float)):
                with self.subTest(name=name, bbox_type=type(bbox).__name__):
                    original = copy.deepcopy(bbox)
                    geometry = adapt_bbox_geometry(bbox)
                    self.assertEqual(geometry.source_shape, "polygon")
                    self.assertEqual(
                        (
                            geometry.x_min,
                            geometry.y_min,
                            geometry.x_max,
                            geometry.y_max,
                        ),
                        expected,
                    )
                    if isinstance(bbox, np.ndarray):
                        np.testing.assert_array_equal(bbox, original)
                    else:
                        self.assertEqual(bbox, original)

    def test_generator_polygon_is_supported_without_rewriting_values(self):
        values = ((0, 1), (4, 0), (6, 5), (2, 7), (1, 3))

        geometry = adapt_bbox_geometry((point for point in values))

        self.assertEqual(
            (geometry.x_min, geometry.y_min, geometry.x_max, geometry.y_max),
            (0.0, 0.0, 6.0, 7.0),
        )
        self.assertEqual(values, ((0, 1), (4, 0), (6, 5), (2, 7), (1, 3)))

    def test_zero_size_is_valid_and_uses_effective_height_one(self):
        geometry = adapt_bbox_geometry((3, 4, 3, 4))

        self.assertEqual(geometry.width, 0.0)
        self.assertEqual(geometry.height, 0.0)
        self.assertEqual(geometry.effective_height, 1.0)

    def test_invalid_bbox_shapes_have_sanitized_error_codes(self):
        cases = (
            (None, BBOX_MISSING),
            ([], BBOX_EMPTY),
            ("not-a-box PRIVATE_TEXT", BBOX_INVALID_TYPE),
            ([0, 1, 2], BBOX_INVALID_FLAT_COUNT),
            ([[0]], BBOX_INVALID_POINT),
            ([[0, 0], [1]], BBOX_INVALID_POINT),
            ([[0, 0, 1], [1, 0], [1, 1], [0, 1]], BBOX_INVALID_POINT),
            ([0, [1, 0], 2, 3], BBOX_MIXED_FORMAT),
            ([0, 0, "2", 3], BBOX_INVALID_NUMBER),
            ([0, 0, float("nan"), 3], BBOX_NON_FINITE),
            ([0, 0, float("inf"), 3], BBOX_NON_FINITE),
            ([5, 0, 4, 3], BBOX_NEGATIVE_SIZE),
            ([0, 5, 4, 3], BBOX_NEGATIVE_SIZE),
        )

        for bbox, code in cases:
            with self.subTest(code=code):
                with self.assertRaises(OcrGeometryError) as caught:
                    adapt_bbox_geometry(bbox)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)
                self.assertNotIn("PRIVATE_TEXT", str(caught.exception))


class OcrReadingOrderTests(unittest.TestCase):
    config = DEFAULT_OCR_NORMALIZATION_CONFIG

    @staticmethod
    def box(box_id, text, bbox, original_index):
        return NormalizationBox(box_id, text, bbox, original_index)

    @staticmethod
    def rect(left, top, right, bottom):
        return (left, top, right, bottom)

    def result(self, boxes, config=None):
        return build_reading_order(
            boxes,
            config=config or self.config,
        )

    def test_empty_list_returns_a_complete_empty_result(self):
        result = self.result([])

        self.assertEqual(result.ordered_box_ids, ())
        self.assertEqual(result.line_groups, ())
        self.assertEqual(result.line_mapping, ())
        self.assertEqual(result.excluded_empty_box_ids, ())
        self.assertEqual(result.normalization_warnings, ())
        self.assertEqual(result.box_geometries, ())
        self.assertIsNone(result.median_box_height)
        self.assertIsNone(result.base_line_tolerance)

    def test_single_box_has_one_line_and_mapping(self):
        result = self.result([
            self.box("only", "保留 UI 标题", self.rect(2, 3, 22, 13), 0)
        ])

        self.assertEqual(result.ordered_box_ids, ("only",))
        self.assertEqual(result.line_groups[0].box_ids, ("only",))
        self.assertEqual(result.line_index_by_box_id, {"only": 0})
        self.assertEqual(result.median_box_height, 10.0)
        self.assertEqual(result.base_line_tolerance, 4.5)

    def test_same_line_boxes_sort_left_to_right(self):
        boxes = [
            self.box("right", "right", self.rect(80, 2, 100, 12), 0),
            self.box("middle", "middle", self.rect(40, 0, 70, 10), 1),
            self.box("left", "left", self.rect(0, 1, 30, 11), 2),
        ]

        result = self.result(boxes)

        self.assertEqual(result.ordered_box_ids, ("left", "middle", "right"))
        self.assertEqual(
            result.line_groups[0].box_ids,
            ("left", "middle", "right"),
        )

    def test_adjacent_lines_sort_top_to_bottom(self):
        boxes = [
            self.box("lower-left", "L2", self.rect(0, 20, 20, 30), 0),
            self.box("upper-right", "R1", self.rect(30, 0, 50, 10), 1),
            self.box("upper-left", "L1", self.rect(0, 0, 20, 10), 2),
        ]

        result = self.result(boxes)

        self.assertEqual(
            result.ordered_box_ids,
            ("upper-left", "upper-right", "lower-left"),
        )
        self.assertEqual(
            tuple(group.box_ids for group in result.line_groups),
            (("upper-left", "upper-right"), ("lower-left",)),
        )

    def test_different_box_heights_use_screen_median_and_dynamic_tolerance(self):
        boxes = [
            self.box("tall", "A", self.rect(0, 0, 20, 40), 0),
            self.box("short", "B", self.rect(30, 18, 50, 28), 1),
            self.box("lower", "C", self.rect(0, 60, 20, 70), 2),
        ]

        result = self.result(boxes)

        self.assertEqual(result.median_box_height, 10.0)
        self.assertEqual(
            tuple(group.box_ids for group in result.line_groups),
            (("tall", "short"), ("lower",)),
        )

    def test_median_height_handles_even_odd_and_degenerate_boxes(self):
        odd = self.result([
            self.box("a", "a", self.rect(0, 0, 1, 10), 0),
            self.box("b", "b", self.rect(0, 20, 1, 40), 1),
            self.box("c", "c", self.rect(0, 50, 1, 80), 2),
        ])
        even = self.result([
            self.box("a", "a", self.rect(0, 0, 1, 10), 0),
            self.box("b", "b", self.rect(0, 20, 1, 40), 1),
        ])
        degenerate = self.result([
            self.box("zero", "z", self.rect(0, 0, 0, 0), 0),
        ])

        self.assertEqual(odd.median_box_height, 20.0)
        self.assertEqual(even.median_box_height, 15.0)
        self.assertEqual(degenerate.median_box_height, 1.0)

    def test_line_center_tolerance_includes_the_frozen_boundary(self):
        def line_count(distance):
            return len(self.result([
                self.box("first", "A", self.rect(0, 0, 10, 10), 0),
                self.box(
                    "second",
                    "B",
                    self.rect(20, distance, 30, distance + 10),
                    1,
                ),
            ]).line_groups)

        self.assertEqual(line_count(4.999), 1)
        self.assertEqual(line_count(5.0), 1)
        self.assertEqual(line_count(5.001), 2)

    def test_line_overlap_threshold_includes_the_frozen_boundary(self):
        config = OcrNormalizationConfig(
            line_tolerance_height_ratio=0.0,
            line_tolerance_min_px=0.0,
            line_tolerance_max_px=0.0,
            line_pair_height_ratio=0.0,
            same_line_vertical_overlap_ratio=0.5,
        )

        def line_count(distance):
            return len(self.result([
                self.box("first", "A", self.rect(0, 0, 10, 10), 0),
                self.box(
                    "second",
                    "B",
                    self.rect(20, distance, 30, distance + 10),
                    1,
                ),
            ], config=config).line_groups)

        self.assertEqual(line_count(4.999), 1)
        self.assertEqual(line_count(5.0), 1)
        self.assertEqual(line_count(5.001), 2)

    def test_center_or_overlap_independently_makes_a_line_candidate(self):
        center_only = OcrNormalizationConfig(
            same_line_vertical_overlap_ratio=1.0,
        )
        overlap_only = OcrNormalizationConfig(
            line_tolerance_height_ratio=0.0,
            line_tolerance_min_px=0.0,
            line_tolerance_max_px=0.0,
            line_pair_height_ratio=0.0,
            same_line_vertical_overlap_ratio=0.5,
        )
        boxes = [
            self.box("first", "A", self.rect(0, 0, 10, 10), 0),
            self.box("second", "B", self.rect(20, 5, 30, 15), 1),
        ]

        self.assertEqual(len(self.result(boxes, config=center_only).line_groups), 1)
        self.assertEqual(len(self.result(boxes, config=overlap_only).line_groups), 1)

    def test_multiple_line_candidates_use_the_frozen_tie_breaker(self):
        projected = (
            ocr_normalization._PreparedBox(
                "upper",
                "A",
                0,
                adapt_bbox_geometry(self.rect(0, -5, 10, 5)),
            ),
            ocr_normalization._PreparedBox(
                "lower",
                "B",
                1,
                adapt_bbox_geometry(self.rect(0, 5, 10, 15)),
            ),
            ocr_normalization._PreparedBox(
                "candidate",
                "C",
                2,
                adapt_bbox_geometry(self.rect(20, 0, 30, 10)),
            ),
        )
        with patch.object(
            ocr_normalization,
            "_valid_box_sort_key",
            side_effect=lambda box: (box.original_index,),
        ):
            groups = ocr_normalization._group_valid_boxes(
                projected,
                5.0,
                self.config,
            )

        self.assertEqual(
            tuple(tuple(box.box_id for box in group) for group in groups),
            (("upper", "candidate"), ("lower",)),
        )

    def test_complete_geometry_ties_use_original_index_then_box_id(self):
        geometry = self.rect(0, 0, 10, 10)
        boxes = [
            self.box("z", "z", geometry, 2),
            self.box("b", "b", geometry, 1),
            self.box("a", "a", geometry, 1),
        ]

        result = self.result(boxes)

        self.assertEqual(result.ordered_box_ids, ("a", "b", "z"))

    def test_shuffled_input_is_stable_when_original_indexes_are_stable(self):
        boxes = [
            self.box("top-left", "A", self.rect(0, 0, 10, 10), 0),
            self.box("top-right", "B", self.rect(20, 1, 30, 11), 1),
            self.box("bottom", "C", self.rect(0, 30, 10, 40), 2),
            self.box("invalid", "D", None, 3),
            self.box("empty", "  \t", self.rect(50, 0, 60, 10), 4),
        ]
        expected = self.result(boxes)

        for seed in range(20):
            shuffled = list(boxes)
            random.Random(seed).shuffle(shuffled)
            with self.subTest(seed=seed):
                self.assertEqual(self.result(shuffled), expected)

    def test_invalid_geometry_with_text_is_retained_as_fallback_line(self):
        boxes = [
            self.box("invalid-first", "必须保留", None, 0),
            self.box("valid", "正常", self.rect(0, 0, 10, 10), 1),
            self.box("invalid-second", "也保留", [5, 0, 4, 1], 2),
        ]

        result = self.result(boxes)

        self.assertEqual(
            result.ordered_box_ids,
            ("valid", "invalid-first", "invalid-second"),
        )
        self.assertEqual(
            tuple(group.has_valid_geometry for group in result.line_groups),
            (True, False, False),
        )
        self.assertEqual(
            tuple(
                (warning.box_id, warning.code)
                for warning in result.normalization_warnings
            ),
            (
                ("invalid-first", BBOX_MISSING),
                ("invalid-second", BBOX_NEGATIVE_SIZE),
            ),
        )
        self.assertEqual(
            set(result.line_index_by_box_id),
            {"valid", "invalid-first", "invalid-second"},
        )

    def test_every_required_invalid_geometry_case_retains_nonempty_text(self):
        invalid_values = (
            ("missing", None, BBOX_MISSING),
            ("nan", [0, 0, float("nan"), 3], BBOX_NON_FINITE),
            ("negative", [5, 0, 4, 3], BBOX_NEGATIVE_SIZE),
            ("missing-dimension", [[0, 0], [1]], BBOX_INVALID_POINT),
            ("mixed", [0, [1, 0], 2, 3], BBOX_MIXED_FORMAT),
        )
        boxes = [
            self.box(box_id, "有效文字", bbox, index)
            for index, (box_id, bbox, _code) in enumerate(invalid_values)
        ]

        result = self.result(boxes)

        self.assertEqual(
            result.ordered_box_ids,
            tuple(box_id for box_id, _bbox, _code in invalid_values),
        )
        self.assertEqual(len(result.line_groups), len(invalid_values))
        self.assertTrue(
            all(not group.has_valid_geometry for group in result.line_groups)
        )
        self.assertEqual(
            tuple(
                (warning.box_id, warning.code)
                for warning in result.normalization_warnings
            ),
            tuple(
                (box_id, code) for box_id, _bbox, code in invalid_values
            ),
        )

    def test_current_stage0_ocr_box_is_consumed_without_mutation(self):
        raw_box = OcrBox(
            box_id="stage0-box",
            raw_text="阶段 0 原始文字",
            confidence=0.97,
            bbox=((1, 2), (21, 2), (21, 12), (1, 12)),
            original_index=0,
            screen_index=1,
        )

        result = self.result([raw_box])

        self.assertEqual(result.ordered_box_ids, ("stage0-box",))
        self.assertEqual(
            result.box_geometries[0].geometry.source_shape,
            "polygon",
        )
        self.assertEqual(
            raw_box.bbox,
            ((1, 2), (21, 2), (21, 12), (1, 12)),
        )
        self.assertEqual(raw_box.raw_text, "阶段 0 原始文字")

    def test_empty_text_is_excluded_but_geometry_and_raw_box_are_retained(self):
        boxes = [
            self.box("empty", " \t\r\n", self.rect(0, 0, 10, 10), 0),
            self.box("text", "UI 按钮", self.rect(20, 0, 30, 10), 1),
        ]
        original = copy.deepcopy(boxes)

        result = self.result(boxes)

        self.assertEqual(result.excluded_empty_box_ids, ("empty",))
        self.assertEqual(result.ordered_box_ids, ("text",))
        self.assertEqual(
            tuple(entry.box_id for entry in result.box_geometries),
            ("empty", "text"),
        )
        self.assertEqual(boxes, original)

    def test_raw_objects_text_bbox_count_and_order_are_never_modified(self):
        boxes = [
            self.box(
                "polygon",
                "  C++ 原始文字  ",
                [[0, 0], [20, 0], [20, 10], [0, 10]],
                0,
            ),
            self.box("flat", "UI 标题", [30, 0, 50, 10], 1),
            self.box("bad", "坐标异常仍保留", [4, 0, 3, 1], 2),
        ]
        original = copy.deepcopy(boxes)

        self.result(boxes)

        self.assertEqual(len(boxes), len(original))
        self.assertEqual(boxes, original)
        self.assertEqual(
            [box.raw_text for box in boxes],
            [box.raw_text for box in original],
        )

    def test_repeated_execution_is_idempotent(self):
        boxes = [
            self.box("a", "A", self.rect(0, 0, 10, 10), 0),
            self.box("b", "B", self.rect(20, 0, 30, 10), 1),
            self.box("bad", "C", None, 2),
        ]

        first = self.result(boxes)
        second = self.result(boxes)
        third = self.result(tuple(boxes))

        self.assertEqual(first, second)
        self.assertEqual(second, third)

    def test_config_thresholds_are_centralized_and_validated(self):
        config = OcrNormalizationConfig(
            line_tolerance_height_ratio=0.4,
            line_tolerance_min_px=3.0,
            line_tolerance_max_px=12.0,
            line_pair_height_ratio=0.6,
            same_line_vertical_overlap_ratio=0.7,
        )
        result = self.result([
            self.box("a", "A", self.rect(0, 0, 10, 20), 0),
        ], config=config)

        self.assertEqual(result.base_line_tolerance, 8.0)
        self.assertEqual(config.compact_join_gap_height_ratio, 0.25)
        self.assertEqual(config.symbol_join_gap_height_ratio, 0.75)
        invalid_configs = (
            {"line_tolerance_height_ratio": -0.1},
            {"line_tolerance_min_px": 5.0, "line_tolerance_max_px": 4.0},
            {"line_pair_height_ratio": -0.1},
            {"same_line_vertical_overlap_ratio": 1.1},
            {"compact_join_gap_height_ratio": -0.1},
            {"symbol_join_gap_height_ratio": -0.1},
            {"line_tolerance_min_px": float("nan")},
        )
        for values in invalid_configs:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    OcrNormalizationConfig(**values)

    def test_module_has_no_platform_or_side_effect_dependencies(self):
        forbidden_globals = {
            "mss",
            "os",
            "platform",
            "pyautogui",
            "subprocess",
            "sys",
            "time",
        }

        self.assertTrue(
            forbidden_globals.isdisjoint(ocr_normalization.__dict__)
        )

    def test_duplicate_box_ids_are_rejected_without_processing_text(self):
        boxes = [
            self.box("same", "PRIVATE_ONE", self.rect(0, 0, 10, 10), 0),
            self.box("same", "PRIVATE_TWO", self.rect(20, 0, 30, 10), 1),
        ]

        with self.assertRaisesRegex(
            ValueError,
            "box_id values must be unique",
        ) as caught:
            self.result(boxes)

        self.assertNotIn("PRIVATE_ONE", str(caught.exception))
        self.assertNotIn("PRIVATE_TWO", str(caught.exception))


class OcrTextNormalizationTests(unittest.TestCase):
    @staticmethod
    def box(box_id, text, bbox, original_index):
        return NormalizationBox(box_id, text, bbox, original_index)

    @staticmethod
    def rect(left, top, right, bottom):
        return (left, top, right, bottom)

    def normalize(self, boxes, **kwargs):
        return ocr_normalization.normalize_ocr_text(boxes, **kwargs)

    def test_engine_screen_raw_text_is_retained_character_for_character(self):
        engine_text = "虚构标题\r\n\t原始段落\x00"
        boxes = [self.box("a", "虚构标题", self.rect(0, 0, 40, 10), 0)]

        result = self.normalize(boxes, engine_raw_text=engine_text)

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_COMPLETED)
        self.assertIs(result.raw_text, engine_text)
        self.assertEqual(
            result.raw_text_source,
            ocr_normalization.RAW_TEXT_SOURCE_ENGINE_SCREEN,
        )
        self.assertEqual(result.raw_text_length, len(engine_text))
        self.assertEqual(result.normalized_text, "虚构标题")

    def test_box_only_raw_text_is_original_index_projection_with_inserted_lf(self):
        boxes = [
            self.box("third", "三", self.rect(0, 40, 10, 50), 2),
            self.box("first", "一\r\n原样", self.rect(0, 0, 20, 10), 0),
            self.box("second", "", self.rect(0, 20, 10, 30), 1),
        ]

        result = self.normalize(boxes)

        self.assertEqual(result.raw_text, "一\r\n原样\n\n三")
        self.assertEqual(
            result.raw_text_source,
            ocr_normalization.RAW_TEXT_SOURCE_DERIVED_BOXES,
        )
        self.assertEqual(result.raw_text_length, len("一\r\n原样\n\n三"))
        self.assertEqual(result.excluded_empty_box_ids, ("second",))

    def test_empty_box_list_has_explicit_empty_completed_result(self):
        result = self.normalize([])

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_COMPLETED)
        self.assertEqual(result.raw_text, "")
        self.assertEqual(
            result.raw_text_source,
            ocr_normalization.RAW_TEXT_SOURCE_DERIVED_BOXES,
        )
        self.assertEqual(result.raw_text_length, 0)
        self.assertEqual(result.normalized_text, "")
        self.assertEqual(result.normalized_text_length, 0)
        self.assertEqual(result.ordered_box_ids, ())
        self.assertEqual(result.line_mapping, ())

    def test_whitespace_collapses_but_nonwhitespace_controls_are_retained(self):
        raw = "  Alpha\r\n\tBeta\rGamma\n\u3000Delta  \x00\u200b\ufeff "

        normalized = ocr_normalization.normalize_box_text(raw)

        self.assertEqual(normalized, "Alpha Beta Gamma Delta \x00\u200b\ufeff")
        self.assertEqual(
            ocr_normalization.normalize_box_text(normalized),
            normalized,
        )

    def test_readable_normalization_preserves_fullwidth_nonwhitespace(self):
        cases = {
            "ＡＢＣ１２３": ("ＡＢＣ１２３", "abc123"),
            "Ｃ＋＋": ("Ｃ＋＋", "c++"),
            "．ＮＥＴ": ("．ＮＥＴ", ".net"),
            "（Ａ／Ｂ－Ｃ＃＿）": ("（Ａ／Ｂ－Ｃ＃＿）", "(a/b-c#_)"),
            "中文ＡＢＣ１２３，＋／": (
                "中文ＡＢＣ１２３，＋／",
                "中文abc123,+/",
            ),
            "　ＡＢＣ　　１２３　": ("ＡＢＣ １２３", "abc123"),
        }

        for raw, (readable, comparison) in cases.items():
            with self.subTest(raw=raw):
                normalized = ocr_normalization.normalize_box_text(raw)

                self.assertEqual(normalized, readable)
                self.assertEqual(
                    ocr_normalization.normalize_box_text(normalized),
                    normalized,
                )
                self.assertEqual(
                    ocr_normalization.build_comparison_text(normalized),
                    comparison,
                )
                self.assertEqual(
                    ocr_normalization.build_comparison_text(comparison),
                    comparison,
                )

    def test_visual_segment_uses_readable_width_contract(self):
        raw_text = "项目 Ｃ＋＋／．ＮＥＴ"
        boxes = [
            self.box("wide", raw_text, self.rect(0, 0, 120, 10), 0),
        ]
        original = copy.deepcopy(boxes)

        result = self.normalize(boxes)

        self.assertEqual(result.raw_text, raw_text)
        self.assertEqual(result.normalized_text, raw_text)
        self.assertEqual(result.comparison_text, "项目c++/.net")
        self.assertEqual(result.normalized_lines[0].normalized_text, raw_text)
        self.assertEqual(result.normalized_lines[0].box_ids, ("wide",))
        self.assertEqual(boxes, original)

    def test_canonical_unicode_and_abnormal_unicode_are_retained_safely(self):
        raw = "Cafe\u0301 \ud800 👩\u200d💻"

        normalized = ocr_normalization.normalize_box_text(raw)

        self.assertEqual(normalized, "Café \ud800 👩\u200d💻")

    def test_visual_lines_drive_output_and_metadata(self):
        boxes = [
            self.box("line2", "模块标题", self.rect(0, 20, 40, 30), 0),
            self.box("en", "Python", self.rect(35, 0, 70, 10), 1),
            self.box("zh", "熟悉", self.rect(0, 0, 20, 10), 2),
        ]

        result = self.normalize(boxes)

        self.assertEqual(result.normalized_text, "熟悉 Python\n模块标题")
        self.assertEqual(result.normalized_text_length, len(result.normalized_text))
        self.assertEqual(result.effective_box_ids, ("zh", "en", "line2"))
        self.assertEqual(result.ordered_box_ids, ("zh", "en", "line2"))
        self.assertEqual(
            tuple((item.box_id, item.line_index) for item in result.line_mapping),
            (("zh", 0), ("en", 0), ("line2", 1)),
        )
        self.assertEqual(
            tuple(line.normalized_text for line in result.normalized_lines),
            ("熟悉 Python", "模块标题"),
        )

    def test_chinese_fragments_join_without_forced_spaces(self):
        boxes = [
            self.box("a", "虚构", self.rect(0, 0, 20, 10), 0),
            self.box("b", "经历", self.rect(30, 0, 50, 10), 1),
        ]

        result = self.normalize(boxes)

        self.assertEqual(result.normalized_text, "虚构经历")

    def test_english_words_and_number_units_do_not_accidentally_stick(self):
        boxes = [
            self.box("english1", "Project ", self.rect(0, 0, 40, 10), 0),
            self.box("english2", " Atlas", self.rect(50, 0, 80, 10), 1),
            self.box("number", "20", self.rect(0, 20, 20, 30), 2),
            self.box("unit", "GB", self.rect(25, 20, 45, 30), 3),
        ]

        result = self.normalize(boxes)

        self.assertEqual(result.normalized_text, "Project Atlas\n20 GB")

    def test_shuffled_box_input_keeps_same_normalized_output(self):
        boxes = [
            self.box("right", "World", self.rect(50, 0, 80, 10), 2),
            self.box("lower", "第二行", self.rect(0, 20, 30, 30), 0),
            self.box("left", "Hello", self.rect(0, 0, 35, 10), 1),
        ]
        expected = self.normalize(boxes)

        for seed in range(10):
            shuffled = list(boxes)
            random.Random(seed).shuffle(shuffled)
            with self.subTest(seed=seed):
                self.assertEqual(self.normalize(shuffled), expected)

    def test_punctuation_spacing_has_no_obvious_extra_spaces(self):
        boxes = [
            self.box("zh", "候选模块", self.rect(0, 0, 40, 10), 0),
            self.box("colon", "：", self.rect(42, 0, 47, 10), 1),
            self.box("button", "按钮", self.rect(49, 0, 69, 10), 2),
            self.box("word1", "Python", self.rect(0, 20, 35, 30), 3),
            self.box("comma", "，", self.rect(37, 20, 42, 30), 4),
            self.box("word2", "SQL", self.rect(48, 20, 68, 30), 5),
            self.box("open", "（", self.rect(0, 40, 5, 50), 6),
            self.box("demo", "Demo", self.rect(7, 40, 30, 50), 7),
            self.box("close", "）", self.rect(32, 40, 37, 50), 8),
        ]

        result = self.normalize(boxes)

        self.assertEqual(
            result.normalized_text,
            "候选模块：按钮\nPython， SQL\n（Demo）",
        )
        self.assertEqual(
            result.comparison_text,
            "候选模块:按钮python,sql(demo)",
        )

    def test_protected_symbol_tokens_dates_and_versions_remain_readable(self):
        boxes = [
            self.box("c", "C", self.rect(0, 0, 10, 10), 0),
            self.box("plusplus", "++", self.rect(12, 0, 22, 10), 1),
            self.box("c2", "C", self.rect(0, 20, 10, 30), 2),
            self.box("sharp", "#", self.rect(12, 20, 17, 30), 3),
            self.box("slg", "SLG", self.rect(0, 40, 20, 50), 4),
            self.box("plus", "+", self.rect(22, 40, 27, 50), 5),
            self.box("x", "X", self.rect(29, 40, 39, 50), 6),
            self.box("zero", "0", self.rect(0, 60, 10, 70), 7),
            self.box("dash", "-", self.rect(12, 60, 17, 70), 8),
            self.box("one", "1", self.rect(19, 60, 29, 70), 9),
            self.box("two_d", "2D", self.rect(0, 80, 15, 90), 10),
            self.box("slash", "/", self.rect(17, 80, 22, 90), 11),
            self.box("three_d", "3D", self.rect(24, 80, 39, 90), 12),
            self.box("ue", "UE", self.rect(0, 100, 15, 110), 13),
            self.box("five", "5", self.rect(17, 100, 27, 110), 14),
            self.box(
                "fixed",
                ".NET Unity 2022.3 iOS 3A 2026-07-30 v1.2.3",
                self.rect(0, 120, 220, 130),
                15,
            ),
        ]

        result = self.normalize(boxes)

        self.assertEqual(
            result.normalized_text,
            "C++\nC#\nSLG+X\n0-1\n2D/3D\nUE5\n"
            ".NET Unity 2022.3 iOS 3A 2026-07-30 v1.2.3",
        )

    def test_inline_gap_ratio_uses_screen_median_not_local_box_heights(self):
        short_left = adapt_bbox_geometry(self.rect(0, 0, 10, 2))
        short_right = adapt_bbox_geometry(self.rect(14, 0, 24, 2))
        tall_left = adapt_bbox_geometry(self.rect(0, 0, 10, 20))
        tall_right = adapt_bbox_geometry(self.rect(14, 0, 24, 20))

        short_result = ocr_normalization.choose_inline_separator(
            "UE",
            "5",
            left_geometry=short_left,
            right_geometry=short_right,
            median_height=20.0,
            config=DEFAULT_OCR_NORMALIZATION_CONFIG,
        )
        tall_result = ocr_normalization.choose_inline_separator(
            "UE",
            "5",
            left_geometry=tall_left,
            right_geometry=tall_right,
            median_height=20.0,
            config=DEFAULT_OCR_NORMALIZATION_CONFIG,
        )

        self.assertEqual(short_result, "")
        self.assertEqual(tall_result, "")

    def test_mixed_font_screen_keeps_compact_symbols_spaces_and_units(self):
        boxes = [
            self.box("dot", ".", self.rect(0, 0, 4, 20), 0),
            self.box("net", "NET", self.rect(6, 0, 36, 20), 1),
            self.box("unity", "Unity", self.rect(0, 30, 50, 50), 2),
            self.box("version", "2022.3", self.rect(60, 30, 120, 50), 3),
            self.box("number", "20", self.rect(0, 60, 20, 80), 4),
            self.box("unit", "GB", self.rect(30, 60, 50, 80), 5),
            self.box(
                "fixed",
                "C++ C# SLG+X 0-1 2D/3D UE5 iOS 3A "
                "2026/07/30 v1.2.3 50% 36.5℃",
                self.rect(0, 90, 350, 110),
                6,
            ),
        ]

        result = self.normalize(boxes)

        self.assertEqual(
            result.normalized_text,
            ".NET\nUnity 2022.3\n20 GB\n"
            "C++ C# SLG+X 0-1 2D/3D UE5 iOS 3A "
            "2026/07/30 v1.2.3 50% 36.5℃",
        )

    def test_ui_labels_titles_buttons_and_navigation_are_all_retained(self):
        boxes = [
            self.box("title", "候选人中心", self.rect(0, 0, 50, 10), 0),
            self.box("tab", "沟通记录", self.rect(0, 20, 40, 30), 1),
            self.box("button", "下一位", self.rect(0, 40, 30, 50), 2),
            self.box("nav", "内部导航", self.rect(0, 60, 40, 70), 3),
        ]

        result = self.normalize(boxes)

        self.assertEqual(
            result.normalized_text,
            "候选人中心\n沟通记录\n下一位\n内部导航",
        )

    def test_text_is_not_corrected_rewritten_or_semantically_replaced(self):
        boxes = [
            self.box("typo", "Pyhton", self.rect(0, 0, 40, 10), 0),
            self.box("literal", "AI != ML", self.rect(0, 20, 50, 30), 1),
        ]

        result = self.normalize(boxes)

        self.assertEqual(result.normalized_text, "Pyhton\nAI != ML")

    def test_empty_boxes_stay_in_evidence_but_not_normalized_text(self):
        boxes = [
            self.box("spaces", " \t\u3000", self.rect(0, 0, 10, 10), 0),
            self.box("linebreaks", "\r\n\t", self.rect(0, 20, 10, 30), 1),
        ]

        result = self.normalize(boxes)

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_COMPLETED)
        self.assertEqual(result.raw_text, " \t\u3000\n\r\n\t")
        self.assertEqual(result.normalized_text, "")
        self.assertEqual(result.normalized_text_length, 0)
        self.assertEqual(result.effective_box_ids, ())
        self.assertEqual(
            result.excluded_empty_box_ids,
            ("spaces", "linebreaks"),
        )
        self.assertEqual(result.normalization_warnings, ())


class OcrComparisonTextTests(unittest.TestCase):
    @staticmethod
    def box(box_id, text, bbox, original_index):
        return NormalizationBox(box_id, text, bbox, original_index)

    @staticmethod
    def rect(left, top, right, bottom):
        return (left, top, right, bottom)

    def normalize(self, boxes, **kwargs):
        return ocr_normalization.normalize_ocr_text(boxes, **kwargs)

    def test_protection_and_restoration_are_lossless_and_explicit(self):
        value = (
            "C++ C# .NET SLG+X 0-1 2D/3D Unity 2022.3 UE5 iOS 3A "
            "2026-07-30 v1.2.3 星河_Project-A1 +++"
        )

        parts = ocr_normalization.protect_comparison_tokens(value)

        self.assertEqual(
            ocr_normalization.restore_comparison_tokens(parts),
            value,
        )
        self.assertEqual(
            tuple(
                part.text for part in parts if part.is_protected_token
            ),
            (
                "C++",
                "C#",
                ".NET",
                "SLG+X",
                "0-1",
                "2D/3D",
                "Unity",
                "2022.3",
                "UE5",
                "iOS",
                "3A",
                "2026-07-30",
                "v1.2.3",
                "星河_Project-A1",
            ),
        )
        self.assertTrue(any(
            "+++" in part.text and not part.is_protected_token
            for part in parts
        ))

    def test_every_required_protected_example_keeps_symbol_structure(self):
        cases = {
            " Ab C ": "abc",
            "C++": "c++",
            "C#": "c#",
            ".NET": ".net",
            "SLG+X": "slg+x",
            "0-1": "0-1",
            "2D/3D": "2d/3d",
            "Unity 2022.3": "unity2022.3",
            "UE5": "ue5",
            "iOS": "ios",
            "3A": "3a",
            "2026-07-30": "2026-07-30",
            "2026/07/30": "2026/07/30",
            "2026": "2026",
            "v1.2.3": "v1.2.3",
            "A_B": "a_b",
            "星河_Project-A1": "星河_project-a1",
            "Project星河_2": "project星河_2",
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(
                    ocr_normalization.build_comparison_text(value),
                    expected,
                )

    def test_case_whitespace_newlines_and_width_variants_are_equivalent(self):
        variants = (
            "Unity 2022.3\nC++ / UE5",
            "UNITY\t２０２２．３\r\nＣ＋＋　／　ＵＥ５",
            " unity\r2022.3  c++/ue5 ",
        )

        comparison_values = {
            ocr_normalization.build_comparison_text(value)
            for value in variants
        }

        self.assertEqual(comparison_values, {"unity2022.3c++/ue5"})

    def test_punctuation_uses_nfkc_without_an_extra_mapping_table(self):
        value = "（Ｃ＋＋）／ＵＥ５，版本：Ｖ１．２．３。—–“”‘’、「」…"
        expected = "".join(
            character
            for character in unicodedata.normalize("NFKC", value).lower()
            if not character.isspace()
        )

        self.assertEqual(
            ocr_normalization.build_comparison_text(value),
            expected,
        )
        punctuation_values = (
            "。", "—", "–", "“", "”", "‘", "’", "、", "「", "」", "…",
        )
        for punctuation in punctuation_values:
            with self.subTest(punctuation=punctuation):
                self.assertIn(
                    unicodedata.normalize("NFKC", punctuation).lower(),
                    expected,
                )

    def test_lower_is_used_instead_of_casefold_for_distinct_unicode(self):
        value = "Straße ẞ"
        nfkc = unicodedata.normalize("NFKC", value)
        lower_expected = "".join(
            character for character in nfkc.lower() if not character.isspace()
        )
        casefold_value = "".join(
            character for character in nfkc.casefold() if not character.isspace()
        )

        self.assertNotEqual(lower_expected, casefold_value)
        self.assertEqual(
            ocr_normalization.build_comparison_text(value),
            lower_expected,
        )

    def test_ui_short_words_numbers_and_punctuation_are_not_deleted(self):
        value = "A I UI 下一位 3A 0-1 " + string.punctuation

        comparison = ocr_normalization.build_comparison_text(value)

        self.assertEqual(
            comparison,
            "aiui下一位3a0-1" + string.punctuation,
        )

    def test_material_text_number_and_symbol_changes_remain_distinct(self):
        cases = (
            ("C++", "C#"),
            ("C++", "C+"),
            ("UE5", "UE6"),
            ("2026-07-30", "2026-07-31"),
            ("v1.2.3", "v1.2.4"),
            ("项目甲_A1", "项目乙_A1"),
            ("2D/3D", "2D-3D"),
        )

        for left, right in cases:
            with self.subTest(left=left, right=right):
                self.assertNotEqual(
                    ocr_normalization.build_comparison_text(left),
                    ocr_normalization.build_comparison_text(right),
                )

    def test_comparison_builder_is_idempotent_and_does_not_change_input(self):
        normalized_text = "Unity 2022.3\nC++ 与 iOS"
        original = normalized_text[:]

        first = ocr_normalization.build_comparison_text(normalized_text)
        second = ocr_normalization.build_comparison_text(first)

        self.assertEqual(first, "unity2022.3c++与ios")
        self.assertEqual(second, first)
        self.assertEqual(normalized_text, original)

    def test_result_keeps_normalized_case_and_derives_comparison_from_it(self):
        boxes = [
            self.box("unity", "Unity", self.rect(0, 0, 30, 10), 0),
            self.box("version", "2022.3", self.rect(40, 0, 80, 10), 1),
            self.box("ios", "iOS", self.rect(0, 20, 20, 30), 2),
        ]
        original = copy.deepcopy(boxes)

        result = ocr_normalization.normalize_ocr_text(boxes)

        self.assertEqual(result.normalization_version, "r04-v1")
        self.assertEqual(result.normalized_text, "Unity 2022.3\niOS")
        self.assertEqual(result.comparison_text, "unity2022.3ios")
        self.assertEqual(
            result.comparison_text_length,
            len(result.comparison_text),
        )
        self.assertEqual(boxes, original)

    def test_empty_completed_result_has_empty_comparison(self):
        result = ocr_normalization.normalize_ocr_text([])

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_COMPLETED)
        self.assertEqual(result.normalization_version, "r04-v1")
        self.assertEqual(result.normalized_text, "")
        self.assertEqual(result.comparison_text, "")
        self.assertEqual(result.comparison_text_length, 0)

    def test_comparison_failure_returns_sanitized_failed_result(self):
        boxes = [
            self.box("safe", "PRIVATE_COMPARISON_BODY", self.rect(0, 0, 80, 10), 0),
        ]

        with patch.object(
            ocr_normalization,
            "build_comparison_text",
            side_effect=RuntimeError("PRIVATE_COMPARISON_BODY"),
        ):
            result = ocr_normalization.normalize_ocr_text(boxes)

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_FAILED)
        self.assertEqual(result.normalization_version, "r04-v1")
        self.assertEqual(result.raw_text, "PRIVATE_COMPARISON_BODY")
        self.assertIsNone(result.normalized_text)
        self.assertIsNone(result.comparison_text)
        self.assertEqual(
            result.normalization_error_type,
            ocr_normalization.COMPARISON_TEXT_BUILD_FAILED,
        )
        self.assertNotIn(
            "PRIVATE_COMPARISON_BODY",
            repr(result.normalization_warnings),
        )

    def test_r03_sha256_helper_is_stable_for_equivalent_comparison_text(self):
        equivalent_values = (
            "Unity 2022.3 C++",
            "UNITY\n２０２２．３\tＣ＋＋",
            "unity2022.3c++",
        )
        hashes = {
            sha256_normalized_text(
                ocr_normalization.build_comparison_text(value)
            )
            for value in equivalent_values
        }
        changed_hash = sha256_normalized_text(
            ocr_normalization.build_comparison_text(
                "Unity 2022.4 C++"
            )
        )

        self.assertEqual(len(hashes), 1)
        self.assertNotIn(changed_hash, hashes)
        self.assertRegex(next(iter(hashes)), r"^[0-9a-f]{64}$")

    def test_r04_contract_remains_stable_after_r05_schema_activation(self):
        record = OcrScreenRecord(
            run_id="run-fictional",
            candidate_record_id="candidate-fictional",
            screen_id="screen-fictional",
            screen_index=1,
            attempt_index=0,
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            captured_at="2026-07-30T12:00:00+08:00",
            raw_boxes=(),
            raw_text="",
        )

        self.assertEqual(STORAGE_SCHEMA_VERSION, "1.4.0")
        self.assertEqual(record.storage_schema_version, "1.4.0")
        self.assertIsNone(record.normalized_text)
        self.assertIsNone(record.comparison_text)
        self.assertEqual(record.segments, ())
        self.assertIsNone(record.normalization_version)
        self.assertIsNone(record.similarity_hash)
        self.assertIsNone(record.similarity_score)
        self.assertIsNone(record.overlap_text)
        self.assertIsNone(record.new_text)
        self.assertIsNone(record.overlap_ratio)
        self.assertIsNone(record.new_text_ratio)
        self.assertIsNone(record.has_effective_new_text)
        self.assertIsNone(record.aggregation_version)
        self.assertIsNone(record.similarity_version)
        self.assertIsNone(record.dynamic_end_version)
        self.assertEqual(record.processing_status, ProcessingStatus.RAW_ONLY)

        # R05 activates the current writer schema only.  The R03/R04 readers
        # remain available and restoring an older payload does not infer R05.
        payload = record.to_dict()
        for version in (
            LEGACY_STORAGE_SCHEMA_VERSION,
            R04_STORAGE_SCHEMA_VERSION,
        ):
            with self.subTest(version=version):
                restored_payload = dict(payload)
                restored_payload["storage_schema_version"] = version
                restored = OcrScreenRecord.from_dict(restored_payload)
                self.assertEqual(restored.storage_schema_version, version)
                self.assertIsNone(restored.aggregation_version)
                self.assertIsNone(restored.similarity_version)
                self.assertIsNone(restored.dynamic_end_version)

    def test_comparison_module_has_no_ai_or_network_dependency(self):
        forbidden_globals = {
            "anthropic",
            "httpx",
            "openai",
            "requests",
            "transformers",
        }

        self.assertTrue(
            forbidden_globals.isdisjoint(ocr_normalization.__dict__)
        )

    def test_stage0_boxes_and_nested_bbox_are_not_mutated_and_run_is_idempotent(self):
        boxes = (
            OcrBox(
                box_id="one",
                raw_text="  虚构  文本  ",
                confidence=0.91,
                bbox=((0, 0), (30, 0), (30, 10), (0, 10)),
                original_index=0,
                screen_index=0,
            ),
            OcrBox(
                box_id="two",
                raw_text="Demo",
                confidence=0.92,
                bbox=((40, 0), (70, 0), (70, 10), (40, 10)),
                original_index=1,
                screen_index=0,
            ),
        )
        original = copy.deepcopy(boxes)

        first = self.normalize(boxes)
        second = self.normalize(boxes)

        self.assertEqual(first, second)
        self.assertEqual(boxes, original)
        self.assertEqual(boxes[0].raw_text, "  虚构  文本  ")
        self.assertEqual(first.raw_text, "  虚构  文本  \nDemo")

    def test_invalid_geometry_fails_derived_text_and_preserves_raw_evidence(self):
        result = self.normalize([
            self.box("bad-geometry", "仍保留", None, 0),
        ])

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_FAILED)
        self.assertEqual(result.raw_text, "仍保留")
        self.assertIsNone(result.normalized_text)
        self.assertIsNone(result.comparison_text)
        self.assertEqual(result.ordered_box_ids, ())
        self.assertEqual(result.normalized_lines, ())
        self.assertEqual(
            result.normalization_error_type,
            ocr_normalization.LAYOUT_DEGRADED,
        )
        self.assertEqual(
            result.normalization_warnings[0].code,
            ocr_normalization.BBOX_MISSING,
        )

    def test_one_box_failure_fails_the_whole_derived_screen(self):
        boxes = [
            self.box("good", "可用文本", self.rect(0, 0, 40, 10), 0),
            self.box("bad", "PRIVATE_FAILURE_MARKER", self.rect(50, 0, 90, 10), 1),
        ]
        real_normalizer = ocr_normalization.normalize_box_text

        def fail_one(value):
            if value == "PRIVATE_FAILURE_MARKER":
                raise UnicodeError("PRIVATE_FAILURE_MARKER")
            return real_normalizer(value)

        with patch.object(
            ocr_normalization,
            "normalize_box_text",
            side_effect=fail_one,
        ):
            result = self.normalize(boxes)

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_FAILED)
        self.assertEqual(result.raw_text, "可用文本\nPRIVATE_FAILURE_MARKER")
        self.assertIsNone(result.normalized_text)
        self.assertIsNone(result.comparison_text)
        self.assertEqual(result.effective_box_ids, ())
        self.assertEqual(result.normalized_lines, ())
        self.assertEqual(
            result.normalization_warnings[0].code,
            ocr_normalization.BOX_TEXT_NORMALIZATION_FAILED,
        )
        self.assertNotIn(
            "PRIVATE_FAILURE_MARKER",
            repr(result.normalization_warnings),
        )

    def test_executed_normalizer_returns_only_completed_or_failed(self):
        completed = self.normalize([])
        failed = self.normalize([
            self.box("bad", "raw evidence", None, 0),
        ])

        self.assertEqual(
            {completed.status, failed.status},
            {
                ocr_normalization.NORMALIZATION_COMPLETED,
                ocr_normalization.NORMALIZATION_FAILED,
            },
        )

    def test_all_nonempty_box_failures_return_failed_without_throwing(self):
        box = self.box("bad", "虚构失败文本", self.rect(0, 0, 40, 10), 0)

        with patch.object(
            ocr_normalization,
            "normalize_box_text",
            side_effect=UnicodeError("do not expose"),
        ):
            result = self.normalize([box])

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_FAILED)
        self.assertEqual(result.raw_text, "虚构失败文本")
        self.assertIsNone(result.normalized_text)
        self.assertIsNone(result.normalized_text_length)
        self.assertEqual(
            result.normalization_error_type,
            ocr_normalization.ALL_BOX_TEXT_NORMALIZATION_FAILED,
        )

    def test_structural_failure_returns_failed_and_preserves_engine_evidence(self):
        boxes = [
            self.box("duplicate", "甲", self.rect(0, 0, 10, 10), 0),
            self.box("duplicate", "乙", self.rect(20, 0, 30, 10), 1),
        ]

        result = self.normalize(boxes, engine_raw_text="整屏原始证据")

        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_FAILED)
        self.assertEqual(result.raw_text, "整屏原始证据")
        self.assertEqual(
            result.normalization_error_type,
            ocr_normalization.READING_ORDER_BUILD_FAILED,
        )
        self.assertEqual(result.normalization_warnings, ())


class OcrDuplicateDetectionTests(unittest.TestCase):
    config = DEFAULT_OCR_NORMALIZATION_CONFIG

    @staticmethod
    def box(box_id, text, bbox, original_index, confidence=None):
        return NormalizationBox(
            box_id,
            text,
            bbox,
            original_index,
            confidence,
        )

    @staticmethod
    def rect(left, top, right, bottom):
        return (left, top, right, bottom)

    def detect(self, boxes, config=None):
        return ocr_normalization.detect_duplicate_boxes(
            boxes,
            config=config or self.config,
        )

    def test_exact_text_and_strong_geometry_confirm_one_duplicate(self):
        boxes = [
            self.box("primary", "重复文字", self.rect(0, 0, 100, 20), 0, 0.95),
            self.box("duplicate", "重复文字", self.rect(1, 0, 101, 20), 1, 0.90),
        ]

        result = self.detect(boxes)

        self.assertEqual(result.deduplicated_box_count, 1)
        self.assertEqual(result.retained_box_ids, ("primary",))
        self.assertEqual(result.suppressed_duplicate_box_ids, ("duplicate",))
        self.assertEqual(len(result.duplicate_groups), 1)
        group = result.duplicate_groups[0]
        self.assertEqual(group.retained_box_id, "primary")
        self.assertEqual(group.source_box_ids, ("primary", "duplicate"))
        evidence = group.pair_evidence[0]
        self.assertEqual(evidence.decision, "confirmed")
        self.assertTrue(evidence.text_exact)
        self.assertGreaterEqual(evidence.iou, self.config.duplicate_confirm_iou)
        self.assertGreaterEqual(evidence.horizontal_overlap_ratio, 0.90)
        self.assertEqual(evidence.vertical_overlap_ratio, 1.0)
        self.assertLessEqual(evidence.center_distance_ratio, 0.20)
        self.assertEqual(evidence.width_similarity, 1.0)
        self.assertEqual(evidence.height_similarity, 1.0)
        self.assertIn("primary_geometry", evidence.basis)
        self.assertFalse(result.duplicate_risk)
        self.assertEqual(result.candidate_pair_count, 1)
        self.assertEqual(result.confirmation_count, 1)
        self.assertEqual(result.duplicate_gray_pair_count, 0)

    def test_duplicate_exact_key_uses_comparison_width_compatibility(self):
        boxes = [
            self.box("wide", "Ｃ＋＋", self.rect(0, 0, 100, 20), 0, 0.95),
            self.box("ascii", "C++", self.rect(1, 0, 101, 20), 1, 0.90),
        ]
        original = copy.deepcopy(boxes)

        result = self.detect(boxes)

        self.assertEqual(result.retained_box_ids, ("wide",))
        self.assertEqual(result.suppressed_duplicate_box_ids, ("ascii",))
        self.assertTrue(result.pair_evidence[0].text_exact)
        self.assertEqual(boxes, original)

    def test_zero_area_suppresses_only_exact_text_and_exact_geometry(self):
        exact = self.detect([
            self.box("a", "同文", self.rect(5, 5, 5, 5), 0, 0.9),
            self.box("b", "同文", self.rect(5, 5, 5, 5), 1, 0.8),
        ])
        shifted = self.detect([
            self.box("a", "同文", self.rect(5, 5, 5, 5), 0, 0.9),
            self.box("b", "同文", self.rect(6, 5, 6, 5), 1, 0.8),
        ])
        different_text = self.detect([
            self.box("a", "甲", self.rect(5, 5, 5, 5), 0, 0.9),
            self.box("b", "乙", self.rect(5, 5, 5, 5), 1, 0.8),
        ])

        self.assertEqual(exact.suppressed_duplicate_box_ids, ("b",))
        self.assertEqual(exact.pair_evidence[0].iou, 0.0)
        self.assertIn("exact_zero_area_geometry", exact.pair_evidence[0].basis)
        self.assertEqual(shifted.suppressed_duplicate_box_ids, ())
        self.assertEqual(different_text.suppressed_duplicate_box_ids, ())

    def test_highly_similar_nonexact_text_is_not_a_duplicate_candidate(self):
        boxes = [
            self.box(
                "left",
                "Senior Python Engineer",
                self.rect(0, 0, 160, 20),
                0,
                0.95,
            ),
            self.box(
                "right",
                "Senior Python Enginer",
                self.rect(1, 0, 161, 20),
                1,
                0.94,
            ),
        ]

        result = self.detect(boxes)

        self.assertEqual(result.retained_box_ids, ("left", "right"))
        self.assertEqual(result.suppressed_duplicate_box_ids, ())
        self.assertFalse(result.duplicate_risk)
        self.assertEqual(result.pair_evidence, ())
        self.assertEqual(result.candidate_pair_count, 0)
        self.assertEqual(result.confirmation_count, 0)
        self.assertEqual(result.duplicate_gray_pair_count, 0)

    def test_prefix_contains_single_character_and_ocr_typos_are_all_retained(self):
        cases = (
            ("Python Engineer", "Python"),
            ("开发", "开发者"),
            ("Python", "Pyhton"),
            ("项目经理", "产品经理"),
        )
        for left_text, right_text in cases:
            with self.subTest(left_text=left_text, right_text=right_text):
                result = self.detect([
                    self.box("left", left_text, self.rect(0, 0, 100, 20), 0),
                    self.box("right", right_text, self.rect(1, 0, 101, 20), 1),
                ])

                self.assertEqual(result.retained_box_ids, ("left", "right"))
                self.assertEqual(result.suppressed_duplicate_box_ids, ())
                self.assertEqual(result.candidate_pair_count, 0)
                self.assertEqual(result.confirmation_count, 0)

    def test_same_text_far_apart_or_in_distinct_visual_roles_is_retained(self):
        cases = {
            "far-coordinates": [
                self.box("a", "Python", self.rect(0, 0, 50, 20), 0),
                self.box("b", "Python", self.rect(500, 0, 550, 20), 1),
            ],
            "same-line-legitimate-repeat": [
                self.box("a", "负责", self.rect(0, 0, 40, 20), 0),
                self.box("b", "负责", self.rect(120, 0, 160, 20), 1),
            ],
            "title-and-body": [
                self.box("title", "项目经历", self.rect(0, 0, 80, 20), 0),
                self.box("body", "项目经历", self.rect(0, 100, 80, 120), 1),
            ],
            "different-experiences": [
                self.box("first", "负责开发", self.rect(0, 0, 80, 20), 0),
                self.box("second", "负责开发", self.rect(0, 200, 80, 220), 1),
            ],
            "invalid-geometry": [
                self.box("valid", "同文", self.rect(0, 0, 40, 20), 0),
                self.box("invalid", "同文", None, 1),
            ],
        }

        for name, boxes in cases.items():
            with self.subTest(name=name):
                result = self.detect(boxes)
                self.assertEqual(
                    result.retained_box_ids,
                    tuple(box.box_id for box in boxes),
                )
                self.assertEqual(result.duplicate_groups, ())
                self.assertEqual(result.suppressed_duplicate_box_ids, ())
                self.assertFalse(result.duplicate_risk)

    def test_confidence_area_original_index_then_geometry_selects_survivor(self):
        cases = (
            (
                [
                    self.box("low", "同文", self.rect(0, 0, 60, 20), 0, 0.80),
                    self.box("high", "同文", self.rect(1, 0, 61, 20), 1, 0.95),
                ],
                "high",
            ),
            (
                [
                    self.box("missing", "同文", self.rect(0, 0, 60, 20), 0, None),
                    self.box("known", "同文", self.rect(1, 0, 61, 20), 1, 0.70),
                ],
                "known",
            ),
            (
                [
                    self.box("small", "同文", self.rect(0, 0, 60, 20), 0, 0.90),
                    self.box("large", "同文", self.rect(0, 0, 61, 20), 1, 0.90),
                ],
                "large",
            ),
            (
                [
                    self.box("later", "同文", self.rect(0, 0, 60, 20), 3, None),
                    self.box("earlier", "同文", self.rect(1, 0, 61, 20), 2, None),
                ],
                "earlier",
            ),
            (
                [
                    self.box("left-geometry", "同文", self.rect(0, 0, 60, 20), 2, 0.90),
                    self.box("right-geometry", "同文", self.rect(1, 0, 61, 20), 2, 0.90),
                ],
                "left-geometry",
            ),
        )

        for boxes, retained_id in cases:
            with self.subTest(retained_id=retained_id):
                result = self.detect(boxes)
                self.assertEqual(
                    result.duplicate_groups[0].retained_box_id,
                    retained_id,
                )

    def test_center_close_low_iou_and_high_iou_different_text_are_retained(self):
        center_close_low_iou = [
            self.box("wide", "同文", self.rect(0, 45, 100, 55), 0),
            self.box("tall", "同文", self.rect(45, 0, 55, 100), 1),
        ]
        high_iou_different_text = [
            self.box("alpha", "标题甲", self.rect(0, 0, 100, 20), 0),
            self.box("beta", "标题乙", self.rect(1, 0, 101, 20), 1),
        ]

        center_result = self.detect(center_close_low_iou)
        different_result = self.detect(high_iou_different_text)

        for result in (center_result, different_result):
            self.assertEqual(len(result.retained_box_ids), 2)
            self.assertEqual(result.duplicate_groups, ())
            self.assertEqual(result.suppressed_duplicate_box_ids, ())
            self.assertFalse(result.duplicate_risk)
            self.assertEqual(result.pair_evidence, ())
        self.assertEqual(center_result.candidate_pair_count, 1)
        self.assertEqual(center_result.confirmation_count, 1)
        self.assertEqual(different_result.candidate_pair_count, 0)
        self.assertEqual(different_result.confirmation_count, 0)

    def test_exact_text_gray_geometry_sets_risk_but_retains_both(self):
        boxes = [
            self.box("left", "同文", self.rect(0, 0, 100, 20), 0),
            self.box("right", "同文", self.rect(15, 0, 115, 20), 1),
        ]

        result = self.detect(boxes)

        self.assertEqual(result.retained_box_ids, ("left", "right"))
        self.assertEqual(result.suppressed_duplicate_box_ids, ())
        self.assertTrue(result.duplicate_risk)
        self.assertEqual(result.pair_evidence, ())
        self.assertEqual(result.duplicate_gray_pair_count, 1)

    def test_three_boxes_are_directly_confirmed_against_one_survivor(self):
        boxes = [
            self.box("first", "重复", self.rect(0, 0, 100, 20), 0, 0.80),
            self.box("best", "重复", self.rect(0.5, 0, 100.5, 20), 1, 0.95),
            self.box("third", "重复", self.rect(1, 0, 101, 20), 2, 0.90),
        ]
        expected = self.detect(boxes)

        self.assertEqual(len(expected.duplicate_groups), 1)
        self.assertEqual(expected.duplicate_groups[0].retained_box_id, "best")
        self.assertEqual(
            expected.duplicate_groups[0].suppressed_duplicate_box_ids,
            ("first", "third"),
        )
        self.assertEqual(len(expected.duplicate_groups[0].pair_evidence), 2)
        for seed in range(10):
            shuffled = list(boxes)
            random.Random(seed).shuffle(shuffled)
            with self.subTest(seed=seed):
                self.assertEqual(self.detect(shuffled), expected)

    def test_nontransitive_confirmed_chain_does_not_overmerge(self):
        boxes = [
            self.box("a", "重复", self.rect(0, 0, 10, 20), 0, 0.90),
            self.box("b", "重复", self.rect(1, 0, 11, 20), 1, 0.80),
            self.box("c", "重复", self.rect(2, 0, 12, 20), 2, 0.70),
        ]

        result = self.detect(boxes)

        self.assertEqual(len(result.duplicate_groups), 1)
        self.assertEqual(result.duplicate_groups[0].source_box_ids, ("a", "b"))
        self.assertEqual(result.retained_box_ids, ("a", "c"))
        self.assertEqual(result.suppressed_duplicate_box_ids, ("b",))

    def test_center_threshold_just_below_equal_and_above_is_conservative(self):
        config = OcrNormalizationConfig(
            duplicate_confirm_iou=1.0,
            duplicate_secondary_iou=0.70,
            duplicate_confirm_center_ratio=0.20,
            duplicate_secondary_size_similarity=0.95,
        )

        def result_for_shift(shift):
            return self.detect([
                self.box("left", "同文", self.rect(0, 0, 100, 20), 0),
                self.box(
                    "right",
                    "同文",
                    self.rect(shift, 0, 100 + shift, 20),
                    1,
                ),
            ], config=config)

        below = result_for_shift(3.999)
        equal = result_for_shift(4.0)
        above = result_for_shift(4.001)

        self.assertEqual(below.suppressed_duplicate_box_ids, ("right",))
        self.assertEqual(equal.suppressed_duplicate_box_ids, ("right",))
        self.assertEqual(equal.pair_evidence[0].center_distance_ratio, 0.20)
        self.assertEqual(above.suppressed_duplicate_box_ids, ())
        self.assertTrue(above.duplicate_risk)

    def test_normalized_result_suppresses_only_derived_duplicate(self):
        boxes = (
            OcrBox(
                box_id="raw-first",
                raw_text="重复证据",
                confidence=0.91,
                bbox=((0, 0), (100, 0), (100, 20), (0, 20)),
                original_index=0,
                screen_index=0,
            ),
            OcrBox(
                box_id="raw-second",
                raw_text="重复证据",
                confidence=0.90,
                bbox=((1, 0), (101, 0), (101, 20), (1, 20)),
                original_index=1,
                screen_index=0,
            ),
        )
        original = copy.deepcopy(boxes)

        result = ocr_normalization.normalize_ocr_text(boxes)

        self.assertEqual(boxes, original)
        self.assertEqual(len(boxes), 2)
        self.assertEqual(result.raw_text, "重复证据\n重复证据")
        self.assertEqual(result.raw_text_length, len(result.raw_text))
        self.assertEqual(result.normalized_text, "重复证据")
        self.assertEqual(result.comparison_text, "重复证据")
        self.assertEqual(result.effective_box_ids, ("raw-first",))
        self.assertEqual(result.deduplicated_box_count, 1)
        self.assertEqual(
            result.suppressed_duplicate_box_ids,
            ("raw-second",),
        )
        self.assertEqual(
            result.duplicate_groups[0].retained_box_id,
            "raw-first",
        )
        self.assertFalse(result.duplicate_risk)

    def test_gray_pair_is_preserved_in_normalized_text_with_warning(self):
        boxes = [
            self.box("left", "同文", self.rect(0, 0, 100, 20), 0),
            self.box("right", "同文", self.rect(15, 0, 115, 20), 1),
        ]

        result = ocr_normalization.normalize_ocr_text(boxes)

        self.assertEqual(result.effective_box_ids, ("left", "right"))
        self.assertEqual(result.normalized_text, "同文同文")
        self.assertTrue(result.duplicate_risk)
        self.assertEqual(result.status, ocr_normalization.NORMALIZATION_COMPLETED)
        self.assertIsNone(result.normalization_error_type)
        self.assertEqual(result.normalization_warnings, ())
        self.assertEqual(result.duplicate_gray_pair_count, 1)

    def test_thresholds_are_centralized_and_validated(self):
        self.assertEqual(self.config.duplicate_candidate_margin_height_ratio, 1.0)
        self.assertEqual(self.config.duplicate_confirm_iou, 0.85)
        self.assertEqual(self.config.duplicate_confirm_center_ratio, 0.20)
        self.assertEqual(self.config.duplicate_confirm_size_similarity, 0.90)
        self.assertEqual(self.config.duplicate_secondary_iou, 0.70)
        self.assertEqual(self.config.duplicate_secondary_size_similarity, 0.95)
        self.assertEqual(self.config.duplicate_gray_iou, 0.65)
        self.assertEqual(self.config.duplicate_gray_center_ratio, 0.35)
        self.assertEqual(self.config.duplicate_gray_size_similarity, 0.80)

        invalid_configs = (
            {"duplicate_candidate_margin_height_ratio": -0.1},
            {"duplicate_confirm_iou": -0.1},
            {"duplicate_confirm_center_ratio": -0.1},
            {"duplicate_confirm_size_similarity": 1.1},
            {"duplicate_secondary_iou": -0.1},
            {"duplicate_secondary_size_similarity": 1.1},
            {"duplicate_gray_iou": 1.1},
            {"duplicate_gray_center_ratio": -0.1},
            {"duplicate_gray_size_similarity": 1.1},
            {"duplicate_confirm_center_ratio": float("nan")},
        )
        for values in invalid_configs:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    OcrNormalizationConfig(**values)

        self.assertNotIn("SequenceMatcher", ocr_normalization.__dict__)
        self.assertFalse(hasattr(self.config, "duplicate_text_similarity_threshold"))
        self.assertFalse(hasattr(self.config, "duplicate_text_risk_threshold"))

    def performance_boxes(self, count, mode):
        boxes = []
        for index in range(count):
            if mode == "dense":
                left, top = 0, 0
                text = "same"
            elif mode == "far":
                left, top = index * 150, 0
                text = "same"
            else:
                row, column = divmod(index, 25)
                left, top = column * 120, row * 30
                text = "unique-{0:03d}".format(index)
            boxes.append(self.box(
                "box-{0:03d}".format(index),
                text,
                self.rect(left, top, left + 100, top + 20),
                index,
                0.90,
            ))
        return boxes

    def test_dense_500_uses_direct_survivor_confirmations_not_pair_matrix(self):
        boxes = self.performance_boxes(500, "dense")
        original = copy.deepcopy(boxes)

        result = self.detect(boxes)

        self.assertEqual(boxes, original)
        self.assertEqual(result.deduplicated_box_count, 1)
        self.assertEqual(len(result.suppressed_duplicate_box_ids), 499)
        self.assertEqual(result.candidate_pair_count, 499)
        self.assertEqual(result.confirmation_count, 499)
        self.assertEqual(len(result.pair_evidence), 499)

    def test_far_500_same_text_has_no_spatial_candidates(self):
        result = self.detect(self.performance_boxes(500, "far"))

        self.assertEqual(result.deduplicated_box_count, 500)
        self.assertEqual(result.suppressed_duplicate_box_ids, ())
        self.assertEqual(result.candidate_pair_count, 0)
        self.assertEqual(result.confirmation_count, 0)

    def test_100_repeated_runs_are_deterministic_and_stateless(self):
        boxes = self.performance_boxes(100, "dense")
        expected = self.detect(boxes)

        for _ in range(100):
            self.assertEqual(self.detect(boxes), expected)
        empty = self.detect(())
        self.assertEqual(empty.retained_box_ids, ())
        self.assertEqual(empty.candidate_pair_count, 0)
        self.assertEqual(empty.confirmation_count, 0)

    def test_normalization_p95_meets_100_and_500_box_contract(self):
        def p95_milliseconds(count):
            boxes = self.performance_boxes(count, "unique")
            for _ in range(3):
                ocr_normalization.normalize_ocr_text(boxes)
            timings = []
            for _ in range(25):
                started = time.perf_counter()
                ocr_normalization.normalize_ocr_text(boxes)
                timings.append((time.perf_counter() - started) * 1000.0)
            return statistics.quantiles(
                timings,
                n=20,
                method="inclusive",
            )[18]

        self.assertLess(p95_milliseconds(100), 10.0)
        self.assertLess(p95_milliseconds(500), 50.0)

    def test_dense_500_peak_memory_is_bounded_and_released(self):
        boxes = self.performance_boxes(500, "dense")
        tracemalloc.start()
        try:
            result = ocr_normalization.normalize_ocr_text(boxes)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertEqual(len(result.suppressed_duplicate_box_ids), 499)
        self.assertLess(peak, 20 * 1024 * 1024)


class OcrNormalizationConfigIdentityTests(unittest.TestCase):
    def test_snapshot_is_complete_canonical_and_digest_changes_with_output_config(self):
        config = DEFAULT_OCR_NORMALIZATION_CONFIG
        snapshot = canonical_normalization_config(config)
        digest = normalization_config_digest(snapshot)

        self.assertEqual(snapshot["normalization_version"], "r04-v1")
        self.assertEqual(
            snapshot["normalization_config_version"], "r04-config-v1"
        )
        self.assertEqual(snapshot["effective_min_confidence"], 0.85)
        self.assertEqual(snapshot["unknown_confidence_policy"], "include")
        self.assertEqual(len(digest), 64)
        self.assertEqual(normalization_config_from_snapshot(snapshot), config)
        self.assertNotEqual(
            digest,
            normalization_config_digest(
                replace(config, duplicate_gray_iou=0.66)
            ),
        )

    def test_snapshot_restore_rejects_missing_extra_and_self_digest_fields(self):
        snapshot = canonical_normalization_config(
            DEFAULT_OCR_NORMALIZATION_CONFIG
        )
        cases = (
            {key: value for key, value in snapshot.items() if key != "duplicate_gray_iou"},
            {**snapshot, "future_threshold": 1.0},
            {**snapshot, "normalization_config_digest": "0" * 64},
        )
        for value in cases:
            with self.subTest(keys=tuple(value)):
                with self.assertRaises(ValueError):
                    normalization_config_from_snapshot(value)


if __name__ == "__main__":
    unittest.main()
