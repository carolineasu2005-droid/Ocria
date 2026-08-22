import unittest
from unittest.mock import Mock, patch

from ai_provider_config import AIProviderConfig
from ai_screening_runtime import AIScreeningResult
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
        self.candidate.candidate_record_id = "candidate-r12"
        self.candidate.capture_status = CaptureStatus.COMPLETED
        self.profile = Mock(spec=ScreeningProfileVersion)
        self.config = make_config()
        self.rule_set = make_rule_set("C001")
        self.saved = (
            simple_brush.action_mode,
            simple_brush.no_forward_mode,
            simple_brush.stop_event,
            simple_brush.forward_consecutive,
        )
        simple_brush.stop_event = False
        simple_brush.no_forward_mode = False
        simple_brush.forward_consecutive = 5

    def tearDown(self):
        (
            simple_brush.action_mode,
            simple_brush.no_forward_mode,
            simple_brush.stop_event,
            simple_brush.forward_consecutive,
        ) = self.saved

    def test_completed_candidate_reaches_r11_once_and_r06_once(self):
        ai_result = AIScreeningResult(
            candidate_record_id="candidate-r12",
            ai_status="completed",
            criteria_results={"C001": True},
        )
        with (
            patch.object(simple_brush, "run_ai_screening", return_value=ai_result) as run_ai,
            patch("candidate_decision.evaluate_rule_set", return_value=True) as evaluate,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
        ):
            simple_brush.action_mode = simple_brush.ACTION_MODE_FAVORITE
            decision = simple_brush._process_finalized_candidate(
                self.candidate, self.profile, self.config, self.rule_set
            )

        self.assertEqual(decision.decision_status, "qualified")
        run_ai.assert_called_once_with(self.candidate, self.profile, self.config)
        evaluate.assert_called_once_with(self.rule_set, ai_result.criteria_results)
        favorite.assert_called_once_with()

    def test_ai_failure_skips_r06_and_all_actions_and_resets_global(self):
        ai_result = AIScreeningResult(
            candidate_record_id="candidate-r12",
            ai_status="failed",
            criteria_results=None,
        )
        with (
            patch.object(simple_brush, "run_ai_screening", return_value=ai_result),
            patch("candidate_decision.evaluate_rule_set") as evaluate,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            decision = simple_brush._process_finalized_candidate(
                self.candidate, self.profile, self.config, self.rule_set
            )

        self.assertEqual(decision.decision_status, "ai_failed")
        evaluate.assert_not_called()
        favorite.assert_not_called()
        forward.assert_not_called()
        self.assertEqual(simple_brush.forward_consecutive, 0)

    def test_rejected_has_zero_actions_and_resets_global(self):
        ai_result = AIScreeningResult(
            candidate_record_id="candidate-r12",
            ai_status="completed",
            criteria_results={"C001": False},
        )
        with (
            patch.object(simple_brush, "run_ai_screening", return_value=ai_result),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            decision = simple_brush._process_finalized_candidate(
                self.candidate, self.profile, self.config, self.rule_set
            )

        self.assertEqual(decision.decision_status, "rejected")
        favorite.assert_not_called()
        forward.assert_not_called()
        self.assertEqual(simple_brush.forward_consecutive, 0)

    def test_qualified_forward_and_suppression_do_not_reclassify_decision(self):
        ai_result = AIScreeningResult(
            candidate_record_id="candidate-r12",
            ai_status="completed",
            criteria_results={"C001": True},
        )
        simple_brush.action_mode = simple_brush.ACTION_MODE_FORWARD
        with (
            patch.object(simple_brush, "run_ai_screening", return_value=ai_result),
            patch.object(simple_brush, "forward_one_candidate", return_value=False) as forward,
        ):
            decision = simple_brush._process_finalized_candidate(
                self.candidate, self.profile, self.config, self.rule_set
            )
        self.assertEqual(decision.decision_status, "qualified")
        forward.assert_called_once_with()

        simple_brush.no_forward_mode = True
        with (
            patch.object(simple_brush, "run_ai_screening", return_value=ai_result),
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush, "perform_favorite_action") as favorite,
        ):
            decision = simple_brush._process_finalized_candidate(
                self.candidate, self.profile, self.config, self.rule_set
            )
        self.assertEqual(decision.decision_status, "qualified")
        forward.assert_not_called()
        favorite.assert_not_called()

    def test_rule_and_runtime_errors_propagate_without_actions(self):
        with (
            patch.object(simple_brush, "run_ai_screening", side_effect=RuntimeError("r11")),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            with self.assertRaisesRegex(RuntimeError, "^r11$"):
                simple_brush._process_finalized_candidate(
                    self.candidate, self.profile, self.config, self.rule_set
                )
        favorite.assert_not_called()
        forward.assert_not_called()

        ai_result = AIScreeningResult(
            candidate_record_id="candidate-r12",
            ai_status="completed",
            criteria_results={"C001": True},
        )
        with (
            patch.object(simple_brush, "run_ai_screening", return_value=ai_result),
            patch.object(
                simple_brush,
                "decide_candidate",
                side_effect=ScreeningRuleInputError("bad mapping"),
            ),
            patch.object(simple_brush, "perform_favorite_action") as favorite,
            patch.object(simple_brush, "forward_one_candidate") as forward,
        ):
            with self.assertRaisesRegex(ScreeningRuleInputError, "^bad mapping$"):
                simple_brush._process_finalized_candidate(
                    self.candidate, self.profile, self.config, self.rule_set
                )
        favorite.assert_not_called()
        forward.assert_not_called()

    def test_multiple_candidates_reuse_the_exact_bound_rule_set(self):
        candidates = []
        for candidate_id in ("candidate-1", "candidate-2"):
            candidate = Mock(spec=CandidateOcrDocument)
            candidate.candidate_record_id = candidate_id
            candidates.append(candidate)
        ai_results = [
            AIScreeningResult(candidate_id, "completed", {"C001": False})
            for candidate_id in ("candidate-1", "candidate-2")
        ]
        with (
            patch.object(simple_brush, "run_ai_screening", side_effect=ai_results),
            patch.object(simple_brush, "decide_candidate", wraps=simple_brush.decide_candidate) as decide,
        ):
            for candidate in candidates:
                simple_brush._process_finalized_candidate(
                    candidate, self.profile, self.config, self.rule_set
                )
        self.assertEqual(decide.call_count, 2)
        self.assertIs(decide.call_args_list[0].args[1], self.rule_set)
        self.assertIs(decide.call_args_list[1].args[1], self.rule_set)


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
