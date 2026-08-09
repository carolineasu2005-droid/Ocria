"""Offline loading and pure R04--R07 replay views without source effects."""

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Type, TypeVar

from ocr_normalization import (
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NORMALIZATION_COMPLETED,
    NORMALIZATION_VERSION,
    RAW_TEXT_SOURCE_ENGINE_SCREEN,
    OcrNormalizationConfig,
    canonical_normalization_config,
    config_with_effective_min_confidence,
    normalization_config_digest,
    normalization_config_from_snapshot,
    normalize_ocr_text,
)
from ocr_candidate import CandidateOcrBuilder, normalization_record_fields
from ocr_aggregation import (
    OcrAggregationConfig,
    aggregation_config_digest,
    aggregation_screen_record_fields,
    restore_aggregation_config,
)
from ocr_similarity import (
    DEFAULT_OCR_SIMILARITY_CONFIG,
    CandidateSimilarityEvaluator,
    OcrSimilarityConfig,
    empty_similarity_summary,
    failed_similarity_result,
    similarity_config_digest,
    similarity_config_from_snapshot,
)

from ocr_records import (
    CandidateOcrDocument,
    CaptureType,
    DocumentBuildStatus,
    DOCUMENT_VERSION,
    LEGACY_STORAGE_SCHEMA_VERSION,
    R04_STORAGE_SCHEMA_VERSION,
    R06_AND_LATER_STORAGE_SCHEMA_VERSIONS,
    NormalizationStatus,
    OcrScreenRecord,
    ReferenceResolution,
    ReferenceResolutionStatus,
    ReferenceSource,
    RecordVersionError,
    RunManifest,
    STORAGE_SCHEMA_VERSION,
    SUPPORTED_DOCUMENT_VERSIONS,
    SUPPORTED_STORAGE_SCHEMA_VERSIONS,
    validate_record_version,
    recompute_similarity_summary,
)
from ocr_store import (
    CANDIDATES_NAME,
    ERRORS_NAME,
    RUN_MANIFEST_NAME,
    SCREENS_NAME,
)


class OcrReplayError(ValueError):
    """Raised for a strict-mode manifest or JSONL read failure."""

    def __init__(
        self,
        path: Path,
        line_number: int,
        error_type: str,
        *,
        version_field: Optional[str] = None,
        actual_version: Optional[str] = None,
        supported_versions: Tuple[str, ...] = (),
    ):
        self.path = Path(path)
        self.line_number = line_number
        self.error_type = error_type
        self.version_field = version_field
        self.actual_version = actual_version
        self.supported_versions = supported_versions
        message = "{0}:{1}: {2}".format(self.path, line_number, error_type)
        if version_field is not None:
            message += " field={0} actual={1!r} supported={2!r}".format(
                version_field,
                actual_version,
                list(supported_versions),
            )
        super().__init__(message)


@dataclass(frozen=True)
class ReplayIssue:
    """Sanitized tolerant-mode problem report without record contents."""

    path: Path
    line_number: int
    error_type: str
    version_field: Optional[str] = None
    actual_version: Optional[str] = None
    supported_versions: Tuple[str, ...] = ()


T = TypeVar("T")


class OcrRunReader:
    """Read one run directory in strict or best-effort tolerant mode."""

    def __init__(self, run_dir: Path, *, strict: bool = True) -> None:
        self.run_dir = Path(run_dir)
        self.strict = strict
        self.issues: List[ReplayIssue] = []

    def _report_or_raise(
        self,
        path: Path,
        line_number: int,
        exc: Exception,
    ) -> None:
        if isinstance(exc, RecordVersionError):
            error_type = exc.error_type
            version_field = exc.field_name
            actual_version = exc.actual_version
            supported_versions = exc.supported_versions
        else:
            error_type = type(exc).__name__
            version_field = None
            actual_version = None
            supported_versions = ()
        if self.strict:
            raise OcrReplayError(
                path,
                line_number,
                error_type,
                version_field=version_field,
                actual_version=actual_version,
                supported_versions=supported_versions,
            ) from exc
        self.issues.append(
            ReplayIssue(
                Path(path),
                line_number,
                error_type,
                version_field,
                actual_version,
                supported_versions,
            )
        )

    def read_manifest(self) -> Optional[RunManifest]:
        path = self.run_dir / RUN_MANIFEST_NAME
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise TypeError("run manifest must be a JSON object")
            return RunManifest.from_dict(data)
        except Exception as exc:
            self._report_or_raise(path, 1, exc)
            return None

    @staticmethod
    def _matches_filters(
        record: Mapping[str, Any],
        *,
        run_id: Optional[str],
        candidate_record_id: Optional[str],
        record_type: Optional[str],
    ) -> bool:
        if run_id is not None and record.get("run_id") != run_id:
            return False
        if record_type is not None and record.get("record_type") != record_type:
            return False
        if candidate_record_id is not None:
            record_candidate_id = record.get("candidate_record_id")
            if record_candidate_id is None:
                context = record.get("context")
                if isinstance(context, dict):
                    record_candidate_id = context.get("candidate_record_id")
            if record_candidate_id != candidate_record_id:
                return False
        return True

    def _iter_jsonl(
        self,
        path: Path,
        *,
        object_type: Optional[Type[T]] = None,
        run_id: Optional[str] = None,
        candidate_record_id: Optional[str] = None,
        record_type: Optional[str] = None,
        version_contracts: Tuple[Tuple[str, Tuple[str, ...]], ...] = (),
    ) -> Iterator[Any]:
        try:
            handle = path.open("r", encoding="utf-8", newline="")
        except Exception as exc:
            self._report_or_raise(path, 0, exc)
            return

        with handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise TypeError("JSONL record must be an object")
                    for field_name, supported_versions in version_contracts:
                        validate_record_version(
                            record,
                            field_name,
                            supported_versions,
                        )
                    if not self._matches_filters(
                        record,
                        run_id=run_id,
                        candidate_record_id=candidate_record_id,
                        record_type=record_type,
                    ):
                        continue
                    if object_type is None:
                        yield record
                    else:
                        yield object_type.from_dict(record)
                except Exception as exc:
                    self._report_or_raise(path, line_number, exc)

    def iter_screens(
        self,
        *,
        run_id: Optional[str] = None,
        candidate_record_id: Optional[str] = None,
        record_type: Optional[str] = None,
    ) -> Iterator[OcrScreenRecord]:
        return self._iter_jsonl(
            self.run_dir / SCREENS_NAME,
            object_type=OcrScreenRecord,
            run_id=run_id,
            candidate_record_id=candidate_record_id,
            record_type=record_type,
            version_contracts=((
                "storage_schema_version",
                SUPPORTED_STORAGE_SCHEMA_VERSIONS,
            ),),
        )

    def iter_candidates(
        self,
        *,
        run_id: Optional[str] = None,
        candidate_record_id: Optional[str] = None,
        record_type: Optional[str] = None,
    ) -> Iterator[CandidateOcrDocument]:
        return self._iter_jsonl(
            self.run_dir / CANDIDATES_NAME,
            object_type=CandidateOcrDocument,
            run_id=run_id,
            candidate_record_id=candidate_record_id,
            record_type=record_type,
            version_contracts=(
                (
                    "storage_schema_version",
                    SUPPORTED_STORAGE_SCHEMA_VERSIONS,
                ),
                ("document_version", SUPPORTED_DOCUMENT_VERSIONS),
            ),
        )

    def iter_errors(
        self,
        *,
        run_id: Optional[str] = None,
        candidate_record_id: Optional[str] = None,
        record_type: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        return self._iter_jsonl(
            self.run_dir / ERRORS_NAME,
            run_id=run_id,
            candidate_record_id=candidate_record_id,
            record_type=record_type,
            version_contracts=((
                "storage_schema_version",
                SUPPORTED_STORAGE_SCHEMA_VERSIONS,
            ),),
        )


@dataclass(frozen=True)
class OcrRunReplay:
    """Materialized convenience result for small offline stage-0 runs."""

    manifest: Optional[RunManifest]
    screens: List[OcrScreenRecord]
    candidates: List[CandidateOcrDocument]
    errors: List[Dict[str, Any]]
    issues: List[ReplayIssue]


@dataclass(frozen=True)
class NormalizationReplayResult:
    """One non-persisting replay view with explicit historical provenance."""

    source: OcrScreenRecord
    normalized: OcrScreenRecord
    effective_min_confidence: float
    confidence_threshold_source: str
    normalization_config_version: str
    normalization_config_digest: str
    issue: Optional[ReplayIssue] = None


@dataclass(frozen=True)
class CandidateAggregationReplay:
    """In-memory R05 rebuild only; it never writes or modifies the source."""

    source: CandidateOcrDocument
    rebuilt: Optional[CandidateOcrDocument]
    config_source: str
    issues: Tuple[ReplayIssue, ...] = ()


@dataclass(frozen=True)
class CandidateSimilarityReplay:
    """In-memory R06 rebuild; the source candidate and source files stay immutable."""

    source: CandidateOcrDocument
    rebuilt: Optional[CandidateOcrDocument]
    config_source: str
    issues: Tuple[ReplayIssue, ...] = ()


@dataclass(frozen=True)
class DynamicEndReplayResult:
    """One R07-only reconstruction from persisted candidate evidence.

    This deliberately reports an offline bottom as *possible* at most.  It
    does not re-run a confirmation capture and therefore cannot establish the
    online ``scroll_bottom`` conclusion.
    """

    candidate_record_id: str
    position_statuses: Tuple[str, ...]
    consecutive_no_new_count: int
    no_new_text_candidate: bool
    offline_bottom_status: str
    first_predicted_end_screen: Optional[int]
    first_predicted_end_reason: Optional[str]
    prediction_would_miss_content: Optional[bool]
    prediction_would_miss_rule_match: Optional[bool]
    prediction_observation_complete: Optional[bool]
    prediction_evidence_complete: Optional[bool]
    legacy_rule_completed: bool
    recorded_dynamic_end_reason: Optional[str]
    insufficient_evidence: bool


_REPLAY_POSITION_STATUSES = frozenset((
    "initial", "changed", "same", "uncertain", "unavailable",
))


def _replay_enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _replay_has_uncertain_evidence(record: OcrScreenRecord) -> bool:
    """Inspect existing R05/R06 projections; never calculate them again."""

    aggregation_status = _replay_enum_value(record.aggregation_status)
    if aggregation_status not in ("not_attempted", "completed"):
        return True
    if (
        record.uncertain_segment_ids
        or (record.uncertain_segment_count or 0) > 0
        or (record.uncertain_char_count or 0) > 0
        or _replay_enum_value(record.aggregation_duplicate_risk) == "elevated"
    ):
        return True
    result = record.similarity_result
    if result is None:
        return False
    if _replay_enum_value(result.effective_new_status) == "possible":
        return True
    if _replay_enum_value(result.comparison_class) == "uncertain":
        return True
    if _replay_enum_value(result.similarity_status) in (
        "partial", "failed", "unavailable",
    ):
        return True
    warnings = tuple(result.warning_codes) + tuple(record.aggregation_warning_codes)
    return any(
        any(token in str(code).lower() for token in (
            "possible", "uncertain", "conflict", "mismatch",
        ))
        for code in warnings
    )


def _replay_has_effective_new_content(record: OcrScreenRecord) -> bool:
    """Read only persisted R05/R06 positive evidence, including short text."""

    if record.has_effective_new_text is True:
        return True
    result = record.similarity_result
    if result is None:
        return False
    if (
        result.has_effective_new_text is True
        or _replay_enum_value(result.effective_new_status) == "present"
        or (result.effective_new_segment_count or 0) > 0
    ):
        return True
    return any(
        decision.reason == "short_text_protected"
        and _replay_enum_value(decision.decision) == "effective"
        for decision in result.effective_new_decisions
    )


def _replay_is_full_no_new_slot(record: OcrScreenRecord, position: str) -> bool:
    """The persisted-only form of the frozen full no-new predicate."""

    result = record.similarity_result
    return (
        _replay_enum_value(record.capture_type) == "formal_screen"
        and record.is_formal_screen is True
        and record.is_position_confirmation is not True
        and position == "changed"
        and _replay_enum_value(record.aggregation_status) == "completed"
        and result is not None
        and _replay_enum_value(result.similarity_status) == "completed"
        and _replay_enum_value(result.effective_new_status) == "none"
        and not _replay_has_uncertain_evidence(record)
        and not _replay_has_effective_new_content(record)
    )


def replay_dynamic_end(candidate: CandidateOcrDocument) -> DynamicEndReplayResult:
    """Replay R07 facts from a saved candidate without OCR, UI, or writes.

    The order is exactly ``candidate.screens``.  R07 position metadata is
    reused when present; an older record without it remains unavailable (apart
    from the order-only initial screen), rather than being treated as healthy.
    No R03--R06 algorithm is invoked here.
    """

    if not isinstance(candidate, CandidateOcrDocument):
        raise TypeError("candidate must be a CandidateOcrDocument")

    positions: List[str] = []
    insufficient = False
    consecutive_no_new_count = 0
    no_new_text_candidate = False
    first_prediction_seen = False
    saw_legacy_rule_after_prediction = False
    saw_content_after_prediction = False

    for index, record in enumerate(candidate.screens):
        position = record.position_status
        if position not in _REPLAY_POSITION_STATUSES:
            # An old schema has no R07 position health.  The leading record is
            # still ordered first, but is not evidence for a dynamic end.
            position = "initial" if index == 0 else "unavailable"
            insufficient = True
        positions.append(position)

        if position in ("uncertain", "unavailable"):
            insufficient = True
        if _replay_is_full_no_new_slot(record, position):
            consecutive_no_new_count += 1
            no_new_text_candidate = (
                no_new_text_candidate or consecutive_no_new_count >= 2
            )
        else:
            consecutive_no_new_count = 0

        if (
            candidate.first_predicted_end_screen is not None
            and record.screen_index is not None
            and record.screen_index >= candidate.first_predicted_end_screen
        ):
            first_prediction_seen = True
            # G1: Only a saved rule_confirmation with legacy_match=True
            # represents a confirmed legacy rule completion.  A first-pass
            # formal_screen.legacy_match is only a candidate hit.
            if (
                _replay_enum_value(record.capture_type) == "rule_confirmation"
                and record.legacy_match is True
            ):
                saw_legacy_rule_after_prediction = True
            if _replay_has_effective_new_content(record):
                saw_content_after_prediction = True

    # G1: legacy_rule_completed is only true when a saved rule_confirmation
    # with legacy_match=True exists.  formal_screen.legacy_match alone cannot
    # represent a confirmed completion.
    legacy_rule_completed = any(
        _replay_enum_value(record.capture_type) == "rule_confirmation"
        and record.legacy_match is True
        for record in candidate.screens
    )

    source_abort_reason = candidate.abort_reason or candidate.capture_summary.abort_reason
    if source_abort_reason is not None or _replay_enum_value(candidate.capture_status) in (
        "aborted", "interrupted",
    ):
        insufficient = True

    prediction_screen = candidate.first_predicted_end_screen
    prediction_reason = candidate.first_predicted_end_reason
    if prediction_screen is not None and not first_prediction_seen:
        insufficient = True
    if prediction_screen is None:
        # Missing R07 fields in legacy data are unknown, never a healthy
        # observation window or a negative miss conclusion.
        insufficient = True

    content_miss = candidate.prediction_would_miss_content
    rule_miss = candidate.prediction_would_miss_rule_match
    observation_complete = candidate.prediction_observation_complete
    evidence_complete = candidate.prediction_evidence_complete
    if prediction_screen is None:
        content_miss = None
        rule_miss = None
        observation_complete = None
        evidence_complete = None
    elif saw_legacy_rule_after_prediction:
        rule_miss = True
        # A rule early stop leaves the later content window incomplete unless
        # an already persisted positive content observation proves otherwise.
        content_miss = True if saw_content_after_prediction else None
    elif saw_content_after_prediction:
        content_miss = True

    # G2: Evidence completeness gates.  When persisted completeness fields
    # are explicitly false, or when any inconsistency exists between the
    # prediction, the persisted fields, and the abort state, the replay must
    # output insufficient_evidence rather than treating the evidence as
    # healthy possible-bottom proof.
    if source_abort_reason is not None:
        content_miss = None
        rule_miss = None
        observation_complete = None
        evidence_complete = None

    # G2: persisted incomplete evidence forces insufficient_evidence
    persisted_observation_incomplete = (
        candidate.prediction_observation_complete is False
        or candidate.prediction_evidence_complete is False
        or (prediction_screen is not None
            and observation_complete is False)
        or (prediction_screen is not None
            and evidence_complete is False)
    )
    # G2: old-schema null completeness is not treated as complete unless all
    # other signs (including the prediction presence) agree it is healthy.
    has_explicit_completeness = (
        candidate.prediction_observation_complete is not None
        or candidate.prediction_evidence_complete is not None
    )
    prediction_exists = prediction_screen is not None
    completions_both_null = (
        candidate.prediction_observation_complete is None
        and candidate.prediction_evidence_complete is None
    )
    completeness_is_healthy = (
        prediction_exists
        and not persisted_observation_incomplete
        and observation_complete is not False
        and evidence_complete is not False
        and not completions_both_null
    )

    offline_bottom_status = "insufficient_evidence"
    if (
        prediction_screen is not None
        and prediction_reason == "possible_scroll_bottom"
        and first_prediction_seen
        and source_abort_reason is None
        and completeness_is_healthy
    ):
        offline_bottom_status = "possible_scroll_bottom"
    else:
        insufficient = True

    return DynamicEndReplayResult(
        candidate_record_id=candidate.candidate_record_id,
        position_statuses=tuple(positions),
        consecutive_no_new_count=consecutive_no_new_count,
        no_new_text_candidate=no_new_text_candidate,
        offline_bottom_status=offline_bottom_status,
        first_predicted_end_screen=prediction_screen,
        first_predicted_end_reason=prediction_reason,
        prediction_would_miss_content=content_miss,
        prediction_would_miss_rule_match=rule_miss,
        prediction_observation_complete=observation_complete,
        prediction_evidence_complete=evidence_complete,
        legacy_rule_completed=legacy_rule_completed,
        recorded_dynamic_end_reason=candidate.dynamic_end_reason,
        insufficient_evidence=insufficient,
    )


class _ReplayContractError(ValueError):
    def __init__(self, error_type: str) -> None:
        self.error_type = error_type
        super().__init__(error_type)


def _screen_replay_error(error_type: str) -> OcrReplayError:
    return OcrReplayError(Path("<screen-replay>"), 0, error_type)


def _replay_issue(error_type: str) -> ReplayIssue:
    return ReplayIssue(Path("<screen-replay>"), 0, error_type)


def _validate_manifest_config(manifest: RunManifest) -> OcrNormalizationConfig:
    if manifest.storage_schema_version not in R06_AND_LATER_STORAGE_SCHEMA_VERSIONS:
        raise _ReplayContractError("ManifestSchemaMismatchError")
    try:
        config = normalization_config_from_snapshot(
            manifest.normalization_config
        )
        digest = normalization_config_digest(manifest.normalization_config)
    except Exception as exc:
        raise _ReplayContractError("ManifestConfigError") from exc
    if (
        manifest.normalization_version != NORMALIZATION_VERSION
        or manifest.normalization_config_version
        != config.normalization_config_version
        or manifest.normalization_config_digest != digest
        or manifest.effective_min_confidence
        != config.effective_min_confidence
        or manifest.rule_evaluation_mode != "legacy_shadow"
    ):
        raise _ReplayContractError("ManifestConfigMismatchError")
    return config


def _validate_screen_config_identity(
    record: OcrScreenRecord,
    config: OcrNormalizationConfig,
    digest: str,
) -> None:
    if record.normalization_status == NormalizationStatus.NOT_ATTEMPTED:
        return
    if (
        record.normalization_version != NORMALIZATION_VERSION
        or record.normalization_config_version
        != config.normalization_config_version
        or record.normalization_config_digest != digest
        or record.effective_min_confidence
        != config.effective_min_confidence
        or record.rule_evaluation_mode != "legacy_shadow"
    ):
        raise _ReplayContractError("ScreenConfigMismatchError")


def _failed_replay_view(
    record: OcrScreenRecord,
    config: OcrNormalizationConfig,
    threshold_source: str,
    error_type: str,
) -> OcrScreenRecord:
    from ocr_normalization import failed_normalization_result

    failed = failed_normalization_result(
        record.raw_boxes,
        engine_raw_text=(
            record.raw_text
            if record.raw_text_source == RAW_TEXT_SOURCE_ENGINE_SCREEN
            else None
        ),
        error_type=error_type,
        config=config,
    )
    fields = normalization_record_fields(
        failed,
        screen_id=record.screen_id,
        screen_index=record.screen_index,
        raw_box_ids=tuple(box.box_id for box in record.raw_boxes),
        confidence_threshold_source=threshold_source,
    )
    return replace(
        record,
        storage_schema_version=STORAGE_SCHEMA_VERSION,
        legacy_match=None,
        r04_match=None,
        comparison_outcome=None,
        legacy_rule_index=None,
        r04_rule_index=None,
        **fields,
    )


def replay_screen_normalization(
    record: OcrScreenRecord,
    *,
    manifest: Optional[RunManifest] = None,
    config: Optional[OcrNormalizationConfig] = None,
    legacy_min_confidence_override: Optional[float] = None,
    strict: bool = True,
) -> NormalizationReplayResult:
    """Recompute one screen from immutable evidence and explicit history."""

    resolved_config: Optional[OcrNormalizationConfig] = None
    threshold_source = "run_manifest"
    try:
        if not isinstance(record, OcrScreenRecord):
            raise _ReplayContractError("InvalidScreenRecordError")
        if record.storage_schema_version in R06_AND_LATER_STORAGE_SCHEMA_VERSIONS:
            if legacy_min_confidence_override is not None:
                raise _ReplayContractError("LegacyOverrideNotAllowedError")
            if manifest is not None:
                resolved_config = _validate_manifest_config(manifest)
                if manifest.run_id != record.run_id:
                    raise _ReplayContractError("ManifestRunMismatchError")
                if config is not None and normalization_config_digest(config) != normalization_config_digest(
                    resolved_config
                ):
                    raise _ReplayContractError("ExplicitConfigMismatchError")
            else:
                if config is None:
                    raise _ReplayContractError("HistoricalConfigRequiredError")
                resolved_config = config
                if record.normalization_status == NormalizationStatus.NOT_ATTEMPTED:
                    raise _ReplayContractError("ScreenConfigIdentityRequiredError")
            digest = normalization_config_digest(resolved_config)
            _validate_screen_config_identity(record, resolved_config, digest)
            threshold_source = "run_manifest" if manifest is not None else "caller_config"
        elif record.storage_schema_version == LEGACY_STORAGE_SCHEMA_VERSION:
            if manifest is not None and manifest.storage_schema_version != LEGACY_STORAGE_SCHEMA_VERSION:
                raise _ReplayContractError("ManifestSchemaMismatchError")
            threshold = (
                0.85
                if legacy_min_confidence_override is None
                else float(legacy_min_confidence_override)
            )
            threshold_source = (
                "legacy_stage0_assumption"
                if legacy_min_confidence_override is None
                else "caller_override"
            )
            resolved_config = config_with_effective_min_confidence(
                config or DEFAULT_OCR_NORMALIZATION_CONFIG,
                threshold,
            )
            digest = normalization_config_digest(resolved_config)
        else:
            raise _ReplayContractError("UnsupportedStorageSchemaError")

        result = normalize_ocr_text(
            record.raw_boxes,
            engine_raw_text=(
                record.raw_text
                if record.raw_text_source == RAW_TEXT_SOURCE_ENGINE_SCREEN
                else None
            ),
            config=resolved_config,
        )
        if result.status != NORMALIZATION_COMPLETED:
            raise _ReplayContractError(
                result.normalization_error_type or "NormalizationFailedError"
            )
        fields = normalization_record_fields(
            result,
            screen_id=record.screen_id,
            screen_index=record.screen_index,
            raw_box_ids=tuple(box.box_id for box in record.raw_boxes),
            confidence_threshold_source=threshold_source,
        )
        normalized = replace(
            record,
            storage_schema_version=STORAGE_SCHEMA_VERSION,
            legacy_match=None if record.storage_schema_version == LEGACY_STORAGE_SCHEMA_VERSION else record.legacy_match,
            r04_match=None if record.storage_schema_version == LEGACY_STORAGE_SCHEMA_VERSION else record.r04_match,
            comparison_outcome=None if record.storage_schema_version == LEGACY_STORAGE_SCHEMA_VERSION else record.comparison_outcome,
            legacy_rule_index=None if record.storage_schema_version == LEGACY_STORAGE_SCHEMA_VERSION else record.legacy_rule_index,
            r04_rule_index=None if record.storage_schema_version == LEGACY_STORAGE_SCHEMA_VERSION else record.r04_rule_index,
            **fields,
        )
        if normalized.raw_boxes != record.raw_boxes or normalized.raw_text != record.raw_text:
            raise _ReplayContractError("RawEvidenceMutationError")
        return NormalizationReplayResult(
            source=record,
            normalized=normalized,
            effective_min_confidence=resolved_config.effective_min_confidence,
            confidence_threshold_source=threshold_source,
            normalization_config_version=resolved_config.normalization_config_version,
            normalization_config_digest=digest,
        )
    except Exception as exc:
        error_type = (
            exc.error_type
            if isinstance(exc, _ReplayContractError)
            else type(exc).__name__
        )
        if strict:
            raise _screen_replay_error(error_type) from exc
        issue = _replay_issue(error_type)
        normalized = record
        if resolved_config is not None:
            try:
                normalized = _failed_replay_view(
                    record,
                    resolved_config,
                    threshold_source,
                    error_type,
                )
            except Exception:
                normalized = record
        return NormalizationReplayResult(
            source=record,
            normalized=normalized,
            effective_min_confidence=(
                resolved_config.effective_min_confidence
                if resolved_config is not None
                else 0.85
            ),
            confidence_threshold_source=threshold_source,
            normalization_config_version=(
                resolved_config.normalization_config_version
                if resolved_config is not None
                else "r04-config-v1"
            ),
            normalization_config_digest=(
                normalization_config_digest(resolved_config)
                if resolved_config is not None
                else ""
            ),
            issue=issue,
        )


def _candidate_replay_error(error_type: str) -> OcrReplayError:
    return OcrReplayError(Path("<candidate-aggregation-replay>"), 0, error_type)


def _candidate_replay_issue(error_type: str) -> ReplayIssue:
    return ReplayIssue(Path("<candidate-aggregation-replay>"), 0, error_type)


def _candidate_similarity_replay_error(error_type: str) -> OcrReplayError:
    return OcrReplayError(Path("<candidate-similarity-replay>"), 0, error_type)


def _candidate_similarity_replay_issue(error_type: str) -> ReplayIssue:
    return ReplayIssue(Path("<candidate-similarity-replay>"), 0, error_type)


def _replay_reference_maps(
    screens: Tuple[OcrScreenRecord, ...],
) -> Tuple[Dict[str, OcrScreenRecord], Dict[int, str]]:
    """Build resolver maps by persisted identity, not JSONL order."""

    by_id: Dict[str, OcrScreenRecord] = {}
    formal_by_index: Dict[int, str] = {}
    for position, screen in enumerate(screens):
        key = screen.screen_id
        if key in by_id:
            key = "{0}#duplicate-{1}".format(key, position)
        by_id[key] = screen
        if (
            screen.capture_type == CaptureType.FORMAL_SCREEN
            and screen.is_formal_screen is True
            and isinstance(screen.screen_index, int)
            and screen.screen_index not in formal_by_index
        ):
            formal_by_index[screen.screen_index] = screen.screen_id
    return by_id, formal_by_index


def _failed_similarity_projection(
    screen: OcrScreenRecord,
    config: OcrSimilarityConfig,
) -> OcrScreenRecord:
    source = (
        ReferenceSource.FORMAL_PREVIOUS_INDEX
        if screen.capture_type == CaptureType.FORMAL_SCREEN and screen.is_formal_screen
        else ReferenceSource.EXPLICIT_RECORD
    )
    result = failed_similarity_result(
        ReferenceResolution(
            ReferenceResolutionStatus.UNAVAILABLE,
            None,
            None,
            None,
            source,
            ("evaluation_failed",),
        ),
        config,
    )
    return replace(
        screen,
        storage_schema_version=STORAGE_SCHEMA_VERSION,
        similarity_hash=result.current_simhash,
        similarity_score=result.similarity_score,
        overlap_ratio=result.overlap_ratio,
        new_text_ratio=result.new_text_ratio,
        has_effective_new_text=result.has_effective_new_text,
        similarity_version=result.similarity_version,
        similarity_result=result,
    )


def _evaluate_r06_screens(
    screens: Tuple[OcrScreenRecord, ...],
    config: OcrSimilarityConfig,
) -> Tuple[OcrScreenRecord, ...]:
    """Use the exact online evaluator/context without changing screen order."""

    if not screens:
        return ()
    run_ids = {screen.run_id for screen in screens}
    candidate_ids = {screen.candidate_record_id for screen in screens}
    if len(run_ids) != 1 or len(candidate_ids) != 1:
        raise _ReplayContractError("CandidateScreenIdentityMismatchError")
    evaluator = CandidateSimilarityEvaluator(
        next(iter(run_ids)), next(iter(candidate_ids)), config
    )
    rebuilt = []
    try:
        for screen in screens:
            by_id, formal_by_index = _replay_reference_maps(tuple(rebuilt))
            try:
                result = evaluator.evaluate(
                    screen,
                    by_id,
                    formal_by_index,
                    source_schema_version=STORAGE_SCHEMA_VERSION,
                )
                rebuilt.append(replace(
                    screen,
                    storage_schema_version=STORAGE_SCHEMA_VERSION,
                    similarity_hash=result.current_simhash,
                    similarity_score=result.similarity_score,
                    overlap_ratio=result.overlap_ratio,
                    new_text_ratio=result.new_text_ratio,
                    has_effective_new_text=result.has_effective_new_text,
                    similarity_version=result.similarity_version,
                    similarity_result=result,
                ))
            except Exception:
                rebuilt.append(_failed_similarity_projection(screen, config))
        return tuple(rebuilt)
    finally:
        evaluator.clear()


def _similarity_document(
    candidate: CandidateOcrDocument,
    screens: Tuple[OcrScreenRecord, ...],
    config: OcrSimilarityConfig,
) -> CandidateOcrDocument:
    summary = (
        recompute_similarity_summary(screens)
        if screens else empty_similarity_summary(config)
    )
    versions = dict(candidate.versions)
    versions["similarity"] = config.similarity_version
    return replace(
        candidate,
        storage_schema_version=STORAGE_SCHEMA_VERSION,
        screens=screens,
        similarity_summary=summary,
        versions=versions,
    )


def _r05_rebuild_for_similarity(
    candidate: CandidateOcrDocument,
    config: OcrAggregationConfig,
) -> CandidateOcrDocument:
    """The mandatory R05 predecessor for 1.0/1.1 R06 replay."""

    builder = CandidateOcrBuilder(
        candidate.run_id,
        candidate.sequence_number,
        candidate_record_id=candidate.candidate_record_id,
        created_at=candidate.created_at,
        metadata=candidate.metadata,
        aggregation_mode="record",
        aggregation_config=config,
        similarity_mode="disabled",
    )
    for screen in candidate.screens:
        builder.add_screen(screen)
    return builder.finalize(
        candidate.capture_status,
        end_reason=candidate.capture_summary.end_reason,
        abort_reason=candidate.capture_summary.abort_reason,
        completed_at=candidate.completed_at,
    )


def replay_candidate_similarity(
    candidate: CandidateOcrDocument,
    manifest: Optional[RunManifest] = None,
    *,
    strict: bool = True,
    similarity_config: Optional[OcrSimilarityConfig] = None,
    aggregation_config: Optional[OcrAggregationConfig] = None,
    normalization_config: Optional[OcrNormalizationConfig] = None,
) -> CandidateSimilarityReplay:
    """Replay R06 with its exact online evaluator and explicit history.

    Older records advance through their missing R04/R05 stages in memory.  No
    source JSONL object, manifest, candidate, or screen is changed.
    """

    try:
        if not isinstance(candidate, CandidateOcrDocument):
            raise _ReplayContractError("InvalidCandidateSimilarityInputError")
        storage_version = candidate.storage_schema_version
        if storage_version in R06_AND_LATER_STORAGE_SCHEMA_VERSIONS:
            if (
                not isinstance(manifest, RunManifest)
                or manifest.storage_schema_version != storage_version
            ):
                raise _ReplayContractError("ManifestSchemaMismatchError")
            if manifest.run_id != candidate.run_id:
                raise _ReplayContractError("ManifestRunMismatchError")
            if manifest.similarity_mode == "disabled":
                if candidate.similarity_summary is not None or any(
                    screen.similarity_result is not None for screen in candidate.screens
                ):
                    raise _ReplayContractError("DisabledSimilarityMismatchError")
                return CandidateSimilarityReplay(candidate, candidate, "manifest_disabled", ())
            if manifest.similarity_mode != "record" or similarity_config is not None:
                raise _ReplayContractError("SimilarityConfigOverrideError")
            try:
                config = similarity_config_from_snapshot(manifest.similarity_config)
            except Exception as exc:
                raise _ReplayContractError("ManifestSimilarityConfigError") from exc
            if (
                manifest.similarity_config_digest != similarity_config_digest(manifest.similarity_config)
                or manifest.similarity_version != config.similarity_version
                or manifest.similarity_config_version != config.similarity_config_version
            ):
                raise _ReplayContractError("ManifestSimilarityConfigMismatchError")
            rebuilt = _similarity_document(
                candidate, _evaluate_r06_screens(candidate.screens, config), config
            )
            if rebuilt != candidate:
                raise _ReplayContractError("SimilarityReplayMismatchError")
            return CandidateSimilarityReplay(candidate, rebuilt, "manifest", ())
        if similarity_config is None:
            raise _ReplayContractError("HistoricalSimilarityConfigRequiredError")
        if storage_version == "1.2.0":
            rebuilt = _similarity_document(
                candidate, _evaluate_r06_screens(candidate.screens, similarity_config), similarity_config
            )
            return CandidateSimilarityReplay(candidate, rebuilt, "caller_config", ())
        if aggregation_config is None:
            raise _ReplayContractError("HistoricalAggregationConfigRequiredError")
        if storage_version == "1.1.0":
            r05_candidate = _r05_rebuild_for_similarity(candidate, aggregation_config)
            rebuilt = _similarity_document(
                r05_candidate,
                _evaluate_r06_screens(r05_candidate.screens, similarity_config),
                similarity_config,
            )
            return CandidateSimilarityReplay(candidate, rebuilt, "caller_config", ())
        if storage_version == "1.0.0":
            if normalization_config is None:
                raise _ReplayContractError("HistoricalNormalizationConfigRequiredError")
            normalized = tuple(
                replay_screen_normalization(screen, config=normalization_config).normalized
                for screen in candidate.screens
            )
            r04_candidate = CandidateOcrDocument(
                run_id=candidate.run_id,
                candidate_record_id=candidate.candidate_record_id,
                sequence_number=candidate.sequence_number,
                created_at=candidate.created_at,
                completed_at=candidate.completed_at,
                capture_status=candidate.capture_status,
                screens=normalized,
                capture_summary=candidate.capture_summary,
                document_version=DOCUMENT_VERSION,
                storage_schema_version=R04_STORAGE_SCHEMA_VERSION,
                versions={
                    "normalization": (
                        normalized[0].normalization_version if normalized else None
                    ),
                },
                metadata=candidate.metadata,
            )
            r05_candidate = _r05_rebuild_for_similarity(r04_candidate, aggregation_config)
            rebuilt = _similarity_document(
                r05_candidate,
                _evaluate_r06_screens(r05_candidate.screens, similarity_config),
                similarity_config,
            )
            return CandidateSimilarityReplay(candidate, rebuilt, "caller_config", ())
        raise _ReplayContractError("UnsupportedStorageSchemaError")
    except Exception as exc:
        error_type = exc.error_type if isinstance(exc, _ReplayContractError) else type(exc).__name__
        if strict:
            raise _candidate_similarity_replay_error(error_type) from exc
        return CandidateSimilarityReplay(
            candidate,
            None,
            "unavailable",
            (_candidate_similarity_replay_issue(error_type),),
        )


def _tolerant_candidate_rebuild(
    candidate: CandidateOcrDocument,
    config: OcrAggregationConfig,
) -> Tuple[CandidateOcrDocument, Tuple[ReplayIssue, ...]]:
    """Rebuild malformed candidate membership conservatively and in memory."""

    screens = tuple(candidate.screens)
    formal_positions = tuple(
        (position, screen)
        for position, screen in enumerate(screens)
        if screen.capture_type.value == "formal_screen" and screen.is_formal_screen
    )
    ordered_formal = tuple(sorted(
        formal_positions,
        key=lambda item: (
            item[1].screen_index
            if isinstance(item[1].screen_index, int)
            and not isinstance(item[1].screen_index, bool)
            else -1,
            item[0],
        ),
    ))
    issue_codes = []
    warning_by_position: Dict[int, str] = {}
    first_index_position: Dict[int, int] = {}
    first_screen_by_id: Dict[str, OcrScreenRecord] = {}
    previous_index = 0
    has_out_of_order = False
    for position, screen in formal_positions:
        if not isinstance(screen.screen_index, int) or isinstance(screen.screen_index, bool):
            warning_by_position[position] = "formal_screen_out_of_order"
            if "formal_screen_out_of_order" not in issue_codes:
                issue_codes.append("formal_screen_out_of_order")
            continue
        if screen.screen_index <= previous_index:
            has_out_of_order = True
        previous_index = screen.screen_index
        prior_index_position = first_index_position.get(screen.screen_index)
        if prior_index_position is None:
            first_index_position[screen.screen_index] = position
        else:
            warning_by_position[position] = "duplicate_formal_screen_index"
            if "duplicate_formal_screen_index" not in issue_codes:
                issue_codes.append("duplicate_formal_screen_index")
        prior_screen = first_screen_by_id.get(screen.screen_id)
        if prior_screen is None:
            first_screen_by_id[screen.screen_id] = screen
        elif prior_screen != screen:
            warning_by_position[position] = "duplicate_screen_id_conflict"
            if "duplicate_screen_id_conflict" not in issue_codes:
                issue_codes.append("duplicate_screen_id_conflict")
    if has_out_of_order:
        if "formal_screen_out_of_order" not in issue_codes:
            issue_codes.append("formal_screen_out_of_order")
        # Stable sorting establishes a deterministic authority order, but no
        # formerly out-of-order formal screen is treated as fully trusted.
        for position, _screen in formal_positions:
            warning_by_position.setdefault(position, "formal_screen_out_of_order")

    builder = CandidateOcrBuilder(
        candidate.run_id,
        candidate.sequence_number,
        candidate_record_id=candidate.candidate_record_id,
        created_at=candidate.created_at,
        metadata=candidate.metadata,
        aggregation_mode="record",
        aggregation_config=config,
        similarity_mode="disabled",
    )
    projected_by_position: Dict[int, OcrScreenRecord] = {}
    for position, screen in ordered_formal:
        result = builder._aggregator.add_screen(  # candidate-local, no I/O
            screen,
            force_uncertain_warning=warning_by_position.get(position),
        )
        projected_by_position[position] = replace(
            screen,
            storage_schema_version=STORAGE_SCHEMA_VERSION,
            **aggregation_screen_record_fields(screen, result, config),
        )
    for position, screen in enumerate(screens):
        if position in projected_by_position:
            continue
        result = builder._aggregator.add_screen(screen)
        projected_by_position[position] = replace(
            screen,
            storage_schema_version=STORAGE_SCHEMA_VERSION,
            **aggregation_screen_record_fields(screen, result, config),
        )
    builder._screens.extend(projected_by_position[position] for position in range(len(screens)))
    rebuilt = builder.finalize(
        candidate.capture_status,
        end_reason=candidate.capture_summary.end_reason,
        abort_reason=candidate.capture_summary.abort_reason,
        completed_at=candidate.completed_at,
    )
    return rebuilt, tuple(_candidate_replay_issue(code) for code in issue_codes)


def replay_candidate_aggregation(
    candidate: CandidateOcrDocument,
    manifest: RunManifest,
    *,
    strict: bool = True,
    aggregation_config: Optional[OcrAggregationConfig] = None,
) -> CandidateAggregationReplay:
    """Replay R05 with explicit historical config and no source side effects."""

    try:
        if not isinstance(candidate, CandidateOcrDocument) or not isinstance(manifest, RunManifest):
            raise _ReplayContractError("InvalidCandidateAggregationInputError")
        if candidate.run_id != manifest.run_id:
            raise _ReplayContractError("ManifestRunMismatchError")
        similarity_mode = "disabled"
        similarity_config = DEFAULT_OCR_SIMILARITY_CONFIG
        if candidate.storage_schema_version in R06_AND_LATER_STORAGE_SCHEMA_VERSIONS:
            if manifest.storage_schema_version != candidate.storage_schema_version:
                raise _ReplayContractError("ManifestSchemaMismatchError")
            if manifest.aggregation_mode == "disabled":
                if candidate.document_build_status != DocumentBuildStatus.NOT_ATTEMPTED:
                    raise _ReplayContractError("DisabledAggregationMismatchError")
                return CandidateAggregationReplay(candidate, candidate, "manifest_disabled", ())
            if manifest.aggregation_mode != "record" or aggregation_config is not None:
                raise _ReplayContractError("AggregationConfigOverrideError")
            try:
                config = restore_aggregation_config(manifest.aggregation_config)
            except Exception as exc:
                raise _ReplayContractError("ManifestAggregationConfigError") from exc
            if (
                manifest.aggregation_config_digest != aggregation_config_digest(manifest.aggregation_config)
                or candidate.aggregation_config_version != manifest.aggregation_config_version
                or candidate.aggregation_config_digest != manifest.aggregation_config_digest
            ):
                raise _ReplayContractError("ManifestAggregationConfigMismatchError")
            if manifest.similarity_mode == "record":
                try:
                    similarity_config = similarity_config_from_snapshot(
                        manifest.similarity_config
                    )
                except Exception as exc:
                    raise _ReplayContractError(
                        "ManifestSimilarityConfigError"
                    ) from exc
                if (
                    manifest.similarity_config_digest
                    != similarity_config_digest(manifest.similarity_config)
                    or candidate.similarity_summary is None
                ):
                    raise _ReplayContractError(
                        "ManifestSimilarityConfigMismatchError"
                    )
                similarity_mode = "record"
            elif manifest.similarity_mode == "disabled":
                if candidate.similarity_summary is not None:
                    raise _ReplayContractError("DisabledSimilarityMismatchError")
            else:
                raise _ReplayContractError("ManifestSimilarityModeError")
            config_source = "manifest"
        elif candidate.storage_schema_version == R04_STORAGE_SCHEMA_VERSION:
            if aggregation_config is None:
                raise _ReplayContractError("HistoricalAggregationConfigRequiredError")
            config = aggregation_config
            config_source = "caller_override"
        elif candidate.storage_schema_version == LEGACY_STORAGE_SCHEMA_VERSION:
            raise _ReplayContractError("LegacyR04ReplayRequiredError")
        else:
            raise _ReplayContractError("UnsupportedStorageSchemaError")
        formal = [
            screen for screen in candidate.screens
            if screen.capture_type.value == "formal_screen" and screen.is_formal_screen
        ]
        identities = set()
        last_index = 0
        malformed = False
        for screen in formal:
            if screen.screen_id in identities or not isinstance(screen.screen_index, int) or screen.screen_index <= last_index:
                malformed = True
            identities.add(screen.screen_id)
            last_index = screen.screen_index
        if malformed and strict:
            raise _ReplayContractError("DuplicateOrOutOfOrderFormalScreenError")
        if malformed:
            rebuilt, issues = _tolerant_candidate_rebuild(candidate, config)
            return CandidateAggregationReplay(candidate, rebuilt, config_source, issues)
        builder = CandidateOcrBuilder(
            candidate.run_id,
            candidate.sequence_number,
            candidate_record_id=candidate.candidate_record_id,
            created_at=candidate.created_at,
            metadata=candidate.metadata,
            aggregation_mode="record",
            aggregation_config=config,
            similarity_mode=similarity_mode,
            similarity_config=similarity_config,
        )
        for screen in candidate.screens:
            builder.add_screen(screen)
        rebuilt = builder.finalize(
            candidate.capture_status,
            end_reason=candidate.capture_summary.end_reason,
            abort_reason=candidate.capture_summary.abort_reason,
            completed_at=candidate.completed_at,
        )
        if candidate.storage_schema_version == STORAGE_SCHEMA_VERSION and rebuilt != candidate:
            raise _ReplayContractError("AggregationReplayMismatchError")
        return CandidateAggregationReplay(candidate, rebuilt, config_source, ())
    except Exception as exc:
        error_type = exc.error_type if isinstance(exc, _ReplayContractError) else type(exc).__name__
        if strict:
            raise _candidate_replay_error(error_type) from exc
        return CandidateAggregationReplay(
            candidate, None, "unavailable", (_candidate_replay_issue(error_type),)
        )


def load_ocr_run(run_dir: Path, *, strict: bool = True) -> OcrRunReplay:
    """Load raw stage-0 records; no normalization or aggregation is performed."""

    reader = OcrRunReader(run_dir, strict=strict)
    manifest = reader.read_manifest()
    screens = list(reader.iter_screens())
    candidates = list(reader.iter_candidates())
    errors = list(reader.iter_errors())
    return OcrRunReplay(
        manifest=manifest,
        screens=screens,
        candidates=candidates,
        errors=errors,
        issues=list(reader.issues),
    )
