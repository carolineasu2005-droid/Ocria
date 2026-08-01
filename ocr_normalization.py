"""Platform-neutral OCR evidence projection and readable text normalization.

Change 2 provides geometry adaptation and deterministic reading order.  Change
3 adds conservative, auditable ``raw_text`` and ``normalized_text`` semantics
on top of that order.  Change 4 derives protected ``comparison_text`` for local
exact comparison.  Change 5 conservatively suppresses confirmed same-screen
OCR duplicate boxes from derived text only.  This module does not deduplicate
across screens/candidates or integrate with the online detector/storage path.
Callers retain ownership of the raw boxes, their per-box ``raw_text`` values,
and their original bbox values; every function in this module is non-mutating.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import re
from statistics import median
import unicodedata
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple


BBOX_MISSING = "bbox_missing"
BBOX_EMPTY = "bbox_empty"
BBOX_INVALID_TYPE = "bbox_invalid_type"
BBOX_INVALID_FLAT_COUNT = "bbox_invalid_flat_count"
BBOX_INVALID_POINT_COUNT = "bbox_invalid_point_count"
BBOX_INVALID_POINT = "bbox_invalid_point"
BBOX_MIXED_FORMAT = "bbox_mixed_format"
BBOX_INVALID_NUMBER = "bbox_invalid_number"
BBOX_NON_FINITE = "bbox_non_finite"
BBOX_NEGATIVE_SIZE = "bbox_negative_size"

BOX_TEXT_NORMALIZATION_FAILED = "box_text_normalization_failed"
RAW_TEXT_BUILD_FAILED = "raw_text_build_failed"
READING_ORDER_BUILD_FAILED = "reading_order_build_failed"
ALL_BOX_TEXT_NORMALIZATION_FAILED = "all_box_text_normalization_failed"
LAYOUT_DEGRADED = "layout_degraded"
COMPARISON_TEXT_BUILD_FAILED = "comparison_text_build_failed"
DUPLICATE_DETECTION_FAILED = "duplicate_detection_failed"

NORMALIZATION_COMPLETED = "completed"
NORMALIZATION_FAILED = "failed"
# Algorithm identity shared by online processing, JSONL records, and offline
# replay.  Storage owns its own independently versioned schema contract.
NORMALIZATION_VERSION = "r04-v1"
NORMALIZATION_CONFIG_VERSION = "r04-config-v1"
UNKNOWN_CONFIDENCE_POLICY_INCLUDE = "include"

RAW_TEXT_SOURCE_ENGINE_SCREEN = "engine_screen_text"
RAW_TEXT_SOURCE_DERIVED_BOXES = "derived_from_box_raw_text"

_WHITESPACE_PATTERN = re.compile(r"\s+")

_OPENING_PUNCTUATION = frozenset("([{<（【《「『")
_CLOSING_PUNCTUATION = frozenset(")]}>）】》」』,.;:!?，。；：！？、%％")
_CONNECTOR_CHARACTERS = frozenset("+#./-_\\")

_COMPARISON_TOKEN_PATTERN = re.compile(r"[\w.+#/\-_]+", re.UNICODE)


class OcrGeometryError(ValueError):
    """A sanitized bbox error that never includes OCR text or coordinates."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OcrDuplicateTextKeyError(ValueError):
    """Sanitized failure while deriving one duplicate-comparison key."""


@dataclass(frozen=True)
class OcrNormalizationConfig:
    """Centralized geometry, joining, and same-screen duplicate thresholds.

    These are the R04 TID's initial suggested values and still require
    validation against synthetic fixtures and controlled Windows + Edge data.
    """

    normalization_config_version: str = NORMALIZATION_CONFIG_VERSION
    effective_min_confidence: float = 0.85
    unknown_confidence_policy: str = UNKNOWN_CONFIDENCE_POLICY_INCLUDE
    line_tolerance_height_ratio: float = 0.45
    line_tolerance_min_px: float = 4.0
    line_tolerance_max_px: float = 18.0
    line_pair_height_ratio: float = 0.50
    same_line_vertical_overlap_ratio: float = 0.50
    compact_join_gap_height_ratio: float = 0.25
    symbol_join_gap_height_ratio: float = 0.75
    duplicate_candidate_margin_height_ratio: float = 1.00
    duplicate_confirm_iou: float = 0.85
    duplicate_confirm_center_ratio: float = 0.20
    duplicate_confirm_size_similarity: float = 0.90
    duplicate_secondary_iou: float = 0.70
    duplicate_secondary_size_similarity: float = 0.95
    duplicate_gray_iou: float = 0.65
    duplicate_gray_center_ratio: float = 0.35
    duplicate_gray_size_similarity: float = 0.80

    def __post_init__(self) -> None:
        if self.normalization_config_version != NORMALIZATION_CONFIG_VERSION:
            raise ValueError("unsupported normalization config version")
        if (
            isinstance(self.effective_min_confidence, bool)
            or not isinstance(self.effective_min_confidence, (int, float))
            or not math.isfinite(float(self.effective_min_confidence))
            or not 0.0 <= float(self.effective_min_confidence) <= 1.0
        ):
            raise ValueError("effective min confidence must be between zero and one")
        if self.unknown_confidence_policy != UNKNOWN_CONFIDENCE_POLICY_INCLUDE:
            raise ValueError("unsupported unknown confidence policy")
        numeric_values = (
            self.line_tolerance_height_ratio,
            self.line_tolerance_min_px,
            self.line_tolerance_max_px,
            self.line_pair_height_ratio,
            self.same_line_vertical_overlap_ratio,
            self.compact_join_gap_height_ratio,
            self.symbol_join_gap_height_ratio,
            self.duplicate_candidate_margin_height_ratio,
            self.duplicate_confirm_iou,
            self.duplicate_confirm_center_ratio,
            self.duplicate_confirm_size_similarity,
            self.duplicate_secondary_iou,
            self.duplicate_secondary_size_similarity,
            self.duplicate_gray_iou,
            self.duplicate_gray_center_ratio,
            self.duplicate_gray_size_similarity,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in numeric_values
        ):
            raise ValueError("normalization config values must be finite numbers")
        if (
            self.line_tolerance_height_ratio < 0
            or self.line_tolerance_min_px < 0
            or self.line_tolerance_max_px < self.line_tolerance_min_px
            or self.line_pair_height_ratio < 0
            or not 0 <= self.same_line_vertical_overlap_ratio <= 1
            or self.compact_join_gap_height_ratio < 0
            or self.symbol_join_gap_height_ratio < 0
            or self.duplicate_candidate_margin_height_ratio < 0
            or not 0 <= self.duplicate_confirm_iou <= 1
            or self.duplicate_confirm_center_ratio < 0
            or not 0 <= self.duplicate_confirm_size_similarity <= 1
            or not 0 <= self.duplicate_secondary_iou <= 1
            or not 0 <= self.duplicate_secondary_size_similarity <= 1
            or not 0 <= self.duplicate_gray_iou <= 1
            or self.duplicate_gray_center_ratio < 0
            or not 0 <= self.duplicate_gray_size_similarity <= 1
        ):
            raise ValueError("normalization config values are out of range")


DEFAULT_OCR_NORMALIZATION_CONFIG = OcrNormalizationConfig()


def canonical_normalization_config(
    config: OcrNormalizationConfig,
) -> Dict[str, Any]:
    """Return the complete run-level canonical R04 configuration snapshot."""

    if not isinstance(config, OcrNormalizationConfig):
        raise TypeError("normalization config has an invalid contract")
    return {
        "normalization_version": NORMALIZATION_VERSION,
        **asdict(config),
    }


def canonical_normalization_config_json(
    config_or_snapshot: Any,
) -> str:
    """Serialize a complete snapshot with the frozen digest representation."""

    snapshot = (
        canonical_normalization_config(config_or_snapshot)
        if isinstance(config_or_snapshot, OcrNormalizationConfig)
        else dict(config_or_snapshot)
    )
    if "normalization_config_digest" in snapshot:
        raise ValueError("normalization config snapshot cannot contain its digest")
    try:
        return json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("normalization config snapshot is not canonicalizable") from exc


def normalization_config_digest(config_or_snapshot: Any) -> str:
    """Return SHA-256 over canonical UTF-8 JSON, excluding the digest itself."""

    canonical = canonical_normalization_config_json(config_or_snapshot)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalization_config_from_snapshot(
    snapshot: Any,
) -> OcrNormalizationConfig:
    """Restore a config only from a complete, exact historical snapshot."""

    if not isinstance(snapshot, dict):
        raise ValueError("normalization config snapshot must be an object")
    expected_keys = {"normalization_version", *asdict(DEFAULT_OCR_NORMALIZATION_CONFIG)}
    if set(snapshot) != expected_keys:
        raise ValueError("normalization config snapshot fields are incomplete")
    if snapshot.get("normalization_version") != NORMALIZATION_VERSION:
        raise ValueError("unsupported normalization version")
    values = {
        key: value
        for key, value in snapshot.items()
        if key != "normalization_version"
    }
    try:
        return OcrNormalizationConfig(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("normalization config snapshot is invalid") from exc


def config_with_effective_min_confidence(
    config: OcrNormalizationConfig,
    effective_min_confidence: float,
) -> OcrNormalizationConfig:
    """Return one immutable config with the actual run confidence threshold."""

    return replace(
        config,
        effective_min_confidence=float(effective_min_confidence),
    )


def eligible_box_ids_for_config(
    boxes: Iterable[Any],
    config: OcrNormalizationConfig,
) -> Tuple[str, ...]:
    """Apply the versioned confidence policy without exposing evidence."""

    eligible = []
    for value in boxes:
        box = _project_box(value)
        confidence = box.confidence
        if confidence is None:
            if config.unknown_confidence_policy == UNKNOWN_CONFIDENCE_POLICY_INCLUDE:
                eligible.append(box.box_id)
            continue
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            raise ValueError("OCR confidence is invalid")
        if float(confidence) >= config.effective_min_confidence:
            eligible.append(box.box_id)
    return tuple(eligible)


@dataclass(frozen=True)
class NormalizationBox:
    """Minimal immutable projection over one raw OCR evidence box."""

    box_id: str
    raw_text: str
    bbox: Any
    original_index: int
    confidence: Optional[float] = None


@dataclass(frozen=True)
class BoxGeometry:
    """Axis-aligned geometry derived without replacing the source bbox."""

    source_shape: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    center_x: float
    center_y: float
    width: float
    height: float

    @property
    def effective_height(self) -> float:
        return max(1.0, self.height)

    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass(frozen=True)
class BoxGeometryEntry:
    box_id: str
    original_index: int
    geometry: Optional[BoxGeometry]


@dataclass(frozen=True)
class NormalizationWarning:
    box_id: str
    code: str


@dataclass(frozen=True)
class LineGroup:
    line_index: int
    box_ids: Tuple[str, ...]
    median_center_y: Optional[float]
    median_height: Optional[float]
    has_valid_geometry: bool


@dataclass(frozen=True)
class BoxLineAssignment:
    box_id: str
    line_index: int


@dataclass(frozen=True)
class ReadingOrderResult:
    ordered_box_ids: Tuple[str, ...]
    line_groups: Tuple[LineGroup, ...]
    line_mapping: Tuple[BoxLineAssignment, ...]
    excluded_empty_box_ids: Tuple[str, ...]
    normalization_warnings: Tuple[NormalizationWarning, ...]
    box_geometries: Tuple[BoxGeometryEntry, ...]
    median_box_height: Optional[float]
    base_line_tolerance: Optional[float]

    @property
    def line_index_by_box_id(self) -> Dict[str, int]:
        return {
            assignment.box_id: assignment.line_index
            for assignment in self.line_mapping
        }


@dataclass(frozen=True)
class NormalizedLine:
    """One visual line after conservative same-line fragment joining."""

    line_index: int
    box_ids: Tuple[str, ...]
    normalized_text: str


@dataclass(frozen=True)
class TextNormalizationResult:
    """Change 3 result that references, but never rewrites, raw evidence.

    ``raw_text_source`` makes the evidence semantics explicit.  Engine screen
    text is retained character-for-character when supplied.  Otherwise the
    field is a projection of per-box evidence ordered by ``original_index``
    (then ``box_id`` for a deterministic tie) with one inserted LF separator.
    In that derived case, ``raw_boxes[*].raw_text`` remain the higher-authority
    source because the inserted separators are not OCR-engine evidence.
    """

    status: str
    normalization_version: str
    normalization_config_version: str
    normalization_config_digest: str
    effective_min_confidence: float
    raw_text: Optional[str]
    raw_text_source: Optional[str]
    raw_text_length: Optional[int]
    normalized_text: Optional[str]
    normalized_text_length: Optional[int]
    comparison_text: Optional[str]
    comparison_text_length: Optional[int]
    effective_box_ids: Tuple[str, ...]
    ordered_box_ids: Tuple[str, ...]
    line_groups: Tuple[LineGroup, ...]
    line_mapping: Tuple[BoxLineAssignment, ...]
    normalized_lines: Tuple[NormalizedLine, ...]
    excluded_empty_box_ids: Tuple[str, ...]
    deduplicated_box_count: int
    duplicate_groups: Tuple["DuplicateGroup", ...]
    suppressed_duplicate_box_ids: Tuple[str, ...]
    duplicate_pair_evidence: Tuple["DuplicatePairEvidence", ...]
    duplicate_risk: bool
    duplicate_candidate_pair_count: int
    duplicate_confirmation_count: int
    duplicate_gray_pair_count: int
    eligible_box_count: int
    low_confidence_box_count: int
    empty_normalized_box_count: int
    normalization_warnings: Tuple[NormalizationWarning, ...]
    normalization_error_type: Optional[str]


@dataclass(frozen=True)
class ComparisonTextPart:
    """One lossless comparison-text part with explicit token protection."""

    text: str
    is_protected_token: bool


@dataclass(frozen=True)
class DuplicatePairEvidence:
    """Sanitized text/geometry scores for one confirmed or gray pair."""

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
    basis: Tuple[str, ...]


@dataclass(frozen=True)
class DuplicateGroup:
    """Boxes directly confirmed against one retained survivor."""

    retained_box_id: str
    suppressed_duplicate_box_ids: Tuple[str, ...]
    source_box_ids: Tuple[str, ...]
    pair_evidence: Tuple[DuplicatePairEvidence, ...]


@dataclass(frozen=True)
class DuplicateDetectionResult:
    deduplicated_box_count: int
    retained_box_ids: Tuple[str, ...]
    duplicate_groups: Tuple[DuplicateGroup, ...]
    suppressed_duplicate_box_ids: Tuple[str, ...]
    pair_evidence: Tuple[DuplicatePairEvidence, ...]
    duplicate_risk: bool
    candidate_pair_count: int
    confirmation_count: int
    duplicate_gray_pair_count: int


@dataclass(frozen=True)
class _DuplicatePreparedBox:
    box: NormalizationBox
    comparison_key: str
    geometry: BoxGeometry


@dataclass(frozen=True)
class _PreparedBox:
    box_id: str
    raw_text: str
    original_index: int
    geometry: Optional[BoxGeometry]


def _as_sequence(value: Any) -> Optional[Tuple[Any, ...]]:
    if isinstance(value, (str, bytes, bytearray)):
        return None
    try:
        return tuple(value)
    except TypeError:
        return None


def _coordinate(value: Any) -> float:
    if isinstance(value, (bool, str, bytes, bytearray)):
        raise OcrGeometryError(BBOX_INVALID_NUMBER)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise OcrGeometryError(BBOX_INVALID_NUMBER) from exc
    if not math.isfinite(number):
        raise OcrGeometryError(BBOX_NON_FINITE)
    return number


def adapt_bbox_geometry(bbox: Any) -> BoxGeometry:
    """Adapt flat LTRB or a one-or-more-point polygon to derived geometry.

    The input object is only read.  Invalid shapes raise a sanitized error so a
    screen-level caller can retain the text box and degrade its layout safely.
    """

    if bbox is None:
        raise OcrGeometryError(BBOX_MISSING)
    values = _as_sequence(bbox)
    if values is None:
        raise OcrGeometryError(BBOX_INVALID_TYPE)
    if not values:
        raise OcrGeometryError(BBOX_EMPTY)

    nested = tuple(_as_sequence(value) for value in values)
    has_nested = any(value is not None for value in nested)
    has_scalar = any(value is None for value in nested)

    if has_nested and has_scalar:
        raise OcrGeometryError(BBOX_MIXED_FORMAT)

    if not has_nested:
        if len(values) != 4:
            raise OcrGeometryError(BBOX_INVALID_FLAT_COUNT)
        x_min, y_min, x_max, y_max = (
            _coordinate(value) for value in values
        )
        if x_max < x_min or y_max < y_min:
            raise OcrGeometryError(BBOX_NEGATIVE_SIZE)
        source_shape = "ltrb"
    else:
        if len(values) < 1:
            raise OcrGeometryError(BBOX_INVALID_POINT_COUNT)
        points = []
        for point in nested:
            if point is None or len(point) != 2:
                raise OcrGeometryError(BBOX_INVALID_POINT)
            points.append((_coordinate(point[0]), _coordinate(point[1])))
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        x_min = min(xs)
        y_min = min(ys)
        x_max = max(xs)
        y_max = max(ys)
        source_shape = "polygon"

    width = x_max - x_min
    height = y_max - y_min
    return BoxGeometry(
        source_shape=source_shape,
        x_min=x_min,
        y_min=y_min,
        x_max=x_max,
        y_max=y_max,
        center_x=(x_min + x_max) / 2.0,
        center_y=(y_min + y_max) / 2.0,
        width=width,
        height=height,
    )


def median_effective_box_height(
    boxes: Iterable[_PreparedBox],
) -> Optional[float]:
    """Return the median effective height of non-empty valid boxes."""

    heights = [
        box.geometry.effective_height
        for box in boxes
        if box.geometry is not None and box.raw_text.strip()
    ]
    return float(median(heights)) if heights else None


def _base_line_tolerance(
    median_height: float,
    config: OcrNormalizationConfig,
) -> float:
    return min(
        config.line_tolerance_max_px,
        max(
            config.line_tolerance_min_px,
            median_height * config.line_tolerance_height_ratio,
        ),
    )


def _line_stats(members: Sequence[_PreparedBox]) -> Dict[str, Any]:
    geometries = [member.geometry for member in members]
    if any(geometry is None for geometry in geometries):
        raise ValueError("line members require valid geometry")
    valid_geometries = [geometry for geometry in geometries if geometry]
    source_key = min(
        (member.original_index, member.box_id) for member in members
    )
    return {
        "median_center_y": float(
            median([geometry.center_y for geometry in valid_geometries])
        ),
        "median_height": float(
            median(
                [geometry.effective_height for geometry in valid_geometries]
            )
        ),
        "top": min(geometry.y_min for geometry in valid_geometries),
        "left": min(geometry.x_min for geometry in valid_geometries),
        "source_key": source_key,
    }


def _vertical_overlap_ratio(
    geometry: BoxGeometry,
    line_center_y: float,
    line_height: float,
) -> float:
    line_top = line_center_y - (line_height / 2.0)
    line_bottom = line_center_y + (line_height / 2.0)
    overlap = max(
        0.0,
        min(geometry.y_max, line_bottom) - max(geometry.y_min, line_top),
    )
    return overlap / min(geometry.effective_height, line_height)


def _valid_box_sort_key(box: _PreparedBox) -> Tuple[Any, ...]:
    geometry = box.geometry
    if geometry is None:
        raise ValueError("valid box sort requires geometry")
    return (
        geometry.center_y,
        geometry.y_min,
        geometry.x_min,
        geometry.y_max,
        geometry.x_max,
        box.original_index,
        box.box_id,
    )


def _member_sort_key(box: _PreparedBox) -> Tuple[Any, ...]:
    geometry = box.geometry
    if geometry is None:
        return (
            math.inf,
            math.inf,
            math.inf,
            math.inf,
            math.inf,
            box.original_index,
            box.box_id,
        )
    return (
        geometry.x_min,
        geometry.center_y,
        geometry.y_min,
        geometry.x_max,
        geometry.y_max,
        box.original_index,
        box.box_id,
    )


class _LineAccumulator:
    """Incremental medians avoid rebuilding every existing line per box."""

    def __init__(self, box: _PreparedBox) -> None:
        geometry = box.geometry
        if geometry is None:
            raise ValueError("line members require valid geometry")
        self.members = [box]
        self.centers = [geometry.center_y]
        self.heights = [geometry.effective_height]
        self.top = geometry.y_min
        self.left = geometry.x_min
        self.source_key = (box.original_index, box.box_id)

    @staticmethod
    def _median(values: Sequence[float]) -> float:
        midpoint = len(values) // 2
        if len(values) % 2:
            return float(values[midpoint])
        return float((values[midpoint - 1] + values[midpoint]) / 2.0)

    @property
    def median_center_y(self) -> float:
        return self._median(self.centers)

    @property
    def median_height(self) -> float:
        return self._median(self.heights)

    def add(self, box: _PreparedBox) -> None:
        geometry = box.geometry
        if geometry is None:
            raise ValueError("line members require valid geometry")
        self.members.append(box)
        insort(self.centers, geometry.center_y)
        insort(self.heights, geometry.effective_height)
        self.top = min(self.top, geometry.y_min)
        self.left = min(self.left, geometry.x_min)
        self.source_key = min(
            self.source_key,
            (box.original_index, box.box_id),
        )


def _group_valid_boxes(
    boxes: Sequence[_PreparedBox],
    base_tolerance: float,
    config: OcrNormalizationConfig,
) -> list[list[_PreparedBox]]:
    lines: list[_LineAccumulator] = []
    for box in sorted(boxes, key=_valid_box_sort_key):
        geometry = box.geometry
        if geometry is None:
            raise ValueError("valid box grouping requires geometry")
        candidates = []
        for line_index, line in enumerate(lines):
            center_distance = abs(
                geometry.center_y - line.median_center_y
            )
            pair_tolerance = max(
                base_tolerance,
                min(geometry.effective_height, line.median_height)
                * config.line_pair_height_ratio,
            )
            overlap_ratio = _vertical_overlap_ratio(
                geometry,
                line.median_center_y,
                line.median_height,
            )
            is_candidate = (
                center_distance <= pair_tolerance
                or overlap_ratio
                >= config.same_line_vertical_overlap_ratio
            )
            if is_candidate:
                candidates.append((
                    center_distance,
                    -overlap_ratio,
                    line.median_center_y,
                    line.top,
                    line.left,
                    line.source_key[0],
                    line.source_key[1],
                    line_index,
                ))

        if not candidates:
            lines.append(_LineAccumulator(box))
            continue

        candidates.sort()
        lines[candidates[0][-1]].add(box)
    return [line.members for line in lines]


def _project_box(value: Any) -> NormalizationBox:
    try:
        box_id = value.box_id
        raw_text = value.raw_text
        bbox = value.bbox
        original_index = value.original_index
        confidence = getattr(value, "confidence", None)
    except AttributeError as exc:
        raise ValueError("reading order input has an invalid box contract") from exc
    if not isinstance(box_id, str) or not box_id:
        raise ValueError("reading order box_id must be a non-empty string")
    if not isinstance(raw_text, str):
        raise ValueError("reading order raw_text must be a string")
    if isinstance(original_index, bool) or not isinstance(original_index, int):
        raise ValueError("reading order original_index must be an integer")
    return NormalizationBox(
        box_id,
        raw_text,
        bbox,
        original_index,
        confidence,
    )


def build_reading_order(
    boxes: Iterable[Any],
    *,
    config: OcrNormalizationConfig,
) -> ReadingOrderResult:
    """Derive deterministic lines and order without mutating raw evidence."""

    projected = [_project_box(value) for value in boxes]
    if len({box.box_id for box in projected}) != len(projected):
        raise ValueError("reading order box_id values must be unique")
    projected.sort(key=lambda box: (box.original_index, box.box_id))

    prepared = []
    entries = []
    warnings = []
    for box in projected:
        try:
            geometry = adapt_bbox_geometry(box.bbox)
        except OcrGeometryError as exc:
            geometry = None
            warnings.append(NormalizationWarning(box.box_id, exc.code))
        prepared_box = _PreparedBox(
            box_id=box.box_id,
            raw_text=box.raw_text,
            original_index=box.original_index,
            geometry=geometry,
        )
        prepared.append(prepared_box)
        entries.append(BoxGeometryEntry(
            box_id=box.box_id,
            original_index=box.original_index,
            geometry=geometry,
        ))

    excluded_empty_box_ids = tuple(
        box.box_id for box in prepared if not box.raw_text.strip()
    )
    effective_boxes = [box for box in prepared if box.raw_text.strip()]
    median_height = median_effective_box_height(effective_boxes)
    base_tolerance = (
        None
        if median_height is None
        else _base_line_tolerance(median_height, config)
    )

    valid_boxes = [box for box in effective_boxes if box.geometry is not None]
    invalid_boxes = [
        box for box in effective_boxes if box.geometry is None
    ]
    grouped_valid = (
        []
        if base_tolerance is None
        else _group_valid_boxes(valid_boxes, base_tolerance, config)
    )

    grouped_with_stats = [
        (_line_stats(members), members) for members in grouped_valid
    ]
    grouped_with_stats.sort(key=lambda item: (
        item[0]["median_center_y"],
        item[0]["top"],
        item[0]["left"],
        item[0]["source_key"][0],
        item[0]["source_key"][1],
    ))
    final_groups = [
        sorted(members, key=_member_sort_key)
        for _stats, members in grouped_with_stats
    ]
    # Unknown geometry cannot be positioned safely.  Preserve every non-empty
    # box as its own fallback line after positioned content.
    final_groups.extend(
        [box]
        for box in sorted(
            invalid_boxes,
            key=lambda box: (box.original_index, box.box_id),
        )
    )

    line_groups = []
    assignments = []
    ordered_ids = []
    for line_index, members in enumerate(final_groups):
        valid_geometry = all(member.geometry is not None for member in members)
        stats = _line_stats(members) if valid_geometry else None
        box_ids = tuple(member.box_id for member in members)
        ordered_ids.extend(box_ids)
        line_groups.append(LineGroup(
            line_index=line_index,
            box_ids=box_ids,
            median_center_y=(
                stats["median_center_y"] if stats is not None else None
            ),
            median_height=(
                stats["median_height"] if stats is not None else None
            ),
            has_valid_geometry=valid_geometry,
        ))
        assignments.extend(
            BoxLineAssignment(box_id, line_index) for box_id in box_ids
        )

    return ReadingOrderResult(
        ordered_box_ids=tuple(ordered_ids),
        line_groups=tuple(line_groups),
        line_mapping=tuple(assignments),
        excluded_empty_box_ids=excluded_empty_box_ids,
        normalization_warnings=tuple(warnings),
        box_geometries=tuple(entries),
        median_box_height=median_height,
        base_line_tolerance=base_tolerance,
    )


def derive_raw_text(
    boxes: Iterable[Any],
    *,
    engine_raw_text: Optional[str] = None,
) -> Tuple[str, str]:
    """Return screen raw text and an explicit evidence-source marker.

    An engine-provided screen string is returned exactly, including its line
    endings and control characters.  When the engine only provides boxes, the
    projection is deterministic but not claimed as byte-for-byte engine
    evidence: boxes are ordered by ``original_index`` (then ``box_id``) and
    joined with one inserted LF.  Per-box strings themselves are never changed.
    """

    if engine_raw_text is not None:
        if not isinstance(engine_raw_text, str):
            raise ValueError("engine raw text must be a string")
        return engine_raw_text, RAW_TEXT_SOURCE_ENGINE_SCREEN

    projected = [_project_box(value) for value in boxes]
    projected.sort(key=lambda box: (box.original_index, box.box_id))
    return (
        "\n".join(box.raw_text for box in projected),
        RAW_TEXT_SOURCE_DERIVED_BOXES,
    )


def normalize_box_text(raw_text: str) -> str:
    """Conservatively normalize one box without semantic rewriting.

    Visual line breaks are owned by Change 2 line groups, so whitespace inside
    an individual OCR box collapses to one ASCII space.  This step does not
    correct spelling, infer entities, replace synonyms, or discard UI labels.
    """

    if not isinstance(raw_text, str):
        raise ValueError("box raw text must be a string")

    # Readable normalization deliberately performs no compatibility folding
    # and removes no non-whitespace character.  Width compatibility belongs
    # exclusively to ``build_comparison_text()`` and its NFKC step.
    normalized = unicodedata.normalize("NFC", raw_text)
    trimmed = normalized.strip()
    return _WHITESPACE_PATTERN.sub(" ", trimmed)


def protect_comparison_tokens(value: str) -> Tuple[ComparisonTextPart, ...]:
    """Split text losslessly while marking symbol-bearing word tokens.

    A protected token is a contiguous sequence made from Unicode letters or
    numbers plus ``. + # - / _`` and contains at least one letter or number.
    This covers technical names, dates, versions, ranges, and mixed-language
    project identifiers without using a product-word dictionary.  No marker is
    injected into user text, avoiding placeholder collisions.
    """

    if not isinstance(value, str):
        raise ValueError("comparison token input must be a string")

    parts = []
    cursor = 0
    for match in _COMPARISON_TOKEN_PATTERN.finditer(value):
        token = match.group(0)
        if not any(character.isalnum() for character in token):
            continue
        if match.start() > cursor:
            parts.append(ComparisonTextPart(
                text=value[cursor:match.start()],
                is_protected_token=False,
            ))
        parts.append(ComparisonTextPart(
            text=token,
            is_protected_token=True,
        ))
        cursor = match.end()
    if cursor < len(value):
        parts.append(ComparisonTextPart(
            text=value[cursor:],
            is_protected_token=False,
        ))
    return tuple(parts)


def restore_comparison_tokens(
    parts: Iterable[ComparisonTextPart],
) -> str:
    """Restore protected and unprotected parts without dropping characters."""

    restored = []
    for part in parts:
        if not isinstance(part, ComparisonTextPart):
            raise ValueError("comparison token part has an invalid contract")
        restored.append(part.text)
    return "".join(restored)


def build_comparison_text(normalized_text: str) -> str:
    """Build deterministic local exact-comparison text from readable text.

    The input contract is a successfully produced R04 ``normalized_text``.
    Processing is NFKC, lowercase, and removal of Unicode whitespace.  All
    remaining letters, numbers, punctuation, symbols, UI text, and short words
    are retained.  The result is for deterministic local comparison only and
    is not an AI/semantic-model input.
    """

    if not isinstance(normalized_text, str):
        raise ValueError("normalized text must be a string")

    compatible = unicodedata.normalize("NFKC", normalized_text)
    lowered = compatible.lower()
    return "".join(
        character for character in lowered if not character.isspace()
    )


def _source_box_key(box: NormalizationBox) -> Tuple[int, str]:
    return box.original_index, box.box_id


def _usable_confidence(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    confidence = float(value)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return None
    return confidence


def _dimension_similarity(left: float, right: float) -> float:
    if left == 0.0 and right == 0.0:
        return 1.0
    maximum = max(left, right)
    return 0.0 if maximum <= 0.0 else min(left, right) / maximum


def _axis_overlap_ratio(
    left_min: float,
    left_max: float,
    right_min: float,
    right_max: float,
) -> float:
    overlap = max(0.0, min(left_max, right_max) - max(left_min, right_min))
    smaller_length = min(left_max - left_min, right_max - right_min)
    if smaller_length > 0.0:
        return overlap / smaller_length
    return 1.0 if left_min == right_min and left_max == right_max else 0.0


def _duplicate_geometry_scores(
    left: BoxGeometry,
    right: BoxGeometry,
    median_height: float,
) -> Dict[str, float]:
    intersection_width = max(
        0.0,
        min(left.x_max, right.x_max) - max(left.x_min, right.x_min),
    )
    intersection_height = max(
        0.0,
        min(left.y_max, right.y_max) - max(left.y_min, right.y_min),
    )
    intersection_area = intersection_width * intersection_height
    left_area = left.width * left.height
    right_area = right.width * right.height
    union_area = left_area + right_area - intersection_area
    if union_area > 0.0:
        iou = intersection_area / union_area
    else:
        iou = 0.0

    center_distance = math.hypot(
        left.center_x - right.center_x,
        left.center_y - right.center_y,
    )
    center_size_reference = min(
        math.sqrt(max(1.0, left.width) * left.effective_height),
        math.sqrt(max(1.0, right.width) * right.effective_height),
    )
    width_similarity = _dimension_similarity(left.width, right.width)
    height_similarity = _dimension_similarity(left.height, right.height)
    return {
        "iou": iou,
        "horizontal_overlap_ratio": _axis_overlap_ratio(
            left.x_min,
            left.x_max,
            right.x_min,
            right.x_max,
        ),
        "vertical_overlap_ratio": _axis_overlap_ratio(
            left.y_min,
            left.y_max,
            right.y_min,
            right.y_max,
        ),
        "center_distance_ratio": center_distance / max(1.0, median_height),
        "center_distance_size_ratio": center_distance
        / max(1.0, center_size_reference),
        "width_similarity": width_similarity,
        "height_similarity": height_similarity,
        "size_similarity": min(width_similarity, height_similarity),
    }


def _duplicate_pair_evidence(
    left: _DuplicatePreparedBox,
    right: _DuplicatePreparedBox,
    median_height: float,
    config: OcrNormalizationConfig,
) -> DuplicatePairEvidence:
    text_exact = left.comparison_key == right.comparison_key
    if not text_exact or not left.comparison_key:
        raise ValueError("duplicate evidence requires one non-empty exact key")
    scores = _duplicate_geometry_scores(
        left.geometry,
        right.geometry,
        median_height,
    )
    has_zero_area = left.geometry.area <= 0.0 or right.geometry.area <= 0.0
    exact_geometry = (
        left.geometry.x_min == right.geometry.x_min
        and left.geometry.y_min == right.geometry.y_min
        and left.geometry.x_max == right.geometry.x_max
        and left.geometry.y_max == right.geometry.y_max
    )
    primary_geometry = (
        scores["iou"] >= config.duplicate_confirm_iou
        and scores["size_similarity"]
        >= config.duplicate_confirm_size_similarity
    )
    secondary_geometry = (
        scores["iou"] >= config.duplicate_secondary_iou
        and scores["center_distance_ratio"]
        <= config.duplicate_confirm_center_ratio
        and scores["size_similarity"]
        >= config.duplicate_secondary_size_similarity
    )
    gray_geometry = (
        scores["iou"] >= config.duplicate_gray_iou
        or (
            scores["center_distance_ratio"]
            <= config.duplicate_gray_center_ratio
            and scores["size_similarity"]
            >= config.duplicate_gray_size_similarity
        )
    )

    if has_zero_area and exact_geometry:
        decision = "confirmed"
        basis = ("text_exact", "exact_zero_area_geometry")
    elif not has_zero_area and primary_geometry:
        decision = "confirmed"
        basis = ("text_exact", "primary_geometry")
    elif not has_zero_area and secondary_geometry:
        decision = "confirmed"
        basis = ("text_exact", "secondary_geometry")
    elif gray_geometry:
        decision = "gray"
        basis = (
            "text_exact",
            "gray_geometry",
            "retain_both",
        )
    else:
        decision = "retained"
        basis = (
            "text_exact_geometry_insufficient",
            "retain_both",
        )

    return DuplicatePairEvidence(
        left_box_id=left.box.box_id,
        right_box_id=right.box.box_id,
        text_similarity=1.0,
        text_exact=True,
        iou=scores["iou"],
        horizontal_overlap_ratio=scores["horizontal_overlap_ratio"],
        vertical_overlap_ratio=scores["vertical_overlap_ratio"],
        center_distance_ratio=scores["center_distance_ratio"],
        center_distance_size_ratio=scores["center_distance_size_ratio"],
        width_similarity=scores["width_similarity"],
        height_similarity=scores["height_similarity"],
        size_similarity=scores["size_similarity"],
        decision=decision,
        basis=basis,
    )


def _duplicate_geometry_key(
    prepared: _DuplicatePreparedBox,
) -> Tuple[Any, ...]:
    geometry = prepared.geometry
    return (
        geometry.x_min,
        geometry.y_min,
        geometry.x_max,
        geometry.y_max,
        prepared.box.box_id,
    )


def _duplicate_survivor_key(
    prepared: _DuplicatePreparedBox,
) -> Tuple[Any, ...]:
    confidence = _usable_confidence(prepared.box.confidence)
    return (
        1 if confidence is None else 0,
        0.0 if confidence is None else -confidence,
        -prepared.geometry.area,
        prepared.box.original_index,
        _duplicate_geometry_key(prepared),
    )


class _SurvivorSpatialSweep:
    """Deterministic interval sweep over direct survivors only."""

    def __init__(self, margin: float) -> None:
        self.margin = margin
        self.by_left: list[Tuple[float, int]] = []
        self.by_right: list[Tuple[float, int]] = []
        self.by_rank: Dict[int, _DuplicatePreparedBox] = {}

    def add(self, rank: int, prepared: _DuplicatePreparedBox) -> None:
        self.by_rank[rank] = prepared
        insort(self.by_left, (prepared.geometry.x_min, rank))
        insort(self.by_right, (prepared.geometry.x_max, rank))

    def nearby(
        self,
        prepared: _DuplicatePreparedBox,
    ) -> Tuple[_DuplicatePreparedBox, ...]:
        geometry = prepared.geometry
        left_limit = geometry.x_min - self.margin
        right_limit = geometry.x_max + self.margin
        left_count = bisect_right(self.by_left, (right_limit, math.inf))
        right_start = bisect_left(self.by_right, (left_limit, -math.inf))
        if left_count <= len(self.by_right) - right_start:
            ranks = (
                rank for _coordinate_value, rank in self.by_left[:left_count]
            )
        else:
            ranks = (
                rank for _coordinate_value, rank in self.by_right[right_start:]
            )
        nearby = []
        for rank in ranks:
            survivor = self.by_rank[rank]
            survivor_geometry = survivor.geometry
            if (
                survivor_geometry.x_max + self.margin < geometry.x_min
                or geometry.x_max + self.margin < survivor_geometry.x_min
                or survivor_geometry.y_max + self.margin < geometry.y_min
                or geometry.y_max + self.margin < survivor_geometry.y_min
            ):
                continue
            nearby.append((rank, survivor))
        nearby.sort(key=lambda item: item[0])
        return tuple(survivor for _rank, survivor in nearby)


def detect_duplicate_boxes(
    boxes: Iterable[Any],
    *,
    config: OcrNormalizationConfig = DEFAULT_OCR_NORMALIZATION_CONFIG,
) -> DuplicateDetectionResult:
    """Detect same-screen OCR duplicate boxes without mutating evidence.

    Non-empty exact comparison keys create independent buckets.  Within each
    bucket, a spatial interval sweep compares each new box only with current
    survivors; suppression still requires direct geometry confirmation.
    """

    projected = [_project_box(value) for value in boxes]
    if len({box.box_id for box in projected}) != len(projected):
        raise ValueError("duplicate detection box_id values must be unique")
    projected.sort(key=_source_box_key)

    prepared = []
    eligible_boxes = []
    for box in projected:
        normalized_text = normalize_box_text(box.raw_text)
        if not normalized_text:
            continue
        eligible_boxes.append(box)
        try:
            comparison_key = build_comparison_text(normalized_text)
        except Exception as exc:
            raise OcrDuplicateTextKeyError(
                "duplicate text key build failed"
            ) from exc
        if not comparison_key:
            continue
        try:
            geometry = adapt_bbox_geometry(box.bbox)
        except OcrGeometryError:
            continue
        prepared.append(_DuplicatePreparedBox(
            box=box,
            comparison_key=comparison_key,
            geometry=geometry,
        ))

    median_height = float(median([
        item.geometry.effective_height for item in prepared
    ])) if prepared else 1.0
    margin = median_height * config.duplicate_candidate_margin_height_ratio
    buckets: Dict[str, list[_DuplicatePreparedBox]] = {}
    for item in prepared:
        buckets.setdefault(item.comparison_key, []).append(item)

    confirmed_evidence = []
    suppressed_by_survivor: Dict[str, list[_DuplicatePreparedBox]] = {}
    evidence_by_survivor: Dict[str, list[DuplicatePairEvidence]] = {}
    candidate_pair_count = 0
    confirmation_count = 0
    duplicate_gray_pair_count = 0
    survivor_priority: Dict[str, Tuple[Any, ...]] = {}
    for comparison_key in sorted(buckets):
        left_sorted = sorted(
            buckets[comparison_key],
            key=lambda item: (
                item.geometry.x_min,
                item.geometry.y_min,
                item.geometry.x_max,
                item.geometry.y_max,
                _source_box_key(item.box),
            ),
        )
        priority_order = sorted(left_sorted, key=_duplicate_survivor_key)
        spatial_sweep = _SurvivorSpatialSweep(margin)
        for rank, current in enumerate(priority_order):
            current_priority = _duplicate_survivor_key(current)
            survivor_priority[current.box.box_id] = current_priority
            nearby_survivors = spatial_sweep.nearby(current)
            candidate_pair_count += len(nearby_survivors)
            confirmed_survivor = None
            confirmed_pair_evidence = None
            for survivor in nearby_survivors:
                confirmation_count += 1
                evidence = _duplicate_pair_evidence(
                    survivor,
                    current,
                    median_height,
                    config,
                )
                if evidence.decision == "confirmed":
                    confirmed_survivor = survivor
                    confirmed_pair_evidence = evidence
                    break
                if evidence.decision == "gray":
                    duplicate_gray_pair_count += 1
            if confirmed_survivor is None:
                spatial_sweep.add(rank, current)
                continue
            survivor_id = confirmed_survivor.box.box_id
            suppressed_by_survivor.setdefault(survivor_id, []).append(current)
            evidence_by_survivor.setdefault(survivor_id, []).append(
                confirmed_pair_evidence
            )
            confirmed_evidence.append(confirmed_pair_evidence)

    ordered_ids = tuple(box.box_id for box in eligible_boxes)
    groups = []
    for survivor_id in sorted(
        suppressed_by_survivor,
        key=lambda box_id: survivor_priority[box_id],
    ):
        suppressed = suppressed_by_survivor[survivor_id]
        suppressed_ids = tuple(
            item.box.box_id
            for item in sorted(suppressed, key=lambda item: _source_box_key(item.box))
        )
        groups.append(DuplicateGroup(
            retained_box_id=survivor_id,
            suppressed_duplicate_box_ids=suppressed_ids,
            source_box_ids=(survivor_id, *suppressed_ids),
            pair_evidence=tuple(evidence_by_survivor[survivor_id]),
        ))

    suppressed_id_set = {
        box_id
        for group in groups
        for box_id in group.suppressed_duplicate_box_ids
    }
    retained_box_ids = tuple(
        box_id for box_id in ordered_ids if box_id not in suppressed_id_set
    )
    suppressed_duplicate_box_ids = tuple(
        box_id
        for box_id in ordered_ids
        if box_id in suppressed_id_set
    )
    return DuplicateDetectionResult(
        deduplicated_box_count=len(retained_box_ids),
        retained_box_ids=retained_box_ids,
        duplicate_groups=tuple(groups),
        suppressed_duplicate_box_ids=suppressed_duplicate_box_ids,
        pair_evidence=tuple(confirmed_evidence),
        duplicate_risk=duplicate_gray_pair_count > 0,
        candidate_pair_count=candidate_pair_count,
        confirmation_count=confirmation_count,
        duplicate_gray_pair_count=duplicate_gray_pair_count,
    )


def _is_cjk_character(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )


def _ascii_alphanumeric(character: str) -> bool:
    return character.isascii() and character.isalnum()


def _inline_gap_ratio(
    left_geometry: Optional[BoxGeometry],
    right_geometry: Optional[BoxGeometry],
    median_height: Optional[float],
) -> Optional[float]:
    if (
        left_geometry is None
        or right_geometry is None
        or median_height is None
        or median_height <= 0.0
    ):
        return None
    gap = right_geometry.x_min - left_geometry.x_max
    if gap <= 0:
        return 0.0
    return gap / median_height


def choose_inline_separator(
    left_text: str,
    right_text: str,
    *,
    left_geometry: Optional[BoxGeometry],
    right_geometry: Optional[BoxGeometry],
    median_height: Optional[float],
    config: OcrNormalizationConfig,
) -> str:
    """Choose either no separator or one space for adjacent line fragments."""

    if not left_text or not right_text:
        return ""
    left_character = left_text[-1]
    right_character = right_text[0]
    gap_ratio = _inline_gap_ratio(
        left_geometry,
        right_geometry,
        median_height,
    )

    if gap_ratio == 0.0:
        return ""
    if left_character in _OPENING_PUNCTUATION:
        return ""
    if right_character in _CLOSING_PUNCTUATION:
        return ""
    if (
        left_character in _CLOSING_PUNCTUATION
        and len(left_text) > 1
        and _is_cjk_character(left_text[-2])
    ):
        return ""
    if _is_cjk_character(left_character) and _is_cjk_character(
        right_character
    ):
        return ""
    if (
        gap_ratio is not None
        and (
            left_character in _CONNECTOR_CHARACTERS
            or right_character in _CONNECTOR_CHARACTERS
        )
        and gap_ratio <= config.symbol_join_gap_height_ratio
    ):
        return ""
    if (
        gap_ratio is not None
        and _ascii_alphanumeric(left_character)
        and _ascii_alphanumeric(right_character)
        and gap_ratio <= config.compact_join_gap_height_ratio
    ):
        return ""
    return " "


def _failed_text_result(
    *,
    raw_text: Optional[str],
    raw_text_source: Optional[str],
    error_type: str,
    config: OcrNormalizationConfig,
    eligible_box_count: int = 0,
    low_confidence_box_count: int = 0,
    warnings: Tuple[NormalizationWarning, ...] = (),
    excluded_empty_box_ids: Tuple[str, ...] = (),
) -> TextNormalizationResult:
    return TextNormalizationResult(
        status=NORMALIZATION_FAILED,
        normalization_version=NORMALIZATION_VERSION,
        normalization_config_version=config.normalization_config_version,
        normalization_config_digest=normalization_config_digest(config),
        effective_min_confidence=config.effective_min_confidence,
        raw_text=raw_text,
        raw_text_source=raw_text_source,
        raw_text_length=None if raw_text is None else len(raw_text),
        normalized_text=None,
        normalized_text_length=None,
        comparison_text=None,
        comparison_text_length=None,
        effective_box_ids=(),
        ordered_box_ids=(),
        line_groups=(),
        line_mapping=(),
        normalized_lines=(),
        excluded_empty_box_ids=excluded_empty_box_ids,
        deduplicated_box_count=0,
        duplicate_groups=(),
        suppressed_duplicate_box_ids=(),
        duplicate_pair_evidence=(),
        duplicate_risk=False,
        duplicate_candidate_pair_count=0,
        duplicate_confirmation_count=0,
        duplicate_gray_pair_count=0,
        eligible_box_count=eligible_box_count,
        low_confidence_box_count=low_confidence_box_count,
        empty_normalized_box_count=len(excluded_empty_box_ids),
        normalization_warnings=warnings,
        normalization_error_type=error_type,
    )


def failed_normalization_result(
    boxes: Iterable[Any],
    *,
    engine_raw_text: Optional[str] = None,
    error_type: str,
    config: OcrNormalizationConfig = DEFAULT_OCR_NORMALIZATION_CONFIG,
) -> TextNormalizationResult:
    """Return a sanitized failed result while preserving available raw text."""

    try:
        source_boxes = tuple(boxes)
        raw_text, raw_text_source = derive_raw_text(
            source_boxes,
            engine_raw_text=engine_raw_text,
        )
    except Exception:
        source_boxes = ()
        raw_text = None
        raw_text_source = None
    try:
        eligible_box_count = len(eligible_box_ids_for_config(source_boxes, config))
        low_confidence_box_count = len(source_boxes) - eligible_box_count
    except Exception:
        eligible_box_count = 0
        low_confidence_box_count = 0
    return _failed_text_result(
        raw_text=raw_text,
        raw_text_source=raw_text_source,
        error_type=error_type,
        config=config,
        eligible_box_count=eligible_box_count,
        low_confidence_box_count=low_confidence_box_count,
    )


def normalize_ocr_text(
    boxes: Iterable[Any],
    *,
    engine_raw_text: Optional[str] = None,
    eligible_box_ids: Optional[Iterable[str]] = None,
    config: OcrNormalizationConfig = DEFAULT_OCR_NORMALIZATION_CONFIG,
) -> TextNormalizationResult:
    """Build Change 3—5 text fields without local failures escaping.

    The returned status is ``completed`` for a fully deterministic result and
    ``failed`` whenever the complete screen result cannot be trusted.
    Only sanitized codes and box IDs are returned in warnings; OCR text and
    coordinates never appear in them.
    """

    try:
        source_boxes = tuple(boxes)
    except Exception:
        return _failed_text_result(
            raw_text=None,
            raw_text_source=None,
            error_type=RAW_TEXT_BUILD_FAILED,
            config=config,
        )

    raw_text: Optional[str] = None
    raw_text_source: Optional[str] = None
    try:
        raw_text, raw_text_source = derive_raw_text(
            source_boxes,
            engine_raw_text=engine_raw_text,
        )
    except Exception:
        return _failed_text_result(
            raw_text=None,
            raw_text_source=None,
            error_type=RAW_TEXT_BUILD_FAILED,
            config=config,
        )

    try:
        projected = [_project_box(value) for value in source_boxes]
        if len({box.box_id for box in projected}) != len(projected):
            raise ValueError("normalization box_id values must be unique")
        projected.sort(key=lambda box: (box.original_index, box.box_id))
    except Exception:
        return _failed_text_result(
            raw_text=raw_text,
            raw_text_source=raw_text_source,
            error_type=READING_ORDER_BUILD_FAILED,
            config=config,
        )

    if eligible_box_ids is None:
        try:
            eligible_id_set = set(eligible_box_ids_for_config(projected, config))
        except Exception:
            return _failed_text_result(
                raw_text=raw_text,
                raw_text_source=raw_text_source,
                error_type=READING_ORDER_BUILD_FAILED,
                config=config,
            )
    else:
        try:
            eligible_id_set = set(eligible_box_ids)
        except Exception:
            return _failed_text_result(
                raw_text=raw_text,
                raw_text_source=raw_text_source,
                error_type=READING_ORDER_BUILD_FAILED,
                config=config,
            )
        if (
            any(not isinstance(box_id, str) for box_id in eligible_id_set)
            or not eligible_id_set.issubset({box.box_id for box in projected})
        ):
            return _failed_text_result(
                raw_text=raw_text,
                raw_text_source=raw_text_source,
                error_type=READING_ORDER_BUILD_FAILED,
                config=config,
            )

    eligible_projected = [
        box for box in projected if box.box_id in eligible_id_set
    ]
    eligible_box_count = len(eligible_projected)
    low_confidence_box_count = len(projected) - eligible_box_count
    normalized_by_box_id: Dict[str, str] = {}
    excluded_empty_box_ids = []
    text_warnings = []
    failed_box_ids = set()
    for box in eligible_projected:
        try:
            normalized_box_text = normalize_box_text(box.raw_text)
        except Exception:
            failed_box_ids.add(box.box_id)
            text_warnings.append(NormalizationWarning(
                box_id=box.box_id,
                code=BOX_TEXT_NORMALIZATION_FAILED,
            ))
            continue
        if normalized_box_text:
            normalized_by_box_id[box.box_id] = normalized_box_text
        else:
            excluded_empty_box_ids.append(box.box_id)

    if failed_box_ids:
        return _failed_text_result(
            raw_text=raw_text,
            raw_text_source=raw_text_source,
            error_type=(
                ALL_BOX_TEXT_NORMALIZATION_FAILED
                if not normalized_by_box_id
                else BOX_TEXT_NORMALIZATION_FAILED
            ),
            warnings=tuple(text_warnings),
            excluded_empty_box_ids=tuple(excluded_empty_box_ids),
            config=config,
            eligible_box_count=eligible_box_count,
            low_confidence_box_count=low_confidence_box_count,
        )

    ordering_boxes = tuple(
        NormalizationBox(
            box_id=box.box_id,
            raw_text=normalized_by_box_id.get(box.box_id, ""),
            bbox=box.bbox,
            original_index=box.original_index,
            confidence=box.confidence,
        )
        for box in eligible_projected
    )
    if normalized_by_box_id:
        try:
            duplicate_result = detect_duplicate_boxes(
                ordering_boxes,
                config=config,
            )
        except Exception as exc:
            return _failed_text_result(
                raw_text=raw_text,
                raw_text_source=raw_text_source,
                error_type=(
                    COMPARISON_TEXT_BUILD_FAILED
                    if isinstance(exc, OcrDuplicateTextKeyError)
                    else DUPLICATE_DETECTION_FAILED
                ),
                warnings=tuple(text_warnings),
                excluded_empty_box_ids=tuple(excluded_empty_box_ids),
                config=config,
                eligible_box_count=eligible_box_count,
                low_confidence_box_count=low_confidence_box_count,
            )
    else:
        duplicate_result = DuplicateDetectionResult(
            deduplicated_box_count=0,
            retained_box_ids=(),
            duplicate_groups=(),
            suppressed_duplicate_box_ids=(),
            pair_evidence=(),
            duplicate_risk=False,
            candidate_pair_count=0,
            confirmation_count=0,
            duplicate_gray_pair_count=0,
        )

    suppressed_duplicate_box_ids = set(
        duplicate_result.suppressed_duplicate_box_ids
    )
    reading_boxes = tuple(
        NormalizationBox(
            box_id=box.box_id,
            raw_text=(
                ""
                if box.box_id in suppressed_duplicate_box_ids
                else box.raw_text
            ),
            bbox=box.bbox,
            original_index=box.original_index,
            confidence=box.confidence,
        )
        for box in ordering_boxes
    )
    try:
        reading_order = build_reading_order(reading_boxes, config=config)
        if reading_order.normalization_warnings:
            return _failed_text_result(
                raw_text=raw_text,
                raw_text_source=raw_text_source,
                error_type=LAYOUT_DEGRADED,
                warnings=reading_order.normalization_warnings,
                excluded_empty_box_ids=tuple(excluded_empty_box_ids),
                config=config,
                eligible_box_count=eligible_box_count,
                low_confidence_box_count=low_confidence_box_count,
            )
        geometry_by_box_id = {
            entry.box_id: entry.geometry
            for entry in reading_order.box_geometries
        }
        normalized_lines = []
        for line in reading_order.line_groups:
            line_text = ""
            previous_box_id: Optional[str] = None
            for box_id in line.box_ids:
                fragment = normalized_by_box_id[box_id]
                if previous_box_id is not None:
                    line_text += choose_inline_separator(
                        line_text,
                        fragment,
                        left_geometry=geometry_by_box_id[previous_box_id],
                        right_geometry=geometry_by_box_id[box_id],
                        median_height=reading_order.median_box_height,
                        config=config,
                    )
                line_text += fragment
                previous_box_id = box_id
            normalized_lines.append(NormalizedLine(
                line_index=line.line_index,
                box_ids=line.box_ids,
                normalized_text=line_text,
            ))
        normalized_text = "\n".join(
            line.normalized_text for line in normalized_lines
        )
    except Exception:
        warnings = tuple(text_warnings)
        return _failed_text_result(
            raw_text=raw_text,
            raw_text_source=raw_text_source,
            error_type=READING_ORDER_BUILD_FAILED,
            warnings=warnings,
            excluded_empty_box_ids=tuple(excluded_empty_box_ids),
            config=config,
            eligible_box_count=eligible_box_count,
            low_confidence_box_count=low_confidence_box_count,
        )

    try:
        comparison_text = build_comparison_text(normalized_text)
    except Exception:
        return _failed_text_result(
            raw_text=raw_text,
            raw_text_source=raw_text_source,
            error_type=COMPARISON_TEXT_BUILD_FAILED,
            warnings=tuple((
                *text_warnings,
                *reading_order.normalization_warnings,
            )),
            excluded_empty_box_ids=tuple(excluded_empty_box_ids),
            config=config,
            eligible_box_count=eligible_box_count,
            low_confidence_box_count=low_confidence_box_count,
        )

    source_key_by_box_id = {
        box.box_id: (box.original_index, box.box_id)
        for box in eligible_projected
    }
    warnings = tuple(
        sorted(
            (
                *text_warnings,
                *reading_order.normalization_warnings,
            ),
            key=lambda warning: (
                source_key_by_box_id.get(
                    warning.box_id,
                    (math.inf, warning.box_id),
                ),
                warning.code,
            ),
        )
    )
    effective_box_ids = reading_order.ordered_box_ids

    return TextNormalizationResult(
        status=NORMALIZATION_COMPLETED,
        normalization_version=NORMALIZATION_VERSION,
        normalization_config_version=config.normalization_config_version,
        normalization_config_digest=normalization_config_digest(config),
        effective_min_confidence=config.effective_min_confidence,
        raw_text=raw_text,
        raw_text_source=raw_text_source,
        raw_text_length=len(raw_text),
        normalized_text=normalized_text,
        normalized_text_length=len(normalized_text),
        comparison_text=comparison_text,
        comparison_text_length=len(comparison_text),
        effective_box_ids=effective_box_ids,
        ordered_box_ids=reading_order.ordered_box_ids,
        line_groups=reading_order.line_groups,
        line_mapping=reading_order.line_mapping,
        normalized_lines=tuple(normalized_lines),
        excluded_empty_box_ids=tuple(excluded_empty_box_ids),
        deduplicated_box_count=duplicate_result.deduplicated_box_count,
        duplicate_groups=duplicate_result.duplicate_groups,
        suppressed_duplicate_box_ids=(
            duplicate_result.suppressed_duplicate_box_ids
        ),
        duplicate_pair_evidence=duplicate_result.pair_evidence,
        duplicate_risk=duplicate_result.duplicate_risk,
        duplicate_candidate_pair_count=(
            duplicate_result.candidate_pair_count
        ),
        duplicate_confirmation_count=duplicate_result.confirmation_count,
        duplicate_gray_pair_count=(
            duplicate_result.duplicate_gray_pair_count
        ),
        eligible_box_count=eligible_box_count,
        low_confidence_box_count=low_confidence_box_count,
        empty_normalized_box_count=len(excluded_empty_box_ids),
        normalization_warnings=warnings,
        normalization_error_type=None,
    )
