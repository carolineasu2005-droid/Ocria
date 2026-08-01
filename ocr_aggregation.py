"""Platform-neutral R05 aggregation contracts and R04 segment adaptation.

This module deliberately contains no overlap classification, persistence, replay,
or page integration.  Those responsibilities begin in later approved changes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import hashlib
import json
import math
import re
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from ocr_normalization import (
    NORMALIZATION_COMPLETED,
    build_comparison_text,
)
from ocr_records import (
    AggregationDuplicateRisk,
    AggregationMatchType,
    AggregationOccurrenceRole,
    AggregationStatus,
    CaptureStatus,
    CaptureType,
    DocumentBuildStatus,
    OcrDocumentSegment,
    OcrSegmentMatchEvidence,
    OcrScreenRecord,
    OcrSourceOccurrence,
    OcrTextSegment,
    NormalizationStatus,
)


AGGREGATION_VERSION = "r05-v1"
AGGREGATION_CONFIG_VERSION = "r05-config-v1"
R05_DOCUMENT_VERSION = "r05-document-v1"

_DOCUMENT_SEGMENT_ID_PATTERN = re.compile(r"document:segment:(0|[1-9][0-9]*)\Z")
_MATCH_ID_PATTERN = re.compile(r"match:([1-9][0-9]*):(0|[1-9][0-9]*)\Z")


class AggregationInvariantError(ValueError):
    """A sanitized violation of a pure R05 data invariant."""


class R04SegmentAdapterError(AggregationInvariantError):
    """An R04 record cannot be safely reused as an R05 screen segment input."""


@dataclass(frozen=True)
class OcrAggregationConfig:
    """All frozen R05 thresholds, including later-stage thresholds by design."""

    aggregation_config_version: str = AGGREGATION_CONFIG_VERSION
    max_formal_screen_count: int = 8
    max_screen_segments: int = 256
    exact_min_segment_count: int = 2
    exact_min_char_count: int = 24
    exact_min_nonshort_segment_count: int = 1
    exact_single_segment_min_char_count: int = 48
    short_segment_char_threshold: int = 8
    fuzzy_similarity_threshold: float = 0.94
    fuzzy_uncertain_similarity_floor: float = 0.88
    fuzzy_tie_epsilon: float = 0.005
    fuzzy_min_char_count: int = 32
    fuzzy_max_tail_segments: int = 4
    fuzzy_max_head_segments: int = 4
    fuzzy_max_combined_segments: int = 3
    fuzzy_max_unmatched_chars_per_side: int = 2
    fuzzy_max_group_char_count: int = 512
    fuzzy_candidate_limit: int = 128
    historical_min_segment_count: int = 2
    historical_max_segment_count: int = 4
    historical_min_char_count: int = 48
    historical_context_anchor_count: int = 2

    def __post_init__(self) -> None:
        validate_aggregation_config(self)


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def validate_aggregation_config(config: OcrAggregationConfig) -> None:
    """Validate the complete frozen config without platform or environment input."""

    if not isinstance(config, OcrAggregationConfig):
        raise TypeError("aggregation config has an invalid contract")
    if config.aggregation_config_version != AGGREGATION_CONFIG_VERSION:
        raise ValueError("unsupported aggregation config version")
    int_names = (
        "max_formal_screen_count",
        "max_screen_segments",
        "exact_min_segment_count",
        "exact_min_char_count",
        "exact_min_nonshort_segment_count",
        "exact_single_segment_min_char_count",
        "short_segment_char_threshold",
        "fuzzy_min_char_count",
        "fuzzy_max_tail_segments",
        "fuzzy_max_head_segments",
        "fuzzy_max_combined_segments",
        "fuzzy_max_unmatched_chars_per_side",
        "fuzzy_max_group_char_count",
        "fuzzy_candidate_limit",
        "historical_min_segment_count",
        "historical_max_segment_count",
        "historical_min_char_count",
        "historical_context_anchor_count",
    )
    if any(not _is_plain_int(getattr(config, name)) for name in int_names):
        raise ValueError("aggregation integer config values must be integers")
    if any(getattr(config, name) < 0 for name in int_names):
        raise ValueError("aggregation integer config values must be non-negative")
    if (
        config.max_formal_screen_count < 1
        or config.max_screen_segments < 1
        or config.exact_min_segment_count < 1
        or config.exact_min_nonshort_segment_count < 1
        or config.exact_single_segment_min_char_count < 1
        or config.fuzzy_min_char_count < 1
        or config.fuzzy_max_tail_segments < 1
        or config.fuzzy_max_head_segments < 1
        or config.fuzzy_max_combined_segments < 1
        or config.fuzzy_max_group_char_count < 1
        or config.fuzzy_candidate_limit < 1
        or config.historical_min_segment_count < 1
        or config.historical_max_segment_count < config.historical_min_segment_count
        or config.historical_context_anchor_count < 1
    ):
        raise ValueError("aggregation integer config values are out of range")
    if config.exact_min_segment_count > config.max_screen_segments:
        raise ValueError("exact segment minimum exceeds screen limit")
    if config.fuzzy_max_combined_segments != 3:
        raise ValueError("unsupported fuzzy combined segment limit")
    if config.historical_max_segment_count > config.max_screen_segments:
        raise ValueError("historical segment maximum exceeds screen limit")

    float_names = (
        "fuzzy_similarity_threshold",
        "fuzzy_uncertain_similarity_floor",
        "fuzzy_tie_epsilon",
    )
    if any(not _is_finite_number(getattr(config, name)) for name in float_names):
        raise ValueError("aggregation float config values must be finite numbers")
    if not (
        0.0 <= config.fuzzy_uncertain_similarity_floor <= 1.0
        and 0.0 <= config.fuzzy_similarity_threshold <= 1.0
        and config.fuzzy_uncertain_similarity_floor
        <= config.fuzzy_similarity_threshold
        and 0.0 <= config.fuzzy_tie_epsilon <= 1.0
    ):
        raise ValueError("aggregation float config values are out of range")


DEFAULT_OCR_AGGREGATION_CONFIG = OcrAggregationConfig()


def aggregation_config_snapshot(
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
) -> dict[str, Any]:
    """Return the complete versioned snapshot used for deterministic identity."""

    if not isinstance(config, OcrAggregationConfig):
        raise TypeError("aggregation config has an invalid contract")
    validate_aggregation_config(config)
    return {"aggregation_version": AGGREGATION_VERSION, **asdict(config)}


def _canonical_aggregation_config_json(config_or_snapshot: Any) -> str:
    snapshot = (
        aggregation_config_snapshot(config_or_snapshot)
        if isinstance(config_or_snapshot, OcrAggregationConfig)
        else dict(config_or_snapshot)
    )
    if "aggregation_config_digest" in snapshot:
        raise ValueError("aggregation config snapshot cannot contain its digest")
    try:
        return json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("aggregation config snapshot is not canonicalizable") from exc


def aggregation_config_digest(config_or_snapshot: Any) -> str:
    """Return the lowercase SHA-256 of canonical UTF-8 config JSON."""

    canonical = _canonical_aggregation_config_json(config_or_snapshot)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def restore_aggregation_config(snapshot: Mapping[str, Any]) -> OcrAggregationConfig:
    """Restore only a complete, exact historical aggregation snapshot."""

    if not isinstance(snapshot, Mapping):
        raise ValueError("aggregation config snapshot must be an object")
    expected_keys = {"aggregation_version", *asdict(DEFAULT_OCR_AGGREGATION_CONFIG)}
    if set(snapshot) != expected_keys:
        raise ValueError("aggregation config snapshot fields are incomplete")
    if snapshot.get("aggregation_version") != AGGREGATION_VERSION:
        raise ValueError("unsupported aggregation version")
    values = {
        key: value
        for key, value in snapshot.items()
        if key != "aggregation_version"
    }
    try:
        return OcrAggregationConfig(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("aggregation config snapshot is invalid") from exc


def aggregation_char_count(comparison_text: str) -> int:
    """Count R04 comparison Unicode code points without re-normalizing them."""

    if not isinstance(comparison_text, str):
        raise AggregationInvariantError("comparison_text_invalid")
    if any(character.isspace() for character in comparison_text):
        raise AggregationInvariantError("comparison_text_contains_whitespace")
    return len(comparison_text)


def document_segment_id(order: int) -> str:
    if not _is_plain_int(order) or order < 0:
        raise AggregationInvariantError("document_segment_order_invalid")
    return "document:segment:{0}".format(order)


def match_id(screen_index: int, order: int) -> str:
    if not _is_plain_int(screen_index) or screen_index < 1:
        raise AggregationInvariantError("match_screen_index_invalid")
    if not _is_plain_int(order) or order < 0:
        raise AggregationInvariantError("match_order_invalid")
    return "match:{0}:{1}".format(screen_index, order)


@dataclass(frozen=True)
class ExactOccurrenceMapping:
    """One immutable current-screen occurrence to append to a document segment."""

    document_segment_id: str
    occurrence: OcrSourceOccurrence


@dataclass(frozen=True)
class ExactBoundaryMatch:
    """Pure result of the one permitted R05 exact boundary comparison."""

    matched_current_segment_ids: Tuple[str, ...]
    matched_document_segment_ids: Tuple[str, ...]
    remaining_current_segment_ids: Tuple[str, ...]
    uncertain_current_segment_ids: Tuple[str, ...]
    exact_basis: Optional[str]
    match_evidence: Tuple[OcrSegmentMatchEvidence, ...]
    occurrence_mappings: Tuple[ExactOccurrenceMapping, ...]

    @property
    def accepted(self) -> bool:
        return bool(self.matched_current_segment_ids)


FUZZY_LINE_SEPARATOR = "\n"
_ALLOWED_FUZZY_SHAPES = ((1, 1), (1, 2), (2, 1))


@dataclass(frozen=True)
class FuzzyGroupScore:
    shape: Tuple[int, int]
    left_text: str
    right_text: str
    left_content_chars: int
    right_content_chars: int
    score: float
    left_unmatched_chars: int
    right_unmatched_chars: int
    exact_equal_protected: bool
    is_accepted: bool
    is_gray: bool


@dataclass(frozen=True)
class FuzzyBoundaryCandidate:
    """One bounded, continuous tail/head fuzzy path of permitted groups."""

    shapes: Tuple[Tuple[int, int], ...]
    document_segment_ids: Tuple[str, ...]
    current_segment_ids: Tuple[str, ...]
    groups: Tuple[FuzzyGroupScore, ...]
    document_content_chars: int
    current_content_chars: int
    weighted_score: float

    @property
    def group_count(self) -> int:
        return len(self.groups)

    @property
    def is_accepted(self) -> bool:
        return bool(self.groups) and all(group.is_accepted for group in self.groups)

    @property
    def is_gray(self) -> bool:
        return bool(self.groups) and any(group.is_gray for group in self.groups)


@dataclass(frozen=True)
class FuzzyOccurrenceMapping:
    document_segment_id: str
    occurrence: OcrSourceOccurrence


@dataclass(frozen=True)
class FuzzyBoundaryMatch:
    matched_current_segment_ids: Tuple[str, ...]
    matched_document_segment_ids: Tuple[str, ...]
    remaining_current_segment_ids: Tuple[str, ...]
    uncertain_current_segment_ids: Tuple[str, ...]
    match_evidence: Tuple[OcrSegmentMatchEvidence, ...]
    occurrence_mappings: Tuple[FuzzyOccurrenceMapping, ...]
    candidate_limit_exceeded: bool = False
    ambiguous_tie: bool = False

    @property
    def accepted(self) -> bool:
        return bool(self.matched_current_segment_ids)


def fuzzy_content_char_count(value: str) -> int:
    """Count fuzzy OCR content, deliberately excluding only R05-inserted LF."""

    if not isinstance(value, str):
        raise AggregationInvariantError("fuzzy_text_invalid")
    return sum(character != FUZZY_LINE_SEPARATOR for character in value)


def fuzzy_unmatched_content_count(
    value: str,
    unmatched_ranges: Sequence[Tuple[int, int]],
) -> int:
    """Count unmatched OCR content while excluding matcher-visible artificial LF."""

    if not isinstance(value, str):
        raise AggregationInvariantError("fuzzy_text_invalid")
    total = 0
    previous_end = 0
    for start, end in unmatched_ranges:
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < previous_end
            or end < start
            or end > len(value)
        ):
            raise AggregationInvariantError("fuzzy_unmatched_range_invalid")
        total += fuzzy_content_char_count(value[start:end])
        previous_end = end
    return total


def _unmatched_ranges(matcher: SequenceMatcher) -> Tuple[Tuple[Tuple[int, int], ...], Tuple[Tuple[int, int], ...]]:
    left_ranges = []
    right_ranges = []
    for opcode, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if opcode in ("delete", "replace") and left_start != left_end:
            left_ranges.append((left_start, left_end))
        if opcode in ("insert", "replace") and right_start != right_end:
            right_ranges.append((right_start, right_end))
    return tuple(left_ranges), tuple(right_ranges)


def enumerate_fuzzy_tilings(
    document_count: int,
    current_count: int,
) -> Tuple[Tuple[Tuple[int, int], ...], ...]:
    """Enumerate only monotonic tilings made from the three approved shapes."""

    if (
        not _is_plain_int(document_count)
        or not _is_plain_int(current_count)
        or document_count < 1
        or current_count < 1
    ):
        raise AggregationInvariantError("fuzzy_tiling_size_invalid")
    tilings = []

    def visit(
        document_position: int,
        current_position: int,
        path: Tuple[Tuple[int, int], ...],
    ) -> None:
        if document_position == document_count and current_position == current_count:
            tilings.append(path)
            return
        for shape in _ALLOWED_FUZZY_SHAPES:
            left_count, right_count = shape
            if (
                document_position + left_count <= document_count
                and current_position + right_count <= current_count
            ):
                visit(
                    document_position + left_count,
                    current_position + right_count,
                    path + (shape,),
                )

    visit(0, 0, ())
    return tuple(tilings)


def _join_fuzzy_group(segments: Sequence[Any]) -> str:
    values = tuple(segments)
    if not values or any(
        not isinstance(item.comparison_text, str)
        or not item.comparison_text
        or FUZZY_LINE_SEPARATOR in item.comparison_text
        for item in values
    ):
        raise AggregationInvariantError("fuzzy_segment_invalid")
    return FUZZY_LINE_SEPARATOR.join(item.comparison_text for item in values)


def score_fuzzy_group(
    left_segments: Sequence[Any],
    right_segments: Sequence[Any],
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
) -> FuzzyGroupScore:
    """Score one and only one allowed fuzzy group without changing its text."""

    if not isinstance(config, OcrAggregationConfig):
        raise TypeError("aggregation config has an invalid contract")
    validate_aggregation_config(config)
    left = tuple(left_segments)
    right = tuple(right_segments)
    shape = (len(left), len(right))
    if shape not in _ALLOWED_FUZZY_SHAPES:
        raise AggregationInvariantError("fuzzy_shape_invalid")
    left_text = _join_fuzzy_group(left)
    right_text = _join_fuzzy_group(right)
    left_content_chars = fuzzy_content_char_count(left_text)
    right_content_chars = fuzzy_content_char_count(right_text)
    exact_equal_protected = shape == (1, 1) and left_text == right_text
    meets_content = (
        min(left_content_chars, right_content_chars) >= config.fuzzy_min_char_count
        and max(left_content_chars, right_content_chars)
        <= config.fuzzy_max_group_char_count
    )
    if max(left_content_chars, right_content_chars) > config.fuzzy_max_group_char_count:
        return FuzzyGroupScore(
            shape=shape,
            left_text=left_text,
            right_text=right_text,
            left_content_chars=left_content_chars,
            right_content_chars=right_content_chars,
            score=0.0,
            left_unmatched_chars=0,
            right_unmatched_chars=0,
            exact_equal_protected=exact_equal_protected,
            is_accepted=False,
            is_gray=True,
        )
    matcher = SequenceMatcher(None, left_text, right_text, autojunk=False)
    left_ranges, right_ranges = _unmatched_ranges(matcher)
    left_unmatched = fuzzy_unmatched_content_count(left_text, left_ranges)
    right_unmatched = fuzzy_unmatched_content_count(right_text, right_ranges)
    score = matcher.ratio()
    meets_unmatched = (
        left_unmatched <= config.fuzzy_max_unmatched_chars_per_side
        and right_unmatched <= config.fuzzy_max_unmatched_chars_per_side
    )
    is_accepted = (
        not exact_equal_protected
        and meets_content
        and meets_unmatched
        and score >= config.fuzzy_similarity_threshold
    )
    is_gray = (
        exact_equal_protected
        or (
            score >= config.fuzzy_uncertain_similarity_floor
            and (not is_accepted or not meets_content or not meets_unmatched)
        )
    )
    return FuzzyGroupScore(
        shape=shape,
        left_text=left_text,
        right_text=right_text,
        left_content_chars=left_content_chars,
        right_content_chars=right_content_chars,
        score=score,
        left_unmatched_chars=left_unmatched,
        right_unmatched_chars=right_unmatched,
        exact_equal_protected=exact_equal_protected,
        is_accepted=is_accepted,
        is_gray=is_gray,
    )


def _fuzzy_group_projection(
    segments: Sequence[Any],
    cache: Dict[Tuple[str, ...], Tuple[str, int, Counter[str]]],
) -> Tuple[str, int, Counter[str]]:
    """Project one already-validated group once per fuzzy search."""

    values = tuple(segments)
    key = tuple(item.comparison_text for item in values)
    projected = cache.get(key)
    if projected is None:
        text = _join_fuzzy_group(values)
        content_chars = sum(len(value) for value in key)
        projected = (text, content_chars, Counter(text))
        cache[key] = projected
    return projected


def _score_fuzzy_group_for_search(
    left_segments: Sequence[Any],
    right_segments: Sequence[Any],
    config: OcrAggregationConfig,
    projection_cache: Dict[Tuple[str, ...], Tuple[str, int, Counter[str]]],
    matcher_cache: Dict[str, SequenceMatcher],
) -> FuzzyGroupScore:
    """Score a group inside one validated search with exact-safe fast rejection.

    The multiset ratio is the same upper bound used by
    ``SequenceMatcher.quick_ratio``.  If it is below the frozen gray floor,
    the exact ratio cannot be accepted or gray, so matching blocks and
    unmatched ranges cannot affect any persisted R05 result.  All groups that
    can affect classification still use the exact ``SequenceMatcher`` result.
    """

    left = tuple(left_segments)
    right = tuple(right_segments)
    shape = (len(left), len(right))
    left_text, left_content_chars, left_counts = _fuzzy_group_projection(
        left, projection_cache
    )
    right_text, right_content_chars, right_counts = _fuzzy_group_projection(
        right, projection_cache
    )
    exact_equal_protected = shape == (1, 1) and left_text == right_text
    meets_content = (
        min(left_content_chars, right_content_chars) >= config.fuzzy_min_char_count
        and max(left_content_chars, right_content_chars)
        <= config.fuzzy_max_group_char_count
    )
    if max(left_content_chars, right_content_chars) > config.fuzzy_max_group_char_count:
        return FuzzyGroupScore(
            shape=shape,
            left_text=left_text,
            right_text=right_text,
            left_content_chars=left_content_chars,
            right_content_chars=right_content_chars,
            score=0.0,
            left_unmatched_chars=0,
            right_unmatched_chars=0,
            exact_equal_protected=exact_equal_protected,
            is_accepted=False,
            is_gray=True,
        )

    multiset_matches = sum(
        min(count, right_counts.get(character, 0))
        for character, count in left_counts.items()
    )
    ratio_upper_bound = (
        2.0 * multiset_matches / (len(left_text) + len(right_text))
    )
    if (
        not exact_equal_protected
        and ratio_upper_bound < config.fuzzy_uncertain_similarity_floor
    ):
        return FuzzyGroupScore(
            shape=shape,
            left_text=left_text,
            right_text=right_text,
            left_content_chars=left_content_chars,
            right_content_chars=right_content_chars,
            score=ratio_upper_bound,
            left_unmatched_chars=0,
            right_unmatched_chars=0,
            exact_equal_protected=False,
            is_accepted=False,
            is_gray=False,
        )

    matcher = matcher_cache.get(right_text)
    if matcher is None:
        matcher = SequenceMatcher(None, "", right_text, autojunk=False)
        matcher_cache[right_text] = matcher
    matcher.set_seq1(left_text)
    left_ranges, right_ranges = _unmatched_ranges(matcher)
    left_unmatched = fuzzy_unmatched_content_count(left_text, left_ranges)
    right_unmatched = fuzzy_unmatched_content_count(right_text, right_ranges)
    score = matcher.ratio()
    meets_unmatched = (
        left_unmatched <= config.fuzzy_max_unmatched_chars_per_side
        and right_unmatched <= config.fuzzy_max_unmatched_chars_per_side
    )
    is_accepted = (
        not exact_equal_protected
        and meets_content
        and meets_unmatched
        and score >= config.fuzzy_similarity_threshold
    )
    is_gray = (
        exact_equal_protected
        or (
            score >= config.fuzzy_uncertain_similarity_floor
            and (not is_accepted or not meets_content or not meets_unmatched)
        )
    )
    return FuzzyGroupScore(
        shape=shape,
        left_text=left_text,
        right_text=right_text,
        left_content_chars=left_content_chars,
        right_content_chars=right_content_chars,
        score=score,
        left_unmatched_chars=left_unmatched,
        right_unmatched_chars=right_unmatched,
        exact_equal_protected=exact_equal_protected,
        is_accepted=is_accepted,
        is_gray=is_gray,
    )


def _candidate_from_tiling(
    document: Tuple[OcrDocumentSegment, ...],
    current: Tuple[OcrTextSegment, ...],
    tiling: Tuple[Tuple[int, int], ...],
    config: OcrAggregationConfig,
    score_cache: dict[Tuple[Tuple[str, ...], Tuple[str, ...]], FuzzyGroupScore],
    projection_cache: Dict[Tuple[str, ...], Tuple[str, int, Counter[str]]],
    matcher_cache: Dict[str, SequenceMatcher],
) -> FuzzyBoundaryCandidate:
    document_position = 0
    current_position = 0
    groups = []
    for left_count, right_count in tiling:
        left_group = document[document_position:document_position + left_count]
        right_group = current[current_position:current_position + right_count]
        cache_key = (
            tuple(item.document_segment_id for item in left_group),
            tuple(item.segment_id for item in right_group),
        )
        group = score_cache.get(cache_key)
        if group is None:
            group = _score_fuzzy_group_for_search(
                left_group,
                right_group,
                config,
                projection_cache,
                matcher_cache,
            )
            score_cache[cache_key] = group
        groups.append(group)
        document_position += left_count
        current_position += right_count
    document_content_chars = sum(group.left_content_chars for group in groups)
    current_content_chars = sum(group.right_content_chars for group in groups)
    score_weight = sum(
        max(group.left_content_chars, group.right_content_chars)
        for group in groups
    )
    weighted_score = (
        0.0
        if score_weight == 0
        else sum(
            group.score * max(group.left_content_chars, group.right_content_chars)
            for group in groups
        ) / score_weight
    )
    return FuzzyBoundaryCandidate(
        shapes=tiling,
        document_segment_ids=tuple(item.document_segment_id for item in document),
        current_segment_ids=tuple(item.segment_id for item in current),
        groups=tuple(groups),
        document_content_chars=document_content_chars,
        current_content_chars=current_content_chars,
        weighted_score=weighted_score,
    )


def _candidate_sort_key(candidate: FuzzyBoundaryCandidate) -> Tuple[Any, ...]:
    return (
        -candidate.current_content_chars,
        -len(candidate.current_segment_ids),
        -candidate.document_content_chars,
        -candidate.weighted_score,
        candidate.group_count,
        candidate.shapes,
    )


def _candidate_mapping_key(candidate: FuzzyBoundaryCandidate) -> Tuple[Any, ...]:
    return (
        candidate.document_segment_ids,
        candidate.current_segment_ids,
        candidate.shapes,
    )


def _fuzzy_tie_candidates(
    candidates: Sequence[FuzzyBoundaryCandidate],
    config: OcrAggregationConfig,
) -> Tuple[Optional[FuzzyBoundaryCandidate], Tuple[FuzzyBoundaryCandidate, ...]]:
    ordered = tuple(sorted(candidates, key=_candidate_sort_key))
    if not ordered:
        return None, ()
    best = ordered[0]
    ties = tuple(
        candidate
        for candidate in ordered
        if (
            candidate.current_content_chars == best.current_content_chars
            and len(candidate.current_segment_ids) == len(best.current_segment_ids)
            and candidate.document_content_chars == best.document_content_chars
            and candidate.group_count == best.group_count
            and abs(candidate.weighted_score - best.weighted_score)
            <= config.fuzzy_tie_epsilon
            and _candidate_mapping_key(candidate) != _candidate_mapping_key(best)
        )
    )
    return best, ties


def _accepted_fuzzy_result(
    candidate: FuzzyBoundaryCandidate,
    document: Tuple[OcrDocumentSegment, ...],
    current: Tuple[OcrTextSegment, ...],
    identity: Optional[Tuple[str, int]] = None,
) -> FuzzyBoundaryMatch:
    screen_id, screen_index = (
        _screen_identity(current) if identity is None else identity
    )
    document_position = 0
    current_position = 0
    evidence = []
    mappings = []
    for group_order, group in enumerate(candidate.groups):
        left_count, right_count = group.shape
        document_group = document[document_position:document_position + left_count]
        current_group = current[current_position:current_position + right_count]
        stable_match_id = match_id(screen_index, group_order)
        match_type = {
            (1, 1): AggregationMatchType.ADJACENT_FUZZY_1_1,
            (1, 2): AggregationMatchType.ADJACENT_FUZZY_1_2,
            (2, 1): AggregationMatchType.ADJACENT_FUZZY_2_1,
        }[group.shape]
        evidence.append(
            OcrSegmentMatchEvidence(
                match_id=stable_match_id,
                match_type=match_type,
                current_screen_id=screen_id,
                current_screen_index=screen_index,
                current_segment_ids=tuple(item.segment_id for item in current_group),
                current_ocr_box_ids=_flatten_current_box_ids(current_group),
                matched_document_segment_ids=tuple(
                    item.document_segment_id for item in document_group
                ),
                score=group.score,
                exact_basis=None,
                risk=AggregationDuplicateRisk.LOW,
                warning_codes=(),
            )
        )
        source_segment_ids = tuple(item.segment_id for item in current_group)
        source_box_ids = _flatten_current_box_ids(current_group)
        for document_segment in document_group:
            mappings.append(
                FuzzyOccurrenceMapping(
                    document_segment_id=document_segment.document_segment_id,
                    occurrence=OcrSourceOccurrence(
                        occurrence_order=len(document_segment.source_occurrences),
                        source_screen_id=screen_id,
                        source_screen_index=screen_index,
                        source_segment_ids=source_segment_ids,
                        source_ocr_box_ids=source_box_ids,
                        occurrence_role=AggregationOccurrenceRole.MATCHED,
                        match_id=stable_match_id,
                    ),
                )
            )
        document_position += left_count
        current_position += right_count
    return FuzzyBoundaryMatch(
        matched_current_segment_ids=candidate.current_segment_ids,
        matched_document_segment_ids=candidate.document_segment_ids,
        remaining_current_segment_ids=tuple(
            item.segment_id for item in current[current_position:]
        ),
        uncertain_current_segment_ids=(),
        match_evidence=tuple(evidence),
        occurrence_mappings=tuple(mappings),
    )


def find_fuzzy_boundary_overlap(
    document_segments: Sequence[OcrDocumentSegment],
    current_segments: Sequence[OcrTextSegment],
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
) -> FuzzyBoundaryMatch:
    """Find one bounded fuzzy tail/head path only after exact found no acceptance."""

    if not isinstance(config, OcrAggregationConfig):
        raise TypeError("aggregation config has an invalid contract")
    validate_aggregation_config(config)
    document = tuple(document_segments)
    current = tuple(current_segments)
    _validate_document_segments(document)
    if not current:
        return FuzzyBoundaryMatch((), (), (), (), (), ())
    return _find_fuzzy_boundary_overlap_validated(
        document,
        current,
        config,
        _screen_identity(current),
    )


def _find_fuzzy_boundary_overlap_validated(
    document: Tuple[OcrDocumentSegment, ...],
    current: Tuple[OcrTextSegment, ...],
    config: OcrAggregationConfig,
    identity: Tuple[str, int],
) -> FuzzyBoundaryMatch:
    """Fuzzy overlap core for aggregator-owned, already-validated inputs."""

    if not document:
        return FuzzyBoundaryMatch(
            (), (), tuple(item.segment_id for item in current), (), (), ()
        )
    tail = document[-config.fuzzy_max_tail_segments:]
    head = current[:config.fuzzy_max_head_segments]
    candidates = []
    score_cache = {}
    projection_cache = {}
    matcher_cache = {}
    gray_current_count = 0
    for document_count in range(1, len(tail) + 1):
        document_window = tail[-document_count:]
        for current_count in range(1, len(head) + 1):
            current_window = head[:current_count]
            for tiling in enumerate_fuzzy_tilings(document_count, current_count):
                candidate = _candidate_from_tiling(
                    document_window,
                    current_window,
                    tiling,
                    config,
                    score_cache,
                    projection_cache,
                    matcher_cache,
                )
                candidates.append(candidate)
                if len(candidates) > config.fuzzy_candidate_limit:
                    return FuzzyBoundaryMatch(
                        (),
                        (),
                        tuple(item.segment_id for item in current),
                        tuple(item.segment_id for item in head),
                        (),
                        (),
                        candidate_limit_exceeded=True,
                    )
                if candidate.is_gray:
                    gray_current_count = max(
                        gray_current_count,
                        len(candidate.current_segment_ids),
                    )
    accepted = tuple(candidate for candidate in candidates if candidate.is_accepted)
    if accepted:
        best, ties = _fuzzy_tie_candidates(accepted, config)
        if best is None:
            raise AggregationInvariantError("fuzzy_candidate_selection_invalid")
        if ties:
            uncertain_count = max(
                len(candidate.current_segment_ids) for candidate in ties + (best,)
            )
            return FuzzyBoundaryMatch(
                (),
                (),
                tuple(item.segment_id for item in current),
                tuple(item.segment_id for item in current[:uncertain_count]),
                (),
                (),
                ambiguous_tie=True,
            )
        return _accepted_fuzzy_result(best, document, current, identity)
    return FuzzyBoundaryMatch(
        (),
        (),
        tuple(item.segment_id for item in current),
        tuple(item.segment_id for item in current[:gray_current_count]),
        (),
        (),
    )


def apply_fuzzy_boundary_occurrences(
    document_segments: Sequence[OcrDocumentSegment],
    match: FuzzyBoundaryMatch,
) -> Tuple[OcrDocumentSegment, ...]:
    """Return fresh document segments with an accepted fuzzy occurrence appended."""

    document = tuple(document_segments)
    _validate_document_segments(document)
    if not isinstance(match, FuzzyBoundaryMatch):
        raise TypeError("fuzzy boundary match has an invalid contract")
    if not match.accepted:
        return document
    document_ids = tuple(item.document_segment_id for item in document)
    mapping_by_id = {}
    for mapping in match.occurrence_mappings:
        if mapping.document_segment_id not in document_ids:
            raise AggregationInvariantError("fuzzy_occurrence_mapping_invalid")
        if mapping.document_segment_id in mapping_by_id:
            raise AggregationInvariantError("fuzzy_occurrence_mapping_invalid")
        mapping_by_id[mapping.document_segment_id] = mapping
    updated = []
    for segment in document:
        mapping = mapping_by_id.get(segment.document_segment_id)
        if mapping is None:
            updated.append(segment)
            continue
        updated.append(
            OcrDocumentSegment(
                document_segment_id=segment.document_segment_id,
                order=segment.order,
                normalized_text=segment.normalized_text,
                comparison_text=segment.comparison_text,
                comparison_char_count=segment.comparison_char_count,
                source_occurrences=segment.source_occurrences + (mapping.occurrence,),
            )
        )
    return tuple(updated)


def _screen_identity(
    current: Tuple[OcrTextSegment, ...], *, allow_subsequence: bool = False,
) -> Tuple[str, int]:
    if not current:
        raise AggregationInvariantError("current_screen_empty")
    first = current[0]
    if not isinstance(first, OcrTextSegment):
        raise AggregationInvariantError("current_segment_invalid")
    prefix = ":line:"
    if prefix not in first.segment_id:
        raise AggregationInvariantError("current_segment_id_invalid")
    screen_id, line_order = first.segment_id.rsplit(prefix, 1)
    if not screen_id or not line_order.isdecimal() or first.order != int(line_order):
        raise AggregationInvariantError("current_segment_id_invalid")
    if (
        not isinstance(first.screen_index, int)
        or isinstance(first.screen_index, bool)
        or first.screen_index < 1
    ):
        raise AggregationInvariantError("current_screen_index_invalid")
    for offset, segment in enumerate(current):
        expected_order = int(line_order) + offset if allow_subsequence else offset
        if not isinstance(segment, OcrTextSegment):
            raise AggregationInvariantError("current_segment_invalid")
        if (
            segment.segment_id != "{0}:line:{1}".format(screen_id, expected_order)
            or segment.order != expected_order
            or segment.screen_index != first.screen_index
            or not isinstance(segment.normalized_text, str)
            or not segment.normalized_text
            or not isinstance(segment.comparison_text, str)
            or not segment.comparison_text
            or any(character.isspace() for character in segment.comparison_text)
        ):
            raise AggregationInvariantError("current_segment_invalid")
    return screen_id, first.screen_index


def _validate_document_segments(
    document: Tuple[OcrDocumentSegment, ...],
) -> None:
    for expected_order, segment in enumerate(document):
        if not isinstance(segment, OcrDocumentSegment) or segment.order != expected_order:
            raise AggregationInvariantError("document_segment_invalid")


def _flatten_current_box_ids(segments: Sequence[OcrTextSegment]) -> Tuple[str, ...]:
    return tuple(
        box_id
        for segment in segments
        for box_id in segment.ocr_box_ids
    )


def _accepted_exact_result(
    document: Tuple[OcrDocumentSegment, ...],
    current: Tuple[OcrTextSegment, ...],
    k: int,
    basis: str,
    identity: Optional[Tuple[str, int]] = None,
) -> ExactBoundaryMatch:
    screen_id, screen_index = identity if identity is not None else _screen_identity(current)
    current_head = current[:k]
    document_tail = document[-k:]
    stable_match_id = match_id(screen_index, 0)
    evidence = OcrSegmentMatchEvidence(
        match_id=stable_match_id,
        match_type=AggregationMatchType.ADJACENT_EXACT,
        current_screen_id=screen_id,
        current_screen_index=screen_index,
        current_segment_ids=tuple(item.segment_id for item in current_head),
        current_ocr_box_ids=_flatten_current_box_ids(current_head),
        matched_document_segment_ids=tuple(
            item.document_segment_id for item in document_tail
        ),
        score=None,
        exact_basis=basis,
        risk=AggregationDuplicateRisk.NONE,
        warning_codes=(),
    )
    mappings = tuple(
        ExactOccurrenceMapping(
            document_segment_id=document_segment.document_segment_id,
            occurrence=OcrSourceOccurrence(
                occurrence_order=len(document_segment.source_occurrences),
                source_screen_id=screen_id,
                source_screen_index=screen_index,
                source_segment_ids=(current_segment.segment_id,),
                source_ocr_box_ids=tuple(current_segment.ocr_box_ids),
                occurrence_role=AggregationOccurrenceRole.MATCHED,
                match_id=stable_match_id,
            ),
        )
        for document_segment, current_segment in zip(document_tail, current_head)
    )
    return ExactBoundaryMatch(
        matched_current_segment_ids=tuple(item.segment_id for item in current_head),
        matched_document_segment_ids=tuple(
            item.document_segment_id for item in document_tail
        ),
        remaining_current_segment_ids=tuple(item.segment_id for item in current[k:]),
        uncertain_current_segment_ids=(),
        exact_basis=basis,
        match_evidence=(evidence,),
        occurrence_mappings=mappings,
    )


def find_exact_boundary_overlap(
    document_segments: Sequence[OcrDocumentSegment],
    current_segments: Sequence[OcrTextSegment],
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
) -> ExactBoundaryMatch:
    """Find only the longest continuous document-tail/current-head exact overlap."""

    if not isinstance(config, OcrAggregationConfig):
        raise TypeError("aggregation config has an invalid contract")
    validate_aggregation_config(config)
    document = tuple(document_segments)
    current = tuple(current_segments)
    _validate_document_segments(document)
    if not current:
        return ExactBoundaryMatch((), (), (), (), None, (), ())
    return _find_exact_boundary_overlap_validated(
        document,
        current,
        config,
        _screen_identity(current),
    )


def _find_exact_boundary_overlap_validated(
    document: Tuple[OcrDocumentSegment, ...],
    current: Tuple[OcrTextSegment, ...],
    config: OcrAggregationConfig,
    identity: Tuple[str, int],
) -> ExactBoundaryMatch:
    """Exact overlap core for aggregator-owned, already-validated inputs."""

    if not document:
        return ExactBoundaryMatch(
            (),
            (),
            tuple(item.segment_id for item in current),
            (),
            None,
            (),
            (),
        )

    document_keys = tuple(item.comparison_text for item in document)
    current_keys = tuple(item.comparison_text for item in current)
    # Identity validation above already establishes the R04 comparison-text
    # contract.  The document count was validated when the frozen segment was
    # created, so no second whitespace scan is necessary here.
    current_counts = tuple(len(value) for value in current_keys)
    document_counts = tuple(item.comparison_char_count for item in document)
    maximum = min(len(document), len(current), config.max_screen_segments)
    longest_inadmissible = 0
    for k in range(maximum, 0, -1):
        if document_keys[-k:] != current_keys[:k]:
            continue
        tail_chars = sum(document_counts[-k:])
        head_chars = sum(current_counts[:k])
        normal_evidence = (
            k >= config.exact_min_segment_count
            and min(tail_chars, head_chars) >= config.exact_min_char_count
            and any(
                count > config.short_segment_char_threshold
                for count in current_counts[:k]
            )
        )
        if normal_evidence:
            return _accepted_exact_result(
                document,
                current,
                k,
                "comparison_sequence_equal",
                identity,
            )
        if (
            k == 1
            and len(current) == 1
            and current_counts[0] >= config.exact_single_segment_min_char_count
        ):
            return _accepted_exact_result(
                document,
                current,
                1,
                "single_full_screen_equal",
                identity,
            )
        longest_inadmissible = max(longest_inadmissible, k)

    current_ids = tuple(item.segment_id for item in current)
    return ExactBoundaryMatch(
        (),
        (),
        current_ids,
        current_ids[:longest_inadmissible],
        None,
        (),
        (),
    )


def apply_exact_boundary_occurrences(
    document_segments: Sequence[OcrDocumentSegment],
    match: ExactBoundaryMatch,
) -> Tuple[OcrDocumentSegment, ...]:
    """Return new document segments with accepted exact occurrences appended."""

    document = tuple(document_segments)
    _validate_document_segments(document)
    if not isinstance(match, ExactBoundaryMatch):
        raise TypeError("exact boundary match has an invalid contract")
    if not match.accepted:
        if match.occurrence_mappings:
            raise AggregationInvariantError("unaccepted_exact_has_occurrences")
        return document
    if len(match.occurrence_mappings) != len(match.matched_document_segment_ids):
        raise AggregationInvariantError("exact_occurrence_mapping_invalid")
    document_ids = tuple(item.document_segment_id for item in document)
    mapping_by_id = {}
    for mapping in match.occurrence_mappings:
        if (
            mapping.document_segment_id not in document_ids
            or mapping.document_segment_id not in match.matched_document_segment_ids
            or mapping.document_segment_id in mapping_by_id
        ):
            raise AggregationInvariantError("exact_occurrence_mapping_invalid")
        mapping_by_id[mapping.document_segment_id] = mapping
    updated = []
    for segment in document:
        mapping = mapping_by_id.get(segment.document_segment_id)
        if mapping is None:
            updated.append(segment)
            continue
        occurrence = mapping.occurrence
        updated.append(
            OcrDocumentSegment(
                document_segment_id=segment.document_segment_id,
                order=segment.order,
                normalized_text=segment.normalized_text,
                comparison_text=segment.comparison_text,
                comparison_char_count=segment.comparison_char_count,
                source_occurrences=segment.source_occurrences + (occurrence,),
            )
        )
    return tuple(updated)


def _validate_r04_segment(
    record: OcrScreenRecord,
    segment: OcrTextSegment,
    expected_order: int,
    known_box_ids: set[str],
    ordered_box_positions: dict[str, int],
) -> None:
    if segment.segment_id != "{0}:line:{1}".format(record.screen_id, expected_order):
        raise R04SegmentAdapterError("segment_id_invalid")
    if segment.screen_index != record.screen_index:
        raise R04SegmentAdapterError("segment_screen_index_invalid")
    if segment.order != expected_order:
        raise R04SegmentAdapterError("segment_order_invalid")
    if not isinstance(segment.normalized_text, str) or not segment.normalized_text:
        raise R04SegmentAdapterError("segment_normalized_text_invalid")
    if segment.comparison_text != build_comparison_text(segment.normalized_text):
        raise R04SegmentAdapterError("segment_comparison_text_invalid")
    if not segment.comparison_text or any(
        character.isspace() for character in segment.comparison_text
    ):
        raise R04SegmentAdapterError("segment_comparison_text_invalid")
    if not segment.ocr_box_ids or len(set(segment.ocr_box_ids)) != len(segment.ocr_box_ids):
        raise R04SegmentAdapterError("segment_box_ids_invalid")
    if any(box_id not in known_box_ids for box_id in segment.ocr_box_ids):
        raise R04SegmentAdapterError("segment_box_missing")
    positions = [ordered_box_positions.get(box_id) for box_id in segment.ocr_box_ids]
    if any(position is None for position in positions) or positions != sorted(positions):
        raise R04SegmentAdapterError("segment_box_order_invalid")


def adapt_r04_screen_segments(
    record: OcrScreenRecord, *, enforce_segment_limit: bool = True,
) -> Tuple[OcrTextSegment, ...]:
    """Validate and return the original frozen R04 visual-line tuple unchanged."""

    if not isinstance(record, OcrScreenRecord):
        raise TypeError("R04 screen record has an invalid contract")
    if record.normalization_status != NormalizationStatus.COMPLETED:
        if record.normalization_status == NormalizationStatus.FAILED:
            raise R04SegmentAdapterError("r04_not_completed")
        raise R04SegmentAdapterError("r04_not_attempted")
    if getattr(record, "screen_id", None) in (None, ""):
        raise R04SegmentAdapterError("screen_id_invalid")
    if not isinstance(record.screen_index, int) or isinstance(record.screen_index, bool):
        raise R04SegmentAdapterError("screen_index_invalid")
    if record.screen_index < 1:
        raise R04SegmentAdapterError("screen_index_invalid")
    if (
        enforce_segment_limit
        and len(record.segments) > DEFAULT_OCR_AGGREGATION_CONFIG.max_screen_segments
    ):
        raise R04SegmentAdapterError("screen_segment_limit_exceeded")
    known_box_ids = {box.box_id for box in record.raw_boxes}
    if len(known_box_ids) != len(record.raw_boxes):
        raise R04SegmentAdapterError("screen_box_ids_invalid")
    ordered_box_positions = {
        box_id: position for position, box_id in enumerate(record.ordered_box_ids)
    }
    for expected_order, segment in enumerate(record.segments):
        _validate_r04_segment(
            record,
            segment,
            expected_order,
            known_box_ids,
            ordered_box_positions,
        )
    return record.segments


def build_document_text(segments: Sequence[OcrDocumentSegment]) -> str:
    """Project the sole document body from sequential document segments."""

    values = tuple(segments)
    for expected_order, segment in enumerate(values):
        if not isinstance(segment, OcrDocumentSegment):
            raise AggregationInvariantError("document_segment_invalid")
        if segment.order != expected_order:
            raise AggregationInvariantError("document_segment_order_invalid")
        if not segment.normalized_text:
            raise AggregationInvariantError("empty_document_segment")
    return "\n".join(segment.normalized_text for segment in values)


# Change 5 deliberately keeps the following historical classifier and document
# assembler in this pure module.  It has no persistence, clocks, process state,
# or connection to CandidateOcrBuilder.


@dataclass(frozen=True)
class HistoricalOccurrenceMapping:
    document_segment_id: str
    occurrence: OcrSourceOccurrence


@dataclass(frozen=True)
class HistoricalDuplicateClassification:
    matched_current_segment_ids: Tuple[str, ...]
    matched_document_segment_ids: Tuple[str, ...]
    remaining_current_segment_ids: Tuple[str, ...]
    uncertain_current_segment_ids: Tuple[str, ...]
    match_evidence: Tuple[OcrSegmentMatchEvidence, ...]
    occurrence_mappings: Tuple[HistoricalOccurrenceMapping, ...]
    warning_codes: Tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return bool(self.matched_current_segment_ids)


class HistoricalSequenceIndex:
    """Candidate-local, incrementally maintained exact keys of lengths 2--4."""

    def __init__(self, config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG) -> None:
        validate_aggregation_config(config)
        self._config = config
        self._keys: Dict[Tuple[str, ...], Tuple[int, ...]] = {}
        self._segments: list[OcrDocumentSegment] = []

    def add_document_segment(self, segment: OcrDocumentSegment) -> None:
        if not isinstance(segment, OcrDocumentSegment) or segment.order != len(self._segments):
            raise AggregationInvariantError("historical_index_segment_invalid")
        self._segments.append(segment)
        end = len(self._segments)
        for length in range(self._config.historical_min_segment_count,
                            self._config.historical_max_segment_count + 1):
            if end < length:
                continue
            key = tuple(item.comparison_text for item in self._segments[end - length:end])
            self._keys[key] = self._keys.get(key, ()) + (end - length,)

    def add_document_segments(self, segments: Sequence[OcrDocumentSegment]) -> None:
        for segment in segments:
            self.add_document_segment(segment)

    def positions(self, comparison_key: Sequence[str]) -> Tuple[int, ...]:
        return self._keys.get(tuple(comparison_key), ())

    def clear(self) -> None:
        self._keys.clear()
        self._segments.clear()


def _historical_occurrence(
    document_segment: OcrDocumentSegment,
    screen_id: str,
    screen_index: int,
    current_segment: OcrTextSegment,
    stable_match_id: str,
) -> HistoricalOccurrenceMapping:
    return HistoricalOccurrenceMapping(
        document_segment.document_segment_id,
        OcrSourceOccurrence(
            occurrence_order=len(document_segment.source_occurrences),
            source_screen_id=screen_id,
            source_screen_index=screen_index,
            source_segment_ids=(current_segment.segment_id,),
            source_ocr_box_ids=tuple(current_segment.ocr_box_ids),
            occurrence_role=AggregationOccurrenceRole.MATCHED,
            match_id=stable_match_id,
        ),
    )


def classify_historical_duplicates(
    document_segments: Sequence[OcrDocumentSegment],
    current_segments: Sequence[OcrTextSegment],
    index: HistoricalSequenceIndex,
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
    match_order_offset: int = 0,
) -> HistoricalDuplicateClassification:
    """Classify bounded non-adjacent exact repeats, failing open on weak context."""

    validate_aggregation_config(config)
    if not isinstance(index, HistoricalSequenceIndex):
        raise TypeError("historical index has an invalid contract")
    if isinstance(match_order_offset, bool) or not isinstance(match_order_offset, int) or match_order_offset < 0:
        raise TypeError("historical match order offset is invalid")
    document = tuple(document_segments)
    current = tuple(current_segments)
    _validate_document_segments(document)
    if not current:
        return HistoricalDuplicateClassification((), (), (), (), (), (), ())
    # Historical classification runs after an accepted boundary stage, so its
    # candidate can be a contiguous suffix of the current R04 screen.  It is
    # still validated against its original R04 order and IDs.
    return _classify_historical_duplicates_validated(
        document,
        current,
        index,
        config,
        match_order_offset,
        _screen_identity(current, allow_subsequence=True),
    )


def _classify_historical_duplicates_validated(
    document: Tuple[OcrDocumentSegment, ...],
    current: Tuple[OcrTextSegment, ...],
    index: HistoricalSequenceIndex,
    config: OcrAggregationConfig,
    match_order_offset: int,
    identity: Tuple[str, int],
) -> HistoricalDuplicateClassification:
    """Historical core for aggregator-owned, already-validated inputs."""

    screen_id, screen_index = identity
    if len(document) < config.historical_min_segment_count:
        return HistoricalDuplicateClassification(
            (), (), tuple(item.segment_id for item in current), (), (), (), ()
        )
    matched: list[str] = []
    matched_document: list[str] = []
    uncertain: list[str] = []
    evidence: list[OcrSegmentMatchEvidence] = []
    mappings: list[HistoricalOccurrenceMapping] = []
    warnings: list[str] = []
    claimed: set[int] = set()
    # Largest sequence first prevents a shorter sub-sequence from consuming it.
    for length in range(config.historical_max_segment_count,
                        config.historical_min_segment_count - 1, -1):
        for start in range(0, len(current) - length + 1):
            span = tuple(range(start, start + length))
            if any(position in claimed for position in span):
                continue
            current_group = current[start:start + length]
            if (sum(len(item.comparison_text) for item in current_group)
                    < config.historical_min_char_count
                    or any(len(item.comparison_text)
                           <= config.short_segment_char_threshold for item in current_group)):
                continue
            key = tuple(item.comparison_text for item in current_group)
            positions = index.positions(key)
            if len(positions) != 1:
                if positions:
                    uncertain.extend(item.segment_id for item in current_group)
                    warnings.append("historical_duplicate_ambiguous")
                    claimed.update(span)
                continue
            history_start = positions[0]
            history_end = history_start + length
            # An external anchor is an immediately adjacent exact line on each side.
            anchored = (
                start > 0 and history_start > 0
                and current[start - 1].comparison_text == document[history_start - 1].comparison_text
                and start + length < len(current) and history_end < len(document)
                and current[start + length].comparison_text == document[history_end].comparison_text
            )
            if not anchored:
                uncertain.extend(item.segment_id for item in current_group)
                warnings.append("historical_context_insufficient")
                # A longer boundary-spanning proposal must not hide a shorter,
                # fully contextualized interior sequence on the same screen.
                continue
            history_group = document[history_start:history_end]
            if any(len(item.source_occurrences) != 1 for item in history_group):
                uncertain.extend(item.segment_id for item in current_group)
                warnings.append("historical_duplicate_ambiguous")
                claimed.update(span)
                continue
            if any(item.document_segment_id in matched_document for item in history_group):
                uncertain.extend(item.segment_id for item in current_group)
                warnings.append("historical_mapping_conflict")
                claimed.update(span)
                continue
            # Earlier boundary stages may already have allocated match IDs for
            # this screen.  Historical matching keeps their deterministic
            # order while preserving the candidate-local classification logic.
            stable_match_id = match_id(screen_index, match_order_offset + len(evidence))
            evidence.append(OcrSegmentMatchEvidence(
                match_id=stable_match_id,
                match_type=AggregationMatchType.HISTORICAL_EXACT,
                current_screen_id=screen_id,
                current_screen_index=screen_index,
                current_segment_ids=tuple(item.segment_id for item in current_group),
                current_ocr_box_ids=_flatten_current_box_ids(current_group),
                matched_document_segment_ids=tuple(item.document_segment_id for item in history_group),
                score=None,
                exact_basis="historical_sequence_with_context",
                risk=AggregationDuplicateRisk.NONE,
                warning_codes=(),
            ))
            for document_segment, current_segment in zip(history_group, current_group):
                mappings.append(_historical_occurrence(
                    document_segment, screen_id, screen_index, current_segment, stable_match_id))
            matched.extend(item.segment_id for item in current_group)
            matched_document.extend(item.document_segment_id for item in history_group)
            claimed.update(span)
    current_ids = tuple(item.segment_id for item in current)
    matched_ids = tuple(matched)
    uncertain_ids = tuple(item for item in dict.fromkeys(uncertain) if item not in matched_ids)
    remaining = tuple(item for item in current_ids if item not in matched_ids)
    return HistoricalDuplicateClassification(
        matched_ids, tuple(matched_document), remaining, uncertain_ids,
        tuple(evidence), tuple(mappings), tuple(dict.fromkeys(warnings)))


def apply_historical_occurrences(
    document_segments: Sequence[OcrDocumentSegment],
    classification: HistoricalDuplicateClassification,
) -> Tuple[OcrDocumentSegment, ...]:
    document = tuple(document_segments)
    _validate_document_segments(document)
    mapping_by_id = {item.document_segment_id: item for item in classification.occurrence_mappings}
    if len(mapping_by_id) != len(classification.occurrence_mappings):
        raise AggregationInvariantError("historical_mapping_conflict")
    return tuple(
        segment if segment.document_segment_id not in mapping_by_id else OcrDocumentSegment(
            document_segment_id=segment.document_segment_id, order=segment.order,
            normalized_text=segment.normalized_text, comparison_text=segment.comparison_text,
            comparison_char_count=segment.comparison_char_count,
            source_occurrences=segment.source_occurrences + (mapping_by_id[segment.document_segment_id].occurrence,),
        )
        for segment in document
    )


@dataclass(frozen=True)
class CandidateAggregationSummary:
    formal_screen_count: int
    appended_document_segment_count: int
    matched_segment_count: int
    uncertain_segment_count: int


@dataclass(frozen=True)
class CandidateAggregationResult:
    run_id: str
    candidate_record_id: str
    document_segments: Tuple[OcrDocumentSegment, ...]
    document_text: Optional[str]
    document_build_status: DocumentBuildStatus
    aggregation_warning_codes: Tuple[str, ...]
    aggregation_duplicate_risk: AggregationDuplicateRisk
    aggregation_summary: CandidateAggregationSummary
    match_evidence: Tuple[OcrSegmentMatchEvidence, ...]


@dataclass(frozen=True)
class ScreenAggregationResult:
    screen_id: str
    screen_index: Optional[int]
    status: AggregationStatus
    warning_codes: Tuple[str, ...]
    match_evidence: Tuple[OcrSegmentMatchEvidence, ...]
    appended_document_segment_ids: Tuple[str, ...]
    matched_segment_ids: Tuple[str, ...] = ()
    new_segment_ids: Tuple[str, ...] = ()
    uncertain_segment_ids: Tuple[str, ...] = ()


class CandidateAggregationFinalizedError(RuntimeError):
    pass


class CandidateAggregationFinalizeConflictError(RuntimeError):
    pass


def aggregation_screen_record_fields(
    record: OcrScreenRecord,
    result: ScreenAggregationResult,
    config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
) -> dict[str, Any]:
    """Project a pure screen result onto the sole persisted R04 screen record."""

    if not isinstance(record, OcrScreenRecord) or not isinstance(result, ScreenAggregationResult):
        raise TypeError("screen aggregation projection has an invalid contract")
    validate_aggregation_config(config)
    if result.status == AggregationStatus.NOT_ATTEMPTED:
        return {
            "aggregation_status": AggregationStatus.NOT_ATTEMPTED,
            "aggregation_version": None, "aggregation_config_version": None,
            "aggregation_config_digest": None, "matched_segment_ids": (),
            "new_segment_ids": (), "uncertain_segment_ids": (),
            "match_evidence": (), "aggregation_warning_codes": (),
            "aggregation_duplicate_risk": None, "overlap_text": None,
            "new_text": None, "overlap_char_count": None,
            "new_text_char_count": None, "overlap_segment_count": None,
            "new_segment_count": None, "certain_new_segment_count": None,
            "uncertain_segment_count": None, "uncertain_char_count": None,
        }
    digest = aggregation_config_digest(config)
    if result.status == AggregationStatus.FAILED:
        return {
            "aggregation_status": AggregationStatus.FAILED,
            "aggregation_version": AGGREGATION_VERSION,
            "aggregation_config_version": AGGREGATION_CONFIG_VERSION,
            "aggregation_config_digest": digest, "matched_segment_ids": (),
            "new_segment_ids": (), "uncertain_segment_ids": (),
            "match_evidence": (), "aggregation_warning_codes": result.warning_codes,
            "aggregation_duplicate_risk": AggregationDuplicateRisk.ELEVATED,
            "overlap_text": None, "new_text": None, "overlap_char_count": None,
            "new_text_char_count": None, "overlap_segment_count": None,
            "new_segment_count": None, "certain_new_segment_count": None,
            "uncertain_segment_count": None, "uncertain_char_count": None,
        }
    selected = {segment.segment_id: segment for segment in record.segments}
    matched = result.matched_segment_ids
    new = result.new_segment_ids
    uncertain = result.uncertain_segment_ids
    def projection(identifiers: Tuple[str, ...]) -> Tuple[str, int]:
        segments = tuple(selected[identifier] for identifier in identifiers)
        return "\n".join(item.normalized_text for item in segments), sum(
            aggregation_char_count(item.comparison_text) for item in segments
        )
    overlap_text, overlap_chars = projection(matched)
    new_text, new_chars = projection(new + uncertain)
    _, uncertain_chars = projection(uncertain)
    risk = (
        AggregationDuplicateRisk.ELEVATED
        if result.status == AggregationStatus.PARTIAL else
        AggregationDuplicateRisk.LOW
        if any(evidence.risk == AggregationDuplicateRisk.LOW for evidence in result.match_evidence) else
        AggregationDuplicateRisk.NONE
    )
    return {
        "aggregation_status": result.status,
        "aggregation_version": AGGREGATION_VERSION,
        "aggregation_config_version": AGGREGATION_CONFIG_VERSION,
        "aggregation_config_digest": digest, "matched_segment_ids": matched,
        "new_segment_ids": new, "uncertain_segment_ids": uncertain,
        "match_evidence": result.match_evidence,
        "aggregation_warning_codes": result.warning_codes,
        "aggregation_duplicate_risk": risk, "overlap_text": overlap_text,
        "new_text": new_text, "overlap_char_count": overlap_chars,
        "new_text_char_count": new_chars, "overlap_segment_count": len(matched),
        "new_segment_count": len(new) + len(uncertain),
        "certain_new_segment_count": len(new),
        "uncertain_segment_count": len(uncertain),
        "uncertain_char_count": uncertain_chars,
    }


class CandidateDocumentAggregator:
    """Pure, candidate-scoped R05 document assembly; callers own all I/O."""

    def __init__(self, run_id: str, candidate_record_id: str,
                 config: OcrAggregationConfig = DEFAULT_OCR_AGGREGATION_CONFIG,
                 mode: str = "record") -> None:
        if not isinstance(run_id, str) or not run_id or not isinstance(candidate_record_id, str) or not candidate_record_id:
            raise AggregationInvariantError("candidate_identity_invalid")
        validate_aggregation_config(config)
        if mode not in ("record", "disabled"):
            raise AggregationInvariantError("aggregation_mode_invalid")
        self._run_id = run_id
        self._candidate_record_id = candidate_record_id
        self._config = config
        self._mode = mode
        self._document: list[OcrDocumentSegment] = []
        self._index = HistoricalSequenceIndex(config)
        self._screens: Dict[str, OcrScreenRecord] = {}
        self._screen_results: Dict[str, ScreenAggregationResult] = {}
        self._formal_indexes: Dict[int, str] = {}
        self._warnings: list[str] = []
        self._evidence: list[OcrSegmentMatchEvidence] = []
        self._formal_count = self._safe_count = self._matched_count = self._uncertain_count = 0
        self._partial = False
        self._final_result: Optional[CandidateAggregationResult] = None
        self._final_capture_status: Optional[CaptureStatus] = None

    def _warn(self, code: str) -> None:
        if code not in self._warnings:
            self._warnings.append(code)
        self._partial = True

    def _append(self, segments: Sequence[OcrTextSegment], role: AggregationOccurrenceRole) -> Tuple[str, ...]:
        appended = []
        for source in segments:
            order = len(self._document)
            document_segment = OcrDocumentSegment(
                document_segment_id=document_segment_id(order), order=order,
                normalized_text=source.normalized_text, comparison_text=source.comparison_text,
                # The R04 adapter has already validated comparison_text for
                # this add.  The frozen document model below still performs
                # its complete final validation.
                comparison_char_count=len(source.comparison_text),
                source_occurrences=(OcrSourceOccurrence(
                    occurrence_order=0, source_screen_id=source.segment_id.rsplit(":line:", 1)[0],
                    source_screen_index=source.screen_index, source_segment_ids=(source.segment_id,),
                    source_ocr_box_ids=tuple(source.ocr_box_ids), occurrence_role=role, match_id=None),),
            )
            self._document.append(document_segment)
            self._index.add_document_segment(document_segment)
            appended.append(document_segment.document_segment_id)
        return tuple(appended)

    def _all_uncertain(
        self,
        record: OcrScreenRecord,
        warning: str,
        *,
        store_result: bool = True,
    ) -> ScreenAggregationResult:
        """Append every structurally valid segment without entering matching.

        The segment-count limit is a matching-work limit, not a source-data
        deletion limit.  This path therefore validates the complete R04 source
        shape but deliberately bypasses only that one limit gate.
        """
        try:
            segments = adapt_r04_screen_segments(record, enforce_segment_limit=False)
        except R04SegmentAdapterError:
            self._warn("segment_mapping_invalid")
            result = ScreenAggregationResult(record.screen_id, record.screen_index, AggregationStatus.FAILED,
                                             ("segment_mapping_invalid",), (), ())
            if store_result:
                self._screen_results[record.screen_id] = result
            return result
        self._safe_count += 1
        return self._append_uncertain_validated(
            record, segments, warning, store_result=store_result,
        )

    def _append_uncertain_validated(
        self,
        record: OcrScreenRecord,
        segments: Sequence[OcrTextSegment],
        warning: str,
        *,
        evidence: Sequence[OcrSegmentMatchEvidence] = (),
        matched_segment_ids: Sequence[str] = (),
        store_result: bool = True,
    ) -> ScreenAggregationResult:
        """Fail open for already adapter-validated current segments."""

        evidence_values = tuple(evidence)
        matched_ids = tuple(matched_segment_ids) or tuple(
            segment_id
            for evidence_item in evidence_values
            for segment_id in evidence_item.current_segment_ids
        )
        ids = self._append(segments, AggregationOccurrenceRole.UNCERTAIN_ORIGIN)
        self._uncertain_count += len(segments)
        self._evidence.extend(evidence_values)
        self._warn(warning)
        result = ScreenAggregationResult(record.screen_id, record.screen_index, AggregationStatus.PARTIAL,
                                         (warning,), evidence_values, ids,
                                         matched_ids, (),
                                         tuple(item.segment_id for item in segments))
        if store_result:
            self._screen_results[record.screen_id] = result
        return result

    def add_screen(
        self,
        record: OcrScreenRecord,
        *,
        force_uncertain_warning: Optional[str] = None,
    ) -> ScreenAggregationResult:
        if self._final_result is not None:
            raise CandidateAggregationFinalizedError("candidate aggregation is finalized")
        if not isinstance(record, OcrScreenRecord):
            raise TypeError("screen record has an invalid contract")
        if record.run_id != self._run_id or record.candidate_record_id != self._candidate_record_id:
            raise AggregationInvariantError("candidate_identity_mismatch")
        if record.capture_type != CaptureType.FORMAL_SCREEN or not record.is_formal_screen or self._mode == "disabled":
            return ScreenAggregationResult(record.screen_id, record.screen_index, AggregationStatus.NOT_ATTEMPTED, (), (), ())
        existing = self._screens.get(record.screen_id)
        if force_uncertain_warning is not None:
            if force_uncertain_warning not in {
                "formal_screen_out_of_order",
                "duplicate_screen_id_conflict",
                "duplicate_formal_screen_index",
            }:
                raise AggregationInvariantError("force_uncertain_warning_invalid")
            self._formal_count += 1
            return self._all_uncertain(
                record,
                force_uncertain_warning,
                store_result=existing is None,
            )
        if existing is not None:
            if existing == record:
                return self._screen_results[record.screen_id]
            # Preserve a conflicting repeat as uncertain rather than silently
            # dropping it behind the first source with the same opaque ID.
            self._formal_count += 1
            return self._all_uncertain(
                record, "duplicate_screen_id_conflict", store_result=False,
            )
        self._screens[record.screen_id] = record
        self._formal_count += 1
        if len(record.segments) > self._config.max_screen_segments:
            return self._all_uncertain(record, "screen_segment_limit_exceeded")
        if not isinstance(record.screen_index, int) or isinstance(record.screen_index, bool) or not 1 <= record.screen_index <= self._config.max_formal_screen_count:
            return self._all_uncertain(record, "formal_screen_index_invalid")
        if record.screen_index in self._formal_indexes:
            return self._all_uncertain(record, "duplicate_formal_screen_index")
        self._formal_indexes[record.screen_index] = record.screen_id
        if record.screen_index != len(self._formal_indexes):
            return self._all_uncertain(record, "formal_screen_out_of_order")
        try:
            current = adapt_r04_screen_segments(record)
        except R04SegmentAdapterError as exc:
            code = ("r04_not_completed" if str(exc).startswith("r04_") else
                    "screen_segment_limit_exceeded" if str(exc) == "screen_segment_limit_exceeded" else
                    "segment_mapping_invalid")
            self._warn(code)
            result = ScreenAggregationResult(record.screen_id, record.screen_index, AggregationStatus.FAILED, (code,), (), ())
            self._screen_results[record.screen_id] = result
            return result
        self._safe_count += 1
        if not current:
            result = ScreenAggregationResult(record.screen_id, record.screen_index, AggregationStatus.COMPLETED, (), (), ())
            self._screen_results[record.screen_id] = result
            return result
        validated_identity = (record.screen_id, record.screen_index)
        warnings: list[str] = []
        boundary_uncertain_ids: set[str] = set()
        evidence: list[OcrSegmentMatchEvidence] = []
        remaining = current
        try:
            exact = _find_exact_boundary_overlap_validated(
                tuple(self._document),
                current,
                self._config,
                validated_identity,
            )
            if exact.accepted:
                self._document = list(apply_exact_boundary_occurrences(self._document, exact))
                remaining = tuple(item for item in current if item.segment_id in exact.remaining_current_segment_ids)
                evidence.extend(exact.match_evidence)
                self._matched_count += len(exact.matched_current_segment_ids)
            elif exact.uncertain_current_segment_ids:
                warnings.append("screen_aggregation_partial")
                boundary_uncertain_ids.update(exact.uncertain_current_segment_ids)
        except Exception:
            return self._append_uncertain_validated(
                record, current, "exact_stage_failed",
            )
        if remaining and not evidence:
            try:
                fuzzy = _find_fuzzy_boundary_overlap_validated(
                    tuple(self._document),
                    remaining,
                    self._config,
                    validated_identity,
                )
                if fuzzy.accepted:
                    self._document = list(apply_fuzzy_boundary_occurrences(self._document, fuzzy))
                    remaining = tuple(item for item in remaining if item.segment_id in fuzzy.remaining_current_segment_ids)
                    evidence.extend(fuzzy.match_evidence)
                    self._matched_count += len(fuzzy.matched_current_segment_ids)
                elif fuzzy.uncertain_current_segment_ids:
                    warnings.append("screen_aggregation_partial")
                    boundary_uncertain_ids.update(fuzzy.uncertain_current_segment_ids)
            except Exception:
                return self._append_uncertain_validated(
                    record, remaining, "fuzzy_stage_failed",
                )
        historical = None
        historical_input = tuple(
            item for item in remaining
            if item.segment_id not in boundary_uncertain_ids
        )
        if historical_input:
            try:
                historical = _classify_historical_duplicates_validated(
                    tuple(self._document), historical_input, self._index,
                    self._config, match_order_offset=len(evidence),
                    identity=validated_identity,
                )
                if historical.accepted:
                    self._document = list(apply_historical_occurrences(self._document, historical))
                    evidence.extend(historical.match_evidence)
                    self._matched_count += len(historical.matched_current_segment_ids)
                warnings.extend(historical.warning_codes)
            except Exception:
                return self._append_uncertain_validated(
                record, remaining, "historical_stage_failed",
                    evidence=evidence,
                )
        uncertain_ids = boundary_uncertain_ids | set(historical.uncertain_current_segment_ids if historical else ())
        if historical:
            appendable = tuple(item for item in remaining if item.segment_id not in historical.matched_current_segment_ids)
        else:
            appendable = remaining
        uncertain_segments = tuple(item for item in appendable if item.segment_id in uncertain_ids)
        new_segments = tuple(item for item in appendable if item.segment_id not in uncertain_ids)
        appended = self._append(uncertain_segments, AggregationOccurrenceRole.UNCERTAIN_ORIGIN)
        appended += self._append(new_segments, AggregationOccurrenceRole.ORIGIN)
        self._uncertain_count += len(uncertain_segments)
        self._evidence.extend(evidence)
        for warning in warnings:
            self._warn(warning)
        status = AggregationStatus.PARTIAL if warnings or uncertain_segments else AggregationStatus.COMPLETED
        result = ScreenAggregationResult(
            record.screen_id, record.screen_index, status,
            tuple(dict.fromkeys(warnings)), tuple(evidence), appended,
            tuple(item.segment_id for item in current if item.segment_id in {
                identifier for item in evidence for identifier in item.current_segment_ids
            }),
            tuple(item.segment_id for item in new_segments),
            tuple(item.segment_id for item in uncertain_segments),
        )
        self._screen_results[record.screen_id] = result
        return result

    def finalize(self, capture_status: CaptureStatus) -> CandidateAggregationResult:
        try:
            status = CaptureStatus(capture_status)
        except (TypeError, ValueError) as exc:
            raise AggregationInvariantError("capture_status_invalid") from exc
        if self._final_result is not None:
            if status != self._final_capture_status:
                raise CandidateAggregationFinalizeConflictError("capture status conflicts with finalized aggregation")
            return self._final_result
        if not self._formal_count:
            build_status, text, segments = DocumentBuildStatus.NOT_ATTEMPTED, None, ()
            self._warn("no_formal_screen")
        elif not self._safe_count:
            build_status, text, segments = DocumentBuildStatus.FAILED, None, ()
        else:
            segments = tuple(self._document)
            text = build_document_text(segments)
            build_status = DocumentBuildStatus.PARTIAL if self._partial or status in (CaptureStatus.ABORTED, CaptureStatus.INTERRUPTED) else DocumentBuildStatus.COMPLETED
            if status == CaptureStatus.ABORTED:
                self._warn("candidate_aborted")
                build_status = DocumentBuildStatus.PARTIAL
            elif status == CaptureStatus.INTERRUPTED:
                self._warn("candidate_interrupted")
                build_status = DocumentBuildStatus.PARTIAL
        risk = AggregationDuplicateRisk.ELEVATED if self._partial or self._uncertain_count else (AggregationDuplicateRisk.LOW if any(item.match_type in (AggregationMatchType.ADJACENT_FUZZY_1_1, AggregationMatchType.ADJACENT_FUZZY_1_2, AggregationMatchType.ADJACENT_FUZZY_2_1) for item in self._evidence) else AggregationDuplicateRisk.NONE)
        self._final_capture_status = status
        self._final_result = CandidateAggregationResult(
            self._run_id, self._candidate_record_id, tuple(segments), text, build_status,
            tuple(self._warnings), risk,
            CandidateAggregationSummary(self._formal_count, len(segments), self._matched_count, self._uncertain_count),
            tuple(self._evidence))
        # The frozen result owns its evidence; discard candidate-local inputs/index.
        self._screens.clear(); self._screen_results.clear(); self._formal_indexes.clear(); self._index.clear(); self._document.clear()
        return self._final_result
