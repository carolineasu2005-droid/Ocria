"""Thread-safe, best-effort JSONL persistence for stage-0 OCR records."""

from datetime import datetime
import logging
import os
from pathlib import Path
import platform as platform_module
import re
import sys
import threading
from typing import Any, Dict, Mapping, Optional, Protocol
from uuid import uuid4

from ocr_normalization import (
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NORMALIZATION_VERSION,
    canonical_normalization_config,
    config_with_effective_min_confidence,
    normalization_config_digest as calculate_normalization_config_digest,
    normalization_config_from_snapshot,
)

from ocr_records import (
    CandidateOcrDocument,
    OcrScreenRecord,
    RunManifest,
    RunStatus,
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


class ScreenManifestIdentityMismatchError(ValueError):
    """Sanitized rejection for a screen produced under another run config."""


class OcrRecordStore(Protocol):
    """Persistence boundary used by the candidate loop."""

    def save_screen(self, record: OcrScreenRecord) -> bool:
        ...

    def save_candidate(self, document: CandidateOcrDocument) -> bool:
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
        rule_evaluation_mode: str = RULE_EVALUATION_MODE_LEGACY_SHADOW,
        fsync: bool = False,
        run_id: Optional[str] = None,
        started_at: Optional[datetime] = None,
        consecutive_failure_limit: int = DEFAULT_CONSECUTIVE_FAILURE_LIMIT,
    ) -> None:
        if consecutive_failure_limit < 1:
            raise ValueError("consecutive_failure_limit must be at least 1")

        self._lock = threading.RLock()
        self._fsync = bool(fsync)
        self._closed = False
        self._enabled = False
        self._consecutive_failures = 0
        self._consecutive_failure_limit = consecutive_failure_limit
        self._closed_call_reported = False

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
        return {
            key: to_json_compatible(value)
            for key, value in context.items()
            if key in allowed
        }

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
        return saved

    def _validate_screen_identity(self, record: OcrScreenRecord) -> None:
        if not isinstance(record, OcrScreenRecord):
            return
        if record.normalization_status.value == "not_attempted":
            return
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

    def save_candidate(self, document: CandidateOcrDocument) -> bool:
        context = {
            "candidate_record_id": getattr(
                document, "candidate_record_id", None
            ),
            "record_type": getattr(document, "record_type", None),
        }
        with self._lock:
            try:
                for screen in document.screens:
                    self._validate_screen_identity(screen)
            except Exception as exc:
                self._record_failure("save_candidate", exc, context)
                return False
            saved = self._save_record(
                self.candidates_path,
                document,
                "save_candidate",
                context,
            )
            if saved:
                self.manifest.candidate_record_count += 1
        return saved

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
                self._enabled = False
            return True

    def finalize(self, status: RunStatus = RunStatus.COMPLETED) -> bool:
        return self.close(status)

    def __enter__(self) -> "JsonlOcrRecordStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        status = RunStatus.ERROR if exc_type is not None else RunStatus.COMPLETED
        self.close(status)
