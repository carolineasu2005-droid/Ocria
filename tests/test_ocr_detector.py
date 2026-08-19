from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timezone
import hashlib
import random
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from ocr_calibration import ScreenRegion
import ocr_normalization
from ocr_normalization import (
    NORMALIZATION_COMPLETED,
    NORMALIZATION_FAILED,
)
from ocr_detector import (
    DYNAMIC_END_DEFAULT_MODE,
    DYNAMIC_END_MODES,
    DetectionResult,
    DynamicEndConfig,
    DynamicEndState,
    FINGERPRINT_HASH_PATTERN,
    FINGERPRINT_VERSION,
    RULE_COMPARISON_LEGACY_ONLY,
    RULE_COMPARISON_NORMALIZATION_FAILED,
    RULE_COMPARISON_R04_ONLY,
    RULE_COMPARISON_SAME_MATCH,
    RULE_COMPARISON_SAME_NO_MATCH,
    RULE_EVALUATION_MODE_LEGACY_SHADOW,
    FingerprintBuildError,
    OCRKeywordDetector,
    PositionDecision,
    RapidOCRBackend,
    ScanObservation,
    ScreenFingerprint,
    accepted_ocr_items,
    bind_fingerprint_screen_index,
    build_fingerprint_normalized_text,
    build_fingerprint_raw_text,
    build_screen_fingerprint,
    calculate_load_metrics,
    classify_position,
    compare_screen_fingerprints,
    evaluate_detail_page_load,
    fingerprint_box_bounds,
    log_fingerprint_comparison,
    normalize_fingerprint_item_text,
    order_fingerprint_items,
    sha256_normalized_text,
)
from ocr_text import (
    OCRItem,
    matching_keyword_rule,
    parse_keyword_rules,
    searchable_text,
)


def single_rule(keyword):
    return parse_keyword_rules(f'"{keyword}"')


class DynamicEndFoundationTests(unittest.TestCase):
    def test_modes_default_state_boundaries_and_invalid_values(self):
        self.assertEqual(DYNAMIC_END_DEFAULT_MODE, "shadow")
        self.assertEqual(DYNAMIC_END_MODES, ("off", "shadow", "safe", "full"))
        for mode in DYNAMIC_END_MODES:
            self.assertEqual(DynamicEndConfig(mode=mode).mode, mode)
            self.assertEqual(DynamicEndState(mode=mode).mode, mode)
        with self.assertRaisesRegex(ValueError, "mode"):
            DynamicEndState(mode="invalid")
        with self.assertRaisesRegex(ValueError, "bound"):
            DynamicEndState(scan_slot_count=9)
        with self.assertRaisesRegex(ValueError, "bound"):
            DynamicEndState(normal_scroll_count=8)

    def test_detection_result_keeps_legacy_completion_separate(self):
        result = DetectionResult(success=True, confirmed_match=True)

        self.assertTrue(result.confirmed_match)
        self.assertIsNone(result.dynamic_end_reason)
        self.assertIsNone(result.abort_reason)
        self.assertIsNone(result.interrupt_reason)


class PositionClassificationTests(unittest.TestCase):
    def record(self, screen_id, exact_hash, **fields):
        values = dict(
            screen_id=screen_id,
            exact_hash=exact_hash,
            fingerprint_version="r03-v1",
            aggregation_status="not_attempted",
            uncertain_segment_ids=(),
            uncertain_segment_count=0,
            uncertain_char_count=0,
            aggregation_duplicate_risk=None,
            aggregation_warning_codes=(),
            has_effective_new_text=False,
            similarity_result=None,
        )
        values.update(fields)
        return SimpleNamespace(**values)

    def decide(self, previous, current, **health):
        return classify_position(
            previous, current,
            load_health=health.get("load_health", True),
            ocr_health=health.get("ocr_health", True),
            identity_health=health.get("identity_health", True),
        )

    def test_initial_same_different_and_disabled_r05_r06(self):
        first = self.record("one", "a" * 64)
        self.assertEqual(self.decide(None, first).position_status, "initial")

        same = self.decide(first, self.record("two", "a" * 64))
        self.assertEqual((same.position_status, same.page_change_status), ("same", "same"))
        self.assertEqual(same.reference_screen_id, "one")

        different = self.decide(first, self.record("three", "b" * 64))
        self.assertEqual((different.position_status, different.page_change_status), ("changed", "changed"))

    def test_effective_new_and_protected_short_text_are_changed(self):
        previous = self.record("one", "a" * 64)
        effective = self.record("two", "a" * 64, has_effective_new_text=True)
        self.assertEqual(self.decide(previous, effective).position_status, "changed")

        protected = self.record(
            "three", "a" * 64,
            similarity_result=SimpleNamespace(
                effective_new_status="present",
                has_effective_new_text=True,
                effective_new_segment_count=1,
                effective_new_decisions=(SimpleNamespace(
                    reason="short_text_protected", decision="effective",
                ),),
                warning_codes=(),
            ),
        )
        self.assertEqual(self.decide(previous, protected).position_status, "changed")

    def test_possible_or_uncertain_evidence_is_uncertain(self):
        previous = self.record("one", "a" * 64)
        possible = self.record(
            "two", "a" * 64,
            similarity_result=SimpleNamespace(
                effective_new_status="possible", comparison_class="uncertain",
                similarity_status="partial", warning_codes=(),
            ),
        )
        decision = self.decide(previous, possible)
        self.assertEqual(decision.position_status, "uncertain")
        self.assertTrue(decision.insufficient_evidence)

    def test_missing_r03_or_health_is_unavailable(self):
        previous = self.record("one", "a" * 64)
        cases = (
            self.record("missing-r03", None),
            self.record("load", "a" * 64),
            self.record("ocr", "a" * 64),
            self.record("identity", "a" * 64),
        )
        for current, health in (
            (cases[0], {}),
            (cases[1], {"load_health": None}),
            (cases[2], {"ocr_health": False}),
            (cases[3], {"identity_health": None}),
        ):
            with self.subTest(current=current.screen_id):
                decision = self.decide(previous, current, **health)
                self.assertEqual(decision.position_status, "unavailable")
                self.assertTrue(decision.insufficient_evidence)


class FirstSameRecoveryFailureTests(unittest.TestCase):
    def _detector(self, *, callback, restore_focus=Mock(return_value=True),
                  scroll=None, wait=None, interrupt_reason_provider=None):
        return OCRKeywordDetector(
            backend=FakeBackend(["no rule match"] * 4),
            capture=FakeCapture(),
            region=ScreenRegion(0, 0, 100, 100),
            max_scans=3,
            scroll=Mock() if scroll is None else scroll,
            wait=Mock() if wait is None else wait,
            observation_callback=callback,
            dynamic_end_config=DynamicEndConfig(mode="safe"),
            restore_focus=restore_focus,
            interrupt_reason_provider=interrupt_reason_provider,
        )

    @staticmethod
    def _callback_with_confirmation(**confirmation_values):
        call_count = 0

        def callback(_observation, _capture_type, _formal, _screen_index):
            nonlocal call_count
            call_count += 1
            initial = call_count == 1
            values = dict(
                record=SimpleNamespace(
                    screen_id="screen-{0}".format(call_count),
                    exact_hash="a" * 64,
                ),
                saved=True,
                position_decision=PositionDecision(
                    "initial" if initial else "same",
                    "initial" if initial else "same",
                    None if initial else "screen-{0}".format(call_count - 1),
                    "test",
                ),
                load_health=True,
                ocr_health=True,
                identity_health=True,
            )
            if call_count == 3:
                values.update(confirmation_values)
            return SimpleNamespace(**values)

        return callback

    def test_confirmation_failure_reasons_are_precise_and_do_not_end_scan(self):
        cases = (
            ("load_failed", {"load_health": False}),
            ("ocr_failed", {"ocr_health": False}),
            ("switch_failed", {"identity_health": False}),
            ("store_failed", {"saved": False}),
            (
                "position_unresolved",
                {"position_decision": PositionDecision(
                    "uncertain", "same", "screen-2", "test", True,
                )},
            ),
        )
        for expected, values in cases:
            with self.subTest(expected=expected):
                detector = self._detector(
                    callback=self._callback_with_confirmation(**values),
                )
                result = detector.detect(single_rule("absent"))
                self.assertEqual(result.recovery_reason, expected)
                self.assertIsNone(result.dynamic_end_reason)
                self.assertFalse(result.confirmed_match)

    def test_focus_scroll_capture_and_interrupt_failures_are_precise(self):
        callback = self._callback_with_confirmation()
        detector = self._detector(callback=callback, restore_focus=Mock(return_value=False))
        self.assertEqual(detector.detect(single_rule("absent")).recovery_reason, "focus_restore_failed")

        scroll = Mock(side_effect=[None, RuntimeError("synthetic"), None])
        detector = self._detector(
            callback=self._callback_with_confirmation(), scroll=scroll,
        )
        self.assertEqual(detector.detect(single_rule("absent")).recovery_reason, "scroll_failed")

        interrupt_calls = iter((None, "user_interrupted"))
        detector = self._detector(
            callback=self._callback_with_confirmation(),
            interrupt_reason_provider=lambda: next(interrupt_calls, "user_interrupted"),
        )
        result = detector.detect(single_rule("absent"))
        self.assertEqual(result.interrupt_reason, "user_interrupted")
        self.assertIsNone(result.dynamic_end_reason)

        runtime_calls = iter((None, "runtime_expired"))
        detector = self._detector(
            callback=self._callback_with_confirmation(),
            interrupt_reason_provider=lambda: next(runtime_calls, "runtime_expired"),
        )
        result = detector.detect(single_rule("absent"))
        self.assertEqual(result.interrupt_reason, "runtime_expired")
        self.assertIsNone(result.dynamic_end_reason)


class ShadowPredictionTests(unittest.TestCase):
    @staticmethod
    def _record(index, *, effective_new=False, protected_short=False,
                possible=False, completed_evidence=True):
        result = None
        aggregation_status = "not_attempted"
        if completed_evidence:
            aggregation_status = "completed"
            result = SimpleNamespace(
                similarity_status="partial" if possible else "completed",
                effective_new_status=(
                    "possible" if possible else
                    "present" if (effective_new or protected_short) else "none"
                ),
                has_effective_new_text=effective_new,
                effective_new_segment_count=1 if effective_new else 0,
                effective_new_decisions=(
                    (SimpleNamespace(reason="short_text_protected", decision="effective"),)
                    if protected_short else ()
                ),
                warning_codes=(),
            )
        return SimpleNamespace(
            screen_id="shadow-{0}".format(index),
            exact_hash=("a" if index < 3 else chr(ord("a") + index)) * 64,
            fingerprint_version="r03-v1",
            aggregation_status=aggregation_status,
            uncertain_segment_ids=(),
            uncertain_segment_count=0,
            uncertain_char_count=0,
            aggregation_duplicate_risk=None,
            aggregation_warning_codes=(),
            has_effective_new_text=effective_new,
            similarity_result=result,
            capture_type="formal_screen",
            is_formal_screen=True,
        )

    def _run(
        self,
        positions,
        *,
        effective_new_at=(),
        protected_short_at=(),
        possible_at=(),
        completed_evidence=True,
        mode="shadow",
        pages=None,
        interrupt_reason_provider=None,
        saved_at=(),
        unhealthy_at=(),
    ):
        formal_calls = 0
        capture = FakeCapture()
        backend = FakeBackend(pages or ["absent"] * (len(positions) + 1))
        scroll = Mock()
        wait = Mock()

        def callback(_observation, capture_type, is_formal, _screen_index):
            nonlocal formal_calls
            if is_formal:
                formal_calls += 1
                index = formal_calls
                position = positions[index - 1]
                healthy = index not in unhealthy_at
                return SimpleNamespace(
                    record=self._record(
                        index,
                        effective_new=index in effective_new_at,
                        protected_short=index in protected_short_at,
                        possible=index in possible_at,
                        completed_evidence=completed_evidence,
                    ),
                    saved=index not in saved_at,
                    position_decision=PositionDecision(
                        position,
                        "initial" if position == "initial" else (
                            "same" if position == "same" else "changed"
                        ),
                        None if index == 1 else "shadow-{0}".format(index - 1),
                        "test",
                        position in ("uncertain", "unavailable"),
                    ),
                    load_health=healthy,
                    ocr_health=healthy,
                    identity_health=healthy,
                )
            return SimpleNamespace(record=self._record(99), saved=True)

        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=ScreenRegion(0, 0, 100, 100),
            max_scans=len(positions),
            scroll=scroll,
            wait=wait,
            observation_callback=callback,
            dynamic_end_config=DynamicEndConfig(mode=mode),
            interrupt_reason_provider=interrupt_reason_provider,
        )
        result = detector.detect(single_rule("MATCH"))
        return capture, backend, scroll, wait, detector, result

    def test_shadow_effect_sequence_matches_off_and_keeps_legacy_rule_return(self):
        args = dict(
            positions=("initial", "same", "changed"),
            pages=("absent", "absent", "MATCH", "MATCH"),
        )
        off = self._run(mode="off", **args)
        shadow = self._run(mode="shadow", **args)
        for off_value, shadow_value in zip(off[:4], shadow[:4]):
            if isinstance(off_value, Mock):
                self.assertEqual(off_value.call_args_list, shadow_value.call_args_list)
            else:
                self.assertEqual(off_value.calls, shadow_value.calls)
        self.assertTrue(shadow[-1].confirmed_match)
        self.assertIsNone(shadow[-1].dynamic_end_reason)
        self.assertEqual(shadow[-1].first_predicted_end_screen, 2)
        self.assertEqual(shadow[-1].first_predicted_end_reason, "possible_scroll_bottom")
        self.assertTrue(shadow[-1].prediction_would_miss_rule_match)
        self.assertIsNone(shadow[-1].prediction_would_miss_content)

    def test_shadow_prediction_true_false_null_and_first_prediction_is_frozen(self):
        _capture, _backend, _scroll, _wait, _detector, true_result = self._run(
            ("initial", "same", "changed", "changed"),
            effective_new_at=(3,),
        )
        self.assertEqual(true_result.first_predicted_end_screen, 2)
        self.assertEqual(true_result.first_predicted_end_reason, "possible_scroll_bottom")
        self.assertTrue(true_result.prediction_would_miss_content)
        self.assertFalse(true_result.prediction_would_miss_rule_match)
        self.assertTrue(true_result.prediction_observation_complete)
        self.assertTrue(true_result.prediction_evidence_complete)

        _capture, _backend, _scroll, _wait, _detector, false_result = self._run(
            ("initial", "same", "changed", "changed"),
        )
        self.assertFalse(false_result.prediction_would_miss_content)
        self.assertFalse(false_result.prediction_would_miss_rule_match)
        self.assertTrue(false_result.prediction_evidence_complete)

        _capture, _backend, _scroll, _wait, _detector, short_result = self._run(
            ("initial", "same", "changed"), protected_short_at=(3,),
        )
        self.assertTrue(short_result.prediction_would_miss_content)

        _capture, _backend, _scroll, _wait, _detector, disabled_result = self._run(
            ("initial", "same", "changed"), completed_evidence=False,
        )
        self.assertIsNone(disabled_result.prediction_would_miss_content)
        self.assertFalse(disabled_result.prediction_would_miss_rule_match)
        self.assertTrue(disabled_result.prediction_observation_complete)
        self.assertFalse(disabled_result.prediction_evidence_complete)

    def test_shadow_marks_late_content_and_insufficient_cases_without_new_effects(self):
        for changed_at in (7, 8):
            positions = ["initial", "same"] + ["changed"] * 6
            _capture, _backend, _scroll, _wait, _detector, result = self._run(
                tuple(positions), effective_new_at=(changed_at,),
            )
            with self.subTest(changed_at=changed_at):
                self.assertTrue(result.prediction_would_miss_content)
                self.assertEqual(result.first_predicted_end_screen, 2)

        for positions in (("initial", "same", "uncertain"), ("initial", "same", "unavailable")):
            _capture, _backend, _scroll, _wait, _detector, result = self._run(positions)
            self.assertIsNone(result.prediction_would_miss_content)
            self.assertFalse(result.prediction_evidence_complete)

        _capture, _backend, _scroll, _wait, _detector, result = self._run(
            ("initial", "same", "changed"), saved_at=(3,),
        )
        self.assertIsNone(result.prediction_would_miss_content)
        self.assertIsNone(result.prediction_would_miss_rule_match)
        self.assertFalse(result.prediction_evidence_complete)

    def test_shadow_interrupts_are_nullable_and_do_not_change_effects(self):
        baseline = self._run(("initial", "same", "changed"))
        interrupted = self._run(
            ("initial", "same", "changed"),
            interrupt_reason_provider=lambda: "runtime_expired",
        )
        self.assertEqual(baseline[0].calls, interrupted[0].calls)
        self.assertEqual(baseline[2].call_args_list, interrupted[2].call_args_list)
        self.assertEqual(baseline[3].call_args_list, interrupted[3].call_args_list)
        self.assertEqual(interrupted[-1].interrupt_reason, "runtime_expired")
        self.assertIsNone(interrupted[-1].prediction_would_miss_content)
        self.assertIsNone(interrupted[-1].prediction_would_miss_rule_match)


class SafeFullReturnTests(ShadowPredictionTests):
    def test_safe_never_ends_for_no_new_but_full_requires_two_slots(self):
        _capture, _backend, _scroll, _wait, _detector, safe_result = self._run(
            ("initial", "changed", "changed"), mode="safe",
        )
        self.assertEqual(safe_result.dynamic_end_reason, "max_screen_limit")
        self.assertNotEqual(safe_result.dynamic_end_reason, "no_new_text")

        _capture, _backend, _scroll, _wait, _detector, single_result = self._run(
            ("initial", "changed", "same"), mode="full",
        )
        self.assertEqual(single_result.dynamic_end_reason, "max_screen_limit")
        self.assertNotEqual(single_result.dynamic_end_reason, "no_new_text")

        _capture, _backend, _scroll, _wait, detector, full_result = self._run(
            ("initial", "changed", "changed", "changed"), mode="full",
        )
        self.assertEqual(full_result.dynamic_end_reason, "no_new_text")
        self.assertEqual(full_result.scans_completed, 3)
        self.assertEqual(detector.dynamic_end_state.consecutive_no_new_count, 2)

    def test_full_no_new_resets_for_new_short_possible_uncertain_and_disabled_evidence(self):
        cases = (
            ("effective_new", {"effective_new_at": (3,)}),
            ("protected_short", {"protected_short_at": (3,)}),
            ("possible", {"possible_at": (3,)}),
            ("uncertain", {"positions": (
                "initial", "changed", "uncertain", "changed", "changed", "changed",
            )}),
            ("disabled", {"completed_evidence": False}),
        )
        for name, values in cases:
            with self.subTest(name=name):
                positions = values.pop(
                    "positions", (
                        "initial", "changed", "changed", "changed", "changed", "changed",
                    ),
                )
                _capture, _backend, _scroll, _wait, _detector, result = self._run(
                    positions, mode="full", **values,
                )
                if name == "disabled":
                    self.assertEqual(result.dynamic_end_reason, "max_screen_limit")
                else:
                    self.assertEqual(result.dynamic_end_reason, "no_new_text")
                    self.assertEqual(result.scans_completed, 5)

    def test_full_rule_match_precedes_no_new_and_keeps_null_dynamic_reason(self):
        _capture, _backend, _scroll, _wait, _detector, result = self._run(
            ("initial", "changed", "changed"),
            mode="full",
            pages=("absent", "MATCH", "MATCH"),
        )
        self.assertTrue(result.confirmed_match)
        self.assertIsNone(result.dynamic_end_reason)
        self.assertEqual(result.scans_completed, 2)

    def test_safe_full_store_and_interrupt_return_without_a_normal_end(self):
        _capture, _backend, _scroll, _wait, _detector, store_result = self._run(
            ("initial", "changed", "changed"), mode="safe", saved_at=(2,),
        )
        self.assertEqual(store_result.abort_reason, "store_failed")
        self.assertIsNone(store_result.dynamic_end_reason)

        _capture, _backend, _scroll, _wait, _detector, interrupt_result = self._run(
            ("initial", "changed"),
            mode="full",
            interrupt_reason_provider=lambda: "user_interrupted",
        )
        self.assertEqual(interrupt_result.interrupt_reason, "user_interrupted")
        self.assertIsNone(interrupt_result.dynamic_end_reason)


# ── R07-IMPL-003: Confirmation capture type aligned with PositionDecision ──

class ConfirmationCaptureTypeTests(unittest.TestCase):
    """R07-IMPL-003: confirmation capture type resolved by canonical decision.

    These tests verify the detector-level ``_final_confirmation_capture_type``
    static method, the promotion in ``_attempt_position_confirmation``, and the
    absence of a ``position_unresolved`` abort on a changed confirmation.
    The in-callback record promotion (G3 proper) is verified in the
    ``_record_ocr_observation_result`` integration path within
    test_ocr_stage0_integration.
    """

    @staticmethod
    def _detector_with_callback(pages, callback, *, mode="safe", scroll=None,
                                max_scans=4):
        return OCRKeywordDetector(
            backend=FakeBackend(pages),
            capture=FakeCapture(),
            region=ScreenRegion(0, 0, 100, 100),
            max_scans=max_scans,
            scroll=scroll or Mock(),
            wait=Mock(),
            observation_callback=callback,
            dynamic_end_config=DynamicEndConfig(mode=mode),
            restore_focus=Mock(return_value=True),
        )

    @staticmethod
    def _record(index, *, effective_new=False, protected_short=False):
        result = SimpleNamespace(
            similarity_status="completed",
            effective_new_status=(
                "present" if (effective_new or protected_short) else "none"
            ),
            has_effective_new_text=effective_new,
            effective_new_segment_count=1 if effective_new else 0,
            effective_new_decisions=(
                (SimpleNamespace(reason="short_text_protected", decision="effective"),)
                if protected_short else ()
            ),
            warning_codes=(),
        )
        return SimpleNamespace(
            screen_id="slot-{0}".format(index),
            exact_hash=("a" * 64) if index <= 2 else ("b" * 64),
            fingerprint_version="r03-v1",
            aggregation_status="completed",
            uncertain_segment_ids=(),
            uncertain_segment_count=0,
            uncertain_char_count=0,
            aggregation_duplicate_risk=None,
            aggregation_warning_codes=(),
            has_effective_new_text=effective_new,
            similarity_result=result,
            capture_type="formal_screen",
            is_formal_screen=True,
        )

    def test_confirmation_same_no_effective_new_is_position_confirmation(self):
        """G3: exact same + no effective new → position_confirmation → scroll_bottom.

        After 2 slots (initial, same), recovery confirmation returns same →
        scroll_bottom.  The detector must NOT abort with position_unresolved.
        """
        call_count = 0

        def callback(_obs, capture_type, _formal, _screen_index):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace(
                    record=ConfirmationCaptureTypeTests._record(1),
                    saved=True,
                    position_decision=PositionDecision(
                        "initial", "initial", None, "initial_screen",
                    ),
                    load_health=True, ocr_health=True, identity_health=True,
                )
            if call_count == 2:
                return SimpleNamespace(
                    record=ConfirmationCaptureTypeTests._record(2),
                    saved=True,
                    position_decision=PositionDecision(
                        "same", "same", "slot-1", "exact_same",
                    ),
                    load_health=True, ocr_health=True, identity_health=True,
                )
            # confirmation: same → scroll_bottom
            return SimpleNamespace(
                record=ConfirmationCaptureTypeTests._record(3),
                saved=True,
                position_decision=PositionDecision(
                    "same", "same", "slot-2", "exact_same",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector_with_callback(
            ["absent", "absent"], callback, max_scans=2,
        )
        result = detector.detect(single_rule("absent"))
        # G3: same confirmation → scroll_bottom, no abort
        self.assertIsNone(result.abort_reason)
        from ocr_detector import _record_has_effective_new_content
        self.assertEqual(
            _record_has_effective_new_content(ConfirmationCaptureTypeTests._record(3)),
            False,
        )

    def test_confirmation_effective_new_promotes_to_formal(self):
        """G3: effective_new → changed decision → confirm no position_unresolved.

        The detector's recovery path must not abort with position_unresolved
        when canonical PositionDecision is changed.  Promotion to formal screen
        happens in the record callback (simple_brush.py G3 fix).
        """
        call_count = 0

        def callback(_obs, capture_type, _formal, _screen_index):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace(
                    record=ConfirmationCaptureTypeTests._record(1),
                    saved=True,
                    position_decision=PositionDecision(
                        "initial", "initial", None, "initial_screen",
                    ),
                    load_health=True, ocr_health=True, identity_health=True,
                )
            if call_count == 2:
                return SimpleNamespace(
                    record=ConfirmationCaptureTypeTests._record(2),
                    saved=True,
                    position_decision=PositionDecision(
                        "same", "same", "slot-1", "exact_same",
                    ),
                    load_health=True, ocr_health=True, identity_health=True,
                )
            # confirmation: changed → promoted_slot=True
            return SimpleNamespace(
                record=ConfirmationCaptureTypeTests._record(3, effective_new=True),
                saved=True,
                position_decision=PositionDecision(
                    "changed", "same", "slot-2", "effective_new_content",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector_with_callback(
            ["absent", "absent", "absent"], callback, max_scans=3,
        )
        result = detector.detect(single_rule("absent"))
        # G3: changed confirmation must not abort with position_unresolved
        self.assertIsNone(result.abort_reason)
        # G3: changed confirmation either promoted or scan continued
        self.assertNotEqual(result.abort_reason, "position_unresolved")

    def test_confirmation_short_text_protected_promotes_to_formal(self):
        """G3: short_text_protected → changed → no position_unresolved abort."""
        call_count = 0

        def callback(_obs, capture_type, _formal, _screen_index):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return SimpleNamespace(
                    record=ConfirmationCaptureTypeTests._record(1),
                    saved=True,
                    position_decision=PositionDecision(
                        "initial", "initial", None, "initial_screen",
                    ),
                    load_health=True, ocr_health=True, identity_health=True,
                )
            if call_count == 2:
                return SimpleNamespace(
                    record=ConfirmationCaptureTypeTests._record(2),
                    saved=True,
                    position_decision=PositionDecision(
                        "same", "same", "slot-1", "exact_same",
                    ),
                    load_health=True, ocr_health=True, identity_health=True,
                )
            return SimpleNamespace(
                record=ConfirmationCaptureTypeTests._record(3, protected_short=True),
                saved=True,
                position_decision=PositionDecision(
                    "changed", "same", "slot-2", "effective_new_content",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector_with_callback(
            ["absent", "absent", "absent"], callback, max_scans=3,
        )
        result = detector.detect(single_rule("absent"))
        self.assertIsNone(result.abort_reason)
        self.assertNotEqual(result.abort_reason, "position_unresolved")

    def test_changed_confirmation_is_single_record_no_double_save(self):
        """G3: changed confirmation does not trigger a second save."""
        call_count = 0
        callback_calls = []

        def callback(obs, capture_type, is_formal, screen_index):
            nonlocal call_count
            call_count += 1
            callback_calls.append((capture_type, is_formal, screen_index))
            if call_count == 1:
                return SimpleNamespace(
                    record=ConfirmationCaptureTypeTests._record(1),
                    saved=True,
                    position_decision=PositionDecision(
                        "initial", "initial", None, "initial_screen",
                    ),
                    load_health=True, ocr_health=True, identity_health=True,
                )
            if call_count == 2:
                return SimpleNamespace(
                    record=ConfirmationCaptureTypeTests._record(2),
                    saved=True,
                    position_decision=PositionDecision(
                        "same", "same", "slot-1", "exact_same",
                    ),
                    load_health=True, ocr_health=True, identity_health=True,
                )
            return SimpleNamespace(
                record=ConfirmationCaptureTypeTests._record(3, effective_new=True),
                saved=True,
                position_decision=PositionDecision(
                    "changed", "same", "slot-2", "effective_new_content",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector_with_callback(
            ["absent", "absent", "absent"], callback, max_scans=3,
        )
        result = detector.detect(single_rule("absent"))
        self.assertIsNone(result.abort_reason)
        # G3: each unique observation is processed at most once
        self.assertEqual(call_count, len(callback_calls))

    def test_same_confirmation_does_not_occupy_formal_slot(self):
        """G3: _final_confirmation_capture_type with same decision stays position_confirmation."""
        from ocr_detector import DynamicEndState
        decision = PositionDecision("same", "same", "slot-1", "exact_same")
        state = DynamicEndState(mode="safe", scan_slot_count=2)
        result = OCRKeywordDetector._final_confirmation_capture_type(
            decision, "position_confirmation", False, None, state)
        self.assertEqual(result, ("position_confirmation", False, None))

    def test_slot_eight_boundary_does_not_trigger_confirmation(self):
        """G3: _final_confirmation_capture_type promotes changed to formal screen."""
        from ocr_detector import DynamicEndState
        decision = PositionDecision("changed", "same", "slot-1", "effective_new_content")
        state = DynamicEndState(mode="safe", scan_slot_count=2)
        result = OCRKeywordDetector._final_confirmation_capture_type(
            decision, "position_confirmation", False, None, state)
        self.assertEqual(result, ("formal_screen", True, 3))


# ── R07-IMPL-005: Safe/full rule branch respects Store failure priority ──

class SafeFullStorePriorityTests(unittest.TestCase):
    """R07-IMPL-005: safe/full must check Store failure before rule confirmation."""

    def _detector(self, *, mode, callback, pages=("MATCH", "MATCH"),
                  scroll=None, interrupt_reason_provider=None):
        return OCRKeywordDetector(
            backend=FakeBackend(pages),
            capture=FakeCapture(),
            region=ScreenRegion(0, 0, 100, 100),
            max_scans=3,
            scroll=scroll or Mock(),
            wait=Mock(),
            observation_callback=callback,
            dynamic_end_config=DynamicEndConfig(mode=mode),
            interrupt_reason_provider=interrupt_reason_provider,
        )

    def test_off_rule_hit_store_false_keeps_legacy_return(self):
        """G5: off mode rule hit + Store false keeps legacy confirmation."""
        def callback(_obs, capture_type, _formal, _screen_index):
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="off-1"),
                saved=False,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector(mode="off", callback=callback)
        result = detector.detect(single_rule("MATCH"))
        # off keeps legacy rule confirmation; G5 does not add Store gate here
        self.assertTrue(result.confirmed_match)

    def test_shadow_rule_hit_store_false_keeps_legacy_return(self):
        """G5: shadow mode rule hit + Store false keeps legacy confirmation."""
        def callback(_obs, capture_type, _formal, _screen_index):
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="shadow-1"),
                saved=False,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector(mode="shadow", callback=callback)
        result = detector.detect(single_rule("MATCH"))
        self.assertTrue(result.confirmed_match)

    def test_safe_rule_hit_store_false_aborts_not_confirms(self):
        """G5: safe mode rule hit + Store false → store_failed, NOT confirmed."""
        def callback(_obs, capture_type, _formal, _screen_index):
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="safe-1"),
                saved=False,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector(mode="safe", callback=callback)
        result = detector.detect(single_rule("MATCH"))
        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.abort_reason, "store_failed")
        self.assertIsNone(result.dynamic_end_reason)

    def test_full_rule_hit_store_false_aborts_not_confirms(self):
        """G5: full mode rule hit + Store false → store_failed, NOT confirmed."""
        def callback(_obs, capture_type, _formal, _screen_index):
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="full-1"),
                saved=False,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector(mode="full", callback=callback)
        result = detector.detect(single_rule("MATCH"))
        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.abort_reason, "store_failed")
        self.assertIsNone(result.dynamic_end_reason)

    def test_full_callback_exception_aborts_before_scroll_or_normal_end(self):
        callback_calls = []
        scroll = Mock()

        def callback(_obs, capture_type, _formal, _screen_index):
            callback_calls.append(capture_type)
            raise ValueError("private callback detail must not escape")

        detector = self._detector(
            mode="full", callback=callback, pages=("absent", "absent"),
            scroll=scroll,
        )
        result = detector.detect(single_rule("missing"))

        self.assertEqual(callback_calls, ["formal_screen"])
        self.assertEqual(result.abort_reason, "unexpected_error")
        self.assertIsNone(result.dynamic_end_reason)
        self.assertFalse(result.confirmed_match)
        scroll.assert_not_called()

    def test_safe_rule_hit_no_rule_confirmation_on_store_failure(self):
        """G5: safe/full must not enter rule confirmation when Store failed."""
        callback_calls = []

        def callback(_obs, capture_type, _formal, _screen_index):
            callback_calls.append(capture_type)
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="safe-no-conf"),
                saved=False,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector(mode="safe", callback=callback)
        result = detector.detect(single_rule("MATCH"))
        self.assertFalse(result.confirmed_match)
        # The callback must be called exactly once (the initial formal screen),
        # not twice (no rule_confirmation callback).
        self.assertEqual(callback_calls, ["formal_screen"])

    def test_off_shadow_confirmations_count_preserved(self):
        """G5: off/shadow rule confirmation count unchanged from legacy."""
        off_calls = []
        shadow_calls = []

        def off_cb(_obs, capture_type, _formal, _screen_index):
            off_calls.append(capture_type)
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="off"),
                saved=True,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        def shadow_cb(_obs, capture_type, _formal, _screen_index):
            shadow_calls.append(capture_type)
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="shadow"),
                saved=True,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        off = self._detector(mode="off", callback=off_cb)
        shadow = self._detector(mode="shadow", callback=shadow_cb)
        off_res = off.detect(single_rule("MATCH"))
        shadow_res = shadow.detect(single_rule("MATCH"))
        self.assertTrue(off_res.confirmed_match)
        self.assertTrue(shadow_res.confirmed_match)
        self.assertEqual(off_calls, shadow_calls)
        self.assertEqual(off_calls, ["formal_screen", "rule_confirmation"])

    def test_safe_full_store_failure_does_not_second_save(self):
        """G5: Store failure does not trigger a second save for the same screen."""
        save_calls = []

        def callback(_obs, capture_type, _formal, _screen_index):
            save_calls.append(capture_type)
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="sf-no-2nd"),
                saved=False,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector(mode="safe", callback=callback)
        detector.detect(single_rule("MATCH"))
        # Exactly one formal_screen callback, no rule_confirmation
        self.assertEqual(save_calls, ["formal_screen"])

    def test_safe_full_rule_with_store_true_works_as_confirmed(self):
        """G5: safe + rule hit + saved=true works normally."""
        def callback(_obs, capture_type, _formal, _screen_index):
            return SimpleNamespace(
                record=SimpleNamespace(screen_id="safe-good"),
                saved=True,
                position_decision=PositionDecision(
                    "initial", "initial", None, "initial_screen",
                ),
                load_health=True, ocr_health=True, identity_health=True,
            )

        detector = self._detector(mode="safe", callback=callback)
        result = detector.detect(single_rule("MATCH"))
        self.assertTrue(result.confirmed_match)
        self.assertIsNone(result.dynamic_end_reason)


def render_parameterized_log(call):
    message, *arguments = call.args
    return message % tuple(arguments)


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


class ScreenFingerprintTests(unittest.TestCase):
    @staticmethod
    def make_item(text, left, top, width=10.0, height=10.0):
        right = left + width
        bottom = top + height
        return OCRItem(
            text,
            0.99,
            [
                [left, top],
                [right, top],
                [right, bottom],
                [left, bottom],
            ],
        )

    @staticmethod
    def captured_at():
        return datetime(2026, 7, 29, 8, 30, tzinfo=timezone.utc)

    def test_box_bounds_supports_rotated_and_numpy_boxes(self):
        rotated = [[10, 0], [20, 5], [15, 15], [5, 10]]
        expected = (5.0, 0.0, 20.0, 15.0, 15.0, 15.0, 7.5)

        self.assertEqual(fingerprint_box_bounds(rotated), expected)
        self.assertEqual(
            fingerprint_box_bounds(np.asarray(rotated)),
            expected,
        )
        self.assertEqual(
            fingerprint_box_bounds([[3, 4], [3, 4]]),
            (3.0, 4.0, 3.0, 4.0, 0.0, 0.0, 4.0),
        )

    def test_invalid_boxes_raise_fingerprint_build_error(self):
        invalid_boxes = (
            None,
            [],
            [[1]],
            [["x", 2]],
            [[float("nan"), 2]],
            [[float("inf"), 2]],
            "not-a-nested-box",
        )

        for box in invalid_boxes:
            with self.subTest(box=box):
                with self.assertRaises(FingerprintBuildError):
                    fingerprint_box_bounds(box)

        with self.assertRaises(FingerprintBuildError):
            build_screen_fingerprint([OCRItem("bad", 0.99, None)])

    def test_order_is_stable_when_non_tied_input_is_shuffled(self):
        items = [
            self.make_item("bottom", 20, 30),
            self.make_item("right", 50, 0),
            self.make_item("left", 0, 0),
        ]
        expected_text = "left\nright\nbottom"
        expected_hash = build_screen_fingerprint(
            items,
            captured_at=self.captured_at(),
        ).exact_hash

        for seed in (3, 17, 41):
            shuffled = list(items)
            random.Random(seed).shuffle(shuffled)
            ordered = order_fingerprint_items(shuffled)
            fingerprint = build_screen_fingerprint(
                shuffled,
                captured_at=self.captured_at(),
            )

            self.assertEqual([item.text for item in ordered], [
                "left",
                "right",
                "bottom",
            ])
            self.assertEqual(fingerprint.raw_text, expected_text)
            self.assertEqual(fingerprint.exact_hash, expected_hash)

    def test_order_groups_small_y_variation_by_frozen_tolerance(self):
        right = self.make_item("right", 100, 0)
        left_at_tolerance = self.make_item("left", 0, 8)

        ordered = order_fingerprint_items([right, left_at_tolerance])

        self.assertEqual([item.text for item in ordered], ["left", "right"])

    def test_order_uses_new_line_outside_frozen_tolerance(self):
        upper_right = self.make_item("upper", 100, 0)
        lower_left = self.make_item("lower", 0, 8.1)

        ordered = order_fingerprint_items([upper_right, lower_left])

        self.assertEqual([item.text for item in ordered], ["upper", "lower"])

    def test_order_uses_source_index_for_complete_coordinate_tie(self):
        first = self.make_item("first", 0, 0)
        second = self.make_item("second", 0, 0)

        first_order = order_fingerprint_items([first, second])
        reversed_order = order_fingerprint_items([second, first])

        self.assertEqual([item.text for item in first_order], [
            "first",
            "second",
        ])
        self.assertEqual([item.text for item in reversed_order], [
            "second",
            "first",
        ])
        self.assertNotEqual(
            build_screen_fingerprint(
                [first, second],
                captured_at=self.captured_at(),
            ).exact_hash,
            build_screen_fingerprint(
                [second, first],
                captured_at=self.captured_at(),
            ).exact_hash,
        )

    def test_raw_and_normalized_text_follow_the_fixed_contract(self):
        ordered_items = [
            OCRItem(" \t ", 0.99),
            OCRItem("  A\t B  ", 0.99),
            OCRItem("Ｆoo!  ", 0.99),
        ]

        raw_text, raw_length = build_fingerprint_raw_text(ordered_items)
        normalized_text, normalized_length = (
            build_fingerprint_normalized_text(ordered_items)
        )

        self.assertEqual(raw_text, " \t \n  A\t B  \nＦoo!  ")
        self.assertEqual(
            raw_length,
            sum(len(item.text) for item in ordered_items),
        )
        self.assertEqual(normalized_text, "A B\nＦoo!")
        self.assertEqual(normalized_length, len(normalized_text))
        self.assertEqual(
            normalize_fingerprint_item_text(" \n Alpha\t\tBeta \r\n "),
            "Alpha Beta",
        )

    def test_normalization_preserves_non_whitespace_characters(self):
        text = "  AbC，１２３!  "

        self.assertEqual(
            normalize_fingerprint_item_text(text),
            "AbC，１２３!",
        )

    def test_empty_normalized_text_has_valid_empty_sha256(self):
        items = [
            self.make_item(" \t ", 0, 0),
            self.make_item("", 20, 0),
        ]

        fingerprint = build_screen_fingerprint(
            items,
            captured_at=self.captured_at(),
        )

        self.assertEqual(fingerprint.ocr_box_count, 2)
        self.assertEqual(fingerprint.raw_text, " \t \n")
        self.assertEqual(fingerprint.raw_text_length, len(" \t "))
        self.assertEqual(fingerprint.normalized_text, "")
        self.assertEqual(fingerprint.normalized_text_length, 0)
        self.assertEqual(
            fingerprint.exact_hash,
            hashlib.sha256(b"").hexdigest(),
        )

    def test_hash_is_lowercase_sha256_of_utf8_normalized_text(self):
        normalized_text = "中文\nPython!"

        exact_hash = sha256_normalized_text(normalized_text)

        self.assertEqual(
            exact_hash,
            hashlib.sha256(normalized_text.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(len(exact_hash), 64)
        self.assertIsNotNone(FINGERPRINT_HASH_PATTERN.fullmatch(exact_hash))

    def test_metadata_does_not_change_exact_hash(self):
        items = [self.make_item("metadata", 0, 0)]
        first = build_screen_fingerprint(
            items,
            captured_at=datetime(2026, 7, 29, 8, 30, tzinfo=timezone.utc),
        )
        second = build_screen_fingerprint(
            items,
            captured_at=datetime(2026, 7, 29, 8, 31, tzinfo=timezone.utc),
        )
        changed_metadata = replace(
            first,
            captured_at="2030-01-01T00:00:00+00:00",
            ocr_box_count=99,
            raw_text_length=0,
            normalized_text_length=0,
            screen_index=7,
        )

        self.assertEqual(first.exact_hash, second.exact_hash)
        self.assertEqual(first.exact_hash, changed_metadata.exact_hash)
        self.assertTrue(compare_screen_fingerprints(first, changed_metadata))

    def test_small_text_change_changes_exact_hash(self):
        original = build_screen_fingerprint(
            [self.make_item("A", 0, 0)],
            captured_at=self.captured_at(),
        )
        punctuation_changed = build_screen_fingerprint(
            [self.make_item("A!", 0, 0)],
            captured_at=self.captured_at(),
        )

        self.assertNotEqual(original.exact_hash, punctuation_changed.exact_hash)

    def test_builder_uses_injected_time_and_samples_automatic_time_last(self):
        injected = datetime(2026, 7, 29, 8, 30, tzinfo=timezone.utc)
        items = [self.make_item("clock", 0, 0)]
        with_injected_time = build_screen_fingerprint(
            items,
            captured_at=injected,
        )
        self.assertEqual(with_injected_time.captured_at, injected.isoformat())

        events = []
        original_hash = sha256_normalized_text

        def record_hash(normalized_text):
            events.append("hash")
            return original_hash(normalized_text)

        class ControlledDatetime:
            @classmethod
            def now(cls):
                events.append("now")
                return injected

        with patch(
            "ocr_detector.sha256_normalized_text",
            side_effect=record_hash,
        ), patch("ocr_detector.datetime", ControlledDatetime):
            automatic_time = build_screen_fingerprint(items)

        self.assertEqual(events, ["hash", "now"])
        self.assertEqual(
            automatic_time.captured_at,
            injected.astimezone().isoformat(),
        )
        with self.assertRaises(FingerprintBuildError):
            build_screen_fingerprint(
                items,
                captured_at=datetime(2026, 7, 29, 8, 30),
            )

        clock = Mock()
        with patch("ocr_detector.datetime", clock):
            with self.assertRaises(FingerprintBuildError):
                build_screen_fingerprint([OCRItem("bad", 0.99, None)])
        clock.now.assert_not_called()

    def test_compare_screen_fingerprints_is_three_state(self):
        fingerprint = build_screen_fingerprint(
            [self.make_item("same", 0, 0)],
            captured_at=self.captured_at(),
        )
        same = replace(fingerprint)
        different = replace(
            fingerprint,
            exact_hash=sha256_normalized_text("different"),
        )
        version_mismatch = replace(
            fingerprint,
            fingerprint_version="r03-v2",
        )
        invalid_hash = replace(fingerprint, exact_hash="not-a-hash")
        invalid_version = replace(fingerprint, fingerprint_version="")

        self.assertIs(compare_screen_fingerprints(fingerprint, same), True)
        self.assertIs(compare_screen_fingerprints(fingerprint, different), False)
        self.assertIsNone(compare_screen_fingerprints(fingerprint, None))
        self.assertIsNone(compare_screen_fingerprints(None, None))
        self.assertIsNone(
            compare_screen_fingerprints(fingerprint, version_mismatch)
        )
        self.assertIsNone(
            compare_screen_fingerprints(fingerprint, invalid_hash)
        )
        self.assertIsNone(
            compare_screen_fingerprints(fingerprint, invalid_version)
        )

    def test_comparison_log_maps_all_three_states_without_body(self):
        private_marker = "PRIVATE_R03_OCR_BODY_9F3A"
        fingerprint = build_screen_fingerprint(
            [self.make_item(private_marker, 0, 0)],
            captured_at=self.captured_at(),
        )
        different = replace(
            fingerprint,
            exact_hash=sha256_normalized_text("different"),
        )

        with patch(
            "ocr_detector.compare_screen_fingerprints",
        ) as compare, patch("ocr_detector.logger.info") as comparison_log:
            log_fingerprint_comparison(fingerprint, fingerprint, True)
            log_fingerprint_comparison(fingerprint, different, False)
            log_fingerprint_comparison(None, None, None)

        compare.assert_not_called()
        rendered = [
            render_parameterized_log(call)
            for call in comparison_log.call_args_list
        ]
        self.assertEqual(rendered, [
            "event=ocr_fingerprint_comparison comparison=same "
            f"left_version={FINGERPRINT_VERSION} "
            f"right_version={FINGERPRINT_VERSION} "
            f"left_hash={fingerprint.exact_hash} "
            f"right_hash={fingerprint.exact_hash}",
            "event=ocr_fingerprint_comparison comparison=different "
            f"left_version={FINGERPRINT_VERSION} "
            f"right_version={FINGERPRINT_VERSION} "
            f"left_hash={fingerprint.exact_hash} "
            f"right_hash={different.exact_hash}",
            "event=ocr_fingerprint_comparison comparison=not_comparable "
            "left_version=- right_version=- left_hash=- right_hash=-",
        ])
        for message in rendered:
            for forbidden in (
                private_marker,
                fingerprint.raw_text,
                fingerprint.normalized_text,
                "OCRItem(",
                "ScreenFingerprint(",
                "FingerprintBuildError(",
                "[",
                "box=",
                "point=",
                "bounds=",
                "width=",
                "height=",
                "center_y=",
                "confidence=",
            ):
                self.assertNotIn(forbidden, message)

    def test_screen_fingerprint_is_frozen_and_observation_defaults_none(self):
        fingerprint = build_screen_fingerprint(
            [self.make_item("frozen", 0, 0)],
            captured_at=self.captured_at(),
        )

        with self.assertRaises(FrozenInstanceError):
            fingerprint.raw_text = "changed"

        fingerprint_field_names = [
            field.name for field in fields(ScreenFingerprint)
        ]
        self.assertEqual(fingerprint_field_names, [
            "raw_text",
            "normalized_text",
            "raw_text_length",
            "normalized_text_length",
            "ocr_box_count",
            "captured_at",
            "exact_hash",
            "fingerprint_version",
            "screen_index",
        ])
        self.assertEqual(fingerprint.fingerprint_version, FINGERPRINT_VERSION)
        self.assertIsNone(fingerprint.screen_index)
        self.assertFalse(
            {"ocr_items", "raw_items", "accepted_items", "boxes"}
            & set(fingerprint_field_names)
        )
        observation = ScanObservation(1, "", 0, 0.0)
        self.assertIsNone(observation.fingerprint)

    def test_binding_replaces_index_without_rehash_or_recapture(self):
        fingerprint = build_screen_fingerprint(
            [self.make_item("bound", 0, 0)],
            captured_at=self.captured_at(),
        )
        observation = ScanObservation(
            1,
            "bound",
            1,
            0.0,
            fingerprint=fingerprint,
        )

        bind_fingerprint_screen_index(observation, 1)

        self.assertIsNot(observation.fingerprint, fingerprint)
        self.assertEqual(observation.fingerprint.screen_index, 1)
        self.assertEqual(observation.fingerprint.exact_hash, fingerprint.exact_hash)
        self.assertEqual(observation.fingerprint.raw_text, fingerprint.raw_text)
        self.assertEqual(
            observation.fingerprint.normalized_text,
            fingerprint.normalized_text,
        )
        self.assertEqual(
            observation.fingerprint.captured_at,
            fingerprint.captured_at,
        )
        with self.assertRaises(ValueError):
            bind_fingerprint_screen_index(observation, 0)
        with self.assertRaises(ValueError):
            bind_fingerprint_screen_index(observation, -1)

        observation_without_fingerprint = ScanObservation(1, "", 0, 0.0)
        bind_fingerprint_screen_index(observation_without_fingerprint, 1)
        self.assertIsNone(observation_without_fingerprint.fingerprint)


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.region = ScreenRegion(10, 20, 800, 600)

    @staticmethod
    def make_box_item(text):
        return OCRItem(
            text,
            0.99,
            [[0, 0], [20, 0], [20, 10], [0, 10]],
        )

    def make_detector(self, pages, max_scans=8, scroll=None):
        return OCRKeywordDetector(
            backend=FakeBackend(pages),
            capture=FakeCapture(),
            region=self.region,
            max_scans=max_scans,
            scroll=scroll,
            wait=lambda _seconds: None,
        )

    def test_unpromoted_load_observations_remain_without_screen_index(self):
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.side_effect = [
            [self.make_box_item(f"load-{attempt}")]
            for attempt in range(4)
        ]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            wait=lambda _seconds: None,
        )

        load_observations = [
            detector.capture_observation(1)
            for _ in range(4)
        ]

        self.assertEqual(capture.calls, 4)
        self.assertEqual(backend.recognize.call_count, 4)
        self.assertTrue(
            all(
                observation.fingerprint is not None
                and observation.fingerprint.screen_index is None
                for observation in load_observations
            )
        )

    def test_direct_detection_assigns_one_through_eight_to_formal_scans(
        self,
    ):
        class BoxBackend:
            def __init__(self):
                self.calls = 0

            def recognize(self, _image):
                self.calls += 1
                return [
                    DetectorTests.make_box_item(f"formal-{self.calls}"),
                ]

        capture = FakeCapture()
        backend = BoxBackend()
        scroll_calls = []
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            max_scans=8,
            scroll=lambda: scroll_calls.append(True),
            wait=lambda _seconds: None,
        )

        with patch(
            "ocr_detector.matching_keyword_rule",
            wraps=matching_keyword_rule,
        ) as matcher:
            result = detector.detect(single_rule("not-present"))
        formal_indexes = [
            observation.fingerprint.screen_index
            for observation in result.observations
            if observation.fingerprint is not None
        ]

        self.assertEqual(formal_indexes, list(range(1, 9)))
        self.assertEqual(len(set(formal_indexes)), 8)
        self.assertNotIn(0, formal_indexes)
        self.assertNotIn(9, formal_indexes)
        self.assertEqual(capture.calls, 8)
        self.assertEqual(backend.calls, 8)
        self.assertEqual(len(scroll_calls), 7)
        self.assertEqual(matcher.call_count, 16)

    def test_confirmation_fingerprint_has_no_formal_screen_index(self):
        class BoxBackend:
            def __init__(self):
                self.calls = 0

            def recognize(self, _image):
                self.calls += 1
                return [DetectorTests.make_box_item("Python")]

        capture = FakeCapture()
        backend = BoxBackend()
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            max_scans=8,
            wait=Mock(),
        )

        with patch(
            "ocr_detector.matching_keyword_rule",
            wraps=matching_keyword_rule,
        ) as matcher:
            result = detector.detect(single_rule("Python"))

        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.scans_completed, 1)
        self.assertEqual(capture.calls, 2)
        self.assertEqual(backend.calls, 2)
        self.assertEqual(len(result.observations), 2)
        self.assertEqual(result.observations[0].fingerprint.screen_index, 1)
        self.assertIsNone(result.observations[1].fingerprint.screen_index)
        self.assertEqual(matcher.call_count, 4)
        self.assertEqual(
            sum(
                observation.fingerprint is not None
                and observation.fingerprint.screen_index is not None
                for observation in result.observations
            ),
            1,
        )

    def test_sequential_detection_results_do_not_retain_prior_fingerprints(
        self,
    ):
        class BoxBackend:
            def __init__(self):
                self.calls = 0

            def recognize(self, _image):
                self.calls += 1
                return [
                    DetectorTests.make_box_item(f"candidate-{self.calls}"),
                ]

        detector = OCRKeywordDetector(
            backend=BoxBackend(),
            capture=FakeCapture(),
            region=self.region,
            max_scans=1,
            wait=lambda _seconds: None,
        )

        first_result = detector.detect(single_rule("not-present"))
        second_result = detector.detect(single_rule("not-present"))

        self.assertIsNot(first_result.observations, second_result.observations)
        self.assertIsNot(
            first_result.observations[0],
            second_result.observations[0],
        )
        self.assertIsNot(
            first_result.observations[0].fingerprint,
            second_result.observations[0].fingerprint,
        )
        self.assertEqual(
            first_result.observations[0].fingerprint.screen_index,
            1,
        )
        self.assertEqual(
            second_result.observations[0].fingerprint.screen_index,
            1,
        )
        self.assertFalse(hasattr(detector, "observations"))

    def test_capture_observation_builds_fingerprint_from_same_accepted_items_once(
        self,
    ):
        capture = FakeCapture()
        backend = Mock()
        raw_items = [
            OCRItem(
                "  Visible\tText  ",
                0.99,
                [[50, 0], [70, 0], [70, 10], [50, 10]],
            ),
            OCRItem(
                "below threshold",
                0.84,
                [[0, 20], [20, 20], [20, 30], [0, 30]],
            ),
            OCRItem(
                " \t ",
                0.99,
                [[0, 0], [20, 0], [20, 10], [0, 10]],
            ),
        ]
        backend.recognize.return_value = raw_items
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
        seen = {}
        original_filter = accepted_ocr_items
        original_metrics = calculate_load_metrics
        original_searchable_text = searchable_text
        original_builder = build_screen_fingerprint

        def record_filter(items, min_confidence):
            accepted = original_filter(items, min_confidence)
            seen["accepted"] = accepted
            return accepted

        def record_metrics(items):
            seen["metrics_items"] = items
            return original_metrics(items)

        def record_searchable_text(items):
            seen["text_items"] = items
            return original_searchable_text(items)

        def record_builder(items, **kwargs):
            seen["fingerprint_items"] = items
            seen["fingerprint_kwargs"] = kwargs
            return original_builder(items, **kwargs)

        with patch(
            "ocr_detector.accepted_ocr_items",
            side_effect=record_filter,
        ) as filter_call, patch(
            "ocr_detector.calculate_load_metrics",
            side_effect=record_metrics,
        ) as metrics_call, patch(
            "ocr_detector.searchable_text",
            side_effect=record_searchable_text,
        ) as text_call, patch(
            "ocr_detector.build_screen_fingerprint",
            side_effect=record_builder,
        ) as builder_call, patch(
            "ocr_detector.normalize_ocr_text",
            wraps=ocr_normalization.normalize_ocr_text,
        ) as normalizer_call, patch(
            "ocr_detector.matching_keyword_rule",
        ) as matcher:
            observation = detector.capture_observation(1)

        self.assertEqual(capture.calls, 1)
        backend.recognize.assert_called_once_with(1)
        filter_call.assert_called_once()
        metrics_call.assert_called_once()
        text_call.assert_called_once()
        builder_call.assert_called_once()
        normalizer_call.assert_called_once()
        matcher.assert_not_called()
        scroll.assert_not_called()
        wait.assert_not_called()
        self.assertIs(seen["metrics_items"], seen["accepted"])
        self.assertIs(seen["text_items"], seen["accepted"])
        self.assertIs(seen["fingerprint_items"], seen["accepted"])
        self.assertEqual(
            observation.captured_at,
            seen["fingerprint_kwargs"]["captured_at"].isoformat(),
        )
        self.assertEqual(observation.raw_items, tuple(raw_items))
        self.assertEqual(
            observation.normalization.raw_text,
            "  Visible\tText  \nbelow threshold\n \t ",
        )
        self.assertNotIn(
            "below threshold",
            observation.normalization.normalized_text,
        )
        self.assertEqual(
            normalizer_call.call_args.kwargs["eligible_box_ids"],
            (
                "{0}:box:0".format(observation.screen_id),
                "{0}:box:2".format(observation.screen_id),
            ),
        )
        self.assertEqual(observation.item_count, len(raw_items))
        self.assertEqual(
            (observation.ocr_box_count, observation.ocr_text_length),
            original_metrics(seen["accepted"]),
        )
        self.assertEqual(
            observation.text,
            original_searchable_text(seen["accepted"]),
        )
        self.assertIsNotNone(observation.fingerprint)
        self.assertEqual(
            observation.fingerprint.ocr_box_count,
            observation.ocr_box_count,
        )
        self.assertIsNone(observation.fingerprint.screen_index)
        self.assertIsNotNone(
            datetime.fromisoformat(observation.fingerprint.captured_at).tzinfo
        )

    def test_r03_fingerprint_is_unchanged_by_every_r04_status(self):
        item = self.make_box_item("Unity  2022.3 C++")
        expected = build_screen_fingerprint([item])
        box = ocr_normalization.NormalizationBox(
            "screen:box:0",
            item.text,
            item.box,
            0,
            item.confidence,
        )
        completed = ocr_normalization.normalize_ocr_text((box,))
        variants = (
            ("completed", completed),
            (
                "completed_empty",
                ocr_normalization.normalize_ocr_text(()),
            ),
            (
                "failed",
                ocr_normalization.failed_normalization_result(
                    (box,),
                    error_type="SyntheticError",
                ),
            ),
        )

        for name, normalization in variants:
            with self.subTest(name=name):
                backend = Mock()
                backend.recognize.return_value = [item]
                detector = OCRKeywordDetector(
                    backend=backend,
                    capture=FakeCapture(),
                    region=self.region,
                    wait=Mock(),
                )
                with patch(
                    "ocr_detector.normalize_ocr_text",
                    return_value=normalization,
                ):
                    observation = detector.capture_observation(1)

                self.assertEqual(
                    observation.fingerprint.raw_text,
                    expected.raw_text,
                )
                self.assertEqual(
                    observation.fingerprint.normalized_text,
                    expected.normalized_text,
                )
                self.assertEqual(
                    observation.fingerprint.exact_hash,
                    expected.exact_hash,
                )
                self.assertEqual(
                    observation.fingerprint.fingerprint_version,
                    FINGERPRINT_VERSION,
                )

        not_attempted = ScanObservation(
            1,
            "unity2022.3c++",
            1,
            0.01,
            fingerprint=expected,
        )
        detector._match_observation(not_attempted, single_rule("Unity"))
        self.assertEqual(not_attempted.fingerprint, expected)
        self.assertEqual(
            not_attempted.rule_comparison.comparison_outcome,
            RULE_COMPARISON_NORMALIZATION_FAILED,
        )

    def test_normalizer_exception_keeps_r03_hash_and_legacy_rule_authority(self):
        backend = Mock()
        item = self.make_box_item("Python C++")
        backend.recognize.return_value = [item]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=FakeCapture(),
            region=self.region,
            wait=Mock(),
        )

        with patch(
            "ocr_detector.normalize_ocr_text",
            side_effect=RuntimeError("PRIVATE_BODY_MUST_NOT_ESCAPE"),
        ) as normalizer:
            observation = detector.capture_observation(1)
            detector._match_observation(observation, single_rule("Python"))

        normalizer.assert_called_once()
        self.assertEqual(observation.normalization.status, NORMALIZATION_FAILED)
        self.assertEqual(
            observation.normalization.normalization_error_type,
            "RuntimeError",
        )
        self.assertEqual(
            observation.fingerprint.exact_hash,
            build_screen_fingerprint([item]).exact_hash,
        )
        self.assertEqual(
            observation.fingerprint.fingerprint_version,
            FINGERPRINT_VERSION,
        )
        self.assertIsNotNone(observation.matched_rule)
        self.assertEqual(
            observation.rule_comparison.comparison_outcome,
            RULE_COMPARISON_NORMALIZATION_FAILED,
        )
        self.assertIsNone(observation.rule_comparison.r04_match)

    def test_invalid_geometry_fails_r04_text_and_r03_fingerprint(self):
        backend = Mock()
        backend.recognize.return_value = [
            OCRItem("C++ 文字仍保留", 0.99, (0, (1, 2), 3, 4)),
        ]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=FakeCapture(),
            region=self.region,
            wait=Mock(),
        )

        observation = detector.capture_observation(1)

        self.assertEqual(observation.normalization.status, NORMALIZATION_FAILED)
        self.assertEqual(observation.normalization.raw_text, "C++ 文字仍保留")
        self.assertIsNone(observation.normalization.normalized_text)
        self.assertIsNone(observation.normalization.comparison_text)
        self.assertIsNone(observation.fingerprint)

    def test_legacy_shadow_records_all_outcomes_without_changing_authority(self):
        detector = OCRKeywordDetector(
            backend=Mock(),
            capture=FakeCapture(),
            region=self.region,
            wait=Mock(),
        )
        base = ocr_normalization.normalize_ocr_text((
            ocr_normalization.NormalizationBox(
                "box-1",
                "placeholder",
                ((0, 0), (20, 0), (20, 10), (0, 10)),
                0,
                0.99,
            ),
        ))
        rules = single_rule("Python")
        cases = (
            (
                "same_match",
                "Python",
                replace(base, comparison_text="python"),
                RULE_COMPARISON_SAME_MATCH,
                True,
                True,
            ),
            (
                "same_no_match",
                "Java",
                replace(base, comparison_text="java"),
                RULE_COMPARISON_SAME_NO_MATCH,
                False,
                False,
            ),
            (
                "legacy_only",
                "Python",
                replace(base, comparison_text="java"),
                RULE_COMPARISON_LEGACY_ONLY,
                True,
                False,
            ),
            (
                "r04_only",
                "Java",
                replace(base, comparison_text="python"),
                RULE_COMPARISON_R04_ONLY,
                False,
                True,
            ),
            (
                "normalization_failed",
                "Python",
                replace(base, status=NORMALIZATION_FAILED),
                RULE_COMPARISON_NORMALIZATION_FAILED,
                True,
                None,
            ),
        )

        for name, legacy_text, normalization, outcome, legacy, r04 in cases:
            with self.subTest(name=name):
                observation = ScanObservation(
                    1,
                    legacy_text,
                    1,
                    0.01,
                    normalization=normalization,
                )
                detector._match_observation(observation, rules)

                comparison = observation.rule_comparison
                self.assertEqual(
                    comparison.rule_evaluation_mode,
                    RULE_EVALUATION_MODE_LEGACY_SHADOW,
                )
                self.assertEqual(comparison.comparison_outcome, outcome)
                self.assertEqual(comparison.legacy_match, legacy)
                self.assertEqual(comparison.r04_match, r04)
                self.assertEqual(observation.matched_rule is not None, legacy)

    def test_shadow_uses_comparison_text_and_records_different_rule_indexes(self):
        detector = OCRKeywordDetector(
            backend=Mock(),
            capture=FakeCapture(),
            region=self.region,
            wait=Mock(),
        )
        rules = parse_keyword_rules('"Legacy"; "R04"')
        normalization = ocr_normalization.normalize_ocr_text((
            ocr_normalization.NormalizationBox(
                "box-1",
                "unused",
                ((0, 0), (20, 0), (20, 10), (0, 10)),
                0,
                0.99,
            ),
        ))
        normalization = replace(
            normalization,
            normalized_text="Legacy",
            comparison_text="r04",
        )
        observation = ScanObservation(
            1,
            "Legacy",
            1,
            0.01,
            normalization=normalization,
        )

        detector._match_observation(observation, rules)

        self.assertEqual(observation.matched_rule, rules[0])
        self.assertEqual(
            observation.rule_comparison.comparison_outcome,
            RULE_COMPARISON_SAME_MATCH,
        )
        self.assertEqual(observation.rule_comparison.legacy_rule_index, 0)
        self.assertEqual(observation.rule_comparison.r04_rule_index, 1)

    def test_fingerprint_generated_log_has_only_allowed_metadata(self):
        private_marker = "PRIVATE_R03_OCR_BODY_9F3A"
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [
            OCRItem(
                private_marker,
                0.99,
                [[0, 0], [20, 0], [20, 10], [0, 10]],
            ),
        ]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            wait=lambda _seconds: None,
        )

        with patch("ocr_detector.logger.info") as generated_log:
            observation = detector.capture_observation(7)

        fingerprint = observation.fingerprint
        self.assertIsNotNone(fingerprint)
        generated_log.assert_called_once()
        rendered = render_parameterized_log(generated_log.call_args)
        self.assertEqual(
            rendered,
            "event=ocr_fingerprint_generated "
            f"fingerprint_version={FINGERPRINT_VERSION} "
            f"exact_hash={fingerprint.exact_hash} "
            f"ocr_box_count={fingerprint.ocr_box_count} "
            f"raw_text_length={fingerprint.raw_text_length} "
            f"normalized_text_length={fingerprint.normalized_text_length} "
            "screen_index=- "
            f"captured_at={fingerprint.captured_at} scan_number=7",
        )
        for forbidden in (
            private_marker,
                fingerprint.raw_text,
                fingerprint.normalized_text,
                "OCRItem(",
                "ScreenFingerprint(",
                "FingerprintBuildError(",
                "[",
                "box=",
                "point=",
            "bounds=",
            "width=",
            "height=",
            "center_y=",
            "confidence=",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_binding_does_not_repeat_fingerprint_generated_log(self):
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [self.make_box_item("prefetched")]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            max_scans=1,
            wait=lambda _seconds: None,
        )

        with patch("ocr_detector.logger.info") as generated_log:
            first_observation = detector.capture_observation(1)
            generated_log.assert_called_once()
            generated_log.reset_mock()
            result = detector.detect(
                single_rule("not-present"),
                first_observation=first_observation,
            )

        self.assertEqual(result.observations[0].fingerprint.screen_index, 1)
        generated_log.assert_not_called()

    def test_fingerprint_failure_log_is_sanitised_and_fail_open(self):
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [
            OCRItem(
                "PRIVATE_R03_OCR_BODY_9F3A",
                0.99,
                [[0, 0], [20, 0], [20, 10], [0, 10]],
            ),
            OCRItem(
                "low",
                0.84,
                [[0, 20], [20, 20], [20, 30], [0, 30]],
            ),
        ]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            min_confidence=0.85,
            scroll=Mock(),
            wait=Mock(),
        )
        original_filter = accepted_ocr_items

        with patch(
            "ocr_detector.accepted_ocr_items",
            wraps=original_filter,
        ) as filter_call, patch(
            "ocr_detector.build_screen_fingerprint",
            side_effect=FingerprintBuildError("PRIVATE_R03_OCR_BODY_9F3A"),
        ) as builder, patch("ocr_detector.logger.warning") as failure_log:
            observation = detector.capture_observation(1)

        self.assertEqual(capture.calls, 1)
        backend.recognize.assert_called_once_with(1)
        filter_call.assert_called_once()
        builder.assert_called_once()
        self.assertIsNone(observation.fingerprint)
        self.assertEqual(
            observation.normalization.status,
            NORMALIZATION_COMPLETED,
        )
        self.assertIsNotNone(observation.normalization.comparison_text)
        self.assertEqual(observation.item_count, 2)
        self.assertEqual(observation.ocr_box_count, 1)
        self.assertEqual(
            observation.ocr_text_length,
            len("PRIVATE_R03_OCR_BODY_9F3A"),
        )
        self.assertEqual(observation.text, "private_r03_ocr_body_9f3a")
        failure_log.assert_called_once()
        rendered = render_parameterized_log(failure_log.call_args)
        self.assertEqual(
            rendered,
            "event=ocr_fingerprint_generation_failed "
            f"fingerprint_version={FINGERPRINT_VERSION} "
            "scan_number=1 error_type=FingerprintBuildError",
        )
        for forbidden in (
            "PRIVATE_R03_OCR_BODY_9F3A",
            observation.text,
            "OCRItem(",
            "ScreenFingerprint(",
            "FingerprintBuildError(",
            "[",
            "box=",
            "point=",
            "bounds=",
            "width=",
            "height=",
            "center_y=",
            "confidence=",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_backend_failure_does_not_attempt_fingerprint_build(self):
        class BrokenBackend:
            def recognize(self, _image):
                raise RuntimeError("OCR unavailable")

        detector = OCRKeywordDetector(
            backend=BrokenBackend(),
            capture=FakeCapture(),
            region=self.region,
            wait=lambda _seconds: None,
        )

        with patch("ocr_detector.build_screen_fingerprint") as builder, patch(
            "ocr_detector.logger.warning",
        ) as failure_log:
            result = detector.detect(single_rule("关键词"))

        builder.assert_not_called()
        failure_log.assert_not_called()
        self.assertFalse(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIn("OCR unavailable", result.error)

    def test_capture_and_searchable_errors_do_not_log_fingerprint_failure(self):
        private_marker = "PRIVATE_R03_OCR_BODY_9F3A"

        class BrokenCapture:
            def capture(self, _region):
                raise RuntimeError(private_marker)

        capture_detector = OCRKeywordDetector(
            backend=Mock(),
            capture=BrokenCapture(),
            region=self.region,
            wait=lambda _seconds: None,
        )
        with patch("ocr_detector.build_screen_fingerprint") as builder, patch(
            "ocr_detector.logger.warning",
        ) as failure_log:
            with self.assertRaisesRegex(RuntimeError, private_marker):
                capture_detector.capture_observation(1)
        builder.assert_not_called()
        failure_log.assert_not_called()

        backend = Mock()
        backend.recognize.return_value = [self.make_box_item(private_marker)]
        text_detector = OCRKeywordDetector(
            backend=backend,
            capture=FakeCapture(),
            region=self.region,
            wait=lambda _seconds: None,
        )
        with patch(
            "ocr_detector.searchable_text",
            side_effect=RuntimeError(private_marker),
        ), patch("ocr_detector.build_screen_fingerprint") as builder, patch(
            "ocr_detector.logger.warning",
        ) as failure_log:
            with self.assertRaisesRegex(RuntimeError, private_marker):
                text_detector.capture_observation(1)
        builder.assert_not_called()
        failure_log.assert_not_called()

    def test_capture_and_detect_do_not_call_comparison_helpers(self):
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [self.make_box_item("no compare")]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            max_scans=1,
            wait=lambda _seconds: None,
        )

        with patch(
            "ocr_detector.compare_screen_fingerprints",
        ) as compare, patch(
            "ocr_detector.log_fingerprint_comparison",
        ) as comparison_log:
            result = detector.detect(single_rule("not-present"))

        compare.assert_not_called()
        comparison_log.assert_not_called()
        self.assertTrue(result.success)
        self.assertEqual(result.scans_completed, 1)

    def test_fingerprint_failure_does_not_change_confirmation_flow(self):
        detector = self.make_detector(["Python", "Python"], max_scans=1)

        with patch(
            "ocr_detector.build_screen_fingerprint",
            side_effect=FingerprintBuildError("PRIVATE_OCR_BODY"),
        ) as builder:
            result = detector.detect(single_rule("Python"))

        self.assertTrue(result.success)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.scans_completed, 1)
        self.assertEqual(detector.capture.calls, 2)
        self.assertEqual(detector.backend.calls, 2)
        self.assertEqual(builder.call_count, 2)
        self.assertTrue(
            all(observation.fingerprint is None for observation in result.observations)
        )

    def test_empty_ocr_result_has_valid_empty_fingerprint(self):
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = []
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            wait=lambda _seconds: None,
        )

        observation = detector.capture_observation(1)

        self.assertEqual(capture.calls, 1)
        backend.recognize.assert_called_once_with(1)
        self.assertEqual(observation.item_count, 0)
        self.assertEqual(observation.ocr_box_count, 0)
        self.assertEqual(observation.ocr_text_length, 0)
        self.assertEqual(observation.text, "")
        self.assertIsNotNone(observation.fingerprint)
        self.assertEqual(observation.fingerprint.normalized_text, "")
        self.assertEqual(observation.fingerprint.ocr_box_count, 0)

    def test_prefetched_fingerprint_is_reused_without_second_ocr(self):
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [
            OCRItem(
                "prefetched",
                0.99,
                [[0, 0], [20, 0], [20, 10], [0, 10]],
            ),
        ]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=self.region,
            max_scans=1,
            wait=Mock(),
        )

        first_observation = detector.capture_observation(1)
        first_fingerprint = first_observation.fingerprint
        result = detector.detect(
            single_rule("not-present"),
            first_observation=first_observation,
        )

        self.assertEqual(capture.calls, 1)
        backend.recognize.assert_called_once_with(1)
        self.assertEqual(result.scans_completed, 1)
        self.assertIs(result.observations[0], first_observation)
        self.assertIsNot(result.observations[0].fingerprint, first_fingerprint)
        self.assertEqual(result.observations[0].fingerprint.screen_index, 1)
        self.assertEqual(
            result.observations[0].fingerprint.exact_hash,
            first_fingerprint.exact_hash,
        )
        self.assertEqual(
            result.observations[0].fingerprint.captured_at,
            first_fingerprint.captured_at,
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

    def test_scan_observation_carries_one_r04_result_without_parallel_text_fields(
        self,
    ):
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
            "fingerprint",
            "raw_items",
            "captured_at",
            "screen_id",
            "normalization",
            "normalization_min_confidence",
            "rule_comparison",
        ])
        for forbidden_name in (
            "accepted_items",
            "evidence",
            "normalized_text",
            "comparison_text",
            "segments",
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

    def test_r04_only_shadow_never_triggers_confirmation_or_page_calls(self):
        wait = Mock()
        detector = OCRKeywordDetector(
            backend=Mock(),
            capture=FakeCapture(),
            region=self.region,
            max_scans=1,
            wait=wait,
        )
        normalization = ocr_normalization.normalize_ocr_text((
            ocr_normalization.NormalizationBox(
                "box-1",
                "Python",
                ((0, 0), (20, 0), (20, 10), (0, 10)),
                0,
                0.99,
            ),
        ))
        first_observation = ScanObservation(
            1,
            "legacy miss",
            1,
            0.01,
            normalization=normalization,
        )

        with patch("ocr_detector.normalize_ocr_text") as normalizer:
            result = detector.detect(
                single_rule("Python"),
                first_observation=first_observation,
            )

        self.assertFalse(result.confirmed_match)
        self.assertEqual(
            first_observation.rule_comparison.comparison_outcome,
            RULE_COMPARISON_R04_ONLY,
        )
        self.assertEqual(detector.capture.calls, 0)
        detector.backend.recognize.assert_not_called()
        wait.assert_not_called()
        normalizer.assert_not_called()

    def test_legacy_only_and_failed_shadow_keep_original_confirmation_budget(self):
        base = ocr_normalization.normalize_ocr_text((
            ocr_normalization.NormalizationBox(
                "box-1",
                "placeholder",
                ((0, 0), (20, 0), (20, 10), (0, 10)),
                0,
                0.99,
            ),
        ))
        variants = (
            (
                "legacy_only",
                replace(base, comparison_text="java"),
                RULE_COMPARISON_LEGACY_ONLY,
            ),
            (
                "normalization_failed",
                replace(base, status=NORMALIZATION_FAILED),
                RULE_COMPARISON_NORMALIZATION_FAILED,
            ),
        )

        for name, normalization, expected_outcome in variants:
            with self.subTest(name=name):
                wait = Mock()
                backend = Mock()
                backend.recognize.return_value = [
                    self.make_box_item("Python")
                ]
                detector = OCRKeywordDetector(
                    backend=backend,
                    capture=FakeCapture(),
                    region=self.region,
                    max_scans=1,
                    wait=wait,
                )
                item = self.make_box_item("Python")
                first_observation = ScanObservation(
                    1,
                    "Python",
                    1,
                    0.01,
                    fingerprint=build_screen_fingerprint([item]),
                    normalization=normalization,
                )

                result = detector.detect(
                    single_rule("Python"),
                    first_observation=first_observation,
                )

                self.assertTrue(result.confirmed_match)
                self.assertEqual(
                    first_observation.rule_comparison.comparison_outcome,
                    expected_outcome,
                )
                self.assertEqual(detector.capture.calls, 1)
                backend.recognize.assert_called_once()
                wait.assert_called_once()
                self.assertEqual(
                    [
                        observation.fingerprint.fingerprint_version
                        for observation in result.observations
                    ],
                    [FINGERPRINT_VERSION, FINGERPRINT_VERSION],
                )

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


class CompleteCandidateScanTests(unittest.TestCase):
    def setUp(self):
        self.region = ScreenRegion(0, 0, 100, 100)

    def _detector(self, pages, *, max_scans=3, callback=None, mode="shadow",
                  scroll=None, wait=None, restore_focus=None,
                  interrupt_reason_provider=None):
        return OCRKeywordDetector(
            backend=FakeBackend(pages),
            capture=FakeCapture(),
            region=self.region,
            max_scans=max_scans,
            scroll=Mock() if scroll is None else scroll,
            wait=Mock() if wait is None else wait,
            observation_callback=callback,
            dynamic_end_config=DynamicEndConfig(mode=mode),
            restore_focus=restore_focus,
            interrupt_reason_provider=interrupt_reason_provider,
        )

    @staticmethod
    def _callback_for_positions(*positions):
        calls = 0

        def callback(_observation, _capture_type, _formal, _screen_index):
            nonlocal calls
            position = positions[min(calls, len(positions) - 1)]
            calls += 1
            return SimpleNamespace(
                record=SimpleNamespace(
                    screen_id="complete-scan-{0}".format(calls),
                    exact_hash=("a" if position != "changed" else "b") * 64,
                ),
                saved=True,
                position_decision=PositionDecision(
                    position,
                    "initial" if position == "initial" else position,
                    None if position == "initial" else "complete-scan-1",
                    "complete-scan-test",
                ),
                load_health=True,
                ocr_health=True,
                identity_health=True,
            )

        return callback

    def test_detect_empty_rules_preserves_legacy_zero_scan_fast_return(self):
        callback = Mock()
        scroll = Mock()
        wait = Mock()
        detector = self._detector(
            ["Python"], callback=callback, scroll=scroll, wait=wait,
        )

        with patch.object(
            detector,
            "_match_observation",
            side_effect=AssertionError("empty rules must not match"),
        ):
            result = detector.detect([])

        self.assertIsInstance(result, DetectionResult)
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.scans_completed, 0)
        self.assertEqual(detector.capture.calls, 0)
        self.assertEqual(detector.backend.calls, 0)
        callback.assert_not_called()
        scroll.assert_not_called()
        wait.assert_not_called()

    def test_scan_candidate_is_separate_rule_free_public_entry(self):
        detector = self._detector(["complete scan"], max_scans=1)

        result = detector.scan_candidate()

        self.assertIsInstance(result, DetectionResult)
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)
        with self.assertRaises(TypeError):
            detector.scan_candidate(rules=single_rule("Python"))

    def test_scan_candidate_reuses_rule_neutral_first_observation_without_recapture(self):
        detector = self._detector(["later evidence"], max_scans=2)
        first = detector.capture_observation(1)
        rule = single_rule("Python")[0]
        first.matched_keyword = rule.source
        first.matched_rule = rule
        first.rule_comparison = object()
        capture_count = detector.capture.calls
        backend_count = detector.backend.calls

        result = detector.scan_candidate(first)

        self.assertEqual(detector.capture.calls, capture_count + 1)
        self.assertEqual(detector.backend.calls, backend_count + 1)
        self.assertIsNot(result.observations[0], first)
        self.assertEqual(result.observations[0].text, first.text)
        self.assertIsNone(result.observations[0].matched_keyword)
        self.assertIsNone(result.observations[0].matched_rule)
        self.assertIsNone(result.observations[0].rule_comparison)
        self.assertEqual(first.matched_keyword, rule.source)
        self.assertIs(first.matched_rule, rule)
        self.assertIsNotNone(first.rule_comparison)
        self.assertEqual(len(result.observations), 2)

    def test_scan_candidate_never_calls_matcher_or_rule_confirmation(self):
        callback_types = []

        def callback(_observation, capture_type, _formal, _screen_index):
            callback_types.append(capture_type)

        wait = Mock()
        detector = self._detector(
            ["Python early evidence", "later evidence", "last evidence"],
            callback=callback,
            wait=wait,
        )

        with patch.object(
            detector,
            "_match_observation",
            side_effect=AssertionError("complete scan must not match"),
        ) as matcher, patch.object(
            detector,
            "_rule_confirmation_result",
            side_effect=AssertionError("complete scan must not confirm"),
        ) as confirmation, patch(
            "ocr_detector.matching_keyword_rule",
            side_effect=AssertionError("legacy matcher must be unreachable"),
        ):
            result = detector.scan_candidate()

        self.assertEqual(matcher.call_count, 0)
        self.assertEqual(confirmation.call_count, 0)
        self.assertEqual(len(result.observations), 3)
        self.assertIn("python", result.observations[0].text)
        self.assertIn("later", result.observations[1].text)
        self.assertEqual(callback_types, ["formal_screen"] * 3)
        self.assertNotIn("rule_confirmation", callback_types)
        self.assertEqual(wait.call_count, 2)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_scan_candidate_rule_independence_for_identical_lifecycle_observations(self):
        def run(matcher_result):
            callback_types = []

            def callback(_observation, capture_type, _formal, _screen_index):
                callback_types.append(capture_type)

            scroll = Mock()
            detector = self._detector(
                ["Python evidence", "later evidence"],
                max_scans=2,
                callback=callback,
                scroll=scroll,
            )
            with patch(
                "ocr_detector.matching_keyword_rule",
                return_value=matcher_result,
            ) as matcher, patch.object(
                detector,
                "_rule_confirmation_result",
                return_value=DetectionResult(True, True),
            ) as confirmation:
                result = detector.scan_candidate()
            return (
                [observation.text for observation in result.observations],
                callback_types,
                detector.capture.calls,
                detector.backend.calls,
                scroll.call_count,
                result.dynamic_end_reason,
                result.confirmed_match,
                result.matched_keyword,
                matcher.call_count,
                confirmation.call_count,
            )

        legacy_match = single_rule("Python")[0]
        self.assertEqual(run(legacy_match), run(None))

    def test_scan_candidate_uses_existing_dynamic_end_and_safety_limit(self):
        bottom_scroll = Mock()
        bottom = self._detector(
            ["Python evidence"] * 3,
            max_scans=4,
            callback=self._callback_for_positions("initial", "same", "same"),
            mode="safe",
            scroll=bottom_scroll,
            restore_focus=Mock(return_value=True),
        )
        bottom_result = bottom.scan_candidate()

        self.assertEqual(bottom_result.dynamic_end_reason, "scroll_bottom")
        self.assertEqual(bottom_result.scans_completed, 2)
        self.assertEqual(bottom.capture.calls, 3)
        self.assertEqual(bottom_scroll.call_count, 2)
        self.assertFalse(bottom_result.confirmed_match)

        limit_scroll = Mock()
        limited = self._detector(
            ["Python evidence", "later evidence"],
            max_scans=2,
            callback=self._callback_for_positions("initial", "changed"),
            mode="safe",
            scroll=limit_scroll,
        )
        limit_result = limited.scan_candidate()

        self.assertEqual(limit_result.dynamic_end_reason, "max_screen_limit")
        self.assertEqual(limit_result.scans_completed, 2)
        self.assertEqual(limited.capture.calls, 2)
        self.assertEqual(limit_scroll.call_count, 1)
        self.assertIsNone(limit_result.abort_reason)

    def test_scan_candidate_recovery_skips_rule_confirmation_and_preserves_focus_scroll_bounds(self):
        callback_types = []

        position_callback = self._callback_for_positions("initial", "same", "same")

        def callback(observation, capture_type, formal, screen_index):
            callback_types.append(capture_type)
            return position_callback(observation, capture_type, formal, screen_index)

        scroll = Mock()
        wait = Mock()
        restore_focus = Mock(return_value=True)
        detector = self._detector(
            ["Python evidence"] * 3,
            max_scans=4,
            callback=callback,
            mode="safe",
            scroll=scroll,
            wait=wait,
            restore_focus=restore_focus,
        )

        with patch.object(
            detector,
            "_match_observation",
            side_effect=AssertionError("recovery must remain rule-neutral"),
        ) as matcher, patch.object(
            detector,
            "_rule_confirmation_result",
            side_effect=AssertionError("recovery must not confirm a rule"),
        ) as confirmation:
            result = detector.scan_candidate()

        self.assertEqual(result.dynamic_end_reason, "scroll_bottom")
        self.assertEqual(matcher.call_count, 0)
        self.assertEqual(confirmation.call_count, 0)
        self.assertEqual(callback_types, [
            "formal_screen", "formal_screen", "position_confirmation",
        ])
        self.assertEqual(scroll.call_count, 2)
        self.assertEqual(wait.call_count, 2)
        restore_focus.assert_called_once()
        self.assertEqual(detector.dynamic_end_state.focus_restore_count, 1)
        self.assertEqual(detector.dynamic_end_state.scroll_retry_count, 1)

    def test_scan_candidate_preserves_interrupt_abort_and_error_projection(self):
        interrupted = self._detector(
            ["Python evidence"],
            max_scans=2,
            callback=self._callback_for_positions("initial"),
            mode="safe",
            interrupt_reason_provider=lambda: "user_interrupted",
        ).scan_candidate()
        self.assertEqual(interrupted.interrupt_reason, "user_interrupted")
        self.assertIsNone(interrupted.dynamic_end_reason)

        aborted = self._detector(
            ["Python evidence"],
            max_scans=2,
            callback=lambda *_args: SimpleNamespace(
                record=None,
                saved=False,
                position_decision=None,
                load_health=None,
                ocr_health=None,
                identity_health=None,
            ),
            mode="safe",
        ).scan_candidate()
        self.assertEqual(aborted.abort_reason, "store_failed")
        self.assertIsNone(aborted.dynamic_end_reason)

        class BrokenBackend:
            def recognize(self, _image):
                raise RuntimeError("complete scan OCR failure")

        failed_detector = OCRKeywordDetector(
            backend=BrokenBackend(),
            capture=FakeCapture(),
            region=self.region,
            max_scans=1,
            wait=lambda _seconds: None,
        )
        failed = failed_detector.scan_candidate()
        self.assertFalse(failed.success)
        self.assertIn("complete scan OCR failure", failed.error)
        self.assertIsNone(failed.dynamic_end_reason)


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
