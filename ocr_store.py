"""Thread-safe, best-effort JSONL persistence for stage-0 OCR records."""

from datetime import datetime
import hashlib
import logging
import os
from pathlib import Path
import platform as platform_module
import re
import sys
import threading
from typing import Any, Dict, Mapping, Optional, Protocol, Set, Tuple
from uuid import uuid4

from ocr_normalization import (
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NORMALIZATION_VERSION,
    canonical_normalization_config,
    config_with_effective_min_confidence,
    normalization_config_digest as calculate_normalization_config_digest,
    normalization_config_from_snapshot,
)
from ocr_aggregation import (
    AGGREGATION_CONFIG_VERSION,
    AGGREGATION_VERSION,
    DEFAULT_OCR_AGGREGATION_CONFIG,
    OcrAggregationConfig,
    aggregation_config_digest,
    aggregation_config_snapshot,
)
from ocr_similarity import (
    DEFAULT_OCR_SIMILARITY_CONFIG,
    OcrSimilarityConfig,
    canonical_similarity_config,
    similarity_config_digest,
)

from ocr_records import (
    CandidateOcrDocument,
    DocumentBuildStatus,
    OcrScreenRecord,
    RunManifest,
    RunStatus,
    ScreeningProfileBinding,
    STORAGE_SCHEMA_VERSION,
    json_dumps,
    timezone_iso,
    to_json_compatible,
)


logger = logging.getLogger(__name__)

DEFAULT_OCR_RUNS_ROOT = Path("data") / "ocr_runs"
RUN_MANIFEST_NAME = "run.json"
SCREENS_NAME = "screens.jsonl"
CANDIDATES_NAME = "candidates.jsonl"
ERRORS_NAME = "errors.jsonl"
DEFAULT_CONSECUTIVE_FAILURE_LIMIT = 3
RULE_EVALUATION_MODE_LEGACY_SHADOW = "legacy_shadow"
_SAFE_DIAGNOSTIC_TOKEN = re.compile(r"^[a-z0-9_]{1,64}$")
_SAFE_FAILURE_STAGES = frozenset({
    "screen_record_validation",
    "position_classification",
    "store_screen",
    "candidate_validation",
    "store_candidate",
    "r05_projection",
    "r06_projection",
})
_SAFE_DIAGNOSTIC_MESSAGES = frozenset({
    "aggregation segment classifications are invalid",
    "document occurrence screen is invalid",
    "similarity projection does not match nested result",
    "effective-new boolean does not match confirmed segments",
    "validation failed",
    "operation failed",
})


class ScreenManifestIdentityMismatchError(ValueError):
    """Sanitized rejection for a screen produced under another run config."""


class OcrRecordStore(Protocol):
    """Persistence boundary used by the candidate loop."""

    def save_screen(self, record: OcrScreenRecord) -> bool:
        ...

    def save_candidate(
        self,
        document: CandidateOcrDocument,
        *,
        owner_candidate_record_id: Optional[str] = None,
    ) -> bool:
        ...

    def save_error(
        self,
        error_type: str,
        operation: str,
        context: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        ...

    def close(self, status: RunStatus = RunStatus.COMPLETED) -> bool:
        ...


class JsonlOcrRecordStore:
    """Append complete JSON objects while keeping storage off the critical path."""

    def __init__(
        self,
        root_dir: Path = DEFAULT_OCR_RUNS_ROOT,
        *,
        action_mode: Optional[str] = None,
        max_screen_count: Optional[int] = None,
        app_version: Optional[str] = None,
        git_commit: Optional[str] = None,
        normalization_version: Optional[str] = None,
        ocr_min_confidence: Optional[float] = None,
        normalization_config_version: Optional[str] = None,
        normalization_config_digest: Optional[str] = None,
        effective_min_confidence: Optional[float] = None,
        normalization_config: Optional[Mapping[str, Any]] = None,
        aggregation_mode: str = "disabled",
        aggregation_config: Optional[OcrAggregationConfig] = None,
        similarity_mode: str = "disabled",
        similarity_config: Optional[OcrSimilarityConfig] = None,
        rule_evaluation_mode: str = RULE_EVALUATION_MODE_LEGACY_SHADOW,
        dynamic_end_version: Optional[str] = None,
        dynamic_end_mode: Optional[str] = None,
        dynamic_end_config: Optional[Mapping[str, Any]] = None,
        screening_profile_binding: Optional[ScreeningProfileBinding] = None,
        fsync: bool = False,
        run_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        consecutive_failure_limit: int = DEFAULT_CONSECUTIVE_FAILURE_LIMIT,
    ) -> None:
        if consecutive_failure_limit < 1:
            raise ValueError("consecutive_failure_limit must be at least 1")
        if aggregation_mode not in ("disabled", "record"):
            raise ValueError("aggregation_mode must be disabled or record")
        if aggregation_config is not None and not isinstance(aggregation_config, OcrAggregationConfig):
            raise TypeError("aggregation_config must be an OcrAggregationConfig")
        if similarity_mode not in ("disabled", "record"):
            raise ValueError("similarity_mode must be disabled or record")
        if similarity_config is not None and not isinstance(similarity_config, OcrSimilarityConfig):
            raise TypeError("similarity_config must be an OcrSimilarityConfig")
        if dynamic_end_mode is not None and dynamic_end_mode not in (
            "off", "shadow", "safe", "full",
        ):
            raise ValueError("dynamic_end_mode must be off, shadow, safe, or full")
        if dynamic_end_config is not None and not isinstance(dynamic_end_config, Mapping):
            raise TypeError("dynamic_end_config must be a mapping")

        self._lock = threading.RLock()
        self._fsync = bool(fsync)
        self._closed = False
        self._enabled = False
        self._consecutive_failures = 0
        self._consecutive_failure_limit = consecutive_failure_limit
        self._closed_call_reported = False
        # A digest gives field-for-field JSONL equivalence without retaining
        # candidate OCR body in memory after the append operation.
        self._saved_screen_digests: Dict[Tuple[str, str, str], str] = {}
        # This is Store-owned lifetime state, established only after a screen
        # line has been written successfully.  It deliberately does not use
        # the later candidate document's embedded screens to discover owner
        # keys: those fields have not yet passed strict validation.
        self._candidate_screen_digest_keys: Dict[
            Tuple[str, str], Set[Tuple[str, str, str]]
        ] = {}

        current = datetime.now().astimezone() if started_at is None else started_at
        started_at_text = timezone_iso(current)
        self.run_id = str(run_id or uuid4())
        safe_run_id = re.sub(r"[^A-Za-z0-9_.-]", "_", self.run_id)
        directory_name = "{0}_{1}".format(
            current.strftime("%Y%m%dT%H%M%S%z"), safe_run_id
        )
        self.root_dir = Path(root_dir)
        self.run_dir = self.root_dir / directory_name
        self.manifest_path = self.run_dir / RUN_MANIFEST_NAME
        self.screens_path = self.run_dir / SCREENS_NAME
        self.candidates_path = self.run_dir / CANDIDATES_NAME
        self.errors_path = self.run_dir / ERRORS_NAME
        threshold = (
            effective_min_confidence
            if effective_min_confidence is not None
            else ocr_min_confidence
            if ocr_min_confidence is not None
            else DEFAULT_OCR_NORMALIZATION_CONFIG.effective_min_confidence
        )
        if normalization_config is None:
            run_config = config_with_effective_min_confidence(
                DEFAULT_OCR_NORMALIZATION_CONFIG,
                threshold,
            )
            config_snapshot = canonical_normalization_config(run_config)
        else:
            config_snapshot = dict(normalization_config)
            run_config = normalization_config_from_snapshot(config_snapshot)
        if (
            effective_min_confidence is not None
            and float(effective_min_confidence)
            != float(run_config.effective_min_confidence)
        ):
            raise ValueError("effective confidence does not match normalization config")
        if (
            ocr_min_confidence is not None
            and float(ocr_min_confidence)
            != float(run_config.effective_min_confidence)
        ):
            raise ValueError("OCR confidence does not match normalization config")
        actual_version = normalization_version or NORMALIZATION_VERSION
        actual_config_version = (
            normalization_config_version
            or run_config.normalization_config_version
        )
        actual_digest = (
            normalization_config_digest
            or calculate_normalization_config_digest(config_snapshot)
        )
        active_similarity_config = similarity_config or DEFAULT_OCR_SIMILARITY_CONFIG
        similarity_snapshot = (
            canonical_similarity_config(active_similarity_config)
            if similarity_mode == "record" else None
        )
        self.manifest = RunManifest(
            run_id=self.run_id,
            started_at=started_at_text,
            status=RunStatus.RUNNING,
            platform=platform_module.system() or sys.platform,
            python_version=platform_module.python_version(),
            action_mode=action_mode,
            max_screen_count=max_screen_count,
            app_version=app_version,
            git_commit=git_commit,
            normalization_version=actual_version,
            normalization_config_version=actual_config_version,
            normalization_config_digest=actual_digest,
            effective_min_confidence=run_config.effective_min_confidence,
            normalization_config=config_snapshot,
            rule_evaluation_mode=rule_evaluation_mode,
            ocr_min_confidence=ocr_min_confidence,
            aggregation_mode=aggregation_mode,
            aggregation_version=(AGGREGATION_VERSION if aggregation_mode == "record" else None),
            aggregation_config_version=(AGGREGATION_CONFIG_VERSION if aggregation_mode == "record" else None),
            aggregation_config_digest=(
                aggregation_config_digest(aggregation_config or DEFAULT_OCR_AGGREGATION_CONFIG)
                if aggregation_mode == "record" else None
            ),
            aggregation_config=(
                aggregation_config_snapshot(aggregation_config or DEFAULT_OCR_AGGREGATION_CONFIG)
                if aggregation_mode == "record" else None
            ),
            similarity_mode=similarity_mode,
            similarity_version=(
                active_similarity_config.similarity_version
                if similarity_mode == "record" else None
            ),
            similarity_config_version=(
                active_similarity_config.similarity_config_version
                if similarity_mode == "record" else None
            ),
            similarity_config_digest=(
                similarity_config_digest(similarity_snapshot)
                if similarity_snapshot is not None else None
            ),
            similarity_config=similarity_snapshot,
            business_short_terms_version=(
                active_similarity_config.business_short_terms_version
                if similarity_mode == "record" else None
            ),
            business_short_terms_digest=(
                active_similarity_config.business_short_terms_digest()
                if similarity_mode == "record" else None
            ),
            dynamic_end_version=dynamic_end_version,
            dynamic_end_mode=dynamic_end_mode,
            dynamic_end_config=(
                dict(dynamic_end_config)
                if dynamic_end_config is not None else None
            ),
            screening_profile_binding=screening_profile_binding,
            data_files={
                "manifest": RUN_MANIFEST_NAME,
                "screens": SCREENS_NAME,
                "candidates": CANDIDATES_NAME,
                "errors": ERRORS_NAME,
            },
        )
        try:
            self._initialize_files()
        except Exception as exc:
            self.manifest.error_count += 1
            self.manifest.status = RunStatus.DISABLED
            logger.warning(
                "event=ocr_store_initialization_failed error_type=%s",
                type(exc).__name__,
            )
        else:
            self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled and not self._closed

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def fsync_enabled(self) -> bool:
        return self._fsync

    def _initialize_files(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=False, exist_ok=False)
        for path in (
            self.screens_path,
            self.candidates_path,
            self.errors_path,
        ):
            with path.open("x", encoding="utf-8", newline=""):
                pass
        self._write_manifest_atomic()

    def _write_manifest_atomic(self) -> None:
        serialized = json_dumps(self.manifest)
        temporary_path = self.run_dir / ".run.{0}.tmp".format(uuid4().hex)
        try:
            with temporary_path.open("x", encoding="utf-8", newline="") as handle:
                handle.write(serialized)
                handle.write("\n")
                handle.flush()
                if self._fsync:
                    os.fsync(handle.fileno())
            os.replace(str(temporary_path), str(self.manifest_path))
        except Exception:
            try:
                temporary_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def _append_line(self, path: Path, value: Any) -> None:
        serialized = json_dumps(value)
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(serialized + "\n")
            handle.flush()
            if self._fsync:
                os.fsync(handle.fileno())

    @staticmethod
    def _safe_context(
        context: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        if not context:
            return {}
        allowed = {
            "candidate_record_id",
            "screen_id",
            "record_type",
            "line_number",
            "path",
            "capture_type",
        }
        safe = {
            key: to_json_compatible(value)
            for key, value in context.items()
            if key in allowed
        }
        failure_stage = context.get("failure_stage")
        if failure_stage in _SAFE_FAILURE_STAGES:
            safe["failure_stage"] = failure_stage
        validation_code = context.get("validation_code")
        if (
            isinstance(validation_code, str)
            and _SAFE_DIAGNOSTIC_TOKEN.fullmatch(validation_code) is not None
        ):
            safe["validation_code"] = validation_code
        sanitized_message = context.get("sanitized_error_message")
        if sanitized_message in _SAFE_DIAGNOSTIC_MESSAGES:
            safe["sanitized_error_message"] = sanitized_message
        return safe

    def _error_record(
        self,
        error_type: str,
        operation: str,
        context: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "record_type": "storage_error",
            "storage_schema_version": STORAGE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "occurred_at": timezone_iso(),
            "operation": operation,
            "error_type": error_type,
            "context": self._safe_context(context),
        }

    def _record_failure(
        self,
        operation: str,
        exc: Exception,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.manifest.error_count += 1
        self._consecutive_failures += 1
        logger.warning(
            "event=ocr_store_write_failed operation=%s error_type=%s "
            "consecutive_failures=%s",
            operation,
            type(exc).__name__,
            self._consecutive_failures,
        )
        if operation != "save_error":
            try:
                self._append_line(
                    self.errors_path,
                    self._error_record(type(exc).__name__, operation, context),
                )
            except Exception:
                pass
        if self._consecutive_failures >= self._consecutive_failure_limit:
            self._enabled = False
            self.manifest.status = RunStatus.DISABLED
            logger.error(
                "event=ocr_store_disabled consecutive_failures=%s",
                self._consecutive_failures,
            )

    def _can_write(self, operation: str) -> bool:
        if self._closed:
            if not self._closed_call_reported:
                self._closed_call_reported = True
                self.manifest.error_count += 1
                logger.warning(
                    "event=ocr_store_closed_call operation=%s", operation
                )
            return False
        return self._enabled

    def _save_record(
        self,
        path: Path,
        value: Any,
        operation: str,
        context: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        with self._lock:
            if not self._can_write(operation):
                return False
            try:
                self._append_line(path, value)
            except Exception as exc:
                self._record_failure(operation, exc, context)
                return False
            self._consecutive_failures = 0
            return True

    def save_screen(self, record: OcrScreenRecord) -> bool:
        context = {
            "candidate_record_id": getattr(
                record, "candidate_record_id", None
            ),
            "screen_id": getattr(record, "screen_id", None),
            "record_type": getattr(record, "record_type", None),
            "capture_type": getattr(record, "capture_type", None),
        }
        with self._lock:
            try:
                self._validate_screen_identity(record)
            except Exception as exc:
                self._record_failure("save_screen", exc, context)
                return False
            saved = self._save_record(
                self.screens_path, record, "save_screen", context
            )
            if saved:
                self.manifest.screen_record_count += 1
                key = self._screen_digest_key(record)
                if key is not None:
                    self._saved_screen_digests[key] = hashlib.sha256(
                        json_dumps(record).encode("utf-8")
                    ).hexdigest()
                    self._candidate_screen_digest_keys.setdefault(
                        key[:2], set()
                    ).add(key)
        return saved

    @staticmethod
    def _screen_digest_key(
        record: OcrScreenRecord,
    ) -> Optional[Tuple[str, str, str]]:
        """Return the internal digest key only for a concrete screen record."""

        if not isinstance(record, OcrScreenRecord):
            return None
        return (
            record.run_id,
            record.candidate_record_id,
            record.screen_id,
        )

    def _candidate_owner_key(
        self,
        document: CandidateOcrDocument,
        owner_candidate_record_id: Optional[str],
    ) -> Optional[Tuple[str, str]]:
        """Resolve terminal cleanup ownership without trusting embedded screens.

        The production call path supplies the Builder's candidate identity.
        The document identity remains a compatibility fallback only when every
        embedded screen agrees with it.  An identity disagreement can therefore
        never make an embedded screen select another candidate's cache.
        """

        if owner_candidate_record_id is not None:
            if not isinstance(owner_candidate_record_id, str) or not owner_candidate_record_id:
                return None
            return (self.run_id, owner_candidate_record_id)
        if (
            isinstance(document, CandidateOcrDocument)
            and document.run_id == self.run_id
            and all(
                isinstance(screen, OcrScreenRecord)
                and screen.run_id == document.run_id
                and screen.candidate_record_id == document.candidate_record_id
                for screen in document.screens
            )
        ):
            return (self.run_id, document.candidate_record_id)
        return None

    def _release_candidate_screen_digests(
        self,
        owner_key: Optional[Tuple[str, str]],
    ) -> None:
        """Idempotently release Store-owned keys for one terminal candidate."""

        if owner_key is None:
            return
        for key in self._candidate_screen_digest_keys.pop(owner_key, set()):
            self._saved_screen_digests.pop(key, None)

    @staticmethod
    def _validate_explicit_candidate_owner(
        document: CandidateOcrDocument,
        owner_candidate_record_id: Optional[str],
    ) -> None:
        """Bind a trusted terminal owner to the document before persistence."""

        if owner_candidate_record_id is None:
            return
        if (
            not isinstance(document, CandidateOcrDocument)
            or owner_candidate_record_id != document.candidate_record_id
        ):
            raise ScreenManifestIdentityMismatchError(
                "trusted owner and candidate document identities do not match"
            )

    def _validate_screen_identity(self, record: OcrScreenRecord) -> None:
        if not isinstance(record, OcrScreenRecord):
            return
        if record.normalization_status.value != "not_attempted":
            screen_identity = (
                record.normalization_version,
                record.normalization_config_version,
                record.normalization_config_digest,
                record.effective_min_confidence,
                record.rule_evaluation_mode,
            )
            manifest_identity = (
                self.manifest.normalization_version,
                self.manifest.normalization_config_version,
                self.manifest.normalization_config_digest,
                self.manifest.effective_min_confidence,
                self.manifest.rule_evaluation_mode,
            )
            if screen_identity != manifest_identity:
                raise ScreenManifestIdentityMismatchError(
                    "screen normalization identity does not match run manifest"
                )
        if record.aggregation_status.value == "not_attempted":
            if self.manifest.aggregation_mode == "record" and (
                record.capture_type.value == "formal_screen" and record.is_formal_screen
            ):
                raise ScreenManifestIdentityMismatchError(
                    "formal screen aggregation was not attempted in record mode"
                )
        else:
            aggregation_identity = (
                record.aggregation_version,
                record.aggregation_config_version,
                record.aggregation_config_digest,
            )
            manifest_aggregation_identity = (
                self.manifest.aggregation_version,
                self.manifest.aggregation_config_version,
                self.manifest.aggregation_config_digest,
            )
            if (
                self.manifest.aggregation_mode != "record"
                or aggregation_identity != manifest_aggregation_identity
            ):
                raise ScreenManifestIdentityMismatchError(
                    "screen aggregation identity does not match run manifest"
                )
        result = record.similarity_result
        if self.manifest.similarity_mode == "disabled":
            if result is not None:
                raise ScreenManifestIdentityMismatchError(
                    "disabled manifest cannot save a similarity result"
                )
            return
        if result is None:
            raise ScreenManifestIdentityMismatchError(
                "record similarity mode requires a completed similarity projection"
            )
        screen_similarity_identity = (
            result.similarity_version,
            result.similarity_config_version,
            result.similarity_config_digest,
        )
        manifest_similarity_identity = (
            self.manifest.similarity_version,
            self.manifest.similarity_config_version,
            self.manifest.similarity_config_digest,
        )
        if screen_similarity_identity != manifest_similarity_identity:
            raise ScreenManifestIdentityMismatchError(
                "screen similarity identity does not match run manifest"
            )

    @staticmethod
    def _validate_candidate_embedded_screen_identities(
        document: CandidateOcrDocument,
    ) -> None:
        """Require each persisted candidate member to carry document identity."""

        if not isinstance(document, CandidateOcrDocument):
            return
        for screen in document.screens:
            if not isinstance(screen, OcrScreenRecord):
                continue
            if (
                screen.run_id != document.run_id
                or screen.candidate_record_id != document.candidate_record_id
            ):
                raise ScreenManifestIdentityMismatchError(
                    "candidate and embedded screen identities do not match"
                )

    def save_candidate(
        self,
        document: CandidateOcrDocument,
        *,
        owner_candidate_record_id: Optional[str] = None,
    ) -> bool:
        context = {
            "candidate_record_id": getattr(
                document, "candidate_record_id", None
            ),
            "record_type": getattr(document, "record_type", None),
        }
        with self._lock:
            owner_key = self._candidate_owner_key(
                document, owner_candidate_record_id,
            )
            try:
                self._validate_explicit_candidate_owner(
                    document, owner_candidate_record_id,
                )
                self._validate_candidate_embedded_screen_identities(document)
                for screen in document.screens:
                    self._validate_screen_identity(screen)
                if document.run_id != self.run_id:
                    raise ScreenManifestIdentityMismatchError("candidate run identity does not match store")
                if document.document_build_status == DocumentBuildStatus.NOT_ATTEMPTED:
                    if (
                        self.manifest.aggregation_mode == "record"
                        and any(screen.is_formal_screen for screen in document.screens)
                    ):
                        raise ScreenManifestIdentityMismatchError(
                            "formal candidate has a not-attempted aggregation document"
                        )
                elif (
                    document.versions.get("aggregation") != self.manifest.aggregation_version
                    or document.aggregation_config_version != self.manifest.aggregation_config_version
                    or document.aggregation_config_digest != self.manifest.aggregation_config_digest
                ):
                    raise ScreenManifestIdentityMismatchError(
                        "candidate aggregation identity does not match run manifest"
                    )
                if self.manifest.similarity_mode == "disabled":
                    if document.similarity_summary is not None:
                        raise ScreenManifestIdentityMismatchError(
                            "disabled manifest cannot save a similarity summary"
                        )
                else:
                    summary = document.similarity_summary
                    if summary is None:
                        raise ScreenManifestIdentityMismatchError(
                            "record similarity mode requires a candidate summary"
                        )
                    if (
                        summary.similarity_version != self.manifest.similarity_version
                        or summary.similarity_config_version != self.manifest.similarity_config_version
                        or summary.similarity_config_digest != self.manifest.similarity_config_digest
                    ):
                        raise ScreenManifestIdentityMismatchError(
                            "candidate similarity identity does not match run manifest"
                        )
                for screen in document.screens:
                    expected_digest = self._saved_screen_digests.get(
                        self._screen_digest_key(screen)
                    )
                    actual_digest = hashlib.sha256(
                        json_dumps(screen).encode("utf-8")
                    ).hexdigest()
                    if expected_digest is None or actual_digest != expected_digest:
                        raise ScreenManifestIdentityMismatchError(
                            "screen JSONL and candidate screen are not identical"
                        )
            except Exception as exc:
                self._record_failure("save_candidate", exc, context)
                return False
            else:
                saved = self._save_record(
                    self.candidates_path,
                    document,
                    "save_candidate",
                    context,
                )
                if saved:
                    self.manifest.candidate_record_count += 1
                return saved
            finally:
                self._release_candidate_screen_digests(owner_key)

    def save_error(
        self,
        error_type: str,
        operation: str,
        context: Optional[Mapping[str, Any]] = None,
    ) -> bool:
        with self._lock:
            if not self._can_write("save_error"):
                return False
            self.manifest.error_count += 1
            record = self._error_record(error_type, operation, context)
            try:
                self._append_line(self.errors_path, record)
            except Exception as exc:
                self._record_failure("save_error", exc, context)
                return False
            self._consecutive_failures = 0
            return True

    def close(self, status: RunStatus = RunStatus.COMPLETED) -> bool:
        with self._lock:
            if self._closed:
                return True
            self._closed = True
            self.manifest.ended_at = timezone_iso()
            if self.manifest.status != RunStatus.DISABLED:
                self.manifest.status = (
                    status
                    if isinstance(status, RunStatus)
                    else RunStatus(status)
                )
            try:
                if self.run_dir.is_dir():
                    self._write_manifest_atomic()
                else:
                    return False
            except Exception as exc:
                self.manifest.error_count += 1
                logger.warning(
                    "event=ocr_store_finalize_failed error_type=%s",
                    type(exc).__name__,
                )
                return False
            finally:
                # Closing is the terminal Store boundary, including runs with
                # screens that never reached a candidate document.
                self._saved_screen_digests.clear()
                self._candidate_screen_digest_keys.clear()
                self._enabled = False
            return True

    def finalize(self, status: RunStatus = RunStatus.COMPLETED) -> bool:
        return self.close(status)

    def __enter__(self) -> "JsonlOcrRecordStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        status = RunStatus.ERROR if exc_type is not None else RunStatus.COMPLETED
        self.close(status)
