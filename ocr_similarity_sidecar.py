"""Append-only, privacy-preserving R06 sidecar generation.

The sidecar never updates a source run, its JSONL files, or its manifest.  It
stores identities and R06 derived values only; OCR text, box geometry, and
contacts are deliberately absent from every line.
"""

from collections import Counter
import hashlib
from pathlib import Path
from typing import Iterable, Mapping, Optional

from ocr_records import (
    CandidateOcrDocument,
    CaptureType,
    OcrScreenRecord,
    RunManifest,
    json_dumps,
)
from ocr_replay import _evaluate_r06_screens, replay_candidate_similarity
from ocr_similarity import (
    DEFAULT_OCR_SIMILARITY_CONFIG,
    OcrSimilarityConfig,
    canonical_similarity_config,
    similarity_config_digest,
    similarity_config_from_snapshot,
)


class OcrSimilaritySidecarError(ValueError):
    """Sanitized sidecar failure; its message intentionally excludes OCR text."""


def _source_screen_digest(screen: OcrScreenRecord) -> str:
    return hashlib.sha256(json_dumps(screen).encode("utf-8")).hexdigest()


def similarity_statistics(
    candidates: Iterable[CandidateOcrDocument],
) -> Mapping[str, object]:
    """Return aggregate-only R06 calibration statistics without source text."""

    results = [
        screen.similarity_result
        for candidate in candidates
        for screen in candidate.screens
        if screen.similarity_result is not None
    ]
    status = Counter(item.similarity_status.value for item in results)
    classes = Counter(item.comparison_class.value for item in results)
    effective = Counter(item.effective_new_status.value for item in results)
    reasons = Counter(
        decision.reason_code
        for item in results
        for decision in item.effective_new_decisions
    )
    warnings = Counter(code for item in results for code in item.warning_codes)
    score_bins = Counter()
    ratio_bins = Counter()
    for item in results:
        if item.similarity_score is not None:
            score_bins["{0:.1f}-{1:.1f}".format(
                int(item.similarity_score * 10) / 10,
                min(1.0, (int(item.similarity_score * 10) + 1) / 10),
            )] += 1
        for ratio in (item.overlap_ratio, item.new_text_ratio, item.uncertain_ratio):
            if ratio is not None:
                ratio_bins["{0:.1f}-{1:.1f}".format(
                    int(ratio * 10) / 10,
                    min(1.0, (int(ratio * 10) + 1) / 10),
                )] += 1
    identities = {
        (item.similarity_version, item.similarity_config_version, item.similarity_config_digest)
        for item in results
    }
    return {
        "sample_count": len(results),
        "similarity_status_counts": dict(sorted(status.items())),
        "comparison_class_counts": dict(sorted(classes.items())),
        "effective_new_status_counts": dict(sorted(effective.items())),
        "reason_code_counts": dict(sorted(reasons.items())),
        "warning_counts": dict(sorted(warnings.items())),
        "similarity_score_distribution": dict(sorted(score_bins.items())),
        "ratio_distribution": dict(sorted(ratio_bins.items())),
        "identities": [list(item) for item in sorted(identities)],
    }


def _resolve_config(
    manifest: RunManifest,
    override: Optional[OcrSimilarityConfig],
) -> OcrSimilarityConfig:
    if override is not None:
        if not isinstance(override, OcrSimilarityConfig):
            raise OcrSimilaritySidecarError("invalid_sidecar_config")
        return override
    if manifest.similarity_mode == "record" and manifest.similarity_config is not None:
        try:
            return similarity_config_from_snapshot(manifest.similarity_config)
        except Exception as exc:
            raise OcrSimilaritySidecarError("invalid_source_similarity_config") from exc
    return DEFAULT_OCR_SIMILARITY_CONFIG


def write_similarity_sidecar(
    run_dir: Path,
    manifest: RunManifest,
    candidates: Iterable[CandidateOcrDocument],
    *,
    similarity_config: Optional[OcrSimilarityConfig] = None,
    strict: bool = True,
) -> Path:
    """Write a new exclusive sidecar for synthetic/offline R06 analysis.

    A config override changes only this new file's identity.  Source data is
    passed read-only and no source path is opened for write.
    """

    if not isinstance(manifest, RunManifest):
        raise OcrSimilaritySidecarError("invalid_source_manifest")
    config = _resolve_config(manifest, similarity_config)
    digest = similarity_config_digest(config)
    path = Path(run_dir) / "r06-sidecar-{0}.jsonl".format(digest)
    ordered_candidates = tuple(sorted(
        candidates,
        key=lambda item: (item.sequence_number, item.candidate_record_id),
    ))
    header = {
        "record_type": "r06_sidecar_manifest",
        "source_run_id": manifest.run_id,
        "source_storage_schema_version": manifest.storage_schema_version,
        "similarity_version": config.similarity_version,
        "similarity_config_version": config.similarity_config_version,
        "similarity_config_digest": digest,
        "similarity_config": canonical_similarity_config(config),
        "override": similarity_config is not None,
    }
    try:
        handle = path.open("x", encoding="utf-8", newline="")
    except FileExistsError as exc:
        raise OcrSimilaritySidecarError("sidecar_already_exists") from exc
    with handle:
        handle.write(json_dumps(header) + "\n")
        for candidate in ordered_candidates:
            try:
                if similarity_config is None:
                    replay = replay_candidate_similarity(
                        candidate, manifest, strict=strict
                    )
                    rebuilt = replay.rebuilt
                    if rebuilt is None:
                        raise OcrSimilaritySidecarError("sidecar_replay_unavailable")
                    screens = rebuilt.screens
                else:
                    # Override is intentionally sidecar-only.  R05 fields are
                    # consumed as saved; no source document is reconstructed.
                    screens = _evaluate_r06_screens(candidate.screens, config)
            except Exception:
                if strict:
                    raise
                continue
            for screen in sorted(
                (
                    item for item in screens
                    if item.capture_type == CaptureType.FORMAL_SCREEN
                    and item.is_formal_screen is True
                ),
                key=lambda item: (item.screen_index, item.screen_id),
            ):
                result = screen.similarity_result
                if result is None:
                    continue
                row = {
                    "record_type": "r06_sidecar_screen",
                    "source_run_id": manifest.run_id,
                    "source_candidate_record_id": candidate.candidate_record_id,
                    "candidate_sequence_number": candidate.sequence_number,
                    "source_screen_id": screen.screen_id,
                    "source_screen_index": screen.screen_index,
                    "source_screen_digest": _source_screen_digest(screen),
                    "reference_screen_id": result.reference_screen_id,
                    "similarity_version": result.similarity_version,
                    "similarity_config_version": result.similarity_config_version,
                    "similarity_config_digest": result.similarity_config_digest,
                    "similarity_result": result,
                }
                handle.write(json_dumps(row) + "\n")
    return path
