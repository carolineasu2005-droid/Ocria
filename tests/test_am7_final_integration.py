import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ai_screening_runtime
import simple_brush
from ai_provider_config import AIProviderConfig
from ai_screening_persistence import (
    AIPersistenceIntegrityError,
    AIScreeningRecordStore,
)
from llm_provider_runtime import (
    LLMCompletionResult,
    LLMOperation,
    LLMRuntimeError,
    LLMRuntimeErrorCode,
)
from ocr_candidate import CandidateOcrBuilder
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_records import CaptureStatus, CaptureType
from ocr_text import OCRItem
from screening_profile import Criterion, ScreeningProfileVersion, criteria_digest
from screening_rule_engine import ScreeningRule, ScreeningRuleSet


class Am7FinalIntegrationTests(unittest.TestCase):
    """Frozen R14 J01-J10 evidence through the real post-Candidate chain."""

    def setUp(self):
        self._temporary_directory = TemporaryDirectory()
        self.run_id = "run-r14-integration"
        self.profile = self._make_profile()
        self.config = AIProviderConfig(
            provider="qwen",
            api_key="synthetic-r14-api-key",
            base_url="https://provider.example.test/v1",
            model="synthetic-r14-model",
        )
        self.store = AIScreeningRecordStore(
            Path(self._temporary_directory.name),
            self.run_id,
        )
        self._saved_simple_brush_globals = (
            simple_brush.action_mode,
            simple_brush.no_forward_mode,
            simple_brush.stop_event,
            simple_brush.paused,
            simple_brush.forward_consecutive,
        )
        simple_brush.action_mode = simple_brush.ACTION_MODE_FORWARD
        simple_brush.no_forward_mode = False
        simple_brush.stop_event = False
        simple_brush.paused = False
        simple_brush.forward_consecutive = 0

    def tearDown(self):
        (
            simple_brush.action_mode,
            simple_brush.no_forward_mode,
            simple_brush.stop_event,
            simple_brush.paused,
            simple_brush.forward_consecutive,
        ) = self._saved_simple_brush_globals
        self._temporary_directory.cleanup()

    def _make_profile(self):
        criteria = (
            Criterion("C001", "Has the required technical experience."),
            Criterion("C002", "Has the required communication experience."),
        )
        return ScreeningProfileVersion(
            screening_profile_id="sp_" + "a" * 32,
            profile_version=1,
            criteria=criteria,
            criteria_digest=criteria_digest(criteria),
            created_at="2026-08-23T12:00:00+00:00",
        )

    def _make_candidate(self, candidate_record_id, sequence_number):
        builder = CandidateOcrBuilder(
            self.run_id,
            sequence_number,
            candidate_record_id=candidate_record_id,
            created_at="2026-08-23T12:00:00+00:00",
            metadata={"source": "r14-integration-test"},
            aggregation_mode="record",
            similarity_mode="disabled",
        )
        item = OCRItem(
            "Synthetic candidate resume evidence",
            0.99,
            ((0, 0), (320, 0), (320, 20), (0, 20)),
        )
        normalization = normalize_ocr_text((
            NormalizationBox(
                "screen-r14-{0}:box:0".format(sequence_number),
                item.text,
                item.box,
                0,
                item.confidence,
            ),
        ))
        builder.build_screen_record(
            (item,),
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            screen_index=1,
            screen_id="screen-r14-{0}".format(sequence_number),
            captured_at="2026-08-23T12:00:01+00:00",
            normalization=normalization,
            ocr_min_confidence=0.85,
        )
        return builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
            completed_at="2026-08-23T12:01:00+00:00",
        )

    def _completion(self, results):
        return LLMCompletionResult(
            content=json.dumps(
                {
                    "criteria_results": [
                        {"criterion_id": criterion_id, "passed": passed}
                        for criterion_id, passed in results.items()
                    ],
                },
                separators=(",", ":"),
            ),
            provider="qwen",
            model="synthetic-r14-model",
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            finish_reason=None,
            request_id="synthetic-r14-request",
        )

    def _runtime_error(self):
        return LLMRuntimeError(
            code=LLMRuntimeErrorCode.NETWORK,
            provider="qwen",
            operation=LLMOperation.COMPLETE,
            message="synthetic network failure",
        )

    def _rule_set(self, *expressions):
        return ScreeningRuleSet(
            tuple(ScreeningRule(expression) for expression in expressions)
        )

    @staticmethod
    def _read_jsonl(path):
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]

    def _process(self, candidate, rule_set):
        return simple_brush._process_finalized_candidate(
            candidate,
            self.profile,
            self.config,
            rule_set,
            self.store,
        )

    def _assert_completed_outcome(self, candidate, attempts_used):
        records = self._read_jsonl(self.store.ai_results_path)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["run_id"], self.run_id)
        self.assertEqual(record["candidate_record_id"], candidate.candidate_record_id)
        self.assertEqual(record["ai_status"], "completed")
        self.assertEqual(record["attempts_used"], attempts_used)
        self.assertEqual(
            record["criteria_results"],
            {"C001": True, "C002": True},
        )
        self.assertEqual(
            record["screening_profile_id"],
            self.profile.screening_profile_id,
        )
        self.assertEqual(record["profile_version"], self.profile.profile_version)
        self.assertEqual(record["criteria_digest"], self.profile.criteria_digest)
        self.assertEqual(record["provider"], self.config.provider)
        self.assertEqual(record["model"], self.config.model)

    def test_j01_completed_qualified_favorite_persists_before_action(self):
        candidate = self._make_candidate("candidate-r14-j01", 1)
        rule_set = self._rule_set("C001 AND C002")
        favorite_calls = []

        def observe_favorite():
            favorite_calls.append("favorite")
            self.assertEqual(len(self._read_jsonl(self.store.ai_results_path)), 1)
            decisions = self._read_jsonl(self.store.decisions_path)
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["decision_status"], "qualified")

        simple_brush.action_mode = simple_brush.ACTION_MODE_FAVORITE
        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                return_value=self._completion({"C001": True, "C002": True}),
            ) as complete,
            patch.object(
                simple_brush,
                "perform_favorite_action",
                side_effect=observe_favorite,
            ) as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            decision = self._process(candidate, rule_set)

        self.assertEqual(decision.decision_status, "qualified")
        complete.assert_called_once()
        favorite.assert_called_once_with()
        forward.assert_not_called()
        self.assertEqual(favorite_calls, ["favorite"])
        self._assert_completed_outcome(candidate, attempts_used=1)
        self.assertEqual(self._read_jsonl(self.store.ai_errors_path), [])
        decisions = self._read_jsonl(self.store.decisions_path)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["decision_status"], "qualified")

    def test_j02_completed_qualified_forward_persists_before_action(self):
        candidate = self._make_candidate("candidate-r14-j02", 1)
        rule_set = self._rule_set("C001 AND C002")
        forward_calls = []

        def observe_forward():
            forward_calls.append("forward")
            self.assertEqual(len(self._read_jsonl(self.store.ai_results_path)), 1)
            decisions = self._read_jsonl(self.store.decisions_path)
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["decision_status"], "qualified")

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                return_value=self._completion({"C001": True, "C002": True}),
            ) as complete,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(
                simple_brush,
                "forward_one_candidate",
                side_effect=observe_forward,
            ) as forward,
        ):
            decision = self._process(candidate, rule_set)

        self.assertEqual(decision.decision_status, "qualified")
        complete.assert_called_once()
        favorite.assert_not_called()
        forward.assert_called_once_with()
        self.assertEqual(forward_calls, ["forward"])
        self._assert_completed_outcome(candidate, attempts_used=1)
        self.assertEqual(
            self._read_jsonl(self.store.decisions_path)[0]["decision_status"],
            "qualified",
        )

    def test_j03_qualified_no_forward_persists_without_action_fallback(self):
        candidate = self._make_candidate("candidate-r14-j03", 1)
        rule_set = self._rule_set("C001 AND C002")
        simple_brush.no_forward_mode = True

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                return_value=self._completion({"C001": True, "C002": True}),
            ),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            decision = self._process(candidate, rule_set)

        self.assertEqual(decision.decision_status, "qualified")
        favorite.assert_not_called()
        forward.assert_not_called()
        self._assert_completed_outcome(candidate, attempts_used=1)
        self.assertEqual(
            self._read_jsonl(self.store.decisions_path)[0]["decision_status"],
            "qualified",
        )

    def test_j04_completed_rejected_returns_normally_without_action(self):
        candidate = self._make_candidate("candidate-r14-j04", 1)
        rule_set = self._rule_set("C001 AND C002")

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                return_value=self._completion({"C001": True, "C002": False}),
            ),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            decision = self._process(candidate, rule_set)

        self.assertEqual(decision.decision_status, "rejected")
        favorite.assert_not_called()
        forward.assert_not_called()
        outcomes = self._read_jsonl(self.store.ai_results_path)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["ai_status"], "completed")
        decisions = self._read_jsonl(self.store.decisions_path)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["decision_status"], "rejected")

    def test_j05_three_technical_failures_persist_ai_failed_without_r06_or_action(self):
        candidate = self._make_candidate("candidate-r14-j05", 1)
        rule_set = self._rule_set("C999")

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                side_effect=[
                    self._runtime_error(),
                    self._runtime_error(),
                    self._runtime_error(),
                ],
            ) as complete,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            decision = self._process(candidate, rule_set)

        self.assertEqual(decision.decision_status, "ai_failed")
        self.assertEqual(complete.call_count, 3)
        errors = self._read_jsonl(self.store.ai_errors_path)
        self.assertEqual([record["attempt_number"] for record in errors], [1, 2, 3])
        outcomes = self._read_jsonl(self.store.ai_results_path)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["ai_status"], "failed")
        self.assertIsNone(outcomes[0]["criteria_results"])
        self.assertEqual(outcomes[0]["attempts_used"], 3)
        decisions = self._read_jsonl(self.store.decisions_path)
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["decision_status"], "ai_failed")
        favorite.assert_not_called()
        forward.assert_not_called()
        self.assertFalse(simple_brush.stop_event)
        self.assertFalse(hasattr(simple_brush, "consecutive_ai_failures"))

    def test_j06_retry_recovery_persists_error_then_qualified_forward(self):
        candidate = self._make_candidate("candidate-r14-j06", 1)
        rule_set = self._rule_set("C001 AND C002")

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                side_effect=[
                    self._runtime_error(),
                    self._completion({"C001": True, "C002": True}),
                ],
            ) as complete,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            decision = self._process(candidate, rule_set)

        self.assertEqual(decision.decision_status, "qualified")
        self.assertEqual(complete.call_count, 2)
        favorite.assert_not_called()
        forward.assert_called_once_with()
        errors = self._read_jsonl(self.store.ai_errors_path)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["attempt_number"], 1)
        self._assert_completed_outcome(candidate, attempts_used=2)
        self.assertEqual(
            self._read_jsonl(self.store.decisions_path)[0]["decision_status"],
            "qualified",
        )

    def test_j07_final_outcome_persistence_failure_blocks_decision_and_action(self):
        candidate = self._make_candidate("candidate-r14-j07", 1)
        rule_set = self._rule_set("C999")
        failure = AIPersistenceIntegrityError(
            "write_ai_result",
            self.store.ai_results_path,
        )

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                return_value=self._completion({"C001": True, "C002": True}),
            ),
            patch.object(self.store, "append_ai_result", side_effect=failure),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            with self.assertRaises(AIPersistenceIntegrityError) as raised:
                self._process(candidate, rule_set)

        self.assertIs(raised.exception, failure)
        self.assertEqual(self._read_jsonl(self.store.ai_results_path), [])
        self.assertEqual(self._read_jsonl(self.store.decisions_path), [])
        favorite.assert_not_called()
        forward.assert_not_called()

    def test_j08_decision_persistence_failure_retains_outcome_and_blocks_action(self):
        candidate = self._make_candidate("candidate-r14-j08", 1)
        rule_set = self._rule_set("C001 AND C002")
        offered_decisions = []

        def fail_decision_write(record):
            offered_decisions.append(record)
            raise AIPersistenceIntegrityError(
                "write_decision",
                self.store.decisions_path,
            )

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                return_value=self._completion({"C001": True, "C002": True}),
            ),
            patch.object(
                self.store,
                "append_decision",
                side_effect=fail_decision_write,
            ),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            with self.assertRaises(AIPersistenceIntegrityError):
                self._process(candidate, rule_set)

        self._assert_completed_outcome(candidate, attempts_used=1)
        self.assertEqual(len(offered_decisions), 1)
        self.assertEqual(offered_decisions[0].candidate_record_id, candidate.candidate_record_id)
        self.assertEqual(offered_decisions[0].decision_status, "qualified")
        self.assertEqual(self._read_jsonl(self.store.decisions_path), [])
        favorite.assert_not_called()
        forward.assert_not_called()

    def test_j09_attempt_error_persistence_failure_stops_retry_and_downstream_work(self):
        candidate = self._make_candidate("candidate-r14-j09", 1)
        rule_set = self._rule_set("C001 AND C002")
        failure = AIPersistenceIntegrityError(
            "write_ai_error",
            self.store.ai_errors_path,
        )

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                side_effect=self._runtime_error(),
            ) as complete,
            patch.object(self.store, "append_ai_error", side_effect=failure),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            with self.assertRaises(AIPersistenceIntegrityError) as raised:
                self._process(candidate, rule_set)

        self.assertIs(raised.exception, failure)
        complete.assert_called_once()
        self.assertEqual(self._read_jsonl(self.store.ai_errors_path), [])
        self.assertEqual(self._read_jsonl(self.store.ai_results_path), [])
        self.assertEqual(self._read_jsonl(self.store.decisions_path), [])
        favorite.assert_not_called()
        forward.assert_not_called()

    def test_j10_same_run_bound_rule_set_is_shared_without_persisted_rule_identity(self):
        candidate_a = self._make_candidate("candidate-r14-j10-a", 1)
        candidate_b = self._make_candidate("candidate-r14-j10-b", 2)
        shared_rule_set = self._rule_set("C001 AND C002")
        first_rule_set = shared_rule_set
        second_rule_set = shared_rule_set
        self.assertIs(first_rule_set, second_rule_set)
        simple_brush.no_forward_mode = True

        with (
            patch.object(
                ai_screening_runtime,
                "complete",
                side_effect=[
                    self._completion({"C001": True, "C002": True}),
                    self._completion({"C001": True, "C002": True}),
                ],
            ) as complete,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            first_decision = self._process(candidate_a, first_rule_set)
            second_decision = self._process(candidate_b, second_rule_set)

        self.assertEqual(first_decision.decision_status, "qualified")
        self.assertEqual(second_decision.decision_status, "qualified")
        self.assertEqual(complete.call_count, 2)
        favorite.assert_not_called()
        forward.assert_not_called()
        all_records = (
            self._read_jsonl(self.store.ai_errors_path)
            + self._read_jsonl(self.store.ai_results_path)
            + self._read_jsonl(self.store.decisions_path)
        )
        self.assertEqual(len(self._read_jsonl(self.store.ai_results_path)), 2)
        self.assertEqual(len(self._read_jsonl(self.store.decisions_path)), 2)
        forbidden_rule_set_fields = {
            "rule_set_id",
            "rule_set_version",
            "rule_set_digest",
            "rule_set",
        }
        self.assertTrue(all(
            forbidden_rule_set_fields.isdisjoint(record)
            for record in all_records
        ))


if __name__ == "__main__":
    unittest.main()
