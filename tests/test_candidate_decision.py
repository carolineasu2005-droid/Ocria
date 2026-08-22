from dataclasses import FrozenInstanceError, fields
import unittest
from unittest.mock import patch

from ai_screening_runtime import AIScreeningResult
from candidate_decision import CandidateDecision, decide_candidate
from screening_rule_engine import (
    ScreeningRule,
    ScreeningRuleInputError,
    ScreeningRuleSet,
    ScreeningRuleValidationError,
)


class CandidateDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule_set = ScreeningRuleSet((ScreeningRule("C001"),))
        self.criteria_results = {"C001": True}

    def test_completed_true_returns_qualified_with_exact_rule_inputs(self) -> None:
        ai_result = AIScreeningResult(
            candidate_record_id="candidate-1",
            ai_status="completed",
            criteria_results=self.criteria_results,
        )

        with patch(
            "candidate_decision.evaluate_rule_set", return_value=True
        ) as evaluate_rule_set:
            decision = decide_candidate(ai_result, self.rule_set)

        self.assertEqual(
            decision,
            CandidateDecision(
                candidate_record_id="candidate-1",
                decision_status="qualified",
            ),
        )
        evaluate_rule_set.assert_called_once()
        passed_rule_set, passed_results = evaluate_rule_set.call_args.args
        self.assertIs(passed_rule_set, self.rule_set)
        self.assertIs(passed_results, self.criteria_results)

    def test_completed_false_returns_rejected_for_all_false_results(self) -> None:
        all_false_results = {"C001": False}
        ai_result = AIScreeningResult(
            candidate_record_id="candidate-2",
            ai_status="completed",
            criteria_results=all_false_results,
        )

        with patch(
            "candidate_decision.evaluate_rule_set", return_value=False
        ) as evaluate_rule_set:
            decision = decide_candidate(ai_result, self.rule_set)

        self.assertEqual(decision.decision_status, "rejected")
        self.assertNotEqual(decision.decision_status, "ai_failed")
        evaluate_rule_set.assert_called_once_with(self.rule_set, all_false_results)

    def test_failed_returns_ai_failed_without_evaluating_rules(self) -> None:
        ai_result = AIScreeningResult(
            candidate_record_id="candidate-3",
            ai_status="failed",
            criteria_results=None,
        )

        with patch("candidate_decision.evaluate_rule_set") as evaluate_rule_set:
            decision = decide_candidate(ai_result, self.rule_set)

        self.assertEqual(
            decision,
            CandidateDecision(
                candidate_record_id="candidate-3",
                decision_status="ai_failed",
            ),
        )
        evaluate_rule_set.assert_not_called()

    def test_candidate_decision_has_exact_frozen_shape_and_validation(self) -> None:
        decision = CandidateDecision("candidate-4", "qualified")

        self.assertEqual(
            tuple(field.name for field in fields(CandidateDecision)),
            ("candidate_record_id", "decision_status"),
        )
        with self.assertRaises(FrozenInstanceError):
            decision.decision_status = "rejected"
        for status in ("qualified", "rejected", "ai_failed"):
            self.assertEqual(CandidateDecision("candidate-4", status).decision_status, status)
        with self.assertRaisesRegex(
            ValueError, "^candidate_record_id must be a string$"
        ):
            CandidateDecision(1, "qualified")
        with self.assertRaisesRegex(
            ValueError,
            "^decision_status must be qualified, rejected, or ai_failed$",
        ):
            CandidateDecision("candidate-4", "other")

    def test_rule_engine_errors_propagate(self) -> None:
        ai_result = AIScreeningResult(
            candidate_record_id="candidate-5",
            ai_status="completed",
            criteria_results=self.criteria_results,
        )

        with patch(
            "candidate_decision.evaluate_rule_set",
            side_effect=ScreeningRuleValidationError("invalid rule set"),
        ):
            with self.assertRaisesRegex(
                ScreeningRuleValidationError, "^invalid rule set$"
            ):
                decide_candidate(ai_result, self.rule_set)
        with patch(
            "candidate_decision.evaluate_rule_set",
            side_effect=ScreeningRuleInputError("invalid criterion results"),
        ):
            with self.assertRaisesRegex(
                ScreeningRuleInputError, "^invalid criterion results$"
            ):
                decide_candidate(ai_result, self.rule_set)

    def test_decide_candidate_validates_input_types_before_failed_short_circuit(self) -> None:
        failed_result = AIScreeningResult(
            candidate_record_id="candidate-6",
            ai_status="failed",
            criteria_results=None,
        )

        with self.assertRaisesRegex(
            TypeError, "^ai_result must be an AIScreeningResult$"
        ):
            decide_candidate(object(), self.rule_set)
        with self.assertRaisesRegex(
            TypeError, "^rule_set must be a ScreeningRuleSet$"
        ):
            decide_candidate(failed_result, object())


if __name__ == "__main__":
    unittest.main()
