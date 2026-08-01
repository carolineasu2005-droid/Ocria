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
            Callable[[ScanObservation, str, bool, Optional[int]], None]
        ] = None,
        normalization_config: OcrNormalizationConfig = (
            DEFAULT_OCR_NORMALIZATION_CONFIG
        ),
        rule_evaluation_mode: str = RULE_EVALUATION_MODE_LEGACY_SHADOW,
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
    ) -> None:
        """Notify optional stage-0 storage without affecting OCR behavior."""

        if self.observation_callback is None:
            return
        try:
            self.observation_callback(
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
        try:
            for scan_number in range(1, self.max_scans + 1):
                if scan_number > 1:
                    if self.scroll is None:
                        break
                    self.scroll()
                    self.wait(self.settle_seconds)

                if scan_number == 1 and first_observation is not None:
                    first = first_observation
                else:
                    first = self.capture_observation(scan_number)
                bind_fingerprint_screen_index(first, scan_number)
                first = self._match_observation(first, rules)
                observations.append(first)
                self._notify_observation(
                    first,
                    "formal_screen",
                    True,
                    scan_number,
                )
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
                    continue

                self.wait(self.confirmation_seconds)
                confirmation = self._observe(scan_number, [first.matched_rule])
                observations.append(confirmation)
                self._notify_observation(
                    confirmation,
                    "scroll_confirmation",
                    False,
                    scan_number,
                )
                confirmed = confirmation.matched_rule == first.matched_rule
                return DetectionResult(
                    success=True,
                    confirmed_match=confirmed,
                    matched_keyword=first.matched_keyword if confirmed else None,
                    scans_completed=scan_number,
                    observations=observations,
                    error=None if confirmed else "second OCR pass did not confirm the match",
                )

            return DetectionResult(
                success=True,
                confirmed_match=False,
                scans_completed=min(self.max_scans, len(observations)),
                observations=observations,
            )
        except Exception as exc:
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
            )
