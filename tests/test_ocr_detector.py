from dataclasses import fields
import unittest
from unittest.mock import Mock, patch

from ocr_calibration import ScreenRegion
from ocr_detector import (
    OCRKeywordDetector,
    RapidOCRBackend,
    ScanObservation,
    accepted_ocr_items,
    calculate_load_metrics,
    evaluate_detail_page_load,
)
from ocr_text import OCRItem, matching_keyword_rule, parse_keyword_rules


def single_rule(keyword):
    return parse_keyword_rules(f'"{keyword}"')


class FakeCapture:
    def __init__(self):
        self.calls = 0

    def capture(self, region):
        self.calls += 1
        return self.calls


class FakeBackend:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = 0

    def recognize(self, _image):
        page = self.pages[min(self.calls, len(self.pages) - 1)]
        self.calls += 1
        return [OCRItem(page, 0.99)]


class DetailPageLoadHelperTests(unittest.TestCase):
    def test_zero_boxes_is_not_loaded(self):
        self.assertEqual(
            evaluate_detail_page_load(0, 0, 5, 30),
            (False, "zero_ocr_boxes"),
        )

    def test_five_boxes_twenty_nine_characters_is_not_loaded(self):
        self.assertEqual(
            evaluate_detail_page_load(5, 29, 5, 30),
            (False, "low_box_count_and_short_text"),
        )

    def test_five_boxes_thirty_characters_is_loaded(self):
        self.assertEqual(
            evaluate_detail_page_load(5, 30, 5, 30),
            (True, "threshold_passed"),
        )

    def test_six_boxes_ten_characters_is_loaded(self):
        self.assertEqual(
            evaluate_detail_page_load(6, 10, 5, 30),
            (True, "threshold_passed"),
        )

    def test_two_boxes_one_hundred_characters_is_loaded(self):
        self.assertEqual(
            evaluate_detail_page_load(2, 100, 5, 30),
            (True, "threshold_passed"),
        )

    def test_items_below_confidence_are_excluded(self):
        items = [OCRItem("below", 0.84), OCRItem("accepted", 0.86)]

        accepted_items = accepted_ocr_items(items, 0.85)

        self.assertEqual(accepted_items, [items[1]])

    def test_items_at_confidence_are_kept(self):
        item = OCRItem("threshold", 0.85)

        self.assertEqual(accepted_ocr_items([item], 0.85), [item])

    def test_empty_accepted_text_counts_box_not_length(self):
        accepted_items = [OCRItem("", 0.99), OCRItem("   ", 0.99)]

        self.assertEqual(calculate_load_metrics(accepted_items), (2, 0))

    def test_text_length_ignores_leading_and_trailing_whitespace(self):
        accepted_items = [OCRItem("  A B  ", 0.99)]

        self.assertEqual(calculate_load_metrics(accepted_items), (1, 3))

    def test_text_length_sums_multiple_boxes(self):
        accepted_items = [
            OCRItem("Python", 0.99),
            OCRItem("中文", 0.99),
            OCRItem("!", 0.99),
        ]

        self.assertEqual(calculate_load_metrics(accepted_items), (3, 9))

    def test_ten_raw_items_filter_to_three_metrics(self):
        items = [
            OCRItem("ab", 0.85),
            OCRItem("c", 0.90),
            OCRItem(" de ", 0.99),
            *[OCRItem("ignored", 0.84) for _ in range(7)],
        ]

        accepted_items = accepted_ocr_items(items, 0.85)

        self.assertEqual(calculate_load_metrics(accepted_items), (3, 5))

    def test_custom_thresholds_are_used(self):
        self.assertEqual(
            evaluate_detail_page_load(2, 39, 2, 40),
            (False, "low_box_count_and_short_text"),
        )
        self.assertEqual(
            evaluate_detail_page_load(2, 40, 2, 40),
            (True, "threshold_passed"),
        )

    def test_helpers_do_not_mutate_inputs(self):
        items = [OCRItem("  kept  ", 0.85), OCRItem("ignored", 0.84)]
        original_items = list(items)
        original_texts = [item.text for item in items]

        accepted_items = accepted_ocr_items(items, 0.85)
        metrics = calculate_load_metrics(accepted_items)
        result = evaluate_detail_page_load(*metrics, 5, 30)

        self.assertEqual(items, original_items)
        self.assertEqual([item.text for item in items], original_texts)
        self.assertIsNot(accepted_items, items)
        self.assertEqual(metrics, (1, 4))
        self.assertEqual(result, (False, "low_box_count_and_short_text"))


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.region = ScreenRegion(10, 20, 800, 600)

    def make_detector(self, pages, max_scans=8, scroll=None):
        return OCRKeywordDetector(
            backend=FakeBackend(pages),
            capture=FakeCapture(),
            region=self.region,
            max_scans=max_scans,
            scroll=scroll,
            wait=lambda _seconds: None,
        )

    def test_capture_observation_collects_once_without_matching_or_motion(self):
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [
            OCRItem("accepted", 0.85),
            OCRItem(" low ", 0.84),
            OCRItem("   ", 0.99),
        ]
        scroll = Mock()
        wait = Mock()
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            min_confidence=0.85,
            scroll=scroll,
            wait=wait,
        )

        with patch("ocr_detector.matching_keyword_rule") as matcher:
            observation = detector.capture_observation(1)

        self.assertEqual(capture.calls, 1)
        backend.recognize.assert_called_once_with(1)
        matcher.assert_not_called()
        scroll.assert_not_called()
        wait.assert_not_called()
        self.assertEqual(observation.item_count, 3)
        self.assertEqual(observation.ocr_box_count, 2)
        self.assertEqual(observation.ocr_text_length, 8)
        self.assertEqual(observation.text, "accepted")

    def test_scan_observation_only_adds_two_load_metric_fields(self):
        field_names = [field.name for field in fields(ScanObservation)]

        self.assertEqual(field_names, [
            "scan_number",
            "text",
            "item_count",
            "elapsed_seconds",
            "matched_keyword",
            "matched_rule",
            "ocr_box_count",
            "ocr_text_length",
        ])
        for forbidden_name in (
            "ocr_items",
            "raw_items",
            "accepted_items",
            "evidence",
        ):
            self.assertNotIn(forbidden_name, field_names)

    def test_prefetched_first_observation_is_not_captured_again(self):
        capture = FakeCapture()
        backend = Mock()
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            max_scans=1,
            wait=Mock(),
        )
        first_observation = ScanObservation(
            1,
            "没有关键词",
            6,
            0.01,
            ocr_box_count=6,
            ocr_text_length=30,
        )

        with patch("ocr_detector.logger.info") as scan_log:
            result = detector.detect(
                single_rule("Python"),
                first_observation=first_observation,
            )

        self.assertEqual(capture.calls, 0)
        backend.recognize.assert_not_called()
        self.assertEqual(result.scans_completed, 1)
        self.assertEqual(result.observations, [first_observation])
        scan_log.assert_not_called()

    def test_prefetched_first_observation_matches_and_appends_once(self):
        detector = self.make_detector([], max_scans=1)
        first_observation = ScanObservation(
            1,
            "没有关键词",
            6,
            0.01,
            ocr_box_count=6,
            ocr_text_length=30,
        )

        with patch(
            "ocr_detector.matching_keyword_rule",
            wraps=matching_keyword_rule,
        ) as matcher:
            result = detector.detect(
                single_rule("Python"),
                first_observation=first_observation,
            )

        matcher.assert_called_once()
        self.assertEqual(result.observations.count(first_observation), 1)
        self.assertEqual(result.scans_completed, 1)

    def test_prefetched_match_still_uses_independent_confirmation(self):
        detector = self.make_detector(["Python"], max_scans=8)
        first_observation = ScanObservation(
            1,
            "Python",
            6,
            0.01,
            ocr_box_count=6,
            ocr_text_length=30,
        )

        result = detector.detect(
            single_rule("Python"),
            first_observation=first_observation,
        )

        self.assertTrue(result.confirmed_match)
        self.assertEqual(detector.capture.calls, 1)
        self.assertEqual(detector.backend.calls, 1)
        self.assertEqual(result.scans_completed, 1)
        self.assertEqual(len(result.observations), 2)
        self.assertIs(result.observations[0], first_observation)
        self.assertIsNot(result.observations[1], first_observation)

    def test_prefetched_miss_keeps_eight_screens_and_seven_scrolls(self):
        scroll_calls = []
        detector = self.make_detector(
            [f"第{number}页" for number in range(2, 9)],
            max_scans=8,
            scroll=lambda: scroll_calls.append(True),
        )
        first_observation = ScanObservation(
            1,
            "第1页",
            6,
            0.01,
            ocr_box_count=6,
            ocr_text_length=30,
        )

        result = detector.detect(
            single_rule("不存在"),
            first_observation=first_observation,
        )

        self.assertEqual(result.scans_completed, 8)
        self.assertEqual(len(result.observations), 8)
        self.assertEqual(detector.capture.calls, 7)
        self.assertEqual(detector.backend.calls, 7)
        self.assertEqual(len(scroll_calls), 7)

    def test_match_requires_second_confirmation(self):
        detector = self.make_detector(["数字媒体", "数字媒体"])
        result = detector.detect(single_rule("数字媒体"))
        self.assertTrue(result.success)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.matched_keyword, '"数字媒体"')
        self.assertEqual(len(result.observations), 2)

    def test_unconfirmed_match_does_not_trigger(self):
        detector = self.make_detector(["数字媒体", "其他内容"])
        result = detector.detect(single_rule("数字媒体"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_scans_fixed_number_and_scrolls_between_pages(self):
        scroll_calls = []
        detector = self.make_detector(
            ["第一页", "第二页", "第三页"],
            max_scans=3,
            scroll=lambda: scroll_calls.append(True),
        )
        result = detector.detect(single_rule("不存在"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.scans_completed, 3)
        self.assertEqual(len(scroll_calls), 2)

    def test_keyword_on_later_screen_is_confirmed(self):
        scroll_calls = []
        detector = self.make_detector(
            ["第一页", "第二页 Python", "第二页 Python"],
            max_scans=8,
            scroll=lambda: scroll_calls.append(True),
        )
        result = detector.detect(single_rule("Python"))
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.scans_completed, 2)
        self.assertEqual(len(scroll_calls), 1)

    def test_eight_screens_without_keyword_never_match(self):
        scroll_calls = []
        detector = self.make_detector(
            [f"第{number}页" for number in range(1, 9)],
            max_scans=8,
            scroll=lambda: scroll_calls.append(True),
        )
        result = detector.detect(single_rule("不存在"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.scans_completed, 8)
        self.assertEqual(len(scroll_calls), 7)

    def test_backend_failure_is_fail_closed(self):
        class BrokenBackend:
            def recognize(self, _image):
                raise RuntimeError("OCR unavailable")

        detector = OCRKeywordDetector(
            backend=BrokenBackend(),
            capture=FakeCapture(),
            region=self.region,
            wait=lambda _seconds: None,
        )
        result = detector.detect(single_rule("关键词"))
        self.assertFalse(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIn("OCR unavailable", result.error)

    def test_empty_ocr_result_does_not_match(self):
        detector = self.make_detector([""], max_scans=1)
        result = detector.detect(single_rule("关键词"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)

    def test_low_confidence_match_does_not_trigger(self):
        class LowConfidenceBackend:
            def recognize(self, _image):
                return [OCRItem("关键词", 0.4)]

        detector = OCRKeywordDetector(
            backend=LowConfidenceBackend(),
            capture=FakeCapture(),
            region=self.region,
            wait=lambda _seconds: None,
            max_scans=1,
            min_confidence=0.85,
        )
        result = detector.detect(single_rule("关键词"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)

    def test_combination_rule_requires_full_second_confirmation(self):
        detector = self.make_detector(["PR AE", "只有 PR"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"PR" and "AE"'))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_same_combination_rule_is_confirmed(self):
        detector = self.make_detector(["PR AE", "AE 与 PR"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"PR" and "AE"'))
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.matched_keyword, '"PR" and "AE"')

    def test_different_rule_cannot_complete_confirmation(self):
        detector = self.make_detector(["技能 A", "技能 B"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"A"; "B"'))
        self.assertFalse(result.confirmed_match)

    def test_not_rule_is_confirmed_when_both_passes_satisfy_the_full_rule(self):
        detector = self.make_detector(["短剧编导", "短剧制作"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"短剧" and not "销售"'))
        self.assertTrue(result.success)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.matched_keyword, '"短剧" and not "销售"')
        self.assertEqual(len(result.observations), 2)

    def test_not_rule_fails_confirmation_when_excluded_keyword_appears(self):
        detector = self.make_detector(["短剧编导", "短剧销售"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"短剧" and not "销售"'))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)
        self.assertEqual(len(result.observations), 2)

    def test_not_rule_fails_confirmation_when_positive_keyword_disappears(self):
        detector = self.make_detector(["短剧编导", "其他岗位"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"短剧" and not "销售"'))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_mixed_not_rule_is_rechecked_as_the_same_complete_rule(self):
        detector = self.make_detector(["只有 C", "B 和 C"], max_scans=1)
        result = detector.detect(
            parse_keyword_rules('"A" or not "B" and "C"')
        )
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_not_rule_does_not_start_confirmation_when_first_pass_is_excluded(self):
        detector = self.make_detector(["短剧销售"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"短剧" and not "销售"'))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertEqual(len(result.observations), 1)

    def test_any_rule_is_confirmed_as_one_complete_rule(self):
        detector = self.make_detector(
            ["魔方 短剧 剪辑", "九州 漫剧 制作"],
            max_scans=1,
        )
        result = detector.detect(parse_keyword_rules(
            'any("魔方","九州") and any("短剧","漫剧") '
            'and not any("投放","消耗")'
        ))
        self.assertTrue(result.success)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(len(result.observations), 2)

    def test_any_rule_fails_confirmation_when_excluded_group_appears(self):
        detector = self.make_detector(
            ["魔方 短剧 剪辑", "九州 漫剧 投放"],
            max_scans=1,
        )
        result = detector.detect(parse_keyword_rules(
            'any("魔方","九州") and any("短剧","漫剧") '
            'and not any("投放","消耗")'
        ))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)
        self.assertEqual(len(result.observations), 2)


class RapidOCRAdapterTests(unittest.TestCase):
    def test_modern_result_object(self):
        class Result:
            txts = ["数字媒体"]
            scores = [0.98]
            boxes = [[[0, 0], [20, 0], [20, 10], [0, 10]]]

        backend = RapidOCRBackend(engine=lambda _image: Result())
        items = backend.recognize(object())
        self.assertEqual(items[0].text, "数字媒体")
        self.assertEqual(items[0].confidence, 0.98)

    def test_legacy_tuple_result(self):
        lines = [[[[0, 0], [20, 0], [20, 10], [0, 10]], "Python", 0.97]]
        backend = RapidOCRBackend(engine=lambda _image: (lines, 0.1))
        items = backend.recognize(object())
        self.assertEqual(items[0].text, "Python")
        self.assertEqual(items[0].confidence, 0.97)


if __name__ == "__main__":
    unittest.main()
