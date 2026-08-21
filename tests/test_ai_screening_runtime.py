from dataclasses import fields
import inspect
import json
import unittest
from unittest.mock import patch

import ai_screening_runtime
from ai_candidate_input import build_ai_candidate_input
from ai_provider_config import AIProviderConfig
from ai_screening_contract import AIScreeningContractError
from ai_screening_prompt import build_ai_screening_prompt
from ai_screening_runtime import AIScreeningResult, run_ai_screening
from llm_provider_runtime import (
    LLMCompletionResult,
    LLMMessageRole,
    LLMOperation,
    LLMRuntimeError,
    LLMRuntimeErrorCode,
)
from ocr_candidate import CandidateOcrBuilder
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_records import CandidateOcrDocument, CaptureStatus, CaptureType
from ocr_text import OCRItem
from screening_profile import Criterion, ScreeningProfileVersion, criteria_digest


class AIScreeningRuntimeTests(unittest.TestCase):
    def make_candidate(
        self,
        texts=("Candidate evidence",),
        *,
        candidate_record_id="candidate-r11",
        aggregation_mode="record",
    ):
        builder = CandidateOcrBuilder(
            "run-r11",
            1,
            candidate_record_id=candidate_record_id,
            created_at="2026-08-22T12:00:00+00:00",
            metadata={},
            aggregation_mode=aggregation_mode,
            similarity_mode="disabled",
        )
        for index, text in enumerate(texts, start=1):
            screen_id = "screen-r11-{0}".format(index)
            item = OCRItem(
                text,
                0.99,
                ((0, 0), (240, 0), (240, 20), (0, 20)),
            )
            normalization = normalize_ocr_text((NormalizationBox(
                "{0}:box:0".format(screen_id),
                item.text,
                item.box,
                0,
                item.confidence,
            ),))
            builder.build_screen_record(
                (item,),
                capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True,
                screen_index=index,
                screen_id=screen_id,
                captured_at="2026-08-22T12:00:{0:02d}+00:00".format(index),
                normalization=normalization,
                ocr_min_confidence=0.85,
            )
        return builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
            completed_at="2026-08-22T12:01:00+00:00",
        )

    def make_missing_text_candidate(self):
        return self.make_candidate(
            ("Screen evidence must not become fallback text",),
            aggregation_mode="disabled",
        )

    def make_profile(self):
        criteria = (
            Criterion("C001", "First Criterion"),
            Criterion("C002", "Second Criterion"),
            Criterion("C003", "Third Criterion"),
        )
        return ScreeningProfileVersion(
            screening_profile_id="sp_" + "a" * 32,
            profile_version=1,
            criteria=criteria,
            criteria_digest=criteria_digest(criteria),
            created_at="2026-08-22T12:00:00+00:00",
        )

    def make_config(self):
        return AIProviderConfig()

    def make_completion(self, content):
        return LLMCompletionResult(
            content=content,
            provider="qwen",
            model="qwen-test",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            finish_reason=None,
            request_id=None,
        )

    def raw_response(self, pairs):
        return json.dumps({
            "criteria_results": [
                {"criterion_id": criterion_id, "passed": passed}
                for criterion_id, passed in pairs
            ],
        })

    def mixed_pairs(self):
        return (("C001", True), ("C002", False), ("C003", True))

    def test_completed_mixed_result_preserves_identity_and_provider_request(self):
        candidate = self.make_candidate(candidate_record_id="candidate-private-r11")
        profile = self.make_profile()
        config = self.make_config()
        completion = self.make_completion(self.raw_response(self.mixed_pairs()))
        projected = build_ai_candidate_input(candidate)
        prompt = build_ai_screening_prompt(projected, profile)

        with patch(
            "ai_screening_runtime.complete",
            return_value=completion,
        ) as complete_mock:
            result = run_ai_screening(candidate, profile, config)

        self.assertEqual(
            result,
            AIScreeningResult(
                "candidate-private-r11",
                "completed",
                {"C001": True, "C002": False, "C003": True},
            ),
        )
        self.assertEqual(candidate.candidate_record_id, projected.candidate_record_id)
        self.assertEqual(projected.candidate_record_id, result.candidate_record_id)
        complete_mock.assert_called_once()
        supplied_config, request = complete_mock.call_args.args
        self.assertIs(supplied_config, config)
        self.assertEqual(len(request.messages), 2)
        self.assertEqual(
            [message.role for message in request.messages],
            [LLMMessageRole.SYSTEM, LLMMessageRole.USER],
        )
        self.assertEqual(request.messages[0].content, prompt.system_message)
        self.assertEqual(request.messages[1].content, prompt.user_message)
        self.assertNotIn(
            candidate.candidate_record_id,
            "".join(message.content for message in request.messages),
        )

    def test_all_true_and_all_false_are_completed_results(self):
        candidate = self.make_candidate()
        profile = self.make_profile()
        config = self.make_config()
        all_true = self.make_completion(self.raw_response((
            ("C001", True), ("C002", True), ("C003", True),
        )))
        all_false = self.make_completion(self.raw_response((
            ("C001", False), ("C002", False), ("C003", False),
        )))

        with patch(
            "ai_screening_runtime.complete",
            side_effect=(all_true, all_false),
        ) as complete_mock:
            true_result = run_ai_screening(candidate, profile, config)
            false_result = run_ai_screening(candidate, profile, config)

        self.assertEqual(true_result.ai_status, "completed")
        self.assertEqual(
            true_result.criteria_results,
            {"C001": True, "C002": True, "C003": True},
        )
        self.assertEqual(false_result.ai_status, "completed")
        self.assertEqual(
            false_result.criteria_results,
            {"C001": False, "C002": False, "C003": False},
        )
        self.assertEqual(complete_mock.call_count, 2)

    def test_multiple_criteria_and_multiple_screens_still_make_one_call(self):
        candidate = self.make_candidate(("First screen", "Second screen"))
        profile = self.make_profile()
        completion = self.make_completion(self.raw_response(self.mixed_pairs()))

        with patch(
            "ai_screening_runtime.complete",
            return_value=completion,
        ) as complete_mock:
            result = run_ai_screening(candidate, profile, self.make_config())

        self.assertIn("\n", candidate.document_text)
        self.assertEqual(result.ai_status, "completed")
        complete_mock.assert_called_once()

    def test_r09_value_error_returns_failed_without_provider_call(self):
        candidate = self.make_missing_text_candidate()
        self.assertIsNone(candidate.document_text)
        self.assertTrue(candidate.screens)

        with patch("ai_screening_runtime.complete") as complete_mock:
            result = run_ai_screening(
                candidate,
                self.make_profile(),
                self.make_config(),
            )

        self.assertEqual(result.candidate_record_id, candidate.candidate_record_id)
        self.assertEqual(result.ai_status, "failed")
        self.assertIsNone(result.criteria_results)
        complete_mock.assert_not_called()

    def test_llm_runtime_error_returns_failed_after_one_provider_call(self):
        candidate = self.make_candidate()
        runtime_error = LLMRuntimeError(
            code=LLMRuntimeErrorCode.NETWORK,
            provider="qwen",
            operation=LLMOperation.COMPLETE,
            message="network failure",
        )

        with patch(
            "ai_screening_runtime.complete",
            side_effect=runtime_error,
        ) as complete_mock:
            result = run_ai_screening(
                candidate,
                self.make_profile(),
                self.make_config(),
            )

        self.assertEqual(result.candidate_record_id, candidate.candidate_record_id)
        self.assertEqual(result.ai_status, "failed")
        self.assertIsNone(result.criteria_results)
        complete_mock.assert_called_once()

    def test_contract_failures_return_failed_without_synthetic_or_partial_mapping(self):
        candidate = self.make_candidate()
        profile = self.make_profile()
        invalid_completion = self.make_completion(self.raw_response((
            ("C001", True),
            ("C002", False),
        )))

        with patch(
            "ai_screening_runtime.complete",
            return_value=invalid_completion,
        ) as complete_mock:
            result = run_ai_screening(candidate, profile, self.make_config())

        self.assertEqual(result.ai_status, "failed")
        self.assertIsNone(result.criteria_results)
        complete_mock.assert_called_once()

    def test_explicit_contract_error_boundary_returns_failed(self):
        candidate = self.make_candidate()
        completion = self.make_completion(self.raw_response(self.mixed_pairs()))

        with patch(
            "ai_screening_runtime.complete",
            return_value=completion,
        ) as complete_mock, patch(
            "ai_screening_runtime.validate_ai_screening_response",
            side_effect=AIScreeningContractError("invalid response"),
        ):
            result = run_ai_screening(
                candidate,
                self.make_profile(),
                self.make_config(),
            )

        self.assertEqual(result.ai_status, "failed")
        self.assertIsNone(result.criteria_results)
        complete_mock.assert_called_once()

    def test_entry_type_and_invalid_source_identity_errors_propagate(self):
        candidate = self.make_candidate()
        profile = self.make_profile()
        config = self.make_config()

        with patch("ai_screening_runtime.complete") as complete_mock:
            with self.assertRaises(TypeError):
                run_ai_screening({}, profile, config)
            with self.assertRaises(TypeError):
                run_ai_screening(candidate, {}, config)
            with self.assertRaises(TypeError):
                run_ai_screening(candidate, profile, {})
            object.__setattr__(candidate, "candidate_record_id", 123)
            with self.assertRaisesRegex(
                ValueError,
                "^candidate\\.candidate_record_id must be a string$",
            ):
                run_ai_screening(candidate, profile, config)

        complete_mock.assert_not_called()

    def test_result_constructor_has_only_frozen_state_invariants(self):
        mapping = {"C001": True}
        completed = AIScreeningResult("candidate-r11", "completed", mapping)
        failed = AIScreeningResult("candidate-r11", "failed", None)

        self.assertIs(completed.criteria_results, mapping)
        self.assertIsNone(failed.criteria_results)
        self.assertEqual(
            [field.name for field in fields(AIScreeningResult)],
            ["candidate_record_id", "ai_status", "criteria_results"],
        )
        invalid_values = (
            (1, "failed", None),
            ("candidate-r11", "completed", None),
            ("candidate-r11", "completed", {}),
            ("candidate-r11", "completed", {1: True}),
            ("candidate-r11", "completed", {"C001": 1}),
            ("candidate-r11", "failed", {"C001": True}),
            ("candidate-r11", "retry", None),
        )
        for values in invalid_values:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    AIScreeningResult(*values)

    def test_unexpected_provider_and_prompt_exceptions_propagate(self):
        candidate = self.make_candidate()
        profile = self.make_profile()
        config = self.make_config()

        with patch(
            "ai_screening_runtime.complete",
            side_effect=RuntimeError("unexpected provider error"),
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected provider error"):
                run_ai_screening(candidate, profile, config)

        with patch(
            "ai_screening_runtime.build_ai_screening_prompt",
            side_effect=RuntimeError("unexpected prompt error"),
        ) as prompt_mock, patch("ai_screening_runtime.complete") as complete_mock:
            with self.assertRaisesRegex(RuntimeError, "unexpected prompt error"):
                run_ai_screening(candidate, profile, config)

        prompt_mock.assert_called_once()
        complete_mock.assert_not_called()

    def test_validator_type_error_propagates_and_raw_content_is_unchanged(self):
        candidate = self.make_candidate()
        profile = self.make_profile()
        raw_content = " \n```json\nnot repaired\n``` \n"
        completion = self.make_completion(raw_content)

        with patch(
            "ai_screening_runtime.complete",
            return_value=completion,
        ), patch(
            "ai_screening_runtime.validate_ai_screening_response",
            side_effect=TypeError("validator integration error"),
        ):
            with self.assertRaisesRegex(TypeError, "validator integration error"):
                run_ai_screening(candidate, profile, self.make_config())

        captured = {}

        def capture_validation(*, raw_response, criteria):
            captured["raw_response"] = raw_response
            captured["criteria"] = criteria
            return {"C001": True, "C002": False, "C003": True}

        with patch(
            "ai_screening_runtime.complete",
            return_value=completion,
        ), patch(
            "ai_screening_runtime.validate_ai_screening_response",
            side_effect=capture_validation,
        ):
            result = run_ai_screening(candidate, profile, self.make_config())

        self.assertEqual(captured["raw_response"], raw_content)
        self.assertIs(captured["criteria"], profile.criteria)
        self.assertEqual(result.ai_status, "completed")

    def test_local_results_are_deterministic_without_cross_invocation_deduplication(self):
        candidate = self.make_candidate()
        profile = self.make_profile()
        config = self.make_config()
        completion = self.make_completion(self.raw_response(self.mixed_pairs()))

        with patch(
            "ai_screening_runtime.complete",
            side_effect=(completion, completion),
        ) as complete_mock:
            first = run_ai_screening(candidate, profile, config)
            second = run_ai_screening(candidate, profile, config)

        self.assertEqual(first, second)
        self.assertEqual(complete_mock.call_count, 2)

    def test_runtime_has_no_r06_or_browser_action_dependencies(self):
        source = inspect.getsource(ai_screening_runtime)

        for forbidden in (
            "screening_rule_engine",
            "evaluate_rule_set",
            "ScreeningRuleSet",
            "CandidateDecision",
            "simple_brush",
            "pyautogui",
            "favorite",
            "forward",
            "skip",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
