"""OCR evidence records and JSON-compatible serialization helpers.

The stage-0 evidence model remains authoritative.  R04 extends that same
record with replayable derived text; later aggregation, similarity, and
dynamic-end fields remain explicitly unimplemented.
"""

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import math
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple, Type, TypeVar


LEGACY_STORAGE_SCHEMA_VERSION = "1.0.0"
R04_STORAGE_SCHEMA_VERSION = "1.1.0"
STORAGE_SCHEMA_VERSION = "1.2.0"
DOCUMENT_VERSION = "stage0-v1"
R05_DOCUMENT_VERSION = "r05-document-v1"
SUPPORTED_STORAGE_SCHEMA_VERSIONS = (
    LEGACY_STORAGE_SCHEMA_VERSION,
    R04_STORAGE_SCHEMA_VERSION,
    STORAGE_SCHEMA_VERSION,
)
SUPPORTED_DOCUMENT_VERSIONS = (DOCUMENT_VERSION, R05_DOCUMENT_VERSION)
NOT_IMPLEMENTED = "not_implemented"
R04_NORMALIZATION_VERSION = "r04-v1"
R04_NORMALIZATION_CONFIG_VERSION = "r04-config-v1"
RULE_EVALUATION_MODE_LEGACY_SHADOW = "legacy_shadow"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_SANITIZED_ERROR_TYPE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,127}\Z")


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
    NORMALIZED = "normalized"
    NOT_IMPLEMENTED = NOT_IMPLEMENTED


class NormalizationStatus(str, Enum):
    """R04 processing state, independent from raw evidence availability."""

    NOT_ATTEMPTED = "not_attempted"
    COMPLETED = "completed"
    FAILED = "failed"


class AggregationStatus(str, Enum):
    """R05 per-screen aggregation status, independent from R04 normalization."""

    NOT_ATTEMPTED = "not_attempted"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class DocumentBuildStatus(str, Enum):
    """R05 per-candidate document status, independent from capture status."""

    NOT_ATTEMPTED = "not_attempted"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class AggregationMatchType(str, Enum):
    ADJACENT_EXACT = "adjacent_exact"
    ADJACENT_FUZZY_1_1 = "adjacent_fuzzy_1_1"
    ADJACENT_FUZZY_1_2 = "adjacent_fuzzy_1_2"
    ADJACENT_FUZZY_2_1 = "adjacent_fuzzy_2_1"
    HISTORICAL_EXACT = "historical_exact"


class AggregationDuplicateRisk(str, Enum):
    NONE = "none"
    LOW = "low"
    ELEVATED = "elevated"


class AggregationOccurrenceRole(str, Enum):
    ORIGIN = "origin"
    MATCHED = "matched"
    UNCERTAIN_ORIGIN = "uncertain_origin"


AGGREGATION_WARNING_CODES = frozenset({
    "no_formal_screen",
    "r04_not_completed",
    "segment_mapping_invalid",
    "formal_screen_index_invalid",
    "formal_screen_out_of_order",
    "duplicate_screen_id_conflict",
    "duplicate_formal_screen_index",
    "screen_segment_limit_exceeded",
    "fuzzy_below_threshold",
    "fuzzy_ambiguous_tie",
    "fuzzy_candidate_limit_exceeded",
    "historical_duplicate_ambiguous",
    "historical_context_insufficient",
    "historical_mapping_conflict",
    "exact_stage_failed",
    "fuzzy_stage_failed",
    "historical_stage_failed",
    "candidate_interrupted",
    "candidate_aborted",
    "screen_aggregation_partial",
    "screen_aggregation_failed",
    "mixed_aggregation_version",
    "finalize_failed",
})

_DOCUMENT_SEGMENT_ID_PATTERN = re.compile(r"document:segment:(0|[1-9][0-9]*)\Z")
_MATCH_ID_PATTERN = re.compile(r"match:([1-9][0-9]*):(0|[1-9][0-9]*)\Z")


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


def _bbox_from_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return tuple(_bbox_from_value(item) for item in value)
    return value


class JsonRecordMixin:
    """Shared conversion API for stage-0 data objects."""

    def to_dict(self) -> Dict[str, Any]:
        return to_json_compatible(self)

    def to_json(self) -> str:
        return json_dumps(self)


def canonical_mapping_digest(value: Mapping[str, Any]) -> str:
    """Return the frozen SHA-256 identity for one canonical config mapping."""

    if not isinstance(value, Mapping):
        raise ValueError("normalization config must be an object")
    if "normalization_config_digest" in value:
        raise ValueError("normalization config cannot contain its digest")
    try:
        serialized = json.dumps(
            to_json_compatible(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("normalization config is not canonicalizable") from exc
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_non_negative_optional_count(name: str, value: Optional[int]) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise ValueError("{0} must be a non-negative integer or null".format(name))


def _validate_config_identity(
    *,
    normalization_version: Optional[str],
    normalization_config_version: Optional[str],
    normalization_config_digest: Optional[str],
    effective_min_confidence: Optional[float],
    rule_evaluation_mode: Optional[str],
) -> None:
    if normalization_version != R04_NORMALIZATION_VERSION:
        raise ValueError("normalization version is invalid")
    if normalization_config_version != R04_NORMALIZATION_CONFIG_VERSION:
        raise ValueError("normalization config version is invalid")
    if (
        not isinstance(normalization_config_digest, str)
        or _SHA256_PATTERN.fullmatch(normalization_config_digest) is None
    ):
        raise ValueError("normalization config digest is invalid")
    if (
        isinstance(effective_min_confidence, bool)
        or not isinstance(effective_min_confidence, (int, float))
        or not math.isfinite(float(effective_min_confidence))
        or not 0.0 <= float(effective_min_confidence) <= 1.0
    ):
        raise ValueError("effective min confidence is invalid")
    if rule_evaluation_mode != RULE_EVALUATION_MODE_LEGACY_SHADOW:
        raise ValueError("rule evaluation mode is invalid")


@dataclass(frozen=True)
class OcrBox(JsonRecordMixin):
    box_id: str
    raw_text: str
    confidence: Optional[float]
    bbox: Any
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


def _is_non_negative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_nonempty_unique_strings(name: str, values: Tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise ValueError("{0} must be a tuple".format(name))
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise ValueError("{0} must contain non-empty strings".format(name))
    if len(set(values)) != len(values):
        raise ValueError("{0} cannot contain duplicates".format(name))


def _validate_ordered_source_ids(
    values: Tuple[str, ...],
    *,
    source_screen_id: str,
    marker: str,
    name: str,
) -> None:
    _validate_nonempty_unique_strings(name, values)
    prefix = "{0}:{1}:".format(source_screen_id, marker)
    orders = []
    for value in values:
        if not value.startswith(prefix):
            raise ValueError("{0} has an invalid source screen".format(name))
        suffix = value[len(prefix):]
        if not suffix.isdecimal():
            raise ValueError("{0} has an invalid ID".format(name))
        orders.append(int(suffix))
    if orders != sorted(orders):
        raise ValueError("{0} are not in source order".format(name))


def _validate_document_segment_id(segment_id: str, order: int) -> None:
    if not isinstance(segment_id, str):
        raise ValueError("document segment ID is invalid")
    matched = _DOCUMENT_SEGMENT_ID_PATTERN.fullmatch(segment_id)
    if matched is None or int(matched.group(1)) != order:
        raise ValueError("document segment ID does not match order")


def _validate_match_id(value: str, screen_index: Optional[int] = None) -> None:
    if not isinstance(value, str):
        raise ValueError("match ID is invalid")
    matched = _MATCH_ID_PATTERN.fullmatch(value)
    if matched is None:
        raise ValueError("match ID is invalid")
    if screen_index is not None and int(matched.group(1)) != screen_index:
        raise ValueError("match ID screen index is invalid")


@dataclass(frozen=True)
class OcrSourceOccurrence(JsonRecordMixin):
    occurrence_order: int
    source_screen_id: str
    source_screen_index: int
    source_segment_ids: Tuple[str, ...]
    source_ocr_box_ids: Tuple[str, ...]
    occurrence_role: AggregationOccurrenceRole
    match_id: Optional[str]

    def __post_init__(self) -> None:
        if not _is_non_negative_int(self.occurrence_order):
            raise ValueError("occurrence order is invalid")
        if not isinstance(self.source_screen_id, str) or not self.source_screen_id:
            raise ValueError("source screen ID is invalid")
        if (
            not isinstance(self.source_screen_index, int)
            or isinstance(self.source_screen_index, bool)
            or self.source_screen_index < 1
        ):
            raise ValueError("source screen index is invalid")
        _validate_ordered_source_ids(
            self.source_segment_ids,
            source_screen_id=self.source_screen_id,
            marker="line",
            name="source segment IDs",
        )
        _validate_ordered_source_ids(
            self.source_ocr_box_ids,
            source_screen_id=self.source_screen_id,
            marker="box",
            name="source OCR box IDs",
        )
        role = _enum_value(AggregationOccurrenceRole, self.occurrence_role)
        if role == AggregationOccurrenceRole.MATCHED:
            if self.match_id is None:
                raise ValueError("matched occurrence requires match ID")
        elif self.match_id is not None:
            raise ValueError("origin occurrence cannot have match ID")
        if self.match_id is not None:
            _validate_match_id(self.match_id, self.source_screen_index)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrSourceOccurrence":
        values = _known_values(cls, data)
        values["source_segment_ids"] = tuple(values.get("source_segment_ids") or ())
        values["source_ocr_box_ids"] = tuple(values.get("source_ocr_box_ids") or ())
        values["occurrence_role"] = _enum_value(
            AggregationOccurrenceRole, values["occurrence_role"]
        )
        return cls(**values)


@dataclass(frozen=True)
class OcrDocumentSegment(JsonRecordMixin):
    document_segment_id: str
    order: int
    normalized_text: str
    comparison_text: str
    comparison_char_count: int
    source_occurrences: Tuple[OcrSourceOccurrence, ...]

    def __post_init__(self) -> None:
        if not _is_non_negative_int(self.order):
            raise ValueError("document segment order is invalid")
        _validate_document_segment_id(self.document_segment_id, self.order)
        if not isinstance(self.normalized_text, str) or not self.normalized_text:
            raise ValueError("document segment normalized text is invalid")
        if not isinstance(self.comparison_text, str) or not self.comparison_text:
            raise ValueError("document segment comparison text is invalid")
        from ocr_normalization import build_comparison_text

        if self.comparison_text != build_comparison_text(self.normalized_text):
            raise ValueError("document segment comparison text is invalid")
        if any(character.isspace() for character in self.comparison_text):
            raise ValueError("document segment comparison text has whitespace")
        if (
            not _is_non_negative_int(self.comparison_char_count)
            or self.comparison_char_count != len(self.comparison_text)
        ):
            raise ValueError("document segment comparison character count is invalid")
        if not isinstance(self.source_occurrences, tuple):
            raise ValueError("document segment occurrences must be a tuple")
        if not self.source_occurrences:
            raise ValueError("document segment requires source occurrences")
        if any(
            not isinstance(item, OcrSourceOccurrence)
            for item in self.source_occurrences
        ):
            raise ValueError("document segment occurrence is invalid")
        if tuple(item.occurrence_order for item in self.source_occurrences) != tuple(
            range(len(self.source_occurrences))
        ):
            raise ValueError("document segment occurrence order is invalid")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrDocumentSegment":
        values = _known_values(cls, data)
        values["source_occurrences"] = tuple(
            item
            if isinstance(item, OcrSourceOccurrence)
            else OcrSourceOccurrence.from_dict(item)
            for item in values.get("source_occurrences") or ()
        )
        return cls(**values)


@dataclass(frozen=True)
class OcrSegmentMatchEvidence(JsonRecordMixin):
    match_id: str
    match_type: AggregationMatchType
    current_screen_id: str
    current_screen_index: int
    current_segment_ids: Tuple[str, ...]
    current_ocr_box_ids: Tuple[str, ...]
    matched_document_segment_ids: Tuple[str, ...]
    score: Optional[float]
    exact_basis: Optional[str]
    risk: AggregationDuplicateRisk
    warning_codes: Tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.current_screen_index, int)
            or isinstance(self.current_screen_index, bool)
            or self.current_screen_index < 1
        ):
            raise ValueError("current screen index is invalid")
        _validate_match_id(self.match_id, self.current_screen_index)
        if not isinstance(self.current_screen_id, str) or not self.current_screen_id:
            raise ValueError("current screen ID is invalid")
        _validate_ordered_source_ids(
            self.current_segment_ids,
            source_screen_id=self.current_screen_id,
            marker="line",
            name="current segment IDs",
        )
        _validate_ordered_source_ids(
            self.current_ocr_box_ids,
            source_screen_id=self.current_screen_id,
            marker="box",
            name="current OCR box IDs",
        )
        _validate_nonempty_unique_strings(
            "matched document segment IDs", self.matched_document_segment_ids
        )
        for index, segment_id in enumerate(self.matched_document_segment_ids):
            _validate_document_segment_id(segment_id, int(segment_id.rsplit(":", 1)[1]))
        match_type = _enum_value(AggregationMatchType, self.match_type)
        risk = _enum_value(AggregationDuplicateRisk, self.risk)
        exact_types = {
            AggregationMatchType.ADJACENT_EXACT,
            AggregationMatchType.HISTORICAL_EXACT,
        }
        if match_type in exact_types:
            if self.score is not None:
                raise ValueError("exact match score must be null")
            if not isinstance(self.exact_basis, str) or not self.exact_basis:
                raise ValueError("exact match basis is invalid")
            if risk != AggregationDuplicateRisk.NONE:
                raise ValueError("exact match risk is invalid")
        else:
            if (
                isinstance(self.score, bool)
                or not isinstance(self.score, (int, float))
                or not math.isfinite(float(self.score))
                or not 0.0 <= float(self.score) <= 1.0
            ):
                raise ValueError("fuzzy match score is invalid")
            if self.exact_basis is not None:
                raise ValueError("fuzzy match cannot have exact basis")
            if risk != AggregationDuplicateRisk.LOW:
                raise ValueError("fuzzy match risk is invalid")
        if any(code not in AGGREGATION_WARNING_CODES for code in self.warning_codes):
            raise ValueError("aggregation warning code is invalid")
        if len(set(self.warning_codes)) != len(self.warning_codes):
            raise ValueError("aggregation warning codes cannot repeat")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrSegmentMatchEvidence":
        values = _known_values(cls, data)
        for field_name in (
            "current_segment_ids",
            "current_ocr_box_ids",
            "matched_document_segment_ids",
            "warning_codes",
        ):
            values[field_name] = tuple(values.get(field_name) or ())
        values["match_type"] = _enum_value(
            AggregationMatchType, values["match_type"]
        )
        values["risk"] = _enum_value(AggregationDuplicateRisk, values["risk"])
        return cls(**values)


@dataclass(frozen=True)
class OcrLineMapping(JsonRecordMixin):
    box_id: str
    line_index: int

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrLineMapping":
        return cls(**_known_values(cls, data))


@dataclass(frozen=True)
class OcrNormalizationWarning(JsonRecordMixin):
    box_id: str
    code: str

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any]
    ) -> "OcrNormalizationWarning":
        return cls(**_known_values(cls, data))


@dataclass(frozen=True)
class OcrDuplicatePairEvidence(JsonRecordMixin):
    left_box_id: str
    right_box_id: str
    text_similarity: float
    text_exact: bool
    iou: float
    horizontal_overlap_ratio: float
    vertical_overlap_ratio: float
    center_distance_ratio: float
    center_distance_size_ratio: float
    width_similarity: float
    height_similarity: float
    size_similarity: float
    decision: str
    basis: Tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any]
    ) -> "OcrDuplicatePairEvidence":
        values = _known_values(cls, data)
        values["basis"] = tuple(values.get("basis") or ())
        return cls(**values)


@dataclass(frozen=True)
class OcrDuplicateGroup(JsonRecordMixin):
    retained_box_id: str
    suppressed_duplicate_box_ids: Tuple[str, ...]
    source_box_ids: Tuple[str, ...]
    pair_evidence: Tuple[OcrDuplicatePairEvidence, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrDuplicateGroup":
        values = _known_values(cls, data)
        values["suppressed_duplicate_box_ids"] = tuple(
            values.get("suppressed_duplicate_box_ids") or ()
        )
        values["source_box_ids"] = tuple(values.get("source_box_ids") or ())
        values["pair_evidence"] = tuple(
            item
            if isinstance(item, OcrDuplicatePairEvidence)
            else OcrDuplicatePairEvidence.from_dict(item)
            for item in values.get("pair_evidence") or ()
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
    raw_text_source: Optional[str] = None
    raw_text_length: Optional[int] = None
    normalized_text: Optional[str] = None
    normalized_text_length: Optional[int] = None
    comparison_text: Optional[str] = None
    comparison_text_length: Optional[int] = None
    segments: Tuple[OcrTextSegment, ...] = ()
    ordered_box_ids: Tuple[str, ...] = ()
    effective_box_ids: Tuple[str, ...] = ()
    excluded_empty_box_ids: Tuple[str, ...] = ()
    suppressed_duplicate_box_ids: Tuple[str, ...] = ()
    line_mapping: Tuple[OcrLineMapping, ...] = ()
    deduplicated_box_count: Optional[int] = None
    duplicate_groups: Tuple[OcrDuplicateGroup, ...] = ()
    exact_hash: Optional[str] = None
    fingerprint_version: Optional[str] = None
    rule_evaluation_mode: Optional[str] = None
    legacy_match: Optional[bool] = None
    r04_match: Optional[bool] = None
    comparison_outcome: Optional[str] = None
    legacy_rule_index: Optional[int] = None
    r04_rule_index: Optional[int] = None
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
    duplicate_gray_pair_count: Optional[int] = None
    eligible_box_count: Optional[int] = None
    low_confidence_box_count: Optional[int] = None
    empty_normalized_box_count: Optional[int] = None
    processing_status: ProcessingStatus = ProcessingStatus.RAW_ONLY
    normalization_status: NormalizationStatus = (
        NormalizationStatus.NOT_ATTEMPTED
    )
    normalization_warnings: Tuple[OcrNormalizationWarning, ...] = ()
    normalization_error_type: Optional[str] = None
    normalization_version: Optional[str] = None
    normalization_config_version: Optional[str] = None
    normalization_config_digest: Optional[str] = None
    effective_min_confidence: Optional[float] = None
    confidence_threshold_source: Optional[str] = None
    ocr_min_confidence: Optional[float] = None
    aggregation_status: AggregationStatus = AggregationStatus.NOT_ATTEMPTED
    aggregation_version: Optional[str] = None
    aggregation_config_version: Optional[str] = None
    aggregation_config_digest: Optional[str] = None
    matched_segment_ids: Tuple[str, ...] = ()
    new_segment_ids: Tuple[str, ...] = ()
    uncertain_segment_ids: Tuple[str, ...] = ()
    match_evidence: Tuple[OcrSegmentMatchEvidence, ...] = ()
    aggregation_warning_codes: Tuple[str, ...] = ()
    aggregation_duplicate_risk: Optional[AggregationDuplicateRisk] = None
    certain_new_segment_count: Optional[int] = None
    uncertain_segment_count: Optional[int] = None
    uncertain_char_count: Optional[int] = None
    similarity_version: Optional[str] = None
    dynamic_end_version: Optional[str] = None

    def __post_init__(self) -> None:
        validate_timezone_iso(self.captured_at)
        validate_record_version(
            {"storage_schema_version": self.storage_schema_version},
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )
        if self.storage_schema_version in (
            R04_STORAGE_SCHEMA_VERSION,
            STORAGE_SCHEMA_VERSION,
        ):
            self._validate_r04_contract()
        if self.storage_schema_version == STORAGE_SCHEMA_VERSION:
            self._validate_r05_contract()

    def _validate_r04_contract(self) -> None:
        status = _enum_value(NormalizationStatus, self.normalization_status)
        processing_status = _enum_value(ProcessingStatus, self.processing_status)
        identity = (
            self.normalization_version,
            self.normalization_config_version,
            self.normalization_config_digest,
            self.effective_min_confidence,
            self.rule_evaluation_mode,
        )
        count_names = (
            "duplicate_gray_pair_count",
            "eligible_box_count",
            "low_confidence_box_count",
            "empty_normalized_box_count",
        )
        for name in count_names:
            _validate_non_negative_optional_count(name, getattr(self, name))

        if status == NormalizationStatus.NOT_ATTEMPTED:
            if processing_status != ProcessingStatus.RAW_ONLY:
                raise ValueError("not-attempted normalization must be raw-only")
            if any(value is not None for value in identity):
                raise ValueError("not-attempted normalization cannot have config identity")
            if (
                self.normalized_text is not None
                or self.comparison_text is not None
                or self.segments
                or self.normalization_error_type is not None
                or self.confidence_threshold_source is not None
                or any(getattr(self, name) is not None for name in count_names)
            ):
                raise ValueError("not-attempted normalization has derived fields")
        else:
            _validate_config_identity(
                normalization_version=self.normalization_version,
                normalization_config_version=self.normalization_config_version,
                normalization_config_digest=self.normalization_config_digest,
                effective_min_confidence=self.effective_min_confidence,
                rule_evaluation_mode=self.rule_evaluation_mode,
            )
            if not isinstance(self.confidence_threshold_source, str) or not self.confidence_threshold_source:
                raise ValueError("executed normalization requires confidence source")
            if any(getattr(self, name) is None for name in count_names):
                raise ValueError("executed normalization requires trace counts")
            if status == NormalizationStatus.COMPLETED:
                if processing_status != ProcessingStatus.NORMALIZED:
                    raise ValueError("completed normalization must be normalized")
                if not isinstance(self.normalized_text, str) or not isinstance(
                    self.comparison_text, str
                ):
                    raise ValueError("completed normalization requires text strings")
                if self.normalization_error_type is not None:
                    raise ValueError("completed normalization cannot have an error")
            elif status == NormalizationStatus.FAILED:
                if processing_status != ProcessingStatus.RAW_ONLY:
                    raise ValueError("failed normalization must be raw-only")
                if self.normalized_text is not None or self.comparison_text is not None or self.segments:
                    raise ValueError("failed normalization cannot have derived text")
                if (
                    not isinstance(self.normalization_error_type, str)
                    or _SANITIZED_ERROR_TYPE_PATTERN.fullmatch(
                        self.normalization_error_type
                    )
                    is None
                ):
                    raise ValueError("failed normalization requires a sanitized error type")

        raw_ids = tuple(box.box_id for box in self.raw_boxes)
        if len(set(raw_ids)) != len(raw_ids):
            raise ValueError("raw OCR box IDs must be unique")
        raw_id_set = set(raw_ids)
        suppressed = set(self.suppressed_duplicate_box_ids)
        if not suppressed.issubset(raw_id_set):
            raise ValueError("suppressed duplicate box ID is missing from raw boxes")
        effective = set(self.effective_box_ids)
        if not effective.issubset(raw_id_set) or effective & suppressed:
            raise ValueError("effective OCR box mapping is invalid")
        for field_name in (
            "ordered_box_ids",
            "excluded_empty_box_ids",
        ):
            if not set(getattr(self, field_name)).issubset(raw_id_set):
                raise ValueError("OCR box trace references missing raw evidence")
        if status == NormalizationStatus.COMPLETED:
            if self.ordered_box_ids != self.effective_box_ids:
                raise ValueError("ordered and effective OCR box IDs must match")
            if (
                self.eligible_box_count + self.low_confidence_box_count
                != len(self.raw_boxes)
            ):
                raise ValueError("OCR eligibility counts do not match raw boxes")
            if (
                len(self.effective_box_ids)
                + len(self.suppressed_duplicate_box_ids)
                + len(self.excluded_empty_box_ids)
                != self.eligible_box_count
            ):
                raise ValueError("OCR derived box partitions do not match eligibility")
        for order, segment in enumerate(self.segments):
            if segment.segment_id != "{0}:line:{1}".format(self.screen_id, order):
                raise ValueError("OCR segment ID is invalid")
            if segment.order != order:
                raise ValueError("OCR segment order is invalid")
            source_ids = set(segment.ocr_box_ids)
            if not source_ids.issubset(raw_id_set) or not source_ids.issubset(effective):
                raise ValueError("OCR segment references a non-survivor box")
        segment_box_ids = tuple(
            box_id for segment in self.segments for box_id in segment.ocr_box_ids
        )
        if status == NormalizationStatus.COMPLETED and segment_box_ids != self.effective_box_ids:
            raise ValueError("OCR segments do not map all survivors in order")
        if status == NormalizationStatus.COMPLETED:
            mapping_ids = tuple(value.box_id for value in self.line_mapping)
            if mapping_ids != self.effective_box_ids:
                raise ValueError("OCR line mapping does not map all survivors in order")
        if self.deduplicated_box_count is not None and self.deduplicated_box_count != len(
            self.effective_box_ids
        ):
            raise ValueError("deduplicated box count does not match survivors")
        if self.empty_normalized_box_count is not None and self.empty_normalized_box_count != len(
            self.excluded_empty_box_ids
        ):
            raise ValueError("empty normalized box count does not match trace")
        if self.duplicate_gray_pair_count is not None and bool(
            self.duplicate_gray_pair_count
        ) != bool(self.duplicate_risk):
            raise ValueError("duplicate gray count does not match duplicate risk")
        for group in self.duplicate_groups:
            group_suppressed = set(group.suppressed_duplicate_box_ids)
            if (
                group.retained_box_id not in effective
                or not group_suppressed.issubset(suppressed)
                or not set(group.source_box_ids).issubset(raw_id_set)
                or set(group.source_box_ids)
                != {group.retained_box_id, *group_suppressed}
            ):
                raise ValueError("duplicate group trace is invalid")

        shadow_values = (
            self.legacy_match,
            self.r04_match,
            self.comparison_outcome,
            self.legacy_rule_index,
            self.r04_rule_index,
        )
        if any(value is not None for value in shadow_values):
            if not isinstance(self.legacy_match, bool):
                raise ValueError("legacy shadow requires legacy_match")
            if self.r04_match is not None and not isinstance(self.r04_match, bool):
                raise ValueError("legacy shadow r04_match is invalid")
            if self.comparison_outcome not in {
                "same_match",
                "same_no_match",
                "legacy_only",
                "r04_only",
                "normalization_failed",
            }:
                raise ValueError("legacy shadow outcome is invalid")
            if self.normalization_status == NormalizationStatus.FAILED and self.r04_match is not None:
                raise ValueError("failed normalization cannot have r04_match")
            for value in (self.legacy_rule_index, self.r04_rule_index):
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                ):
                    raise ValueError("legacy shadow rule index is invalid")

    def _validate_r05_contract(self) -> None:
        status = _enum_value(AggregationStatus, self.aggregation_status)
        identity = (
            self.aggregation_version,
            self.aggregation_config_version,
            self.aggregation_config_digest,
        )
        classifications = (
            self.matched_segment_ids,
            self.new_segment_ids,
            self.uncertain_segment_ids,
        )
        projections = (
            self.overlap_text,
            self.new_text,
            self.overlap_char_count,
            self.new_text_char_count,
            self.overlap_segment_count,
            self.new_segment_count,
            self.certain_new_segment_count,
            self.uncertain_segment_count,
            self.uncertain_char_count,
        )
        if status == AggregationStatus.NOT_ATTEMPTED:
            if (
                any(value is not None for value in identity)
                or any(classifications)
                or self.match_evidence
                or self.aggregation_warning_codes
                or self.aggregation_duplicate_risk is not None
                or any(value is not None for value in projections)
            ):
                raise ValueError("not-attempted aggregation has derived fields")
            return
        if (
            self.aggregation_version != "r05-v1"
            or self.aggregation_config_version != "r05-config-v1"
            or not isinstance(self.aggregation_config_digest, str)
            or _SHA256_PATTERN.fullmatch(self.aggregation_config_digest) is None
        ):
            raise ValueError("attempted aggregation requires config identity")
        if any(
            not isinstance(value, tuple) for value in classifications + (
                self.match_evidence, self.aggregation_warning_codes,
            )
        ):
            raise ValueError("aggregation collections must be tuples")
        if any(code not in AGGREGATION_WARNING_CODES for code in self.aggregation_warning_codes):
            raise ValueError("aggregation warning code is invalid")
        if len(set(self.aggregation_warning_codes)) != len(self.aggregation_warning_codes):
            raise ValueError("aggregation warning code is duplicated")
        if status == AggregationStatus.FAILED:
            if any(classifications) or self.match_evidence or any(value is not None for value in projections):
                raise ValueError("failed aggregation cannot have classifications")
            if not self.aggregation_warning_codes or self.aggregation_duplicate_risk != AggregationDuplicateRisk.ELEVATED:
                raise ValueError("failed aggregation requires elevated warning risk")
            return
        if self.normalization_status != NormalizationStatus.COMPLETED:
            raise ValueError("successful aggregation requires completed normalization")
        segment_by_id = {segment.segment_id: segment for segment in self.segments}
        classified = self.matched_segment_ids + self.new_segment_ids + self.uncertain_segment_ids
        if (
            len(classified) != len(set(classified))
            or any(identifier not in segment_by_id for identifier in classified)
            or classified != tuple(
                segment.segment_id for segment in self.segments
                if segment.segment_id in classified
            )
            or set(classified) != set(segment_by_id)
        ):
            raise ValueError("aggregation segment classifications are invalid")
        evidence_ids = set()
        evidence_match_ids = set()
        for evidence in self.match_evidence:
            if not isinstance(evidence, OcrSegmentMatchEvidence):
                raise ValueError("aggregation evidence is invalid")
            if evidence.current_screen_id != self.screen_id or evidence.current_screen_index != self.screen_index:
                raise ValueError("aggregation evidence screen identity is invalid")
            if evidence.match_id in evidence_match_ids:
                raise ValueError("aggregation evidence match ID is duplicated")
            evidence_match_ids.add(evidence.match_id)
            if (
                any(identifier not in segment_by_id for identifier in evidence.current_segment_ids)
                or any(identifier not in {box.box_id for box in self.raw_boxes}
                       for identifier in evidence.current_ocr_box_ids)
                or evidence_ids.intersection(evidence.current_segment_ids)
            ):
                raise ValueError("aggregation evidence source is invalid")
            evidence_ids.update(evidence.current_segment_ids)
        if evidence_ids != set(self.matched_segment_ids):
            raise ValueError("matched aggregation segments lack evidence")
        def project(identifiers: Tuple[str, ...]) -> Tuple[str, int]:
            selected = tuple(segment_by_id[identifier] for identifier in identifiers)
            return "\n".join(segment.normalized_text for segment in selected), sum(
                len(segment.comparison_text) for segment in selected
            )
        expected_overlap, expected_overlap_chars = project(self.matched_segment_ids)
        contribution_ids = self.new_segment_ids + self.uncertain_segment_ids
        expected_new, expected_new_chars = project(contribution_ids)
        expected_uncertain_chars = project(self.uncertain_segment_ids)[1]
        expected_projections = (
            expected_overlap,
            expected_new,
            expected_overlap_chars,
            expected_new_chars,
            len(self.matched_segment_ids),
            len(contribution_ids),
            len(self.new_segment_ids),
            len(self.uncertain_segment_ids),
            expected_uncertain_chars,
        )
        if projections != expected_projections:
            raise ValueError("aggregation projection is invalid")
        risk = _enum_value(AggregationDuplicateRisk, self.aggregation_duplicate_risk)
        if status == AggregationStatus.COMPLETED:
            if self.uncertain_segment_ids or self.aggregation_warning_codes or risk == AggregationDuplicateRisk.ELEVATED:
                raise ValueError("completed aggregation cannot be uncertain")
        elif status == AggregationStatus.PARTIAL:
            if not (self.uncertain_segment_ids or self.aggregation_warning_codes) or risk != AggregationDuplicateRisk.ELEVATED:
                raise ValueError("partial aggregation requires uncertainty")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrScreenRecord":
        storage_version = validate_record_version(
            data,
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )
        values = _known_values(cls, data)
        if storage_version in (R04_STORAGE_SCHEMA_VERSION, STORAGE_SCHEMA_VERSION):
            required_fields = (
                "processing_status",
                "normalization_status",
                "normalization_version",
                "normalization_config_version",
                "normalization_config_digest",
                "effective_min_confidence",
                "normalized_text",
                "comparison_text",
                "segments",
                "normalization_error_type",
            )
            if any(field_name not in data for field_name in required_fields):
                raise ValueError("R04 screen schema fields are incomplete")
        if storage_version == STORAGE_SCHEMA_VERSION:
            required_aggregation_fields = (
                "aggregation_status", "aggregation_version",
                "aggregation_config_version", "aggregation_config_digest",
                "matched_segment_ids", "new_segment_ids", "uncertain_segment_ids",
                "match_evidence", "aggregation_warning_codes",
                "aggregation_duplicate_risk", "overlap_text", "new_text",
                "overlap_char_count", "new_text_char_count", "overlap_segment_count",
                "new_segment_count", "certain_new_segment_count",
                "uncertain_segment_count", "uncertain_char_count",
            )
            if any(field_name not in data for field_name in required_aggregation_fields):
                raise ValueError("R05 screen schema fields are incomplete")
        if storage_version == LEGACY_STORAGE_SCHEMA_VERSION:
            for field_name in (
                "normalization_version",
                "normalization_config_version",
                "normalization_config_digest",
                "effective_min_confidence",
                "confidence_threshold_source",
                "rule_evaluation_mode",
                "legacy_match",
                "r04_match",
                "comparison_outcome",
                "legacy_rule_index",
                "r04_rule_index",
                "normalized_text",
                "normalized_text_length",
                "comparison_text",
                "comparison_text_length",
                "normalization_error_type",
                "deduplicated_box_count",
                "duplicate_risk",
                "duplicate_gray_pair_count",
                "eligible_box_count",
                "low_confidence_box_count",
                "empty_normalized_box_count",
            ):
                values[field_name] = None
            values["processing_status"] = ProcessingStatus.RAW_ONLY
            values["normalization_status"] = NormalizationStatus.NOT_ATTEMPTED
            values["segments"] = ()
            values["ordered_box_ids"] = ()
            values["effective_box_ids"] = ()
            values["excluded_empty_box_ids"] = ()
            values["suppressed_duplicate_box_ids"] = ()
            values["line_mapping"] = ()
            values["duplicate_groups"] = ()
            values["normalization_warnings"] = ()
        if storage_version != STORAGE_SCHEMA_VERSION:
            values.update({
                "aggregation_status": AggregationStatus.NOT_ATTEMPTED,
                "aggregation_version": None,
                "aggregation_config_version": None,
                "aggregation_config_digest": None,
                "matched_segment_ids": (),
                "new_segment_ids": (),
                "uncertain_segment_ids": (),
                "match_evidence": (),
                "aggregation_warning_codes": (),
                "aggregation_duplicate_risk": None,
                "overlap_text": None,
                "new_text": None,
                "overlap_char_count": None,
                "new_text_char_count": None,
                "overlap_segment_count": None,
                "new_segment_count": None,
                "certain_new_segment_count": None,
                "uncertain_segment_count": None,
                "uncertain_char_count": None,
            })
        values["capture_type"] = _enum_value(
            CaptureType, values["capture_type"]
        )
        values["processing_status"] = _enum_value(
            ProcessingStatus,
            values.get("processing_status", ProcessingStatus.RAW_ONLY),
        )
        values["normalization_status"] = _enum_value(
            NormalizationStatus,
            values.get(
                "normalization_status",
                NormalizationStatus.NOT_ATTEMPTED,
            ),
        )
        values["aggregation_status"] = _enum_value(
            AggregationStatus,
            values.get("aggregation_status", AggregationStatus.NOT_ATTEMPTED),
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
        for field_name in (
            "ordered_box_ids",
            "effective_box_ids",
            "excluded_empty_box_ids",
            "suppressed_duplicate_box_ids",
        ):
            values[field_name] = tuple(values.get(field_name) or ())
        values["line_mapping"] = tuple(
            item
            if isinstance(item, OcrLineMapping)
            else OcrLineMapping.from_dict(item)
            for item in values.get("line_mapping") or ()
        )
        values["duplicate_groups"] = tuple(
            item
            if isinstance(item, OcrDuplicateGroup)
            else OcrDuplicateGroup.from_dict(item)
            for item in values.get("duplicate_groups") or ()
        )
        values["normalization_warnings"] = tuple(
            item
            if isinstance(item, OcrNormalizationWarning)
            else OcrNormalizationWarning.from_dict(item)
            for item in values.get("normalization_warnings") or ()
        )
        for field_name in (
            "matched_segment_ids", "new_segment_ids", "uncertain_segment_ids",
            "aggregation_warning_codes",
        ):
            values[field_name] = tuple(values.get(field_name) or ())
        values["match_evidence"] = tuple(
            item if isinstance(item, OcrSegmentMatchEvidence)
            else OcrSegmentMatchEvidence.from_dict(item)
            for item in values.get("match_evidence") or ()
        )
        if values.get("aggregation_duplicate_risk") is not None:
            values["aggregation_duplicate_risk"] = _enum_value(
                AggregationDuplicateRisk, values["aggregation_duplicate_risk"]
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
class NormalizationSummary(JsonRecordMixin):
    formal_normalization_completed_count: int = 0
    formal_normalization_failed_count: int = 0
    formal_normalization_not_attempted_count: int = 0
    nonformal_normalization_completed_count: int = 0
    nonformal_normalization_failed_count: int = 0
    nonformal_normalization_not_attempted_count: int = 0

    def __post_init__(self) -> None:
        for item in fields(self):
            _validate_non_negative_optional_count(item.name, getattr(self, item.name))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NormalizationSummary":
        return cls(**_known_values(cls, data))


def recompute_normalization_summary(
    screens: Tuple[OcrScreenRecord, ...],
) -> NormalizationSummary:
    counts = {
        "formal_normalization_completed_count": 0,
        "formal_normalization_failed_count": 0,
        "formal_normalization_not_attempted_count": 0,
        "nonformal_normalization_completed_count": 0,
        "nonformal_normalization_failed_count": 0,
        "nonformal_normalization_not_attempted_count": 0,
    }
    for screen in screens:
        prefix = "formal" if screen.is_formal_screen else "nonformal"
        status = _enum_value(NormalizationStatus, screen.normalization_status).value
        counts["{0}_normalization_{1}_count".format(prefix, status)] += 1
    return NormalizationSummary(**counts)


@dataclass(frozen=True)
class AggregationSummary(JsonRecordMixin):
    formal_screen_count: int = 0
    completed_screen_count: int = 0
    partial_screen_count: int = 0
    failed_screen_count: int = 0
    matched_segment_count: int = 0
    new_segment_count: int = 0
    uncertain_segment_count: int = 0
    matched_char_count: int = 0
    new_char_count: int = 0
    uncertain_char_count: int = 0

    def __post_init__(self) -> None:
        for item in fields(self):
            _validate_non_negative_optional_count(item.name, getattr(self, item.name))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AggregationSummary":
        return cls(**_known_values(cls, data))


def recompute_aggregation_summary(
    screens: Tuple[OcrScreenRecord, ...],
) -> AggregationSummary:
    counts = {item.name: 0 for item in fields(AggregationSummary)}
    for screen in screens:
        if not (screen.capture_type == CaptureType.FORMAL_SCREEN and screen.is_formal_screen):
            continue
        counts["formal_screen_count"] += 1
        status = _enum_value(AggregationStatus, screen.aggregation_status)
        if status == AggregationStatus.COMPLETED:
            counts["completed_screen_count"] += 1
        elif status == AggregationStatus.PARTIAL:
            counts["partial_screen_count"] += 1
        elif status == AggregationStatus.FAILED:
            counts["failed_screen_count"] += 1
        counts["matched_segment_count"] += len(screen.matched_segment_ids)
        counts["new_segment_count"] += len(screen.new_segment_ids)
        counts["uncertain_segment_count"] += len(screen.uncertain_segment_ids)
        counts["matched_char_count"] += screen.overlap_char_count or 0
        counts["new_char_count"] += screen.new_text_char_count or 0
        counts["uncertain_char_count"] += screen.uncertain_char_count or 0
    return AggregationSummary(**counts)


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
    document_version: str = R05_DOCUMENT_VERSION
    storage_schema_version: str = STORAGE_SCHEMA_VERSION
    document_text: Optional[str] = None
    document_segments: Tuple[OcrDocumentSegment, ...] = ()
    document_build_status: DocumentBuildStatus = DocumentBuildStatus.NOT_ATTEMPTED
    normalization_summary: Optional[NormalizationSummary] = None
    aggregation_config_version: Optional[str] = None
    aggregation_config_digest: Optional[str] = None
    aggregation_warning_codes: Tuple[str, ...] = ()
    aggregation_duplicate_risk: Optional[AggregationDuplicateRisk] = None
    aggregation_summary: Optional[AggregationSummary] = None
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
        expected_summary = recompute_normalization_summary(self.screens)
        if self.normalization_summary is None:
            object.__setattr__(self, "normalization_summary", expected_summary)
        elif self.normalization_summary != expected_summary:
            raise ValueError("candidate normalization summary does not match screens")
        if self.storage_schema_version in (
            R04_STORAGE_SCHEMA_VERSION,
            STORAGE_SCHEMA_VERSION,
        ):
            attempted_versions = {
                screen.normalization_version
                for screen in self.screens
                if _enum_value(
                    NormalizationStatus, screen.normalization_status
                )
                in (NormalizationStatus.COMPLETED, NormalizationStatus.FAILED)
            }
            if len(attempted_versions) > 1:
                raise ValueError("mixed candidate normalization versions are unsupported")
            expected_version = (
                next(iter(attempted_versions)) if attempted_versions else None
            )
            if self.versions.get("normalization") != expected_version:
                raise ValueError("candidate normalization version index is invalid")
        if self.storage_schema_version == STORAGE_SCHEMA_VERSION:
            self._validate_r05_contract()

    def _validate_r05_contract(self) -> None:
        status = _enum_value(DocumentBuildStatus, self.document_build_status)
        expected_summary = recompute_aggregation_summary(self.screens)
        if self.aggregation_summary is None:
            object.__setattr__(self, "aggregation_summary", expected_summary)
        elif self.aggregation_summary != expected_summary:
            raise ValueError("candidate aggregation summary does not match screens")
        if any(code not in AGGREGATION_WARNING_CODES for code in self.aggregation_warning_codes):
            raise ValueError("candidate aggregation warning is invalid")
        if len(set(self.aggregation_warning_codes)) != len(self.aggregation_warning_codes):
            raise ValueError("candidate aggregation warning is duplicated")
        attempted_screens = tuple(
            screen for screen in self.screens
            if screen.aggregation_status != AggregationStatus.NOT_ATTEMPTED
        )
        if status == DocumentBuildStatus.NOT_ATTEMPTED:
            if (
                self.document_version != R05_DOCUMENT_VERSION
                or self.document_text is not None
                or self.document_segments
                or self.versions.get("aggregation") is not None
                or self.aggregation_config_version is not None
                or self.aggregation_config_digest is not None
                or self.aggregation_warning_codes
                or self.aggregation_duplicate_risk is not None
                or attempted_screens
            ):
                raise ValueError("not-attempted document has aggregation fields")
            return
        if (
            self.document_version != R05_DOCUMENT_VERSION
            or self.versions.get("aggregation") != "r05-v1"
            or self.aggregation_config_version != "r05-config-v1"
            or not isinstance(self.aggregation_config_digest, str)
            or _SHA256_PATTERN.fullmatch(self.aggregation_config_digest) is None
            or self.aggregation_duplicate_risk is None
        ):
            raise ValueError("attempted document requires aggregation identity")
        if status == DocumentBuildStatus.FAILED:
            if self.document_text is not None or self.document_segments:
                raise ValueError("failed document cannot have text")
            return
        if not isinstance(self.document_text, str):
            raise ValueError("built document requires text")
        if tuple(segment.order for segment in self.document_segments) != tuple(range(len(self.document_segments))):
            raise ValueError("document segment order is invalid")
        if self.document_text != "\n".join(segment.normalized_text for segment in self.document_segments):
            raise ValueError("document text projection is invalid")
        screens_by_identity: Dict[Tuple[str, Optional[int]], Tuple[OcrScreenRecord, ...]] = {}
        for screen in self.screens:
            key = (screen.screen_id, screen.screen_index)
            screens_by_identity[key] = screens_by_identity.get(key, ()) + (screen,)
        all_evidence = tuple(
            evidence for screen in self.screens for evidence in screen.match_evidence
        )
        evidence_by_id = {
            evidence.match_id: evidence
            for evidence in all_evidence
        }
        if len(evidence_by_id) != len(all_evidence):
            raise ValueError("candidate aggregation evidence match ID is duplicated")
        for segment in self.document_segments:
            for occurrence in segment.source_occurrences:
                source_screens = screens_by_identity.get((
                    occurrence.source_screen_id,
                    occurrence.source_screen_index,
                ), ())
                if not source_screens:
                    raise ValueError("document occurrence screen is invalid")
                if not any(
                    all(
                        identifier in {item.segment_id for item in screen.segments}
                        for identifier in occurrence.source_segment_ids
                    )
                    and all(
                        identifier in {box.box_id for box in screen.raw_boxes}
                        for identifier in occurrence.source_ocr_box_ids
                    )
                    for screen in source_screens
                ):
                    raise ValueError("document occurrence segment is invalid")
                if occurrence.match_id is not None and occurrence.match_id not in evidence_by_id:
                    raise ValueError("document occurrence match is invalid")
        document_ids = {segment.document_segment_id for segment in self.document_segments}
        for evidence in evidence_by_id.values():
            if any(identifier not in document_ids for identifier in evidence.matched_document_segment_ids):
                raise ValueError("screen evidence document reference is invalid")
        identities = {
            (screen.aggregation_version, screen.aggregation_config_version, screen.aggregation_config_digest)
            for screen in attempted_screens
        }
        expected_identity = ("r05-v1", self.aggregation_config_version, self.aggregation_config_digest)
        if identities and identities != {expected_identity}:
            raise ValueError("mixed aggregation identity is unsupported")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CandidateOcrDocument":
        document_version = validate_record_version(
            data,
            "document_version",
            SUPPORTED_DOCUMENT_VERSIONS,
        )
        storage_version = validate_record_version(
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
        if storage_version == STORAGE_SCHEMA_VERSION:
            required_aggregation_fields = (
                "document_build_status", "aggregation_config_version",
                "aggregation_config_digest", "aggregation_warning_codes",
                "aggregation_duplicate_risk", "aggregation_summary",
            )
            if any(field_name not in data for field_name in required_aggregation_fields):
                raise ValueError("R05 candidate schema fields are incomplete")
            values["document_segments"] = tuple(
                item if isinstance(item, OcrDocumentSegment)
                else OcrDocumentSegment.from_dict(item)
                for item in values.get("document_segments") or ()
            )
            values["document_build_status"] = _enum_value(
                DocumentBuildStatus, values.get("document_build_status")
            )
            values["aggregation_warning_codes"] = tuple(
                values.get("aggregation_warning_codes") or ()
            )
            if values.get("aggregation_duplicate_risk") is not None:
                values["aggregation_duplicate_risk"] = _enum_value(
                    AggregationDuplicateRisk, values["aggregation_duplicate_risk"]
                )
            aggregation_summary = values.get("aggregation_summary")
            if aggregation_summary is not None and not isinstance(aggregation_summary, AggregationSummary):
                values["aggregation_summary"] = AggregationSummary.from_dict(aggregation_summary)
        else:
            values.update({
                "document_text": None,
                "document_segments": (),
                "document_build_status": DocumentBuildStatus.NOT_ATTEMPTED,
                "aggregation_config_version": None,
                "aggregation_config_digest": None,
                "aggregation_warning_codes": (),
                "aggregation_duplicate_risk": None,
                "aggregation_summary": None,
            })
        if storage_version in (R04_STORAGE_SCHEMA_VERSION, STORAGE_SCHEMA_VERSION) and "normalization_summary" not in data:
            raise ValueError("candidate normalization summary is required")
        normalization_summary = values.get("normalization_summary")
        if normalization_summary is not None and not isinstance(
            normalization_summary, NormalizationSummary
        ):
            values["normalization_summary"] = NormalizationSummary.from_dict(
                normalization_summary
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
    normalization_config_version: Optional[str] = None
    normalization_config_digest: Optional[str] = None
    effective_min_confidence: Optional[float] = None
    normalization_config: Optional[Dict[str, Any]] = None
    rule_evaluation_mode: Optional[str] = None
    ocr_min_confidence: Optional[float] = None
    aggregation_mode: str = "disabled"
    aggregation_version: Optional[str] = None
    aggregation_config_version: Optional[str] = None
    aggregation_config_digest: Optional[str] = None
    aggregation_config: Optional[Dict[str, Any]] = None
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
        if self.storage_schema_version in (
            R04_STORAGE_SCHEMA_VERSION,
            STORAGE_SCHEMA_VERSION,
        ):
            from ocr_normalization import normalization_config_from_snapshot

            _validate_config_identity(
                normalization_version=self.normalization_version,
                normalization_config_version=self.normalization_config_version,
                normalization_config_digest=self.normalization_config_digest,
                effective_min_confidence=self.effective_min_confidence,
                rule_evaluation_mode=self.rule_evaluation_mode,
            )
            if not isinstance(self.normalization_config, dict):
                raise ValueError("run manifest requires a normalization config")
            try:
                restored_config = normalization_config_from_snapshot(
                    self.normalization_config
                )
            except ValueError as exc:
                raise ValueError(
                    "run manifest normalization config is invalid"
                ) from exc
            if canonical_mapping_digest(self.normalization_config) != self.normalization_config_digest:
                raise ValueError("run manifest normalization config digest mismatch")
            expected_snapshot_values = {
                "normalization_version": self.normalization_version,
                "normalization_config_version": (
                    restored_config.normalization_config_version
                ),
                "effective_min_confidence": (
                    restored_config.effective_min_confidence
                ),
            }
            if any(
                self.normalization_config.get(key) != value
                for key, value in expected_snapshot_values.items()
            ):
                raise ValueError("run manifest normalization config identity mismatch")
        if self.storage_schema_version == STORAGE_SCHEMA_VERSION:
            if self.aggregation_mode not in ("disabled", "record"):
                raise ValueError("run manifest aggregation mode is invalid")
            aggregation_identity = (
                self.aggregation_version,
                self.aggregation_config_version,
                self.aggregation_config_digest,
                self.aggregation_config,
            )
            if self.aggregation_mode == "disabled":
                if any(value is not None for value in aggregation_identity):
                    raise ValueError("disabled run manifest cannot have aggregation identity")
            else:
                from ocr_aggregation import (
                    AGGREGATION_CONFIG_VERSION,
                    AGGREGATION_VERSION,
                    aggregation_config_digest,
                    restore_aggregation_config,
                )
                if not isinstance(self.aggregation_config, dict):
                    raise ValueError("record run manifest requires aggregation config")
                try:
                    config = restore_aggregation_config(self.aggregation_config)
                except ValueError as exc:
                    raise ValueError("run manifest aggregation config is invalid") from exc
                if (
                    self.aggregation_version != AGGREGATION_VERSION
                    or self.aggregation_config_version != AGGREGATION_CONFIG_VERSION
                    or self.aggregation_config_digest != aggregation_config_digest(self.aggregation_config)
                    or config.aggregation_config_version != self.aggregation_config_version
                ):
                    raise ValueError("run manifest aggregation config identity mismatch")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunManifest":
        storage_version = validate_record_version(
            data,
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )
        values = _known_values(cls, data)
        if storage_version == STORAGE_SCHEMA_VERSION:
            required_aggregation_fields = (
                "aggregation_mode", "aggregation_version",
                "aggregation_config_version", "aggregation_config_digest",
                "aggregation_config",
            )
            if any(field_name not in data for field_name in required_aggregation_fields):
                raise ValueError("R05 run manifest fields are incomplete")
        values["status"] = _enum_value(RunStatus, values["status"])
        values["data_files"] = {
            key: str(value)
            for key, value in dict(values.get("data_files") or {}).items()
        }
        if storage_version == LEGACY_STORAGE_SCHEMA_VERSION:
            for field_name in (
                "normalization_version",
                "normalization_config_version",
                "normalization_config_digest",
                "effective_min_confidence",
                "normalization_config",
                "rule_evaluation_mode",
            ):
                values[field_name] = None
        if storage_version != STORAGE_SCHEMA_VERSION:
            values.update({
                "aggregation_mode": "disabled",
                "aggregation_version": None,
                "aggregation_config_version": None,
                "aggregation_config_digest": None,
                "aggregation_config": None,
            })
        elif values.get("normalization_config") is not None:
            values["normalization_config"] = dict(values["normalization_config"])
        if values.get("aggregation_config") is not None:
            values["aggregation_config"] = dict(values["aggregation_config"])
        return cls(**values)
