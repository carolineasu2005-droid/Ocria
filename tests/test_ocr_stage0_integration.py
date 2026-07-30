import unittest
from unittest.mock import Mock, patch

import simple_brush
from ocr_detector import OCRKeywordDetector, ScanObservation
from ocr_records import CaptureStatus, CaptureType, RunStatus
from ocr_text import OCRItem


class FakeStore:
    def __init__(self, enabled=True, fail_screens=False):
        self.enabled = enabled
        self.run_id = "run-stage0-test"
        self.fail_screens = fail_screens
        self.screens = []
        self.candidates = []
        self.errors = []
        self.closed_status = None

    def save_screen(self, record):
        self.screens.append(record)
        return not self.fail_screens

    def save_candidate(self, document):
        self.candidates.append(document)
        return True

    def save_error(self, error_type, operation, context=None):
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
