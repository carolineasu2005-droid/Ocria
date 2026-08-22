import unittest
from unittest.mock import Mock, patch

from ai_provider_config import AIProviderConfig
from ai_screening_persistence import (
    AIPersistenceIntegrityError,
    AIScreeningRecordStore,
)
from ai_screening_runtime import (
    AIScreeningResult,
    _AIScreeningAttemptFailure,
    _AIScreeningAttemptOutcome,
)
from candidate_decision import CandidateDecision
from ocr_records import CandidateOcrDocument, CaptureStatus
from screening_profile import ScreeningProfileVersion
from screening_rule_engine import (
    ScreeningRule,
    ScreeningRuleInputError,
    ScreeningRuleSet,
)
import simple_brush


def make_rule_set(*expressions):
    return ScreeningRuleSet(tuple(ScreeningRule(expression) for expression in expressions))


def make_config():
    return AIProviderConfig(
        provider="qwen",
        api_key="synthetic-r12-api-key",
        base_url="https://example.test/v1",
        model="synthetic-model",
    )


class FinalizedCandidateDecisionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.candidate = Mock(spec=CandidateOcrDocument)
        self.candidate.run_id = "run-r13"
        self.candidate.candidate_record_id = "candidate-r12"
        self.candidate.capture_status = CaptureStatus.COMPLETED
        self.profile = Mock(spec=ScreeningProfileVersion)
        self.profile.screening_profile_id = "profile-r13"
        self.profile.profile_version = 1
        self.profile.criteria_digest = "sha256:criteria-r13"
        self.config = make_config()
        self.rule_set = make_rule_set("C001")
        self.store = Mock(spec=AIScreeningRecordStore)
        self.store.run_id = "run-r13"
        self.saved = (
            simple_brush.action_mode,
            simple_brush.no_forward_mode,
            simple_brush.stop_event,
            simple_brush.paused,
            simple_brush.forward_consecutive,
        )
        simple_brush.stop_event = False
        simple_brush.paused = False
        simple_brush.no_forward_mode = False
        simple_brush.forward_consecutive = 5

    def tearDown(self):
        (
            simple_brush.action_mode,
            simple_brush.no_forward_mode,
            simple_brush.stop_event,
            simple_brush.paused,
            simple_brush.forward_consecutive,
        ) = self.saved

    def completed_attempt(self, criteria_results=None):
        return _AIScreeningAttemptOutcome(
            result=AIScreeningResult(
                candidate_record_id=self.candidate.candidate_record_id,
                ai_status="completed",
                criteria_results=criteria_results or {"C001": True},
            ),
            failure=None,
        )

    def failed_attempt(self):
        return _AIScreeningAttemptOutcome(
            result=AIScreeningResult(
                candidate_record_id=self.candidate.candidate_record_id,
                ai_status="failed",
                criteria_results=None,
            ),
            failure=_AIScreeningAttemptFailure(
                failure_stage="provider_runtime",
                failure_type="LLMRuntimeError",
                error_code="network_error",
                provider="qwen",
                operation="complete",
                status_code=None,
                request_id=None,
                message="network unavailable",
            ),
        )

    def process(self, candidate=None):
        return simple_brush._process_finalized_candidate(
            candidate or self.candidate,
            self.profile,
            self.config,
            self.rule_set,
            self.store,
        )

    def test_first_attempt_completed_orders_outcome_decision_persistence_and_qualified_action(self):
        events = []
        outcome = self.completed_attempt()
        decision = CandidateDecision("candidate-r12", "qualified")
        with (
            patch.object(
                simple_brush,
                "_run_ai_screening_attempt",
                side_effect=lambda *args: events.append("attempt") or outcome,
            ) as attempt,
            patch.object(
                self.store,
                "append_ai_result",
                side_effect=lambda record: events.append("outcome"),
            ),
            patch.object(
                simple_brush,
                "decide_candidate",
                side_effect=lambda *args: events.append("decision") or decision,
            ) as decide,
            patch.object(
                self.store,
                "append_decision",
                side_effect=lambda record: events.append("decision_record"),
            ),
            patch.object(
                simple_brush,
                "perform_favorite_action",
                side_effect=lambda: events.append("action"),
            ),
        ):
            simple_brush.action_mode = simple_brush.ACTION_MODE_FAVORITE
            self.assertIs(self.process(), decision)

        self.assertEqual(
            events,
            ["attempt", "outcome", "decision", "decision_record", "action"],
        )
        attempt.assert_called_once_with(self.candidate, self.profile, self.config)
        self.assertIs(decide.call_args.args[0], outcome.result)
        self.assertIs(decide.call_args.args[1], self.rule_set)
        self.store.append_ai_error.assert_not_called()

    def test_failed_then_completed_persists_error_before_retry_and_reuses_exact_objects(self):
        events = []
        outcomes = [self.failed_attempt(), self.completed_attempt()]

        def next_attempt(*args):
            events.append("attempt")
            self.assertIs(args[0], self.candidate)
            self.assertIs(args[1], self.profile)
            self.assertIs(args[2], self.config)
            return outcomes.pop(0)

        with (
            patch.object(simple_brush, "_run_ai_screening_attempt", side_effect=next_attempt) as attempt,
            patch.object(
                self.store,
                "append_ai_error",
                side_effect=lambda record: events.append("error"),
            ) as append_error,
            patch.object(
                self.store,
                "append_ai_result",
                side_effect=lambda record: events.append("outcome"),
            ) as append_result,
            patch.object(
                simple_brush,
                "decide_candidate",
                side_effect=lambda *args: events.append("decision") or CandidateDecision("candidate-r12", "rejected"),
            ) as decide,
            patch.object(self.store, "append_decision", side_effect=lambda record: events.append("decision_record")),
        ):
            decision = self.process()

        self.assertEqual(decision.decision_status, "rejected")
        self.assertEqual(
            events,
            ["attempt", "error", "attempt", "outcome", "decision", "decision_record"],
        )
        self.assertEqual(attempt.call_count, 2)
        error_record = append_error.call_args.args[0]
        self.assertEqual(error_record.attempt_number, 1)
        self.assertEqual(append_result.call_args.args[0].attempts_used, 2)
        self.assertIs(decide.call_args.args[1], self.rule_set)

    def test_two_failures_then_completed_stops_after_third_call(self):
        with (
            patch.object(
                simple_brush,
                "_run_ai_screening_attempt",
                side_effect=[self.failed_attempt(), self.failed_attempt(), self.completed_attempt()],
            ) as attempt,
            patch.object(simple_brush, "decide_candidate", return_value=CandidateDecision("candidate-r12", "rejected")),
        ):
            decision = self.process()

        self.assertEqual(decision.decision_status, "rejected")
        self.assertEqual(attempt.call_count, 3)
        self.assertEqual(self.store.append_ai_error.call_count, 2)
        self.assertEqual(self.store.append_ai_result.call_count, 1)
        self.assertEqual(self.store.append_ai_result.call_args.args[0].attempts_used, 3)

    def test_three_failures_select_third_persist_ai_failed_and_continue(self):
        with (
            patch.object(
                simple_brush,
                "_run_ai_screening_attempt",
                side_effect=[self.failed_attempt(), self.failed_attempt(), self.failed_attempt()],
            ) as attempt,
            patch("candidate_decision.evaluate_rule_set") as evaluate,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            decision = self.process()

        self.assertEqual(decision.decision_status, "ai_failed")
        self.assertEqual(attempt.call_count, 3)
        self.assertEqual(self.store.append_ai_error.call_count, 3)
        final_record = self.store.append_ai_result.call_args.args[0]
        self.assertEqual(final_record.ai_status, "failed")
        self.assertIsNone(final_record.criteria_results)
        self.assertEqual(final_record.attempts_used, 3)
        self.assertEqual(self.store.append_decision.call_count, 1)
        evaluate.assert_not_called()
        favorite.assert_not_called()
        forward.assert_not_called()
        self.assertEqual(simple_brush.forward_consecutive, 0)

    def test_attempt_error_write_failure_blocks_retry_outcome_decision_and_action(self):
        error = AIPersistenceIntegrityError("write_ai_error", Mock())
        with (
            patch.object(simple_brush, "_run_ai_screening_attempt", return_value=self.failed_attempt()) as attempt,
            patch.object(self.store, "append_ai_error", side_effect=error),
            patch.object(simple_brush, "decide_candidate") as decide,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            with self.assertRaises(AIPersistenceIntegrityError):
                self.process()

        attempt.assert_called_once_with(self.candidate, self.profile, self.config)
        self.store.append_ai_result.assert_not_called()
        decide.assert_not_called()
        favorite.assert_not_called()
        forward.assert_not_called()

    def test_final_outcome_write_failure_blocks_decision_and_action(self):
        cases = (
            ("completed", [self.completed_attempt()]),
            ("failed", [self.failed_attempt(), self.failed_attempt(), self.failed_attempt()]),
        )
        for status, outcomes in cases:
            with self.subTest(status=status):
                self.store.reset_mock()
                with (
                    patch.object(simple_brush, "_run_ai_screening_attempt", side_effect=outcomes),
                    patch.object(
                        self.store,
                        "append_ai_result",
                        side_effect=AIPersistenceIntegrityError("write_ai_result", Mock()),
                    ),
                    patch.object(simple_brush, "decide_candidate") as decide,
                    patch.object(simple_brush, "perform_favorite_action") as favorite,
                    patch.object(simple_brush, "forward_one_candidate") as forward,
                ):
                    with self.assertRaises(AIPersistenceIntegrityError):
                        self.process()
                decide.assert_not_called()
                self.store.append_decision.assert_not_called()
                favorite.assert_not_called()
                forward.assert_not_called()

    def test_decision_write_failure_blocks_action_and_continuation(self):
        decision = CandidateDecision("candidate-r12", "qualified")
        with (
            patch.object(simple_brush, "_run_ai_screening_attempt", return_value=self.completed_attempt()),
            patch.object(simple_brush, "decide_candidate", return_value=decision),
            patch.object(
                self.store,
                "append_decision",
                side_effect=AIPersistenceIntegrityError("write_decision", Mock()),
            ),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            with self.assertRaises(AIPersistenceIntegrityError):
                self.process()

        self.store.append_ai_result.assert_called_once()
        favorite.assert_not_called()
        forward.assert_not_called()

    def test_r06_failure_after_final_outcome_writes_no_decision(self):
        with (
            patch.object(simple_brush, "_run_ai_screening_attempt", return_value=self.completed_attempt()),
            patch.object(
                simple_brush,
                "decide_candidate",
                side_effect=ScreeningRuleInputError("bad mapping"),
            ),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            with self.assertRaisesRegex(ScreeningRuleInputError, "^bad mapping$"):
                self.process()

        self.store.append_ai_result.assert_called_once()
        self.store.append_decision.assert_not_called()
        favorite.assert_not_called()
        forward.assert_not_called()

    def test_stop_and_pause_use_existing_state_without_synthetic_decision(self):
        simple_brush.stop_event = True
        with patch.object(simple_brush, "_run_ai_screening_attempt") as attempt:
            self.assertIsNone(self.process())
        attempt.assert_not_called()
        self.store.append_ai_error.assert_not_called()
        self.store.append_ai_result.assert_not_called()
        self.store.append_decision.assert_not_called()

        self.store.reset_mock()
        simple_brush.stop_event = False
        simple_brush.paused = True

        def release_pause(_seconds):
            simple_brush.paused = False

        with (
            patch.object(simple_brush.time, "sleep", side_effect=release_pause) as sleep,
            patch.object(simple_brush, "_run_ai_screening_attempt", return_value=self.completed_attempt()),
            patch.object(simple_brush, "decide_candidate", return_value=CandidateDecision("candidate-r12", "rejected")),
        ):
            self.assertEqual(self.process().decision_status, "rejected")
        sleep.assert_called_once_with(0.2)

    def test_repeated_ai_failed_candidates_add_no_counter_or_stop(self):
        candidates = []
        for candidate_id in ("candidate-1", "candidate-2"):
            candidate = Mock(spec=CandidateOcrDocument)
            candidate.run_id = "run-r13"
            candidate.candidate_record_id = candidate_id
            candidates.append(candidate)
        failed_outcomes = []
        for candidate in candidates:
            failed_outcomes.extend(
                [
                    _AIScreeningAttemptOutcome(
                        AIScreeningResult(candidate.candidate_record_id, "failed", None),
                        _AIScreeningAttemptFailure("provider_runtime", "LLMRuntimeError", None, None, None, None, None, "failed"),
                    )
                    for _ in range(3)
                ]
            )
        with patch.object(simple_brush, "_run_ai_screening_attempt", side_effect=failed_outcomes):
            for candidate in candidates:
                decision = self.process(candidate)
                self.assertEqual(decision.decision_status, "ai_failed")

        self.assertFalse(simple_brush.stop_event)
        self.assertFalse(hasattr(simple_brush, "consecutive_ai_failures"))
        self.assertEqual(self.store.append_ai_error.call_count, 6)
        self.assertEqual(self.store.append_ai_result.call_count, 2)
        self.assertEqual(self.store.append_decision.call_count, 2)

    def test_action_result_does_not_write_an_additional_record(self):
        simple_brush.action_mode = simple_brush.ACTION_MODE_FORWARD
        cases = (False, RuntimeError("action failed"))
        for result in cases:
            with self.subTest(result=type(result).__name__):
                self.store.reset_mock()
                patches = (
                    patch.object(
                        simple_brush,
                        "_run_ai_screening_attempt",
                        return_value=self.completed_attempt(),
                    ),
                    patch.object(
                        simple_brush,
                        "decide_candidate",
                        return_value=CandidateDecision("candidate-r12", "qualified"),
                    ),
                    patch.object(
                        simple_brush,
                        "forward_one_candidate",
                        side_effect=result if isinstance(result, Exception) else None,
                        return_value=None if isinstance(result, Exception) else result,
                    ),
                )
                with patches[0], patches[1], patches[2] as forward:
                    if isinstance(result, Exception):
                        with self.assertRaisesRegex(RuntimeError, "^action failed$"):
                            self.process()
                    else:
                        self.assertEqual(self.process().decision_status, "qualified")
                forward.assert_called_once_with()
                self.store.append_decision.assert_called_once()


class RuleInputIntegrationTests(unittest.TestCase):
    def test_repeatable_cli_rules_preserve_order_duplicates_and_raw_expression(self):
        argv = [
            "simple_brush.py",
            "--screening-rule",
            " C001 AND (C002 OR C003) ",
            "--screening-rule",
            "C001",
            "--screening-rule",
            "C001",
        ]
        with patch.object(simple_brush.sys, "argv", argv):
            args = simple_brush.parse_args()
        self.assertEqual(
            args["screening_rules"],
            [" C001 AND (C002 OR C003) ", "C001", "C001"],
        )
        rule_set = simple_brush._build_screening_rule_set(
            tuple(args["screening_rules"])
        )
        self.assertEqual(
            tuple(rule.expression for rule in rule_set.rules),
            tuple(args["screening_rules"]),
        )

    def test_prompt_rules_preserve_nonblank_raw_input_and_require_first_rule(self):
        with patch("builtins.input", side_effect=["  ", " C001 ", ""]):
            expressions = simple_brush.prompt_screening_rule_expressions()
        self.assertEqual(expressions, (" C001 ",))

    def test_formal_flags_do_not_change_startup_mode_and_noninteractive_requires_both_inputs(self):
        self.assertFalse(
            simple_brush.is_noninteractive_startup(
                {"screening_profile_id": "profile", "screening_rules": ["C001"]}
            )
        )
        with (
            patch.object(simple_brush.sys, "argv", ["simple_brush.py", "--auto"]),
            patch.object(simple_brush, "run") as run,
        ):
            self.assertEqual(simple_brush.main(), 2)
        run.assert_not_called()
        with (
            patch.object(
                simple_brush.sys,
                "argv",
                ["simple_brush.py", "--auto", "--screening-profile-id", "profile"],
            ),
            patch.object(simple_brush, "run") as run,
        ):
            self.assertEqual(simple_brush.main(), 2)
        run.assert_not_called()

    def test_valid_noninteractive_startup_builds_one_bound_rule_set(self):
        bound_rule_set = make_rule_set("C001")
        with (
            patch.object(
                simple_brush.sys,
                "argv",
                [
                    "simple_brush.py",
                    "--auto",
                    "--screening-profile-id",
                    "profile",
                    "--screening-rule",
                    "C001",
                ],
            ),
            patch.object(simple_brush, "_build_screening_rule_set", return_value=bound_rule_set) as build,
            patch.object(simple_brush, "run", return_value=0) as run,
        ):
            self.assertEqual(simple_brush.main(), 0)
        build.assert_called_once_with(("C001",))
        run.assert_called_once_with(
            screening_profile_id="profile",
            run_bound_rule_set=bound_rule_set,
        )


if __name__ == "__main__":
    unittest.main()
