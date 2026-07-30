import unittest
from unittest.mock import Mock, patch

import simple_brush
from ocr_detector import OCRKeywordDetector, ScanObservation
from ocr_records import CaptureStatus, CaptureType, RunStatus
from ocr_text import OCRItem


class FakeStore:
    def __init__(
        self,
        enabled=True,
        fail_screens=False,
        candidate_save_result=True,
        candidate_save_error=None,
        error_save_error=None,
    ):
        self.enabled = enabled
        self.run_id = "run-stage0-test"
        self.fail_screens = fail_screens
        self.candidate_save_result = candidate_save_result
        self.candidate_save_error = candidate_save_error
        self.error_save_error = error_save_error
        self.screens = []
        self.candidates = []
        self.candidate_attempts = []
        self.errors = []
        self.error_attempts = 0
        self.closed_status = None

    def save_screen(self, record):
        self.screens.append(record)
        return not self.fail_screens

    def save_candidate(self, document):
        self.candidate_attempts.append(document)
        if self.candidate_save_error is not None:
            raise self.candidate_save_error
        if not self.enabled or not self.candidate_save_result:
            return False
        self.candidates.append(document)
        return True

    def save_error(self, error_type, operation, context=None):
        self.error_attempts += 1
        if self.error_save_error is not None:
            raise self.error_save_error
        self.errors.append((error_type, operation, context))
        return True

    def close(self, status=RunStatus.COMPLETED):
        self.closed_status = status
        self.enabled = False
        return True


class FakeCapture:
    def __init__(self):
        self.calls = 0

    def capture(self, _region):
        self.calls += 1
        return self.calls


class Stage0MainFlowIntegrationTests(unittest.TestCase):
    def setUp(self):
        names = (
            "ocr_record_store",
            "current_candidate_builder",
            "candidate_record_sequence",
            "recorded_observation_ids",
            "ocr_detector",
            "forward_enabled",
            "forward_keywords",
            "stop_event",
            "stop_reason",
        )
        self.saved = {name: getattr(simple_brush, name) for name in names}
        simple_brush.ocr_record_store = None
        simple_brush.current_candidate_builder = None
        simple_brush.candidate_record_sequence = 0
        simple_brush.recorded_observation_ids = {}
        simple_brush.stop_event = False
        simple_brush.stop_reason = None

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(simple_brush, name, value)

    @staticmethod
    def observation(text="虚构 Python C++ C# .NET"):
        item = OCRItem(
            text,
            0.96,
            ((1, 2), (50, 2), (50, 18), (1, 18)),
        )
        return ScanObservation(
            scan_number=1,
            text="python",
            item_count=1,
            elapsed_seconds=0.01,
            ocr_box_count=6,
            ocr_text_length=40,
            raw_items=(item,),
            captured_at="2026-07-30T12:00:00+08:00",
        )

    def start_builder(self, store):
        simple_brush.ocr_record_store = store
        return simple_brush.start_candidate_ocr_recording(1, 0)

    def test_detector_callback_saves_formal_and_confirmation_without_extra_ocr(self):
        store = FakeStore()
        self.start_builder(store)
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [
            OCRItem(
                "虚构 Python",
                0.99,
                ((0, 0), (20, 0), (20, 10), (0, 10)),
            )
        ]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=Mock(),
            max_scans=8,
            min_confidence=0.85,
            scroll=Mock(),
            wait=Mock(),
            observation_callback=simple_brush.record_detection_observation,
        )
        simple_brush.ocr_detector = detector
        simple_brush.forward_enabled = True
        simple_brush.forward_keywords = simple_brush.parse_keyword_rules(
            '"Python"'
        )

        with patch.object(
            simple_brush, "ensure_ocr_region_calibrated", return_value=True
        ):
            matched, result = simple_brush.detect_keywords()

        self.assertTrue(matched)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(capture.calls, 2)
        self.assertEqual(backend.recognize.call_count, 2)
        self.assertEqual(len(store.screens), 2)
        self.assertEqual(
            [record.capture_type for record in store.screens],
            [CaptureType.FORMAL_SCREEN, CaptureType.SCROLL_CONFIRMATION],
        )
        self.assertEqual(
            [record.is_formal_screen for record in store.screens],
            [True, False],
        )
        self.assertEqual(store.screens[0].raw_boxes[0].raw_text, "虚构 Python")

    def test_same_observation_is_saved_only_once_when_reused(self):
        store = FakeStore()
        self.start_builder(store)
        observation = self.observation()

        first = simple_brush.record_ocr_observation(
            observation, CaptureType.FORMAL_SCREEN, True, 1
        )
        second = simple_brush.record_ocr_observation(
            observation, CaptureType.FORMAL_SCREEN, True, 1
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(store.screens), 1)

    def test_load_retry_recording_does_not_change_ocr_or_wait_counts(self):
        store = FakeStore(fail_screens=True)
        self.start_builder(store)
        first = self.observation("虚构短页")
        first.ocr_box_count = 2
        first.ocr_text_length = 5
        second = self.observation("虚构完整页 Python")
        detector = Mock()
        detector.capture_observation.side_effect = [first, second]
        simple_brush.ocr_detector = detector

        with patch.object(
            simple_brush, "safe_wait", return_value=True
        ) as wait:
            outcome, loaded, retry_number, _reason = (
                simple_brush.run_detail_load_gate(1, 0, 0, False)
            )

        self.assertEqual(outcome, "loaded")
        self.assertIs(loaded, second)
        self.assertEqual(retry_number, 1)
        self.assertEqual(detector.capture_observation.call_count, 2)
        wait.assert_called_once_with(simple_brush.LOAD_RETRY_WAIT_SECONDS)
        self.assertEqual(len(store.screens), 1)
        self.assertEqual(store.screens[0].capture_type, CaptureType.LOAD_CHECK)
        simple_brush.record_ocr_observation(
            second, CaptureType.FORMAL_SCREEN, True, 1
        )
        self.assertEqual(len(store.screens), 2)

    def test_esc_finalization_keeps_already_saved_screen_and_adds_document(self):
        store = FakeStore()
        builder = self.start_builder(store)
        simple_brush.record_ocr_observation(
            self.observation(), CaptureType.FORMAL_SCREEN, True, 1
        )
        simple_brush.stop_event = True
        simple_brush.stop_reason = "esc"

        document = simple_brush.finalize_active_candidate_for_stop()

        self.assertEqual(len(store.screens), 1)
        self.assertEqual(len(store.candidates), 1)
        self.assertIs(document, store.candidates[0])
        self.assertEqual(document.capture_status, CaptureStatus.INTERRUPTED)
        self.assertEqual(
            document.capture_summary.abort_reason,
            "user_interrupted",
        )
        self.assertIsNone(document.capture_summary.end_reason)
        self.assertTrue(builder.finalized)
        self.assertIsNone(simple_brush.current_candidate_builder)

    def test_runtime_expiry_is_interrupted_with_abort_reason_only(self):
        store = FakeStore()
        self.start_builder(store)
        simple_brush.stop_event = True
        simple_brush.stop_reason = "run_duration_elapsed"

        document = simple_brush.finalize_active_candidate_for_stop()

        self.assertEqual(document.capture_status, CaptureStatus.INTERRUPTED)
        self.assertIsNone(document.capture_summary.end_reason)
        self.assertEqual(
            document.capture_summary.abort_reason,
            "runtime_expired",
        )

    def test_max_screen_outcome_is_completed_with_limit(self):
        detection_result = Mock(confirmed_match=False, scans_completed=8)

        status, end_reason = simple_brush.candidate_capture_status(
            detection_result
        )

        self.assertEqual(status, CaptureStatus.COMPLETED_WITH_LIMIT)
        self.assertEqual(end_reason, "max_screen_limit")

    def run_one_candidate(self, store, view_side_effect):
        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_enabled = False
            simple_brush.batch_filter_regions = None

        with (
            patch.object(simple_brush, "create_ocr_record_store", return_value=store),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": False,
                "no_batch_filter": False,
                "simple_mouse": False,
                "auto": True,
                "action_mode": None,
                "calibration_profile": "",
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "open_first_candidate_for_batch", return_value=True),
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(simple_brush, "view_candidate", side_effect=view_side_effect) as view,
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            result = simple_brush.run()
        return result, view

    def run_hard_recovery(
        self,
        store,
        *,
        recovery_succeeds=True,
        old_finalize_error=None,
    ):
        old_observation = self.observation("恢复前旧 OCR")
        new_load_observation = self.observation("恢复后加载 OCR")
        new_formal_observation = self.observation("恢复后正式 OCR Python")
        facts = {}
        gate_attempt = 0

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = True
            simple_brush.forward_keywords = simple_brush.parse_keyword_rules(
                '"Python"'
            )
            simple_brush.batch_filter_enabled = True
            simple_brush.batch_filter_regions = Mock()
            simple_brush.run_duration_seconds = 0

        def load_gate(*_args, **_kwargs):
            nonlocal gate_attempt
            gate_attempt += 1
            if gate_attempt == 1:
                facts["old_builder"] = simple_brush.current_candidate_builder
                if (
                    facts["old_builder"] is not None
                    and old_finalize_error is not None
                ):
                    facts["old_builder"].finalize = Mock(
                        side_effect=old_finalize_error
                    )
                simple_brush.record_ocr_observation(
                    old_observation,
                    CaptureType.LOAD_CHECK,
                    False,
                    None,
                )
                return (
                    "load_recovering",
                    None,
                    simple_brush.MAX_LOAD_RETRIES,
                    "low_box_count_and_short_text",
                )

            new_builder = simple_brush.current_candidate_builder
            facts["new_builder"] = new_builder
            facts["new_initial_screen_count"] = (
                None
                if new_builder is None
                else new_builder.retained_screen_count
            )
            facts["ids_before_new_observation"] = set(
                simple_brush.recorded_observation_ids
            )
            simple_brush.record_ocr_observation(
                new_load_observation,
                CaptureType.LOAD_CHECK,
                False,
                None,
            )
            return (
                "loaded",
                new_formal_observation,
                0,
                "detail_ready",
            )

        def stop_after_view(*_args, **_kwargs):
            facts["view_builder"] = simple_brush.current_candidate_builder
            simple_brush.stop_event = True
            simple_brush.stop_reason = "esc"
            return False, None

        with (
            patch.object(simple_brush, "create_ocr_record_store", return_value=store),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": False,
                "no_batch_filter": False,
                "simple_mouse": False,
                "auto": True,
                "action_mode": None,
                "calibration_profile": "",
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                return_value=True,
            ),
            patch.object(
                simple_brush,
                "open_first_candidate_for_batch",
                return_value=True,
            ) as open_first,
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(
                simple_brush,
                "run_detail_load_gate",
                side_effect=load_gate,
            ) as gate,
            patch.object(
                simple_brush,
                "refresh_page",
                return_value=recovery_succeeds,
            ) as refresh,
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                return_value=True,
            ) as reopen,
            patch.object(
                simple_brush,
                "recover_detail_page",
                wraps=simple_brush.recover_detail_page,
            ) as recover,
            patch.object(
                simple_brush,
                "view_candidate",
                side_effect=stop_after_view,
            ) as view,
            patch.object(simple_brush, "safe_wait", return_value=True) as wait,
            patch.object(simple_brush, "next_candidate") as next_candidate,
            patch.object(simple_brush, "ocr_scroll_down") as ocr_scroll,
            patch.object(simple_brush, "human_scroll_once") as human_scroll,
        ):
            result = simple_brush.run()

        return {
            "result": result,
            "facts": facts,
            "old_observation": old_observation,
            "gate": gate,
            "open_first": open_first,
            "refresh": refresh,
            "reopen": reopen,
            "recover": recover,
            "view": view,
            "wait": wait,
            "next_candidate": next_candidate,
            "ocr_scroll": ocr_scroll,
            "human_scroll": human_scroll,
        }

    @staticmethod
    def recovery_business_call_counts(calls):
        return {
            name: calls[name].call_count
            for name in (
                "gate",
                "open_first",
                "refresh",
                "reopen",
                "recover",
                "view",
                "wait",
                "next_candidate",
                "ocr_scroll",
                "human_scroll",
            )
        }

    def test_hard_recovery_starts_a_fresh_candidate_recording_lifecycle(self):
        store = FakeStore()

        calls = self.run_hard_recovery(store)

        self.assertEqual(calls["result"], 0)
        self.assertEqual(len(store.candidates), 2)
        old_document, new_document = store.candidates
        old_builder = calls["facts"]["old_builder"]
        new_builder = calls["facts"]["new_builder"]

        self.assertTrue(old_builder.finalized)
        self.assertEqual(old_builder.retained_screen_count, 0)
        self.assertEqual(old_document.capture_status, CaptureStatus.ABORTED)
        self.assertIsNone(old_document.capture_summary.end_reason)
        self.assertEqual(
            old_document.capture_summary.abort_reason,
            "load_recovery_restart",
        )
        self.assertEqual(
            sum(
                document.candidate_record_id
                == old_document.candidate_record_id
                for document in store.candidates
            ),
            1,
        )

        self.assertIsNot(old_builder, new_builder)
        self.assertNotEqual(
            old_document.candidate_record_id,
            new_document.candidate_record_id,
        )
        self.assertEqual(new_document.sequence_number, 2)
        self.assertEqual(
            new_document.sequence_number,
            old_document.sequence_number + 1,
        )
        self.assertEqual(calls["facts"]["new_initial_screen_count"], 0)
        self.assertNotIn(
            id(calls["old_observation"]),
            calls["facts"]["ids_before_new_observation"],
        )
        self.assertEqual(
            [screen.attempt_index for screen in old_document.screens],
            [1],
        )
        self.assertEqual(new_document.screens[0].attempt_index, 1)
        self.assertEqual(
            [screen.raw_text for screen in old_document.screens],
            ["恢复前旧 OCR"],
        )
        self.assertNotIn(
            "恢复前旧 OCR",
            [screen.raw_text for screen in new_document.screens],
        )
        self.assertIsNone(simple_brush.current_candidate_builder)
        self.assertEqual(simple_brush.recorded_observation_ids, {})
        self.assertEqual(
            self.recovery_business_call_counts(calls),
            {
                "gate": 2,
                "open_first": 1,
                "refresh": 1,
                "reopen": 1,
                "recover": 1,
                "view": 1,
                "wait": 0,
                "next_candidate": 0,
                "ocr_scroll": 0,
                "human_scroll": 0,
            },
        )

    def test_failed_hard_recovery_keeps_existing_stop_finalization(self):
        store = FakeStore()

        calls = self.run_hard_recovery(store, recovery_succeeds=False)

        self.assertEqual(calls["result"], 0)
        self.assertEqual(simple_brush.stop_reason, "load_failed")
        self.assertEqual(len(store.candidates), 1)
        self.assertEqual(len(store.candidate_attempts), 1)
        document = store.candidates[0]
        self.assertEqual(document.capture_status, CaptureStatus.ABORTED)
        self.assertEqual(document.capture_summary.abort_reason, "load_failed")
        self.assertNotEqual(
            document.capture_summary.abort_reason,
            "load_recovery_restart",
        )
        self.assertEqual(
            self.recovery_business_call_counts(calls),
            {
                "gate": 1,
                "open_first": 1,
                "refresh": 1,
                "reopen": 0,
                "recover": 1,
                "view": 0,
                "wait": 0,
                "next_candidate": 0,
                "ocr_scroll": 0,
                "human_scroll": 0,
            },
        )

    def test_hard_recovery_ignores_candidate_and_error_store_failures(self):
        baseline_calls = self.run_hard_recovery(FakeStore())
        baseline_counts = self.recovery_business_call_counts(baseline_calls)
        cases = (
            (
                "save_candidate_false",
                FakeStore(candidate_save_result=False),
                0,
                2,
                None,
            ),
            (
                "save_candidate_and_save_error_raise",
                FakeStore(
                    candidate_save_error=OSError("candidate write failed"),
                    error_save_error=OSError("error write failed"),
                ),
                2,
                2,
                None,
            ),
            (
                "builder_finalize_and_save_error_raise",
                FakeStore(error_save_error=OSError("error write failed")),
                1,
                1,
                OSError("builder finalize failed"),
            ),
        )

        for (
            name,
            store,
            expected_error_attempts,
            expected_candidate_attempts,
            old_finalize_error,
        ) in cases:
            with self.subTest(name=name):
                calls = self.run_hard_recovery(
                    store,
                    old_finalize_error=old_finalize_error,
                )

                self.assertEqual(calls["result"], 0)
                self.assertEqual(
                    self.recovery_business_call_counts(calls),
                    baseline_counts,
                )
                self.assertEqual(
                    len(store.candidate_attempts),
                    expected_candidate_attempts,
                )
                self.assertEqual(store.error_attempts, expected_error_attempts)
                self.assertIsNotNone(calls["facts"]["new_builder"])
                self.assertIsNot(
                    calls["facts"]["old_builder"],
                    calls["facts"]["new_builder"],
                )
                self.assertEqual(
                    calls["facts"]["new_builder"].sequence_number,
                    2,
                )
                self.assertNotIn(
                    id(calls["old_observation"]),
                    calls["facts"]["ids_before_new_observation"],
                )

    def test_disabled_store_does_not_change_hard_recovery_business_calls(self):
        baseline_calls = self.run_hard_recovery(FakeStore())
        disabled_store = FakeStore(enabled=False)

        calls = self.run_hard_recovery(disabled_store)

        self.assertEqual(calls["result"], 0)
        self.assertEqual(
            self.recovery_business_call_counts(calls),
            self.recovery_business_call_counts(baseline_calls),
        )
        self.assertIsNone(calls["facts"]["old_builder"])
        self.assertIsNone(calls["facts"]["new_builder"])
        self.assertEqual(disabled_store.candidate_attempts, [])

    def test_recovery_reset_releases_builder_if_store_is_disabled(self):
        store = FakeStore()
        old_builder = self.start_builder(store)
        old_observation = self.observation("恢复前旧 OCR")
        simple_brush.record_ocr_observation(
            old_observation,
            CaptureType.LOAD_CHECK,
            False,
            None,
        )
        store.enabled = False

        document = simple_brush.finalize_current_candidate_recording(
            CaptureStatus.ABORTED,
            None,
            "load_recovery_restart",
        )

        self.assertTrue(old_builder.finalized)
        self.assertEqual(document.capture_status, CaptureStatus.ABORTED)
        self.assertEqual(len(store.candidate_attempts), 1)
        self.assertEqual(store.candidates, [])
        self.assertIsNone(simple_brush.current_candidate_builder)
        self.assertEqual(simple_brush.recorded_observation_ids, {})

        store.enabled = True
        new_builder = simple_brush.start_candidate_ocr_recording(1, 0)
        self.assertIsNotNone(new_builder)
        self.assertNotEqual(
            new_builder.candidate_record_id,
            old_builder.candidate_record_id,
        )
        self.assertEqual(new_builder.sequence_number, 2)
        self.assertEqual(new_builder.retained_screen_count, 0)
        self.assertNotIn(
            id(old_observation),
            simple_brush.recorded_observation_ids,
        )

    def test_normal_run_keeps_one_builder_and_sequence_for_one_candidate(self):
        store = FakeStore()
        facts = {}

        def complete_then_stop(_index):
            facts["builder"] = simple_brush.current_candidate_builder
            facts["saved_before_view_completed"] = len(store.candidates)
            simple_brush.stop_event = True
            simple_brush.stop_reason = "esc"
            return True, None

        result, view = self.run_one_candidate(store, complete_then_stop)

        self.assertEqual(result, 0)
        self.assertEqual(view.call_count, 1)
        self.assertEqual(facts["saved_before_view_completed"], 0)
        self.assertEqual(len(store.candidates), 1)
        document = store.candidates[0]
        self.assertEqual(document.sequence_number, 1)
        self.assertEqual(
            document.candidate_record_id,
            facts["builder"].candidate_record_id,
        )
        self.assertTrue(facts["builder"].finalized)

    def test_run_enabled_and_disabled_storage_keep_view_call_count_unchanged(self):
        def completed_then_stop(_index):
            simple_brush.stop_event = True
            simple_brush.stop_reason = "esc"
            return True, None

        enabled = FakeStore(enabled=True)
        enabled_result, enabled_view = self.run_one_candidate(
            enabled, completed_then_stop
        )
        disabled = FakeStore(enabled=False)
        disabled_result, disabled_view = self.run_one_candidate(
            disabled, completed_then_stop
        )

        self.assertEqual((enabled_result, disabled_result), (0, 0))
        self.assertEqual(enabled_view.call_count, 1)
        self.assertEqual(disabled_view.call_count, 1)
        self.assertEqual(len(enabled.candidates), 1)
        self.assertEqual(enabled.candidates[0].capture_status, CaptureStatus.COMPLETED)
        self.assertEqual(len(disabled.candidates), 0)
        self.assertEqual(enabled.closed_status, RunStatus.INTERRUPTED)
        self.assertEqual(disabled.closed_status, RunStatus.INTERRUPTED)

    def test_run_exception_saves_aborted_candidate_and_closes_error(self):
        store = FakeStore(enabled=True)

        result, view = self.run_one_candidate(
            store, RuntimeError("synthetic view failure")
        )

        self.assertEqual(result, 0)
        self.assertEqual(view.call_count, 1)
        self.assertEqual(len(store.candidates), 1)
        document = store.candidates[0]
        self.assertEqual(document.capture_status, CaptureStatus.ABORTED)
        self.assertEqual(document.capture_summary.abort_reason, "RuntimeError")
        self.assertIsNone(document.capture_summary.end_reason)
        self.assertEqual(store.closed_status, RunStatus.ERROR)


if __name__ == "__main__":
    unittest.main()
