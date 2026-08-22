from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ocr_records import json_dumps, validate_timezone_iso


_ATTEMPT_FAILURE_STAGES = (
    "candidate_input",
    "provider_runtime",
    "response_contract",
)
_DECISION_STATUSES = ("qualified", "rejected", "ai_failed")
_PERSISTENCE_OPERATIONS = (
    "initialize",
    "write_ai_error",
    "write_ai_result",
    "write_decision",
)
_MAX_ATTEMPT_NUMBER = 3
_DIAGNOSTIC_MESSAGE_MAX_CHARS = 512


def _require_non_empty_string(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_attempt_number(value: object, field_name: str) -> None:
    if type(value) is not int or not 1 <= value <= _MAX_ATTEMPT_NUMBER:
        raise ValueError(f"{field_name} must be an integer from 1 through 3")


def _require_optional_string(value: object, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"{field_name} must be None or a non-empty string")


@dataclass(frozen=True)
class AIAttemptErrorRecord:
    run_id: str
    candidate_record_id: str
    attempt_number: int
    failure_stage: Literal[
        "candidate_input",
        "provider_runtime",
        "response_contract",
    ]
    failure_type: str
    occurred_at: str
    error_code: str | None
    provider: str | None
    operation: str | None
    status_code: int | None
    request_id: str | None
    message: str | None

    def __post_init__(self) -> None:
        _require_non_empty_string(self.run_id, "run_id")
        _require_non_empty_string(self.candidate_record_id, "candidate_record_id")
        _require_attempt_number(self.attempt_number, "attempt_number")
        if self.failure_stage not in _ATTEMPT_FAILURE_STAGES:
            raise ValueError("failure_stage is invalid")
        _require_non_empty_string(self.failure_type, "failure_type")
        if not isinstance(self.occurred_at, str):
            raise ValueError("occurred_at must be an ISO 8601 timestamp")
        validate_timezone_iso(self.occurred_at)
        _require_optional_string(self.error_code, "error_code")
        _require_optional_string(self.provider, "provider")
        _require_optional_string(self.operation, "operation")
        if self.status_code is not None and (
            type(self.status_code) is not int or self.status_code <= 0
        ):
            raise ValueError("status_code must be None or a positive integer")
        _require_optional_string(self.request_id, "request_id")
        _require_optional_string(self.message, "message")
        if self.message is not None and len(self.message) > _DIAGNOSTIC_MESSAGE_MAX_CHARS:
            raise ValueError("message must be at most 512 characters")


@dataclass(frozen=True)
class AIFinalOutcomeRecord:
    run_id: str
    candidate_record_id: str
    ai_status: Literal["completed", "failed"]
    criteria_results: dict[str, bool] | None
    attempts_used: int
    screening_profile_id: str
    profile_version: int
    criteria_digest: str
    provider: str
    model: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.run_id, "run_id")
        _require_non_empty_string(self.candidate_record_id, "candidate_record_id")
        _require_attempt_number(self.attempts_used, "attempts_used")
        _require_non_empty_string(
            self.screening_profile_id,
            "screening_profile_id",
        )
        if type(self.profile_version) is not int or self.profile_version <= 0:
            raise ValueError("profile_version must be a positive integer")
        _require_non_empty_string(self.criteria_digest, "criteria_digest")
        _require_non_empty_string(self.provider, "provider")
        _require_non_empty_string(self.model, "model")
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
class CandidateDecisionRecord:
    run_id: str
    candidate_record_id: str
    decision_status: Literal["qualified", "rejected", "ai_failed"]

    def __post_init__(self) -> None:
        _require_non_empty_string(self.run_id, "run_id")
        _require_non_empty_string(self.candidate_record_id, "candidate_record_id")
        if self.decision_status not in _DECISION_STATUSES:
            raise ValueError("decision_status is invalid")


class AIPersistenceIntegrityError(RuntimeError):
    def __init__(self, operation: str, path: Path) -> None:
        if operation not in _PERSISTENCE_OPERATIONS:
            raise ValueError("operation is invalid")
        self.operation = operation
        self.path = path
        super().__init__(
            f"R13 persistence integrity failure during {operation}"
        )


class AIScreeningRecordStore:
    def __init__(self, run_dir: Path, run_id: str) -> None:
        _require_non_empty_string(run_id, "run_id")
        if not isinstance(run_dir, Path):
            raise TypeError("run_dir must be a Path")
        try:
            if not run_dir.is_dir():
                raise ValueError("run_dir must be an existing directory")
        except OSError as exc:
            raise AIPersistenceIntegrityError("initialize", run_dir) from exc

        self.run_dir = run_dir
        self.run_id = run_id
        self.ai_results_path = run_dir / "ai_results.jsonl"
        self.ai_errors_path = run_dir / "ai_errors.jsonl"
        self.decisions_path = run_dir / "decisions.jsonl"
        for path in (
            self.ai_results_path,
            self.ai_errors_path,
            self.decisions_path,
        ):
            try:
                with path.open(mode="x", encoding="utf-8", newline=""):
                    pass
            except OSError as exc:
                raise AIPersistenceIntegrityError("initialize", path) from exc

    def append_ai_error(self, record: AIAttemptErrorRecord) -> None:
        self._append(
            record,
            AIAttemptErrorRecord,
            "write_ai_error",
            self.ai_errors_path,
        )

    def append_ai_result(self, record: AIFinalOutcomeRecord) -> None:
        self._append(
            record,
            AIFinalOutcomeRecord,
            "write_ai_result",
            self.ai_results_path,
        )

    def append_decision(self, record: CandidateDecisionRecord) -> None:
        self._append(
            record,
            CandidateDecisionRecord,
            "write_decision",
            self.decisions_path,
        )

    def _append(
        self,
        record: object,
        record_type: type,
        operation: str,
        path: Path,
    ) -> None:
        if type(record) is not record_type:
            raise TypeError(f"record must be an exact {record_type.__name__}")
        if record.run_id != self.run_id:
            raise ValueError("record.run_id must match store.run_id")
        serialized = json_dumps(record)
        try:
            with path.open(mode="a", encoding="utf-8", newline="") as stream:
                stream.write(serialized + "\n")
                stream.flush()
        except OSError as exc:
            raise AIPersistenceIntegrityError(operation, path) from exc
