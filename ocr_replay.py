"""Offline loading of stage-0 OCR run records without later-stage processing."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Type, TypeVar

from ocr_records import (
    CandidateOcrDocument,
    OcrScreenRecord,
    RecordVersionError,
    RunManifest,
    SUPPORTED_DOCUMENT_VERSIONS,
    SUPPORTED_STORAGE_SCHEMA_VERSIONS,
    validate_record_version,
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
