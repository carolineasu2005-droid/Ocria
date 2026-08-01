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
STORAGE_SCHEMA_VERSION = "1.1.0"
DOCUMENT_VERSION = "stage0-v1"
SUPPORTED_STORAGE_SCHEMA_VERSIONS = (
    LEGACY_STORAGE_SCHEMA_VERSION,
    STORAGE_SCHEMA_VERSION,
)
SUPPORTED_DOCUMENT_VERSIONS = (DOCUMENT_VERSION,)
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
        if self.storage_schema_version == STORAGE_SCHEMA_VERSION:
            self._validate_r04_contract()

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

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OcrScreenRecord":
        storage_version = validate_record_version(
            data,
            "storage_schema_version",
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )
        values = _known_values(cls, data)
        if storage_version == STORAGE_SCHEMA_VERSION:
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
    normalization_summary: Optional[NormalizationSummary] = None
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
        if self.storage_schema_version == STORAGE_SCHEMA_VERSION:
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

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CandidateOcrDocument":
        storage_version = validate_record_version(
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
        if storage_version == STORAGE_SCHEMA_VERSION and "normalization_summary" not in data:
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
        if self.storage_schema_version == STORAGE_SCHEMA_VERSION:
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

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunManifest":
        storage_version = validate_record_version(
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
        elif values.get("normalization_config") is not None:
            values["normalization_config"] = dict(values["normalization_config"])
        return cls(**values)
