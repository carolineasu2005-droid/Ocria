from dataclasses import dataclass
from typing import Literal

from ai_candidate_input import build_ai_candidate_input
from ai_provider_config import AIProviderConfig
from ai_screening_contract import (
    AIScreeningContractError,
    validate_ai_screening_response,
)
from ai_screening_prompt import build_ai_screening_prompt
from llm_provider_runtime import (
    LLMCompletionRequest,
    LLMMessage,
    LLMMessageRole,
    LLMRuntimeError,
    complete,
)
from ocr_records import CandidateOcrDocument
from screening_profile import ScreeningProfileVersion


@dataclass(frozen=True)
class AIScreeningResult:
    candidate_record_id: str
    ai_status: Literal["completed", "failed"]
    criteria_results: dict[str, bool] | None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_record_id, str):
            raise ValueError("candidate_record_id must be a string")

        if self.ai_status == "completed":
            if (
                not isinstance(self.criteria_results, dict)
                or not self.criteria_results
                or any(
                    type(criterion_id) is not str or type(value) is not bool
                    for criterion_id, value in self.criteria_results.items()
                )
            ):
                raise ValueError(
                    "completed result requires a non-empty Boolean mapping"
                )
        elif self.ai_status == "failed":
            if self.criteria_results is not None:
                raise ValueError("failed result requires criteria_results=None")
        else:
            raise ValueError("ai_status must be completed or failed")


def run_ai_screening(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> AIScreeningResult:
    if not isinstance(candidate, CandidateOcrDocument):
        raise TypeError("candidate must be a CandidateOcrDocument")
    if not isinstance(profile, ScreeningProfileVersion):
        raise TypeError("profile must be a ScreeningProfileVersion")
    if not isinstance(config, AIProviderConfig):
        raise TypeError("config must be an AIProviderConfig")

    candidate_record_id = candidate.candidate_record_id
    if not isinstance(candidate_record_id, str):
        raise ValueError("candidate.candidate_record_id must be a string")

    try:
        candidate_input = build_ai_candidate_input(candidate)
    except ValueError:
        return AIScreeningResult(
            candidate_record_id=candidate_record_id,
            ai_status="failed",
            criteria_results=None,
        )

    prompt = build_ai_screening_prompt(candidate_input, profile)
    messages = (
        LLMMessage(
            role=LLMMessageRole.SYSTEM,
            content=prompt.system_message,
        ),
        LLMMessage(
            role=LLMMessageRole.USER,
            content=prompt.user_message,
        ),
    )
    request = LLMCompletionRequest(messages=messages)

    try:
        completion = complete(config, request)
    except LLMRuntimeError:
        return AIScreeningResult(
            candidate_record_id=candidate_record_id,
            ai_status="failed",
            criteria_results=None,
        )

    try:
        criteria_results = validate_ai_screening_response(
            raw_response=completion.content,
            criteria=profile.criteria,
        )
    except AIScreeningContractError:
        return AIScreeningResult(
            candidate_record_id=candidate_record_id,
            ai_status="failed",
            criteria_results=None,
        )

    return AIScreeningResult(
        candidate_record_id=candidate_record_id,
        ai_status="completed",
        criteria_results=criteria_results,
    )
