import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import simple_brush
import ocr_normalization
from ocr_detector import DynamicEndConfig, OCRKeywordDetector, ScanObservation
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_records import (
    CandidateOcrDocument,
    CaptureStatus,
    CaptureType,
    RunStatus,
    ScreeningProfileBinding,
)
from ocr_store import JsonlOcrRecordStore
from screening_profile import Criterion, ScreeningProfileVersion, criteria_digest
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
        self.candidate_owner_attempts = []
        self.errors = []
        self.error_attempts = 0
        self.closed_status = None

    def save_screen(self, record):
        self.screens.append(record)
        return not self.fail_screens

    def save_candidate(self, document, *, owner_candidate_record_id=None):
        self.candidate_attempts.append(document)
        self.candidate_owner_attempts.append(owner_candidate_record_id)
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
        criteria = (Criterion("C001", "Python experience"),)
        self.screening_profile_version = ScreeningProfileVersion(
            screening_profile_id="sp_0123456789abcdef0123456789abcdef",
            profile_version=1,
            criteria=criteria,
            criteria_digest=criteria_digest(criteria),
            created_at="2026-08-18T12:00:00+08:00",
        )
        self.screening_profile_id = (
            self.screening_profile_version.screening_profile_id
        )

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
        screen_id = "screen-stage0-{0}".format(len(text))
        normalization = normalize_ocr_text((NormalizationBox(
            "{0}:box:0".format(screen_id),
            item.text,
            item.box,
            0,
            item.confidence,
        ),))
        return ScanObservation(
            scan_number=1,
            text="python",
            item_count=1,
            elapsed_seconds=0.01,
            ocr_box_count=6,
            ocr_text_length=40,
            raw_items=(item,),
            captured_at="2026-07-30T12:00:00+08:00",
            screen_id=screen_id,
            normalization=normalization,
            normalization_min_confidence=0.85,
        )

    def start_builder(self, store):
        simple_brush.ocr_record_store = store
        return simple_brush.start_candidate_ocr_recording(1, 0)

    def test_bound_store_persists_the_same_binding_after_close(self):
        binding = ScreeningProfileBinding(
            screening_profile_id=self.screening_profile_id,
            profile_version=self.screening_profile_version.profile_version,
            criteria_digest=self.screening_profile_version.criteria_digest,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root_dir = Path(temporary)

            def construct_store(**kwargs):
                return JsonlOcrRecordStore(root_dir=root_dir, **kwargs)

            with patch.object(
                simple_brush,
                "JsonlOcrRecordStore",
                side_effect=construct_store,
            ) as constructor:
                store = simple_brush.create_ocr_record_store(binding)

            self.assertIs(
                constructor.call_args.kwargs["screening_profile_binding"],
                binding,
            )
            self.assertTrue(store.enabled)
            store.close(RunStatus.INTERRUPTED)
            manifest = json.loads(store.manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["status"], RunStatus.INTERRUPTED.value)
        self.assertEqual(
            manifest["screening_profile_binding"],
            binding.to_dict(),
        )

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
        scroll = Mock()
        wait = Mock()
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=Mock(),
            max_scans=8,
            min_confidence=0.85,
            scroll=scroll,
            wait=wait,
            observation_callback=simple_brush.record_detection_observation,
        )
        simple_brush.ocr_detector = detector
        simple_brush.forward_enabled = True
        simple_brush.forward_keywords = simple_brush.parse_keyword_rules(
            '"Python"'
        )

        with patch.object(
            simple_brush, "ensure_ocr_region_calibrated", return_value=True
        ), patch(
            "ocr_detector.normalize_ocr_text",
            wraps=ocr_normalization.normalize_ocr_text,
        ) as normalizer:
            matched, result = simple_brush.detect_keywords()

        self.assertTrue(matched)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(capture.calls, 2)
        self.assertEqual(backend.recognize.call_count, 2)
        self.assertEqual(normalizer.call_count, 2)
        self.assertEqual(wait.call_count, 1)
        scroll.assert_not_called()
        self.assertEqual(len(store.screens), 2)
        self.assertEqual(
            [record.capture_type for record in store.screens],
            [CaptureType.FORMAL_SCREEN, CaptureType.RULE_CONFIRMATION],
        )
        self.assertEqual(
            [record.is_formal_screen for record in store.screens],
            [True, False],
        )
        self.assertEqual(store.screens[0].raw_boxes[0].raw_text, "虚构 Python")
        self.assertEqual(store.screens[0].position_status, "initial")
        self.assertEqual(store.screens[0].page_change_status, "initial")
        self.assertEqual(store.screens[0].prediction_reason, "initial_screen")
        self.assertEqual(store.screens[0].dynamic_end_version, "r07-v1")
        for record in store.screens:
            self.assertEqual(record.normalization_status.value, "completed")
            self.assertEqual(record.normalization_version, "r04-v1")
            self.assertIsNotNone(record.normalized_text)
            self.assertIsNotNone(record.comparison_text)
            self.assertEqual(record.ordered_box_ids, record.effective_box_ids)
            self.assertEqual(record.rule_evaluation_mode, "legacy_shadow")
            self.assertTrue(record.legacy_match)
            self.assertTrue(record.r04_match)
            self.assertEqual(record.comparison_outcome, "same_match")
            self.assertEqual(record.legacy_rule_index, 0)
            self.assertEqual(record.r04_rule_index, 0)

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

    def test_detector_callback_returns_store_bool_without_scan_control(self):
        store = FakeStore()
        self.start_builder(store)

        result = simple_brush.record_detection_observation(
            self.observation(),
            CaptureType.FORMAL_SCREEN,
            True,
            1,
        )

        self.assertTrue(result.saved)
        self.assertIs(result.record, store.screens[0])
        self.assertEqual(result.position_decision.position_status, "initial")

        failing_store = FakeStore(fail_screens=True)
        simple_brush.current_candidate_builder = None
        simple_brush.recorded_observation_ids = {}
        simple_brush.ocr_record_store = failing_store
        self.start_builder(failing_store)
        failed = simple_brush.record_detection_observation(
            self.observation("保存失败"),
            CaptureType.FORMAL_SCREEN,
            True,
            1,
        )
        self.assertFalse(failed.saved)
        self.assertEqual(len(failing_store.screens), 1)

    def test_failed_screen_is_discarded_and_candidate_still_finalizes_once(self):
        class RejectSecondScreenStore(FakeStore):
            def __init__(self):
                super().__init__()
                self.screen_attempts = []

            def save_screen(self, record):
                self.screen_attempts.append(record)
                if len(self.screen_attempts) == 2:
                    return False
                self.screens.append(record)
                return True

        store = RejectSecondScreenStore()
        builder = self.start_builder(store)
        first_observation = self.observation("第一屏成功保存的合成内容 Python")
        failed_observation = self.observation("第二屏技术保存失败的合成内容 C++")

        first = simple_brush.record_detection_observation(
            first_observation, CaptureType.FORMAL_SCREEN, True, 1,
        )
        failed = simple_brush.record_detection_observation(
            failed_observation, CaptureType.FORMAL_SCREEN, True, 2,
        )
        duplicate = simple_brush.record_detection_observation(
            failed_observation, CaptureType.FORMAL_SCREEN, True, 2,
        )

        self.assertTrue(first.saved)
        self.assertFalse(failed.saved)
        self.assertFalse(duplicate.saved)
        self.assertEqual(len(store.screen_attempts), 2)
        self.assertEqual(builder.retained_screen_count, 1)

        document = simple_brush.finalize_current_candidate_recording(
            CaptureStatus.ABORTED, None, "store_failed",
        )

        self.assertEqual(len(store.candidates), 1)
        self.assertIs(store.candidates[0], document)
        self.assertEqual(document.capture_status, CaptureStatus.ABORTED)
        self.assertEqual(document.capture_summary.abort_reason, "store_failed")
        self.assertEqual(document.screens, (store.screens[0],))
        self.assertEqual(
            {
                occurrence.source_screen_id
                for segment in document.document_segments
                for occurrence in segment.source_occurrences
            },
            {first.record.screen_id},
        )
        self.assertNotEqual(failed.record.screen_id, first.record.screen_id)
        self.assertEqual(
            document.candidate_record_id,
            store.screens[0].candidate_record_id,
        )
        self.assertEqual(
            document.candidate_record_id,
            builder.candidate_record_id,
        )
        self.assertTrue(builder.finalized)

    def test_record_validation_error_writes_only_sanitized_diagnostics(self):
        store = FakeStore()
        builder = self.start_builder(store)
        private_text = "PRIVATE OCR BODY MUST NOT APPEAR"

        with patch.object(
            builder,
            "build_screen_record",
            side_effect=ValueError(
                "aggregation segment classifications are invalid"
            ),
        ):
            result = simple_brush.record_detection_observation(
                self.observation(private_text),
                CaptureType.FORMAL_SCREEN,
                True,
                2,
            )

        self.assertFalse(result.saved)
        self.assertEqual(result.failure_stage, "screen_record_validation")
        self.assertEqual(
            result.validation_code, "r05_segment_partition_invalid",
        )
        self.assertEqual(len(store.errors), 1)
        error_type, operation, context = store.errors[0]
        self.assertEqual(error_type, "ValueError")
        self.assertEqual(operation, "record_ocr_observation")
        self.assertEqual(
            context["failure_stage"], "screen_record_validation",
        )
        self.assertEqual(
            context["sanitized_error_message"],
            "aggregation segment classifications are invalid",
        )
        self.assertNotIn(private_text, repr(context))
        self.assertEqual(builder.retained_screen_count, 0)

    def test_formal_slots_build_classify_and_save_one_canonical_record_once(self):
        store = FakeStore()
        builder = self.start_builder(store)
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [
            OCRItem(
                "同一视觉位置的完整候选人内容用于通过既有加载健康阈值并保持足够长的文本", 0.99,
                ((0, 0), (20, 0), (20, 10), (0, 10)),
            )
        ]
        scroll = Mock()
        wait = Mock()
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=Mock(),
            max_scans=2,
            scroll=scroll,
            wait=wait,
            observation_callback=simple_brush.record_detection_observation,
        )
        simple_brush.ocr_detector = detector

        with patch.object(
            builder, "build_screen_record", wraps=builder.build_screen_record,
        ) as build, patch.object(
            detector, "_match_observation", wraps=detector._match_observation,
        ) as rule, patch(
            "simple_brush.classify_position", wraps=simple_brush.classify_position,
        ) as classify, patch.object(
            store, "save_screen", wraps=store.save_screen,
        ) as save:
            result = detector.detect(simple_brush.parse_keyword_rules('"不存在"'))

        self.assertFalse(result.confirmed_match)
        self.assertEqual(capture.calls, 2)
        self.assertEqual(rule.call_count, 2)
        self.assertEqual(build.call_count, 2)
        self.assertEqual(classify.call_count, 2)
        self.assertEqual(save.call_count, 2)
        scroll.assert_called_once()
        self.assertEqual(
            [record.capture_type for record in store.screens],
            [CaptureType.FORMAL_SCREEN, CaptureType.FORMAL_SCREEN],
        )
        self.assertEqual(
            [record.position_status for record in store.screens],
            ["initial", "same"],
        )
        self.assertEqual(store.screens[1].reference_screen_id, store.screens[0].screen_id)
        self.assertIs(builder._screens[0], store.screens[0])
        self.assertIs(builder._screens[1], store.screens[1])
        self.assertTrue(detector.last_observation_result.saved)
        self.assertEqual(detector.dynamic_end_state.scan_slot_count, 2)
        self.assertEqual(detector.dynamic_end_state.normal_scroll_count, 1)
        self.assertEqual(detector.dynamic_end_state.ocr_attempt_count, 2)
        self.assertEqual(detector.dynamic_end_state.unique_position_count, 1)

    @staticmethod
    def _recovery_item(text):
        return OCRItem(
            text,
            0.99,
            ((0, 0), (320, 0), (320, 20), (0, 20)),
        )

    def _run_recovery_detector(self, *, mode, texts, max_scans, store=None):
        store = FakeStore() if store is None else store
        self.start_builder(store)
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.side_effect = [
            [self._recovery_item(text)] for text in texts
        ]
        scroll = Mock()
        wait = Mock()
        restore_focus = Mock(return_value=True)
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=Mock(),
            max_scans=max_scans,
            scroll=scroll,
            wait=wait,
            observation_callback=simple_brush.record_detection_observation,
            dynamic_end_config=DynamicEndConfig(mode=mode),
            restore_focus=restore_focus,
        )
        simple_brush.ocr_detector = detector
        result = detector.detect(simple_brush.parse_keyword_rules('"不存在"'))
        return store, capture, scroll, wait, restore_focus, detector, result

    def _run_complete_scan_detector(self, *, mode, texts, max_scans):
        store = FakeStore()
        self.start_builder(store)
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.side_effect = [
            [self._recovery_item(text)] for text in texts
        ]
        scroll = Mock()
        wait = Mock()
        restore_focus = Mock(return_value=True)
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=Mock(),
            max_scans=max_scans,
            scroll=scroll,
            wait=wait,
            observation_callback=simple_brush.record_detection_observation,
            dynamic_end_config=DynamicEndConfig(mode=mode),
            restore_focus=restore_focus,
        )
        simple_brush.ocr_detector = detector
        result = detector.scan_candidate()
        status, end_reason = simple_brush.candidate_capture_status(result)
        document = simple_brush.finalize_current_candidate_recording(
            status,
            end_reason,
            detection_result=result,
        )
        return (
            store,
            capture,
            scroll,
            wait,
            restore_focus,
            detector,
            result,
            document,
        )

    def test_shadow_and_off_keep_first_same_recovery_side_effect_free(self):
        for mode in ("off", "shadow"):
            with self.subTest(mode=mode):
                store, capture, scroll, wait, restore, detector, result = (
                    self._run_recovery_detector(
                        mode=mode,
                        texts=("足够长的同一视觉位置内容用于保持加载健康" * 2,) * 2,
                        max_scans=2,
                    )
                )
                self.assertFalse(result.scroll_bottom_candidate)
                restore.assert_not_called()
                self.assertEqual(capture.calls, 2)
                self.assertEqual(scroll.call_count, 1)
                self.assertEqual(wait.call_count, 1)
                self.assertEqual(detector.dynamic_end_state.focus_restore_count, 0)
                self.assertEqual(detector.dynamic_end_state.scroll_retry_count, 0)
                self.assertFalse(detector.dynamic_end_state.recovery_used)
                self.assertNotIn(
                    CaptureType.POSITION_CONFIRMATION,
                    [record.capture_type for record in store.screens],
                )

    def test_shadow_candidate_summary_projects_nullable_prediction_fields(self):
        same_text = "足够长的同一视觉位置内容用于保持加载健康" * 2
        store, _capture, _scroll, _wait, _restore, _detector, result = (
            self._run_recovery_detector(
                mode="shadow", texts=(same_text,) * 3, max_scans=3,
            )
        )
        document = simple_brush.finalize_current_candidate_recording(
            CaptureStatus.COMPLETED,
            "existing_flow_completed",
            detection_result=result,
        )

        self.assertEqual(document.dynamic_end_mode, "shadow")
        self.assertIsNone(document.dynamic_end_reason)
        self.assertEqual(document.first_predicted_end_screen, 2)
        self.assertEqual(document.first_predicted_end_reason, "possible_scroll_bottom")
        self.assertIsNone(document.prediction_would_miss_content)
        self.assertFalse(document.prediction_would_miss_rule_match)
        self.assertTrue(document.prediction_observation_complete)
        self.assertFalse(document.prediction_evidence_complete)
        self.assertEqual(document.versions["dynamic_end"], "r07-v1")
        self.assertIs(store.candidates[0], document)
        restored = CandidateOcrDocument.from_dict(document.to_dict())
        self.assertEqual(restored.first_predicted_end_screen, 2)
        self.assertIsNone(restored.prediction_would_miss_content)

    def test_shadow_store_failure_keeps_legacy_scan_and_invalidates_false_conclusions(self):
        same_text = "足够长的同一视觉位置内容用于保持加载健康" * 2
        store = FakeStore()
        original_save_screen = store.save_screen
        save_count = 0

        def save_screen(record):
            nonlocal save_count
            save_count += 1
            was_failed = store.fail_screens
            store.fail_screens = save_count == 3
            try:
                return original_save_screen(record)
            finally:
                store.fail_screens = was_failed

        store.save_screen = Mock(side_effect=save_screen)
        _store, capture, scroll, wait, restore, detector, result = (
            self._run_recovery_detector(
                mode="shadow", texts=(same_text,) * 3, max_scans=3, store=store,
            )
        )

        self.assertEqual(store.save_screen.call_count, 3)
        self.assertEqual(capture.calls, 3)
        self.assertEqual(scroll.call_count, 2)
        self.assertEqual(wait.call_count, 2)
        restore.assert_not_called()
        self.assertEqual(detector.dynamic_end_state.scan_slot_count, 3)
        self.assertIsNone(result.prediction_would_miss_content)
        self.assertIsNone(result.prediction_would_miss_rule_match)
        self.assertFalse(result.prediction_evidence_complete)

    def test_shadow_detector_never_enters_upper_action_finalize_next_or_refresh_flow(self):
        same_text = "足够长的同一视觉位置内容用于保持加载健康" * 2
        with patch.object(simple_brush, "perform_favorite_action") as action, \
             patch.object(simple_brush, "finalize_current_candidate_recording") as finalize, \
             patch.object(simple_brush, "next_candidate") as next_candidate, \
             patch.object(simple_brush, "refresh_page") as refresh:
            self._run_recovery_detector(
                mode="shadow", texts=(same_text,) * 3, max_scans=3,
            )

        action.assert_not_called()
        finalize.assert_not_called()
        next_candidate.assert_not_called()
        refresh.assert_not_called()

    def test_safe_first_same_returns_confirmed_bottom_once(self):
        same_text = "足够长的同一视觉位置内容用于保持加载健康" * 2
        store, capture, scroll, wait, restore, detector, result = (
            self._run_recovery_detector(
                mode="safe", texts=(same_text,) * 3, max_scans=3,
            )
        )

        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.dynamic_end_reason, "scroll_bottom")
        self.assertTrue(result.scroll_bottom_candidate)
        self.assertEqual(capture.calls, 3)
        self.assertEqual(scroll.call_count, 2)  # 1 normal + 1 retry
        self.assertEqual(wait.call_count, 2)  # normal settle + confirmation settle
        restore.assert_called_once()
        self.assertEqual(
            [record.capture_type for record in store.screens],
            [
                CaptureType.FORMAL_SCREEN,
                CaptureType.FORMAL_SCREEN,
                CaptureType.POSITION_CONFIRMATION,
            ],
        )
        self.assertTrue(store.screens[2].is_position_confirmation)
        self.assertEqual(store.screens[2].position_status, "same")
        self.assertEqual(detector.dynamic_end_state.scan_slot_count, 2)
        self.assertEqual(detector.dynamic_end_state.unique_position_count, 1)
        self.assertEqual(detector.dynamic_end_state.ocr_attempt_count, 3)
        self.assertEqual(detector.dynamic_end_state.normal_scroll_count, 1)
        self.assertEqual(detector.dynamic_end_state.focus_restore_count, 1)
        self.assertEqual(detector.dynamic_end_state.scroll_retry_count, 1)
        self.assertEqual(
            simple_brush.candidate_capture_status(result),
            (CaptureStatus.COMPLETED_WITH_LIMIT, "scroll_bottom"),
        )

    def test_complete_scan_collects_later_screens_into_existing_candidate_document(self):
        same_text = "Python 命中样式文本仍应作为完整候选人证据继续采集" * 2
        (
            store,
            capture,
            scroll,
            wait,
            restore,
            detector,
            result,
            document,
        ) = self._run_complete_scan_detector(
            mode="safe",
            texts=(same_text,) * 3,
            max_scans=3,
        )

        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)
        self.assertEqual(result.dynamic_end_reason, "scroll_bottom")
        self.assertEqual(capture.calls, 3)
        self.assertEqual(scroll.call_count, 2)
        self.assertEqual(wait.call_count, 2)
        restore.assert_called_once()
        self.assertEqual([record.capture_type for record in store.screens], [
            CaptureType.FORMAL_SCREEN,
            CaptureType.FORMAL_SCREEN,
            CaptureType.POSITION_CONFIRMATION,
        ])
        self.assertNotIn(
            "rule_confirmation",
            [record.capture_type.value for record in store.screens],
        )
        self.assertIsInstance(document, CandidateOcrDocument)
        self.assertEqual(document.screens, tuple(store.screens))
        self.assertEqual(document.capture_status, CaptureStatus.COMPLETED_WITH_LIMIT)
        self.assertEqual(document.capture_summary.end_reason, "scroll_bottom")
        self.assertEqual(document.dynamic_end_reason, "scroll_bottom")
        self.assertTrue(all(
            observation.matched_rule is None
            and observation.rule_comparison is None
            for observation in result.observations
        ))
        self.assertEqual(detector.dynamic_end_state.ocr_attempt_count, 3)

    def test_complete_scan_preserves_existing_completion_reason_projection(self):
        normal_text = "Python 形式的普通完整证据不会触发业务提前结束" * 2
        (
            _normal_store,
            _normal_capture,
            _normal_scroll,
            _normal_wait,
            _normal_restore,
            _normal_detector,
            normal_result,
            normal_document,
        ) = self._run_complete_scan_detector(
            mode="safe",
            texts=(normal_text,) * 3,
            max_scans=3,
        )
        limit_texts = tuple(
            "第{0}个不同的完整候选人页面证据".format(index) * 3
            for index in range(1, 3)
        )
        (
            _limit_store,
            limit_capture,
            limit_scroll,
            _limit_wait,
            limit_restore,
            _limit_detector,
            limit_result,
            limit_document,
        ) = self._run_complete_scan_detector(
            mode="safe",
            texts=limit_texts,
            max_scans=2,
        )

        self.assertEqual(normal_result.dynamic_end_reason, "scroll_bottom")
        self.assertEqual(
            normal_document.capture_summary.end_reason,
            "scroll_bottom",
        )
        self.assertEqual(normal_document.dynamic_end_reason, "scroll_bottom")
        self.assertEqual(limit_result.dynamic_end_reason, "max_screen_limit")
        self.assertEqual(
            limit_document.capture_summary.end_reason,
            "max_screen_limit",
        )
        self.assertEqual(limit_document.dynamic_end_reason, "max_screen_limit")
        self.assertNotEqual(
            normal_document.capture_summary.end_reason,
            limit_document.capture_summary.end_reason,
        )
        self.assertEqual(limit_capture.calls, 2)
        limit_scroll.assert_called_once()
        limit_restore.assert_not_called()

    def test_full_scroll_bottom_finalizes_completed_with_limit_candidate(self):
        same_text = "Full 配置滚动到底的合成候选人内容" * 3
        store, _capture, _scroll, _wait, _restore, _detector, result = (
            self._run_recovery_detector(
                mode="full", texts=(same_text,) * 3, max_scans=3,
            )
        )
        status, end_reason = simple_brush.candidate_capture_status(result)
        document = simple_brush.finalize_current_candidate_recording(
            status, end_reason, detection_result=result,
        )

        self.assertEqual(status, CaptureStatus.COMPLETED_WITH_LIMIT)
        self.assertEqual(end_reason, "scroll_bottom")
        self.assertEqual(document.capture_status, CaptureStatus.COMPLETED_WITH_LIMIT)
        self.assertEqual(document.dynamic_end_mode, "full")
        self.assertEqual(document.dynamic_end_reason, "scroll_bottom")
        self.assertEqual(len(document.screens), 3)
        self.assertEqual(
            sum(screen.is_position_confirmation is True for screen in document.screens),
            1,
        )
        self.assertTrue(all(
            screen.candidate_record_id == document.candidate_record_id
            for screen in store.screens
        ))
        self.assertEqual(store.candidates, [document])

    def test_full_two_healthy_changed_no_new_screens_finalize_candidate(self):
        base_segments = tuple(
            "合成历史片段 {0}，长度足够用于稳定边界匹配".format(index) * 2
            for index in range(8)
        )
        pages = (base_segments, base_segments[1:], base_segments[2:])

        class SegmentBackend:
            def __init__(self, values):
                self.values = values
                self.calls = 0

            def recognize(self, _image):
                values = self.values[self.calls]
                self.calls += 1
                return tuple(
                    OCRItem(
                        text, 0.99,
                        ((0, index * 30), (240, index * 30),
                         (240, index * 30 + 20), (0, index * 30 + 20)),
                    )
                    for index, text in enumerate(values)
                )

        store = FakeStore()
        self.start_builder(store)
        backend = SegmentBackend(pages)
        scroll = Mock()
        detector = OCRKeywordDetector(
            backend=backend,
            capture=FakeCapture(),
            region=Mock(),
            max_scans=8,
            scroll=scroll,
            wait=Mock(),
            observation_callback=simple_brush.record_detection_observation,
            dynamic_end_config=DynamicEndConfig(mode="full"),
            restore_focus=Mock(return_value=True),
        )
        simple_brush.ocr_detector = detector

        result = detector.detect(simple_brush.parse_keyword_rules('"不存在"'))
        status, end_reason = simple_brush.candidate_capture_status(result)
        document = simple_brush.finalize_current_candidate_recording(
            status, end_reason, detection_result=result,
        )

        self.assertEqual(backend.calls, 3)
        self.assertEqual(scroll.call_count, 2)
        self.assertEqual(result.dynamic_end_reason, "no_new_text")
        self.assertEqual(status, CaptureStatus.COMPLETED_WITH_LIMIT)
        self.assertEqual(end_reason, "no_new_text")
        self.assertEqual(
            [screen.position_status for screen in document.screens],
            ["initial", "changed", "changed"],
        )
        for screen in document.screens[1:]:
            self.assertEqual(screen.aggregation_status.value, "completed")
            self.assertEqual(
                screen.similarity_result.similarity_status.value, "completed",
            )
            self.assertEqual(
                screen.similarity_result.effective_new_status.value, "none",
            )
            self.assertFalse(screen.similarity_result.has_effective_new_text)
            self.assertEqual(screen.similarity_result.effective_new_segment_count, 0)
            self.assertEqual(screen.similarity_result.possible_new_segment_count, 0)
            self.assertEqual(screen.uncertain_segment_ids, ())
        self.assertEqual(document.dynamic_end_mode, "full")
        self.assertEqual(document.dynamic_end_reason, "no_new_text")
        self.assertEqual(document.capture_status, CaptureStatus.COMPLETED_WITH_LIMIT)
        self.assertEqual(store.candidates, [document])

    def test_confirmation_store_failure_is_not_a_bottom_candidate_or_retry(self):
        same_text = "足够长的同一视觉位置内容用于保持加载健康" * 2
        store = FakeStore()
        original_save_screen = store.save_screen
        save_count = 0

        def save_screen(record):
            nonlocal save_count
            save_count += 1
            was_failed = store.fail_screens
            store.fail_screens = save_count == 3  # confirmation only
            try:
                return original_save_screen(record)
            finally:
                store.fail_screens = was_failed

        store.save_screen = Mock(side_effect=save_screen)
        store, capture, scroll, wait, restore, detector, result = (
            self._run_recovery_detector(
                mode="safe", texts=(same_text,) * 4, max_scans=3, store=store,
            )
        )

        self.assertEqual(store.save_screen.call_count, 3)
        self.assertEqual(capture.calls, 3)
        self.assertEqual(scroll.call_count, 2)
        self.assertEqual(wait.call_count, 2)
        restore.assert_called_once()
        self.assertFalse(result.scroll_bottom_candidate)
        self.assertEqual(result.abort_reason, "store_failed")
        self.assertEqual(result.recovery_reason, "store_failed")
        self.assertEqual(detector.dynamic_end_state.scroll_retry_count, 1)

    def test_recovery_never_invokes_page_lifecycle_or_next(self):
        same_text = "足够长的同一视觉位置内容用于保持加载健康" * 2
        with patch.object(simple_brush, "run_detail_load_gate", side_effect=AssertionError("P0")), \
             patch.object(simple_brush, "confirm_candidate_switch", side_effect=AssertionError("R01")), \
             patch.object(simple_brush, "next_candidate", side_effect=AssertionError("next")):
            self._run_recovery_detector(
                mode="safe", texts=(same_text,) * 4, max_scans=3,
            )

    def test_changed_confirmation_is_promoted_once_and_eighth_same_does_not_recover(self):
        first = "第一段足够长的内容用于保持加载健康" * 2
        changed = "第二段不同且足够长的内容用于保持加载健康" * 2
        later = "第三段不同且足够长的内容用于保持加载健康" * 2
        store, capture, scroll, wait, restore, detector, _result = (
            self._run_recovery_detector(
                mode="full", texts=(first, first, changed, later), max_scans=4,
            )
        )
        self.assertEqual(capture.calls, 4)
        self.assertEqual(scroll.call_count, 3)  # slot 2, retry, slot 4
        self.assertEqual(wait.call_count, 3)
        restore.assert_called_once()
        self.assertEqual(
            [record.capture_type for record in store.screens],
            [CaptureType.FORMAL_SCREEN] * 4,
        )
        self.assertEqual(store.screens[2].screen_index, 3)
        self.assertEqual(store.screens[2].position_status, "changed")
        self.assertEqual(detector.dynamic_end_state.scan_slot_count, 4)
        self.assertEqual(detector.dynamic_end_state.unique_position_count, 3)

        values = tuple(
            "第{0}段不同且足够长的内容用于保持加载健康".format(index) * 2
            for index in range(1, 8)
        )
        eighth_store, eighth_capture, eighth_scroll, eighth_wait, eighth_restore, eighth_detector, eighth_result = (
            self._run_recovery_detector(
                mode="safe", texts=values + (values[-1],), max_scans=8,
            )
        )
        self.assertEqual(eighth_capture.calls, 8)
        self.assertEqual(eighth_scroll.call_count, 7)
        self.assertEqual(eighth_wait.call_count, 7)
        eighth_restore.assert_not_called()
        self.assertEqual(eighth_detector.dynamic_end_state.focus_restore_count, 0)
        self.assertEqual(eighth_detector.dynamic_end_state.scroll_retry_count, 0)
        self.assertEqual(eighth_detector.dynamic_end_state.scan_slot_count, 8)
        self.assertEqual(eighth_store.screens[-1].position_status, "same")
        self.assertEqual(eighth_result.dynamic_end_reason, "max_screen_limit")
        self.assertEqual(
            simple_brush.candidate_capture_status(eighth_result),
            (CaptureStatus.COMPLETED_WITH_LIMIT, "max_screen_limit"),
        )

    def test_normalizer_failure_keeps_raw_screen_and_does_not_add_page_calls(self):
        store = FakeStore()
        self.start_builder(store)
        capture = FakeCapture()
        backend = Mock()
        backend.recognize.return_value = [
            OCRItem(
                "PRIVATE_SYNTHETIC_BODY Python",
                0.99,
                ((0, 0), (20, 0), (20, 10), (0, 10)),
            )
        ]
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=Mock(),
            wait=Mock(),
        )

        with patch(
            "ocr_detector.normalize_ocr_text",
            side_effect=RuntimeError("PRIVATE_SYNTHETIC_BODY"),
        ) as normalizer:
            observation = detector.capture_observation(1)
            record = simple_brush.record_ocr_observation(
                observation,
                CaptureType.LOAD_CHECK,
                False,
                None,
            )

        normalizer.assert_called_once()
        self.assertEqual(capture.calls, 1)
        self.assertEqual(backend.recognize.call_count, 1)
        self.assertEqual(len(store.screens), 1)
        self.assertIs(record, store.screens[0])
        self.assertEqual(record.raw_boxes[0].raw_text, "PRIVATE_SYNTHETIC_BODY Python")
        self.assertEqual(record.normalization_status.value, "failed")
        self.assertEqual(record.normalization_error_type, "RuntimeError")
        self.assertIsNone(record.normalized_text)
        self.assertIsNone(record.comparison_text)
        self.assertEqual(record.rule_evaluation_mode, "legacy_shadow")
        self.assertIsNone(record.legacy_match)
        self.assertIsNone(record.r04_match)
        self.assertIsNone(record.comparison_outcome)

    def test_failed_normalization_shadow_is_saved_without_extra_page_calls(self):
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
        wait = Mock()
        detector = OCRKeywordDetector(
            backend=backend,
            capture=capture,
            region=Mock(),
            max_scans=1,
            wait=wait,
            observation_callback=simple_brush.record_detection_observation,
        )

        with patch(
            "ocr_detector.normalize_ocr_text",
            side_effect=RuntimeError("PRIVATE_SYNTHETIC_BODY"),
        ) as normalizer:
            result = detector.detect(simple_brush.parse_keyword_rules('"Python"'))

        self.assertTrue(result.confirmed_match)
        self.assertEqual(capture.calls, 2)
        self.assertEqual(backend.recognize.call_count, 2)
        self.assertEqual(normalizer.call_count, 2)
        self.assertEqual(wait.call_count, 1)
        self.assertEqual(len(store.screens), 2)
        for record in store.screens:
            self.assertEqual(record.rule_evaluation_mode, "legacy_shadow")
            self.assertTrue(record.legacy_match)
            self.assertIsNone(record.r04_match)
            self.assertEqual(
                record.comparison_outcome,
                "normalization_failed",
            )
            self.assertEqual(record.legacy_rule_index, 0)
            self.assertIsNone(record.r04_rule_index)

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
        self.assertEqual(document.screens, (store.screens[0],))
        self.assertEqual(
            document.screens[0].normalization_version,
            "r04-v1",
        )
        self.assertIsNotNone(document.screens[0].comparison_text)
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
            patch.object(simple_brush, "ScreeningProfileStore") as profile_store,
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
            profile_store.return_value.load_latest.return_value = (
                self.screening_profile_version
            )
            result = simple_brush.run(
                screening_profile_id=self.screening_profile_id
            )
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
            patch.object(simple_brush, "ScreeningProfileStore") as profile_store,
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
            profile_store.return_value.load_latest.return_value = (
                self.screening_profile_version
            )
            result = simple_brush.run(
                screening_profile_id=self.screening_profile_id
            )

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

    def test_disabled_initial_store_stops_before_hard_recovery_business_calls(self):
        disabled_store = FakeStore(enabled=False)

        calls = self.run_hard_recovery(disabled_store)

        self.assertNotEqual(calls["result"], 0)
        self.assertEqual(
            self.recovery_business_call_counts(calls),
            {
                "gate": 0,
                "open_first": 0,
                "refresh": 0,
                "reopen": 0,
                "recover": 0,
                "view": 0,
                "wait": 0,
                "next_candidate": 0,
                "ocr_scroll": 0,
                "human_scroll": 0,
            },
        )
        self.assertIsNone(calls["facts"].get("old_builder"))
        self.assertIsNone(calls["facts"].get("new_builder"))
        self.assertEqual(disabled_store.candidate_attempts, [])
        self.assertIsNone(disabled_store.closed_status)

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
        self.assertEqual(
            store.candidate_owner_attempts,
            [document.candidate_record_id],
        )
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

    def test_disabled_initial_store_stops_before_listener_browser_or_view(self):
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

        self.assertEqual(enabled_result, 0)
        self.assertNotEqual(disabled_result, 0)
        self.assertEqual(enabled_view.call_count, 1)
        self.assertEqual(disabled_view.call_count, 0)
        self.assertEqual(len(enabled.candidates), 1)
        self.assertEqual(enabled.candidates[0].capture_status, CaptureStatus.COMPLETED)
        self.assertEqual(len(disabled.candidates), 0)
        self.assertEqual(enabled.closed_status, RunStatus.INTERRUPTED)
        self.assertIsNone(disabled.closed_status)

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
