"""Pure, deterministic R06 similarity primitives without online integration."""

from collections import Counter
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
import re
import unicodedata
from typing import Any, Mapping, Optional, Tuple

from ocr_records import (
    AggregationStatus,
    CaptureType,
    ComparisonClass,
    EffectiveNewStatus,
    EffectiveDecision,
    EffectiveNewDecision,
    NgramScore,
    NormalizationStatus,
    OcrSimilarityResult,
    OcrScreenRecord,
    R06_STORAGE_SCHEMA_VERSION,
    R06CandidateSummary,
    ReferenceResolution,
    ReferenceResolutionStatus,
    ReferenceSource,
    SIMILARITY_WARNING_CODES,
    SimilarityStatus,
    STORAGE_SCHEMA_VERSION,
)
from ocr_aggregation import aggregation_char_count
from ocr_normalization import protect_comparison_tokens


SIMILARITY_VERSION = "r06-v1"
SIMILARITY_CONFIG_VERSION = "r06-config-v1"
BUSINESS_SHORT_TERMS_VERSION = "r06-business-short-v1"
R06_SIMILARITY_MODE = "record"
R06_COMPAT_SCHEMA_VERSIONS = (
    R06_STORAGE_SCHEMA_VERSION,
    STORAGE_SCHEMA_VERSION,
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_SIMHASH_DOMAIN_PREFIX = b"r06-simhash-3gram-v1\0"


def _finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _warning_codes(*codes: str) -> Tuple[str, ...]:
    selected = set(codes)
    return tuple(code for code in SIMILARITY_WARNING_CODES if code in selected)


@dataclass(frozen=True)
class OcrSimilarityConfig:
    similarity_version: str = SIMILARITY_VERSION
    similarity_config_version: str = SIMILARITY_CONFIG_VERSION
    ngram_sizes: Tuple[int, ...] = (2, 3, 4)
    ngram_weights: Tuple[float, ...] = (0.20, 0.30, 0.50)
    primary_similarity_metric: str = "weighted_multiset_dice"
    simhash_bit_count: int = 64
    simhash_ngram_size: int = 3
    simhash_feature_hash_algorithm: str = "sha256_first_8_bytes_big_endian"
    simhash_domain_prefix: str = "r06-simhash-3gram-v1"
    high_similarity_threshold: float = 0.85
    effective_min_confidence: float = 0.85
    low_confidence_delta: float = 0.03
    low_confidence_max_chars: int = 2
    business_short_terms: Tuple[str, ...] = (
        "SLG", "UE5", "3D", "C++", "C#", ".NET", "Unity", "主美", "UI", "TA", "3A", "0-1", "2D/3D",
    )
    business_short_terms_version: str = BUSINESS_SHORT_TERMS_VERSION
    ui_min_formal_screen_occurrences: int = 3
    ui_center_tolerance_min_px: float = 8.0
    ui_center_tolerance_height_ratio: float = 0.5
    ui_min_size_similarity: float = 0.90
    floating_point_tolerance: float = 1e-12
    max_comparison_text_length: int = 100000
    max_formal_screens: int = 8

    def __post_init__(self) -> None:
        if self.similarity_version != SIMILARITY_VERSION or self.similarity_config_version != SIMILARITY_CONFIG_VERSION:
            raise ValueError("unsupported similarity config identity")
        if not isinstance(self.ngram_sizes, tuple) or not isinstance(self.ngram_weights, tuple) or not isinstance(self.business_short_terms, tuple):
            raise ValueError("similarity configuration collections must be tuples")
        if not self.ngram_sizes or len(self.ngram_sizes) != len(self.ngram_weights):
            raise ValueError("ngram sizes and weights are invalid")
        if any(not _positive_int(value) for value in self.ngram_sizes) or len(set(self.ngram_sizes)) != len(self.ngram_sizes):
            raise ValueError("ngram sizes must be unique positive integers")
        if any(not _finite_number(value) or float(value) < 0.0 for value in self.ngram_weights) or not any(float(value) > 0.0 for value in self.ngram_weights):
            raise ValueError("ngram weights are invalid")
        if self.primary_similarity_metric != "weighted_multiset_dice":
            raise ValueError("primary similarity metric is invalid")
        if self.simhash_bit_count != 64 or self.simhash_ngram_size != 3:
            raise ValueError("SimHash parameters are invalid")
        if self.simhash_feature_hash_algorithm != "sha256_first_8_bytes_big_endian" or self.simhash_domain_prefix != "r06-simhash-3gram-v1":
            raise ValueError("SimHash identity is invalid")
        bounded = (
            self.high_similarity_threshold, self.effective_min_confidence,
            self.ui_min_size_similarity,
        )
        if any(not _finite_number(value) or not 0.0 <= float(value) <= 1.0 for value in bounded):
            raise ValueError("similarity threshold is invalid")
        if not _finite_number(self.low_confidence_delta) or not 0.0 <= float(self.low_confidence_delta) <= 1.0 or not _positive_int(self.low_confidence_max_chars):
            raise ValueError("low-confidence parameters are invalid")
        if not self.business_short_terms_version or not self.business_short_terms or any(not isinstance(term, str) or not term for term in self.business_short_terms):
            raise ValueError("business short terms are invalid")
        if self.ui_min_formal_screen_occurrences < 3 or not _finite_number(self.ui_center_tolerance_min_px) or float(self.ui_center_tolerance_min_px) < 0.0 or not _finite_number(self.ui_center_tolerance_height_ratio) or float(self.ui_center_tolerance_height_ratio) < 0.0:
            raise ValueError("UI evidence parameters are invalid")
        if not _finite_number(self.floating_point_tolerance) or float(self.floating_point_tolerance) < 0.0 or not _positive_int(self.max_comparison_text_length) or not _positive_int(self.max_formal_screens) or self.max_formal_screens > 8 or self.ui_min_formal_screen_occurrences > self.max_formal_screens:
            raise ValueError("similarity bounds are invalid")

    def business_short_terms_digest(self) -> str:
        payload = {
            "business_short_terms": list(self.business_short_terms),
            "business_short_terms_version": self.business_short_terms_version,
        }
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


DEFAULT_OCR_SIMILARITY_CONFIG = OcrSimilarityConfig()


def _canonical_json(snapshot: Mapping[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_similarity_config(config: OcrSimilarityConfig) -> dict[str, Any]:
    if not isinstance(config, OcrSimilarityConfig):
        raise TypeError("similarity config has an invalid contract")
    snapshot = asdict(config)
    snapshot["ngram_sizes"] = list(config.ngram_sizes)
    snapshot["ngram_weights"] = list(config.ngram_weights)
    snapshot["business_short_terms"] = list(config.business_short_terms)
    snapshot["business_short_terms_digest"] = config.business_short_terms_digest()
    return snapshot


def similarity_config_digest(config_or_snapshot: Any) -> str:
    snapshot = canonical_similarity_config(config_or_snapshot) if isinstance(config_or_snapshot, OcrSimilarityConfig) else dict(config_or_snapshot)
    return hashlib.sha256(_canonical_json(snapshot).encode("utf-8")).hexdigest()


def similarity_config_from_snapshot(snapshot: Any) -> OcrSimilarityConfig:
    if not isinstance(snapshot, dict):
        raise ValueError("similarity config snapshot must be an object")
    expected = set(canonical_similarity_config(DEFAULT_OCR_SIMILARITY_CONFIG))
    if set(snapshot) != expected:
        raise ValueError("similarity config snapshot fields are incomplete")
    values = dict(snapshot)
    digest = values.pop("business_short_terms_digest")
    values["ngram_sizes"] = tuple(values["ngram_sizes"])
    values["ngram_weights"] = tuple(values["ngram_weights"])
    values["business_short_terms"] = tuple(values["business_short_terms"])
    try:
        config = OcrSimilarityConfig(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError("similarity config snapshot is invalid") from exc
    if digest != config.business_short_terms_digest():
        raise ValueError("similarity business terms digest mismatch")
    return config


def _is_formal(record: OcrScreenRecord) -> bool:
    return record.capture_type == CaptureType.FORMAL_SCREEN and record.is_formal_screen is True


def _unavailable(source: ReferenceSource, *warnings: str) -> ReferenceResolution:
    return ReferenceResolution(
        ReferenceResolutionStatus.UNAVAILABLE, None, None, None, source,
        _warning_codes(*warnings),
    )


def resolve_reference(
    current: OcrScreenRecord,
    candidate_screens_by_id: Mapping[str, OcrScreenRecord],
    formal_screen_id_by_index: Mapping[int, str],
    *,
    explicit_reference_screen_id: Optional[str],
    source_schema_version: str,
) -> ReferenceResolution:
    """Resolve only the frozen R06 reference relation; this function has no I/O."""
    records = tuple(candidate_screens_by_id.values())
    if any(key != record.screen_id for key, record in candidate_screens_by_id.items()):
        return _unavailable(ReferenceSource.FORMAL_PREVIOUS_INDEX, "duplicate_screen_id_conflict")
    if _is_formal(current):
        if current.screen_index == 1:
            return ReferenceResolution(ReferenceResolutionStatus.NO_REFERENCE, None, None, None, ReferenceSource.NONE)
        if not isinstance(current.screen_index, int) or current.screen_index <= 1:
            return _unavailable(ReferenceSource.FORMAL_PREVIOUS_INDEX, "reference_index_invalid")
        target_index = current.screen_index - 1
        target_id = formal_screen_id_by_index.get(target_index)
        targets = tuple(record for record in records if _is_formal(record) and record.screen_index == target_index)
        source = ReferenceSource.FORMAL_PREVIOUS_INDEX if source_schema_version in R06_COMPAT_SCHEMA_VERSIONS else ReferenceSource.RECONSTRUCTED_FORMAL_INDEX
        if target_id is None or len(targets) != 1 or targets[0].screen_id != target_id:
            return _unavailable(source, "reference_missing" if not targets else "reference_conflict")
        target = targets[0]
        if target.run_id != current.run_id:
            return _unavailable(source, "reference_run_mismatch")
        if target.candidate_record_id != current.candidate_record_id:
            return _unavailable(source, "reference_candidate_mismatch")
        return ReferenceResolution(ReferenceResolutionStatus.RESOLVED, target.screen_id, target.screen_index, target.capture_type, source)
    if source_schema_version not in R06_COMPAT_SCHEMA_VERSIONS and explicit_reference_screen_id is None:
        return _unavailable(ReferenceSource.EXPLICIT_RECORD, "legacy_reference_unavailable")
    if not explicit_reference_screen_id:
        return _unavailable(ReferenceSource.EXPLICIT_RECORD, "reference_missing")
    target = candidate_screens_by_id.get(explicit_reference_screen_id)
    if target is None:
        return _unavailable(ReferenceSource.EXPLICIT_RECORD, "reference_missing")
    if target.run_id != current.run_id:
        return _unavailable(ReferenceSource.EXPLICIT_RECORD, "reference_run_mismatch")
    if target.candidate_record_id != current.candidate_record_id:
        return _unavailable(ReferenceSource.EXPLICIT_RECORD, "reference_candidate_mismatch")
    valid_relation = (
        current.capture_type == CaptureType.SCROLL_CONFIRMATION and _is_formal(target) and target.screen_index == current.screen_index
    ) or (
        current.capture_type == CaptureType.LOAD_RETRY and target.capture_type in (CaptureType.LOAD_CHECK, CaptureType.LOAD_RETRY) and target.attempt_index < current.attempt_index
    )
    if not valid_relation:
        return _unavailable(ReferenceSource.EXPLICIT_RECORD, "reference_capture_invalid")
    return ReferenceResolution(ReferenceResolutionStatus.RESOLVED, target.screen_id, target.screen_index, target.capture_type, ReferenceSource.EXPLICIT_RECORD)


def compare_r03_exact_hash(left: OcrScreenRecord, right: OcrScreenRecord) -> Tuple[Optional[bool], Tuple[str, ...]]:
    """Read and compare only persisted R03 hashes; never recompute or mutate them."""
    if not all(isinstance(record.exact_hash, str) and _SHA256_PATTERN.fullmatch(record.exact_hash) for record in (left, right)):
        return None, _warning_codes("exact_hash_unavailable")
    if left.fingerprint_version != "r03-v1" or right.fingerprint_version != "r03-v1" or left.fingerprint_version != right.fingerprint_version:
        return None, _warning_codes("fingerprint_version_mismatch")
    return left.exact_hash == right.exact_hash, ()


def _build_ngram_counter(text: str, n: int) -> Counter[Tuple[str, ...]]:
    """Build a character multiset without normalization or tokenization."""
    return Counter(zip(*(text[offset:] for offset in range(n))))


def compute_char_ngram_similarity(
    left_text: str,
    right_text: str,
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> Tuple[Optional[float], Tuple[NgramScore, ...], Tuple[str, ...]]:
    """Return the frozen weighted multiset-Dice score and auditable per-n scores."""
    if not isinstance(left_text, str) or not isinstance(right_text, str):
        raise TypeError("comparison texts must be strings")
    if not isinstance(config, OcrSimilarityConfig):
        raise TypeError("similarity config has an invalid contract")
    if len(left_text) > config.max_comparison_text_length or len(right_text) > config.max_comparison_text_length:
        return None, (), _warning_codes("comparison_text_too_long")
    if not left_text and not right_text:
        return 1.0, (), ()
    if not left_text or not right_text:
        return 0.0, (), ()

    weighted_scores = []
    ngram_scores = []
    for n, weight in zip(config.ngram_sizes, config.ngram_weights):
        left_counter = _build_ngram_counter(left_text, n)
        right_counter = left_counter if left_text == right_text else _build_ngram_counter(right_text, n)
        left_count = sum(left_counter.values())
        right_count = sum(right_counter.values())
        if left_count == 0 and right_count == 0:
            continue
        if left_count == 0 or right_count == 0:
            dice_score = 0.0
        else:
            intersection = sum(
                min(count, right_counter.get(feature, 0))
                for feature, count in left_counter.items()
            )
            dice_score = (2.0 * intersection) / (left_count + right_count)
        ngram_scores.append(NgramScore(n, float(weight), left_count, right_count, dice_score))
        weighted_scores.append((float(weight), dice_score))
    if not weighted_scores:
        return (1.0 if left_text == right_text else 0.0), (), ()
    total_weight = sum(weight for weight, _ in weighted_scores)
    score = sum(weight * dice for weight, dice in weighted_scores) / total_weight
    return min(1.0, max(0.0, score)), tuple(ngram_scores), ()


def _simhash_features(text: str, n: int):
    if not text:
        return ()
    if len(text) < n:
        return (text,)
    return zip(*(text[offset:] for offset in range(n)))


def compute_stable_simhash(
    comparison_text: str,
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> Optional[str]:
    """Return the TID-frozen 64-bit SimHash, or ``None`` for empty input."""
    if not isinstance(comparison_text, str):
        raise TypeError("comparison text must be a string")
    if not isinstance(config, OcrSimilarityConfig):
        raise TypeError("similarity config has an invalid contract")
    if not comparison_text or len(comparison_text) > config.max_comparison_text_length:
        return None
    votes = [0] * config.simhash_bit_count
    for feature, occurrence_count in Counter(_simhash_features(comparison_text, config.simhash_ngram_size)).items():
        feature_text = "".join(feature) if isinstance(feature, tuple) else feature
        feature_hash = int.from_bytes(
            hashlib.sha256(_SIMHASH_DOMAIN_PREFIX + feature_text.encode("utf-8")).digest()[:8],
            "big",
        )
        for bit_index in range(config.simhash_bit_count):
            votes[bit_index] += occurrence_count if feature_hash & (1 << bit_index) else -occurrence_count
    value = sum(1 << bit_index for bit_index, vote in enumerate(votes) if vote > 0)
    return "{0:016x}".format(value)


def compute_simhash_similarity(
    left_text: str,
    right_text: str,
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[float]]:
    """Return both frozen SimHashes and their Hamming-derived auxiliary score."""
    left_hash = compute_stable_simhash(left_text, config)
    right_hash = compute_stable_simhash(right_text, config)
    if left_hash is None or right_hash is None:
        return left_hash, right_hash, None, None
    distance = (int(left_hash, 16) ^ int(right_hash, 16)).bit_count()
    return left_hash, right_hash, distance, 1.0 - distance / config.simhash_bit_count


@dataclass(frozen=True)
class PairSimilaritySignals:
    """Non-persisted Change 3 output; it deliberately has no comparison class."""

    exact_same: Optional[bool]
    similarity_score: Optional[float]
    ngram_scores: Tuple[NgramScore, ...]
    current_simhash: Optional[str]
    reference_simhash: Optional[str]
    simhash_hamming_distance: Optional[int]
    simhash_similarity_score: Optional[float]
    warning_codes: Tuple[str, ...]


def compute_pair_similarity_signals(
    current: OcrScreenRecord,
    reference: OcrScreenRecord,
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> PairSimilaritySignals:
    """Compute only R03 exact and R04 text pair signals; no R05/classification work."""
    if not isinstance(current, OcrScreenRecord) or not isinstance(reference, OcrScreenRecord):
        raise TypeError("similarity inputs must be screen records")
    exact_same, exact_warnings = compare_r03_exact_hash(current, reference)
    if (
        current.normalization_status != NormalizationStatus.COMPLETED
        or reference.normalization_status != NormalizationStatus.COMPLETED
        or not isinstance(current.comparison_text, str)
        or not isinstance(reference.comparison_text, str)
    ):
        return PairSimilaritySignals(exact_same, None, (), None, None, None, None, _warning_codes(*exact_warnings, "r04_not_completed"))
    similarity_score, ngram_scores, ngram_warnings = compute_char_ngram_similarity(current.comparison_text, reference.comparison_text, config)
    if ngram_warnings:
        return PairSimilaritySignals(
            exact_same, similarity_score, ngram_scores, None, None, None, None,
            _warning_codes(*exact_warnings, *ngram_warnings),
        )
    current_hash, reference_hash, distance, simhash_score = compute_simhash_similarity(current.comparison_text, reference.comparison_text, config)
    return PairSimilaritySignals(
        exact_same, similarity_score, ngram_scores, current_hash, reference_hash,
        distance, simhash_score, _warning_codes(*exact_warnings, *ngram_warnings),
    )


@dataclass(frozen=True)
class R05AccountingResult:
    """Pure R06 accounting derived only from the persisted R05 partition."""

    is_verifiable: bool
    overlap_char_count: Optional[int] = None
    new_char_count: Optional[int] = None
    uncertain_char_count: Optional[int] = None
    current_effective_char_count: Optional[int] = None
    overlap_segment_count: Optional[int] = None
    new_segment_count: Optional[int] = None
    uncertain_segment_count: Optional[int] = None
    current_effective_segment_count: Optional[int] = None
    overlap_ratio_numerator: Optional[int] = None
    overlap_ratio_denominator: Optional[int] = None
    overlap_ratio: Optional[float] = None
    new_text_ratio_numerator: Optional[int] = None
    new_text_ratio_denominator: Optional[int] = None
    new_text_ratio: Optional[float] = None
    uncertain_ratio_numerator: Optional[int] = None
    uncertain_ratio_denominator: Optional[int] = None
    uncertain_ratio: Optional[float] = None
    warning_codes: Tuple[str, ...] = ()


_ACCOUNTING_FIELDS = (
    "overlap_char_count", "new_char_count", "uncertain_char_count",
    "current_effective_char_count", "overlap_segment_count", "new_segment_count",
    "uncertain_segment_count", "current_effective_segment_count",
    "overlap_ratio_numerator", "overlap_ratio_denominator", "overlap_ratio",
    "new_text_ratio_numerator", "new_text_ratio_denominator", "new_text_ratio",
    "uncertain_ratio_numerator", "uncertain_ratio_denominator", "uncertain_ratio",
)


def _unverifiable_accounting(*warnings: str) -> R05AccountingResult:
    return R05AccountingResult(False, warning_codes=_warning_codes(*warnings))


def compute_r05_accounting(
    current: OcrScreenRecord,
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> R05AccountingResult:
    """Recompute counts from R05 IDs, and reject rather than repair any discrepancy."""
    if not isinstance(current, OcrScreenRecord):
        raise TypeError("accounting input must be a screen record")
    if not isinstance(config, OcrSimilarityConfig):
        raise TypeError("similarity config has an invalid contract")
    if current.aggregation_status == AggregationStatus.NOT_ATTEMPTED:
        return _unverifiable_accounting("r05_not_attempted")
    if current.aggregation_status == AggregationStatus.FAILED:
        return _unverifiable_accounting("r05_failed")
    if current.aggregation_status not in (AggregationStatus.COMPLETED, AggregationStatus.PARTIAL):
        return _unverifiable_accounting("r05_not_attempted")

    warnings = ["r05_partial"] if current.aggregation_status == AggregationStatus.PARTIAL else []
    segments = current.segments
    segment_ids = tuple(segment.segment_id for segment in segments)
    if len(set(segment_ids)) != len(segment_ids):
        return _unverifiable_accounting(*warnings, "segment_partition_invalid")
    segment_by_id = {segment.segment_id: segment for segment in segments}
    groups = (
        current.matched_segment_ids,
        current.new_segment_ids,
        current.uncertain_segment_ids,
    )
    grouped_ids = tuple(identifier for group in groups for identifier in group)
    if (
        any(not isinstance(identifier, str) for identifier in grouped_ids)
        or len(set(grouped_ids)) != len(grouped_ids)
        or set(grouped_ids) != set(segment_ids)
        or any(
            group != tuple(
                identifier for identifier in segment_ids if identifier in set(group)
            )
            for group in groups
        )
    ):
        return _unverifiable_accounting(*warnings, "segment_partition_invalid")

    try:
        counts = {
            identifier: aggregation_char_count(segment_by_id[identifier].comparison_text)
            for identifier in segment_ids
        }
    except Exception:
        return _unverifiable_accounting(*warnings, "accounting_mismatch")
    overlap_ids, new_ids, uncertain_ids = groups
    overlap_chars = sum(counts[identifier] for identifier in overlap_ids)
    new_chars = sum(counts[identifier] for identifier in new_ids)
    uncertain_chars = sum(counts[identifier] for identifier in uncertain_ids)
    current_chars = sum(counts.values())
    overlap_segments, new_segments, uncertain_segments = map(len, groups)
    current_segments = len(segments)

    projection_matches = (
        current.overlap_char_count == overlap_chars
        and current.new_text_char_count == new_chars + uncertain_chars
        and current.uncertain_char_count == uncertain_chars
        and current.overlap_segment_count == overlap_segments
        and current.new_segment_count == new_segments + uncertain_segments
        and current.certain_new_segment_count == new_segments
        and current.uncertain_segment_count == uncertain_segments
    )
    if not projection_matches:
        warnings.append("r05_projection_mismatch")
    totals_match = (
        overlap_chars + new_chars + uncertain_chars == current_chars
        and overlap_segments + new_segments + uncertain_segments == current_segments
    )
    if not totals_match:
        warnings.append("accounting_mismatch")
    if not projection_matches or not totals_match:
        return _unverifiable_accounting(*warnings)

    if current_chars == 0:
        return R05AccountingResult(
            True, overlap_chars, new_chars, uncertain_chars, 0,
            overlap_segments, new_segments, uncertain_segments, current_segments,
            0, 0, None, 0, 0, None, 0, 0, None,
            _warning_codes(*warnings, "zero_effective_char_denominator"),
        )
    denominator = current_chars
    ratios = (overlap_chars / denominator, new_chars / denominator, uncertain_chars / denominator)
    if (
        any(not 0.0 <= ratio <= 1.0 for ratio in ratios)
        or abs(sum(ratios) - 1.0) > config.floating_point_tolerance
    ):
        return _unverifiable_accounting(*warnings, "accounting_mismatch")
    return R05AccountingResult(
        True, overlap_chars, new_chars, uncertain_chars, current_chars,
        overlap_segments, new_segments, uncertain_segments, current_segments,
        overlap_chars, denominator, ratios[0], new_chars, denominator, ratios[1],
        uncertain_chars, denominator, ratios[2], _warning_codes(*warnings),
    )


def apply_r05_accounting(
    result: OcrSimilarityResult,
    accounting: R05AccountingResult,
) -> OcrSimilarityResult:
    """Project independently recomputed R05 accounting without changing R05 evidence."""
    if not isinstance(result, OcrSimilarityResult) or not isinstance(accounting, R05AccountingResult):
        raise TypeError("similarity accounting projection has an invalid contract")
    warnings = _warning_codes(*result.warning_codes, *accounting.warning_codes)
    if not accounting.is_verifiable:
        status = result.similarity_status
        if status not in (SimilarityStatus.FAILED, SimilarityStatus.UNAVAILABLE, SimilarityStatus.NO_REFERENCE):
            status = SimilarityStatus.PARTIAL
        return replace(
            result, similarity_status=status, comparison_class=ComparisonClass.UNCERTAIN,
            effective_new_status=EffectiveNewStatus.UNAVAILABLE,
            **{field: None for field in _ACCOUNTING_FIELDS}, warning_codes=warnings,
        )
    values = {field: getattr(accounting, field) for field in _ACCOUNTING_FIELDS}
    status = result.similarity_status
    comparison_class = result.comparison_class
    if status == SimilarityStatus.NOT_ATTEMPTED:
        status, comparison_class = SimilarityStatus.PARTIAL, ComparisonClass.UNCERTAIN
    if "r05_partial" in accounting.warning_codes and status == SimilarityStatus.COMPLETED:
        status, comparison_class = SimilarityStatus.PARTIAL, ComparisonClass.UNCERTAIN
    if "zero_effective_char_denominator" in accounting.warning_codes:
        comparison_class = ComparisonClass.EMPTY_OR_UNAVAILABLE
    return replace(result, similarity_status=status, comparison_class=comparison_class, **values, warning_codes=warnings)


_YEAR_RE = re.compile(r"(?:19|20)\d{2}年?\Z")
_DATE_RE = re.compile(r"(?:19|20)\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?\Z")
_RANGE_RE = re.compile(r"\d+(?:[-~–—]\d+)+(?:年|月|天|小时|h|%)?\Z")
_VERSION_RE = re.compile(r"(?:v|version)?\d+(?:\.\d+){1,}(?:[-+._][a-z0-9]+)?\Z", re.I)


def _segment_source_boxes(record: OcrScreenRecord, segment_id: str):
    segment = next((item for item in record.segments if item.segment_id == segment_id), None)
    if segment is None:
        return None, ()
    by_id = {box.box_id: box for box in record.raw_boxes}
    if not segment.ocr_box_ids or any(identifier not in by_id for identifier in segment.ocr_box_ids):
        return segment, ()
    return segment, tuple(by_id[identifier] for identifier in segment.ocr_box_ids)


def _has_protected_content(segment_text: str, normalized_text: str, config: OcrSimilarityConfig) -> bool:
    canonical_terms = {term.casefold() for term in config.business_short_terms}
    if segment_text.casefold() in canonical_terms or normalized_text.casefold() in canonical_terms:
        return True
    if _YEAR_RE.fullmatch(segment_text) or _DATE_RE.fullmatch(segment_text) or _RANGE_RE.fullmatch(segment_text) or _VERSION_RE.fullmatch(segment_text):
        return True
    return any(part.is_protected_token for part in protect_comparison_tokens(normalized_text))


def _format_only(text: str, normalized_text: str, config: OcrSimilarityConfig) -> bool:
    if not text or _has_protected_content(text, normalized_text, config):
        return False
    return all(unicodedata.category(character)[0] in ("P", "Z", "C") for character in text)


def _duplicate_artifact(record: OcrScreenRecord, segment_id: str) -> bool:
    segment, boxes = _segment_source_boxes(record, segment_id)
    if segment is None or not boxes:
        return False
    source_ids = {box.box_id for box in boxes}
    for group in record.duplicate_groups:
        if not source_ids.intersection(group.source_box_ids):
            continue
        if not group.pair_evidence or not group.suppressed_duplicate_box_ids:
            continue
        if all(pair.text_exact and pair.decision == "duplicate" for pair in group.pair_evidence):
            return True
    return False


def _low_confidence_noise(record: OcrScreenRecord, segment_id: str, config: OcrSimilarityConfig) -> bool:
    segment, boxes = _segment_source_boxes(record, segment_id)
    if segment is None or len(record.new_segment_ids) != 1 or len(boxes) != 1:
        return False
    box = boxes[0]
    if box.confidence is None or not config.effective_min_confidence <= box.confidence <= config.effective_min_confidence + config.low_confidence_delta:
        return False
    if aggregation_char_count(segment.comparison_text) > config.low_confidence_max_chars:
        return False
    if _has_protected_content(segment.comparison_text, segment.normalized_text, config):
        return False
    return not any(character.isalpha() or character.isdigit() or "\u4e00" <= character <= "\u9fff" for character in segment.comparison_text)


@dataclass(frozen=True)
class EffectiveNewEvaluation:
    status: EffectiveNewStatus
    decisions: Tuple[EffectiveNewDecision, ...]
    effective_segment_count: Optional[int]
    ineffective_segment_count: Optional[int]
    possible_segment_count: Optional[int]
    effective_char_count: Optional[int]
    possible_char_count: Optional[int]
    has_effective_new_text: Optional[bool]
    warning_codes: Tuple[str, ...]


class CandidateSimilarityEvaluator:
    """Bounded, candidate-isolated context for R06 UI evidence; no I/O or diff."""

    def __init__(self, run_id: str, candidate_record_id: str, config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG) -> None:
        if not run_id or not candidate_record_id or not isinstance(config, OcrSimilarityConfig):
            raise ValueError("candidate similarity context is invalid")
        self._run_id, self._candidate_record_id, self._config = run_id, candidate_record_id, config
        self._formal = []
        self._by_text = {}

    def add_screen(self, record: OcrScreenRecord) -> None:
        if record.run_id != self._run_id or record.candidate_record_id != self._candidate_record_id:
            raise ValueError("candidate similarity context identity mismatch")
        if record.capture_type != CaptureType.FORMAL_SCREEN or record.is_formal_screen is not True:
            return
        if len(self._formal) >= self._config.max_formal_screens:
            return
        self._formal.append(record)
        for segment in record.segments:
            _, boxes = _segment_source_boxes(record, segment.segment_id)
            if boxes:
                self._by_text.setdefault(segment.comparison_text, []).append((record.screen_id, boxes[0]))

    def fork(self) -> "CandidateSimilarityEvaluator":
        """Copy mutable candidate indexes while sharing frozen OCR records."""

        clone = object.__new__(type(self))
        clone.__dict__ = self.__dict__.copy()
        clone._formal = list(self._formal)
        clone._by_text = {
            key: list(values) for key, values in self._by_text.items()
        }
        return clone

    def ui_noise(self, record: OcrScreenRecord, segment_id: str, protected: bool) -> Tuple[bool, bool]:
        """Return (proved_noise, evidence_insufficient), using exact-text index only."""
        segment, boxes = _segment_source_boxes(record, segment_id)
        if segment is None or not boxes or protected:
            return False, not protected
        entries = self._by_text.get(segment.comparison_text, ())
        unique = {screen_id: box for screen_id, box in entries}
        if len(unique) < self._config.ui_min_formal_screen_occurrences:
            return False, len(unique) >= 2
        # Geometry is intentionally checked against the first box per screen, never pairwise screens.
        dimensions = []
        for box in unique.values():
            try:
                xs = [point[0] for point in box.bbox]; ys = [point[1] for point in box.bbox]
                width, height = max(xs) - min(xs), max(ys) - min(ys)
                dimensions.append(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, width, height))
            except (TypeError, ValueError, IndexError):
                return False, True
        heights = sorted(item[3] for item in dimensions)
        median_height = heights[len(heights) // 2]
        center_x = sum(item[0] for item in dimensions) / len(dimensions)
        center_y = sum(item[1] for item in dimensions) / len(dimensions)
        tolerance = max(self._config.ui_center_tolerance_min_px, self._config.ui_center_tolerance_height_ratio * median_height)
        if any(math.hypot(item[0] - center_x, item[1] - center_y) > tolerance for item in dimensions):
            return False, True
        baseline = dimensions[0]
        if baseline[2] <= 0 or baseline[3] <= 0 or any(min(item[2] / baseline[2], baseline[2] / item[2], item[3] / baseline[3], baseline[3] / item[3]) < self._config.ui_min_size_similarity for item in dimensions):
            return False, True
        return True, False

    def clear(self) -> None:
        self._formal.clear(); self._by_text.clear()

    def evaluate(
        self,
        current: OcrScreenRecord,
        candidate_screens_by_id: Mapping[str, OcrScreenRecord],
        formal_screen_id_by_index: Mapping[int, str],
        *,
        explicit_reference_screen_id: Optional[str] = None,
        source_schema_version: str = STORAGE_SCHEMA_VERSION,
    ) -> OcrSimilarityResult:
        """Evaluate one final R05-projected screen exactly once.

        The builder owns when this method is called.  This context only keeps
        bounded, candidate-local UI evidence and never performs I/O.
        """

        resolution = resolve_reference(
            current,
            candidate_screens_by_id,
            formal_screen_id_by_index,
            explicit_reference_screen_id=explicit_reference_screen_id,
            source_schema_version=source_schema_version,
        )
        reference = (
            candidate_screens_by_id.get(resolution.reference_screen_id)
            if resolution.status == ReferenceResolutionStatus.RESOLVED
            else None
        )
        # Include the current formal screen while evaluating its UI evidence,
        # but publish that state only when the one R06 pass completes.  A
        # failed pass must not influence a later screen.
        formal_before = list(self._formal)
        by_text_before = {
            key: list(values) for key, values in self._by_text.items()
        }
        try:
            self.add_screen(current)
            return evaluate_screen_similarity(
                current,
                reference,
                resolution,
                self,
                self._config,
            )
        except Exception:
            self._formal = formal_before
            self._by_text = by_text_before
            raise


def _result_identity(config: OcrSimilarityConfig) -> dict[str, Optional[str]]:
    return {
        "similarity_version": config.similarity_version,
        "similarity_config_version": config.similarity_config_version,
        "similarity_config_digest": similarity_config_digest(config),
    }


def _base_similarity_result(
    resolution: ReferenceResolution,
    config: OcrSimilarityConfig,
    *,
    status: SimilarityStatus,
    reference: Optional[OcrScreenRecord] = None,
    warning_codes: Tuple[str, ...] = (),
) -> OcrSimilarityResult:
    """Create the sole R06 nested-result authority without any projection."""

    return OcrSimilarityResult(
        similarity_status=status,
        reference_screen_id=resolution.reference_screen_id,
        reference_screen_index=resolution.reference_screen_index,
        reference_capture_type=resolution.reference_capture_type,
        reference_source=resolution.reference_source,
        reference_fingerprint_version=(
            reference.fingerprint_version if reference is not None else None
        ),
        reference_exact_hash=(reference.exact_hash if reference is not None else None),
        comparison_class=ComparisonClass.EMPTY_OR_UNAVAILABLE,
        warning_codes=_warning_codes(*resolution.warning_codes, *warning_codes),
        **_result_identity(config),
    )


def failed_similarity_result(
    resolution: ReferenceResolution,
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> OcrSimilarityResult:
    """Return the fixed, content-free fail-open view used by the builder."""

    return _base_similarity_result(
        resolution,
        config,
        status=SimilarityStatus.FAILED,
        warning_codes=("evaluation_failed",),
    )


def empty_similarity_summary(
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> R06CandidateSummary:
    """Build the legal record-mode summary for a candidate with zero screens."""

    identity = _result_identity(config)
    return R06CandidateSummary(
        **identity,
        screen_count=0,
        not_attempted_screen_count=0,
        completed_screen_count=0,
        partial_screen_count=0,
        failed_screen_count=0,
        unavailable_screen_count=0,
        no_reference_screen_count=0,
        exact_same_screen_count=0,
        high_similarity_with_effective_new_screen_count=0,
        high_similarity_without_effective_new_screen_count=0,
        changed_with_effective_new_screen_count=0,
        changed_without_effective_new_screen_count=0,
        empty_or_unavailable_screen_count=0,
        uncertain_screen_count=0,
        effective_present_screen_count=0,
        effective_possible_screen_count=0,
        effective_none_screen_count=0,
        effective_unavailable_screen_count=0,
        warning_count=0,
    )


def evaluate_screen_similarity(
    current: OcrScreenRecord,
    reference: Optional[OcrScreenRecord],
    resolution: ReferenceResolution,
    candidate_context: CandidateSimilarityEvaluator,
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> OcrSimilarityResult:
    """Compose frozen R03--R06 pure stages for one already-finalized screen.

    This function deliberately consumes the persisted R04/R05 projection.  It
    neither calls OCR nor rebuilds R04/R05, and is shared by online and replay
    callers.
    """

    if not isinstance(current, OcrScreenRecord):
        raise TypeError("similarity current record is invalid")
    if not isinstance(resolution, ReferenceResolution):
        raise TypeError("similarity reference resolution is invalid")
    if not isinstance(candidate_context, CandidateSimilarityEvaluator):
        raise TypeError("similarity candidate context is invalid")
    if not isinstance(config, OcrSimilarityConfig):
        raise TypeError("similarity config has an invalid contract")

    if resolution.status == ReferenceResolutionStatus.NO_REFERENCE:
        result = _base_similarity_result(
            resolution, config, status=SimilarityStatus.NO_REFERENCE
        )
    elif resolution.status == ReferenceResolutionStatus.UNAVAILABLE or reference is None:
        result = _base_similarity_result(
            resolution, config, status=SimilarityStatus.UNAVAILABLE
        )
    else:
        signals = compute_pair_similarity_signals(current, reference, config)
        status = (
            SimilarityStatus.UNAVAILABLE
            if "r04_not_completed" in signals.warning_codes
            else SimilarityStatus.PARTIAL
            if "comparison_text_too_long" in signals.warning_codes
            else SimilarityStatus.COMPLETED
        )
        result = replace(
            _base_similarity_result(
                resolution,
                config,
                status=status,
                reference=reference,
                warning_codes=signals.warning_codes,
            ),
            exact_same=signals.exact_same,
            similarity_score=signals.similarity_score,
            ngram_scores=signals.ngram_scores,
            current_simhash=signals.current_simhash,
            reference_simhash=signals.reference_simhash,
            simhash_hamming_distance=signals.simhash_hamming_distance,
            simhash_similarity_score=signals.simhash_similarity_score,
            comparison_class=(
                ComparisonClass.UNCERTAIN
                if status == SimilarityStatus.PARTIAL
                else ComparisonClass.EMPTY_OR_UNAVAILABLE
            ),
        )

    accounting = compute_r05_accounting(current, config)
    result = apply_r05_accounting(result, accounting)
    evaluation = evaluate_effective_new(current, candidate_context, config)
    return apply_effective_new(
        result,
        current,
        evaluation,
        reference=reference,
        config=config,
    )


def evaluate_effective_new(
    current: OcrScreenRecord,
    candidate_context: CandidateSimilarityEvaluator,
    config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG,
) -> EffectiveNewEvaluation:
    """Evaluate only R05 new/uncertain segments, with R05 partition as sole authority."""
    accounting = compute_r05_accounting(current, config)
    evidence_ids = {identifier for evidence in current.match_evidence for identifier in evidence.current_segment_ids}
    if not accounting.is_verifiable or evidence_ids.intersection(current.new_segment_ids + current.uncertain_segment_ids):
        warning = "segment_partition_invalid" if evidence_ids.intersection(current.new_segment_ids + current.uncertain_segment_ids) else accounting.warning_codes
        return EffectiveNewEvaluation(EffectiveNewStatus.UNAVAILABLE, (), None, None, None, None, None, None, _warning_codes(*((warning,) if isinstance(warning, str) else warning)))
    decisions = []
    warnings = []
    by_id = {item.segment_id: item for item in current.segments}
    for segment in current.segments:
        if segment.segment_id in current.uncertain_segment_ids:
            decisions.append(EffectiveNewDecision(segment.segment_id, "uncertain", EffectiveDecision.UNCERTAIN, "source_uncertain", ("r05_uncertain",)))
        elif segment.segment_id in current.new_segment_ids:
            protected = _has_protected_content(segment.comparison_text, segment.normalized_text, config)
            if _format_only(segment.comparison_text, segment.normalized_text, config):
                decisions.append(EffectiveNewDecision(segment.segment_id, "new", EffectiveDecision.INEFFECTIVE, "format_only", ("unicode_format_only",)))
            elif _duplicate_artifact(current, segment.segment_id):
                decisions.append(EffectiveNewDecision(segment.segment_id, "new", EffectiveDecision.INEFFECTIVE, "duplicate_artifact", ("r04_duplicate_geometry",)))
            elif _low_confidence_noise(current, segment.segment_id, config):
                decisions.append(EffectiveNewDecision(segment.segment_id, "new", EffectiveDecision.INEFFECTIVE, "low_confidence_noise", ("frozen_confidence_band",)))
            else:
                ui, insufficient = candidate_context.ui_noise(current, segment.segment_id, protected)
                if ui:
                    decisions.append(EffectiveNewDecision(segment.segment_id, "new", EffectiveDecision.INEFFECTIVE, "likely_repeated_ui_noise", ("three_formal_screens_geometry",)))
                elif protected:
                    decisions.append(EffectiveNewDecision(segment.segment_id, "new", EffectiveDecision.EFFECTIVE, "short_text_protected", ("protected_token",)))
                elif insufficient:
                    warnings.append("ui_evidence_insufficient")
                    decisions.append(EffectiveNewDecision(segment.segment_id, "new", EffectiveDecision.UNCERTAIN, "evidence_insufficient", ("ui_evidence_incomplete",)))
                elif any(character.isalpha() or character.isdigit() or "\u4e00" <= character <= "\u9fff" for character in segment.comparison_text):
                    decisions.append(EffectiveNewDecision(segment.segment_id, "new", EffectiveDecision.EFFECTIVE, "effective_content", ("structured_content",)))
                else:
                    decisions.append(EffectiveNewDecision(segment.segment_id, "new", EffectiveDecision.UNCERTAIN, "evidence_insufficient", ("insufficient_evidence",)))
    effective = tuple(item for item in decisions if item.decision == EffectiveDecision.EFFECTIVE)
    ineffective = tuple(item for item in decisions if item.decision == EffectiveDecision.INEFFECTIVE)
    possible = tuple(item for item in decisions if item.decision == EffectiveDecision.UNCERTAIN)
    status = EffectiveNewStatus.PRESENT if effective else EffectiveNewStatus.POSSIBLE if possible else EffectiveNewStatus.NONE
    chars = lambda items: sum(aggregation_char_count(by_id[item.segment_id].comparison_text) for item in items)
    return EffectiveNewEvaluation(status, tuple(decisions), len(effective), len(ineffective), len(possible), chars(effective), chars(possible), bool(effective), _warning_codes(*warnings))


def apply_effective_new(result: OcrSimilarityResult, current: OcrScreenRecord, evaluation: EffectiveNewEvaluation, *, reference: Optional[OcrScreenRecord] = None, config: OcrSimilarityConfig = DEFAULT_OCR_SIMILARITY_CONFIG) -> OcrSimilarityResult:
    """Project effective-new data and frozen neutral class; never changes R03/R04/R05."""
    if evaluation.status == EffectiveNewStatus.UNAVAILABLE:
        return replace(result, similarity_status=SimilarityStatus.PARTIAL if result.similarity_status == SimilarityStatus.COMPLETED else result.similarity_status, effective_new_status=evaluation.status, effective_new_decisions=(), effective_new_segment_count=None, ineffective_new_segment_count=None, possible_new_segment_count=None, effective_new_char_count=None, possible_new_char_count=None, has_effective_new_text=None, comparison_class=ComparisonClass.UNCERTAIN, warning_codes=_warning_codes(*result.warning_codes, *evaluation.warning_codes))
    warnings = _warning_codes(*result.warning_codes, *evaluation.warning_codes)
    conflict = result.exact_same is True and (reference is not None and reference.comparison_text != current.comparison_text or result.similarity_score is not None and abs(result.similarity_score - 1.0) > config.floating_point_tolerance or bool(current.new_segment_ids or current.uncertain_segment_ids))
    status = SimilarityStatus.PARTIAL if conflict and result.similarity_status == SimilarityStatus.COMPLETED else result.similarity_status
    if conflict: warnings = _warning_codes(*warnings, "cross_layer_similarity_conflict")
    if status in (SimilarityStatus.NO_REFERENCE, SimilarityStatus.UNAVAILABLE, SimilarityStatus.FAILED) or (reference is not None and (not current.comparison_text or not reference.comparison_text)):
        klass = ComparisonClass.EMPTY_OR_UNAVAILABLE
    elif conflict or evaluation.status in (EffectiveNewStatus.POSSIBLE, EffectiveNewStatus.UNAVAILABLE): klass = ComparisonClass.UNCERTAIN
    elif result.exact_same is True: klass = ComparisonClass.EXACT_SAME
    elif result.similarity_score is None: klass = ComparisonClass.UNCERTAIN
    elif result.similarity_score >= config.high_similarity_threshold: klass = ComparisonClass.HIGH_SIMILARITY_WITH_EFFECTIVE_NEW if evaluation.status == EffectiveNewStatus.PRESENT else ComparisonClass.HIGH_SIMILARITY_WITHOUT_EFFECTIVE_NEW
    else: klass = ComparisonClass.CHANGED_WITH_EFFECTIVE_NEW if evaluation.status == EffectiveNewStatus.PRESENT else ComparisonClass.CHANGED_WITHOUT_EFFECTIVE_NEW
    return replace(result, similarity_status=status, effective_new_status=evaluation.status, effective_new_decisions=evaluation.decisions, effective_new_segment_count=evaluation.effective_segment_count, ineffective_new_segment_count=evaluation.ineffective_segment_count, possible_new_segment_count=evaluation.possible_segment_count, effective_new_char_count=evaluation.effective_char_count, possible_new_char_count=evaluation.possible_char_count, has_effective_new_text=evaluation.has_effective_new_text, comparison_class=klass, warning_codes=warnings)
