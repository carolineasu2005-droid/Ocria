"""Current-candidate-only assembly for stage-0 OCR documents."""

from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union
from uuid import uuid4

from ocr_records import (
    NOT_IMPLEMENTED,
    CandidateOcrDocument,
    CaptureStatus,
    CaptureSummary,
    CaptureType,
    NormalizationStatus,
    OcrBox,
    OcrDuplicateGroup,
    OcrDuplicatePairEvidence,
    OcrLineMapping,
    OcrNormalizationWarning,
    OcrScreenRecord,
    OcrTextSegment,
    ProcessingStatus,
    timezone_iso,
    validate_timezone_iso,
    recompute_normalization_summary,
)
from ocr_normalization import (
    NORMALIZATION_COMPLETED,
    NORMALIZATION_FAILED,
    NORMALIZATION_VERSION,
    RAW_TEXT_SOURCE_DERIVED_BOXES,
    TextNormalizationResult,
    build_comparison_text,
)
from ocr_text import OCRItem


class CandidateBuilderFinalizedError(RuntimeError):
    """Raised when a finalized builder is used again."""


Timestamp = Union[str, datetime]


def _timestamp_text(value: Optional[Timestamp]) -> str:
    if value is None:
        return timezone_iso()
    if isinstance(value, datetime):
        return timezone_iso(value)
    validate_timezone_iso(value)
    return value


def _bbox_tuple(item: OCRItem) -> Any:
    if item.box is None:
        return None

    def convert(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (bytes, bytearray)):
            return bytes(value).decode("utf-8", errors="replace")
        try:
            values = tuple(value)
        except TypeError:
            try:
                return float(value)
            except (TypeError, ValueError, OverflowError):
                return value
        return tuple(convert(child) for child in values)

    return convert(item.box)


def _normalization_status(value: str) -> NormalizationStatus:
    return {
        NORMALIZATION_COMPLETED: NormalizationStatus.COMPLETED,
        NORMALIZATION_FAILED: NormalizationStatus.FAILED,
    }[value]


def _project_pair_evidence(value) -> OcrDuplicatePairEvidence:
    return OcrDuplicatePairEvidence(
        left_box_id=value.left_box_id,
        right_box_id=value.right_box_id,
        text_similarity=value.text_similarity,
        text_exact=value.text_exact,
        iou=value.iou,
        horizontal_overlap_ratio=value.horizontal_overlap_ratio,
        vertical_overlap_ratio=value.vertical_overlap_ratio,
        center_distance_ratio=value.center_distance_ratio,
        center_distance_size_ratio=value.center_distance_size_ratio,
        width_similarity=value.width_similarity,
        height_similarity=value.height_similarity,
        size_similarity=value.size_similarity,
        decision=value.decision,
        basis=tuple(value.basis),
    )


def normalization_record_fields(
    normalization: TextNormalizationResult,
    *,
    screen_id: str,
    screen_index: Optional[int],
    raw_box_ids: Tuple[str, ...],
    confidence_threshold_source: str = "run_manifest",
) -> Dict[str, Any]:
    """Project one already-computed R04 result without normalizing again."""

    raw_box_id_set = set(raw_box_ids)
    referenced_ids = set(normalization.ordered_box_ids)
    referenced_ids.update(normalization.effective_box_ids)
    referenced_ids.update(normalization.excluded_empty_box_ids)
    referenced_ids.update(normalization.suppressed_duplicate_box_ids)
    if not referenced_ids.issubset(raw_box_id_set):
        raise ValueError("normalization references unknown OCR box IDs")

    segments = tuple(
        OcrTextSegment(
            segment_id="{0}:line:{1}".format(screen_id, line.line_index),
            screen_index=screen_index,
            order=line.line_index,
            normalized_text=line.normalized_text,
            comparison_text=build_comparison_text(line.normalized_text),
            ocr_box_ids=tuple(line.box_ids),
            char_count=len(line.normalized_text),
            processing_status=ProcessingStatus.NORMALIZED,
        )
        for line in normalization.normalized_lines
    )
    duplicate_groups = tuple(
        OcrDuplicateGroup(
            retained_box_id=group.retained_box_id,
            suppressed_duplicate_box_ids=tuple(
                group.suppressed_duplicate_box_ids
            ),
            source_box_ids=tuple(group.source_box_ids),
            pair_evidence=tuple(
                _project_pair_evidence(value)
                for value in group.pair_evidence
            ),
        )
        for group in normalization.duplicate_groups
    )
    return {
        "raw_text_source": normalization.raw_text_source,
        "raw_text_length": normalization.raw_text_length,
        "normalized_text": normalization.normalized_text,
        "normalized_text_length": normalization.normalized_text_length,
        "comparison_text": normalization.comparison_text,
        "comparison_text_length": normalization.comparison_text_length,
        "segments": segments,
        "ordered_box_ids": tuple(normalization.ordered_box_ids),
        "effective_box_ids": tuple(normalization.effective_box_ids),
        "excluded_empty_box_ids": tuple(
            normalization.excluded_empty_box_ids
        ),
        "suppressed_duplicate_box_ids": tuple(
            normalization.suppressed_duplicate_box_ids
        ),
        "line_mapping": tuple(
            OcrLineMapping(value.box_id, value.line_index)
            for value in normalization.line_mapping
        ),
        "deduplicated_box_count": normalization.deduplicated_box_count,
        "duplicate_groups": duplicate_groups,
        "duplicate_risk": normalization.duplicate_risk,
        "duplicate_gray_pair_count": normalization.duplicate_gray_pair_count,
        "eligible_box_count": normalization.eligible_box_count,
        "low_confidence_box_count": normalization.low_confidence_box_count,
        "empty_normalized_box_count": normalization.empty_normalized_box_count,
        "processing_status": (
            ProcessingStatus.RAW_ONLY
            if normalization.status == NORMALIZATION_FAILED
            else ProcessingStatus.NORMALIZED
        ),
        "normalization_status": _normalization_status(normalization.status),
        "normalization_warnings": tuple(
            OcrNormalizationWarning(value.box_id, value.code)
            for value in normalization.normalization_warnings
        ),
        "normalization_error_type": normalization.normalization_error_type,
        "normalization_version": normalization.normalization_version,
        "normalization_config_version": (
            normalization.normalization_config_version
        ),
        "normalization_config_digest": normalization.normalization_config_digest,
        "effective_min_confidence": normalization.effective_min_confidence,
        "confidence_threshold_source": confidence_threshold_source,
        "rule_evaluation_mode": "legacy_shadow",
    }


def _rule_comparison_record_fields(rule_comparison: Any) -> Dict[str, Any]:
    """Flatten one already-computed legacy-shadow result for stage-0 storage."""

    values = {
        "rule_evaluation_mode": getattr(
            rule_comparison,
            "rule_evaluation_mode",
            None,
        ),
        "legacy_match": getattr(rule_comparison, "legacy_match", None),
        "r04_match": getattr(rule_comparison, "r04_match", None),
        "comparison_outcome": getattr(
            rule_comparison,
            "comparison_outcome",
            None,
        ),
        "legacy_rule_index": getattr(
            rule_comparison,
            "legacy_rule_index",
            None,
        ),
        "r04_rule_index": getattr(
            rule_comparison,
            "r04_rule_index",
            None,
        ),
    }
    if values["rule_evaluation_mode"] != "legacy_shadow":
        raise ValueError("unsupported rule evaluation mode")
    if values["comparison_outcome"] not in {
        "same_match",
        "same_no_match",
        "legacy_only",
        "r04_only",
        "normalization_failed",
    }:
        raise ValueError("unsupported rule comparison outcome")
    if not isinstance(values["legacy_match"], bool):
        raise ValueError("legacy_match must be boolean")
    if values["r04_match"] is not None and not isinstance(
        values["r04_match"],
        bool,
    ):
        raise ValueError("r04_match must be boolean or null")
    for field_name in ("legacy_rule_index", "r04_rule_index"):
        value = values[field_name]
        if value is not None and (not isinstance(value, int) or value < 0):
            raise ValueError("rule index must be a non-negative integer or null")
    return values


class CandidateOcrBuilder:
    """Collect only one candidate and release its detailed records on finalize."""

    def __init__(
        self,
        run_id: str,
        sequence_number: int,
        *,
        candidate_record_id: Optional[str] = None,
        created_at: Optional[Timestamp] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if sequence_number < 1:
            raise ValueError("sequence_number must be at least 1")
        self.run_id = run_id
        self.sequence_number = sequence_number
        self.candidate_record_id = str(candidate_record_id or uuid4())
        self.created_at = _timestamp_text(created_at)
        self.metadata: Dict[str, Any] = dict(metadata or {})
        self._screens: List[OcrScreenRecord] = []
        self._attempts: Dict[Tuple[str, Optional[int]], int] = {}
        self._finalized = False

    @property
    def finalized(self) -> bool:
        return self._finalized

    @property
    def retained_screen_count(self) -> int:
        return len(self._screens)

    def _require_active(self) -> None:
        if self._finalized:
            raise CandidateBuilderFinalizedError(
                "candidate OCR builder is already finalized"
            )

    @staticmethod
    def _attempt_key(
        capture_type: CaptureType,
        screen_index: Optional[int],
    ) -> Tuple[str, Optional[int]]:
        if capture_type in (CaptureType.LOAD_CHECK, CaptureType.LOAD_RETRY):
            return ("load", screen_index)
        if capture_type == CaptureType.FORMAL_SCREEN:
            return ("formal", screen_index)
        if capture_type == CaptureType.SCROLL_CONFIRMATION:
            return ("confirmation", screen_index)
        if capture_type == CaptureType.SWITCH_CHECK:
            return ("switch", screen_index)
        if capture_type == CaptureType.SCROLL_RETRY:
            return ("scroll_retry", screen_index)
        return (capture_type.value, screen_index)

    def next_attempt_index(
        self,
        capture_type: CaptureType,
        screen_index: Optional[int],
    ) -> int:
        self._require_active()
        capture_type = (
            capture_type
            if isinstance(capture_type, CaptureType)
            else CaptureType(capture_type)
        )
        key = self._attempt_key(capture_type, screen_index)
        next_value = self._attempts.get(key, 0) + 1
        self._attempts[key] = next_value
        return next_value

    def build_screen_record(
        self,
        raw_items: Iterable[OCRItem],
        *,
        capture_type: CaptureType,
        is_formal_screen: bool,
        screen_index: Optional[int],
        captured_at: Optional[Timestamp] = None,
        exact_hash: Optional[str] = None,
        fingerprint_version: Optional[str] = None,
        screen_id: Optional[str] = None,
        normalization: Optional[TextNormalizationResult] = None,
        ocr_min_confidence: Optional[float] = None,
        confidence_threshold_source: str = "run_manifest",
        rule_comparison: Optional[Any] = None,
    ) -> OcrScreenRecord:
        """Build and retain one evidence record in engine-return order."""

        self._require_active()
        capture_type = (
            capture_type
            if isinstance(capture_type, CaptureType)
            else CaptureType(capture_type)
        )
        if is_formal_screen and screen_index is None:
            raise ValueError("formal OCR screens require screen_index")
        if not is_formal_screen:
            box_screen_index = None
        else:
            box_screen_index = screen_index

        screen_id = str(screen_id or uuid4())
        items = tuple(raw_items)
        boxes = tuple(
            OcrBox(
                box_id="{0}:box:{1}".format(screen_id, original_index),
                raw_text=item.text,
                confidence=(
                    None
                    if getattr(item, "confidence", None) is None
                    else float(item.confidence)
                ),
                bbox=_bbox_tuple(item),
                original_index=original_index,
                screen_index=box_screen_index,
            )
            for original_index, item in enumerate(items)
        )
        raw_text = "\n".join(box.raw_text for box in boxes)
        normalization_fields: Dict[str, Any] = {
            "raw_text_source": RAW_TEXT_SOURCE_DERIVED_BOXES,
            "raw_text_length": len(raw_text),
        }
        if normalization is not None:
            try:
                normalization_fields.update(normalization_record_fields(
                    normalization,
                    screen_id=screen_id,
                    screen_index=screen_index,
                    raw_box_ids=tuple(box.box_id for box in boxes),
                    confidence_threshold_source=confidence_threshold_source,
                ))
                if (
                    ocr_min_confidence is not None
                    and float(ocr_min_confidence)
                    != float(normalization.effective_min_confidence)
                ):
                    raise ValueError("normalization confidence identity mismatch")
                if normalization.raw_text is not None:
                    raw_text = normalization.raw_text
            except Exception as exc:
                attempted_version = getattr(
                    normalization,
                    "normalization_version",
                    None,
                )
                normalization_fields.update({
                    "processing_status": ProcessingStatus.RAW_ONLY,
                    "normalization_status": NormalizationStatus.FAILED,
                    "normalization_error_type": type(exc).__name__,
                    "normalization_version": (
                        attempted_version
                        if isinstance(attempted_version, str)
                        and attempted_version
                        else NORMALIZATION_VERSION
                    ),
                    "normalization_config_version": getattr(
                        normalization, "normalization_config_version", None
                    ),
                    "normalization_config_digest": getattr(
                        normalization, "normalization_config_digest", None
                    ),
                    "effective_min_confidence": getattr(
                        normalization, "effective_min_confidence", None
                    ),
                    "confidence_threshold_source": confidence_threshold_source,
                    "rule_evaluation_mode": "legacy_shadow",
                    "duplicate_gray_pair_count": 0,
                    "eligible_box_count": getattr(
                        normalization, "eligible_box_count", 0
                    ),
                    "low_confidence_box_count": getattr(
                        normalization, "low_confidence_box_count", 0
                    ),
                    "empty_normalized_box_count": 0,
                })
        rule_comparison_fields: Dict[str, Any] = {}
        if rule_comparison is not None:
            rule_comparison_fields.update(
                _rule_comparison_record_fields(rule_comparison)
            )
        projected_fields = dict(normalization_fields)
        projected_fields.update(rule_comparison_fields)

        record = OcrScreenRecord(
            run_id=self.run_id,
            candidate_record_id=self.candidate_record_id,
            screen_id=screen_id,
            screen_index=screen_index,
            attempt_index=self.next_attempt_index(
                capture_type, screen_index
            ),
            capture_type=capture_type,
            is_formal_screen=is_formal_screen,
            captured_at=_timestamp_text(captured_at),
            raw_boxes=boxes,
            raw_text=raw_text,
            exact_hash=exact_hash,
            fingerprint_version=fingerprint_version,
            ocr_min_confidence=ocr_min_confidence,
            **projected_fields,
        )
        self._screens.append(record)
        return record

    def add_screen(self, record: OcrScreenRecord) -> None:
        self._require_active()
        if record.run_id != self.run_id:
            raise ValueError("screen run_id does not match builder")
        if record.candidate_record_id != self.candidate_record_id:
            raise ValueError("screen candidate_record_id does not match builder")
        self._screens.append(record)

    def finalize(
        self,
        capture_status: CaptureStatus,
        *,
        end_reason: Optional[str],
        abort_reason: Optional[str] = None,
        completed_at: Optional[Timestamp] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> CandidateOcrDocument:
        """Create one document, then drop builder references to screen details."""

        self._require_active()
        capture_status = (
            capture_status
            if isinstance(capture_status, CaptureStatus)
            else CaptureStatus(capture_status)
        )
        screens = tuple(self._screens)
        formal_indexes = {
            screen.screen_index
            for screen in screens
            if screen.is_formal_screen and screen.screen_index is not None
        }
        scroll_attempt_count = sum(
            1
            for screen in screens
            if (
                screen.is_formal_screen
                and screen.screen_index is not None
                and screen.screen_index > 1
            )
            or screen.capture_type == CaptureType.SCROLL_RETRY
        )
        summary = CaptureSummary(
            actual_screen_count=len(formal_indexes),
            ocr_attempt_count=len(screens),
            scroll_attempt_count=scroll_attempt_count,
            scroll_retry_count=sum(
                screen.capture_type == CaptureType.SCROLL_RETRY
                for screen in screens
            ),
            end_screen_index=max(formal_indexes) if formal_indexes else None,
            capture_status=capture_status,
            end_reason=end_reason,
            abort_reason=abort_reason,
        )
        document_metadata = dict(self.metadata)
        if metadata:
            document_metadata.update(metadata)
        normalization_versions = {
            screen.normalization_version
            for screen in screens
            if screen.normalization_status
            in (NormalizationStatus.COMPLETED, NormalizationStatus.FAILED)
        }
        if len(normalization_versions) > 1:
            raise ValueError("mixed candidate normalization versions are unsupported")
        document = CandidateOcrDocument(
            run_id=self.run_id,
            candidate_record_id=self.candidate_record_id,
            sequence_number=self.sequence_number,
            created_at=self.created_at,
            completed_at=_timestamp_text(completed_at),
            capture_status=capture_status,
            screens=screens,
            capture_summary=summary,
            document_text=None,
            document_segments=(),
            document_build_status=NOT_IMPLEMENTED,
            normalization_summary=recompute_normalization_summary(screens),
            versions={
                "normalization": (
                    next(iter(normalization_versions))
                    if normalization_versions
                    else None
                ),
                "aggregation": None,
                "similarity": None,
                "dynamic_end": None,
            },
            metadata=document_metadata,
        )
        self._screens.clear()
        self._attempts.clear()
        self._finalized = True
        return document
