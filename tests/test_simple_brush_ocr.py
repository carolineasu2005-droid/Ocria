import unittest
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, fields
import hashlib
import logging
import os
from pathlib import Path
import tempfile
from unittest.mock import Mock, call, patch

import simple_brush
from calibration_profiles import CalibrationProfileError, REQUIRED_AREA_FIELDS
from ocr_detector import DetectionResult, ScanObservation, ScreenFingerprint
from ocr_candidate import CandidateOcrBuilder
from ocr_records import CaptureStatus, CaptureType
from ocr_text import OCRItem


def sample_profile_areas():
    return {
        field_name: simple_brush.ScreenRegion(
            left=10 + index,
            top=20 + index,
            width=30 + index,
            height=40 + index,
        )
        for index, field_name in enumerate(REQUIRED_AREA_FIELDS)
    }


def sample_profile(*, missing=()):
    areas = sample_profile_areas()
    for field_name in missing:
        areas.pop(field_name, None)
    return Mock(
        profile_name="main",
        areas=areas,
        system_info={
            "os": "Windows",
            "screen_width": 1920,
            "screen_height": 1080,
            "dpi_scale": 1.25,
        },
    )


def loaded_observation():
    return ScanObservation(
        1,
        "loaded detail text",
        6,
        0.01,
        ocr_box_count=6,
        ocr_text_length=30,
    )


def not_loaded_observation():
    return ScanObservation(
        1,
        "short",
        2,
        0.01,
        ocr_box_count=2,
        ocr_text_length=5,
    )


def sample_batch_filter_regions():
    return simple_brush.BatchFilterRegions(
        first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
        open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
        unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
        confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
    )


def make_switch_fingerprint(
    hash_character,
    *,
    screen_index=None,
    fingerprint_version="r03-v1",
    exact_hash=None,
):
    return ScreenFingerprint(
        raw_text="",
        normalized_text="",
        raw_text_length=0,
        normalized_text_length=0,
        ocr_box_count=0,
        captured_at="2026-01-01T00:00:00+00:00",
        exact_hash=(
            exact_hash
            if exact_hash is not None
            else hash_character * 64
        ),
        fingerprint_version=fingerprint_version,
        screen_index=screen_index,
    )


def make_switch_observation(fingerprint):
    return ScanObservation(
        scan_number=1,
        text="",
        item_count=0,
        elapsed_seconds=0.0,
        fingerprint=fingerprint,
    )


def make_ready_switch_observation(
    hash_character,
    *,
    screen_index=None,
    fingerprint_version="r03-v1",
    ready=True,
    fingerprint=True,
):
    screen_fingerprint = (
        make_switch_fingerprint(
            hash_character,
            screen_index=screen_index,
            fingerprint_version=fingerprint_version,
        )
        if fingerprint
        else None
    )
    return ScanObservation(
        scan_number=1,
        text="",
        item_count=6 if ready else 2,
        elapsed_seconds=0.0,
        ocr_box_count=6 if ready else 2,
        ocr_text_length=30 if ready else 5,
        fingerprint=screen_fingerprint,
    )


def render_log_calls(*loggers):
    rendered = []
    for log_mock in loggers:
        for log_call in log_mock.call_args_list:
            message, *values = log_call.args
            rendered.append(message % tuple(values) if values else message)
    return rendered


def file_snapshot(path):
    path = Path(path)
    if not path.exists():
        return None
    stat = path.stat()
    return (
        stat.st_size,
        stat.st_mtime_ns,
        hashlib.sha256(path.read_bytes()).hexdigest(),
    )


class LoggingIsolationTests(unittest.TestCase):
    def test_imported_module_has_no_default_file_handler_or_real_log_write(self):
        real_log_path = simple_brush.DEFAULT_LOG_PATH.resolve()
        before = file_snapshot(real_log_path)

        matching_handlers = [
            handler
            for handler in logging.getLogger().handlers
            if isinstance(handler, logging.FileHandler)
            and Path(handler.baseFilename).resolve() == real_log_path
        ]
        self.assertEqual(matching_handlers, [])

        simple_brush.logger.info(
            "event=test_logging_isolation state=imported_without_file_handler"
        )
        simple_brush.logger.warning(
            "event=test_logging_isolation error_type=FictionalError"
        )

        self.assertEqual(file_snapshot(real_log_path), before)

    def test_absent_default_log_is_not_created_by_logging_calls(self):
        previous_working_directory = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            try:
                os.chdir(temporary_path)
                simple_brush.logger.info(
                    "event=test_logging_isolation state=absent_default"
                )
                self.assertFalse(Path("logs/simple_brush.log").exists())
            finally:
                os.chdir(previous_working_directory)

    def test_explicit_temporary_file_handler_is_idempotent_private_and_closed(self):
        private_email = "private-user@privacy-marker.invalid"
        private_rule = "PRIVATE_RULE_SOURCE_7F2A"
        private_body = "PRIVATE_OCR_BODY_9C4D"
        private_markers = (private_email, private_rule, private_body)
        temporary_directory_path = None

        with tempfile.TemporaryDirectory() as temporary:
            temporary_directory_path = Path(temporary)
            temporary_log_path = temporary_directory_path / "test-simple-brush.log"
            handler = simple_brush.configure_file_logging(temporary_log_path)
            repeated = simple_brush.configure_file_logging(temporary_log_path)
            self.assertIs(repeated, handler)
            self.assertEqual(
                sum(
                    isinstance(candidate, logging.FileHandler)
                    and Path(candidate.baseFilename).resolve()
                    == temporary_log_path.resolve()
                    for candidate in logging.getLogger().handlers
                ),
                1,
            )

            saved_rules = simple_brush.forward_keywords
            saved_forward_enabled = simple_brush.forward_enabled
            saved_detector = simple_brush.ocr_detector
            saved_backup_email = simple_brush.backup_email
            saved_forward_count = simple_brush.forward_consecutive
            try:
                simple_brush.forward_keywords = simple_brush.parse_keyword_rules(
                    '"{0}"'.format(private_rule)
                )
                simple_brush.forward_enabled = True
                detector = Mock()
                detector.detect.return_value = DetectionResult(
                    success=True,
                    confirmed_match=True,
                    matched_keyword=private_rule,
                    scans_completed=1,
                    observations=[ScanObservation(
                        1,
                        private_body,
                        1,
                        0.01,
                        private_rule,
                    )],
                )
                simple_brush.ocr_detector = detector
                with patch.object(
                    simple_brush,
                    "ensure_ocr_region_calibrated",
                    return_value=True,
                ):
                    matched, _result = simple_brush.detect_keywords()
                self.assertTrue(matched)

                simple_brush.backup_email = private_email
                simple_brush.forward_consecutive = 0
                with (
                    patch.object(simple_brush, "click_in_region"),
                    patch.object(simple_brush, "human_click"),
                    patch.object(
                        simple_brush,
                        "random_point_in_region",
                        return_value=(500, 400),
                    ),
                    patch.object(simple_brush, "human_delay", return_value=True),
                    patch.object(simple_brush, "get_clipboard_text", return_value=""),
                    patch.object(
                        simple_brush,
                        "type_text_human",
                        return_value=True,
                    ) as type_text,
                    patch.object(simple_brush.pyautogui, "hotkey"),
                    patch.object(simple_brush.pyautogui, "press"),
                    patch.object(simple_brush.time, "sleep"),
                ):
                    self.assertTrue(simple_brush.forward_one_candidate())
                type_text.assert_called_once_with(private_email)

                simple_brush.forward_consecutive = 0
                with (
                    patch.object(simple_brush, "click_in_region"),
                    patch.object(simple_brush, "human_click"),
                    patch.object(
                        simple_brush,
                        "random_point_in_region",
                        return_value=(500, 400),
                    ),
                    patch.object(simple_brush, "human_delay", return_value=True),
                    patch.object(
                        simple_brush,
                        "get_clipboard_text",
                        return_value=private_email,
                    ),
                    patch.object(simple_brush, "type_text_human") as type_text,
                    patch.object(simple_brush.pyautogui, "hotkey"),
                    patch.object(simple_brush.pyautogui, "press"),
                    patch.object(simple_brush.time, "sleep"),
                ):
                    self.assertTrue(simple_brush.forward_one_candidate())
                type_text.assert_not_called()

                simple_brush.logger.error("运行异常 error_type=RuntimeError")
            finally:
                simple_brush.forward_keywords = saved_rules
                simple_brush.forward_enabled = saved_forward_enabled
                simple_brush.ocr_detector = saved_detector
                simple_brush.backup_email = saved_backup_email
                simple_brush.forward_consecutive = saved_forward_count
                simple_brush.close_file_logging(handler)

            self.assertNotIn(handler, logging.getLogger().handlers)
            self.assertIsNone(handler.stream)
            rendered = temporary_log_path.read_text(encoding="utf-8")
            self.assertIn("rule_count=1", rendered)
            self.assertIn("email_source=manual", rendered)
            self.assertIn("email_source=recent_contact", rendered)
            self.assertIn("error_type=RuntimeError", rendered)
            for marker in private_markers:
                self.assertNotIn(marker, rendered)

        self.assertFalse(temporary_directory_path.exists())

    def test_console_handler_installation_is_idempotent(self):
        console_handlers = [
            handler
            for handler in simple_brush.logger.handlers
            if getattr(
                handler,
                simple_brush._CONSOLE_HANDLER_MARKER,
                False,
            )
        ]

        self.assertEqual(console_handlers, [simple_brush.console])


class CandidateSwitchPureTests(unittest.TestCase):
    def test_state_constants_and_frozen_budgets_match_tid(self):
        self.assertEqual(simple_brush.CANDIDATE_SWITCH_MAX_ACTIONS, 2)
        self.assertEqual(
            simple_brush.CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION,
            6,
        )
        self.assertEqual(
            simple_brush.CANDIDATE_SWITCH_STABLE_OBSERVATIONS,
            2,
        )
        self.assertEqual(
            simple_brush.CANDIDATE_SWITCH_OBSERVATION_WAIT_SECONDS,
            0.8,
        )
        self.assertEqual(
            (
                simple_brush.CANDIDATE_SWITCH_PENDING,
                simple_brush.CANDIDATE_SWITCH_LOADING,
                simple_brush.CANDIDATE_SWITCH_OBSERVING,
                simple_brush.CANDIDATE_SWITCH_UNCHANGED,
                simple_brush.CANDIDATE_SWITCH_CONFIRMED,
                simple_brush.CANDIDATE_SWITCH_UNVERIFIABLE,
                simple_brush.CANDIDATE_SWITCH_FAILED,
            ),
            (
                "switch_pending",
                "switch_loading",
                "switch_observing",
                "switch_unchanged",
                "switch_confirmed",
                "switch_unverifiable",
                "switch_failed",
            ),
        )

    def test_value_objects_have_only_frozen_tid_fields(self):
        self.assertEqual(
            tuple(field.name for field in fields(
                simple_brush.CandidateSwitchContext
            )),
            ("formal_fingerprints", "pre_switch_fingerprint"),
        )
        self.assertEqual(
            tuple(field.name for field in fields(
                simple_brush.CandidateSwitchResult
            )),
            (
                "state",
                "action_attempt",
                "observation_attempt",
                "confirmed_observation",
                "failure_reason",
            ),
        )

        baseline = make_switch_fingerprint("a")
        context = simple_brush.CandidateSwitchContext((), baseline)
        result = simple_brush.CandidateSwitchResult(
            simple_brush.CANDIDATE_SWITCH_PENDING,
            0,
            0,
        )
        with self.assertRaises(FrozenInstanceError):
            context.pre_switch_fingerprint = make_switch_fingerprint("b")
        with self.assertRaises(FrozenInstanceError):
            result.state = simple_brush.CANDIDATE_SWITCH_FAILED

    def test_comparable_fingerprint_reuses_r03_validation(self):
        valid = make_switch_fingerprint("a")
        bad_hash = make_switch_fingerprint(
            "a",
            exact_hash="not-a-valid-hash",
        )
        bad_version = make_switch_fingerprint(
            "a",
            fingerprint_version="",
        )

        self.assertTrue(
            simple_brush.is_comparable_screen_fingerprint(valid)
        )
        self.assertFalse(
            simple_brush.is_comparable_screen_fingerprint(None)
        )
        self.assertFalse(
            simple_brush.is_comparable_screen_fingerprint(bad_hash)
        )
        self.assertFalse(
            simple_brush.is_comparable_screen_fingerprint(bad_version)
        )

    def test_formal_fingerprints_filter_and_sort_without_confirmation(self):
        formal_three = make_switch_fingerprint("3", screen_index=3)
        formal_one = make_switch_fingerprint("1", screen_index=1)
        confirmation = make_switch_fingerprint("c")
        invalid = make_switch_fingerprint(
            "d",
            screen_index=2,
            exact_hash="bad",
        )
        result = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[
                make_switch_observation(formal_three),
                make_switch_observation(None),
                make_switch_observation(confirmation),
                make_switch_observation(invalid),
                make_switch_observation(formal_one),
            ],
        )

        self.assertEqual(
            simple_brush.extract_formal_fingerprints(result),
            (formal_one, formal_three),
        )
        self.assertEqual(simple_brush.extract_formal_fingerprints(None), ())

    def test_formal_fingerprints_accept_exactly_eight(self):
        fingerprints = tuple(
            make_switch_fingerprint(
                format(screen_index, "x"),
                screen_index=screen_index,
            )
            for screen_index in range(1, 9)
        )
        result = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[
                make_switch_observation(fingerprint)
                for fingerprint in reversed(fingerprints)
            ],
        )

        self.assertEqual(
            simple_brush.extract_formal_fingerprints(result),
            fingerprints,
        )

    def test_formal_fingerprints_reject_invalid_or_duplicate_indexes(self):
        for invalid_index in (True, 0, 9, "1"):
            with self.subTest(screen_index=invalid_index):
                result = DetectionResult(
                    success=True,
                    confirmed_match=False,
                    observations=[make_switch_observation(
                        make_switch_fingerprint(
                            "a",
                            screen_index=invalid_index,
                        )
                    )],
                )
                with self.assertRaisesRegex(
                    ValueError,
                    "^formal fingerprint invariant failed$",
                ):
                    simple_brush.extract_formal_fingerprints(result)

        duplicate_result = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[
                make_switch_observation(
                    make_switch_fingerprint("a", screen_index=1)
                ),
                make_switch_observation(
                    make_switch_fingerprint("b", screen_index=1)
                ),
            ],
        )
        with self.assertRaisesRegex(
            ValueError,
            "^formal fingerprint invariant failed$",
        ):
            simple_brush.extract_formal_fingerprints(duplicate_result)

    def test_references_append_valid_pre_switch_baseline(self):
        formal = make_switch_fingerprint("a", screen_index=1)
        baseline = make_switch_fingerprint("b")
        context = simple_brush.CandidateSwitchContext((formal,), baseline)

        self.assertEqual(
            simple_brush.candidate_switch_references(context),
            (formal, baseline),
        )
        self.assertEqual(
            simple_brush.candidate_switch_references(
                simple_brush.CandidateSwitchContext((), baseline)
            ),
            (baseline,),
        )

    def test_references_reject_invalid_context_invariants(self):
        baseline = make_switch_fingerprint("f")
        too_many = tuple(
            make_switch_fingerprint(
                format(index % 16, "x"),
                screen_index=(index % 8) + 1,
            )
            for index in range(9)
        )
        contexts = (
            simple_brush.CandidateSwitchContext(
                too_many,
                baseline,
            ),
            simple_brush.CandidateSwitchContext(
                (make_switch_fingerprint("a", screen_index=0),),
                baseline,
            ),
            simple_brush.CandidateSwitchContext(
                (),
                make_switch_fingerprint("a", screen_index=1),
            ),
            simple_brush.CandidateSwitchContext(
                (),
                make_switch_fingerprint("a", exact_hash="bad"),
            ),
        )

        for context in contexts:
            with self.subTest(context=context):
                with self.assertRaisesRegex(
                    ValueError,
                    "^candidate switch context invariant failed$",
                ):
                    simple_brush.candidate_switch_references(context)

    def test_any_match_wins_even_when_another_comparison_is_none(self):
        current = make_switch_fingerprint("a")
        incompatible = make_switch_fingerprint(
            "b",
            fingerprint_version="r03-v2",
        )
        same = make_switch_fingerprint("a")

        self.assertIs(
            simple_brush.matches_any_previous_fingerprint(
                current,
                (incompatible, same),
            ),
            True,
        )
        self.assertIs(
            simple_brush.differs_from_all_previous_fingerprints(
                current,
                (incompatible, same),
            ),
            False,
        )

    def test_different_from_all_requires_every_comparison_false(self):
        current = make_switch_fingerprint("c")
        previous = (
            make_switch_fingerprint("a"),
            make_switch_fingerprint("b"),
        )

        self.assertIs(
            simple_brush.matches_any_previous_fingerprint(
                current,
                previous,
            ),
            False,
        )
        self.assertIs(
            simple_brush.differs_from_all_previous_fingerprints(
                current,
                previous,
            ),
            True,
        )

    def test_none_comparison_and_empty_previous_are_not_different(self):
        current = make_switch_fingerprint("a")
        incompatible = make_switch_fingerprint(
            "b",
            fingerprint_version="r03-v2",
        )

        self.assertIsNone(
            simple_brush.matches_any_previous_fingerprint(
                current,
                (incompatible,),
            )
        )
        self.assertIsNone(
            simple_brush.differs_from_all_previous_fingerprints(
                current,
                (incompatible,),
            )
        )
        self.assertIsNone(
            simple_brush.matches_any_previous_fingerprint(current, ())
        )
        self.assertIsNone(
            simple_brush.differs_from_all_previous_fingerprints(current, ())
        )

    def test_fingerprint_stability_is_exact_three_state(self):
        first = make_switch_fingerprint("a")
        same = make_switch_fingerprint("a")
        different = make_switch_fingerprint("b")
        incompatible = make_switch_fingerprint(
            "a",
            fingerprint_version="r03-v2",
        )

        self.assertIs(
            simple_brush.fingerprints_are_stable(first, same),
            True,
        )
        self.assertIs(
            simple_brush.fingerprints_are_stable(first, different),
            False,
        )
        self.assertIsNone(
            simple_brush.fingerprints_are_stable(first, incompatible)
        )

    def test_r02_not_ready_and_unknown_are_not_observing(self):
        current = make_switch_fingerprint("a")
        previous = (make_switch_fingerprint("b"),)

        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                False,
                current,
                previous,
                None,
                None,
            ),
            (simple_brush.CANDIDATE_SWITCH_LOADING, None),
        )
        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                None,
                current,
                previous,
                None,
                None,
            ),
            (simple_brush.CANDIDATE_SWITCH_UNVERIFIABLE, None),
        )

    def test_single_ready_old_or_new_is_only_observing(self):
        old = make_switch_fingerprint("a")
        new = make_switch_fingerprint("b")
        previous = (old,)

        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                True,
                old,
                previous,
                None,
                None,
            ),
            (simple_brush.CANDIDATE_SWITCH_OBSERVING, "old"),
        )
        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                True,
                new,
                previous,
                None,
                None,
            ),
            (simple_brush.CANDIDATE_SWITCH_OBSERVING, "new"),
        )

    def test_two_ready_stable_old_observations_are_unchanged(self):
        old_first = make_switch_fingerprint("a")
        old_second = make_switch_fingerprint("a")
        previous = (make_switch_fingerprint("a"),)

        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                True,
                old_second,
                previous,
                old_first,
                "old",
            ),
            (simple_brush.CANDIDATE_SWITCH_UNCHANGED, "old"),
        )

    def test_old_new_relation_changes_are_only_observing(self):
        old = make_switch_fingerprint("a")
        new = make_switch_fingerprint("b")
        previous = (old,)

        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                True,
                new,
                previous,
                old,
                "old",
            ),
            (simple_brush.CANDIDATE_SWITCH_OBSERVING, "new"),
        )
        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                True,
                old,
                previous,
                new,
                "new",
            ),
            (simple_brush.CANDIDATE_SWITCH_OBSERVING, "old"),
        )

    def test_two_ready_stable_new_observations_are_confirmed(self):
        previous = (
            make_switch_fingerprint("a"),
            make_switch_fingerprint("b"),
        )
        new_first = make_switch_fingerprint("c")
        new_second = make_switch_fingerprint("c")

        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                True,
                new_second,
                previous,
                new_first,
                "new",
            ),
            (simple_brush.CANDIDATE_SWITCH_CONFIRMED, "new"),
        )

    def test_two_different_new_observations_remain_observing(self):
        previous = (make_switch_fingerprint("a"),)
        new_first = make_switch_fingerprint("b")
        new_second = make_switch_fingerprint("c")

        self.assertEqual(
            simple_brush.evaluate_candidate_switch_observation(
                True,
                new_second,
                previous,
                new_first,
                "new",
            ),
            (simple_brush.CANDIDATE_SWITCH_OBSERVING, "new"),
        )

    def test_invalid_incompatible_or_unreferenced_observation_is_unverifiable(self):
        previous = (make_switch_fingerprint("a"),)
        incompatible = make_switch_fingerprint(
            "b",
            fingerprint_version="r03-v2",
        )

        for current, references in (
            (None, previous),
            (make_switch_fingerprint("b", exact_hash="bad"), previous),
            (incompatible, previous),
            (make_switch_fingerprint("b"), ()),
        ):
            with self.subTest(current=current, references=references):
                self.assertEqual(
                    simple_brush.evaluate_candidate_switch_observation(
                        True,
                        current,
                        references,
                        None,
                        None,
                    ),
                    (
                        simple_brush.CANDIDATE_SWITCH_UNVERIFIABLE,
                        None,
                    ),
                )

    def test_action_and_observation_budget_boundaries(self):
        self.assertFalse(
            simple_brush.candidate_switch_action_budget_exhausted(1)
        )
        self.assertTrue(
            simple_brush.candidate_switch_action_budget_exhausted(2)
        )
        self.assertTrue(
            simple_brush.candidate_switch_action_budget_exhausted(3)
        )
        self.assertFalse(
            simple_brush.candidate_switch_observation_budget_exhausted(5)
        )
        self.assertTrue(
            simple_brush.candidate_switch_observation_budget_exhausted(6)
        )
        self.assertTrue(
            simple_brush.candidate_switch_observation_budget_exhausted(7)
        )

    def test_only_first_unchanged_action_allows_focus_recovery(self):
        self.assertTrue(
            simple_brush.candidate_switch_focus_recovery_allowed(
                simple_brush.CANDIDATE_SWITCH_UNCHANGED,
                1,
            )
        )
        for state, action_attempt in (
            (simple_brush.CANDIDATE_SWITCH_UNCHANGED, 2),
            (simple_brush.CANDIDATE_SWITCH_PENDING, 1),
            (simple_brush.CANDIDATE_SWITCH_LOADING, 1),
            (simple_brush.CANDIDATE_SWITCH_OBSERVING, 1),
            (simple_brush.CANDIDATE_SWITCH_CONFIRMED, 1),
            (simple_brush.CANDIDATE_SWITCH_UNVERIFIABLE, 1),
            (simple_brush.CANDIDATE_SWITCH_FAILED, 1),
        ):
            with self.subTest(state=state, action_attempt=action_attempt):
                self.assertFalse(
                    simple_brush.candidate_switch_focus_recovery_allowed(
                        state,
                        action_attempt,
                    )
                )

    def test_only_confirmed_allows_formal_scan(self):
        self.assertTrue(simple_brush.candidate_switch_scan_allowed(
            simple_brush.CANDIDATE_SWITCH_CONFIRMED
        ))
        for state in (
            simple_brush.CANDIDATE_SWITCH_PENDING,
            simple_brush.CANDIDATE_SWITCH_LOADING,
            simple_brush.CANDIDATE_SWITCH_OBSERVING,
            simple_brush.CANDIDATE_SWITCH_UNCHANGED,
            simple_brush.CANDIDATE_SWITCH_UNVERIFIABLE,
            simple_brush.CANDIDATE_SWITCH_FAILED,
        ):
            with self.subTest(state=state):
                self.assertFalse(
                    simple_brush.candidate_switch_scan_allowed(state)
                )

    def test_pure_helpers_reference_no_side_effect_operations(self):
        forbidden_names = {
            "capture_observation",
            "human_scroll_once",
            "logger",
            "matching_keyword_rule",
            "next_candidate",
            "ocr_detector",
            "safe_wait",
            "sleep",
        }
        pure_helpers = (
            simple_brush.is_comparable_screen_fingerprint,
            simple_brush.extract_formal_fingerprints,
            simple_brush.candidate_switch_references,
            simple_brush.matches_any_previous_fingerprint,
            simple_brush.differs_from_all_previous_fingerprints,
            simple_brush.fingerprints_are_stable,
            simple_brush.evaluate_candidate_switch_observation,
            simple_brush.candidate_switch_action_budget_exhausted,
            simple_brush.candidate_switch_observation_budget_exhausted,
            simple_brush.candidate_switch_focus_recovery_allowed,
            simple_brush.candidate_switch_scan_allowed,
        )

        for helper in pure_helpers:
            with self.subTest(helper=helper.__name__):
                self.assertTrue(
                    forbidden_names.isdisjoint(helper.__code__.co_names)
                )


class SimpleBrushOCRTests(unittest.TestCase):
    def setUp(self):
        self.saved = {
            name: getattr(simple_brush, name)
            for name in (
                "forward_enabled",
                "forward_keywords",
                "forward_consecutive",
                "backup_email",
                "no_forward_mode",
                "action_mode",
                "forward_click_regions",
                "forward_click_calibration_requested",
                "forward_click_calibration_attempted",
                "forward_click_calibration_in_progress",
                "batch_filter_regions",
                "batch_filter_calibration_requested",
                "batch_filter_calibration_attempted",
                "batch_filter_calibration_in_progress",
                "batch_filter_enabled",
                "focus_restore_region",
                "focus_restore_calibration_requested",
                "focus_restore_calibration_attempted",
                "focus_restore_calibration_in_progress",
                "favorite_button_region",
                "selected_calibration_profile",
                "ocr_backend",
                "ocr_capture",
                "ocr_detector",
                "ocr_initialization_attempted",
                "ocr_calibration_attempted",
                "ocr_calibration_in_progress",
                "ocr_record_store",
                "current_candidate_builder",
                "candidate_record_sequence",
                "recorded_observation_ids",
                "stop_event",
                "stop_reason",
                "paused",
                "run_duration_seconds",
                "_programmatic_esc",
            )
        }
        simple_brush.forward_enabled = True
        simple_brush.forward_keywords = simple_brush.parse_keyword_rules('"Python"')
        simple_brush.forward_consecutive = 0
        simple_brush.backup_email = ""
        simple_brush.no_forward_mode = False
        simple_brush.action_mode = simple_brush.ACTION_MODE_FORWARD
        simple_brush.reset_forward_click_calibration()
        simple_brush.reset_batch_filter_calibration()
        simple_brush.reset_focus_restore_calibration()
        simple_brush.favorite_button_region = None
        simple_brush.selected_calibration_profile = None
        simple_brush.stop_event = False
        simple_brush.stop_reason = None
        simple_brush.paused = False
        simple_brush.run_duration_seconds = 0
        simple_brush._programmatic_esc = False
        self.disabled_ocr_store = Mock(
            enabled=False,
            run_id="disabled-test-run",
        )
        self.ocr_store_factory_patcher = patch.object(
            simple_brush,
            "create_ocr_record_store",
            return_value=self.disabled_ocr_store,
        )
        self.ocr_store_factory_patcher.start()

    def tearDown(self):
        self.ocr_store_factory_patcher.stop()
        for name, value in self.saved.items():
            setattr(simple_brush, name, value)

    def test_summary_fail_open_still_saves_candidate_without_page_actions(self):
        store = Mock(enabled=True, run_id="summary-fail-open-run")
        builder = CandidateOcrBuilder(
            store.run_id, 1, candidate_record_id="summary-fail-open-candidate",
            similarity_mode="record",
        )
        builder.build_screen_record(
            (OCRItem("synthetic", 0.95, None),),
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            screen_index=1,
            screen_id="summary-fail-open-screen",
        )
        simple_brush.ocr_record_store = store
        simple_brush.current_candidate_builder = builder
        page_actions = ("ocr_scroll_down", "human_scroll_once", "next_candidate", "refresh_page")

        with ExitStack() as stack:
            summary = stack.enter_context(patch(
                "ocr_candidate.recompute_similarity_summary",
                side_effect=RuntimeError("synthetic"),
            ))
            patched = [
                stack.enter_context(patch.object(simple_brush, name))
                for name in page_actions
            ]
            document = simple_brush.finalize_current_candidate_recording(
                CaptureStatus.COMPLETED, "existing_flow_completed",
            )

        self.assertEqual(summary.call_count, 1)
        self.assertIsNotNone(document)
        store.save_candidate.assert_called_once_with(
            document,
            owner_candidate_record_id="summary-fail-open-candidate",
        )
        self.assertTrue(builder.finalized)
        self.assertEqual(builder.retained_screen_count, 0)
        self.assertIsNone(simple_brush.current_candidate_builder)
        for action in patched:
            action.assert_not_called()

    def test_finalize_passes_owner_matching_normal_document_identity(self):
        store = Mock(enabled=True, run_id="normal-owner-run")
        builder = CandidateOcrBuilder(
            store.run_id, 1, candidate_record_id="normal-owner-candidate",
        )
        builder.build_screen_record(
            (OCRItem("synthetic", 0.95, None),),
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            screen_index=1,
            screen_id="normal-owner-screen",
        )
        simple_brush.ocr_record_store = store
        simple_brush.current_candidate_builder = builder

        document = simple_brush.finalize_current_candidate_recording(
            CaptureStatus.COMPLETED, "existing_flow_completed",
        )

        self.assertIsNotNone(document)
        store.save_candidate.assert_called_once_with(
            document,
            owner_candidate_record_id=document.candidate_record_id,
        )

    def run_load_gate_candidate(
        self,
        *,
        observation=None,
        capture_error=None,
        capture_sequence=None,
        keywords=True,
        action_mode=None,
        no_forward=False,
        batch_filter_enabled=True,
        recovery_available=False,
        recovery_result=(True, "reopen_completed"),
        recovery_side_effect=None,
        real_recovery=False,
        view_side_effect=None,
        info_side_effect=None,
    ):
        timer = Mock()
        detector = Mock()
        if capture_sequence is not None:
            detector.capture_observation.side_effect = capture_sequence
        elif capture_error is not None:
            detector.capture_observation.side_effect = capture_error
        else:
            detector.capture_observation.return_value = (
                observation or loaded_observation()
            )
        simple_brush.ocr_detector = detector

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = keywords
            simple_brush.forward_keywords = (
                simple_brush.parse_keyword_rules('"Python"') if keywords else []
            )
            simple_brush.batch_filter_enabled = batch_filter_enabled
            simple_brush.batch_filter_regions = (
                sample_batch_filter_regions()
                if recovery_available
                else None
            )
            simple_brush.action_mode = (
                action_mode or simple_brush.ACTION_MODE_FORWARD
            )
            simple_brush.no_forward_mode = no_forward

        def stop_after_view(*_args, **_kwargs):
            simple_brush.stop_event = True
            return False, None

        with ExitStack() as stack:
            stack.enter_context(patch.object(
                simple_brush,
                "parse_args",
                return_value={
                    "keywords": "",
                    "email": "",
                    "duration_seconds": "",
                    "no_forward": no_forward,
                    "auto": False,
                },
            ))
            stack.enter_context(patch.object(
                simple_brush,
                "get_user_input",
                side_effect=configure_input,
            ))
            initialize_ocr = stack.enter_context(
                patch.object(simple_brush, "initialize_ocr")
            )
            stack.enter_context(patch.object(simple_brush.listener, "start"))
            stack.enter_context(patch.object(
                simple_brush,
                "bring_edge_foreground",
                return_value=True,
            ))
            position = stack.enter_context(patch.object(
                simple_brush.pyautogui,
                "position",
                return_value=(10, 20),
            ))
            press = stack.enter_context(
                patch.object(simple_brush.pyautogui, "press")
            )
            open_first = stack.enter_context(patch.object(
                simple_brush,
                "open_first_candidate_for_batch",
                return_value=True,
            ))
            wait = stack.enter_context(patch.object(
                simple_brush,
                "safe_wait",
                return_value=True,
            ))
            ensure_ocr = stack.enter_context(patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                return_value=True,
            ))
            stack.enter_context(patch.object(
                simple_brush,
                "ensure_favorite_button_region_calibrated",
                return_value=simple_brush.ScreenRegion(10, 20, 30, 40),
            ))
            stack.enter_context(patch.object(
                simple_brush,
                "start_run_timer",
                return_value=timer,
            ))
            detect_keywords = stack.enter_context(
                patch.object(simple_brush, "detect_keywords")
            )
            ocr_scroll = stack.enter_context(
                patch.object(simple_brush, "ocr_scroll_down")
            )
            human_scroll = stack.enter_context(
                patch.object(simple_brush, "human_scroll_once")
            )
            favorite_action = stack.enter_context(
                patch.object(simple_brush, "perform_favorite_action")
            )
            forward_action = stack.enter_context(
                patch.object(simple_brush, "forward_one_candidate")
            )
            favorite_focus_restore = stack.enter_context(patch.object(
                simple_brush,
                "restore_candidate_page_focus_after_favorite",
            ))
            view = stack.enter_context(patch.object(
                simple_brush,
                "view_candidate",
                side_effect=view_side_effect or stop_after_view,
            ))
            next_candidate = stack.enter_context(
                patch.object(simple_brush, "next_candidate")
            )
            if real_recovery:
                refresh = stack.enter_context(patch.object(
                    simple_brush,
                    "refresh_page",
                    wraps=simple_brush.refresh_page,
                ))
                apply_reopen = stack.enter_context(patch.object(
                    simple_brush,
                    "apply_batch_filter_and_open_first_candidate",
                    return_value=True,
                ))
                recover = stack.enter_context(patch.object(
                    simple_brush,
                    "recover_detail_page",
                    wraps=simple_brush.recover_detail_page,
                ))
            else:
                refresh = stack.enter_context(
                    patch.object(simple_brush, "refresh_page")
                )
                apply_reopen = None
                recover = stack.enter_context(patch.object(
                    simple_brush,
                    "recover_detail_page",
                    return_value=recovery_result,
                    side_effect=recovery_side_effect,
                ))
            info = stack.enter_context(
                patch.object(
                    simple_brush.logger,
                    "info",
                    side_effect=info_side_effect,
                )
            )
            warning = stack.enter_context(
                patch.object(simple_brush.logger, "warning")
            )
            error = stack.enter_context(
                patch.object(simple_brush.logger, "error")
            )
            result = simple_brush.run()

        return {
            "result": result,
            "timer": timer,
            "detector": detector,
            "initialize_ocr": initialize_ocr,
            "ensure_ocr": ensure_ocr,
            "position": position,
            "press": press,
            "open_first": open_first,
            "wait": wait,
            "detect_keywords": detect_keywords,
            "ocr_scroll": ocr_scroll,
            "human_scroll": human_scroll,
            "favorite_action": favorite_action,
            "forward_action": forward_action,
            "favorite_focus_restore": favorite_focus_restore,
            "view": view,
            "next_candidate": next_candidate,
            "refresh": refresh,
            "apply_reopen": apply_reopen,
            "recover": recover,
            "info": info,
            "warning": warning,
            "error": error,
        }

    def run_candidate_switch_confirmation(
        self,
        observations,
        *,
        context=None,
        next_result=True,
        next_side_effect=None,
        focus_result=True,
        focus_side_effect=None,
        wait_side_effect=None,
    ):
        detector = Mock()
        detector.capture_observation.side_effect = observations
        simple_brush.ocr_detector = detector
        if context is None:
            old = make_switch_fingerprint("a", screen_index=1)
            baseline = make_switch_fingerprint("a")
            context = simple_brush.CandidateSwitchContext(
                (old,),
                baseline,
            )

        with (
            patch.object(
                simple_brush,
                "next_candidate",
                return_value=next_result,
                side_effect=next_side_effect,
            ) as next_candidate,
            patch.object(
                simple_brush,
                "safe_wait",
                return_value=True,
                side_effect=wait_side_effect,
            ) as wait,
            patch.object(simple_brush, "ocr_scroll_down") as ocr_scroll,
            patch.object(simple_brush, "human_scroll_once") as human_scroll,
            patch.object(
                simple_brush,
                "perform_favorite_action",
            ) as favorite,
            patch.object(
                simple_brush,
                "forward_one_candidate",
            ) as forward,
            patch.object(simple_brush, "refresh_page") as refresh,
            patch.object(
                simple_brush,
                "restore_candidate_detail_focus",
                return_value=focus_result,
                side_effect=focus_side_effect,
            ) as focus_restore,
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "warning") as warning,
            patch.object(simple_brush.logger, "error") as error,
        ):
            result = simple_brush.confirm_candidate_switch(
                context,
                candidate_in_batch=2,
                total_viewed=1,
            )

        return {
            "result": result,
            "detector": detector,
            "next": next_candidate,
            "wait": wait,
            "ocr_scroll": ocr_scroll,
            "human_scroll": human_scroll,
            "favorite": favorite,
            "forward": forward,
            "refresh": refresh,
            "focus_restore": focus_restore,
            "info": info,
            "warning": warning,
            "error": error,
        }

    def run_mocked_keyword_switch(
        self,
        switch_result,
        *,
        action_mode=simple_brush.ACTION_MODE_FORWARD,
        no_forward=True,
        stop_on_view_call=2,
        refresh_result=False,
        batch_filter_enabled=False,
    ):
        first_observation = loaded_observation()
        first_detection = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[],
        )
        context = simple_brush.CandidateSwitchContext(
            (make_switch_fingerprint("a", screen_index=1),),
            make_switch_fingerprint("a"),
        )
        view_calls = 0

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = True
            simple_brush.forward_keywords = (
                simple_brush.parse_keyword_rules('"Python"')
            )
            simple_brush.batch_filter_enabled = batch_filter_enabled
            simple_brush.batch_filter_regions = (
                sample_batch_filter_regions()
                if batch_filter_enabled
                else None
            )
            simple_brush.no_forward_mode = no_forward
            simple_brush.action_mode = action_mode

        def view_side_effect(_index, first_observation=None):
            nonlocal view_calls
            view_calls += 1
            if view_calls == stop_on_view_call:
                simple_brush.stop_event = True
                simple_brush.stop_reason = "esc"
                return False, first_detection
            return True, first_detection

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush, "BATCH_SIZE", 2))
            stack.enter_context(patch.object(
                simple_brush,
                "parse_args",
                return_value={
                    "keywords": "",
                    "email": "",
                    "duration_seconds": "",
                    "no_forward": no_forward,
                    "auto": False,
                },
            ))
            stack.enter_context(patch.object(
                simple_brush,
                "get_user_input",
                side_effect=configure_input,
            ))
            stack.enter_context(patch.object(simple_brush, "initialize_ocr"))
            stack.enter_context(patch.object(simple_brush.listener, "start"))
            stack.enter_context(patch.object(
                simple_brush,
                "bring_edge_foreground",
                return_value=True,
            ))
            stack.enter_context(patch.object(
                simple_brush,
                "safe_wait",
                return_value=True,
            ))
            stack.enter_context(patch.object(
                simple_brush.pyautogui,
                "position",
                return_value=(10, 20),
            ))
            open_first = stack.enter_context(patch.object(
                simple_brush,
                "click_first_candidate",
                return_value=True,
            ))
            filter_open = stack.enter_context(patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                return_value=True,
            ))
            stack.enter_context(patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                return_value=True,
            ))
            stack.enter_context(patch.object(
                simple_brush,
                "ensure_favorite_button_region_calibrated",
                return_value=simple_brush.ScreenRegion(10, 20, 30, 40),
            ))
            load_gate = stack.enter_context(patch.object(
                simple_brush,
                "run_detail_load_gate",
                return_value=(
                    "loaded",
                    first_observation,
                    0,
                    "threshold_passed",
                ),
            ))
            view = stack.enter_context(patch.object(
                simple_brush,
                "view_candidate",
                side_effect=view_side_effect,
            ))
            prepare_context = stack.enter_context(patch.object(
                simple_brush,
                "prepare_candidate_switch_context",
                return_value=(context, None),
            ))
            confirm_switch = stack.enter_context(patch.object(
                simple_brush,
                "confirm_candidate_switch",
                return_value=switch_result,
            ))
            next_candidate = stack.enter_context(patch.object(
                simple_brush,
                "next_candidate",
            ))
            favorite = stack.enter_context(patch.object(
                simple_brush,
                "perform_favorite_action",
            ))
            forward = stack.enter_context(patch.object(
                simple_brush,
                "forward_one_candidate",
            ))
            refresh = stack.enter_context(patch.object(
                simple_brush,
                "refresh_page",
                return_value=refresh_result,
            ))
            stack.enter_context(patch.object(
                simple_brush,
                "start_run_timer",
                return_value=None,
            ))
            info = stack.enter_context(patch.object(
                simple_brush.logger,
                "info",
            ))
            warning = stack.enter_context(patch.object(
                simple_brush.logger,
                "warning",
            ))
            error = stack.enter_context(patch.object(
                simple_brush.logger,
                "error",
            ))
            result = simple_brush.run()

        return {
            "result": result,
            "first_observation": first_observation,
            "context": context,
            "open_first": open_first,
            "filter_open": filter_open,
            "load_gate": load_gate,
            "view": view,
            "prepare_context": prepare_context,
            "confirm_switch": confirm_switch,
            "next_candidate": next_candidate,
            "favorite": favorite,
            "forward": forward,
            "refresh": refresh,
            "info": info,
            "warning": warning,
            "error": error,
        }

    def test_prepare_switch_context_uses_one_dedicated_baseline(self):
        formal_three = make_switch_fingerprint("3", screen_index=3)
        formal_one = make_switch_fingerprint("1", screen_index=1)
        confirmation = make_switch_fingerprint("c")
        detection_result = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[
                make_switch_observation(formal_three),
                make_switch_observation(confirmation),
                make_switch_observation(None),
                make_switch_observation(formal_one),
            ],
        )
        baseline_observation = make_ready_switch_observation("b")
        detector = Mock()
        detector.capture_observation.return_value = baseline_observation
        simple_brush.ocr_detector = detector

        context, reason = simple_brush.prepare_candidate_switch_context(
            detection_result,
            candidate_in_batch=1,
            total_viewed=1,
        )

        self.assertIsNone(reason)
        self.assertEqual(
            context.formal_fingerprints,
            (formal_one, formal_three),
        )
        self.assertIs(
            context.pre_switch_fingerprint,
            baseline_observation.fingerprint,
        )
        self.assertEqual(
            [
                fingerprint.fingerprint_version
                for fingerprint in context.formal_fingerprints
            ],
            ["r03-v1", "r03-v1"],
        )
        self.assertEqual(
            context.pre_switch_fingerprint.fingerprint_version,
            "r03-v1",
        )
        self.assertIsNone(context.pre_switch_fingerprint.screen_index)
        detector.capture_observation.assert_called_once_with(1)
        detector.detect.assert_not_called()

    def test_prepare_switch_context_allows_baseline_only(self):
        baseline_observation = make_ready_switch_observation("b")
        detector = Mock()
        detector.capture_observation.return_value = baseline_observation
        simple_brush.ocr_detector = detector

        context, reason = simple_brush.prepare_candidate_switch_context(
            None,
            candidate_in_batch=1,
            total_viewed=1,
        )

        self.assertIsNone(reason)
        self.assertEqual(context.formal_fingerprints, ())
        self.assertEqual(
            simple_brush.candidate_switch_references(context),
            (baseline_observation.fingerprint,),
        )

    def test_prepare_switch_context_fails_closed_before_next(self):
        invalid_baselines = (
            make_ready_switch_observation("a", ready=False),
            make_ready_switch_observation("a", fingerprint=False),
            make_ready_switch_observation("a", screen_index=1),
            make_ready_switch_observation(
                "a",
                fingerprint_version="",
            ),
        )

        for baseline in invalid_baselines:
            with self.subTest(baseline=baseline):
                detector = Mock()
                detector.capture_observation.return_value = baseline
                simple_brush.ocr_detector = detector
                with patch.object(
                    simple_brush,
                    "next_candidate",
                ) as next_candidate:
                    context, reason = (
                        simple_brush.prepare_candidate_switch_context(
                            None,
                            candidate_in_batch=1,
                            total_viewed=1,
                        )
                    )

                self.assertIsNone(context)
                self.assertEqual(
                    reason,
                    "pre_switch_baseline_unavailable",
                )
                detector.capture_observation.assert_called_once_with(1)
                next_candidate.assert_not_called()

    def test_confirm_switch_stable_new_returns_last_observation(self):
        new_first = make_ready_switch_observation("b")
        new_second = make_ready_switch_observation("b")

        with patch.object(
            simple_brush,
            "evaluate_detail_page_load",
            wraps=simple_brush.evaluate_detail_page_load,
        ) as readiness:
            calls = self.run_candidate_switch_confirmation([
                new_first,
                new_second,
            ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_CONFIRMED)
        self.assertEqual(result.action_attempt, 1)
        self.assertEqual(result.observation_attempt, 2)
        self.assertIs(result.confirmed_observation, new_second)
        self.assertIsNone(result.failure_reason)
        calls["next"].assert_called_once_with()
        calls["focus_restore"].assert_not_called()
        self.assertEqual(
            calls["detector"].capture_observation.call_args_list,
            [call(1), call(1)],
        )
        calls["wait"].assert_called_once_with(
            simple_brush.CANDIDATE_SWITCH_OBSERVATION_WAIT_SECONDS
        )
        self.assertIsNone(new_first.fingerprint.screen_index)
        self.assertIsNone(new_second.fingerprint.screen_index)
        self.assertEqual(new_first.fingerprint.fingerprint_version, "r03-v1")
        self.assertEqual(new_second.fingerprint.fingerprint_version, "r03-v1")
        self.assertEqual(readiness.call_count, 2)
        self.assertEqual(
            readiness.call_args_list[0],
            call(
                6,
                30,
                simple_brush.OCR_BOX_COUNT_THRESHOLD,
                simple_brush.OCR_TEXT_LENGTH_THRESHOLD,
            ),
        )

    def test_confirm_switch_old_then_two_new_is_confirmed(self):
        old = make_ready_switch_observation("a")
        new_first = make_ready_switch_observation("b")
        new_second = make_ready_switch_observation("b")

        calls = self.run_candidate_switch_confirmation([
            old,
            new_first,
            new_second,
        ])

        self.assertEqual(
            calls["result"].state,
            simple_brush.CANDIDATE_SWITCH_CONFIRMED,
        )
        self.assertIs(calls["result"].confirmed_observation, new_second)
        calls["next"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 3)
        self.assertEqual(
            calls["wait"].call_args_list,
            [
                call(simple_brush.CANDIDATE_SWITCH_OBSERVATION_WAIT_SECONDS),
                call(simple_brush.CANDIDATE_SWITCH_OBSERVATION_WAIT_SECONDS),
            ],
        )

    def test_confirm_switch_loading_then_stable_new_uses_one_next(self):
        calls = self.run_candidate_switch_confirmation([
            make_ready_switch_observation("b", ready=False),
            make_ready_switch_observation("b", ready=False),
            make_ready_switch_observation("b"),
            make_ready_switch_observation("b"),
        ])

        self.assertEqual(
            calls["result"].state,
            simple_brush.CANDIDATE_SWITCH_CONFIRMED,
        )
        calls["next"].assert_called_once_with()
        calls["focus_restore"].assert_not_called()
        self.assertEqual(calls["detector"].capture_observation.call_count, 4)
        self.assertEqual(calls["wait"].call_count, 3)

    def test_confirm_switch_full_old_action_consumes_budget_before_retry(self):
        confirmed = make_ready_switch_observation("b")
        calls = self.run_candidate_switch_confirmation([
            *[make_ready_switch_observation("a") for _ in range(6)],
            make_ready_switch_observation("b"),
            confirmed,
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_CONFIRMED)
        self.assertEqual(result.action_attempt, 2)
        self.assertEqual(result.observation_attempt, 2)
        self.assertIs(result.confirmed_observation, confirmed)
        self.assertEqual(calls["next"].call_args_list, [call(), call()])
        calls["focus_restore"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 8)
        self.assertEqual(calls["wait"].call_count, 6)

    def test_confirm_switch_old_old_then_new_new_confirms_first_action(self):
        confirmed = make_ready_switch_observation("b")
        calls = self.run_candidate_switch_confirmation([
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("b"),
            confirmed,
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_CONFIRMED)
        self.assertEqual(result.action_attempt, 1)
        self.assertEqual(result.observation_attempt, 4)
        self.assertIs(result.confirmed_observation, confirmed)
        calls["next"].assert_called_once_with()
        calls["focus_restore"].assert_not_called()
        self.assertEqual(calls["detector"].capture_observation.call_count, 4)
        calls["detector"].detect.assert_not_called()

    def test_confirm_switch_loading_disqualifies_unchanged_retry(self):
        calls = self.run_candidate_switch_confirmation([
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a", ready=False),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(result.action_attempt, 1)
        self.assertEqual(result.observation_attempt, 6)
        self.assertEqual(result.failure_reason, "observation_budget_exhausted")
        calls["next"].assert_called_once_with()
        calls["focus_restore"].assert_not_called()
        self.assertEqual(calls["detector"].capture_observation.call_count, 6)
        calls["detector"].detect.assert_not_called()

    def test_confirm_switch_unverifiable_disqualifies_unchanged_retry(self):
        calls = self.run_candidate_switch_confirmation([
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a", fingerprint=False),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(result.action_attempt, 1)
        self.assertEqual(result.observation_attempt, 6)
        self.assertEqual(result.failure_reason, "comparison_unverifiable")
        calls["next"].assert_called_once_with()
        calls["focus_restore"].assert_not_called()
        self.assertEqual(calls["detector"].capture_observation.call_count, 6)

    def test_confirm_switch_new_seen_disqualifies_later_old_retry(self):
        calls = self.run_candidate_switch_confirmation([
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("b"),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
            make_ready_switch_observation("a"),
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(result.action_attempt, 1)
        self.assertEqual(result.observation_attempt, 6)
        self.assertEqual(result.failure_reason, "observation_budget_exhausted")
        calls["next"].assert_called_once_with()
        calls["focus_restore"].assert_not_called()
        self.assertEqual(calls["detector"].capture_observation.call_count, 6)

    def test_confirm_switch_second_full_old_action_fails_at_full_budget(self):
        calls = self.run_candidate_switch_confirmation([
            *[make_ready_switch_observation("a") for _ in range(12)],
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(result.action_attempt, 2)
        self.assertEqual(result.observation_attempt, 6)
        self.assertEqual(
            result.failure_reason,
            "stable_unchanged_after_retry",
        )
        self.assertEqual(calls["next"].call_args_list, [call(), call()])
        calls["focus_restore"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 12)
        self.assertEqual(calls["wait"].call_count, 10)

    def test_confirm_switch_first_unchanged_recovers_then_confirms(self):
        confirmed = make_ready_switch_observation("b")
        calls = self.run_candidate_switch_confirmation([
            *[make_ready_switch_observation("a") for _ in range(6)],
            make_ready_switch_observation("b"),
            confirmed,
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_CONFIRMED)
        self.assertEqual(result.action_attempt, 2)
        self.assertEqual(result.observation_attempt, 2)
        self.assertIs(result.confirmed_observation, confirmed)
        self.assertIsNone(result.failure_reason)
        self.assertEqual(calls["next"].call_args_list, [call(), call()])
        calls["focus_restore"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 8)
        self.assertEqual(calls["wait"].call_count, 6)
        calls["favorite"].assert_not_called()
        calls["forward"].assert_not_called()
        calls["refresh"].assert_not_called()

    def test_confirm_switch_second_unchanged_fails_without_third_next(self):
        calls = self.run_candidate_switch_confirmation([
            *[make_ready_switch_observation("a") for _ in range(12)],
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(result.action_attempt, 2)
        self.assertEqual(result.observation_attempt, 6)
        self.assertEqual(
            result.failure_reason,
            "stable_unchanged_after_retry",
        )
        self.assertIsNone(result.confirmed_observation)
        self.assertEqual(calls["next"].call_args_list, [call(), call()])
        calls["focus_restore"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 12)

    def test_confirm_switch_second_loading_then_stable_new_confirms(self):
        confirmed = make_ready_switch_observation("b")
        calls = self.run_candidate_switch_confirmation([
            *[make_ready_switch_observation("a") for _ in range(6)],
            make_ready_switch_observation("b", ready=False),
            make_ready_switch_observation("b"),
            confirmed,
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_CONFIRMED)
        self.assertEqual(result.action_attempt, 2)
        self.assertEqual(result.observation_attempt, 3)
        self.assertIs(result.confirmed_observation, confirmed)
        self.assertEqual(calls["next"].call_args_list, [call(), call()])
        calls["focus_restore"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 9)
        self.assertEqual(calls["wait"].call_count, 7)

    def test_confirm_switch_second_unstable_exhausts_fresh_budget(self):
        calls = self.run_candidate_switch_confirmation([
            *[make_ready_switch_observation("a") for _ in range(6)],
            *[
                make_ready_switch_observation(character)
                for character in ("b", "c", "d", "e", "f", "0")
            ],
        ])

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(result.action_attempt, 2)
        self.assertEqual(
            result.observation_attempt,
            simple_brush.CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION,
        )
        self.assertEqual(
            result.failure_reason,
            "observation_budget_exhausted",
        )
        self.assertEqual(calls["next"].call_args_list, [call(), call()])
        calls["focus_restore"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 12)
        self.assertEqual(calls["wait"].call_count, 10)

    def test_confirm_switch_focus_recovery_failure_stops_before_retry(self):
        for focus_side_effect, focus_result in (
            (None, False),
            (RuntimeError("focus unavailable"), True),
        ):
            with self.subTest(focus_side_effect=focus_side_effect):
                calls = self.run_candidate_switch_confirmation(
                    [make_ready_switch_observation("a") for _ in range(6)],
                    focus_result=focus_result,
                    focus_side_effect=focus_side_effect,
                )

                result = calls["result"]
                self.assertEqual(
                    result.state,
                    simple_brush.CANDIDATE_SWITCH_FAILED,
                )
                self.assertEqual(result.action_attempt, 1)
                self.assertEqual(
                    result.failure_reason,
                    "focus_recovery_failed",
                )
                calls["next"].assert_called_once_with()
                calls["focus_restore"].assert_called_once_with()
                self.assertEqual(
                    calls["detector"].capture_observation.call_count,
                    6,
                )

    def test_confirm_switch_stop_during_focus_prevents_second_next(self):
        def stop_during_focus():
            simple_brush.stop_event = True
            simple_brush.stop_reason = "esc"
            return True

        calls = self.run_candidate_switch_confirmation(
            [make_ready_switch_observation("a") for _ in range(6)],
            focus_side_effect=stop_during_focus,
        )

        self.assertIsNone(calls["result"])
        calls["next"].assert_called_once_with()
        calls["focus_restore"].assert_called_once_with()

    def test_confirm_switch_stop_during_observation_wait_prevents_actions(self):
        def stop_during_wait(_seconds):
            simple_brush.stop_event = True
            simple_brush.stop_reason = "run_duration_elapsed"
            return False

        calls = self.run_candidate_switch_confirmation(
            [make_ready_switch_observation("b")],
            wait_side_effect=stop_during_wait,
        )

        self.assertIsNone(calls["result"])
        calls["next"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 1)
        calls["focus_restore"].assert_not_called()

    def test_confirm_switch_next_failure_observes_nothing(self):
        calls = self.run_candidate_switch_confirmation(
            [],
            next_result=False,
        )

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(result.failure_reason, "next_action_failed")
        self.assertEqual(result.observation_attempt, 0)
        calls["next"].assert_called_once_with()
        calls["detector"].capture_observation.assert_not_called()
        calls["wait"].assert_not_called()
        calls["focus_restore"].assert_not_called()

    def test_confirm_switch_second_next_failure_stops_without_observation(self):
        calls = self.run_candidate_switch_confirmation(
            [make_ready_switch_observation("a") for _ in range(6)],
            next_side_effect=[True, False],
        )

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(result.action_attempt, 2)
        self.assertEqual(result.observation_attempt, 0)
        self.assertEqual(result.failure_reason, "next_action_failed")
        self.assertEqual(calls["next"].call_args_list, [call(), call()])
        calls["focus_restore"].assert_called_once_with()
        self.assertEqual(calls["detector"].capture_observation.call_count, 6)

    def test_candidate_switch_failure_sets_only_the_first_stop_reason(self):
        result = simple_brush.CandidateSwitchResult(
            state=simple_brush.CANDIDATE_SWITCH_FAILED,
            action_attempt=1,
            observation_attempt=6,
            failure_reason="comparison_unverifiable",
        )

        with patch.object(simple_brush.logger, "error") as error:
            simple_brush.request_candidate_switch_failed_stop(
                result,
                candidate_in_batch=2,
                total_viewed=1,
            )
            simple_brush.request_candidate_switch_failed_stop(
                result,
                candidate_in_batch=2,
                total_viewed=1,
            )

        self.assertTrue(simple_brush.stop_event)
        self.assertEqual(
            simple_brush.stop_reason,
            "candidate_switch_failed",
        )
        error.assert_called_once()
        failed_log = render_log_calls(error)[0]
        self.assertIn("event=candidate_switch_failed", failed_log)
        self.assertIn("phase=post_next", failed_log)
        self.assertIn("state=switch_failed", failed_log)
        self.assertIn("action_attempt=1", failed_log)
        self.assertIn("observation_attempt=6", failed_log)
        self.assertIn("current_hash=-", failed_log)
        self.assertIn("failure_reason=comparison_unverifiable", failed_log)
        self.assertIn("stop_reason=candidate_switch_failed", failed_log)
        self.assertIn("candidate_in_batch=2", failed_log)
        self.assertIn("total_viewed=1", failed_log)

        for existing_reason in (
            "esc",
            "run_duration_elapsed",
            "load_failed",
        ):
            with self.subTest(existing_reason=existing_reason):
                simple_brush.stop_event = True
                simple_brush.stop_reason = existing_reason
                with patch.object(simple_brush.logger, "error") as error:
                    simple_brush.request_candidate_switch_failed_stop(
                        result,
                        candidate_in_batch=2,
                        total_viewed=1,
                    )
                self.assertEqual(simple_brush.stop_reason, existing_reason)
                error.assert_not_called()

    def test_confirm_switch_unstable_new_exhausts_six_observations(self):
        observations = [
            make_ready_switch_observation(character)
            for character in ("b", "c", "d", "e", "f", "0")
        ]

        calls = self.run_candidate_switch_confirmation(observations)

        result = calls["result"]
        self.assertEqual(result.state, simple_brush.CANDIDATE_SWITCH_FAILED)
        self.assertEqual(
            result.observation_attempt,
            simple_brush.CANDIDATE_SWITCH_MAX_OBSERVATIONS_PER_ACTION,
        )
        self.assertEqual(
            result.failure_reason,
            "observation_budget_exhausted",
        )
        self.assertEqual(calls["detector"].capture_observation.call_count, 6)
        self.assertEqual(calls["wait"].call_count, 5)
        calls["next"].assert_called_once_with()
        calls["focus_restore"].assert_not_called()

    def test_confirm_switch_unverifiable_observations_are_bounded(self):
        scenarios = (
            [
                make_ready_switch_observation("b", fingerprint=False)
                for _ in range(6)
            ],
            [
                make_ready_switch_observation(
                    "b",
                    fingerprint_version="r03-v2",
                )
                for _ in range(6)
            ],
            [RuntimeError("capture unavailable") for _ in range(6)],
        )

        for observations in scenarios:
            with self.subTest(observations=observations):
                calls = self.run_candidate_switch_confirmation(observations)
                result = calls["result"]
                self.assertEqual(
                    result.state,
                    simple_brush.CANDIDATE_SWITCH_FAILED,
                )
                self.assertEqual(
                    result.failure_reason,
                    "comparison_unverifiable",
                )
                self.assertEqual(
                    calls["detector"].capture_observation.call_count,
                    6,
                )
                self.assertEqual(calls["wait"].call_count, 5)
                calls["next"].assert_called_once_with()
                calls["focus_restore"].assert_not_called()

    def test_confirm_switch_performs_no_business_or_navigation_side_effects(self):
        calls = self.run_candidate_switch_confirmation([
            make_ready_switch_observation("b"),
            make_ready_switch_observation("b"),
        ])

        calls["ocr_scroll"].assert_not_called()
        calls["human_scroll"].assert_not_called()
        calls["favorite"].assert_not_called()
        calls["forward"].assert_not_called()
        calls["refresh"].assert_not_called()
        calls["detector"].detect.assert_not_called()
        calls["focus_restore"].assert_not_called()

    def test_candidate_switch_logs_use_five_frozen_events_and_fields(self):
        formal = make_switch_fingerprint("a", screen_index=1)
        baseline_observation = make_ready_switch_observation("a")
        simple_brush.ocr_detector = Mock()
        simple_brush.ocr_detector.capture_observation.return_value = (
            baseline_observation
        )
        detection_result = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[make_switch_observation(formal)],
        )

        with (
            patch.object(simple_brush.logger, "info") as baseline_info,
            patch.object(simple_brush.logger, "warning") as baseline_warning,
        ):
            context, reason = simple_brush.prepare_candidate_switch_context(
                detection_result,
                candidate_in_batch=1,
                total_viewed=1,
            )

        self.assertIsNone(reason)
        baseline_warning.assert_not_called()
        calls = self.run_candidate_switch_confirmation(
            [
                *[make_ready_switch_observation("a") for _ in range(6)],
                make_ready_switch_observation("b"),
                make_ready_switch_observation("b"),
            ],
            context=context,
        )
        failed_result = simple_brush.CandidateSwitchResult(
            state=simple_brush.CANDIDATE_SWITCH_FAILED,
            action_attempt=2,
            observation_attempt=6,
            failure_reason="observation_budget_exhausted",
        )
        with patch.object(simple_brush.logger, "error") as failed_error:
            simple_brush.request_candidate_switch_failed_stop(
                failed_result,
                candidate_in_batch=3,
                total_viewed=2,
            )

        info_logs = render_log_calls(baseline_info, calls["info"])
        warning_logs = render_log_calls(calls["warning"])
        error_logs = render_log_calls(failed_error)
        r01_logs = [
            line
            for line in info_logs + warning_logs + error_logs
            if line.startswith("event=candidate_switch_")
        ]
        event_names = {
            line.split(" ", 1)[0].split("=", 1)[1]
            for line in r01_logs
        }
        self.assertEqual(
            event_names,
            {
                "candidate_switch_check",
                "candidate_switch_focus_recovery",
                "candidate_switch_retry",
                "candidate_switch_confirmed",
                "candidate_switch_failed",
            },
        )
        self.assertEqual(
            sum("event=candidate_switch_check" in line for line in r01_logs),
            9,
        )
        self.assertEqual(
            sum("event=candidate_switch_confirmed" in line for line in r01_logs),
            1,
        )
        self.assertEqual(
            sum("event=candidate_switch_failed" in line for line in r01_logs),
            1,
        )
        self.assertTrue(all(
            "event=candidate_switch_check" in line
            or "event=candidate_switch_confirmed" in line
            for line in info_logs
            if line.startswith("event=candidate_switch_")
        ))
        self.assertEqual(
            {
                line.split(" ", 1)[0]
                for line in warning_logs
                if line.startswith("event=candidate_switch_")
            },
            {
                "event=candidate_switch_focus_recovery",
                "event=candidate_switch_retry",
            },
        )
        self.assertEqual(
            [line.split(" ", 1)[0] for line in error_logs],
            ["event=candidate_switch_failed"],
        )
        required_fields = (
            "phase=",
            "state=",
            "action_attempt=",
            "observation_attempt=",
            "old_fingerprint_count=",
            "current_hash=-",
            "compare_relation=",
            "r02_ready=",
            "r02_reason=",
            "failure_reason=",
            "stop_reason=",
            "candidate_in_batch=",
            "total_viewed=",
        )
        self.assertTrue(all(
            all(field in line for field in required_fields)
            for line in r01_logs
        ))

    def test_candidate_switch_logs_do_not_leak_private_page_data(self):
        private_marker = "PRIVATE_R01_SWITCH_BODY_7D4F"
        private_exception = (
            f"{private_marker} OCRItem coordinate=(123,456) "
            "confidence=0.987"
        )

        def private_fingerprint(character, *, screen_index=None):
            return ScreenFingerprint(
                raw_text=private_marker,
                normalized_text=private_marker,
                raw_text_length=len(private_marker),
                normalized_text_length=len(private_marker),
                ocr_box_count=1,
                captured_at="2026-01-01T00:00:00+00:00",
                exact_hash=character * 64,
                fingerprint_version="r03-v1",
                screen_index=screen_index,
            )

        def private_observation(character):
            return ScanObservation(
                scan_number=1,
                text=private_marker,
                item_count=6,
                elapsed_seconds=0.987,
                ocr_box_count=6,
                ocr_text_length=30,
                fingerprint=private_fingerprint(character),
            )

        formal = private_fingerprint("a", screen_index=1)
        baseline = private_observation("a")
        simple_brush.ocr_detector = Mock()
        simple_brush.ocr_detector.capture_observation.return_value = baseline
        with patch.object(simple_brush.logger, "info") as baseline_info:
            context, reason = simple_brush.prepare_candidate_switch_context(
                DetectionResult(
                    success=True,
                    confirmed_match=False,
                    observations=[make_switch_observation(formal)],
                ),
                candidate_in_batch=1,
                total_viewed=1,
            )
        self.assertIsNone(reason)

        confirmed_calls = self.run_candidate_switch_confirmation(
            [
                private_observation("a"),
                private_observation("a"),
                private_observation("b"),
                private_observation("b"),
            ],
            context=context,
        )
        failed_calls = self.run_candidate_switch_confirmation(
            [RuntimeError(private_exception) for _ in range(6)],
            context=context,
        )
        simple_brush.stop_event = False
        simple_brush.stop_reason = None
        with patch.object(simple_brush.logger, "error") as failed_error:
            simple_brush.request_candidate_switch_failed_stop(
                failed_calls["result"],
                candidate_in_batch=2,
                total_viewed=1,
            )

        rendered = "\n".join(render_log_calls(
            baseline_info,
            confirmed_calls["info"],
            confirmed_calls["warning"],
            confirmed_calls["error"],
            failed_calls["info"],
            failed_calls["warning"],
            failed_calls["error"],
            failed_error,
        ))
        self.assertIn("error_type=RuntimeError", rendered)
        for forbidden in (
            private_marker,
            "OCRItem",
            "coordinate=(123,456)",
            "confidence=0.987",
            "ScreenFingerprint(",
            "ScanObservation(",
            "DetectionResult(",
            "a" * 64,
            "b" * 64,
            "candidate_name",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, rendered)

        production_source = Path(simple_brush.__file__).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("candidate_name", production_source)

    def test_nonconfirmed_terminal_states_stop_before_count_or_actions(self):
        states = (
            simple_brush.CANDIDATE_SWITCH_LOADING,
            simple_brush.CANDIDATE_SWITCH_OBSERVING,
            simple_brush.CANDIDATE_SWITCH_UNCHANGED,
            simple_brush.CANDIDATE_SWITCH_UNVERIFIABLE,
            simple_brush.CANDIDATE_SWITCH_FAILED,
        )
        for state in states:
            with self.subTest(state=state):
                simple_brush.stop_event = False
                simple_brush.stop_reason = None
                calls = self.run_mocked_keyword_switch(
                    simple_brush.CandidateSwitchResult(
                        state=state,
                        action_attempt=1,
                        observation_attempt=1,
                        failure_reason=(
                            "observation_budget_exhausted"
                            if state == simple_brush.CANDIDATE_SWITCH_FAILED
                            else None
                        ),
                    )
                )

                self.assertEqual(calls["result"], 0)
                calls["view"].assert_called_once_with(
                    0,
                    first_observation=calls["first_observation"],
                )
                calls["confirm_switch"].assert_called_once_with(
                    calls["context"],
                    candidate_in_batch=2,
                    total_viewed=1,
                )
                calls["next_candidate"].assert_not_called()
                calls["favorite"].assert_not_called()
                calls["forward"].assert_not_called()
                calls["refresh"].assert_not_called()
                self.assertEqual(
                    simple_brush.stop_reason,
                    "candidate_switch_failed",
                )
                failed_logs = [
                    line
                    for line in render_log_calls(calls["error"])
                    if line.startswith("event=candidate_switch_failed")
                ]
                self.assertEqual(len(failed_logs), 1)
                self.assertIn("total_viewed=1", failed_logs[0])
                self.assertTrue(any(
                    log_call.args
                    and log_call.args[0]
                    == "\n🏁 停止运行。累计查看 1 位候选人。"
                    for log_call in calls["info"].call_args_list
                ))

    def test_favorite_forward_and_no_forward_modes_all_enter_r01(self):
        modes = (
            (simple_brush.ACTION_MODE_FAVORITE, False),
            (simple_brush.ACTION_MODE_FORWARD, False),
            (simple_brush.ACTION_MODE_FORWARD, True),
        )
        for action_mode, no_forward in modes:
            with self.subTest(
                action_mode=action_mode,
                no_forward=no_forward,
            ):
                simple_brush.stop_event = False
                simple_brush.stop_reason = None
                confirmed_observation = make_ready_switch_observation("b")
                calls = self.run_mocked_keyword_switch(
                    simple_brush.CandidateSwitchResult(
                        state=simple_brush.CANDIDATE_SWITCH_CONFIRMED,
                        action_attempt=1,
                        observation_attempt=2,
                        confirmed_observation=confirmed_observation,
                    ),
                    action_mode=action_mode,
                    no_forward=no_forward,
                )

                calls["load_gate"].assert_called_once_with(
                    candidate_in_batch=1,
                    total_viewed=0,
                    recovery_count=0,
                    recovery_available=False,
                )
                calls["prepare_context"].assert_called_once()
                calls["confirm_switch"].assert_called_once_with(
                    calls["context"],
                    candidate_in_batch=2,
                    total_viewed=1,
                )
                self.assertIs(
                    calls["view"].call_args_list[1].kwargs[
                        "first_observation"
                    ],
                    confirmed_observation,
                )
                calls["next_candidate"].assert_not_called()
                calls["refresh"].assert_not_called()
                self.assertTrue(any(
                    log_call.args
                    and log_call.args[0]
                    == "\n🏁 停止运行。累计查看 2 位候选人。"
                    for log_call in calls["info"].call_args_list
                ))

    def test_refresh_and_refilter_clear_context_before_new_first_r02(self):
        confirmed_observation = make_ready_switch_observation("b")
        calls = self.run_mocked_keyword_switch(
            simple_brush.CandidateSwitchResult(
                state=simple_brush.CANDIDATE_SWITCH_CONFIRMED,
                action_attempt=1,
                observation_attempt=2,
                confirmed_observation=confirmed_observation,
            ),
            stop_on_view_call=3,
            refresh_result=True,
            batch_filter_enabled=True,
        )

        self.assertEqual(calls["load_gate"].call_count, 2)
        self.assertEqual(
            calls["load_gate"].call_args_list,
            [
                call(
                    candidate_in_batch=1,
                    total_viewed=0,
                    recovery_count=0,
                    recovery_available=True,
                ),
                call(
                    candidate_in_batch=1,
                    total_viewed=2,
                    recovery_count=0,
                    recovery_available=True,
                ),
            ],
        )
        calls["confirm_switch"].assert_called_once_with(
            calls["context"],
            candidate_in_batch=2,
            total_viewed=1,
        )
        self.assertEqual(
            [view_call.args[0] for view_call in calls["view"].call_args_list],
            [0, 1, 0],
        )
        calls["prepare_context"].assert_called_once()
        calls["open_first"].assert_not_called()
        self.assertEqual(calls["filter_open"].call_count, 2)
        calls["refresh"].assert_called_once_with()
        self.assertTrue(any(
            log_call.args
            and log_call.args[0]
            == "\n🏁 停止运行。累计查看 3 位候选人。"
            for log_call in calls["info"].call_args_list
        ))

    def test_normal_refresh_completion_does_not_become_r01_failure(self):
        confirmed_observation = make_ready_switch_observation("b")
        calls = self.run_mocked_keyword_switch(
            simple_brush.CandidateSwitchResult(
                state=simple_brush.CANDIDATE_SWITCH_CONFIRMED,
                action_attempt=1,
                observation_attempt=2,
                confirmed_observation=confirmed_observation,
            ),
            stop_on_view_call=99,
            refresh_result=False,
        )

        self.assertEqual(calls["result"], 0)
        calls["refresh"].assert_called_once_with()
        calls["error"].assert_not_called()
        self.assertIsNone(simple_brush.stop_reason)
        self.assertFalse(simple_brush.stop_event)
        self.assertTrue(any(
            log_call.args
            and log_call.args[0]
            == "event=run_stopped stop_reason=none"
            for log_call in calls["info"].call_args_list
        ))

    def test_run_reuses_second_action_confirmation_and_counts_once(self):
        first_loaded = loaded_observation()
        formal_old = make_switch_fingerprint("a", screen_index=1)
        first_detection = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[make_switch_observation(formal_old)],
        )
        baseline = make_ready_switch_observation("a")
        unchanged_observations = [
            make_ready_switch_observation("a")
            for _ in range(6)
        ]
        new_first = make_ready_switch_observation("b")
        new_second = make_ready_switch_observation("b")
        second_detection = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[new_second],
        )
        detector = Mock()
        detector.capture_observation.side_effect = [
            baseline,
            *unchanged_observations,
            new_first,
            new_second,
        ]
        detector.detect.side_effect = [first_detection, second_detection]
        simple_brush.ocr_detector = detector

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = True
            simple_brush.forward_keywords = (
                simple_brush.parse_keyword_rules('"Python"')
            )
            simple_brush.batch_filter_enabled = False
            simple_brush.no_forward_mode = True

        with (
            patch.object(simple_brush, "BATCH_SIZE", 2),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(
                simple_brush,
                "get_user_input",
                side_effect=configure_input,
            ),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "bring_edge_foreground",
                return_value=True,
            ),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(
                simple_brush.pyautogui,
                "position",
                return_value=(10, 20),
            ),
            patch.object(
                simple_brush,
                "click_first_candidate",
                return_value=True,
            ),
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                return_value=True,
            ),
            patch.object(
                simple_brush,
                "run_detail_load_gate",
                return_value=(
                    "loaded",
                    first_loaded,
                    0,
                    "threshold_passed",
                ),
            ) as load_gate,
            patch.object(
                simple_brush,
                "next_candidate",
                return_value=True,
            ) as next_candidate,
            patch.object(
                simple_brush,
                "restore_candidate_detail_focus",
                return_value=True,
            ) as restore_focus,
            patch.object(
                simple_brush.random,
                "uniform",
                return_value=0.0,
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "warning") as warning,
            patch.object(simple_brush.logger, "error") as error,
        ):
            self.assertEqual(simple_brush.run(), 0)

        load_gate.assert_called_once()
        self.assertEqual(next_candidate.call_args_list, [call(), call()])
        restore_focus.assert_called_once_with()
        self.assertEqual(
            detector.capture_observation.call_args_list,
            [call(1) for _ in range(9)],
        )
        self.assertEqual(detector.detect.call_count, 2)
        self.assertIs(
            detector.detect.call_args_list[1].kwargs["first_observation"],
            new_second,
        )
        favorite.assert_not_called()
        forward.assert_not_called()
        error.assert_not_called()
        r01_logs = [
            line
            for line in render_log_calls(info, warning)
            if line.startswith("event=candidate_switch_")
        ]
        self.assertEqual(
            sum("event=candidate_switch_confirmed" in line for line in r01_logs),
            1,
        )
        self.assertEqual(
            sum("event=candidate_switch_focus_recovery" in line for line in r01_logs),
            1,
        )
        self.assertEqual(
            sum("event=candidate_switch_retry" in line for line in r01_logs),
            1,
        )
        confirmed_log = next(
            line
            for line in r01_logs
            if "event=candidate_switch_confirmed" in line
        )
        self.assertIn("action_attempt=2", confirmed_log)
        self.assertIn("candidate_in_batch=2", confirmed_log)
        self.assertIn("total_viewed=1", confirmed_log)
        self.assertTrue(any(
            log_call.args
            and log_call.args[0]
            == '\n🏁 停止运行。累计查看 2 位候选人。'
            for log_call in info.call_args_list
        ))

    def test_run_second_unchanged_never_scans_or_counts_second_candidate(self):
        first_observation = loaded_observation()
        old_fingerprint = make_switch_fingerprint("a", screen_index=1)
        first_detection = DetectionResult(
            success=True,
            confirmed_match=False,
            observations=[make_switch_observation(old_fingerprint)],
        )
        baseline = make_ready_switch_observation("a")
        old_observations = [
            make_ready_switch_observation("a")
            for _ in range(12)
        ]
        detector = Mock()
        detector.capture_observation.side_effect = [
            baseline,
            *old_observations,
        ]
        simple_brush.ocr_detector = detector

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = True
            simple_brush.forward_keywords = (
                simple_brush.parse_keyword_rules('"Python"')
            )
            simple_brush.batch_filter_enabled = False

        def first_view(*_args, **_kwargs):
            return True, first_detection

        with (
            patch.object(simple_brush, "BATCH_SIZE", 2),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(
                simple_brush,
                "get_user_input",
                side_effect=configure_input,
            ),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "bring_edge_foreground",
                return_value=True,
            ),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(
                simple_brush.pyautogui,
                "position",
                return_value=(10, 20),
            ),
            patch.object(
                simple_brush,
                "click_first_candidate",
                return_value=True,
            ),
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                return_value=True,
            ),
            patch.object(
                simple_brush,
                "run_detail_load_gate",
                return_value=(
                    "loaded",
                    first_observation,
                    0,
                    "threshold_passed",
                ),
            ),
            patch.object(
                simple_brush,
                "view_candidate",
                side_effect=first_view,
            ) as view,
            patch.object(
                simple_brush,
                "next_candidate",
                return_value=True,
            ) as next_candidate,
            patch.object(
                simple_brush,
                "restore_candidate_detail_focus",
                return_value=True,
            ) as restore_focus,
            patch.object(simple_brush, "refresh_page") as refresh,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "warning") as warning,
            patch.object(simple_brush.logger, "error") as error,
        ):
            self.assertEqual(simple_brush.run(), 0)

        view.assert_called_once_with(
            0,
            first_observation=first_observation,
        )
        self.assertEqual(next_candidate.call_args_list, [call(), call()])
        restore_focus.assert_called_once_with()
        refresh.assert_not_called()
        favorite.assert_not_called()
        forward.assert_not_called()
        self.assertEqual(simple_brush.stop_reason, "candidate_switch_failed")
        r01_errors = [
            line
            for line in render_log_calls(error)
            if line.startswith("event=candidate_switch_")
        ]
        self.assertEqual(len(r01_errors), 1)
        self.assertIn("event=candidate_switch_failed", r01_errors[0])
        self.assertIn("action_attempt=2", r01_errors[0])
        self.assertIn("total_viewed=1", r01_errors[0])
        self.assertFalse(any(
            "event=candidate_switch_confirmed" in line
            for line in render_log_calls(info, warning, error)
        ))
        self.assertTrue(any(
            log_call.args
            and log_call.args[0]
            == '\n🏁 停止运行。累计查看 1 位候选人。'
            for log_call in info.call_args_list
        ))

    def test_detect_keywords_uses_ocr_without_clipboard(self):
        observation = ScanObservation(1, "python", 1, 0.05, "Python")
        detector = Mock()
        detector.detect.return_value = DetectionResult(
            success=True,
            confirmed_match=True,
            matched_keyword="Python",
            scans_completed=1,
            observations=[observation, observation],
        )
        simple_brush.ocr_detector = detector

        with patch.object(simple_brush, "get_clipboard_text") as clipboard:
            keyword_hit, result = simple_brush.detect_keywords()
        self.assertTrue(keyword_hit)
        self.assertIs(result, detector.detect.return_value)
        clipboard.assert_not_called()
        detector.detect.assert_called_once_with(
            simple_brush.forward_keywords,
            first_observation=None,
        )

    def test_detect_keyword_logs_do_not_expose_rule_or_matched_keyword(self):
        private_rule_marker = "R04_PRIVATE_RULE_MARKER_7F2A"
        rules = simple_brush.parse_keyword_rules(
            '"{0}"'.format(private_rule_marker)
        )
        observation = ScanObservation(
            1,
            private_rule_marker,
            1,
            0.05,
            private_rule_marker,
        )
        detector = Mock()
        detector.detect.return_value = DetectionResult(
            success=True,
            confirmed_match=True,
            matched_keyword=private_rule_marker,
            scans_completed=1,
            observations=[observation],
        )
        simple_brush.forward_keywords = rules
        simple_brush.ocr_detector = detector

        with (
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "warning") as warning,
            patch.object(simple_brush.logger, "error") as error,
        ):
            keyword_hit, result = simple_brush.detect_keywords()

        self.assertTrue(keyword_hit)
        self.assertIs(result, detector.detect.return_value)
        rendered = "\n".join(render_log_calls(info, warning, error))
        self.assertNotIn(private_rule_marker, rendered)
        self.assertIn("rule_count=1", rendered)
        self.assertIn("matched=true", rendered)

    def test_detect_keywords_passes_the_complete_not_rule_to_ocr(self):
        rules = simple_brush.parse_keyword_rules('"短剧" and not "销售"')
        detector = Mock()
        detector.detect.return_value = DetectionResult(
            success=True,
            confirmed_match=True,
            matched_keyword='"短剧" and not "销售"',
            scans_completed=1,
            observations=[],
        )
        simple_brush.forward_keywords = rules
        simple_brush.ocr_detector = detector

        keyword_hit, result = simple_brush.detect_keywords()
        self.assertTrue(keyword_hit)
        self.assertIs(result, detector.detect.return_value)
        detector.detect.assert_called_once_with(rules, first_observation=None)

    def test_detect_keywords_reuses_prefetched_observation_without_relogging_it(self):
        first_observation = loaded_observation()
        confirmation = ScanObservation(1, "python", 1, 0.02, "Python")
        detector = Mock()
        detector.detect.return_value = DetectionResult(
            success=True,
            confirmed_match=True,
            matched_keyword="Python",
            scans_completed=1,
            observations=[first_observation, confirmation],
        )
        simple_brush.ocr_detector = detector

        with patch.object(simple_brush.logger, "info") as info:
            keyword_hit, result = simple_brush.detect_keywords(
                first_observation
            )

        self.assertTrue(keyword_hit)
        self.assertIs(result, detector.detect.return_value)
        detector.detect.assert_called_once_with(
            simple_brush.forward_keywords,
            first_observation=first_observation,
        )
        observation_logs = [
            log_call
            for log_call in info.call_args_list
            if log_call.args and log_call.args[0].startswith('  OCR %s:')
        ]
        self.assertEqual(len(observation_logs), 1)
        self.assertEqual(observation_logs[0].args[1], '二次确认')

    def test_single_load_gate_does_not_wait_or_retry(self):
        observation = loaded_observation()
        detector = Mock()
        detector.capture_observation.return_value = observation
        simple_brush.ocr_detector = detector

        with patch.object(simple_brush, "safe_wait") as wait:
            result = simple_brush.run_detail_load_gate(1, 0, 0, False)

        self.assertEqual(
            result,
            ("loaded", observation, 0, "threshold_passed"),
        )
        detector.capture_observation.assert_called_once_with(1)
        wait.assert_not_called()

    def assert_load_gate_succeeds_on_retry(self, retry_number):
        failed_observations = [
            not_loaded_observation()
            for _ in range(retry_number)
        ]
        success_observation = loaded_observation()
        detector = Mock()
        detector.capture_observation.side_effect = [
            *failed_observations,
            success_observation,
        ]
        simple_brush.ocr_detector = detector

        with patch.object(
            simple_brush,
            "safe_wait",
            return_value=True,
        ) as wait:
            result = simple_brush.run_detail_load_gate(1, 0, 0, False)

        self.assertEqual(
            result,
            ("loaded", success_observation, retry_number, "threshold_passed"),
        )
        self.assertEqual(
            detector.capture_observation.call_args_list,
            [call(1)] * (retry_number + 1),
        )
        self.assertEqual(
            wait.call_args_list,
            [call(simple_brush.LOAD_RETRY_WAIT_SECONDS)] * retry_number,
        )

    def test_retry_one_success_uses_two_ocr_calls_and_one_wait(self):
        self.assertEqual(simple_brush.LOAD_RETRY_WAIT_SECONDS, 1.5)
        self.assert_load_gate_succeeds_on_retry(1)

    def test_retry_two_success_uses_three_ocr_calls_and_two_waits(self):
        self.assert_load_gate_succeeds_on_retry(2)

    def test_retry_three_success_uses_four_ocr_calls_and_three_waits(self):
        self.assert_load_gate_succeeds_on_retry(3)

    def test_four_failures_exhaust_budget_without_fifth_ocr(self):
        self.assertEqual(simple_brush.MAX_LOAD_RETRIES, 3)
        detector = Mock()
        detector.capture_observation.side_effect = [
            not_loaded_observation()
            for _ in range(simple_brush.MAX_LOAD_RETRIES + 1)
        ]
        simple_brush.ocr_detector = detector

        with (
            patch.object(
                simple_brush,
                "safe_wait",
                return_value=True,
            ) as wait,
            patch("ocr_detector.matching_keyword_rule") as matcher,
        ):
            result = simple_brush.run_detail_load_gate(1, 0, 0, False)

        self.assertEqual(
            result,
            (
                "retries_exhausted",
                None,
                simple_brush.MAX_LOAD_RETRIES,
                "low_box_count_and_short_text",
            ),
        )
        self.assertEqual(
            detector.capture_observation.call_count,
            simple_brush.MAX_LOAD_RETRIES + 1,
        )
        self.assertEqual(
            wait.call_args_list,
            [call(simple_brush.LOAD_RETRY_WAIT_SECONDS)] * 3,
        )
        matcher.assert_not_called()

    def test_exhausted_gate_returns_load_recovering_when_available(self):
        detector = Mock()
        detector.capture_observation.return_value = not_loaded_observation()
        simple_brush.ocr_detector = detector

        with (
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.logger, "info") as info,
        ):
            result = simple_brush.run_detail_load_gate(1, 0, 0, True)

        self.assertEqual(
            result,
            (
                "load_recovering",
                None,
                simple_brush.MAX_LOAD_RETRIES,
                "low_box_count_and_short_text",
            ),
        )
        self.assertEqual(detector.capture_observation.call_count, 4)
        self.assertEqual(info.call_args.args[-1], "hard_refresh")

    def test_exhausted_gate_respects_consecutive_recovery_limit(self):
        detector = Mock()
        detector.capture_observation.return_value = not_loaded_observation()
        simple_brush.ocr_detector = detector

        with patch.object(simple_brush, "safe_wait", return_value=True):
            result = simple_brush.run_detail_load_gate(
                1,
                0,
                simple_brush.MAX_CONSECUTIVE_LOAD_RECOVERIES,
                True,
            )

        self.assertEqual(result[0], "retries_exhausted")
        self.assertEqual(detector.capture_observation.call_count, 4)

    def test_threshold_failures_and_ocr_error_share_one_budget(self):
        success_observation = loaded_observation()
        detector = Mock()
        detector.capture_observation.side_effect = [
            not_loaded_observation(),
            RuntimeError("OCR unavailable"),
            not_loaded_observation(),
            success_observation,
        ]
        simple_brush.ocr_detector = detector

        with (
            patch.object(simple_brush, "safe_wait", return_value=True) as wait,
            patch.object(simple_brush.logger, "warning") as warning,
        ):
            result = simple_brush.run_detail_load_gate(1, 0, 0, False)

        self.assertEqual(
            result,
            ("loaded", success_observation, 3, "threshold_passed"),
        )
        self.assertEqual(detector.capture_observation.call_count, 4)
        self.assertEqual(
            wait.call_args_list,
            [call(simple_brush.LOAD_RETRY_WAIT_SECONDS)] * 3,
        )
        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[5:9], ('-', '-', 'error', 'ocr_error'))

    def test_empty_ocr_metrics_are_zero_not_ocr_error(self):
        empty_observation = ScanObservation(
            1,
            "",
            0,
            0.01,
            ocr_box_count=0,
            ocr_text_length=0,
        )
        detector = Mock()
        detector.capture_observation.side_effect = [
            empty_observation,
            loaded_observation(),
        ]
        simple_brush.ocr_detector = detector

        with (
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "warning") as warning,
        ):
            result = simple_brush.run_detail_load_gate(1, 0, 0, False)

        self.assertEqual(result[0], "loaded")
        warning.assert_not_called()
        self.assertEqual(
            info.call_args.args[5:9],
            (0, 0, 'not_loaded', 'zero_ocr_boxes'),
        )

    def test_detail_load_check_logs_frozen_fields_without_ocr_text(self):
        private_observation = ScanObservation(
            1,
            "PRIVATE_OCR_BODY",
            2,
            0.01,
            ocr_box_count=2,
            ocr_text_length=5,
        )
        detector = Mock()
        detector.capture_observation.side_effect = [
            private_observation,
            loaded_observation(),
        ]
        simple_brush.ocr_detector = detector

        with (
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.logger, "info") as info,
        ):
            result = simple_brush.run_detail_load_gate(7, 12, 1, False)

        self.assertEqual(result[0], "loaded")
        self.assertEqual(len(info.call_args_list), 1)
        rendered = info.call_args.args[0] % info.call_args.args[1:]
        for expected in (
            "event=detail_load_check",
            "candidate_in_batch=7",
            "total_viewed=12",
            "attempt=initial",
            "retry_number=0",
            "ocr_box_count=2",
            "ocr_text_length=5",
            "decision=not_loaded",
            "reason=low_box_count_and_short_text",
            "state=loading",
            "recovery_count=1",
            "next_action=wait_and_retry",
        ):
            self.assertIn(expected, rendered)
        self.assertNotIn("PRIVATE_OCR_BODY", rendered)
        self.assertNotIn("not_ready", rendered)

    def test_all_retries_use_the_same_ocr_region(self):
        region = simple_brush.ScreenRegion(10, 20, 800, 600)

        class RegionRecordingDetector:
            def __init__(self):
                self.region = region
                self.regions = []
                self.observations = [
                    not_loaded_observation(),
                    not_loaded_observation(),
                    not_loaded_observation(),
                    loaded_observation(),
                ]

            def capture_observation(self, _scan_number):
                self.regions.append(self.region)
                return self.observations.pop(0)

        detector = RegionRecordingDetector()
        simple_brush.ocr_detector = detector

        with patch.object(simple_brush, "safe_wait", return_value=True):
            result = simple_brush.run_detail_load_gate(1, 0, 0, False)

        self.assertEqual(result[0], "loaded")
        self.assertEqual(len(detector.regions), 4)
        self.assertTrue(all(item is region for item in detector.regions))

    def test_stop_during_retry_wait_prevents_next_ocr(self):
        detector = Mock()
        detector.capture_observation.return_value = not_loaded_observation()
        simple_brush.ocr_detector = detector

        def stop_wait(_seconds):
            simple_brush.stop_event = True
            return False

        with patch.object(simple_brush, "safe_wait", side_effect=stop_wait) as wait:
            result = simple_brush.run_detail_load_gate(1, 0, 0, False)

        self.assertEqual(result, (None, None, 1, "stopped"))
        detector.capture_observation.assert_called_once_with(1)
        wait.assert_called_once_with(simple_brush.LOAD_RETRY_WAIT_SECONDS)

    def test_stop_during_synchronous_ocr_is_not_counted_as_ocr_error(self):
        detector = Mock()

        def capture_and_stop(_scan_number):
            simple_brush.stop_event = True
            return loaded_observation()

        detector.capture_observation.side_effect = capture_and_stop
        simple_brush.ocr_detector = detector

        with (
            patch.object(simple_brush, "evaluate_detail_page_load") as evaluate,
            patch.object(simple_brush.logger, "warning") as warning,
        ):
            result = simple_brush.run_detail_load_gate(1, 0, 0, False)

        self.assertEqual(result, (None, None, 0, "stopped"))
        evaluate.assert_not_called()
        warning.assert_not_called()

    def test_refresh_page_default_call_keeps_normal_message_and_wait(self):
        with (
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush, "safe_wait", return_value=True) as wait,
            patch.object(simple_brush.logger, "info") as info,
        ):
            self.assertTrue(simple_brush.refresh_page())

        info.assert_called_once_with('🔄 已查看 100 位，按 F5 刷新页面')
        press.assert_called_once_with('f5')
        wait.assert_called_once_with(simple_brush.REFRESH_WAIT_SECONDS)

    def test_recover_detail_page_preserves_navigation_event_order(self):
        regions = sample_batch_filter_regions()
        simple_brush.batch_filter_enabled = True
        simple_brush.batch_filter_regions = regions
        events = []
        region_names = {
            regions.open_filter: "open_filter",
            regions.unseen_filter: "unseen_filter",
            regions.confirm_filter: "confirm_filter",
            regions.first_candidate: "first_candidate",
        }

        def press(key):
            self.assertEqual(key, 'f5')
            events.append('f5')

        def wait(seconds):
            if seconds == simple_brush.REFRESH_WAIT_SECONDS:
                events.append('refresh_wait')
            else:
                self.assertEqual(seconds, simple_brush.CLICK_WAIT_SECONDS)
                events.append('candidate_wait')
            return True

        def delay(minimum, maximum):
            if (
                minimum == simple_brush.FILTER_RESULTS_DELAY_MIN
                and maximum == simple_brush.FILTER_RESULTS_DELAY_MAX
            ):
                events.append('results_wait')
            else:
                events.append('filter_wait')
            return True

        def click(region):
            events.append(region_names[region])

        with (
            patch.object(simple_brush.pyautogui, "press", side_effect=press),
            patch.object(simple_brush, "safe_wait", side_effect=wait),
            patch.object(simple_brush, "human_delay", side_effect=delay),
            patch.object(simple_brush, "click_in_region", side_effect=click),
        ):
            result = simple_brush.recover_detail_page()

        self.assertEqual(result, (True, "reopen_completed"))
        self.assertEqual(
            events,
            [
                'f5',
                'refresh_wait',
                'open_filter',
                'filter_wait',
                'unseen_filter',
                'filter_wait',
                'confirm_filter',
                'results_wait',
                'first_candidate',
                'candidate_wait',
            ],
        )

    def test_recover_detail_page_reuses_existing_helpers_once(self):
        with (
            patch.object(simple_brush, "refresh_page", return_value=True) as refresh,
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                return_value=True,
            ) as reopen,
            patch.object(simple_brush.logger, "info") as info,
        ):
            result = simple_brush.recover_detail_page()

        self.assertEqual(result, (True, "reopen_completed"))
        refresh.assert_called_once_with(reason='详情页加载检测重试耗尽')
        reopen.assert_called_once_with()
        reopen_logs = [
            log_call.args[0]
            for log_call in info.call_args_list
            if log_call.args
            and 'event=detail_load_recovery_reopen_completed' in log_call.args[0]
        ]
        self.assertEqual(len(reopen_logs), 1)
        self.assertNotIn('detail_load_recovery_confirmed', '\n'.join(reopen_logs))

    def test_recover_detail_page_non_stop_failures_are_controlled(self):
        cases = (
            (RuntimeError("refresh failed"), True, (False, "refresh_failed")),
            (False, True, (False, "refresh_failed")),
            (True, RuntimeError("reopen failed"), (False, "batch_reopen_failed")),
            (True, False, (False, "batch_reopen_failed")),
        )
        for refresh_result, reopen_result, expected in cases:
            with self.subTest(expected=expected, refresh_result=refresh_result):
                simple_brush.stop_event = False
                refresh_effect = (
                    refresh_result
                    if isinstance(refresh_result, Exception)
                    else None
                )
                reopen_effect = (
                    reopen_result
                    if isinstance(reopen_result, Exception)
                    else None
                )
                with (
                    patch.object(
                        simple_brush,
                        "refresh_page",
                        return_value=refresh_result,
                        side_effect=refresh_effect,
                    ),
                    patch.object(
                        simple_brush,
                        "apply_batch_filter_and_open_first_candidate",
                        return_value=reopen_result,
                        side_effect=reopen_effect,
                    ),
                ):
                    self.assertEqual(simple_brush.recover_detail_page(), expected)

    def test_recover_detail_page_stop_is_not_recorded_as_failure(self):
        def stop_during_step(*_args, **_kwargs):
            simple_brush.stop_event = True
            return False

        for stopped_step in ('refresh', 'reopen'):
            with self.subTest(stopped_step=stopped_step):
                simple_brush.stop_event = False
                refresh_side_effect = (
                    stop_during_step if stopped_step == 'refresh' else None
                )
                reopen_side_effect = (
                    stop_during_step if stopped_step == 'reopen' else None
                )
                with (
                    patch.object(
                        simple_brush,
                        "refresh_page",
                        return_value=True,
                        side_effect=refresh_side_effect,
                    ),
                    patch.object(
                        simple_brush,
                        "apply_batch_filter_and_open_first_candidate",
                        return_value=True,
                        side_effect=reopen_side_effect,
                    ),
                    patch.object(simple_brush.logger, "error") as error,
                ):
                    self.assertEqual(
                        simple_brush.recover_detail_page(),
                        (None, "stopped"),
                    )
                error.assert_not_called()

    def test_hard_recovery_does_not_clear_forward_consecutive(self):
        simple_brush.forward_consecutive = 4
        with (
            patch.object(simple_brush, "refresh_page", return_value=True),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                return_value=True,
            ),
        ):
            self.assertEqual(
                simple_brush.recover_detail_page(),
                (True, "reopen_completed"),
            )

        self.assertEqual(simple_brush.forward_consecutive, 4)

    def test_request_load_failed_stop_logs_complete_safe_stop_fields(self):
        simple_brush.forward_consecutive = 4
        with patch.object(simple_brush.logger, "error") as error:
            simple_brush.request_load_failed_stop(
                candidate_in_batch=3,
                total_viewed=12,
                retry_number=3,
                reason="hard_recovery_unavailable",
                recovery_count=0,
            )

        self.assertTrue(simple_brush.stop_event)
        self.assertEqual(simple_brush.stop_reason, "load_failed")
        self.assertEqual(simple_brush.forward_consecutive, 4)
        error.assert_called_once()
        rendered = error.call_args.args[0] % error.call_args.args[1:]
        for expected in (
            "event=detail_load_failed",
            "candidate_in_batch=3",
            "total_viewed=12",
            "attempt=retry",
            "retry_number=3",
            "ocr_box_count=-",
            "ocr_text_length=-",
            "decision=error",
            "reason=hard_recovery_unavailable",
            "state=load_failed",
            "recovery_count=0",
            "next_action=safe_stop",
        ):
            self.assertIn(expected, rendered)
        self.assertNotIn("loaded detail text", rendered)

    def test_first_stop_reason_is_not_overwritten(self):
        with (
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "error") as error,
        ):
            simple_brush.on_press(simple_brush.keyboard.Key.esc)
            simple_brush.request_timed_stop()
            simple_brush.request_load_failed_stop(1, 0, 3, "refresh_failed", 1)

        self.assertEqual(simple_brush.stop_reason, "esc")
        self.assertTrue(simple_brush.stop_event)
        info.assert_called_once_with('⚡ 收到 ESC，准备停止')
        error.assert_not_called()

        simple_brush.stop_event = False
        simple_brush.stop_reason = None
        with (
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "error") as error,
        ):
            simple_brush.request_timed_stop()
            simple_brush.on_press(simple_brush.keyboard.Key.esc)
            simple_brush.request_load_failed_stop(1, 0, 3, "refresh_failed", 1)

        self.assertEqual(simple_brush.stop_reason, "run_duration_elapsed")
        info.assert_not_called()
        error.assert_not_called()

        simple_brush.stop_event = False
        simple_brush.stop_reason = None
        with (
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "error") as error,
        ):
            simple_brush.request_load_failed_stop(1, 0, 3, "refresh_failed", 1)
            simple_brush.request_timed_stop()
            simple_brush.on_press(simple_brush.keyboard.Key.esc)

        self.assertEqual(simple_brush.stop_reason, "load_failed")
        info.assert_not_called()
        error.assert_called_once()

    def test_keyword_modes_all_pass_through_single_load_gate(self):
        modes = (
            (simple_brush.ACTION_MODE_FAVORITE, False),
            (simple_brush.ACTION_MODE_FORWARD, False),
            (simple_brush.ACTION_MODE_FORWARD, True),
        )
        for action_mode, no_forward in modes:
            with self.subTest(action_mode=action_mode, no_forward=no_forward):
                observation = loaded_observation()
                calls = self.run_load_gate_candidate(
                    observation=observation,
                    action_mode=action_mode,
                    no_forward=no_forward,
                )

                self.assertEqual(calls["result"], 0)
                calls["detector"].capture_observation.assert_called_once_with(1)
                calls["wait"].assert_not_called()
                calls["view"].assert_called_once_with(
                    0,
                    first_observation=observation,
                )
                calls["next_candidate"].assert_not_called()
                calls["refresh"].assert_not_called()
                calls["timer"].cancel.assert_called_once_with()
                loaded_logs = [
                    log_call
                    for log_call in calls["info"].call_args_list
                    if log_call.args and 'state=loaded' in log_call.args[0]
                ]
                self.assertEqual(len(loaded_logs), 1)
                self.assertEqual(loaded_logs[0].args[2], 1)

    def test_retry_success_is_reused_once_and_counted_once_by_run(self):
        success_observation = loaded_observation()
        calls = self.run_load_gate_candidate(capture_sequence=[
            not_loaded_observation(),
            RuntimeError("OCR unavailable"),
            success_observation,
        ])

        self.assertEqual(calls["result"], 0)
        self.assertEqual(
            calls["detector"].capture_observation.call_args_list,
            [call(1)] * 3,
        )
        self.assertEqual(
            calls["wait"].call_args_list,
            [call(simple_brush.LOAD_RETRY_WAIT_SECONDS)] * 2,
        )
        calls["view"].assert_called_once_with(
            0,
            first_observation=success_observation,
        )
        calls["next_candidate"].assert_not_called()
        calls["refresh"].assert_not_called()
        loaded_logs = [
            log_call
            for log_call in calls["info"].call_args_list
            if log_call.args and 'state=loaded' in log_call.args[0]
        ]
        self.assertEqual(len(loaded_logs), 1)
        self.assertEqual(loaded_logs[0].args[2:5], (1, 'retry', 2))

    def test_no_keyword_run_bypasses_load_gate_and_ocr_setup(self):
        with (
            patch.object(
                simple_brush,
                "prepare_candidate_switch_context",
            ) as prepare_context,
            patch.object(
                simple_brush,
                "confirm_candidate_switch",
            ) as confirm_switch,
        ):
            calls = self.run_load_gate_candidate(keywords=False)

        self.assertEqual(calls["result"], 0)
        calls["initialize_ocr"].assert_not_called()
        calls["ensure_ocr"].assert_not_called()
        calls["detector"].capture_observation.assert_not_called()
        calls["view"].assert_called_once_with(0)
        calls["next_candidate"].assert_not_called()
        calls["refresh"].assert_not_called()
        prepare_context.assert_not_called()
        confirm_switch.assert_not_called()
        self.assertFalse(any(
            line.startswith("event=candidate_switch_")
            for line in render_log_calls(
                calls["info"],
                calls["warning"],
                calls["error"],
            )
        ))

    def test_run_resets_stop_reason_at_start(self):
        simple_brush.stop_reason = "esc"

        calls = self.run_load_gate_candidate(observation=loaded_observation())

        self.assertEqual(calls["result"], 0)
        self.assertIsNone(simple_brush.stop_reason)

    def test_independent_keyword_runs_each_start_with_r02_not_r01(self):
        with patch.object(
            simple_brush,
            "confirm_candidate_switch",
        ) as confirm_switch:
            first = self.run_load_gate_candidate(
                observation=loaded_observation()
            )
            second = self.run_load_gate_candidate(
                observation=loaded_observation()
            )

        first["detector"].capture_observation.assert_called_once_with(1)
        second["detector"].capture_observation.assert_called_once_with(1)
        first["view"].assert_called_once_with(
            0,
            first_observation=first["detector"].capture_observation.return_value,
        )
        second["view"].assert_called_once_with(
            0,
            first_observation=second["detector"].capture_observation.return_value,
        )
        confirm_switch.assert_not_called()

    def test_unavailable_recovery_requests_load_failed_without_side_effects(self):
        calls = self.run_load_gate_candidate(
            observation=not_loaded_observation(),
        )

        self.assertEqual(calls["result"], 0)
        self.assertEqual(
            calls["detector"].capture_observation.call_args_list,
            [call(1)] * 4,
        )
        self.assertEqual(
            calls["wait"].call_args_list,
            [call(simple_brush.LOAD_RETRY_WAIT_SECONDS)] * 3,
        )
        calls["detector"].detect.assert_not_called()
        calls["detect_keywords"].assert_not_called()
        calls["ocr_scroll"].assert_not_called()
        calls["human_scroll"].assert_not_called()
        calls["favorite_action"].assert_not_called()
        calls["forward_action"].assert_not_called()
        calls["favorite_focus_restore"].assert_not_called()
        calls["view"].assert_not_called()
        calls["next_candidate"].assert_not_called()
        calls["refresh"].assert_not_called()
        calls["recover"].assert_not_called()
        calls["open_first"].assert_called_once_with()
        calls["timer"].cancel.assert_called_once_with()
        self.assertTrue(simple_brush.stop_event)
        self.assertEqual(simple_brush.stop_reason, "load_failed")
        calls["warning"].assert_not_called()
        calls["error"].assert_called_once()
        self.assertIn(
            'hard_recovery_unavailable',
            calls["error"].call_args.args,
        )
        final_logs = [
            log_call.args[0]
            for log_call in calls["info"].call_args_list
            if log_call.args and '停止运行。累计查看' in log_call.args[0]
        ]
        self.assertEqual(final_logs, ['\n🏁 停止运行。累计查看 0 位候选人。'])
        self.assertTrue(
            any(
                log_call.args
                and log_call.args[0]
                == 'event=run_stopped stop_reason=load_failed'
                for log_call in calls["info"].call_args_list
            )
        )

    def test_repeated_ocr_errors_exhaust_run_without_candidate_side_effects(self):
        calls = self.run_load_gate_candidate(
            capture_error=RuntimeError("OCR unavailable"),
        )

        self.assertEqual(calls["result"], 0)
        self.assertEqual(
            calls["detector"].capture_observation.call_args_list,
            [call(1)] * 4,
        )
        self.assertEqual(
            calls["wait"].call_args_list,
            [call(simple_brush.LOAD_RETRY_WAIT_SECONDS)] * 3,
        )
        calls["detector"].detect.assert_not_called()
        calls["detect_keywords"].assert_not_called()
        calls["ocr_scroll"].assert_not_called()
        calls["human_scroll"].assert_not_called()
        calls["favorite_action"].assert_not_called()
        calls["forward_action"].assert_not_called()
        calls["favorite_focus_restore"].assert_not_called()
        calls["view"].assert_not_called()
        calls["next_candidate"].assert_not_called()
        calls["refresh"].assert_not_called()
        calls["recover"].assert_not_called()
        calls["open_first"].assert_called_once_with()
        calls["timer"].cancel.assert_called_once_with()
        self.assertTrue(simple_brush.stop_event)
        self.assertEqual(simple_brush.stop_reason, "load_failed")
        self.assertEqual(calls["warning"].call_count, 4)
        calls["error"].assert_called_once()
        self.assertIn(
            'hard_recovery_unavailable',
            calls["error"].call_args.args,
        )

    def test_legacy_exhaustion_does_not_refresh_or_reopen_by_coordinates(self):
        calls = self.run_load_gate_candidate(
            observation=not_loaded_observation(),
            batch_filter_enabled=False,
        )

        self.assertEqual(calls["result"], 0)
        calls["open_first"].assert_called_once_with((10, 20))
        calls["recover"].assert_not_called()
        calls["refresh"].assert_not_called()
        self.assertEqual(simple_brush.stop_reason, "load_failed")
        self.assertIn(
            'hard_recovery_unavailable',
            calls["error"].call_args.args,
        )

    def test_recovery_restarts_at_first_candidate_without_duplicate_open(self):
        observation = loaded_observation()
        events = []

        def record_info(message, *_args):
            if 'event=detail_load_check' in message and 'state=loaded' in message:
                events.append('loaded')
            if 'event=detail_load_recovery_confirmed' in message:
                events.append('confirmed')

        def record_view(*_args, **_kwargs):
            events.append('view')
            simple_brush.stop_event = True
            return False, None

        calls = self.run_load_gate_candidate(
            capture_sequence=[
                not_loaded_observation(),
                not_loaded_observation(),
                not_loaded_observation(),
                not_loaded_observation(),
                observation,
            ],
            recovery_available=True,
            view_side_effect=record_view,
            info_side_effect=record_info,
        )

        self.assertEqual(calls["result"], 0)
        self.assertEqual(calls["detector"].capture_observation.call_count, 5)
        calls["recover"].assert_called_once_with()
        calls["open_first"].assert_called_once_with()
        calls["refresh"].assert_not_called()
        calls["view"].assert_called_once_with(
            0,
            first_observation=observation,
        )
        loaded_logs = [
            log_call
            for log_call in calls["info"].call_args_list
            if log_call.args
            and 'event=detail_load_check' in log_call.args[0]
            and 'state=loaded' in log_call.args[0]
        ]
        self.assertEqual(len(loaded_logs), 1)
        self.assertEqual(loaded_logs[0].args[-1], 1)
        confirmed_logs = [
            log_call
            for log_call in calls["info"].call_args_list
            if log_call.args
            and 'detail_load_recovery_confirmed' in log_call.args[0]
        ]
        self.assertEqual(len(confirmed_logs), 1)
        self.assertEqual(confirmed_logs[0].args[-1], 1)
        self.assertLess(
            calls["info"].call_args_list.index(loaded_logs[0]),
            calls["info"].call_args_list.index(confirmed_logs[0]),
        )
        self.assertEqual(events, ['loaded', 'confirmed', 'view'])

    def test_recovered_first_candidate_still_requires_valid_pre_switch_baseline(self):
        def continue_to_baseline(*_args, **_kwargs):
            return True, DetectionResult(False, False)

        with patch.object(
            simple_brush,
            "confirm_candidate_switch",
        ) as confirm_switch:
            calls = self.run_load_gate_candidate(
                capture_sequence=[
                    *[not_loaded_observation() for _ in range(4)],
                    loaded_observation(),
                    *[not_loaded_observation() for _ in range(4)],
                    loaded_observation(),
                ],
                recovery_available=True,
                view_side_effect=continue_to_baseline,
            )

        self.assertEqual(calls["detector"].capture_observation.call_count, 6)
        self.assertEqual(calls["recover"].call_count, 1)
        self.assertEqual(
            [view_call.args[0] for view_call in calls["view"].call_args_list],
            [0],
        )
        calls["next_candidate"].assert_not_called()
        confirm_switch.assert_not_called()
        recovery_start_logs = [
            log_call
            for log_call in calls["warning"].call_args_list
            if log_call.args
            and 'event=detail_load_recovery_start' in log_call.args[0]
        ]
        self.assertEqual(len(recovery_start_logs), 1)
        self.assertTrue(all(log_call.args[-1] == 1 for log_call in recovery_start_logs))
        confirmed_logs = [
            log_call
            for log_call in calls["info"].call_args_list
            if log_call.args
            and 'event=detail_load_recovery_confirmed' in log_call.args[0]
        ]
        self.assertEqual(len(confirmed_logs), 1)
        calls["error"].assert_called_once()
        self.assertEqual(simple_brush.stop_reason, "candidate_switch_failed")

    def test_exhaustion_triggers_exactly_one_f5_and_filter_reopen(self):
        calls = self.run_load_gate_candidate(
            capture_sequence=[
                not_loaded_observation(),
                not_loaded_observation(),
                not_loaded_observation(),
                not_loaded_observation(),
                loaded_observation(),
            ],
            recovery_available=True,
            real_recovery=True,
        )

        calls["recover"].assert_called_once_with()
        calls["refresh"].assert_called_once_with(
            reason='详情页加载检测重试耗尽'
        )
        calls["press"].assert_called_once_with('f5')
        calls["apply_reopen"].assert_called_once_with()
        self.assertEqual(
            calls["wait"].call_args_list,
            [
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
                call(simple_brush.REFRESH_WAIT_SECONDS),
            ],
        )
        calls["open_first"].assert_called_once_with()
        calls["refresh"].assert_called_once()

    def test_second_consecutive_exhaustion_stops_without_second_recovery(self):
        calls = self.run_load_gate_candidate(
            observation=not_loaded_observation(),
            recovery_available=True,
            real_recovery=True,
        )

        self.assertEqual(calls["result"], 0)
        self.assertEqual(calls["detector"].capture_observation.call_count, 8)
        self.assertEqual(
            calls["wait"].call_args_list,
            [
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
                call(simple_brush.REFRESH_WAIT_SECONDS),
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
                call(simple_brush.LOAD_RETRY_WAIT_SECONDS),
            ],
        )
        calls["recover"].assert_called_once_with()
        calls["open_first"].assert_called_once_with()
        calls["refresh"].assert_called_once_with(
            reason='详情页加载检测重试耗尽'
        )
        calls["press"].assert_called_once_with('f5')
        calls["apply_reopen"].assert_called_once_with()
        calls["view"].assert_not_called()
        self.assertTrue(simple_brush.stop_event)
        self.assertEqual(simple_brush.stop_reason, "load_failed")
        self.assertIn(
            'max_consecutive_load_recoveries_reached',
            calls["error"].call_args.args,
        )
        calls["timer"].cancel.assert_called_once_with()

    def test_non_stop_recovery_failure_returns_through_finally(self):
        for failure_reason in ("refresh_failed", "batch_reopen_failed"):
            with self.subTest(failure_reason=failure_reason):
                calls = self.run_load_gate_candidate(
                    observation=not_loaded_observation(),
                    recovery_available=True,
                    recovery_result=(False, failure_reason),
                )

                self.assertEqual(calls["result"], 0)
                calls["recover"].assert_called_once_with()
                calls["view"].assert_not_called()
                calls["next_candidate"].assert_not_called()
                calls["refresh"].assert_not_called()
                calls["timer"].cancel.assert_called_once_with()
                self.assertTrue(simple_brush.stop_event)
                self.assertEqual(simple_brush.stop_reason, "load_failed")
                self.assertIn(failure_reason, calls["error"].call_args.args)

    def test_stop_during_recovery_uses_existing_stop_path(self):
        def stop_recovery():
            simple_brush.stop_reason = "esc"
            simple_brush.stop_event = True
            return None, "stopped"

        calls = self.run_load_gate_candidate(
            observation=not_loaded_observation(),
            recovery_available=True,
            recovery_side_effect=stop_recovery,
        )

        self.assertEqual(calls["result"], 0)
        calls["recover"].assert_called_once_with()
        calls["view"].assert_not_called()
        calls["next_candidate"].assert_not_called()
        calls["refresh"].assert_not_called()
        calls["timer"].cancel.assert_called_once_with()
        self.assertTrue(simple_brush.stop_event)
        self.assertEqual(simple_brush.stop_reason, "esc")
        calls["error"].assert_not_called()

    def test_no_forward_mode_never_calls_real_forward(self):
        simple_brush.no_forward_mode = True
        simple_brush.action_mode = simple_brush.ACTION_MODE_FORWARD
        detection_result = DetectionResult(True, True)
        with (
            patch.object(
                simple_brush,
                "detect_keywords",
                return_value=(True, detection_result),
            ),
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush.random, "uniform", return_value=0.0),
        ):
            completed, result = simple_brush.view_candidate(0)
        self.assertTrue(completed)
        self.assertIs(result, detection_result)
        forward.assert_not_called()
        favorite.assert_not_called()

    def test_forward_mode_keyword_hit_calls_forward_action(self):
        simple_brush.action_mode = simple_brush.ACTION_MODE_FORWARD
        detection_result = DetectionResult(True, True)
        with (
            patch.object(
                simple_brush,
                "detect_keywords",
                return_value=(True, detection_result),
            ),
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush.random, "uniform", return_value=0.0),
        ):
            completed, result = simple_brush.view_candidate(0)
        self.assertTrue(completed)
        self.assertIs(result, detection_result)
        forward.assert_called_once_with()
        favorite.assert_not_called()

    def test_favorite_mode_keyword_hit_calls_favorite_action_only(self):
        simple_brush.action_mode = simple_brush.ACTION_MODE_FAVORITE
        simple_brush.no_forward_mode = True
        detection_result = DetectionResult(True, True)
        with (
            patch.object(
                simple_brush,
                "detect_keywords",
                return_value=(True, detection_result),
            ),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush, "ensure_forward_click_regions_calibrated") as forward_calibrate,
            patch.object(simple_brush.random, "uniform", return_value=0.0),
        ):
            completed, result = simple_brush.view_candidate(0)
        self.assertTrue(completed)
        self.assertIs(result, detection_result)
        favorite.assert_called_once_with()
        forward.assert_not_called()
        forward_calibrate.assert_not_called()

    def test_ocr_failure_never_calls_real_forward(self):
        detection_result = DetectionResult(False, False)
        with (
            patch.object(
                simple_brush,
                "detect_keywords",
                return_value=(False, detection_result),
            ),
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush.random, "uniform", return_value=0.0),
        ):
            completed, result = simple_brush.view_candidate(0)
        self.assertTrue(completed)
        self.assertIs(result, detection_result)
        forward.assert_not_called()
        favorite.assert_not_called()

    def test_invalid_action_mode_fails_when_keyword_hits(self):
        simple_brush.action_mode = "invalid"
        with (
            patch.object(
                simple_brush,
                "detect_keywords",
                return_value=(True, DetectionResult(True, True)),
            ),
            patch.object(simple_brush.random, "uniform", return_value=0.0),
        ):
            with self.assertRaisesRegex(ValueError, "未知候选人处理模式"):
                simple_brush.view_candidate(0)

    def assert_focus_restored_twice(self, click, choose_point):
        focus_call = call(
            500,
            400,
            offset=0,
            region_width=simple_brush.focus_restore_region.width,
            region_height=simple_brush.focus_restore_region.height,
        )
        self.assertEqual(
            choose_point.call_args_list,
            [
                call(simple_brush.focus_restore_region),
                call(simple_brush.focus_restore_region),
            ],
        )
        self.assertEqual(click.call_args_list, [focus_call, focus_call])

    def test_forward_restores_focus_after_success(self):
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value="test@example.com"),
            patch.object(simple_brush.pyautogui, "hotkey"),
            patch.object(simple_brush.pyautogui, "press"),
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        self.assertEqual(
            region_click.call_args_list,
            [
                call(simple_brush.forward_click_regions.forward_icon),
                call(simple_brush.forward_click_regions.email_tab),
                call(simple_brush.forward_click_regions.recent_email),
                call(simple_brush.forward_click_regions.input_box),
                call(simple_brush.forward_click_regions.forward_button),
            ],
        )
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_uses_calibrated_regions_and_reuses_input_box_region(self):
        calibrated = simple_brush.ForwardClickRegions(
            forward_icon=simple_brush.ScreenRegion(10, 20, 12, 12),
            email_tab=simple_brush.ScreenRegion(30, 40, 12, 12),
            input_box=simple_brush.ScreenRegion(50, 60, 20, 12),
            recent_email=simple_brush.ScreenRegion(70, 80, 12, 12),
            forward_button=simple_brush.ScreenRegion(90, 100, 20, 12),
        )
        simple_brush.forward_click_regions = calibrated
        simple_brush.backup_email = "backup@example.com"
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value=""),
            patch.object(simple_brush, "type_text_human", return_value=True),
            patch.object(simple_brush.pyautogui, "hotkey"),
            patch.object(simple_brush.pyautogui, "press"),
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        self.assertEqual(
            region_click.call_args_list,
            [
                call(calibrated.forward_icon),
                call(calibrated.email_tab),
                call(calibrated.recent_email),
                call(calibrated.input_box),
                call(calibrated.input_box),
                call(calibrated.forward_button),
            ],
        )
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_email_marker_is_not_logged_but_is_typed_unchanged(self):
        private_email = (
            "r04-private-user-7f2a@privacy-marker.invalid"
        )
        private_user, private_domain = private_email.split("@", 1)
        simple_brush.backup_email = private_email
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value=""),
            patch.object(
                simple_brush,
                "type_text_human",
                return_value=True,
            ) as type_text,
            patch.object(simple_brush.pyautogui, "hotkey"),
            patch.object(simple_brush.pyautogui, "press"),
            patch.object(simple_brush.time, "sleep"),
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "warning") as warning,
            patch.object(simple_brush.logger, "error") as error,
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        type_text.assert_called_once_with(private_email)
        self.assertEqual(
            region_click.call_args_list,
            [
                call(simple_brush.forward_click_regions.forward_icon),
                call(simple_brush.forward_click_regions.email_tab),
                call(simple_brush.forward_click_regions.recent_email),
                call(simple_brush.forward_click_regions.input_box),
                call(simple_brush.forward_click_regions.input_box),
                call(simple_brush.forward_click_regions.forward_button),
            ],
        )
        self.assert_focus_restored_twice(click, choose_point)
        rendered = "\n".join(render_log_calls(info, warning, error))
        self.assertNotIn(private_email, rendered)
        self.assertNotIn(private_user, rendered)
        self.assertNotIn(private_domain, rendered)
        self.assertIn(
            "alternate_email_provided=true email_source=manual",
            rendered,
        )

    def test_recent_contact_email_marker_is_not_logged_or_retyped(self):
        private_email = (
            "r04-recent-user-8c3b@recent-privacy.invalid"
        )
        private_user, private_domain = private_email.split("@", 1)
        with (
            patch.object(simple_brush, "click_in_region"),
            patch.object(simple_brush, "human_click"),
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ),
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(
                simple_brush,
                "get_clipboard_text",
                return_value=private_email,
            ),
            patch.object(simple_brush, "type_text_human") as type_text,
            patch.object(simple_brush.pyautogui, "hotkey"),
            patch.object(simple_brush.pyautogui, "press"),
            patch.object(simple_brush.time, "sleep"),
            patch.object(simple_brush.logger, "info") as info,
            patch.object(simple_brush.logger, "warning") as warning,
            patch.object(simple_brush.logger, "error") as error,
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        type_text.assert_not_called()
        rendered = "\n".join(render_log_calls(info, warning, error))
        self.assertNotIn(private_email, rendered)
        self.assertNotIn(private_user, rendered)
        self.assertNotIn(private_domain, rendered)
        self.assertIn(
            "email_provided=true email_source=recent_contact",
            rendered,
        )

    def test_forward_restores_focus_at_consecutive_limit(self):
        simple_brush.forward_consecutive = simple_brush.FORWARD_MAX_CONSEC
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        region_click.assert_not_called()
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_without_backup_email(self):
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value=""),
            patch.object(simple_brush.pyautogui, "hotkey"),
            patch.object(simple_brush.pyautogui, "press"),
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        self.assertEqual(
            region_click.call_args_list,
            [
                call(simple_brush.forward_click_regions.forward_icon),
                call(simple_brush.forward_click_regions.email_tab),
                call(simple_brush.forward_click_regions.recent_email),
                call(simple_brush.forward_click_regions.input_box),
            ],
        )
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_when_wait_is_interrupted(self):
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=False),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        region_click.assert_called_once_with(simple_brush.forward_click_regions.forward_icon)
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_when_forwarding_raises(self):
        with (
            patch.object(
                simple_brush,
                "click_in_region",
                side_effect=RuntimeError("forward failed"),
            ) as region_click,
            patch.object(
                simple_brush,
                "human_click",
            ) as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "forward failed"):
                simple_brush.forward_one_candidate()

        region_click.assert_called_once_with(simple_brush.forward_click_regions.forward_icon)
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_from_calibrated_runtime_region(self):
        simple_brush.focus_restore_region = simple_brush.ScreenRegion(
            left=600,
            top=300,
            width=120,
            height=60,
        )
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(650, 330),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value="test@example.com"),
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        self.assertEqual(region_click.call_count, 5)
        self.assertEqual(
            hotkey.call_args_list,
            [call("ctrl", "a"), call("ctrl", "c")],
        )
        self.assertEqual(
            choose_point.call_args_list,
            [
                call(simple_brush.focus_restore_region),
                call(simple_brush.focus_restore_region),
            ],
        )
        focus_call = call(
            650,
            330,
            offset=0,
            region_width=120,
            region_height=60,
        )
        self.assertEqual(click.call_args_list, [focus_call, focus_call])

    def test_second_focus_restore_is_attempted_when_first_click_raises(self):
        simple_brush.forward_consecutive = simple_brush.FORWARD_MAX_CONSEC
        with (
            patch.object(
                simple_brush,
                "random_point_in_region",
                side_effect=[(500, 400), (501, 401)],
            ) as choose_point,
            patch.object(
                simple_brush,
                "human_click",
                side_effect=[RuntimeError("first restore failed"), None],
            ) as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
            patch.object(simple_brush.logger, "error") as log_error,
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        self.assertEqual(
            choose_point.call_args_list,
            [
                call(simple_brush.focus_restore_region),
                call(simple_brush.focus_restore_region),
            ],
        )
        self.assertEqual(
            click.call_args_list,
            [
                call(
                    500,
                    400,
                    offset=0,
                    region_width=simple_brush.focus_restore_region.width,
                    region_height=simple_brush.focus_restore_region.height,
                ),
                call(
                    501,
                    401,
                    offset=0,
                    region_width=simple_brush.focus_restore_region.width,
                    region_height=simple_brush.focus_restore_region.height,
                ),
            ],
        )
        delay.assert_called_once_with(0.3, 0.5)
        log_error.assert_called_once()
        rendered = render_log_calls(log_error)[0]
        self.assertIn("第 1 次", rendered)
        self.assertIn("error_type=RuntimeError", rendered)

    def test_calibration_escape_does_not_stop_browsing(self):
        simple_brush.ocr_calibration_in_progress = True
        result = simple_brush.on_press(simple_brush.keyboard.Key.esc)
        self.assertTrue(result)
        self.assertFalse(simple_brush.stop_event)

    def test_focus_restore_default_region_includes_original_boundaries(self):
        self.assertEqual(
            simple_brush.DEFAULT_FOCUS_RESTORE_REGION,
            simple_brush.ScreenRegion(left=400, top=350, width=101, height=51),
        )

    def test_default_forward_click_regions_preserve_existing_click_ranges(self):
        regions = simple_brush.DEFAULT_FORWARD_CLICK_REGIONS
        self.assertEqual(
            regions.forward_icon,
            simple_brush.ScreenRegion(left=1665, top=255, width=11, height=11),
        )
        self.assertEqual(
            regions.email_tab,
            simple_brush.ScreenRegion(left=695, top=595, width=11, height=11),
        )
        self.assertEqual(
            regions.input_box,
            simple_brush.ScreenRegion(left=897, top=387, width=7, height=7),
        )
        self.assertEqual(
            regions.recent_email,
            simple_brush.ScreenRegion(left=995, top=435, width=11, height=11),
        )
        self.assertEqual(
            regions.forward_button,
            simple_brush.ScreenRegion(left=1205, top=735, width=11, height=11),
        )

    def test_region_around_rejects_negative_radius(self):
        with self.assertRaisesRegex(ValueError, "半径不能为负数"):
            simple_brush.region_around(10, 20, -1)

    def test_click_in_region_chooses_once_and_disables_second_offset(self):
        region = simple_brush.ScreenRegion(left=10, top=20, width=5, height=6)
        with (
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(12, 24),
            ) as choose_point,
            patch.object(simple_brush, "human_click") as click,
        ):
            simple_brush.click_in_region(region)
        choose_point.assert_called_once_with(region)
        click.assert_called_once_with(
            12,
            24,
            offset=0,
            region_width=5,
            region_height=6,
        )

    def test_reset_forward_click_calibration_restores_defaults(self):
        simple_brush.forward_click_regions = simple_brush.ForwardClickRegions(
            forward_icon=simple_brush.ScreenRegion(1, 2, 3, 4),
            email_tab=simple_brush.ScreenRegion(5, 6, 7, 8),
            input_box=simple_brush.ScreenRegion(9, 10, 11, 12),
            recent_email=simple_brush.ScreenRegion(13, 14, 15, 16),
            forward_button=simple_brush.ScreenRegion(17, 18, 19, 20),
        )
        simple_brush.forward_click_calibration_requested = True
        simple_brush.forward_click_calibration_attempted = True
        simple_brush.forward_click_calibration_in_progress = True
        simple_brush.reset_forward_click_calibration()
        self.assertEqual(
            simple_brush.forward_click_regions,
            simple_brush.DEFAULT_FORWARD_CLICK_REGIONS,
        )
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_attempted)
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)

    def test_forward_click_calibration_selects_in_order_and_publishes_atomically(self):
        regions = [
            simple_brush.ScreenRegion(index * 10, index * 20, 12, 12)
            for index in range(1, 6)
        ]
        simple_brush.forward_click_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=regions,
            ) as select,
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
            patch.object(
                simple_brush,
                "close_forward_dialog_after_calibration",
            ) as close_dialog,
        ):
            result = simple_brush.ensure_forward_click_regions_calibrated()

        self.assertEqual(
            result,
            simple_brush.ForwardClickRegions(
                forward_icon=regions[0],
                email_tab=regions[1],
                input_box=regions[2],
                recent_email=regions[3],
                forward_button=regions[4],
            ),
        )
        self.assertEqual(select.call_count, 5)
        self.assertEqual(
            [item.kwargs["subtitle"].split(" · ")[0] for item in select.call_args_list],
            ["校准 1/5", "校准 2/5", "校准 3/5", "校准 4/5", "校准 5/5"],
        )
        self.assertEqual(click.call_args_list, [call(regions[0]), call(regions[1])])
        self.assertNotIn(call(regions[4]), click.call_args_list)
        self.assertEqual(delay.call_args_list, [call(0.8, 1.2), call(0.5, 0.8)])
        close_dialog.assert_called_once_with()
        self.assertTrue(simple_brush.forward_click_calibration_attempted)
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)

    def test_cancelled_forward_click_calibration_falls_back_atomically_and_once(self):
        first = simple_brush.ScreenRegion(10, 20, 12, 12)
        simple_brush.forward_click_regions = simple_brush.ForwardClickRegions(
            forward_icon=simple_brush.ScreenRegion(1, 2, 3, 4),
            email_tab=simple_brush.ScreenRegion(5, 6, 7, 8),
            input_box=simple_brush.ScreenRegion(9, 10, 11, 12),
            recent_email=simple_brush.ScreenRegion(13, 14, 15, 16),
            forward_button=simple_brush.ScreenRegion(17, 18, 19, 20),
        )
        simple_brush.forward_click_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=[first, simple_brush.CalibrationCancelled],
            ) as select,
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "close_forward_dialog_after_calibration") as close,
        ):
            first_result = simple_brush.ensure_forward_click_regions_calibrated()
            second_result = simple_brush.ensure_forward_click_regions_calibrated()

        self.assertEqual(first_result, simple_brush.DEFAULT_FORWARD_CLICK_REGIONS)
        self.assertEqual(second_result, simple_brush.DEFAULT_FORWARD_CLICK_REGIONS)
        self.assertEqual(select.call_count, 2)
        click.assert_called_once_with(first)
        close.assert_called_once_with()
        self.assertTrue(simple_brush.forward_click_calibration_attempted)
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)
        self.assertFalse(simple_brush.stop_event)

    def test_failed_forward_click_calibration_falls_back_without_stopping(self):
        simple_brush.forward_click_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=RuntimeError("overlay failed"),
            ),
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "close_forward_dialog_after_calibration") as close,
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            result = simple_brush.ensure_forward_click_regions_calibrated()

        self.assertEqual(result, simple_brush.DEFAULT_FORWARD_CLICK_REGIONS)
        click.assert_not_called()
        close.assert_called_once_with()
        log_exception.assert_called_once()
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)
        self.assertFalse(simple_brush.stop_event)

    def test_forward_click_calibration_is_skipped_when_not_requested(self):
        with (
            patch.object(simple_brush, "select_screen_region") as select,
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "close_forward_dialog_after_calibration") as close,
        ):
            result = simple_brush.ensure_forward_click_regions_calibrated()
        self.assertEqual(result, simple_brush.DEFAULT_FORWARD_CLICK_REGIONS)
        select.assert_not_called()
        click.assert_not_called()
        close.assert_not_called()

    def test_forward_click_calibration_escape_does_not_stop_browsing(self):
        simple_brush.forward_click_calibration_in_progress = True
        result = simple_brush.on_press(simple_brush.keyboard.Key.esc)
        self.assertTrue(result)
        self.assertFalse(simple_brush.stop_event)

    def test_calibration_dialog_close_uses_programmatic_escape(self):
        with patch.object(simple_brush.pyautogui, "press") as press:
            simple_brush.close_forward_dialog_after_calibration()
        press.assert_called_once_with("esc")
        self.assertFalse(simple_brush._programmatic_esc)

    def test_reset_batch_filter_calibration_clears_runtime_state(self):
        simple_brush.batch_filter_regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(1, 2, 20, 20),
            open_filter=simple_brush.ScreenRegion(3, 4, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(5, 6, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(7, 8, 12, 12),
        )
        simple_brush.batch_filter_calibration_requested = True
        simple_brush.batch_filter_calibration_attempted = True
        simple_brush.batch_filter_calibration_in_progress = True
        simple_brush.batch_filter_enabled = True

        simple_brush.reset_batch_filter_calibration()

        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)
        self.assertFalse(simple_brush.batch_filter_calibration_attempted)
        self.assertFalse(simple_brush.batch_filter_calibration_in_progress)
        self.assertFalse(simple_brush.batch_filter_enabled)

    def test_load_calibration_profile_into_runtime_loads_all_regions(self):
        profile = sample_profile()

        self.assertTrue(simple_brush.load_calibration_profile_into_runtime(profile))

        areas = profile.areas
        self.assertEqual(
            simple_brush.forward_click_regions,
            simple_brush.ForwardClickRegions(
                forward_icon=areas["forward_icon"],
                email_tab=areas["email_tab"],
                input_box=areas["input_box"],
                recent_email=areas["recent_email"],
                forward_button=areas["forward_button"],
            ),
        )
        self.assertEqual(
            simple_brush.batch_filter_regions,
            simple_brush.BatchFilterRegions(
                first_candidate=areas["first_candidate"],
                open_filter=areas["open_filter"],
                unseen_filter=areas["unseen_filter"],
                confirm_filter=areas["confirm_filter"],
            ),
        )
        self.assertTrue(simple_brush.batch_filter_enabled)
        self.assertEqual(simple_brush.focus_restore_region, areas["focus_restore_region"])
        self.assertEqual(simple_brush.favorite_button_region, areas["favorite_button_region"])
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)
        self.assertFalse(simple_brush.focus_restore_calibration_requested)

    def test_load_calibration_profile_accepts_dict_regions(self):
        profile = sample_profile()
        profile.areas["favorite_button_region"] = {
            "left": 1,
            "top": 2,
            "width": 3,
            "height": 4,
        }

        simple_brush.load_calibration_profile_into_runtime(profile)

        self.assertEqual(
            simple_brush.favorite_button_region,
            simple_brush.ScreenRegion(left=1, top=2, width=3, height=4),
        )

    def test_load_calibration_profile_missing_forward_field_rejects_forward_mode(self):
        original_forward = simple_brush.forward_click_regions
        profile = sample_profile(missing=("forward_icon",))

        with self.assertRaisesRegex(
            simple_brush.CalibrationProfileRuntimeLoadError,
            "forward_icon",
        ):
            simple_brush.load_calibration_profile_into_runtime(
                profile,
                action_mode_value=simple_brush.ACTION_MODE_FORWARD,
            )

        self.assertEqual(simple_brush.forward_click_regions, original_forward)
        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertIsNone(simple_brush.favorite_button_region)

    def test_load_calibration_profile_favorite_does_not_require_forward_regions(self):
        profile = sample_profile(missing=(
            "forward_icon",
            "email_tab",
            "input_box",
            "recent_email",
            "forward_button",
        ))

        self.assertTrue(simple_brush.load_calibration_profile_into_runtime(
            profile,
            action_mode_value=simple_brush.ACTION_MODE_FAVORITE,
        ))

        self.assertIsNone(simple_brush.forward_click_regions)
        self.assertEqual(
            simple_brush.favorite_button_region,
            profile.areas["favorite_button_region"],
        )
        self.assertEqual(
            simple_brush.focus_restore_region,
            profile.areas["focus_restore_region"],
        )

    def test_load_calibration_profile_missing_favorite_field_rejects_favorite_mode(self):
        profile = sample_profile(missing=("favorite_button_region",))

        with self.assertRaisesRegex(
            simple_brush.CalibrationProfileRuntimeLoadError,
            "favorite_button_region",
        ):
            simple_brush.load_calibration_profile_into_runtime(
                profile,
                action_mode_value=simple_brush.ACTION_MODE_FAVORITE,
            )

        self.assertIsNone(simple_brush.favorite_button_region)
        self.assertIsNone(simple_brush.batch_filter_regions)

    def test_load_calibration_profile_respects_no_batch_filter(self):
        profile = sample_profile()

        simple_brush.load_calibration_profile_into_runtime(
            profile,
            no_batch_filter=True,
        )

        self.assertIsNotNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_enabled)

    def test_load_calibration_profile_rejects_non_positive_region_size(self):
        profile = sample_profile()
        profile.areas["forward_icon"] = simple_brush.ScreenRegion(
            left=1,
            top=2,
            width=0,
            height=4,
        )

        with self.assertRaisesRegex(
            simple_brush.CalibrationProfileRuntimeLoadError,
            "forward_icon",
        ):
            simple_brush.load_calibration_profile_into_runtime(profile)

        self.assertEqual(
            simple_brush.forward_click_regions,
            simple_brush.DEFAULT_FORWARD_CLICK_REGIONS,
        )
        self.assertIsNone(simple_brush.batch_filter_regions)

    def test_batch_filter_calibration_selects_in_order_and_publishes_atomically(self):
        regions = [
            simple_brush.ScreenRegion(index * 10, index * 20, 24, 24)
            for index in range(1, 5)
        ]
        simple_brush.batch_filter_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=regions,
            ) as select,
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
            patch.object(
                simple_brush,
                "close_batch_filter_panel_after_calibration",
            ) as close_panel,
        ):
            result = simple_brush.ensure_batch_filter_regions_calibrated()

        expected = simple_brush.BatchFilterRegions(
            first_candidate=regions[0],
            open_filter=regions[1],
            unseen_filter=regions[2],
            confirm_filter=regions[3],
        )
        self.assertEqual(result, expected)
        self.assertEqual(simple_brush.batch_filter_regions, expected)
        self.assertTrue(simple_brush.batch_filter_enabled)
        self.assertTrue(simple_brush.batch_filter_calibration_attempted)
        self.assertFalse(simple_brush.batch_filter_calibration_in_progress)
        self.assertEqual(
            [item.kwargs["subtitle"].split(" · ")[0] for item in select.call_args_list],
            ["校准 1/4", "校准 2/4", "校准 3/4", "校准 4/4"],
        )
        click.assert_called_once_with(regions[1])
        self.assertNotIn(call(regions[0]), click.call_args_list)
        self.assertNotIn(call(regions[2]), click.call_args_list)
        self.assertNotIn(call(regions[3]), click.call_args_list)
        delay.assert_called_once_with(0.5, 1.0)
        close_panel.assert_called_once_with()

    def test_batch_filter_calibration_cancellation_is_atomic_at_every_region(self):
        regions = [
            simple_brush.ScreenRegion(index * 10, index * 20, 24, 24)
            for index in range(1, 5)
        ]
        for cancelled_index in range(4):
            with self.subTest(cancelled_index=cancelled_index):
                simple_brush.reset_batch_filter_calibration()
                simple_brush.batch_filter_calibration_requested = True
                side_effect = regions[:cancelled_index] + [
                    simple_brush.CalibrationCancelled()
                ]
                with (
                    patch.object(
                        simple_brush,
                        "select_screen_region",
                        side_effect=side_effect,
                    ),
                    patch.object(simple_brush, "click_in_region") as click,
                    patch.object(simple_brush, "human_delay", return_value=True),
                    patch.object(
                        simple_brush,
                        "close_batch_filter_panel_after_calibration",
                    ) as close_panel,
                ):
                    result = simple_brush.ensure_batch_filter_regions_calibrated()

                self.assertIsNone(result)
                self.assertIsNone(simple_brush.batch_filter_regions)
                self.assertFalse(simple_brush.batch_filter_enabled)
                self.assertTrue(simple_brush.batch_filter_calibration_attempted)
                self.assertFalse(simple_brush.batch_filter_calibration_in_progress)
                self.assertFalse(simple_brush.stop_event)
                if cancelled_index < 2:
                    click.assert_not_called()
                    close_panel.assert_not_called()
                else:
                    click.assert_called_once_with(regions[1])
                    close_panel.assert_called_once_with()

    def test_batch_filter_calibration_exception_before_open_does_not_press_escape(self):
        simple_brush.batch_filter_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=RuntimeError("overlay failed"),
            ),
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(
                simple_brush,
                "close_batch_filter_panel_after_calibration",
            ) as close_panel,
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            result = simple_brush.ensure_batch_filter_regions_calibrated()

        self.assertIsNone(result)
        self.assertFalse(simple_brush.batch_filter_enabled)
        click.assert_not_called()
        close_panel.assert_not_called()
        log_exception.assert_called_once()
        self.assertFalse(simple_brush.stop_event)

    def test_batch_filter_calibration_wait_interruption_closes_and_falls_back(self):
        first = simple_brush.ScreenRegion(10, 20, 24, 24)
        open_filter = simple_brush.ScreenRegion(30, 40, 12, 12)
        simple_brush.batch_filter_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=[first, open_filter],
            ),
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=False),
            patch.object(
                simple_brush,
                "close_batch_filter_panel_after_calibration",
            ) as close_panel,
        ):
            result = simple_brush.ensure_batch_filter_regions_calibrated()

        self.assertIsNone(result)
        self.assertFalse(simple_brush.batch_filter_enabled)
        click.assert_called_once_with(open_filter)
        close_panel.assert_called_once_with()

    def test_batch_filter_calibration_close_failure_prevents_publish(self):
        regions = [
            simple_brush.ScreenRegion(index * 10, index * 20, 24, 24)
            for index in range(1, 5)
        ]
        simple_brush.batch_filter_calibration_requested = True
        with (
            patch.object(simple_brush, "select_screen_region", side_effect=regions),
            patch.object(simple_brush, "click_in_region"),
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(
                simple_brush,
                "close_batch_filter_panel_after_calibration",
                side_effect=RuntimeError("escape failed"),
            ) as close_panel,
        ):
            result = simple_brush.ensure_batch_filter_regions_calibrated()

        self.assertIsNone(result)
        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_enabled)
        close_panel.assert_called_once_with()

    def test_batch_filter_calibration_is_only_attempted_once(self):
        simple_brush.batch_filter_calibration_requested = True
        with patch.object(
            simple_brush,
            "select_screen_region",
            side_effect=simple_brush.CalibrationCancelled(),
        ) as select:
            self.assertIsNone(simple_brush.ensure_batch_filter_regions_calibrated())
            self.assertIsNone(simple_brush.ensure_batch_filter_regions_calibrated())
        select.assert_called_once()
        self.assertTrue(simple_brush.batch_filter_calibration_attempted)

    def test_batch_filter_calibration_escape_does_not_stop_browsing(self):
        simple_brush.batch_filter_calibration_in_progress = True
        result = simple_brush.on_press(simple_brush.keyboard.Key.esc)
        self.assertTrue(result)
        self.assertFalse(simple_brush.stop_event)

    def test_batch_filter_panel_close_uses_programmatic_escape(self):
        with patch.object(simple_brush.pyautogui, "press") as press:
            simple_brush.close_batch_filter_panel_after_calibration()
        press.assert_called_once_with("esc")
        self.assertFalse(simple_brush._programmatic_esc)

    def test_apply_batch_filter_clicks_regions_in_order(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )
        simple_brush.batch_filter_regions = regions
        simple_brush.batch_filter_enabled = True
        with (
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
            patch.object(simple_brush, "safe_wait", return_value=True) as wait,
        ):
            self.assertTrue(
                simple_brush.apply_batch_filter_and_open_first_candidate()
            )

        self.assertEqual(
            click.call_args_list,
            [
                call(regions.open_filter),
                call(regions.unseen_filter),
                call(regions.confirm_filter),
                call(regions.first_candidate),
            ],
        )
        self.assertEqual(
            delay.call_args_list,
            [
                call(
                    simple_brush.FILTER_OPEN_DELAY_MIN,
                    simple_brush.FILTER_OPEN_DELAY_MAX,
                ),
                call(
                    simple_brush.FILTER_OPTION_DELAY_MIN,
                    simple_brush.FILTER_OPTION_DELAY_MAX,
                ),
                call(
                    simple_brush.FILTER_RESULTS_DELAY_MIN,
                    simple_brush.FILTER_RESULTS_DELAY_MAX,
                ),
            ],
        )
        wait.assert_called_once_with(simple_brush.CLICK_WAIT_SECONDS)

    def test_apply_batch_filter_stops_after_interrupted_wait(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )
        simple_brush.batch_filter_regions = regions
        simple_brush.batch_filter_enabled = True
        with (
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(
                simple_brush,
                "human_delay",
                side_effect=[True, False],
            ),
            patch.object(simple_brush, "safe_wait") as wait,
        ):
            self.assertFalse(
                simple_brush.apply_batch_filter_and_open_first_candidate()
            )

        self.assertEqual(
            click.call_args_list,
            [call(regions.open_filter), call(regions.unseen_filter)],
        )
        wait.assert_not_called()

    def test_apply_batch_filter_exception_fails_closed(self):
        simple_brush.batch_filter_regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )
        simple_brush.batch_filter_enabled = True
        with (
            patch.object(
                simple_brush,
                "click_in_region",
                side_effect=RuntimeError("click failed"),
            ) as click,
            patch.object(simple_brush, "human_delay") as delay,
            patch.object(simple_brush, "safe_wait") as wait,
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            self.assertFalse(
                simple_brush.apply_batch_filter_and_open_first_candidate()
            )
        click.assert_called_once_with(simple_brush.batch_filter_regions.open_filter)
        delay.assert_not_called()
        wait.assert_not_called()
        log_exception.assert_called_once()

    def test_random_focus_restore_point_uses_half_open_region_bounds(self):
        region = simple_brush.ScreenRegion(left=400, top=350, width=101, height=51)
        with patch.object(
            simple_brush.random,
            "randint",
            side_effect=[500, 400],
        ) as randint:
            self.assertEqual(simple_brush.random_point_in_region(region), (500, 400))
        self.assertEqual(
            randint.call_args_list,
            [call(400, 500), call(350, 400)],
        )

    def test_random_focus_restore_point_rejects_empty_region(self):
        with self.assertRaisesRegex(ValueError, "尺寸必须为正数"):
            simple_brush.random_point_in_region(
                simple_brush.ScreenRegion(left=400, top=350, width=0, height=51)
            )

    def test_random_inner_region_point_uses_center_sixty_percent(self):
        region = simple_brush.ScreenRegion(left=100, top=200, width=300, height=100)
        with patch.object(simple_brush.random, "uniform", side_effect=[160.0, 240.0]) as uniform:
            point = simple_brush.random_point_in_inner_region(region)
        self.assertEqual(point, (160.0, 240.0))
        self.assertEqual(
            uniform.call_args_list,
            [
                call(160.0, 340.0),
                call(220.0, 280.0),
            ],
        )

    def test_random_inner_region_point_rejects_empty_region(self):
        with self.assertRaisesRegex(ValueError, "尺寸必须为正数"):
            simple_brush.random_point_in_inner_region(
                simple_brush.ScreenRegion(left=100, top=200, width=0, height=100)
            )

    def test_perform_favorite_action_clicks_inner_region_and_waits(self):
        region = simple_brush.ScreenRegion(left=100, top=200, width=300, height=100)
        simple_brush.favorite_button_region = region
        with (
            patch.object(
                simple_brush,
                "random_point_in_inner_region",
                return_value=(180.5, 240.5),
            ) as random_point,
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush.time, "sleep") as sleep,
            patch.object(
                simple_brush,
                "restore_candidate_page_focus_after_favorite",
            ) as restore_focus,
        ):
            self.assertTrue(simple_brush.perform_favorite_action())
        random_point.assert_called_once_with(region)
        click.assert_called_once_with(
            180.5,
            240.5,
            offset=0,
            region_width=300,
            region_height=100,
        )
        sleep.assert_called_once_with(0.5)
        restore_focus.assert_called_once_with()

    def test_shared_detail_focus_restore_clicks_calibrated_region_twice(self):
        simple_brush.focus_restore_region = simple_brush.ScreenRegion(
            left=100, top=200, width=300, height=100,
        )
        with (
            patch.object(
                simple_brush,
                "random_point_in_region",
                side_effect=[(180.0, 240.0), (260.0, 250.0)],
            ) as random_point,
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
        ):
            self.assertTrue(simple_brush.restore_candidate_detail_focus())

        self.assertEqual(
            random_point.call_args_list,
            [
                call(simple_brush.focus_restore_region),
                call(simple_brush.focus_restore_region),
            ],
        )
        self.assertEqual(
            click.call_args_list,
            [
                call(180.0, 240.0, offset=0, region_width=300, region_height=100),
                call(260.0, 250.0, offset=0, region_width=300, region_height=100),
            ],
        )
        self.assertEqual(delay.call_args_list, [call(0.3, 0.5), call(0.3, 0.5)])

    def test_favorite_focus_wrapper_delegates_to_neutral_helper(self):
        with patch.object(
            simple_brush,
            "restore_candidate_detail_focus",
            return_value=False,
        ) as restore_focus:
            self.assertFalse(
                simple_brush.restore_candidate_page_focus_after_favorite()
            )

        restore_focus.assert_called_once_with()

    def test_legacy_focus_restore_entry_uses_safe_region_not_ocr_body(self):
        focus_region = simple_brush.ScreenRegion(
            left=100, top=100, width=100, height=80,
        )
        simple_brush.focus_restore_region = focus_region

        class OCRBodyForbidden:
            @property
            def region(self):
                raise AssertionError("focus restore must not access OCR body region")

        simple_brush.ocr_detector = OCRBodyForbidden()
        with (
            patch.object(
                simple_brush,
                "random_point_in_region",
                side_effect=[(120, 120), (180, 160)],
            ) as point,
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush, "human_delay", return_value=True),
        ):
            self.assertTrue(simple_brush.restore_candidate_page_focus())

        self.assertEqual(point.call_args_list, [call(focus_region), call(focus_region)])
        self.assertEqual(
            click.call_args_list,
            [
                call(120, 120, offset=0, region_width=100, region_height=80),
                call(180, 160, offset=0, region_width=100, region_height=80),
            ],
        )

    def test_r07_detector_receives_shared_safe_focus_restore_callback(self):
        ocr_region = simple_brush.ScreenRegion(
            left=1000, top=500, width=400, height=500,
        )
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                return_value=ocr_region,
            ),
            patch.object(simple_brush, "save_region_preview"),
            patch.object(simple_brush, "OCRKeywordDetector") as detector_class,
        ):
            self.assertTrue(simple_brush.ensure_ocr_region_calibrated())

        self.assertIs(
            detector_class.call_args.kwargs["restore_focus"],
            simple_brush.restore_candidate_detail_focus,
        )

    def test_shared_focus_restore_reports_failure_after_click_error(self):
        focus_region = simple_brush.ScreenRegion(
            left=100, top=100, width=100, height=80,
        )
        simple_brush.focus_restore_region = focus_region
        with (
            patch.object(
                simple_brush,
                "random_point_in_region",
                side_effect=[(120, 120), (180, 160)],
            ),
            patch.object(
                simple_brush,
                "human_click",
                side_effect=[RuntimeError("first click failed"), None],
            ) as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
        ):
            self.assertFalse(simple_brush.restore_candidate_detail_focus())

        self.assertEqual(click.call_count, 2)
        delay.assert_called_once_with(0.3, 0.5)

    def test_favorite_restore_uses_shared_calibrated_focus_region(self):
        favorite_region = simple_brush.ScreenRegion(
            left=100, top=200, width=60, height=30,
        )
        focus_region = simple_brush.ScreenRegion(
            left=600, top=300, width=120, height=60,
        )
        simple_brush.favorite_button_region = favorite_region
        simple_brush.focus_restore_region = focus_region
        simple_brush.ocr_detector = Mock(
            region=simple_brush.ScreenRegion(left=10, top=20, width=30, height=40),
        )
        with (
            patch.object(
                simple_brush,
                "random_point_in_inner_region",
                return_value=(120, 215),
            ) as favorite_point,
            patch.object(
                simple_brush,
                "random_point_in_region",
                side_effect=[(650, 330), (660, 340)],
            ) as focus_point,
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush.time, "sleep"),
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
        ):
            self.assertTrue(simple_brush.perform_favorite_action())

        favorite_point.assert_called_once_with(favorite_region)
        self.assertEqual(
            focus_point.call_args_list,
            [call(focus_region), call(focus_region)],
        )
        self.assertEqual(
            click.call_args_list,
            [
                call(120, 215, offset=0, region_width=60, region_height=30),
                call(650, 330, offset=0, region_width=120, region_height=60),
                call(660, 340, offset=0, region_width=120, region_height=60),
            ],
        )
        self.assertEqual(delay.call_args_list, [call(0.3, 0.5), call(0.3, 0.5)])

    def test_perform_favorite_action_restores_focus_after_favorite_click(self):
        region = simple_brush.ScreenRegion(left=100, top=200, width=300, height=100)
        simple_brush.favorite_button_region = region
        events = []

        def choose_point(_region):
            events.append("choose_favorite")
            return (180.0, 240.0)

        def click(*_args, **_kwargs):
            events.append("click_favorite")

        def wait(_seconds):
            events.append("favorite_wait")

        def restore_focus():
            events.append("restore_focus")
            return True

        with (
            patch.object(simple_brush, "random_point_in_inner_region", side_effect=choose_point),
            patch.object(simple_brush, "human_click", side_effect=click),
            patch.object(simple_brush.time, "sleep", side_effect=wait),
            patch.object(
                simple_brush,
                "restore_candidate_page_focus_after_favorite",
                side_effect=restore_focus,
            ),
        ):
            self.assertTrue(simple_brush.perform_favorite_action())

        self.assertEqual(
            events,
            ["choose_favorite", "click_favorite", "favorite_wait", "restore_focus"],
        )

    def test_perform_favorite_action_without_region_fails_without_clicking(self):
        simple_brush.favorite_button_region = None
        with (
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush.time, "sleep") as sleep,
            patch.object(
                simple_brush,
                "restore_candidate_page_focus_after_favorite",
            ) as restore_focus,
        ):
            self.assertFalse(simple_brush.perform_favorite_action())
        click.assert_not_called()
        sleep.assert_not_called()
        restore_focus.assert_not_called()

    def test_focus_restore_calibration_is_skipped_when_not_requested(self):
        with patch.object(simple_brush, "select_screen_region") as select:
            region = simple_brush.ensure_focus_restore_region_calibrated()
        self.assertEqual(region, simple_brush.DEFAULT_FOCUS_RESTORE_REGION)
        select.assert_not_called()
        self.assertFalse(simple_brush.focus_restore_calibration_attempted)

    def test_focus_restore_calibration_updates_runtime_region(self):
        calibrated = simple_brush.ScreenRegion(left=600, top=300, width=120, height=60)
        simple_brush.focus_restore_calibration_requested = True
        with patch.object(
            simple_brush,
            "select_screen_region",
            return_value=calibrated,
        ) as select:
            self.assertEqual(
                simple_brush.ensure_focus_restore_region_calibrated(),
                calibrated,
            )
        select.assert_called_once_with(
            min_size=20,
            instruction="拖动框选候选人详情页空白区域 · Esc 使用默认区域",
            subtitle="第一版仅支持主显示器",
        )
        self.assertEqual(simple_brush.focus_restore_region, calibrated)
        self.assertTrue(simple_brush.focus_restore_calibration_attempted)
        self.assertFalse(simple_brush.focus_restore_calibration_in_progress)

    def test_cancelled_focus_restore_calibration_keeps_default_and_runs_once(self):
        simple_brush.focus_restore_calibration_requested = True
        with patch.object(
            simple_brush,
            "select_screen_region",
            side_effect=simple_brush.CalibrationCancelled,
        ) as select:
            self.assertEqual(
                simple_brush.ensure_focus_restore_region_calibrated(),
                simple_brush.DEFAULT_FOCUS_RESTORE_REGION,
            )
            self.assertEqual(
                simple_brush.ensure_focus_restore_region_calibrated(),
                simple_brush.DEFAULT_FOCUS_RESTORE_REGION,
            )
        self.assertEqual(select.call_count, 1)
        self.assertFalse(simple_brush.focus_restore_calibration_in_progress)
        self.assertFalse(simple_brush.stop_event)

    def test_failed_focus_restore_calibration_keeps_default_region(self):
        simple_brush.focus_restore_calibration_requested = True
        simple_brush.focus_restore_region = simple_brush.ScreenRegion(1, 2, 3, 4)
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=RuntimeError("overlay failed"),
            ),
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            region = simple_brush.ensure_focus_restore_region_calibrated()
        self.assertEqual(region, simple_brush.DEFAULT_FOCUS_RESTORE_REGION)
        self.assertTrue(simple_brush.focus_restore_calibration_attempted)
        self.assertFalse(simple_brush.focus_restore_calibration_in_progress)
        log_exception.assert_called_once()

    def test_favorite_button_calibration_selects_when_missing(self):
        calibrated = simple_brush.ScreenRegion(left=1200, top=240, width=80, height=32)
        with patch.object(
            simple_brush,
            "select_screen_region",
            return_value=calibrated,
        ) as select:
            region = simple_brush.ensure_favorite_button_region_calibrated()
        self.assertEqual(region, calibrated)
        self.assertEqual(simple_brush.favorite_button_region, calibrated)
        select.assert_called_once_with(
            min_size=12,
            instruction='框选“收藏”按钮内部安全区域 · Esc 取消收藏区域校准',
            subtitle='调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态与校准时基本一致',
        )

    def test_favorite_button_calibration_reuses_current_process_region(self):
        calibrated = simple_brush.ScreenRegion(left=1200, top=240, width=80, height=32)
        simple_brush.favorite_button_region = calibrated
        with patch.object(simple_brush, "select_screen_region") as select:
            region = simple_brush.ensure_favorite_button_region_calibrated()
        self.assertEqual(region, calibrated)
        select.assert_not_called()

    def test_cancelled_favorite_button_calibration_fails_safely(self):
        with patch.object(
            simple_brush,
            "select_screen_region",
            side_effect=simple_brush.CalibrationCancelled,
        ) as select:
            region = simple_brush.ensure_favorite_button_region_calibrated()
        self.assertIsNone(region)
        self.assertIsNone(simple_brush.favorite_button_region)
        select.assert_called_once()
        self.assertFalse(simple_brush.stop_event)

    def test_failed_favorite_button_calibration_fails_safely(self):
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=RuntimeError("overlay failed"),
            ),
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            region = simple_brush.ensure_favorite_button_region_calibrated()
        self.assertIsNone(region)
        self.assertIsNone(simple_brush.favorite_button_region)
        log_exception.assert_called_once()

    def test_favorite_button_calibration_does_not_call_forward_calibration(self):
        calibrated = simple_brush.ScreenRegion(left=1200, top=240, width=80, height=32)
        with (
            patch.object(simple_brush, "select_screen_region", return_value=calibrated),
            patch.object(simple_brush, "ensure_forward_click_regions_calibrated") as forward_calibrate,
        ):
            region = simple_brush.ensure_favorite_button_region_calibrated()
        self.assertEqual(region, calibrated)
        forward_calibrate.assert_not_called()

    def test_run_resets_focus_restore_calibration_state(self):
        simple_brush.forward_click_regions = simple_brush.ForwardClickRegions(
            forward_icon=simple_brush.ScreenRegion(1, 2, 3, 4),
            email_tab=simple_brush.ScreenRegion(5, 6, 7, 8),
            input_box=simple_brush.ScreenRegion(9, 10, 11, 12),
            recent_email=simple_brush.ScreenRegion(13, 14, 15, 16),
            forward_button=simple_brush.ScreenRegion(17, 18, 19, 20),
        )
        simple_brush.forward_click_calibration_requested = True
        simple_brush.forward_click_calibration_attempted = True
        simple_brush.forward_click_calibration_in_progress = True
        simple_brush.focus_restore_region = simple_brush.ScreenRegion(1, 2, 3, 4)
        simple_brush.focus_restore_calibration_requested = True
        simple_brush.focus_restore_calibration_attempted = True
        simple_brush.focus_restore_calibration_in_progress = True
        simple_brush.batch_filter_regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(1, 2, 20, 20),
            open_filter=simple_brush.ScreenRegion(3, 4, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(5, 6, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(7, 8, 12, 12),
        )
        simple_brush.batch_filter_calibration_requested = True
        simple_brush.batch_filter_calibration_attempted = True
        simple_brush.batch_filter_calibration_in_progress = True
        simple_brush.batch_filter_enabled = True
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--duration-seconds", "invalid", "--auto"],
        ):
            self.assertEqual(simple_brush.run(), 2)
        self.assertEqual(
            simple_brush.focus_restore_region,
            simple_brush.DEFAULT_FOCUS_RESTORE_REGION,
        )
        self.assertFalse(simple_brush.focus_restore_calibration_requested)
        self.assertFalse(simple_brush.focus_restore_calibration_attempted)
        self.assertFalse(simple_brush.focus_restore_calibration_in_progress)
        self.assertEqual(
            simple_brush.forward_click_regions,
            simple_brush.DEFAULT_FORWARD_CLICK_REGIONS,
        )
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_attempted)
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)
        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)
        self.assertFalse(simple_brush.batch_filter_calibration_attempted)
        self.assertFalse(simple_brush.batch_filter_calibration_in_progress)
        self.assertFalse(simple_brush.batch_filter_enabled)

    def test_focus_restore_calibration_escape_does_not_stop_browsing(self):
        simple_brush.focus_restore_calibration_in_progress = True
        result = simple_brush.on_press(simple_brush.keyboard.Key.esc)
        self.assertTrue(result)
        self.assertFalse(simple_brush.stop_event)

    def test_cancelled_calibration_is_only_attempted_once(self):
        simple_brush.ocr_backend = Mock()
        simple_brush.ocr_capture = Mock()
        simple_brush.ocr_detector = None
        simple_brush.ocr_initialization_attempted = True
        simple_brush.ocr_calibration_attempted = False

        with patch.object(
            simple_brush,
            "select_screen_region",
            side_effect=simple_brush.CalibrationCancelled,
        ) as select:
            self.assertFalse(simple_brush.ensure_ocr_region_calibrated())
            self.assertFalse(simple_brush.ensure_ocr_region_calibrated())
        self.assertEqual(select.call_count, 1)
        self.assertFalse(simple_brush.stop_event)

    def test_no_forward_argument_is_parsed(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--keywords", "Python", "--no-forward", "--auto"],
        ):
            args = simple_brush.parse_args()
        self.assertTrue(args["no_forward"])
        self.assertEqual(args["keywords"], "Python")

    def test_no_batch_filter_argument_is_parsed(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--no-batch-filter"],
        ):
            args = simple_brush.parse_args()
        self.assertTrue(args["no_batch_filter"])

    def test_action_mode_argument_parses_favorite(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--action-mode", "favorite"],
        ):
            args = simple_brush.parse_args()
        self.assertEqual(args["action_mode"], simple_brush.ACTION_MODE_FAVORITE)

    def test_action_mode_argument_parses_forward(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--action-mode", "forward"],
        ):
            args = simple_brush.parse_args()
        self.assertEqual(args["action_mode"], simple_brush.ACTION_MODE_FORWARD)

    def test_calibration_profile_argument_is_parsed(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--auto", "--calibration-profile", "main"],
        ):
            args = simple_brush.parse_args()
        self.assertEqual(args["calibration_profile"], "main")

    def test_calibration_profile_argument_requires_value(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--calibration-profile"],
        ):
            with self.assertRaisesRegex(ValueError, "缺少模板名称"):
                simple_brush.parse_args()

    def test_action_mode_argument_rejects_invalid_value(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--action-mode", "invalid"],
        ):
            with self.assertRaisesRegex(ValueError, "favorite 或 forward"):
                simple_brush.parse_args()

    def test_duration_argument_is_parsed(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--duration-seconds", "60", "--auto"],
        ):
            args = simple_brush.parse_args()
        self.assertEqual(args["duration_seconds"], "60")

    def test_duration_argument_requires_a_value(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--duration-seconds"],
        ):
            with self.assertRaisesRegex(ValueError, "缺少秒数"):
                simple_brush.parse_args()

    def test_duration_parser_accepts_empty_zero_and_positive_integer(self):
        self.assertEqual(simple_brush.parse_duration_seconds(""), 0)
        self.assertEqual(simple_brush.parse_duration_seconds(" 0 "), 0)
        self.assertEqual(simple_brush.parse_duration_seconds("3600"), 3600)

    def test_duration_parser_rejects_invalid_values(self):
        for value in ("-1", "1.5", "abc", "10秒", "+1", "１"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    simple_brush.parse_duration_seconds(value)

    def test_action_mode_choice_parses_favorite(self):
        self.assertEqual(
            simple_brush.parse_action_mode_choice("1"),
            simple_brush.ACTION_MODE_FAVORITE,
        )

    def test_action_mode_choice_parses_forward(self):
        self.assertEqual(
            simple_brush.parse_action_mode_choice("2"),
            simple_brush.ACTION_MODE_FORWARD,
        )

    def test_action_mode_choice_strips_whitespace(self):
        self.assertEqual(
            simple_brush.parse_action_mode_choice(" 1 "),
            simple_brush.ACTION_MODE_FAVORITE,
        )

    def test_action_mode_choice_rejects_invalid_input(self):
        for value in ("", "0", "3", "favorite", "forward", "１", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    simple_brush.parse_action_mode_choice(value)

    def test_prompt_action_mode_retries_invalid_input(self):
        with patch("builtins.input", side_effect=["bad", "2"]), patch(
            "builtins.print"
        ) as mocked_print:
            mode = simple_brush.prompt_action_mode()
        self.assertEqual(mode, simple_brush.ACTION_MODE_FORWARD)
        mocked_print.assert_called_once_with('  输入无效，请输入 1 或 2。')

    def test_noninteractive_mode_defaults_action_mode_to_forward(self):
        simple_brush.action_mode = simple_brush.ACTION_MODE_FAVORITE
        simple_brush.get_user_input(
            keywords_str='"Python"',
            auto=True,
            action_mode_value=None,
        )
        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FORWARD)

    def test_noninteractive_mode_uses_explicit_action_mode(self):
        simple_brush.get_user_input(
            keywords_str='"Python"',
            auto=True,
            action_mode_value=simple_brush.ACTION_MODE_FAVORITE,
        )
        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FAVORITE)

    def test_noninteractive_mode_without_profile_does_not_load_templates(self):
        with (
            patch.object(simple_brush, "load_profile") as load_profile,
            patch.object(simple_brush, "scan_profiles") as scan_profiles,
            patch("builtins.input") as user_input,
        ):
            simple_brush.get_user_input(keywords_str='"Python"', auto=True)

        load_profile.assert_not_called()
        scan_profiles.assert_not_called()
        user_input.assert_not_called()
        self.assertIsNone(simple_brush.selected_calibration_profile)
        self.assertIsNone(simple_brush.batch_filter_regions)

    def test_noninteractive_mode_loads_explicit_calibration_profile(self):
        profile = sample_profile()
        match = Mock(matches=True, mismatches={})

        with (
            patch.object(simple_brush, "load_profile", return_value=profile) as load_profile,
            patch.object(simple_brush, "compare_system_info", return_value=match) as compare,
            patch("builtins.input") as user_input,
        ):
            simple_brush.get_user_input(
                keywords_str='"Python"',
                auto=True,
                calibration_profile_name="main",
            )

        load_profile.assert_called_once_with("main")
        compare.assert_called_once_with(profile.system_info)
        user_input.assert_not_called()
        self.assertIs(simple_brush.selected_calibration_profile, profile)
        self.assertEqual(
            simple_brush.forward_click_regions.forward_icon,
            profile.areas["forward_icon"],
        )
        self.assertEqual(
            simple_brush.batch_filter_regions.first_candidate,
            profile.areas["first_candidate"],
        )
        self.assertTrue(simple_brush.batch_filter_enabled)

    def test_calibration_profile_argument_alone_does_not_prompt(self):
        profile = sample_profile()
        match = Mock(matches=True, mismatches={})

        with (
            patch.object(simple_brush, "load_profile", return_value=profile),
            patch.object(simple_brush, "compare_system_info", return_value=match),
            patch("builtins.input") as user_input,
        ):
            simple_brush.get_user_input(calibration_profile_name="main")

        user_input.assert_not_called()
        self.assertIs(simple_brush.selected_calibration_profile, profile)

    def test_noninteractive_profile_respects_no_batch_filter(self):
        profile = sample_profile()
        with (
            patch.object(simple_brush, "load_profile", return_value=profile),
            patch.object(
                simple_brush,
                "compare_system_info",
                return_value=Mock(matches=True, mismatches={}),
            ),
        ):
            simple_brush.get_user_input(
                keywords_str='"Python"',
                auto=True,
                no_batch_filter=True,
                calibration_profile_name="main",
            )

        self.assertIsNotNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_enabled)

    def test_noninteractive_profile_missing_file_fails_before_prompting(self):
        with (
            patch.object(
                simple_brush,
                "load_profile",
                side_effect=CalibrationProfileError("cannot read profile: missing"),
            ),
            patch("builtins.input") as user_input,
        ):
            with self.assertRaisesRegex(ValueError, "校准模板加载失败"):
                simple_brush.get_user_input(
                    keywords_str='"Python"',
                    auto=True,
                    calibration_profile_name="missing",
                )

        user_input.assert_not_called()
        self.assertIsNone(simple_brush.batch_filter_regions)

    def test_noninteractive_profile_damaged_json_fails_before_prompting(self):
        with (
            patch.object(
                simple_brush,
                "load_profile",
                side_effect=CalibrationProfileError("invalid JSON"),
            ),
            patch("builtins.input") as user_input,
        ):
            with self.assertRaisesRegex(ValueError, "invalid JSON"):
                simple_brush.get_user_input(
                    keywords_str='"Python"',
                    auto=True,
                    calibration_profile_name="broken",
                )

        user_input.assert_not_called()

    def test_noninteractive_profile_system_mismatch_fails_closed(self):
        profile = sample_profile()
        mismatch = Mock(
            matches=False,
            mismatches={"screen_width": (1920, 2560), "dpi_scale": (1.25, 1.5)},
        )

        with (
            patch.object(simple_brush, "load_profile", return_value=profile),
            patch.object(simple_brush, "compare_system_info", return_value=mismatch),
        ):
            with self.assertRaisesRegex(ValueError, "系统信息不匹配"):
                simple_brush.get_user_input(
                    keywords_str='"Python"',
                    auto=True,
                    calibration_profile_name="main",
                )

        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertIsNone(simple_brush.favorite_button_region)

    def test_noninteractive_profile_missing_field_fails_closed(self):
        profile = sample_profile(missing=("forward_icon",))

        with (
            patch.object(simple_brush, "load_profile", return_value=profile),
            patch.object(
                simple_brush,
                "compare_system_info",
                return_value=Mock(matches=True, mismatches={}),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "forward_icon"):
                simple_brush.get_user_input(
                    keywords_str='"Python"',
                    auto=True,
                    calibration_profile_name="main",
                )

        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertIsNone(simple_brush.favorite_button_region)

    def test_interactive_mode_prompts_for_action_mode_before_keywords(self):
        events = []
        responses = iter(["", "n", ""])

        def choose_mode():
            events.append("mode")
            return simple_brush.ACTION_MODE_FAVORITE

        def user_input(_prompt):
            events.append("keyword" if len(events) == 1 else "input")
            return next(responses)

        with patch.object(
            simple_brush,
            "prompt_action_mode",
            side_effect=choose_mode,
        ), patch("builtins.input", side_effect=user_input):
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(events[:2], ["mode", "keyword"])
        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FAVORITE)

    def test_interactive_choice_one_sets_action_mode_to_favorite(self):
        with patch("builtins.input", side_effect=["1", "", "n", ""]):
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FAVORITE)

    def test_interactive_choice_two_sets_action_mode_to_forward(self):
        simple_brush.action_mode = simple_brush.ACTION_MODE_FAVORITE
        with patch("builtins.input", side_effect=["2", "", "n", ""]):
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FORWARD)

    def test_interactive_profile_empty_list_keeps_legacy_prompt_path(self):
        scan = Mock(profiles=[], invalid_profiles=[])
        with patch.object(simple_brush, "scan_profiles", return_value=scan), patch(
            "builtins.input",
            side_effect=["2", "", "n", ""],
        ) as user_input:
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(user_input.call_count, 4)
        self.assertIsNone(simple_brush.selected_calibration_profile)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_interactive_profile_selection_can_decline_template(self):
        summary = Mock(
            profile_name="main",
            path=Path("calibration_profiles/main.json"),
            created_at="2026-07-10T00:00:00",
        )
        scan = Mock(profiles=[summary], invalid_profiles=[])
        with (
            patch.object(simple_brush, "scan_profiles", return_value=scan),
            patch.object(simple_brush, "load_calibration_profile_into_runtime") as load_runtime,
            patch("builtins.input", side_effect=["2", "", "0", "n", ""]),
        ):
            simple_brush.get_user_input(no_forward=True)
        load_runtime.assert_not_called()
        self.assertIsNone(simple_brush.selected_calibration_profile)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_interactive_profile_selection_loads_template_and_skips_legacy_prompts(self):
        summary = Mock(
            profile_name="main",
            path=Path("calibration_profiles/main.json"),
            created_at="2026-07-10T00:00:00",
        )
        loaded_profile = sample_profile()
        scan = Mock(profiles=[summary], invalid_profiles=[])
        with (
            patch.object(simple_brush, "scan_profiles", return_value=scan),
            patch.object(simple_brush, "load_profile_file", return_value=loaded_profile) as load_profile,
            patch.object(
                simple_brush,
                "compare_system_info",
                return_value=Mock(matches=True, mismatches={}),
            ),
            patch("builtins.input", side_effect=["2", "", "1", ""]),
        ):
            simple_brush.get_user_input(no_forward=True)
        load_profile.assert_called_once_with(summary.path)
        self.assertIs(simple_brush.selected_calibration_profile, loaded_profile)
        self.assertEqual(
            simple_brush.forward_click_regions.forward_icon,
            loaded_profile.areas["forward_icon"],
        )
        self.assertEqual(
            simple_brush.batch_filter_regions.first_candidate,
            loaded_profile.areas["first_candidate"],
        )
        self.assertEqual(
            simple_brush.focus_restore_region,
            loaded_profile.areas["focus_restore_region"],
        )
        self.assertEqual(
            simple_brush.favorite_button_region,
            loaded_profile.areas["favorite_button_region"],
        )
        self.assertTrue(simple_brush.batch_filter_enabled)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_interactive_profile_selection_respects_no_batch_filter(self):
        summary = Mock(
            profile_name="main",
            path=Path("calibration_profiles/main.json"),
            created_at="2026-07-10T00:00:00",
        )
        loaded_profile = sample_profile()
        scan = Mock(profiles=[summary], invalid_profiles=[])
        with (
            patch.object(simple_brush, "scan_profiles", return_value=scan),
            patch.object(simple_brush, "load_profile_file", return_value=loaded_profile),
            patch.object(
                simple_brush,
                "compare_system_info",
                return_value=Mock(matches=True, mismatches={}),
            ),
            patch("builtins.input", side_effect=["2", "", "1", ""]),
        ):
            simple_brush.get_user_input(no_forward=True, no_batch_filter=True)
        self.assertIsNotNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_enabled)

    def test_interactive_profile_missing_field_falls_back_to_legacy_path(self):
        summary = Mock(
            profile_name="main",
            path=Path("calibration_profiles/main.json"),
            created_at="2026-07-10T00:00:00",
        )
        loaded_profile = sample_profile(missing=("forward_icon",))
        scan = Mock(profiles=[summary], invalid_profiles=[])
        with (
            patch.object(simple_brush, "scan_profiles", return_value=scan),
            patch.object(simple_brush, "load_profile_file", return_value=loaded_profile),
            patch.object(
                simple_brush,
                "compare_system_info",
                return_value=Mock(matches=True, mismatches={}),
            ),
            patch("builtins.input", side_effect=["2", "", "1", "n", ""]),
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertIsNone(simple_brush.selected_calibration_profile)
        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_interactive_profile_system_mismatch_can_fallback_to_legacy_path(self):
        summary = Mock(
            profile_name="main",
            path=Path("calibration_profiles/main.json"),
            created_at="2026-07-10T00:00:00",
        )
        loaded_profile = sample_profile()
        mismatch = Mock(
            matches=False,
            mismatches={"screen_width": (1920, 2560), "dpi_scale": (1.25, 1.5)},
        )
        scan = Mock(profiles=[summary], invalid_profiles=[])
        with (
            patch.object(simple_brush, "scan_profiles", return_value=scan),
            patch.object(simple_brush, "load_profile_file", return_value=loaded_profile),
            patch.object(simple_brush, "compare_system_info", return_value=mismatch),
            patch("builtins.input", side_effect=["2", "", "1", "0", "n", ""]),
            patch("builtins.print") as printed,
        ):
            simple_brush.get_user_input(no_forward=True)

        output = "\n".join(
            str(call_args.args[0])
            for call_args in printed.call_args_list
            if call_args.args
        )
        self.assertIn("当前环境与模板环境不一致", output)
        self.assertIn("调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态与校准时基本一致", output)
        self.assertIn("旧模板中的点击区域可能发生偏移", output)
        self.assertIsNone(simple_brush.selected_calibration_profile)
        self.assertIsNone(simple_brush.batch_filter_regions)

    def test_interactive_profile_system_mismatch_can_reselect_template(self):
        first = Mock(
            profile_name="old",
            path=Path("calibration_profiles/old.json"),
            created_at="2026-07-10T00:00:00",
        )
        second = Mock(
            profile_name="main",
            path=Path("calibration_profiles/main.json"),
            created_at="2026-07-10T00:00:00",
        )
        old_profile = sample_profile()
        old_profile.profile_name = "old"
        main_profile = sample_profile()
        scan = Mock(profiles=[first, second], invalid_profiles=[])
        mismatch = Mock(matches=False, mismatches={"screen_height": (1080, 900)})
        match = Mock(matches=True, mismatches={})
        with (
            patch.object(simple_brush, "scan_profiles", return_value=scan),
            patch.object(
                simple_brush,
                "load_profile_file",
                side_effect=[old_profile, main_profile],
            ),
            patch.object(
                simple_brush,
                "compare_system_info",
                side_effect=[mismatch, match],
            ),
            patch("builtins.input", side_effect=["2", "", "1", "r", "2", ""]),
        ):
            simple_brush.get_user_input(no_forward=True)

        self.assertIs(simple_brush.selected_calibration_profile, main_profile)
        self.assertEqual(
            simple_brush.forward_click_regions.forward_icon,
            main_profile.areas["forward_icon"],
        )

    def test_interactive_profile_read_failure_falls_back_to_legacy_path(self):
        summary = Mock(
            profile_name="broken",
            path=Path("calibration_profiles/broken.json"),
            created_at="2026-07-10T00:00:00",
        )
        scan = Mock(profiles=[summary], invalid_profiles=[])
        with (
            patch.object(simple_brush, "scan_profiles", return_value=scan),
            patch.object(
                simple_brush,
                "load_profile_file",
                side_effect=CalibrationProfileError("bad template"),
            ),
            patch("builtins.input", side_effect=["2", "", "1", "n", ""]),
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertIsNone(simple_brush.selected_calibration_profile)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_interactive_favorite_mode_skips_email_and_forward_calibration(self):
        with patch("builtins.input", side_effect=["1", '"Python"', "n", ""]) as user_input:
            simple_brush.get_user_input()
        self.assertEqual(user_input.call_count, 4)
        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FAVORITE)
        self.assertEqual(simple_brush.backup_email, "")
        self.assertTrue(simple_brush.focus_restore_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_requested)

    def test_interactive_duration_retries_invalid_input(self):
        with patch("builtins.input", side_effect=["2", "", "n", "invalid", "3"]):
            simple_brush.get_user_input()
        self.assertEqual(simple_brush.run_duration_seconds, 3)

    def test_auto_mode_rejects_invalid_duration(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--duration-seconds", "invalid", "--auto"],
        ), patch.object(simple_brush, "bring_edge_foreground") as bring_edge:
            self.assertEqual(simple_brush.run(), 2)
        bring_edge.assert_not_called()

    def test_run_noninteractive_bad_calibration_profile_returns_error(self):
        with (
            patch.object(
                simple_brush.sys,
                "argv",
                [
                    "simple_brush.py",
                    "--keywords",
                    '"Python"',
                    "--auto",
                    "--calibration-profile",
                    "missing",
                ],
            ),
            patch.object(
                simple_brush,
                "load_profile",
                side_effect=CalibrationProfileError("cannot read profile: missing"),
            ),
            patch.object(simple_brush, "bring_edge_foreground") as bring_edge,
        ):
            self.assertEqual(simple_brush.run(), 2)
        bring_edge.assert_not_called()

    def test_run_passes_cli_action_mode_to_user_input(self):
        def configure_input(**kwargs):
            simple_brush.action_mode = kwargs["action_mode_value"]
            simple_brush.forward_keywords = []
            simple_brush.forward_enabled = False
            simple_brush.run_duration_seconds = 0

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": '"Python"',
                "email": "",
                "duration_seconds": "",
                "no_forward": False,
                "no_batch_filter": False,
                "simple_mouse": False,
                "auto": True,
                "action_mode": simple_brush.ACTION_MODE_FAVORITE,
                "calibration_profile": "main",
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input) as user_input,
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)
        self.assertEqual(
            user_input.call_args.kwargs["action_mode_value"],
            simple_brush.ACTION_MODE_FAVORITE,
        )
        self.assertEqual(user_input.call_args.kwargs["calibration_profile_name"], "main")
        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FAVORITE)

    def test_auto_mode_parses_quoted_keyword_rules(self):
        simple_brush.get_user_input(
            keywords_str='"PR" and "AE"; "剪映"',
            auto=True,
        )
        self.assertTrue(simple_brush.forward_enabled)
        self.assertEqual(
            simple_brush.keyword_rule_sources(),
            ['"PR" and "AE"', '"剪映"'],
        )

    def test_auto_mode_parses_complete_not_keyword_rules(self):
        simple_brush.get_user_input(
            keywords_str='"A" or not "B" and "C"',
            auto=True,
        )
        self.assertTrue(simple_brush.forward_enabled)
        self.assertEqual(
            simple_brush.keyword_rule_sources(),
            ['"A" or not "B" and "C"'],
        )

    def test_auto_mode_rejects_unquoted_legacy_keywords(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--keywords", "Python;短剧", "--auto"],
        ), patch.object(simple_brush, "bring_edge_foreground") as bring_edge:
            self.assertEqual(simple_brush.run(), 2)
        bring_edge.assert_not_called()

    def test_auto_mode_rejects_pure_not_branch_before_opening_edge(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--keywords", 'not "销售" or "短剧"', "--auto"],
        ), patch.object(simple_brush, "bring_edge_foreground") as bring_edge:
            self.assertEqual(simple_brush.run(), 2)
        bring_edge.assert_not_called()

    def test_interactive_keyword_rules_retry_invalid_input(self):
        with patch(
            "builtins.input",
            side_effect=["2", "Python", '"Python" or "短剧"', "n", "n", ""],
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(
            simple_brush.keyword_rule_sources(),
            ['"Python" or "短剧"'],
        )

    def test_interactive_keyword_rules_retry_pure_not_branch(self):
        with patch(
            "builtins.input",
            side_effect=[
                "2",
                'not "销售"',
                '"短剧" and not "销售"',
                "n",
                "n",
                "",
            ],
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(
            simple_brush.keyword_rule_sources(),
            ['"短剧" and not "销售"'],
        )

    def test_interactive_mode_can_request_focus_restore_calibration(self):
        with patch(
            "builtins.input",
            side_effect=["2", '"Python"', "y", "n", ""],
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertTrue(simple_brush.focus_restore_calibration_requested)
        self.assertTrue(simple_brush.forward_click_calibration_requested)

    def test_interactive_mode_defaults_to_focus_restore_region_fallback(self):
        with patch(
            "builtins.input",
            side_effect=["2", '"Python"', "", "n", ""],
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertFalse(simple_brush.focus_restore_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_requested)

    def test_auto_mode_never_prompts_for_focus_restore_calibration(self):
        simple_brush.focus_restore_calibration_requested = True
        simple_brush.forward_click_calibration_requested = True
        simple_brush.batch_filter_calibration_requested = True
        with patch("builtins.input") as user_input, patch.object(
            simple_brush,
            "scan_profiles",
        ) as scan_profiles:
            simple_brush.get_user_input(keywords_str='"Python"', auto=True)
        user_input.assert_not_called()
        scan_profiles.assert_not_called()
        self.assertFalse(simple_brush.focus_restore_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)
        self.assertIsNone(simple_brush.selected_calibration_profile)

    def test_interactive_mode_without_keywords_does_not_offer_forward_calibration(self):
        with patch("builtins.input", side_effect=["2", "", "n", ""]) as user_input:
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(user_input.call_count, 4)
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.focus_restore_calibration_requested)

    def test_no_keywords_and_no_forward_can_request_batch_filter_calibration(self):
        with patch("builtins.input", side_effect=["2", "", "y", ""]):
            simple_brush.get_user_input(no_forward=True)
        self.assertTrue(simple_brush.batch_filter_calibration_requested)

    def test_no_batch_filter_skips_prompt_in_interactive_mode(self):
        with patch("builtins.input", side_effect=["2", "", ""]) as user_input:
            simple_brush.get_user_input(
                no_forward=True,
                no_batch_filter=True,
            )
        self.assertEqual(user_input.call_count, 3)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_cli_keywords_noninteractive_mode_never_prompts_for_batch_filter(self):
        simple_brush.batch_filter_calibration_requested = True
        with patch("builtins.input") as user_input:
            simple_brush.get_user_input(keywords_str='"Python"')
        user_input.assert_not_called()
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_run_calibrates_after_first_detail_opens_before_viewing(self):
        events = []

        def configure_input(**_kwargs):
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True

        def open_detail(_x, _y):
            events.append("detail")
            return True

        def calibrate():
            events.append("focus_calibrate")
            return simple_brush.DEFAULT_FOCUS_RESTORE_REGION

        def calibrate_forward():
            events.append("forward_calibrate")
            return simple_brush.DEFAULT_FORWARD_CLICK_REGIONS

        def calibrate_ocr():
            events.append("ocr_calibrate")
            return True

        def start_timer(_duration):
            events.append("timer_start")
            return None

        def view(_index, first_observation=None):
            events.append("view")
            return False, None

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", side_effect=open_detail),
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
                side_effect=calibrate,
            ) as ensure,
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
                side_effect=calibrate_forward,
            ) as ensure_forward,
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                side_effect=calibrate_ocr,
            ) as ensure_ocr,
            patch.object(simple_brush, "start_run_timer", side_effect=start_timer),
            patch.object(
                simple_brush,
                "run_detail_load_gate",
                return_value=("loaded", loaded_observation(), 0, "threshold_passed"),
            ),
            patch.object(simple_brush, "view_candidate", side_effect=view),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)
        self.assertEqual(
            events,
            [
                "detail",
                "focus_calibrate",
                "forward_calibrate",
                "ocr_calibrate",
                "timer_start",
                "view",
            ],
        )
        ensure.assert_called_once_with()
        ensure_forward.assert_called_once_with()
        ensure_ocr.assert_called_once_with()

    def test_run_interactive_favorite_calibrates_before_viewing(self):
        events = []

        def configure_input(**_kwargs):
            simple_brush.action_mode = simple_brush.ACTION_MODE_FAVORITE
            simple_brush.forward_enabled = True
            simple_brush.forward_keywords = [Mock(source='"Python"')]
            simple_brush.focus_restore_calibration_requested = True

        def record(name, result=True):
            def action(*_args, **_kwargs):
                events.append(name)
                return result
            return action

        favorite_region = simple_brush.ScreenRegion(left=1200, top=240, width=80, height=32)
        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
                "action_mode": None,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", side_effect=record("detail")),
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
                side_effect=record("focus_calibrate"),
            ) as focus_calibrate,
            patch.object(
                simple_brush,
                "ensure_favorite_button_region_calibrated",
                side_effect=record("favorite_calibrate", favorite_region),
            ) as favorite_calibrate,
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                side_effect=record("ocr_calibrate"),
            ),
            patch.object(simple_brush, "start_run_timer", side_effect=record("timer_start", None)),
            patch.object(
                simple_brush,
                "run_detail_load_gate",
                return_value=("loaded", loaded_observation(), 0, "threshold_passed"),
            ),
            patch.object(
                simple_brush,
                "view_candidate",
                side_effect=record("view", (False, None)),
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            events,
            [
                "detail",
                "focus_calibrate",
                "favorite_calibrate",
                "ocr_calibrate",
                "timer_start",
                "view",
            ],
        )
        focus_calibrate.assert_called_once_with()
        favorite_calibrate.assert_called_once_with()

    def test_run_cli_favorite_calibrates_before_viewing(self):
        events = []

        def record(name, result=True):
            def action(*_args, **_kwargs):
                events.append(name)
                return result
            return action

        favorite_region = simple_brush.ScreenRegion(left=1200, top=240, width=80, height=32)
        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": '"Python"',
                "email": "",
                "duration_seconds": "",
                "no_forward": False,
                "no_batch_filter": False,
                "simple_mouse": False,
                "auto": True,
                "action_mode": simple_brush.ACTION_MODE_FAVORITE,
            }),
            patch.object(
                simple_brush,
                "get_user_input",
                wraps=simple_brush.get_user_input,
            ),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", side_effect=record("detail")),
            patch.object(
                simple_brush,
                "ensure_favorite_button_region_calibrated",
                side_effect=record("favorite_calibrate", favorite_region),
            ) as favorite_calibrate,
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                side_effect=record("ocr_calibrate"),
            ),
            patch.object(simple_brush, "start_run_timer", side_effect=record("timer_start", None)),
            patch.object(
                simple_brush,
                "run_detail_load_gate",
                return_value=("loaded", loaded_observation(), 0, "threshold_passed"),
            ),
            patch.object(
                simple_brush,
                "view_candidate",
                side_effect=record("view", (False, None)),
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FAVORITE)
        self.assertEqual(
            events,
            ["detail", "favorite_calibrate", "ocr_calibrate", "timer_start", "view"],
        )
        favorite_calibrate.assert_called_once_with()

    def test_run_stops_when_favorite_calibration_fails(self):
        events = []

        def configure_input(**_kwargs):
            simple_brush.action_mode = simple_brush.ACTION_MODE_FAVORITE
            simple_brush.forward_enabled = True
            simple_brush.forward_keywords = [Mock(source='"Python"')]

        def open_detail(_x, _y):
            events.append("detail")
            return True

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
                "action_mode": None,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", side_effect=open_detail),
            patch.object(
                simple_brush,
                "ensure_favorite_button_region_calibrated",
                return_value=None,
            ) as favorite_calibrate,
            patch.object(simple_brush, "ensure_ocr_region_calibrated") as ocr_calibrate,
            patch.object(simple_brush, "start_run_timer") as start_timer,
            patch.object(simple_brush, "view_candidate") as view,
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(events, ["detail"])
        favorite_calibrate.assert_called_once_with()
        ocr_calibrate.assert_not_called()
        start_timer.assert_not_called()
        view.assert_not_called()

    def test_run_forward_mode_does_not_calibrate_favorite_button(self):
        def configure_input(**_kwargs):
            simple_brush.action_mode = simple_brush.ACTION_MODE_FORWARD
            simple_brush.forward_enabled = True
            simple_brush.forward_keywords = [Mock(source='"Python"')]

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
                "action_mode": None,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", return_value=True),
            patch.object(simple_brush, "ensure_favorite_button_region_calibrated") as favorite_calibrate,
            patch.object(simple_brush, "ensure_ocr_region_calibrated", return_value=True),
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(
                simple_brush,
                "view_candidate",
                return_value=(False, None),
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)

        favorite_calibrate.assert_not_called()

    def test_run_noninteractive_default_forward_does_not_calibrate_favorite_button(self):
        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": '"Python"',
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "no_batch_filter": False,
                "simple_mouse": False,
                "auto": True,
                "action_mode": None,
            }),
            patch.object(simple_brush, "get_user_input", wraps=simple_brush.get_user_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", return_value=True),
            patch.object(simple_brush, "ensure_favorite_button_region_calibrated") as favorite_calibrate,
            patch.object(simple_brush, "ensure_ocr_region_calibrated", return_value=True),
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(
                simple_brush,
                "view_candidate",
                return_value=(False, None),
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(simple_brush.action_mode, simple_brush.ACTION_MODE_FORWARD)
        favorite_calibrate.assert_not_called()

    def test_run_does_not_calibrate_when_first_detail_fails_to_open(self):
        def configure_input(**_kwargs):
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", return_value=False),
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
            ) as ensure,
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
            ) as ensure_forward,
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
            ) as ensure_ocr,
            patch.object(simple_brush, "start_run_timer") as start_timer,
        ):
            self.assertEqual(simple_brush.run(), 0)
        ensure.assert_not_called()
        ensure_forward.assert_not_called()
        ensure_ocr.assert_not_called()
        start_timer.assert_not_called()

    def test_run_batch_filter_success_prepares_before_timer_and_view(self):
        events = []
        timer = Mock()
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.batch_filter_calibration_requested = True
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True
            simple_brush.forward_enabled = True

        def calibrate_batch():
            events.append("batch_calibrate")
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True
            return regions

        def record(name, result=True):
            def action(*_args, **_kwargs):
                events.append(name)
                return result
            return action

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(
                simple_brush,
                "ensure_batch_filter_regions_calibrated",
                side_effect=calibrate_batch,
            ),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                side_effect=record("apply_filter"),
            ),
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(15, 25),
            ),
            patch.object(simple_brush.pyautogui, "position") as position,
            patch.object(simple_brush, "click_first_candidate") as legacy_click,
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
                side_effect=record("focus_calibrate"),
            ),
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
                side_effect=record("forward_calibrate"),
            ),
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                side_effect=record("ocr_calibrate"),
            ),
            patch.object(
                simple_brush,
                "start_run_timer",
                side_effect=record("timer_start", timer),
            ),
            patch.object(
                simple_brush,
                "run_detail_load_gate",
                return_value=("loaded", loaded_observation(), 0, "threshold_passed"),
            ),
            patch.object(
                simple_brush,
                "view_candidate",
                side_effect=record("view", (False, None)),
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            events,
            [
                "batch_calibrate",
                "apply_filter",
                "focus_calibrate",
                "forward_calibrate",
                "ocr_calibrate",
                "timer_start",
                "view",
            ],
        )
        position.assert_not_called()
        legacy_click.assert_not_called()
        timer.cancel.assert_called_once_with()

    def test_run_first_batch_filter_failure_stops_before_calibration_and_timer(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.batch_filter_calibration_requested = True
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True

        def calibrate_batch():
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True
            return regions

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(
                simple_brush,
                "ensure_batch_filter_regions_calibrated",
                side_effect=calibrate_batch,
            ),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                return_value=False,
            ),
            patch.object(simple_brush.pyautogui, "position") as position,
            patch.object(simple_brush, "click_first_candidate") as legacy_click,
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
            ) as focus_calibrate,
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
            ) as forward_calibrate,
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
            ) as ocr_calibrate,
            patch.object(simple_brush, "start_run_timer") as start_timer,
            patch.object(simple_brush, "view_candidate") as view,
        ):
            self.assertEqual(simple_brush.run(), 0)

        position.assert_not_called()
        legacy_click.assert_not_called()
        focus_calibrate.assert_not_called()
        forward_calibrate.assert_not_called()
        ocr_calibrate.assert_not_called()
        start_timer.assert_not_called()
        view.assert_not_called()

    def test_run_batch_filter_fallback_starts_timer_after_legacy_preparation(self):
        events = []
        timer = Mock()

        def configure_input(**_kwargs):
            simple_brush.batch_filter_calibration_requested = True
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True
            simple_brush.forward_enabled = True

        def calibrate_batch():
            events.append("batch_calibrate")
            simple_brush.batch_filter_regions = None
            simple_brush.batch_filter_enabled = False

        def record(name, result=True):
            def action(*_args, **_kwargs):
                events.append(name)
                return result
            return action

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(
                simple_brush,
                "ensure_batch_filter_regions_calibrated",
                side_effect=calibrate_batch,
            ),
            patch.object(simple_brush, "safe_wait", side_effect=record("countdown")),
            patch.object(
                simple_brush.pyautogui,
                "position",
                side_effect=record("position", (10, 20)),
            ),
            patch.object(
                simple_brush,
                "click_first_candidate",
                side_effect=record("legacy_click"),
            ),
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
                side_effect=record("focus_calibrate"),
            ),
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
                side_effect=record("forward_calibrate"),
            ),
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                side_effect=record("ocr_calibrate"),
            ),
            patch.object(
                simple_brush,
                "start_run_timer",
                side_effect=record("timer_start", timer),
            ),
            patch.object(
                simple_brush,
                "run_detail_load_gate",
                return_value=("loaded", loaded_observation(), 0, "threshold_passed"),
            ),
            patch.object(
                simple_brush,
                "view_candidate",
                side_effect=record("view", (False, None)),
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            events,
            [
                "batch_calibrate",
                "countdown",
                "position",
                "legacy_click",
                "focus_calibrate",
                "forward_calibrate",
                "ocr_calibrate",
                "timer_start",
                "view",
            ],
        )
        timer.cancel.assert_called_once_with()

    def test_run_reapplies_batch_filter_after_refresh_before_next_batch(self):
        events = []
        view_calls = 0
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True

        def apply_filter():
            events.append("apply_filter")
            return True

        def view(index):
            nonlocal view_calls
            view_calls += 1
            events.append(f"view({index})")
            if view_calls == 2:
                simple_brush.forward_consecutive = 3
            if view_calls == 3:
                simple_brush.stop_event = True
                return False, None
            return True, None

        def next_candidate():
            events.append("next")
            return True

        def refresh():
            self.assertEqual(simple_brush.forward_consecutive, 0)
            events.append("refresh")
            return True

        def start_timer(_duration):
            events.append("timer_start")
            return None

        with (
            patch.object(simple_brush, "BATCH_SIZE", 2),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                side_effect=apply_filter,
            ),
            patch.object(simple_brush, "start_run_timer", side_effect=start_timer),
            patch.object(simple_brush, "view_candidate", side_effect=view),
            patch.object(simple_brush, "next_candidate", side_effect=next_candidate),
            patch.object(simple_brush, "refresh_page", side_effect=refresh),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            events,
            [
                "apply_filter",
                "timer_start",
                "view(0)",
                "next",
                "view(1)",
                "refresh",
                "apply_filter",
                "view(0)",
            ],
        )

    def test_run_does_not_filter_next_batch_when_refresh_fails(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True

        with (
            patch.object(simple_brush, "BATCH_SIZE", 1),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                return_value=True,
            ) as apply_filter,
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(
                simple_brush,
                "view_candidate",
                return_value=(True, None),
            ) as view,
            patch.object(simple_brush, "refresh_page", return_value=False) as refresh,
        ):
            self.assertEqual(simple_brush.run(), 0)

        apply_filter.assert_called_once_with()
        view.assert_called_once_with(0)
        refresh.assert_called_once_with()

    def test_run_stops_before_next_view_when_batch_filter_reapply_fails(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True

        with (
            patch.object(simple_brush, "BATCH_SIZE", 1),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                side_effect=[True, False],
            ) as apply_filter,
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(
                simple_brush,
                "view_candidate",
                return_value=(True, None),
            ) as view,
            patch.object(simple_brush, "refresh_page", return_value=True) as refresh,
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(apply_filter.call_count, 2)
        view.assert_called_once_with(0)
        refresh.assert_called_once_with()

    def test_run_legacy_path_reuses_same_point_after_refresh(self):
        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_enabled = False

        with (
            patch.object(simple_brush, "BATCH_SIZE", 1),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(
                simple_brush,
                "click_first_candidate",
                side_effect=[True, False],
            ) as legacy_click,
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(
                simple_brush,
                "view_candidate",
                return_value=(True, None),
            ),
            patch.object(simple_brush, "refresh_page", return_value=True),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            legacy_click.call_args_list,
            [call(10, 20), call(10, 20)],
        )

    def test_zero_duration_does_not_create_timer(self):
        with patch.object(simple_brush.threading, "Timer") as timer_factory:
            self.assertIsNone(simple_brush.start_run_timer(0))
        timer_factory.assert_not_called()

    def test_positive_duration_starts_timer(self):
        timer = Mock()
        with patch.object(simple_brush.threading, "Timer", return_value=timer) as factory:
            self.assertIs(simple_brush.start_run_timer(60), timer)
        factory.assert_called_once_with(60, simple_brush.request_timed_stop)
        self.assertTrue(timer.daemon)
        timer.start.assert_called_once_with()

    def test_timed_stop_sets_existing_stop_flag(self):
        simple_brush.request_timed_stop()
        self.assertTrue(simple_brush.stop_event)
        self.assertEqual(simple_brush.stop_reason, "run_duration_elapsed")

    def test_run_does_not_start_timer_when_countdown_is_interrupted(self):
        with (
            patch.object(
                simple_brush.sys,
                "argv",
                ["simple_brush.py", "--duration-seconds", "5", "--auto"],
            ),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "start_run_timer") as start_timer,
            patch.object(simple_brush, "safe_wait", return_value=False),
            patch.object(simple_brush.listener, "start"),
        ):
            self.assertEqual(simple_brush.run(), 0)
        start_timer.assert_not_called()

    def test_stop_prevents_new_navigation_actions(self):
        simple_brush.stop_event = True
        with (
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
        ):
            self.assertFalse(simple_brush.click_first_candidate(10, 20))
            self.assertFalse(simple_brush.next_candidate())
            self.assertFalse(simple_brush.refresh_page())
            simple_brush.human_scroll_once()
        click.assert_not_called()
        press.assert_not_called()
        scroll.assert_not_called()

    def test_ocr_time_is_deducted_from_stay_budget(self):
        self.assertEqual(simple_brush.remaining_stay_seconds(12.0, 100.0, 107.5), 4.5)
        self.assertEqual(simple_brush.remaining_stay_seconds(12.0, 100.0, 115.0), 0.0)

    def test_ocr_wait_stops_when_escape_was_requested(self):
        with patch.object(simple_brush, "safe_wait", return_value=False):
            with self.assertRaises(simple_brush.OCRInterrupted):
                simple_brush.ocr_wait(0.6)

    def test_ocr_scroll_uses_configured_production_range(self):
        for steps in (600, 1000):
            with self.subTest(steps=steps):
                with (
                    patch.object(simple_brush.random, "randint", return_value=steps) as randint,
                    patch.object(simple_brush.pyautogui, "scroll") as scroll,
                ):
                    simple_brush.ocr_scroll_down()

                randint.assert_called_once_with(600, 1000)
                scroll.assert_called_once_with(-steps)

class BossBrowserWindowTests(unittest.TestCase):
    def test_window_match_accepts_supported_boss_titles(self):
        for process_name, title in (
            ('chrome.exe', 'BOSS直聘 - Google Chrome'),
            ('chrome.exe', '职位详情 - zhipin - Google Chrome'),
            ('msedge.exe', 'BOSS直聘 - Microsoft Edge'),
            ('msedge.exe', '职位详情 - zhipin - Microsoft Edge'),
        ):
            with self.subTest(process_name=process_name, title=title):
                self.assertTrue(simple_brush.is_boss_browser_window(title, process_name))

    def test_window_match_rejects_unrelated_titles_or_processes(self):
        for process_name, title in (
            ('chrome.exe', 'New Tab - Google Chrome'),
            ('msedge.exe', 'New Tab - Microsoft Edge'),
            ('firefox.exe', 'BOSS直聘 - Mozilla Firefox'),
            ('notepad.exe', 'BOSS notes'),
            ('code.exe', 'BossOCR.spec - BOSSOCR - Visual Studio Code'),
        ):
            with self.subTest(process_name=process_name, title=title):
                self.assertFalse(simple_brush.is_boss_browser_window(title, process_name))

    def _bring_foreground(self, windows):
        def enum_windows(callback, _):
            for hwnd, _title, _process_name in windows:
                callback(hwnd, None)

        titles = {hwnd: title for hwnd, title, _process_name in windows}
        processes = {hwnd: process_name for hwnd, _title, process_name in windows}
        patches = ExitStack()
        mocks = (
            patches.enter_context(
                patch.object(simple_brush.win32gui, 'EnumWindows', side_effect=enum_windows)
            ),
            patches.enter_context(
                patch.object(simple_brush.win32gui, 'IsWindowVisible', return_value=True)
            ),
            patches.enter_context(
                patch.object(simple_brush.win32gui, 'GetWindowText', side_effect=titles.__getitem__)
            ),
            patches.enter_context(
                patch.object(simple_brush, 'get_window_process_name', side_effect=processes.__getitem__)
            ),
            patches.enter_context(
                patch.object(simple_brush.win32gui, 'IsIconic', return_value=False)
            ),
            patches.enter_context(patch.object(simple_brush.win32gui, 'SetForegroundWindow')),
            patches.enter_context(patch.object(simple_brush.time, 'sleep')),
        )
        return patches, mocks

    def test_bring_boss_foreground_prefers_chrome_over_edge_regardless_of_enum_order(self):
        windows = [
            (101, 'BOSS直聘 - Microsoft Edge', 'msedge.exe'),
            (202, 'BOSS直聘 - Google Chrome', 'chrome.exe'),
        ]
        patches, mocks = self._bring_foreground(windows)
        with patches:
            self.assertTrue(simple_brush.bring_boss_foreground())
        mocks[5].assert_called_once_with(202)

    def test_bring_boss_foreground_uses_edge_when_chrome_is_absent(self):
        windows = [(101, 'BOSS直聘 - Microsoft Edge', 'msedge.exe')]
        patches, mocks = self._bring_foreground(windows)
        with patches:
            self.assertTrue(simple_brush.bring_boss_foreground())
        mocks[5].assert_called_once_with(101)

    def test_bring_boss_foreground_uses_chrome_when_edge_is_absent(self):
        windows = [(202, 'BOSS直聘 - Google Chrome', 'chrome.exe')]
        patches, mocks = self._bring_foreground(windows)
        with patches:
            self.assertTrue(simple_brush.bring_boss_foreground())
        mocks[5].assert_called_once_with(202)

    def test_bring_boss_foreground_returns_false_without_matching_window(self):
        windows = [(101, 'New Tab - Microsoft Edge', 'msedge.exe')]
        patches, mocks = self._bring_foreground(windows)
        with patches:
            self.assertFalse(simple_brush.bring_boss_foreground())
        mocks[5].assert_not_called()

    def test_bring_edge_foreground_delegates_to_new_compatibility_function(self):
        with patch.object(simple_brush, 'bring_boss_foreground', return_value=True) as bring_boss:
            self.assertTrue(simple_brush.bring_edge_foreground())
        bring_boss.assert_called_once_with()


class StartupMenuTests(unittest.TestCase):
    def test_interactive_menu_shows_and_run_delegates_to_existing_flow(self):
        with (
            patch.object(simple_brush.sys, "argv", ["simple_brush.py"]),
            patch("builtins.input", return_value="1") as user_input,
            patch.object(simple_brush, "run", return_value=0) as run,
        ):
            self.assertEqual(simple_brush.main(), 0)

        self.assertIn("开始运行 Ocria Am7", user_input.call_args.args[0])
        self.assertIn("创建或更新校准模板", user_input.call_args.args[0])
        run.assert_called_once_with()

    def test_template_generator_success_returns_to_startup_menu(self):
        with (
            patch.object(simple_brush.sys, "argv", ["simple_brush.py"]),
            patch("builtins.input", side_effect=["2", "0"]),
            patch.object(simple_brush, "calibration_template_main", return_value=0) as calibrate,
            patch.object(simple_brush, "run") as run,
        ):
            self.assertEqual(simple_brush.main(), 0)

        calibrate.assert_called_once_with()
        run.assert_not_called()

    def test_template_generator_cancel_returns_to_startup_menu(self):
        with (
            patch.object(simple_brush.sys, "argv", ["simple_brush.py"]),
            patch("builtins.input", side_effect=["2", "0"]),
            patch.object(simple_brush, "calibration_template_main", return_value=2) as calibrate,
        ):
            self.assertEqual(simple_brush.main(), 0)
        calibrate.assert_called_once_with()

    def test_template_generator_exception_is_reported_then_returns_to_menu(self):
        with (
            patch.object(simple_brush.sys, "argv", ["simple_brush.py"]),
            patch("builtins.input", side_effect=["2", "0"]),
            patch.object(simple_brush, "calibration_template_main", side_effect=RuntimeError("boom")),
            patch("builtins.print") as output,
        ):
            self.assertEqual(simple_brush.main(), 0)

        self.assertTrue(
            any("校准模板启动失败：boom" in str(call.args) for call in output.call_args_list)
        )

    def test_exit_does_not_enter_main_program(self):
        with (
            patch.object(simple_brush.sys, "argv", ["simple_brush.py"]),
            patch("builtins.input", return_value="0"),
            patch.object(simple_brush, "run") as run,
        ):
            self.assertEqual(simple_brush.main(), 0)
        run.assert_not_called()

    def test_invalid_startup_menu_input_reprompts(self):
        with (
            patch("builtins.input", side_effect=["bad", "0"]) as user_input,
            patch("builtins.print") as output,
        ):
            self.assertEqual(simple_brush.choose_startup_action(), "exit")
        self.assertEqual(user_input.call_count, 2)
        output.assert_called_once_with("  输入无效，请输入 1、2 或 0。")

    def test_noninteractive_options_bypass_startup_menu(self):
        cases = (
            ["simple_brush.py", "--auto"],
            ["simple_brush.py", "--keywords", '"Python"'],
            ["simple_brush.py", "--calibration-profile", "main"],
        )
        for argv in cases:
            with (
                self.subTest(argv=argv),
                patch.object(simple_brush.sys, "argv", argv),
                patch("builtins.input") as user_input,
                patch.object(simple_brush, "run", return_value=0) as run,
            ):
                self.assertEqual(simple_brush.main(), 0)
                user_input.assert_not_called()
                run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
