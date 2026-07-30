"""Stage-0 OCR records and JSON-compatible serialization helpers.

This module deliberately preserves OCR evidence without implementing the
normalization, aggregation, similarity, or dynamic-end algorithms planned for
later stages.
"""

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type, TypeVar


STORAGE_SCHEMA_VERSION = "1.0.0"
DOCUMENT_VERSION = "stage0-v1"
SUPPORTED_STORAGE_SCHEMA_VERSIONS = (STORAGE_SCHEMA_VERSION,)
SUPPORTED_DOCUMENT_VERSIONS = (DOCUMENT_VERSION,)
NOT_IMPLEMENTED = "not_implemented"


class CaptureType(str, Enum):
    """Known purposes for an OCR capture in the current workflow."""

    FORMAL_SCREEN = "formal_screen"
    LOAD_CHECK = "load_check"
    LOAD_RETRY = "load_retry"
    SWITCH_CHECK = "switch_check"
    SCROLL_CONFIRMATION = "scroll_confirmation"
    SCROLL_RETRY = "scroll_retry"
    OTHER = "other"


class CaptureStatus(str, Enum):
    """Terminal candidate capture outcomes supported by stage 0."""

    COMPLETED = "completed"
    COMPLETED_WITH_LIMIT = "completed_with_limit"
    ABORTED = "aborted"
    INTERRUPTED = "interrupted"
    # A completed candidate for which no OCR observation was captured at all.
    EMPTY = "empty"


class ProcessingStatus(str, Enum):
    """Processing state without claiming later-stage algorithms ran."""

    RAW_ONLY = "raw_only"
    NOT_IMPLEMENTED = NOT_IMPLEMENTED


class RunStatus(str, Enum):
    """Lifecycle states written to the run manifest."""

    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    ERROR = "error"
    DISABLED = "disabled"


def timezone_iso(value: Optional[datetime] = None) -> str:
    """Return a timezone-aware ISO 8601 timestamp."""

    current = datetime.now().astimezone() if value is None else value
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("datetime must include a timezone")
    return current.isoformat()


def validate_timezone_iso(value: str) -> None:
    """Validate that an ISO 8601 string includes an explicit timezone."""

    parse_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(parse_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")


class RecordVersionError(ValueError):
    """A sanitized version-contract failure raised during record restore."""

    def __init__(
        self,
        field_name: str,
        actual_version: Optional[str],
        supported_versions: Tuple[str, ...],
        error_type: str,
    ) -> None:
        self.field_name = field_name
        self.actual_version = actual_version
        self.supported_versions = supported_versions
        self.error_type = error_type
        super().__init__(
            "{0}: actual={1!r} supported={2!r}".format(
                error_type,
                actual_version,
                list(supported_versions),
            )
        )


def validate_record_version(
    data: Mapping[str, Any],
    field_name: str,
    supported_versions: Tuple[str, ...],
) -> str:
    """Require one supported string version without inspecting record content."""

    if field_name not in data:
        raise RecordVersionError(
            field_name,
            None,
            supported_versions,
            "MissingVersionError",
        )
    value = data[field_name]
    if not isinstance(value, str):
        raise RecordVersionError(
            field_name,
            "<{0}>".format(type(value).__name__),
            supported_versions,
            "InvalidVersionTypeError",
        )
    if value not in supported_versions:
        raise RecordVersionError(
            field_name,
            value,
            supported_versions,
            "UnsupportedVersionError",
        )
    return value


def validate_capture_outcome(
    capture_status: CaptureStatus,
    end_reason: Optional[str],
    abort_reason: Optional[str],
) -> None:
    """Enforce mutually exclusive normal-end and abnormal-stop reasons."""

    status = _enum_value(CaptureStatus, capture_status)
    for field_name, value in (
        ("end_reason", end_reason),
        ("abort_reason", abort_reason),
    ):
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            raise ValueError("{0} must be a non-empty string or null".format(
                field_name
            ))
    if end_reason is not None and abort_reason is not None:
        raise ValueError("end_reason and abort_reason are mutually exclusive")
    if status in (
        CaptureStatus.COMPLETED,
        CaptureStatus.COMPLETED_WITH_LIMIT,
        CaptureStatus.EMPTY,
    ):
        if abort_reason is not None:
            raise ValueError("completed captures cannot have abort_reason")
    else:
        if end_reason is not None:
            raise ValueError("aborted or interrupted captures cannot have end_reason")
        if abort_reason is None:
            raise ValueError("aborted or interrupted captures require abort_reason")
    if (
        status == CaptureStatus.COMPLETED_WITH_LIMIT
        and end_reason != "max_screen_limit"
    ):
        raise ValueError(
            "completed_with_limit requires end_reason=max_screen_limit"
        )


def to_json_compatible(value: Any) -> Any:
    """Recursively convert supported values to JSON-compatible primitives."""

    if isinstance(value, Enum):
        return to_json_compatible(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return timezone_iso(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: to_json_compatible(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        converted = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            converted[key] = to_json_compatible(item)
        return converted
    if isinstance(value, (list, tuple)):
        return [to_json_compatible(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(
        "unsupported JSON value type: {0}".format(type(value).__name__)
    )


def json_dumps(value: Any) -> str:
    """Serialize one value as compact UTF-8-friendly JSON text."""

    return json.dumps(
        to_json_compatible(value),
        ensure_ascii=False,
        separators=(",", ":"),
    )


T = TypeVar("T")


def _known_values(cls: Type[T], data: Mapping[str, Any]) -> Dict[str, Any]:
    """Ignore additive unknown fields when restoring a known stage-0 type."""

    known_names = {item.name for item in fields(cls)}
    return {key: value for key, value in data.items() if key in known_names}


def _enum_value(enum_cls: Type[T], value: Any) -> T:
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)


def _bbox_from_value(value: Any) -> Optional[Tuple[Tuple[float, float], ...]]:
    if value is None:
        return None
    try:
        return tuple((point[0], point[1]) for point in value)
    except (IndexError, KeyError, TypeError) as exc:
        raise ValueError("bbox must contain coordinate pairs") from exc


class JsonRecordMixin:
    """Shared conversion API for stage-0 data objects."""

    def to_dict(self) -> Dict[str, Any]:
        return to_json_compatible(self)

    def to_json(self) -> str:
        return json_dumps(self)


@dataclass(frozen=True)
class OcrBox(JsonRecordMixin):
    box_id: str
    raw_text: str
    confidence: Optional[float]
    bbox: Optional[Tuple[Tuple[float, float], ...]]
    original_index: int
    screen_index: Optional[int]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrBox":
        values = _known_values(cls, data)
        values["bbox"] = _bbox_from_value(values.get("bbox"))
        return cls(**values)


@dataclass(frozen=True)
class OcrTextSegment(JsonRecordMixin):
    segment_id: str
    screen_index: Optional[int]
    order: Optional[int] = None
    normalized_text: Optional[str] = None
    comparison_text: Optional[str] = None
    ocr_box_ids: Tuple[str, ...] = ()
    char_count: Optional[int] = None
    processing_status: ProcessingStatus = ProcessingStatus.NOT_IMPLEMENTED

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrTextSegment":
        values = _known_values(cls, data)
        values["ocr_box_ids"] = tuple(values.get("ocr_box_ids") or ())
        values["processing_status"] = _enum_value(
            ProcessingStatus,
            values.get("processing_status", ProcessingStatus.NOT_IMPLEMENTED),
        )
        return cls(**values)


@dataclass(frozen=True)
class OcrScreenRecord(JsonRecordMixin):
    run_id: str
    candidate_record_id: str
    screen_id: str
    screen_index: Optional[int]
    attempt_index: int
    capture_type: CaptureType
    is_formal_screen: bool
    captured_at: str
    raw_boxes: Tuple[OcrBox, ...]
    raw_text: str
    record_type: str = "ocr_screen"
    storage_schema_version: str = STORAGE_SCHEMA_VERSION
    normalized_text: Optional[str] = None
    comparison_text: Optional[str] = None
    segments: Tuple[OcrTextSegment, ...] = ()
    exact_hash: Optional[str] = None
    fingerprint_version: Optional[str] = None
    similarity_hash: Optional[str] = None
    similarity_score: Optional[float] = None
    overlap_text: Optional[str] = None
    new_text: Optional[str] = None
    overlap_char_count: Optional[int] = None
    new_text_char_count: Optional[int] = None
    overlap_segment_count: Optional[int] = None
    new_segment_count: Optional[int] = None
    overlap_ratio: Optional[float] = None
    new_text_ratio: Optional[float] = None
    has_effective_new_text: Optional[bool] = None
    duplicate_risk: Optional[bool] = None
    processing_status: ProcessingStatus = ProcessingStatus.RAW_ONLY
    normalization_version: Optional[str] = None
    aggregation_version: Optional[str] = None
    similarity_version: Optional[str] = None
    dynamic_end_version: Optional[str] = None

    def __post_init__(self) -> None:
        validate_timezone_iso(self.captured_at)
        validate_record_version(
            {"storage_schema_version": self.storage_schema_version},
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrScreenRecord":
        validate_record_version(
            data,
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )
        values = _known_values(cls, data)
        values["capture_type"] = _enum_value(
            CaptureType, values["capture_type"]
        )
        values["processing_status"] = _enum_value(
            ProcessingStatus,
            values.get("processing_status", ProcessingStatus.RAW_ONLY),
        )
        values["raw_boxes"] = tuple(
            item if isinstance(item, OcrBox) else OcrBox.from_dict(item)
            for item in values.get("raw_boxes") or ()
        )
        values["segments"] = tuple(
            item
            if isinstance(item, OcrTextSegment)
            else OcrTextSegment.from_dict(item)
            for item in values.get("segments") or ()
        )
        return cls(**values)


@dataclass(frozen=True)
class CaptureSummary(JsonRecordMixin):
    actual_screen_count: Optional[int]
    ocr_attempt_count: Optional[int]
    scroll_attempt_count: Optional[int]
    scroll_retry_count: Optional[int]
    end_screen_index: Optional[int]
    capture_status: CaptureStatus
    end_reason: Optional[str]
    abort_reason: Optional[str]

    def __post_init__(self) -> None:
        validate_capture_outcome(
            self.capture_status,
            self.end_reason,
            self.abort_reason,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CaptureSummary":
        values = _known_values(cls, data)
        values["capture_status"] = _enum_value(
            CaptureStatus, values["capture_status"]
        )
        return cls(**values)


@dataclass(frozen=True)
class CandidateOcrDocument(JsonRecordMixin):
    run_id: str
    candidate_record_id: str
    sequence_number: int
    created_at: str
    completed_at: str
    capture_status: CaptureStatus
    screens: Tuple[OcrScreenRecord, ...]
    capture_summary: CaptureSummary
    record_type: str = "candidate_ocr_document"
    document_version: str = DOCUMENT_VERSION
    storage_schema_version: str = STORAGE_SCHEMA_VERSION
    document_text: Optional[str] = None
    document_segments: Tuple[OcrTextSegment, ...] = ()
    document_build_status: str = NOT_IMPLEMENTED
    versions: Dict[str, Optional[str]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_timezone_iso(self.created_at)
        validate_timezone_iso(self.completed_at)
        validate_record_version(
            {"document_version": self.document_version},
            "document_version",
            SUPPORTED_DOCUMENT_VERSIONS,
        )
        validate_record_version(
            {"storage_schema_version": self.storage_schema_version},
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )
        if self.capture_status != self.capture_summary.capture_status:
            raise ValueError(
                "candidate capture_status must match capture_summary"
            )
        if self.capture_status == CaptureStatus.EMPTY and (
            self.screens
            or self.capture_summary.actual_screen_count != 0
            or self.capture_summary.ocr_attempt_count != 0
        ):
            raise ValueError("empty captures cannot contain OCR observations")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CandidateOcrDocument":
        validate_record_version(
            data,
            "document_version",
            SUPPORTED_DOCUMENT_VERSIONS,
        )
        validate_record_version(
            data,
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )
        values = _known_values(cls, data)
        values["capture_status"] = _enum_value(
            CaptureStatus, values["capture_status"]
        )
        values["screens"] = tuple(
            item
            if isinstance(item, OcrScreenRecord)
            else OcrScreenRecord.from_dict(item)
            for item in values.get("screens") or ()
        )
        summary = values["capture_summary"]
        if not isinstance(summary, CaptureSummary):
            values["capture_summary"] = CaptureSummary.from_dict(summary)
        values["document_segments"] = tuple(
            item
            if isinstance(item, OcrTextSegment)
            else OcrTextSegment.from_dict(item)
            for item in values.get("document_segments") or ()
        )
        values["versions"] = dict(values.get("versions") or {})
        values["metadata"] = dict(values.get("metadata") or {})
        return cls(**values)


@dataclass
class RunManifest(JsonRecordMixin):
    run_id: str
    started_at: str
    status: RunStatus
    platform: str
    python_version: str
    data_files: Dict[str, str]
    storage_schema_version: str = STORAGE_SCHEMA_VERSION
    ended_at: Optional[str] = None
    action_mode: Optional[str] = None
    max_screen_count: Optional[int] = None
    app_version: Optional[str] = None
    git_commit: Optional[str] = None
    normalization_version: Optional[str] = None
    aggregation_version: Optional[str] = None
    similarity_version: Optional[str] = None
    dynamic_end_version: Optional[str] = None
    error_count: int = 0
    candidate_record_count: int = 0
    screen_record_count: int = 0

    def __post_init__(self) -> None:
        validate_timezone_iso(self.started_at)
        if self.ended_at is not None:
            validate_timezone_iso(self.ended_at)
        validate_record_version(
            {"storage_schema_version": self.storage_schema_version},
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunManifest":
        validate_record_version(
            data,
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )
        values = _known_values(cls, data)
        values["status"] = _enum_value(RunStatus, values["status"])
        values["data_files"] = {
            key: str(value)
            for key, value in dict(values.get("data_files") or {}).items()
        }
        return cls(**values)
