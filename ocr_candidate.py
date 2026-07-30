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
    OcrBox,
    OcrScreenRecord,
    timezone_iso,
    validate_timezone_iso,
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


def _bbox_tuple(item: OCRItem) -> Optional[Tuple[Tuple[float, float], ...]]:
    if item.box is None:
        return None
    try:
        return tuple(
            (float(point[0]), float(point[1])) for point in item.box
        )
    except (IndexError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("OCR item bbox must contain numeric coordinate pairs") from exc


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
    ) -> OcrScreenRecord:
        """Build and retain one raw record in engine-return order."""

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

        screen_id = str(uuid4())
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
            raw_text="\n".join(box.raw_text for box in boxes),
            exact_hash=exact_hash,
            fingerprint_version=fingerprint_version,
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
            versions={
                "normalization": None,
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
