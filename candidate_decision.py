from dataclasses import dataclass
from typing import Literal

from ai_screening_runtime import AIScreeningResult
from screening_rule_engine import ScreeningRuleSet, evaluate_rule_set


@dataclass(frozen=True)
class CandidateDecision:
    candidate_record_id: str
    decision_status: Literal["qualified", "rejected", "ai_failed"]

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_record_id, str):
            raise ValueError("candidate_record_id must be a string")
        if self.decision_status not in (
            "qualified",
            "rejected",
            "ai_failed",
        ):
            raise ValueError(
                "decision_status must be qualified, rejected, or ai_failed"
            )


def decide_candidate(
    ai_result: AIScreeningResult,
    rule_set: ScreeningRuleSet,
) -> CandidateDecision:
    if not isinstance(ai_result, AIScreeningResult):
        raise TypeError("ai_result must be an AIScreeningResult")
    if not isinstance(rule_set, ScreeningRuleSet):
        raise TypeError("rule_set must be a ScreeningRuleSet")
    if ai_result.ai_status == "failed":
        return CandidateDecision(
            candidate_record_id=ai_result.candidate_record_id,
            decision_status="ai_failed",
        )
    qualified = evaluate_rule_set(rule_set, ai_result.criteria_results)
    return CandidateDecision(
        candidate_record_id=ai_result.candidate_record_id,
        decision_status="qualified" if qualified else "rejected",
    )
