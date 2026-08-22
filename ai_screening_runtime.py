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


R13_DIAGNOSTIC_MESSAGE_MAX_CHARS = 512


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


@dataclass(frozen=True)
class _AIScreeningAttemptFailure:
    failure_stage: Literal[
        "candidate_input",
        "provider_runtime",
        "response_contract",
    ]
    failure_type: str
    error_code: str | None
    provider: str | None
    operation: str | None
    status_code: int | None
    request_id: str | None
    message: str | None


@dataclass(frozen=True)
class _AIScreeningAttemptOutcome:
    result: AIScreeningResult
    failure: _AIScreeningAttemptFailure | None

    def __post_init__(self) -> None:
        if self.result.ai_status == "completed" and self.failure is not None:
            raise ValueError("completed attempt outcome requires failure=None")
        if (
            self.result.ai_status == "failed"
            and not isinstance(self.failure, _AIScreeningAttemptFailure)
        ):
            raise ValueError("failed attempt outcome requires an attempt failure")


def _bounded_failure_message(exception) -> str | None:
    text = str(exception)
    if not text:
        return None
    return text[:R13_DIAGNOSTIC_MESSAGE_MAX_CHARS]


def _run_ai_screening_attempt(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> _AIScreeningAttemptOutcome:
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
    except ValueError as exc:
        return _AIScreeningAttemptOutcome(
            result=AIScreeningResult(
                candidate_record_id=candidate_record_id,
                ai_status="failed",
                criteria_results=None,
            ),
            failure=_AIScreeningAttemptFailure(
                failure_stage="candidate_input",
                failure_type="ValueError",
                error_code=None,
                provider=None,
                operation=None,
                status_code=None,
                request_id=None,
                message=_bounded_failure_message(exc),
            ),
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
    except LLMRuntimeError as exc:
        return _AIScreeningAttemptOutcome(
            result=AIScreeningResult(
                candidate_record_id=candidate_record_id,
                ai_status="failed",
                criteria_results=None,
            ),
            failure=_AIScreeningAttemptFailure(
                failure_stage="provider_runtime",
                failure_type="LLMRuntimeError",
                error_code=exc.code.value,
                provider=exc.provider,
                operation=exc.operation.value,
                status_code=exc.status_code,
                request_id=exc.request_id,
                message=_bounded_failure_message(exc),
            ),
        )

    try:
        criteria_results = validate_ai_screening_response(
            raw_response=completion.content,
            criteria=profile.criteria,
        )
    except AIScreeningContractError as exc:
        return _AIScreeningAttemptOutcome(
            result=AIScreeningResult(
                candidate_record_id=candidate_record_id,
                ai_status="failed",
                criteria_results=None,
            ),
            failure=_AIScreeningAttemptFailure(
                failure_stage="response_contract",
                failure_type="AIScreeningContractError",
                error_code=None,
                provider=None,
                operation=None,
                status_code=None,
                request_id=None,
                message=_bounded_failure_message(exc),
            ),
        )

    return _AIScreeningAttemptOutcome(
        result=AIScreeningResult(
            candidate_record_id=candidate_record_id,
            ai_status="completed",
            criteria_results=criteria_results,
        ),
        failure=None,
    )


def run_ai_screening(
    candidate: CandidateOcrDocument,
    profile: ScreeningProfileVersion,
    config: AIProviderConfig,
) -> AIScreeningResult:
    return _run_ai_screening_attempt(candidate, profile, config).result
