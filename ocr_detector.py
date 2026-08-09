"""Screen-only RapidOCR keyword detector with injectable test backends."""

from dataclasses import dataclass, field, replace
from datetime import datetime
import hashlib
import logging
import math
import re
import time
from typing import Callable, Iterable, List, Optional, Protocol, Sequence, Tuple
from uuid import uuid4

from ocr_calibration import ScreenRegion
from ocr_normalization import (
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NORMALIZATION_COMPLETED,
    NormalizationBox,
    OcrNormalizationConfig,
    TextNormalizationResult,
    config_with_effective_min_confidence,
    eligible_box_ids_for_config,
    failed_normalization_result,
    normalize_ocr_text,
)
from ocr_text import KeywordRule, OCRItem, matching_keyword_rule, searchable_text


logger = logging.getLogger(__name__)


DYNAMIC_END_VERSION = "r07-v1"
DYNAMIC_END_DEFAULT_MODE = "shadow"
DYNAMIC_END_MODES = ("off", "shadow", "safe", "full")
POSITION_STATUSES = ("initial", "changed", "same", "uncertain", "unavailable")
PAGE_CHANGE_STATUSES = ("initial", "changed", "same", "unavailable")


@dataclass(frozen=True)
class PositionDecision:
    """Pure R07 classification of one canonical record against its predecessor."""

    position_status: str
    page_change_status: str
    reference_screen_id: Optional[str]
    prediction_reason: Optional[str]
    insufficient_evidence: bool = False

    def __post_init__(self) -> None:
        if self.position_status not in POSITION_STATUSES:
            raise ValueError("position status is invalid")
        if self.page_change_status not in PAGE_CHANGE_STATUSES:
            raise ValueError("page change status is invalid")
        if not isinstance(self.insufficient_evidence, bool):
            raise ValueError("insufficient_evidence must be a boolean")


def _record_value(record: object, name: str, default=None):
    return getattr(record, name, default) if record is not None else default


def _enum_value(value):
    return getattr(value, "value", value)


def _record_has_uncertain_evidence(record: object) -> bool:
    """Read existing R05/R06 projections only; never derive them again."""

    aggregation_status = _enum_value(_record_value(record, "aggregation_status"))
    if aggregation_status not in (None, "not_attempted", "completed"):
        return True
    if any(
        bool(_record_value(record, name, ()))
        for name in ("uncertain_segment_ids",)
    ):
        return True
    if any(
        (_record_value(record, name) or 0) > 0
        for name in ("uncertain_segment_count", "uncertain_char_count")
    ):
        return True
    if _enum_value(_record_value(record, "aggregation_duplicate_risk")) == "elevated":
        return True

    result = _record_value(record, "similarity_result")
    if result is None:
        return False
    if _enum_value(getattr(result, "effective_new_status", None)) == "possible":
        return True
    if _enum_value(getattr(result, "comparison_class", None)) == "uncertain":
        return True
    if _enum_value(getattr(result, "similarity_status", None)) in (
        "partial", "failed", "unavailable",
    ):
        return True
    warnings = tuple(getattr(result, "warning_codes", ()) or ()) + tuple(
        _record_value(record, "aggregation_warning_codes", ()) or ()
    )
    return any(
        any(token in str(code).lower() for token in ("possible", "uncertain", "conflict", "mismatch"))
        for code in warnings
    )


def _is_benign_duplicate_warning(code: str) -> bool:
    """Warnings that are normal artifacts of R05 duplicate detection or
    cross-layer conflict when both R05 and R06 project benign duplicate
    facts.  They do not represent content-level uncertainty and should
    not block a ``same`` position classification on identical hashes.
    """
    return code in (
        "screen_aggregation_partial",
        "r05_partial",
        "r05_not_attempted",
        "cross_layer_similarity_conflict",
        "reference_missing",
    )


def _record_has_blocking_position_uncertainty(
    record: object,
    *,
    exact_same: bool = False,
) -> bool:
    """Return True only for content-level evidence that should prevent
    ``same`` classification.

    When *exact_same* is True, benign R05-partial cascades that are normal
    artifacts of exact-hash duplicate detection are filtered out.  When
    *exact_same* is False, the existing ``_record_has_uncertain_evidence``
    contract is used (the hash already differs, so aggregation-level
    uncertain is meaningful).
    """

    status = _enum_value(_record_value(record, "aggregation_status"))

    # R05 FAILED is always blocking.
    if status == "failed":
        return True

    if not exact_same:
        # When the hash already differs, we use the full uncertain-evidence
        # contract: any aggregation-level PARTIAL / uncertain is meaningful.
        return _record_has_uncertain_evidence(record)

    # --- exact_same gate below ---
    # We only reach here when exact hash matches.  At this point the *only*
    # thing that can override 'same' is genuine evidence ambiguity:
    # non-benign warning codes, or R06 failure.  Effective-new content
    # (present, short_text_protected, effective_new_segments) is handled
    # by the ``changed`` path in ``classify_position`` and must NOT be
    # treated as blocking here.

    # Aggregation warnings beyond the benign duplicate set.
    agg_warnings = tuple(
        _record_value(record, "aggregation_warning_codes", ()) or ()
    )
    # screen_aggregation_partial is the expected R05 code for a screen
    # whose segments could not be confidently matched to the existing
    # document — normal for a pure duplicate.
    if any(w != "screen_aggregation_partial" for w in agg_warnings):
        return True

    result = _record_value(record, "similarity_result")
    if result is None:
        return False

    # R06 explicit failure is blocking.
    sim_status = _enum_value(getattr(result, "similarity_status", None))
    if sim_status in ("failed", "unavailable"):
        # When R05 is genuinely not_attempted (e.g. position_confirmation
        # screens), the unavailable status cascades from that rather than
        # from a real R06 failure, so it is not blocking.
        if status == "not_attempted":
            return False
        return True

    # R06 warning codes beyond the benign cross-layer cascade set.
    r06_warnings = tuple(getattr(result, "warning_codes", ()) or ())
    _benign_r06 = frozenset((
        "r05_partial",
        "cross_layer_similarity_conflict",
        "exact_hash_unavailable",
    ))
    if any(w not in _benign_r06 for w in r06_warnings):
        return True

    # comparison_class == uncertain only when NOT cascaded from partial.
    if (
        _enum_value(getattr(result, "comparison_class", None)) == "uncertain"
        and status != "partial"
    ):
        return True

    return False


def _record_has_effective_new_content(record: object) -> bool:
    """Return only existing R05/R06 positive evidence, including protected short text."""

    if _record_value(record, "has_effective_new_text") is True:
        return True
    result = _record_value(record, "similarity_result")
    if result is None:
        return False
    if getattr(result, "has_effective_new_text", None) is True:
        return True
    if _enum_value(getattr(result, "effective_new_status", None)) == "present":
        return True
    if (getattr(result, "effective_new_segment_count", None) or 0) > 0:
        return True
    return any(
        getattr(decision, "reason", None) == "short_text_protected"
        and _enum_value(getattr(decision, "decision", None)) == "effective"
        for decision in tuple(getattr(result, "effective_new_decisions", ()) or ())
    )


def _record_has_content_level_effective_new(record: object) -> bool:
    """Like ``_record_has_effective_new_content`` but excludes R06 fallback
    signals (``has_effective_new_text=True`` on similarity_result when
    ``effective_new_status`` is only ``possible``).  This prevents the benign
    R05-partial -> R06-fallback cascade from being mistaken for real
    effective-new content in position classification.

    The top-level ``has_effective_new_text`` record field is also checked
    because it is set from R05 projection which may itself flag duplicates
    as ``new_text``.  When both ``effective_new_status`` is ``possible``
    and ``effective_new_segment_count`` is 0, the aggregate signal is a
    R06 fallback, not a genuine content-level finding.
    """
    result = _record_value(record, "similarity_result")

    # Short-text-protected is always real regardless of other signals.
    if result is not None and any(
        getattr(d, "reason", None) == "short_text_protected"
        and _enum_value(getattr(d, "decision", None)) == "effective"
        for d in tuple(getattr(result, "effective_new_decisions", ()) or ())
    ):
        return True

    # effective_new_status == present is a real signal.
    if result is not None and _enum_value(
        getattr(result, "effective_new_status", None)
    ) == "present":
        return True

    # Non-zero effective_new_segment_count is a real signal.
    if (getattr(result, "effective_new_segment_count", None) or 0) > 0:
        return True

    # Top-level record field: treat as real only when it does NOT come
    # from the R06 fallback cascade.
    if _record_value(record, "has_effective_new_text") is True:
        # If R06 says 'possible' with 0 segments, the top-level True
        # is a fallback from cross-layer conflict — not real content.
        if result is not None:
            en_status = _enum_value(
                getattr(result, "effective_new_status", None)
            )
            if (
                en_status == "possible"
                and (getattr(result, "effective_new_segment_count", None) or 0)
                == 0
            ):
                return False
        return True

    return False


def classify_position(
    previous_record: Optional[object],
    current_record: object,
    *,
    load_health: Optional[bool],
    ocr_health: Optional[bool],
    identity_health: Optional[bool],
) -> PositionDecision:
    """Classify a saved-screen candidate without OCR, Store, or page effects."""

    if previous_record is None:
        return PositionDecision("initial", "initial", None, "initial_screen")

    reference_screen_id = _record_value(previous_record, "screen_id")
    previous_hash = _record_value(previous_record, "exact_hash")
    current_hash = _record_value(current_record, "exact_hash")
    previous_version = _record_value(previous_record, "fingerprint_version")
    current_version = _record_value(current_record, "fingerprint_version")
    if (
        load_health is not True
        or ocr_health is not True
        or identity_health is not True
        or not isinstance(previous_hash, str)
        or not isinstance(current_hash, str)
        or not isinstance(previous_version, str)
        or not isinstance(current_version, str)
    ):
        return PositionDecision(
            "unavailable", "unavailable", reference_screen_id,
            "position_unavailable", True,
        )

    exact_same = previous_hash == current_hash
    page_change_status = "same" if exact_same else "changed"

    if _record_has_blocking_position_uncertainty(
        current_record, exact_same=exact_same,
    ):
        return PositionDecision(
            "uncertain", page_change_status, reference_screen_id,
            "position_uncertain", True,
        )

    if exact_same and not _record_has_content_level_effective_new(current_record):
        return PositionDecision(
            "same", "same", reference_screen_id, "exact_same",
        )

    return PositionDecision(
        "changed", page_change_status, reference_screen_id,
        "effective_new_content" if _record_has_content_level_effective_new(current_record) else "exact_different",
    )


@dataclass(frozen=True)
class DynamicEndConfig:
    """Minimal R07 configuration; it does not change legacy scan control."""

    mode: str = DYNAMIC_END_DEFAULT_MODE
    no_new_text_threshold: int = 2
    dynamic_end_version: str = DYNAMIC_END_VERSION

    def __post_init__(self) -> None:
        if self.mode not in DYNAMIC_END_MODES:
            raise ValueError("dynamic end mode is invalid")
        if (
            isinstance(self.no_new_text_threshold, bool)
            or not isinstance(self.no_new_text_threshold, int)
            or self.no_new_text_threshold < 1
        ):
            raise ValueError("no_new_text_threshold must be a positive integer")

    def manifest_config(self) -> dict:
        return {"no_new_text_threshold": self.no_new_text_threshold}


@dataclass
class DynamicEndState:
    """Bounded R07 scan facts only; no transition or effect logic lives here."""

    mode: str = DYNAMIC_END_DEFAULT_MODE
    scan_slot_count: int = 0
    normal_scroll_count: int = 0
    unique_position_count: int = 0
    ocr_attempt_count: int = 0
    scroll_retry_count: int = 0
    focus_restore_count: int = 0
    consecutive_no_new_count: int = 0
    last_comparable_record: Optional[object] = None
    last_comparable_record_id: Optional[str] = None
    last_comparable_exact_hash: Optional[str] = None
    first_predicted_end_screen: Optional[int] = None
    first_predicted_end_reason: Optional[str] = None
    recovery_used: bool = False

    def __post_init__(self) -> None:
        if self.mode not in DYNAMIC_END_MODES:
            raise ValueError("dynamic end mode is invalid")
        limits = {
            "scan_slot_count": (self.scan_slot_count, 8),
            "normal_scroll_count": (self.normal_scroll_count, 7),
            "unique_position_count": (self.unique_position_count, 8),
            "ocr_attempt_count": (self.ocr_attempt_count, None),
            "scroll_retry_count": (self.scroll_retry_count, 1),
            "focus_restore_count": (self.focus_restore_count, 1),
            "consecutive_no_new_count": (self.consecutive_no_new_count, None),
        }
        for name, (value, maximum) in limits.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("{0} must be a non-negative integer".format(name))
            if maximum is not None and value > maximum:
                raise ValueError("{0} exceeds its R07 bound".format(name))
        if self.first_predicted_end_screen is not None and (
            isinstance(self.first_predicted_end_screen, bool)
            or not isinstance(self.first_predicted_end_screen, int)
            or self.first_predicted_end_screen < 1
        ):
            raise ValueError("first_predicted_end_screen must be a positive integer or null")
        if not isinstance(self.recovery_used, bool):
            raise ValueError("recovery_used must be a boolean")


@dataclass
class ShadowPredictionAnalysis:
    """Small per-scan shadow facts; this is not an event ledger."""

    store_failed: bool = False
    technical_failure: bool = False
    rule_early_stop: bool = False
    saw_effective_new_content: bool = False
    content_evidence_complete: bool = True


def accepted_ocr_items(
    items: Iterable[OCRItem],
    min_confidence: float,
) -> List[OCRItem]:
    """Return OCR items accepted by the existing confidence threshold."""

    return [item for item in items if item.confidence >= min_confidence]


def calculate_load_metrics(
    accepted_items: Iterable[OCRItem],
) -> Tuple[int, int]:
    """Return box count and stripped text length for accepted OCR items."""

    accepted_items = list(accepted_items)
    return (
        len(accepted_items),
        sum(
            len(item.text.strip())
            for item in accepted_items
            if item.text.strip()
        ),
    )


def evaluate_detail_page_load(
    ocr_box_count: int,
    ocr_text_length: int,
    box_count_threshold: int,
    text_length_threshold: int,
) -> Tuple[bool, str]:
    """Return whether OCR metrics meet the minimum detail-page threshold."""

    if ocr_box_count == 0:
        return False, "zero_ocr_boxes"
    if (
        ocr_box_count <= box_count_threshold
        and ocr_text_length < text_length_threshold
    ):
        return False, "low_box_count_and_short_text"
    return True, "threshold_passed"


FINGERPRINT_VERSION = "r03-v1"
FINGERPRINT_SEPARATOR = "\n"
FINGERPRINT_MIN_LINE_TOLERANCE = 8.0
FINGERPRINT_LINE_HEIGHT_RATIO = 0.5
FINGERPRINT_HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
FINGERPRINT_WHITESPACE_PATTERN = re.compile(r"\s+")


class FingerprintBuildError(ValueError):
    """Raised for an R03-only fingerprint construction failure."""


@dataclass(frozen=True)
class ScreenFingerprint:
    raw_text: str
    normalized_text: str
    raw_text_length: int
    normalized_text_length: int
    ocr_box_count: int
    captured_at: str
    exact_hash: str
    fingerprint_version: str = FINGERPRINT_VERSION
    screen_index: Optional[int] = None


def fingerprint_box_bounds(
    box: Optional[Sequence[Sequence[float]]],
) -> Tuple[float, float, float, float, float, float, float]:
    """Return left, top, right, bottom, width, height, center_y."""

    if box is None:
        raise FingerprintBuildError("fingerprint box geometry is invalid")

    try:
        points = list(box)
    except TypeError as exc:
        raise FingerprintBuildError(
            "fingerprint box geometry is invalid"
        ) from exc
    if not points:
        raise FingerprintBuildError("fingerprint box geometry is invalid")

    try:
        coordinates = [
            (float(point[0]), float(point[1]))
            for point in points
        ]
    except (IndexError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise FingerprintBuildError(
            "fingerprint box geometry is invalid"
        ) from exc

    xs = [coordinate[0] for coordinate in coordinates]
    ys = [coordinate[1] for coordinate in coordinates]
    if not all(math.isfinite(value) for value in (*xs, *ys)):
        raise FingerprintBuildError("fingerprint box geometry is invalid")

    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)
    width = right - left
    height = bottom - top
    center_y = (top + bottom) / 2.0
    return left, top, right, bottom, width, height, center_y


def order_fingerprint_items(
    accepted_items: Sequence[OCRItem],
) -> List[OCRItem]:
    """Return accepted OCR items in the R03 coordinate reading order."""

    records = []
    for original_index, item in enumerate(accepted_items):
        left, top, right, bottom, width, height, center_y = (
            fingerprint_box_bounds(item.box)
        )
        records.append(
            (
                item,
                original_index,
                left,
                top,
                right,
                bottom,
                width,
                max(1.0, height),
                center_y,
            )
        )

    records.sort(
        key=lambda record: (
            record[8],
            record[3],
            record[2],
            record[5],
            record[4],
            record[1],
        )
    )

    lines = []
    for record in records:
        for line in lines:
            tolerance = max(
                FINGERPRINT_MIN_LINE_TOLERANCE,
                min(record[7], line["line_height"])
                * FINGERPRINT_LINE_HEIGHT_RATIO,
            )
            if abs(record[8] - line["line_center_y"]) <= tolerance:
                line["members"].append(record)
                member_count = len(line["members"])
                line["line_center_y"] = (
                    sum(member[8] for member in line["members"])
                    / member_count
                )
                line["line_height"] = (
                    sum(member[7] for member in line["members"])
                    / member_count
                )
                break
        else:
            lines.append(
                {
                    "members": [record],
                    "line_center_y": record[8],
                    "line_height": record[7],
                }
            )

    lines.sort(
        key=lambda line: (
            line["line_center_y"],
            line["members"][0][3],
            line["members"][0][2],
        )
    )
    ordered_items = []
    for line in lines:
        line["members"].sort(
            key=lambda record: (
                record[2],
                record[3],
                record[4],
                record[5],
                record[1],
            )
        )
        ordered_items.extend(record[0] for record in line["members"])
    return ordered_items


def normalize_fingerprint_item_text(text: str) -> str:
    """Apply only the R03 per-item strip and whitespace compression."""

    return FINGERPRINT_WHITESPACE_PATTERN.sub(" ", text.strip())


def build_fingerprint_raw_text(
    ordered_items: Sequence[OCRItem],
) -> Tuple[str, int]:
    """Return raw_text and raw_text_length without separator length."""

    return (
        FINGERPRINT_SEPARATOR.join(item.text for item in ordered_items),
        sum(len(item.text) for item in ordered_items),
    )


def build_fingerprint_normalized_text(
    ordered_items: Sequence[OCRItem],
) -> Tuple[str, int]:
    """Return normalized_text and normalized_text_length."""

    normalized_values = [
        normalize_fingerprint_item_text(item.text)
        for item in ordered_items
    ]
    normalized_text = FINGERPRINT_SEPARATOR.join(
        value for value in normalized_values if value
    )
    return normalized_text, len(normalized_text)


def sha256_normalized_text(normalized_text: str) -> str:
    """Return the SHA-256 lowercase hex digest of UTF-8 text."""

    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def build_screen_fingerprint(
    accepted_items: Sequence[OCRItem],
    *,
    captured_at: Optional[datetime] = None,
) -> ScreenFingerprint:
    """Build the authoritative R03 exact fingerprint from accepted OCR items."""

    if captured_at is not None and (
        not isinstance(captured_at, datetime)
        or captured_at.tzinfo is None
        or captured_at.utcoffset() is None
    ):
        raise FingerprintBuildError(
            "fingerprint timestamp must include a timezone"
        )

    ordered_items = order_fingerprint_items(accepted_items)
    raw_text, raw_text_length = build_fingerprint_raw_text(ordered_items)
    normalized_text, normalized_text_length = (
        build_fingerprint_normalized_text(ordered_items)
    )
    exact_hash = sha256_normalized_text(normalized_text)
    if captured_at is None:
        captured_at = datetime.now().astimezone()

    return ScreenFingerprint(
        raw_text=raw_text,
        normalized_text=normalized_text,
        raw_text_length=raw_text_length,
        normalized_text_length=normalized_text_length,
        ocr_box_count=len(accepted_items),
        captured_at=captured_at.isoformat(),
        exact_hash=exact_hash,
        fingerprint_version=FINGERPRINT_VERSION,
    )


def compare_screen_fingerprints(
    left: Optional[ScreenFingerprint],
    right: Optional[ScreenFingerprint],
) -> Optional[bool]:
    """Return True, False, or None for exact R03 comparison."""

    def is_valid(fingerprint: Optional[ScreenFingerprint]) -> bool:
        return (
            fingerprint is not None
            and isinstance(fingerprint.fingerprint_version, str)
            and bool(fingerprint.fingerprint_version)
            and isinstance(fingerprint.exact_hash, str)
            and FINGERPRINT_HASH_PATTERN.fullmatch(fingerprint.exact_hash)
            is not None
        )

    if not is_valid(left) or not is_valid(right):
        return None
    if left.fingerprint_version != right.fingerprint_version:
        return None
    return left.exact_hash == right.exact_hash


class OCRBackend(Protocol):
    def recognize(self, image: object) -> Sequence[OCRItem]:
        ...


class ScreenCapture(Protocol):
    def capture(self, region: ScreenRegion) -> object:
        ...


RULE_EVALUATION_MODE_LEGACY_SHADOW = "legacy_shadow"
RULE_COMPARISON_SAME_MATCH = "same_match"
RULE_COMPARISON_SAME_NO_MATCH = "same_no_match"
RULE_COMPARISON_LEGACY_ONLY = "legacy_only"
RULE_COMPARISON_R04_ONLY = "r04_only"
RULE_COMPARISON_NORMALIZATION_FAILED = "normalization_failed"


@dataclass(frozen=True)
class RuleComparisonResult:
    """One non-authoritative R04 comparison beside the legacy rule result."""

    rule_evaluation_mode: str
    legacy_match: bool
    r04_match: Optional[bool]
    comparison_outcome: str
    legacy_rule_index: Optional[int]
    r04_rule_index: Optional[int]


def _matched_rule_index(
    matched_rule: Optional[KeywordRule],
    rules: Sequence[KeywordRule],
) -> Optional[int]:
    """Return the stable zero-based index of a matched configured rule."""

    if matched_rule is None:
        return None
    for index, rule in enumerate(rules):
        if rule is matched_rule:
            return index
    for index, rule in enumerate(rules):
        if rule == matched_rule:
            return index
    return None


@dataclass
class ScanObservation:
    scan_number: int
    text: str
    item_count: int
    elapsed_seconds: float
    matched_keyword: Optional[str] = None
    matched_rule: Optional[KeywordRule] = None
    ocr_box_count: Optional[int] = None
    ocr_text_length: Optional[int] = None
    fingerprint: Optional[ScreenFingerprint] = None
    raw_items: Tuple[OCRItem, ...] = ()
    captured_at: Optional[str] = None
    screen_id: Optional[str] = None
    normalization: Optional[TextNormalizationResult] = None
    normalization_min_confidence: Optional[float] = None
    rule_comparison: Optional[RuleComparisonResult] = None


def bind_fingerprint_screen_index(
    observation: ScanObservation,
    screen_index: int,
) -> None:
    """Replace a valid observation fingerprint with its formal screen index."""

    if screen_index < 1:
        raise ValueError("screen_index must be at least 1")
    if observation.fingerprint is None:
        return
    observation.fingerprint = replace(
        observation.fingerprint,
        screen_index=screen_index,
    )


def _log_fingerprint_generated(observation: ScanObservation) -> None:
    """Log only safe scalar metadata for a completed fingerprint."""

    fingerprint = observation.fingerprint
    if fingerprint is None:
        return
    screen_index = (
        fingerprint.screen_index
        if fingerprint.screen_index is not None
        else "-"
    )
    logger.info(
        "event=ocr_fingerprint_generated fingerprint_version=%s "
        "exact_hash=%s ocr_box_count=%s raw_text_length=%s "
        "normalized_text_length=%s screen_index=%s captured_at=%s "
        "scan_number=%s",
        fingerprint.fingerprint_version,
        fingerprint.exact_hash,
        fingerprint.ocr_box_count,
        fingerprint.raw_text_length,
        fingerprint.normalized_text_length,
        screen_index,
        fingerprint.captured_at,
        observation.scan_number,
    )


def _log_fingerprint_generation_failed(scan_number: int, error_type: str) -> None:
    """Log a builder-only failure without exposing OCR or exception content."""

    logger.warning(
        "event=ocr_fingerprint_generation_failed fingerprint_version=%s "
        "scan_number=%s error_type=%s",
        FINGERPRINT_VERSION,
        scan_number,
        error_type,
    )


def log_fingerprint_comparison(
    left: Optional[ScreenFingerprint],
    right: Optional[ScreenFingerprint],
    comparison: Optional[bool],
) -> None:
    """Log an already-computed comparison without changing scan behavior."""

    comparison_name = (
        "same"
        if comparison is True
        else "different"
        if comparison is False
        else "not_comparable"
    )
    logger.info(
        "event=ocr_fingerprint_comparison comparison=%s left_version=%s "
        "right_version=%s left_hash=%s right_hash=%s",
        comparison_name,
        left.fingerprint_version if left is not None else "-",
        right.fingerprint_version if right is not None else "-",
        left.exact_hash if left is not None else "-",
        right.exact_hash if right is not None else "-",
    )


@dataclass
class DetectionResult:
    success: bool
    confirmed_match: bool
    matched_keyword: Optional[str] = None
    scans_completed: int = 0
    observations: List[ScanObservation] = field(default_factory=list)
    error: Optional[str] = None
    dynamic_end_reason: Optional[str] = None
    abort_reason: Optional[str] = None
    interrupt_reason: Optional[str] = None
    scroll_bottom_candidate: bool = False
    recovery_reason: Optional[str] = None
    dynamic_end_mode: Optional[str] = None
    scan_slot_count: Optional[int] = None
    normal_scroll_count: Optional[int] = None
    unique_position_count: Optional[int] = None
    ocr_attempt_count: Optional[int] = None
    scroll_retry_count: Optional[int] = None
    focus_restore_count: Optional[int] = None
    first_predicted_end_screen: Optional[int] = None
    first_predicted_end_reason: Optional[str] = None
    prediction_would_miss_content: Optional[bool] = None
    prediction_would_miss_rule_match: Optional[bool] = None
    prediction_observation_complete: Optional[bool] = None
    prediction_evidence_complete: Optional[bool] = None


@dataclass(frozen=True)
class PositionConfirmationResult:
    """One bounded first-same recovery attempt; it does not end the scan."""

    attempted: bool
    bottom_candidate: bool
    reason: Optional[str]
    record: Optional[object] = None
    saved: bool = False
    position_decision: Optional[PositionDecision] = None
    promoted_slot: bool = False


@dataclass(frozen=True)
class ObservationCallbackFailure:
    """OCR-free evidence that the callback itself raised unexpectedly."""

    record: Optional[object] = None
    saved: bool = False
    position_decision: Optional[PositionDecision] = None
    failure_reason: str = "unexpected_error"


class MSSScreenCapture:
    """Capture only physical pixels visible inside the selected rectangle."""

    def capture(self, region: ScreenRegion):
        try:
            import mss
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("mss and NumPy are required for screen capture") from exc
        with mss.MSS() as sct:
            shot = sct.grab(region.as_mss_monitor())
        # Drop alpha. MSS byte order is BGRA, which RapidOCR accepts as BGR.
        return np.asarray(shot)[:, :, :3].copy()


class RapidOCRBackend:
    """Lazy RapidOCR adapter supporting modern and legacy result shapes."""

    def __init__(self, engine=None):
        if engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise RuntimeError(
                    "RapidOCR is not installed; install requirements-ocr.txt"
                ) from exc
            engine = RapidOCR()
        self.engine = engine

    def recognize(self, image: object) -> Sequence[OCRItem]:
        result = self.engine(image)
        if result is None:
            return []

        # RapidOCR 3.x result object.
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        boxes = getattr(result, "boxes", None)
        if txts is not None:
            scores = scores if scores is not None else [1.0] * len(txts)
            boxes = boxes if boxes is not None else [None] * len(txts)
            return [
                OCRItem(str(text), float(score), box)
                for text, score, box in zip(txts, scores, boxes)
            ]

        # Older releases return (lines, elapsed), where each line is
        # [box, text, score]. Some wrappers return lines directly.
        lines = result
        if isinstance(result, tuple) and len(result) == 2:
            lines = result[0]
        if not lines:
            return []
        parsed = []
        for line in lines:
            if not isinstance(line, (list, tuple)) or len(line) < 2:
                continue
            box, text = line[0], line[1]
            score = line[2] if len(line) > 2 else 1.0
            parsed.append(OCRItem(str(text), float(score), box))
        return parsed


class OCRKeywordDetector:
    """Scan a calibrated screen region and confirm exact keyword matches."""

    def __init__(
        self,
        backend: OCRBackend,
        capture: ScreenCapture,
        region: ScreenRegion,
        max_scans: int = 8,
        min_confidence: float = 0.85,
        scroll: Optional[Callable[[], None]] = None,
        wait: Callable[[float], None] = time.sleep,
        settle_seconds: float = 0.6,
        confirmation_seconds: float = 0.7,
        observation_callback: Optional[
            Callable[[ScanObservation, str, bool, Optional[int]], object]
        ] = None,
        normalization_config: OcrNormalizationConfig = (
            DEFAULT_OCR_NORMALIZATION_CONFIG
        ),
        rule_evaluation_mode: str = RULE_EVALUATION_MODE_LEGACY_SHADOW,
        dynamic_end_config: DynamicEndConfig = DynamicEndConfig(),
        restore_focus: Optional[Callable[[], bool]] = None,
        interrupt_reason_provider: Optional[Callable[[], Optional[str]]] = None,
    ):
        if max_scans < 1:
            raise ValueError("max_scans must be at least 1")
        self.backend = backend
        self.capture = capture
        self.region = region
        self.max_scans = max_scans
        self.min_confidence = min_confidence
        self.scroll = scroll
        self.wait = wait
        self.settle_seconds = settle_seconds
        self.confirmation_seconds = confirmation_seconds
        self.observation_callback = observation_callback
        if rule_evaluation_mode != RULE_EVALUATION_MODE_LEGACY_SHADOW:
            raise ValueError("unsupported rule evaluation mode")
        self.rule_evaluation_mode = rule_evaluation_mode
        self.dynamic_end_config = dynamic_end_config
        self.dynamic_end_state = DynamicEndState(mode=dynamic_end_config.mode)
        self.last_observation_result = None
        self.restore_focus = restore_focus
        self.interrupt_reason_provider = interrupt_reason_provider
        self.last_position_confirmation: Optional[PositionConfirmationResult] = None
        self.saw_scroll_bottom_candidate = False
        self._shadow_prediction = ShadowPredictionAnalysis()
        self.normalization_config = config_with_effective_min_confidence(
            normalization_config,
            min_confidence,
        )

    def _notify_observation(
        self,
        observation: ScanObservation,
        capture_type: str,
        is_formal_screen: bool,
        screen_index: Optional[int],
    ):
        """Return optional callback evidence without affecting OCR behavior."""

        if self.observation_callback is None:
            return
        try:
            return self.observation_callback(
                observation,
                capture_type,
                is_formal_screen,
                screen_index,
            )
        except Exception as exc:
            logger.warning(
                "event=ocr_observation_callback_failed error_type=%s",
                type(exc).__name__,
            )
            return ObservationCallbackFailure()

    def _update_dynamic_end_state(
        self,
        callback_result: object,
        *,
        is_formal_screen: bool,
    ) -> None:
        """Retain bounded callback facts only; this never controls the scan loop."""

        state = self.dynamic_end_state
        state.ocr_attempt_count += 1
        if is_formal_screen:
            state.scan_slot_count = min(8, state.scan_slot_count + 1)
        if callback_result is None:
            return
        record = getattr(callback_result, "record", None)
        decision = getattr(callback_result, "position_decision", None)
        saved = getattr(callback_result, "saved", False) is True
        if not saved or record is None or decision is None:
            return
        if is_formal_screen and decision.position_status in ("initial", "changed"):
            state.unique_position_count = min(8, state.unique_position_count + 1)
        if decision.position_status in ("initial", "same", "changed"):
            state.last_comparable_record = record
            state.last_comparable_record_id = getattr(record, "screen_id", None)
            state.last_comparable_exact_hash = getattr(record, "exact_hash", None)

    @staticmethod
    def _has_complete_content_evidence(record: object) -> bool:
        """Read only completed R05/R06 projections already attached to a record."""

        if _enum_value(_record_value(record, "aggregation_status")) != "completed":
            return False
        result = _record_value(record, "similarity_result")
        return (
            result is not None
            and _enum_value(getattr(result, "similarity_status", None)) == "completed"
            and _enum_value(getattr(result, "effective_new_status", None))
            in ("none", "present")
        )

    def _set_first_prediction(self, reason: str) -> None:
        """Freeze the earliest shadow stop prediction; later evidence never replaces it."""

        state = self.dynamic_end_state
        if state.first_predicted_end_screen is None:
            state.first_predicted_end_screen = state.scan_slot_count
            state.first_predicted_end_reason = reason

    def _consume_shadow_formal_callback(self, callback_result: object) -> None:
        """Analyze existing formal-record evidence without influencing scan effects."""

        if self.dynamic_end_state.mode == "off":
            return
        state = self.dynamic_end_state
        analysis = self._shadow_prediction
        has_prediction = state.first_predicted_end_screen is not None
        saved = getattr(callback_result, "saved", False) is True
        decision = getattr(callback_result, "position_decision", None)
        record = getattr(callback_result, "record", None)
        healthy = (
            getattr(callback_result, "load_health", None) is True
            and getattr(callback_result, "ocr_health", None) is True
            and getattr(callback_result, "identity_health", None) is True
        )

        if not saved:
            if has_prediction:
                analysis.store_failed = True
            return
        if record is None or decision is None or not healthy:
            if has_prediction:
                analysis.technical_failure = True
            return

        position = getattr(decision, "position_status", None)
        if position in ("unavailable", "uncertain"):
            if has_prediction:
                analysis.content_evidence_complete = False
            state.consecutive_no_new_count = 0
            return

        if has_prediction and state.scan_slot_count > state.first_predicted_end_screen:
            if _record_has_content_level_effective_new(record):
                analysis.saw_effective_new_content = True
            if not self._has_complete_content_evidence(record):
                analysis.content_evidence_complete = False

        if (
            position == "same"
            and not getattr(decision, "insufficient_evidence", True)
        ):
            self._set_first_prediction("possible_scroll_bottom")
            state.consecutive_no_new_count = 0
            return

        if (
            position == "changed"
            and self._has_complete_content_evidence(record)
            and not _record_has_uncertain_evidence(record)
            and not _record_has_effective_new_content(record)
        ):
            if state.mode == "shadow":
                state.consecutive_no_new_count += 1
                if state.consecutive_no_new_count >= self.dynamic_end_config.no_new_text_threshold:
                    self._set_first_prediction("no_new_text_candidate")
            return
        if state.mode == "shadow":
            state.consecutive_no_new_count = 0

    def _consume_rule_confirmation(self, callback_result: object, confirmed: bool) -> None:
        """Record the legacy early-stop boundary for an already-frozen prediction."""

        if self.dynamic_end_state.first_predicted_end_screen is None:
            return
        if getattr(callback_result, "saved", False) is not True:
            self._shadow_prediction.store_failed = True
        if confirmed:
            self._shadow_prediction.rule_early_stop = True

    def _dynamic_result_fields(self, *, normal_completion: bool) -> dict:
        """Project bounded shadow facts into the compatible scan result."""

        state = self.dynamic_end_state
        analysis = self._shadow_prediction
        first_prediction = state.first_predicted_end_screen is not None
        interrupt_reason = self._interrupt_reason()
        if not first_prediction:
            miss_content = None
            miss_rule = None
            observation_complete = None
            evidence_complete = None
        elif (
            analysis.store_failed
            or analysis.technical_failure
            or interrupt_reason is not None
        ):
            miss_content = None
            miss_rule = None
            observation_complete = False
            evidence_complete = False
        elif analysis.rule_early_stop:
            miss_content = None
            miss_rule = True
            observation_complete = False
            evidence_complete = False
        elif normal_completion:
            observation_complete = True
            miss_content = (
                True if analysis.saw_effective_new_content
                else False if analysis.content_evidence_complete else None
            )
            miss_rule = False
            evidence_complete = (
                analysis.content_evidence_complete
                and miss_content is not None
            )
        else:
            miss_content = None
            miss_rule = None
            observation_complete = False
            evidence_complete = False
        return {
            "dynamic_end_mode": state.mode,
            "scan_slot_count": state.scan_slot_count,
            "normal_scroll_count": state.normal_scroll_count,
            "unique_position_count": state.unique_position_count,
            "ocr_attempt_count": state.ocr_attempt_count,
            "scroll_retry_count": state.scroll_retry_count,
            "focus_restore_count": state.focus_restore_count,
            "first_predicted_end_screen": state.first_predicted_end_screen,
            "first_predicted_end_reason": state.first_predicted_end_reason,
            "prediction_would_miss_content": miss_content,
            "prediction_would_miss_rule_match": miss_rule,
            "prediction_observation_complete": observation_complete,
            "prediction_evidence_complete": evidence_complete,
            "interrupt_reason": interrupt_reason,
        }

    def _interrupt_reason(self) -> Optional[str]:
        """Read an injected stop fact without creating a new stop mechanism."""

        if self.interrupt_reason_provider is None:
            return None
        try:
            reason = self.interrupt_reason_provider()
        except Exception:
            return None
        return reason if reason in ("user_interrupted", "runtime_expired") else None

    @staticmethod
    def _callback_failure_reason(callback_result: object) -> Optional[str]:
        if callback_result is None:
            return "position_unresolved"
        explicit_reason = getattr(callback_result, "failure_reason", None)
        if explicit_reason in (
            "load_failed", "switch_failed", "scroll_failed", "ocr_failed",
            "focus_restore_failed", "position_unresolved", "store_failed",
            "unexpected_error",
        ):
            return explicit_reason
        if getattr(callback_result, "saved", False) is not True:
            return "store_failed"
        decision = getattr(callback_result, "position_decision", None)
        if decision is None:
            return "position_unresolved"
        if getattr(callback_result, "load_health", None) is not True:
            return "load_failed"
        if getattr(callback_result, "ocr_health", None) is not True:
            return "ocr_failed"
        if getattr(callback_result, "identity_health", None) is not True:
            return "switch_failed"
        if (
            getattr(decision, "position_status", None) != "same"
            or getattr(decision, "insufficient_evidence", True)
        ):
            return "position_unresolved"
        return None

    @staticmethod
    def _critical_callback_failure_reason(callback_result: object) -> Optional[str]:
        """Classify a saved formal slot before it can support a safe/full end."""

        if callback_result is None:
            return "position_unresolved"
        explicit_reason = getattr(callback_result, "failure_reason", None)
        if explicit_reason in (
            "load_failed", "switch_failed", "scroll_failed", "ocr_failed",
            "focus_restore_failed", "position_unresolved", "store_failed",
            "unexpected_error",
        ):
            return explicit_reason
        if getattr(callback_result, "saved", False) is not True:
            return "store_failed"
        if getattr(callback_result, "load_health", None) is not True:
            return "load_failed"
        if getattr(callback_result, "ocr_health", None) is not True:
            return "ocr_failed"
        if getattr(callback_result, "identity_health", None) is not True:
            return "switch_failed"
        if (
            getattr(callback_result, "record", None) is None
            or getattr(callback_result, "position_decision", None) is None
        ):
            return "position_unresolved"
        return None

    @staticmethod
    def _is_full_no_new_slot(callback_result: object) -> bool:
        """Accept only one fully healthy, saved changed formal R05/R06 record."""

        if OCRKeywordDetector._critical_callback_failure_reason(callback_result):
            return False
        record = getattr(callback_result, "record", None)
        decision = getattr(callback_result, "position_decision", None)
        result = _record_value(record, "similarity_result")
        return (
            _enum_value(_record_value(record, "capture_type")) == "formal_screen"
            and _record_value(record, "is_formal_screen") is True
            and getattr(decision, "position_status", None) == "changed"
            and _enum_value(_record_value(record, "aggregation_status")) == "completed"
            and result is not None
            and _enum_value(getattr(result, "similarity_status", None)) == "completed"
            and _enum_value(getattr(result, "effective_new_status", None)) == "none"
            and not _record_has_uncertain_evidence(record)
            and not _record_has_effective_new_content(record)
        )

    def _safe_full_control_result(
        self,
        callback_result: object,
        observations: List[ScanObservation],
        *,
        allow_no_new: bool,
        scroll_bottom_confirmed: bool = False,
        recovery_reason: Optional[str] = None,
    ) -> Optional[DetectionResult]:
        """Apply the frozen safe/full priority after one slot's Store result."""

        state = self.dynamic_end_state
        if state.mode not in ("safe", "full"):
            return None
        interrupt_reason = self._interrupt_reason()
        if interrupt_reason is not None:
            return DetectionResult(
                success=True,
                confirmed_match=False,
                scans_completed=state.scan_slot_count,
                observations=observations,
                interrupt_reason=interrupt_reason,
                recovery_reason=recovery_reason,
                **{
                    key: value
                    for key, value in self._dynamic_result_fields(
                        normal_completion=False,
                    ).items()
                    if key != "interrupt_reason"
                },
            )

        failure_reason = self._critical_callback_failure_reason(callback_result)
        if failure_reason is not None:
            return DetectionResult(
                success=True,
                confirmed_match=False,
                scans_completed=state.scan_slot_count,
                observations=observations,
                abort_reason=failure_reason,
                recovery_reason=recovery_reason,
                **self._dynamic_result_fields(normal_completion=False),
            )

        if state.scan_slot_count >= min(self.max_scans, 8):
            return DetectionResult(
                success=True,
                confirmed_match=False,
                scans_completed=state.scan_slot_count,
                observations=observations,
                dynamic_end_reason="max_screen_limit",
                recovery_reason=recovery_reason,
                **self._dynamic_result_fields(normal_completion=True),
            )

        if scroll_bottom_confirmed:
            return DetectionResult(
                success=True,
                confirmed_match=False,
                scans_completed=state.scan_slot_count,
                observations=observations,
                dynamic_end_reason="scroll_bottom",
                scroll_bottom_candidate=True,
                recovery_reason=recovery_reason,
                **self._dynamic_result_fields(normal_completion=False),
            )

        if state.mode == "full" and allow_no_new:
            if self._is_full_no_new_slot(callback_result):
                state.consecutive_no_new_count += 1
            else:
                state.consecutive_no_new_count = 0
            if state.consecutive_no_new_count >= self.dynamic_end_config.no_new_text_threshold:
                return DetectionResult(
                    success=True,
                    confirmed_match=False,
                    scans_completed=state.scan_slot_count,
                    observations=observations,
                    dynamic_end_reason="no_new_text",
                    recovery_reason=recovery_reason,
                    **self._dynamic_result_fields(normal_completion=False),
                )
        elif state.mode == "full":
            state.consecutive_no_new_count = 0
        return None

    def _recovery_is_allowed(
        self,
        callback_result: object,
        scan_number: int,
    ) -> bool:
        state = self.dynamic_end_state
        decision = getattr(callback_result, "position_decision", None)
        return (
            state.mode in ("safe", "full")
            and scan_number > 1
            and state.normal_scroll_count > 0
            and state.recovery_used is False
            and state.scan_slot_count < 8
            and scan_number < min(self.max_scans, 8)
            and getattr(callback_result, "saved", False) is True
            and getattr(decision, "position_status", None) == "same"
            and getattr(callback_result, "load_health", None) is True
            and getattr(callback_result, "ocr_health", None) is True
            and getattr(callback_result, "identity_health", None) is True
            and self._interrupt_reason() is None
        )

    def _rule_confirmation_result(
        self,
        first: ScanObservation,
        scan_number: int,
        observations: List[ScanObservation],
    ) -> DetectionResult:
        """Preserve the existing one-rule-confirmation early-return contract."""

        self.wait(self.confirmation_seconds)
        confirmation = self._observe(scan_number, [first.matched_rule])
        observations.append(confirmation)
        callback_result = self._notify_observation(
            confirmation,
            "rule_confirmation",
            False,
            scan_number,
        )
        self.last_observation_result = callback_result
        self._update_dynamic_end_state(
            callback_result, is_formal_screen=False,
        )
        confirmed = confirmation.matched_rule == first.matched_rule
        self._consume_rule_confirmation(callback_result, confirmed)
        return DetectionResult(
            success=True,
            confirmed_match=confirmed,
            matched_keyword=first.matched_keyword if confirmed else None,
            scans_completed=self.dynamic_end_state.scan_slot_count,
            observations=observations,
            error=None if confirmed else "second OCR pass did not confirm the match",
            scroll_bottom_candidate=self.saw_scroll_bottom_candidate,
            recovery_reason=(
                self.last_position_confirmation.reason
                if self.last_position_confirmation is not None else None
            ),
            **self._dynamic_result_fields(normal_completion=False),
        )

    def _position_confirmation_capture_type(
        self,
        observation: ScanObservation,
    ) -> Tuple[str, bool, Optional[int]]:
        """Route exact-different confirmation evidence into its promoted formal slot.

        This is a best-guess pre-classification used before the canonical
        ``PositionDecision`` is available.  The final decision is resolved in
        ``_final_confirmation_capture_type`` after the callback returns.
        """

        fingerprint = observation.fingerprint
        current_hash = getattr(fingerprint, "exact_hash", None)
        previous_hash = self.dynamic_end_state.last_comparable_exact_hash
        if (
            isinstance(current_hash, str)
            and isinstance(previous_hash, str)
            and current_hash != previous_hash
        ):
            slot = min(8, self.dynamic_end_state.scan_slot_count + 1)
            bind_fingerprint_screen_index(observation, slot)
            return "formal_screen", True, slot
        return "position_confirmation", False, None

    @staticmethod
    def _final_confirmation_capture_type(
        decision: Optional[PositionDecision],
        pre_capture_type: str,
        pre_is_formal: bool,
        pre_screen_index: Optional[int],
        state: DynamicEndState,
    ) -> Tuple[str, bool, Optional[int]]:
        """Resolve the authoritative capture type using the canonical PositionDecision.

        When the pre-classification says ``position_confirmation`` but the
        canonical decision says ``changed`` (e.g. due to effective new content
        or short_text_protected), the capture must be promoted to a formal
        screen.  The same capture must only be saved once.
        """
        if (
            pre_capture_type == "position_confirmation"
            and decision is not None
            and decision.position_status == "changed"
        ):
            slot = min(8, state.scan_slot_count + 1)
            return "formal_screen", True, slot
        return pre_capture_type, pre_is_formal, pre_screen_index

    def _attempt_position_confirmation(
        self,
        rules: Iterable[KeywordRule],
        observations: List[ScanObservation],
    ) -> Tuple[PositionConfirmationResult, Optional[DetectionResult]]:
        """Run the single safe/full recovery sequence without ending the scan."""

        state = self.dynamic_end_state
        state.recovery_used = True
        interrupt_reason = self._interrupt_reason()
        if interrupt_reason is not None:
            return PositionConfirmationResult(True, False, interrupt_reason), None
        if self.restore_focus is None:
            return PositionConfirmationResult(True, False, "focus_restore_failed"), None

        state.focus_restore_count += 1
        try:
            focus_restored = self.restore_focus() is True
        except Exception:
            focus_restored = False
        if not focus_restored:
            return PositionConfirmationResult(True, False, "focus_restore_failed"), None
        interrupt_reason = self._interrupt_reason()
        if interrupt_reason is not None:
            return PositionConfirmationResult(True, False, interrupt_reason), None
        if self.scroll is None:
            return PositionConfirmationResult(True, False, "scroll_failed"), None

        state.scroll_retry_count += 1
        try:
            self.scroll()
        except Exception:
            interrupt_reason = self._interrupt_reason()
            return PositionConfirmationResult(
                True, False, interrupt_reason or "scroll_failed",
            ), None
        interrupt_reason = self._interrupt_reason()
        if interrupt_reason is not None:
            return PositionConfirmationResult(True, False, interrupt_reason), None
        try:
            self.wait(self.settle_seconds)
        except Exception:
            interrupt_reason = self._interrupt_reason()
            return PositionConfirmationResult(
                True, False, interrupt_reason or "position_unresolved",
            ), None
        interrupt_reason = self._interrupt_reason()
        if interrupt_reason is not None:
            return PositionConfirmationResult(True, False, interrupt_reason), None

        next_scan_number = min(8, state.scan_slot_count + 1)
        try:
            confirmation = self.capture_observation(next_scan_number)
        except Exception:
            interrupt_reason = self._interrupt_reason()
            return PositionConfirmationResult(
                True, False, interrupt_reason or "ocr_failed",
            ), None
        interrupt_reason = self._interrupt_reason()
        if interrupt_reason is not None:
            return PositionConfirmationResult(True, False, interrupt_reason), None
        try:
            confirmation = self._match_observation(confirmation, rules)
        except Exception:
            return PositionConfirmationResult(True, False, "ocr_failed"), None
        observations.append(confirmation)
        pre_capture_type, pre_is_formal, pre_screen_index = (
            self._position_confirmation_capture_type(confirmation)
        )
        callback_result = self._notify_observation(
            confirmation, pre_capture_type, pre_is_formal, pre_screen_index,
        )
        self.last_observation_result = callback_result
        # G3: The canonical PositionDecision is the sole authority for the
        # final capture type.  When the pre-classification says
        # position_confirmation but the decision says changed (e.g. due to
        # effective new content / short_text_protected), the capture must be
        # promoted to a formal screen.  The same capture must only be saved
        # once — no second OCR, build, R05/R06, or Store.
        final_decision = getattr(callback_result, "position_decision", None)
        capture_type, is_formal_screen, screen_index = (
            self._final_confirmation_capture_type(
                final_decision,
                pre_capture_type, pre_is_formal, pre_screen_index,
                state,
            )
        )
        self._update_dynamic_end_state(
            callback_result, is_formal_screen=is_formal_screen,
        )
        if is_formal_screen:
            self._consume_shadow_formal_callback(callback_result)

        if confirmation.matched_rule is not None:
            recovery = PositionConfirmationResult(
                True, False, "rule_match",
                record=getattr(callback_result, "record", None),
                saved=getattr(callback_result, "saved", False) is True,
                position_decision=getattr(callback_result, "position_decision", None),
                promoted_slot=is_formal_screen,
            )
            return recovery, self._rule_confirmation_result(
                confirmation, self.dynamic_end_state.scan_slot_count, observations,
            )

        failure_reason = self._callback_failure_reason(callback_result)
        bottom_candidate = (
            capture_type == "position_confirmation"
            and failure_reason is None
        )
        return PositionConfirmationResult(
            True,
            bottom_candidate,
            (
                "scroll_bottom_candidate" if bottom_candidate
                else "position_changed" if is_formal_screen
                and failure_reason == "position_unresolved"
                else failure_reason
            ),
            record=getattr(callback_result, "record", None),
            saved=getattr(callback_result, "saved", False) is True,
            position_decision=getattr(callback_result, "position_decision", None),
            promoted_slot=is_formal_screen,
        ), None

    def capture_observation(self, scan_number: int) -> ScanObservation:
        started = time.perf_counter()
        image = self.capture.capture(self.region)
        raw_items = list(self.backend.recognize(image))
        accepted_items = accepted_ocr_items(raw_items, self.min_confidence)
        ocr_box_count, ocr_text_length = calculate_load_metrics(accepted_items)
        text = searchable_text(accepted_items)
        captured_at = datetime.now().astimezone()
        screen_id = str(uuid4())
        try:
            fingerprint = build_screen_fingerprint(
                accepted_items,
                captured_at=captured_at,
            )
        except Exception as exc:
            fingerprint = None
            _log_fingerprint_generation_failed(scan_number, type(exc).__name__)
        normalization_boxes = tuple(
            NormalizationBox(
                box_id="{0}:box:{1}".format(screen_id, original_index),
                raw_text=item.text,
                bbox=item.box,
                original_index=original_index,
                confidence=getattr(item, "confidence", None),
            )
            for original_index, item in enumerate(raw_items)
        )
        try:
            eligible_box_ids = eligible_box_ids_for_config(
                normalization_boxes,
                self.normalization_config,
            )
            normalization = normalize_ocr_text(
                normalization_boxes,
                eligible_box_ids=eligible_box_ids,
                config=self.normalization_config,
            )
        except Exception as exc:
            normalization = failed_normalization_result(
                normalization_boxes,
                error_type=type(exc).__name__,
                config=self.normalization_config,
            )
        observation = ScanObservation(
            scan_number=scan_number,
            text=text,
            item_count=len(raw_items),
            elapsed_seconds=time.perf_counter() - started,
            ocr_box_count=ocr_box_count,
            ocr_text_length=ocr_text_length,
            fingerprint=fingerprint,
            raw_items=tuple(raw_items),
            captured_at=captured_at.isoformat(),
            screen_id=screen_id,
            normalization=normalization,
            normalization_min_confidence=self.min_confidence,
        )
        if fingerprint is not None:
            _log_fingerprint_generated(observation)
        return observation

    def _match_observation(
        self,
        observation: ScanObservation,
        rules: Iterable[KeywordRule],
    ) -> ScanObservation:
        rules = tuple(rules)
        legacy_rule = matching_keyword_rule(observation.text, rules)
        legacy_rule_index = _matched_rule_index(legacy_rule, rules)
        normalization = observation.normalization
        if (
            normalization is None
            or normalization.status != NORMALIZATION_COMPLETED
            or normalization.comparison_text is None
        ):
            r04_rule = None
            r04_match = None
            r04_rule_index = None
            comparison_outcome = RULE_COMPARISON_NORMALIZATION_FAILED
        else:
            r04_rule = matching_keyword_rule(
                normalization.comparison_text,
                rules,
            )
            r04_match = r04_rule is not None
            r04_rule_index = _matched_rule_index(r04_rule, rules)
            if legacy_rule is not None and r04_match:
                comparison_outcome = RULE_COMPARISON_SAME_MATCH
            elif legacy_rule is None and not r04_match:
                comparison_outcome = RULE_COMPARISON_SAME_NO_MATCH
            elif legacy_rule is not None:
                comparison_outcome = RULE_COMPARISON_LEGACY_ONLY
            else:
                comparison_outcome = RULE_COMPARISON_R04_ONLY

        observation.rule_comparison = RuleComparisonResult(
            rule_evaluation_mode=self.rule_evaluation_mode,
            legacy_match=legacy_rule is not None,
            r04_match=r04_match,
            comparison_outcome=comparison_outcome,
            legacy_rule_index=legacy_rule_index,
            r04_rule_index=r04_rule_index,
        )
        # Change 5A keeps legacy rule evaluation authoritative.  R04 is
        # observational only and cannot trigger confirmation or actions.
        observation.matched_keyword = (
            legacy_rule.source if legacy_rule is not None else None
        )
        observation.matched_rule = legacy_rule
        return observation

    def _observe(self, scan_number: int, rules: Iterable[KeywordRule]):
        observation = self.capture_observation(scan_number)
        return self._match_observation(observation, rules)

    def detect(
        self,
        rules: Iterable[KeywordRule],
        first_observation: Optional[ScanObservation] = None,
    ) -> DetectionResult:
        rules = list(rules)
        if not rules:
            return DetectionResult(success=True, confirmed_match=False)

        observations = []
        self.dynamic_end_state = DynamicEndState(mode=self.dynamic_end_config.mode)
        self.last_observation_result = None
        self.last_position_confirmation = None
        self.saw_scroll_bottom_candidate = False
        self._shadow_prediction = ShadowPredictionAnalysis()
        promoted_slot_to_skip = None
        try:
            for scan_number in range(1, self.max_scans + 1):
                if promoted_slot_to_skip == scan_number:
                    promoted_slot_to_skip = None
                    continue
                if scan_number > 1:
                    if self.scroll is None:
                        break
                    self.scroll()
                    self.dynamic_end_state.normal_scroll_count = min(
                        7, self.dynamic_end_state.normal_scroll_count + 1,
                    )
                    self.wait(self.settle_seconds)

                if scan_number == 1 and first_observation is not None:
                    first = first_observation
                else:
                    first = self.capture_observation(scan_number)
                bind_fingerprint_screen_index(first, scan_number)
                first = self._match_observation(first, rules)
                observations.append(first)
                callback_result = self._notify_observation(
                    first,
                    "formal_screen",
                    True,
                    scan_number,
                )
                self.last_observation_result = callback_result
                self._update_dynamic_end_state(
                    callback_result, is_formal_screen=True,
                )
                self._consume_shadow_formal_callback(callback_result)
                if first is not first_observation:
                    logger.info(
                        "OCR scan %s/%s: %s items, %.3fs, match=%r",
                        scan_number,
                        self.max_scans,
                        first.item_count,
                        first.elapsed_seconds,
                        first.matched_keyword,
                    )
                if first.matched_rule is None:
                    control_result = self._safe_full_control_result(
                        callback_result,
                        observations,
                        allow_no_new=True,
                    )
                    if control_result is not None:
                        return control_result
                    if self._recovery_is_allowed(callback_result, scan_number):
                        recovery, rule_result = self._attempt_position_confirmation(
                            rules, observations,
                        )
                        self.last_position_confirmation = recovery
                        self.saw_scroll_bottom_candidate = (
                            self.saw_scroll_bottom_candidate
                            or recovery.bottom_candidate
                        )
                        if rule_result is not None:
                            return replace(
                                rule_result,
                                scroll_bottom_candidate=recovery.bottom_candidate,
                                recovery_reason=recovery.reason,
                            )
                        if recovery.reason in (
                            "user_interrupted", "runtime_expired",
                        ):
                            return DetectionResult(
                                success=True,
                                confirmed_match=False,
                                scans_completed=self.dynamic_end_state.scan_slot_count,
                                observations=observations,
                                interrupt_reason=recovery.reason,
                                recovery_reason=recovery.reason,
                                **{
                                    key: value
                                    for key, value in self._dynamic_result_fields(
                                        normal_completion=False,
                                    ).items()
                                    if key != "interrupt_reason"
                                },
                            )
                        if recovery.reason not in (
                            None, "scroll_bottom_candidate", "position_changed",
                        ):
                            return DetectionResult(
                                success=True,
                                confirmed_match=False,
                                scans_completed=self.dynamic_end_state.scan_slot_count,
                                observations=observations,
                                abort_reason=recovery.reason,
                                recovery_reason=recovery.reason,
                                **self._dynamic_result_fields(normal_completion=False),
                            )
                        recovery_control = self._safe_full_control_result(
                            self.last_observation_result,
                            observations,
                            allow_no_new=recovery.promoted_slot,
                            scroll_bottom_confirmed=recovery.bottom_candidate,
                            recovery_reason=recovery.reason,
                        )
                        if recovery_control is not None:
                            return recovery_control
                        if recovery.promoted_slot:
                            promoted_slot_to_skip = scan_number + 1
                    continue

                # G5: In safe/full, check Store failure BEFORE entering rule
                # confirmation.  The frozen priority is: interrupt → Store/tech
                # failure → confirmed rule → slot limit → bottom → no-new → continue.
                # off/shadow keep legacy rule-early-stop behaviour unchanged.
                pre_rule_control = self._safe_full_control_result(
                    callback_result,
                    observations,
                    allow_no_new=False,
                )
                if pre_rule_control is not None:
                    return pre_rule_control

                return self._rule_confirmation_result(
                    first, scan_number, observations,
                )

            return DetectionResult(
                success=True,
                confirmed_match=False,
                scans_completed=self.dynamic_end_state.scan_slot_count,
                observations=observations,
                scroll_bottom_candidate=self.saw_scroll_bottom_candidate,
                recovery_reason=(
                    self.last_position_confirmation.reason
                    if self.last_position_confirmation is not None else None
                ),
                **self._dynamic_result_fields(
                    normal_completion=(
                        self.dynamic_end_state.scan_slot_count
                        >= min(self.max_scans, 8)
                    ),
                ),
            )
        except Exception as exc:
            self._shadow_prediction.technical_failure = True
            interrupt_reason = self._interrupt_reason()
            if (
                self.dynamic_end_state.mode in ("safe", "full")
                and interrupt_reason is not None
            ):
                return DetectionResult(
                    success=True,
                    confirmed_match=False,
                    scans_completed=self.dynamic_end_state.scan_slot_count,
                    observations=observations,
                    interrupt_reason=interrupt_reason,
                    **{
                        key: value
                        for key, value in self._dynamic_result_fields(
                            normal_completion=False,
                        ).items()
                        if key != "interrupt_reason"
                    },
                )
            logger.error(
                "OCR keyword detection failed error_type=%s",
                type(exc).__name__,
            )
            return DetectionResult(
                success=False,
                confirmed_match=False,
                scans_completed=len([item for item in observations if item.scan_number]),
                observations=observations,
                error=str(exc),
                **self._dynamic_result_fields(normal_completion=False),
            )
