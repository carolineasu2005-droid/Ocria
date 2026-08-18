import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ocr_records import (
    CandidateOcrDocument,
    AggregationStatus,
    ComparisonClass,
    CaptureStatus,
    CaptureSummary,
    CaptureType,
    DOCUMENT_VERSION,
    LEGACY_STORAGE_SCHEMA_VERSION,
    NormalizationStatus,
    OcrBox,
    OcrScreenRecord,
    RunManifest,
    RunStatus,
    ScreeningProfileBinding,
    EffectiveNewStatus,
    SimilarityStatus,
    STORAGE_SCHEMA_VERSION,
    SUPPORTED_DOCUMENT_VERSIONS,
    SUPPORTED_STORAGE_SCHEMA_VERSIONS,
)
from ocr_candidate import CandidateOcrBuilder
from ocr_aggregation import (
    DEFAULT_OCR_AGGREGATION_CONFIG,
    aggregation_config_digest,
    aggregation_config_snapshot,
)
from ocr_normalization import (
    DEFAULT_OCR_NORMALIZATION_CONFIG,
    NORMALIZATION_VERSION,
    NormalizationBox,
    OcrNormalizationConfig,
    canonical_normalization_config,
    config_with_effective_min_confidence,
    normalization_config_digest,
    normalize_ocr_text,
)
from ocr_text import OCRItem
from ocr_replay import (
    OcrReplayError,
    OcrRunReader,
    load_ocr_run,
    replay_candidate_aggregation,
    replay_candidate_similarity,
    replay_dynamic_end,
    replay_screen_normalization,
)
from ocr_similarity_sidecar import similarity_statistics, write_similarity_sidecar
from ocr_store import JsonlOcrRecordStore
from ocr_similarity import DEFAULT_OCR_SIMILARITY_CONFIG, OcrSimilarityConfig


class OcrRunReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temporary.name)
        self.config = DEFAULT_OCR_NORMALIZATION_CONFIG
        self.config_snapshot = canonical_normalization_config(self.config)
        self.manifest = RunManifest(
            run_id="run-replay",
            started_at="2026-07-30T12:00:00+08:00",
            ended_at="2026-07-30T12:01:00+08:00",
            status=RunStatus.COMPLETED,
            platform="Windows",
            python_version="3.13.5",
            normalization_version=NORMALIZATION_VERSION,
            normalization_config_version=self.config.normalization_config_version,
            normalization_config_digest=normalization_config_digest(
                self.config_snapshot
            ),
            effective_min_confidence=self.config.effective_min_confidence,
            normalization_config=self.config_snapshot,
            rule_evaluation_mode="legacy_shadow",
            data_files={
                "manifest": "run.json",
                "screens": "screens.jsonl",
                "candidates": "candidates.jsonl",
                "errors": "errors.jsonl",
            },
        )
        (self.run_dir / "run.json").write_text(
            self.manifest.to_json() + "\n", encoding="utf-8"
        )
        for name in ("screens.jsonl", "candidates.jsonl", "errors.jsonl"):
            (self.run_dir / name).write_text("", encoding="utf-8")

    def tearDown(self):
        self.temporary.cleanup()

    def make_screen(self, candidate_id="candidate-1", suffix="1"):
        text = "虚构候选人 {0} C++ C# .NET SLG+X".format(suffix)
        return OcrScreenRecord(
            run_id="run-replay",
            candidate_record_id=candidate_id,
            screen_id="screen-{0}".format(suffix),
            screen_index=1,
            attempt_index=1,
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            captured_at="2026-07-30T12:00:00+08:00",
            raw_boxes=(OcrBox(
                "box-{0}".format(suffix),
                text,
                0.95,
                ((0, 0), (10, 0), (10, 10), (0, 10)),
                0,
                1,
            ),),
            raw_text=text,
        )

    def make_candidate(self, screen):
        summary = CaptureSummary(
            actual_screen_count=1,
            ocr_attempt_count=1,
            scroll_attempt_count=0,
            scroll_retry_count=0,
            end_screen_index=1,
            capture_status=CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
            abort_reason=None,
        )
        return CandidateOcrDocument(
            run_id="run-replay",
            candidate_record_id=screen.candidate_record_id,
            sequence_number=1,
            created_at="2026-07-30T12:00:00+08:00",
            completed_at="2026-07-30T12:01:00+08:00",
            capture_status=CaptureStatus.COMPLETED,
            screens=(screen,),
            capture_summary=summary,
        )

    def make_candidate_for_screens(self, screens, **dynamic_fields):
        summary = CaptureSummary(
            actual_screen_count=len(screens),
            ocr_attempt_count=len(screens),
            scroll_attempt_count=max(0, len(screens) - 1),
            scroll_retry_count=0,
            end_screen_index=len(screens) or None,
            capture_status=CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
            abort_reason=None,
        )
        return CandidateOcrDocument(
            run_id="run-replay",
            candidate_record_id="candidate-r07",
            sequence_number=1,
            created_at="2026-07-30T12:00:00+08:00",
            completed_at="2026-07-30T12:01:00+08:00",
            capture_status=CaptureStatus.COMPLETED,
            screens=tuple(screens),
            capture_summary=summary,
            **dynamic_fields,
        )

    def make_legacy_r04_candidate(self, specifications, candidate_id="candidate-r05"):
        """Build valid frozen R04 members whose order may be malformed for R05."""

        builder = CandidateOcrBuilder(
            "run-replay", 1, candidate_record_id=candidate_id,
            created_at="2026-07-30T12:00:00+08:00",
            aggregation_mode="disabled", similarity_mode="disabled",
        )
        for position, (screen_id, screen_index, text) in enumerate(specifications):
            item = OCRItem(
                text, 0.95,
                ((0, position * 30), (160, position * 30),
                 (160, position * 30 + 20), (0, position * 30 + 20)),
            )
            normalization = normalize_ocr_text((NormalizationBox(
                "{}:box:0".format(screen_id), item.text, item.box, 0,
                item.confidence,
            ),))
            builder.build_screen_record(
                (item,), capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True, screen_index=screen_index,
                screen_id=screen_id,
                captured_at="2026-07-30T12:00:{:02d}+08:00".format(position),
                normalization=normalization, ocr_min_confidence=0.85,
            )
        document = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            completed_at="2026-07-30T12:01:00+08:00",
        )
        payload = document.to_dict()
        payload["storage_schema_version"] = "1.1.0"
        payload["document_version"] = DOCUMENT_VERSION
        for screen in payload["screens"]:
            screen["storage_schema_version"] = "1.1.0"
        return CandidateOcrDocument.from_dict(payload)

    @staticmethod
    def write_records(path, records):
        path.write_text(
            "".join(record.to_json() + "\n" for record in records),
            encoding="utf-8",
        )

    def test_empty_jsonl_files_and_manifest_load(self):
        replay = load_ocr_run(self.run_dir)

        self.assertEqual(replay.manifest, self.manifest)
        self.assertEqual(replay.screens, [])
        self.assertEqual(replay.candidates, [])
        self.assertEqual(replay.errors, [])
        self.assertEqual(replay.issues, [])

    def test_bound_manifest_reads_without_mutating_source_run_json(self):
        binding = ScreeningProfileBinding(
            screening_profile_id="sp_" + "a" * 32,
            profile_version=2,
            criteria_digest="sha256:" + "b" * 64,
        )
        manifest = replace(self.manifest, screening_profile_binding=binding)
        path = self.run_dir / "run.json"
        source = manifest.to_json() + "\n"
        path.write_text(source, encoding="utf-8")

        restored = OcrRunReader(self.run_dir).read_manifest()

        self.assertEqual(restored.screening_profile_binding, binding)
        self.assertEqual(path.read_text(encoding="utf-8"), source)

    def test_legacy_manifest_missing_binding_reads_none_without_backfill(self):
        legacy = self.manifest.to_dict()
        legacy.pop("screening_profile_binding")
        path = self.run_dir / "run.json"
        source = json.dumps(legacy, ensure_ascii=False) + "\n"
        path.write_text(source, encoding="utf-8")

        restored = OcrRunReader(self.run_dir).read_manifest()

        self.assertIsNone(restored.screening_profile_binding)
        self.assertEqual(path.read_text(encoding="utf-8"), source)

    def test_normal_multiline_chinese_records_restore_core_objects(self):
        screens = [self.make_screen("candidate-1", "一"), self.make_screen("candidate-2", "二")]
        self.write_records(self.run_dir / "screens.jsonl", screens)
        candidates = [self.make_candidate(screen) for screen in screens]
        self.write_records(self.run_dir / "candidates.jsonl", candidates)

        replay = load_ocr_run(self.run_dir)

        self.assertEqual(replay.screens, screens)
        self.assertEqual(replay.candidates, candidates)
        self.assertIn("虚构候选人", replay.screens[0].raw_text)

    def test_offline_replay_uses_same_normalizer_without_mutating_record(self):
        screen = self.make_screen()
        before = screen.to_json()

        with self.assertRaises(OcrReplayError):
            replay_screen_normalization(screen)

        replayed = replay_screen_normalization(
            screen,
            manifest=self.manifest,
        )
        expected = normalize_ocr_text(
            screen.raw_boxes,
            config=self.config,
        )

        self.assertEqual(replayed.normalized.normalized_text, expected.normalized_text)
        self.assertEqual(replayed.normalized.screen_id, screen.screen_id)
        self.assertEqual(replayed.effective_min_confidence, 0.85)
        self.assertEqual(replayed.confidence_threshold_source, "run_manifest")
        self.assertEqual(screen.to_json(), before)

    def test_r05_replay_uses_manifest_snapshot_without_override(self):
        source = self.make_screen()
        builder = CandidateOcrBuilder(
            "run-replay", 1, candidate_record_id="candidate-1",
            created_at="2026-07-30T12:00:00+08:00", aggregation_mode="record",
            similarity_mode="disabled",
        )
        builder.add_screen(source)
        candidate = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            completed_at="2026-07-30T12:01:00+08:00",
        )
        snapshot = aggregation_config_snapshot()
        manifest = replace(
            self.manifest, aggregation_mode="record", aggregation_version="r05-v1",
            aggregation_config_version="r05-config-v1",
            aggregation_config_digest=aggregation_config_digest(snapshot),
            aggregation_config=snapshot,
        )
        replayed = replay_candidate_aggregation(candidate, manifest)
        self.assertEqual(replayed.config_source, "manifest")
        self.assertEqual(replayed.rebuilt, candidate)
        with self.assertRaises(OcrReplayError):
            replay_candidate_aggregation(candidate, manifest, aggregation_config=object())

    def test_tolerant_candidate_replay_preserves_duplicate_and_out_of_order_members(self):
        cases = (
            (
                "duplicate_index",
                (
                    ("duplicate-index-a", 1, "first duplicate index body long enough"),
                    ("duplicate-index-b", 1, "second duplicate index body long enough"),
                ),
                "duplicate_formal_screen_index",
            ),
            (
                "same_id_conflict",
                (
                    ("same-id", 1, "first same identifier body long enough"),
                    ("same-id", 2, "conflicting same identifier body long enough"),
                ),
                "duplicate_screen_id_conflict",
            ),
            (
                "out_of_order",
                (
                    ("out-order-two", 2, "out of order second body long enough"),
                    ("out-order-one", 1, "out of order first body long enough"),
                ),
                "formal_screen_out_of_order",
            ),
        )
        for label, specifications, expected_issue in cases:
            with self.subTest(label=label):
                source = self.make_legacy_r04_candidate(specifications, "candidate-{}".format(label))
                before = source.to_json()
                with self.assertRaises(OcrReplayError):
                    replay_candidate_aggregation(
                        source, self.manifest,
                        aggregation_config=DEFAULT_OCR_AGGREGATION_CONFIG,
                    )
                tolerant = replay_candidate_aggregation(
                    source, self.manifest, strict=False,
                    aggregation_config=DEFAULT_OCR_AGGREGATION_CONFIG,
                )
                self.assertEqual(source.to_json(), before)
                self.assertIsNotNone(tolerant.rebuilt)
                self.assertEqual(tolerant.rebuilt.document_build_status.value, "partial")
                self.assertEqual(tolerant.rebuilt.aggregation_duplicate_risk.value, "elevated")
                self.assertIn(expected_issue, tuple(issue.error_type for issue in tolerant.issues))
                self.assertGreaterEqual(
                    len(tolerant.rebuilt.document_segments), len(specifications)
                )

    def test_tolerant_candidate_replay_keeps_identical_duplicate_and_uses_candidate_members(self):
        source = self.make_legacy_r04_candidate((
            ("same-identical", 1, "identical source body long enough"),
            ("same-identical", 1, "identical source body long enough"),
        ))
        before = source.to_json()
        # The run-level screens file is intentionally empty: candidate members
        # remain the replay authority and no source JSONL is changed.
        tolerant = replay_candidate_aggregation(
            source, self.manifest, strict=False,
            aggregation_config=DEFAULT_OCR_AGGREGATION_CONFIG,
        )
        self.assertEqual(source.to_json(), before)
        self.assertIsNotNone(tolerant.rebuilt)
        self.assertGreaterEqual(len(tolerant.rebuilt.document_segments), 1)
        self.assertIn("duplicate_formal_screen_index", tuple(
            issue.error_type for issue in tolerant.issues
        ))

    def test_online_record_and_offline_replay_have_identical_r04_fields(self):
        screen_id = "screen-online-offline"
        items = (
            OCRItem(
                "Unity  2022.3 C++",
                0.96,
                ((0, 0), (100, 0), (100, 20), (0, 20)),
            ),
            OCRItem(
                "3A UE5 iOS",
                0.97,
                ((0, 30), (100, 30), (100, 50), (0, 50)),
            ),
        )
        boxes = tuple(
            NormalizationBox(
                "{0}:box:{1}".format(screen_id, index),
                item.text,
                item.box,
                index,
                item.confidence,
            )
            for index, item in enumerate(items)
        )
        online_result = normalize_ocr_text(boxes, config=self.config)
        builder = CandidateOcrBuilder(
            "run-replay",
            1,
            candidate_record_id="candidate-replay",
            created_at="2026-07-30T12:00:00+08:00",
        )
        screen = builder.build_screen_record(
            items,
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            screen_index=1,
            captured_at="2026-07-30T12:00:01+08:00",
            screen_id=screen_id,
            normalization=online_result,
            ocr_min_confidence=0.85,
        )

        offline = replay_screen_normalization(
            screen,
            manifest=self.manifest,
        )

        self.assertEqual(screen.normalized_text, offline.normalized.normalized_text)
        self.assertEqual(screen.comparison_text, offline.normalized.comparison_text)
        self.assertEqual(screen.ordered_box_ids, offline.normalized.ordered_box_ids)
        self.assertEqual(screen.effective_box_ids, offline.normalized.effective_box_ids)
        self.assertEqual(
            screen.suppressed_duplicate_box_ids,
            offline.normalized.suppressed_duplicate_box_ids,
        )
        self.assertEqual(
            screen.normalization_version,
            offline.normalized.normalization_version,
        )
        self.assertEqual(screen.segments, offline.normalized.segments)
        self.assertEqual(screen.duplicate_gray_pair_count, offline.normalized.duplicate_gray_pair_count)
        self.assertEqual(screen.eligible_box_count, offline.normalized.eligible_box_count)
        self.assertEqual(screen.low_confidence_box_count, offline.normalized.low_confidence_box_count)
        self.assertEqual(screen.empty_normalized_box_count, offline.normalized.empty_normalized_box_count)

    def test_replay_marks_version_difference_and_legacy_threshold_source(self):
        screen = OcrScreenRecord.from_dict({
            **self.make_screen().to_dict(),
            "storage_schema_version": LEGACY_STORAGE_SCHEMA_VERSION,
        })

        assumed = replay_screen_normalization(screen)
        overridden = replay_screen_normalization(
            screen,
            legacy_min_confidence_override=0.90,
        )

        self.assertEqual(
            assumed.confidence_threshold_source,
            "legacy_stage0_assumption",
        )
        self.assertEqual(assumed.effective_min_confidence, 0.85)
        self.assertEqual(overridden.confidence_threshold_source, "caller_override")
        self.assertEqual(overridden.effective_min_confidence, 0.90)
        self.assertEqual(
            overridden.normalized.confidence_threshold_source,
            "caller_override",
        )

    def test_standalone_new_screen_requires_digest_matching_explicit_config(self):
        source = self.make_screen()
        completed = replay_screen_normalization(
            source,
            manifest=self.manifest,
        ).normalized

        replayed = replay_screen_normalization(completed, config=self.config)
        self.assertEqual(replayed.normalized.normalized_text, completed.normalized_text)

        wrong_config = replace(
            self.config,
            line_tolerance_height_ratio=0.46,
        )
        with self.assertRaises(OcrReplayError) as caught:
            replay_screen_normalization(completed, config=wrong_config)
        self.assertEqual(caught.exception.error_type, "ScreenConfigMismatchError")

    def test_tolerant_config_mismatch_returns_sanitized_failed_raw_only_view(self):
        private_text = "PRIVATE_REPLAY_BODY private@example.test 13800138000"
        source = self.make_screen(suffix="private")
        source = replace(
            source,
            raw_text=private_text,
            raw_boxes=(replace(source.raw_boxes[0], raw_text=private_text),),
        )
        completed = replay_screen_normalization(
            source,
            manifest=self.manifest,
        ).normalized
        wrong_config = replace(self.config, duplicate_confirm_iou=0.86)

        replayed = replay_screen_normalization(
            completed,
            config=wrong_config,
            strict=False,
        )

        self.assertIsNotNone(replayed.issue)
        self.assertEqual(replayed.issue.error_type, "ScreenConfigMismatchError")
        self.assertEqual(replayed.normalized.normalization_status, NormalizationStatus.FAILED)
        self.assertIsNone(replayed.normalized.normalized_text)
        self.assertEqual(replayed.normalized.raw_text, private_text)
        self.assertNotIn(private_text, str(replayed.issue))

    def test_historical_manifest_config_controls_replay_and_full_trace_equality(self):
        config = config_with_effective_min_confidence(
            replace(self.config, line_tolerance_height_ratio=0.44),
            0.90,
        )
        snapshot = canonical_normalization_config(config)
        manifest = replace(
            self.manifest,
            normalization_config_version=config.normalization_config_version,
            normalization_config_digest=normalization_config_digest(snapshot),
            effective_min_confidence=config.effective_min_confidence,
            normalization_config=snapshot,
        )
        screen_id = "screen-full-equality"
        items = (
            OCRItem("Unity 2022.3", 0.99, ((0, 0), (100, 0), (100, 20), (0, 20))),
            OCRItem("Unity 2022.3", 0.98, ((1, 0), (101, 0), (101, 20), (1, 20))),
            OCRItem("low", 0.50, ((0, 30), (30, 30), (30, 50), (0, 50))),
            OCRItem("  ", 0.95, ((0, 60), (30, 60), (30, 80), (0, 80))),
        )
        boxes = tuple(
            NormalizationBox(
                "{0}:box:{1}".format(screen_id, index),
                item.text,
                item.box,
                index,
                item.confidence,
            )
            for index, item in enumerate(items)
        )
        online_result = normalize_ocr_text(boxes, config=config)
        builder = CandidateOcrBuilder(
            "run-replay",
            1,
            candidate_record_id="candidate-equality",
        )
        online = builder.build_screen_record(
            items,
            capture_type=CaptureType.LOAD_CHECK,
            is_formal_screen=False,
            screen_index=None,
            screen_id=screen_id,
            normalization=online_result,
            ocr_min_confidence=0.90,
        )
        source_before = online.to_json()

        offline = replay_screen_normalization(online, manifest=manifest).normalized

        for field_name in (
            "normalization_status",
            "normalized_text",
            "comparison_text",
            "segments",
            "suppressed_duplicate_box_ids",
            "duplicate_gray_pair_count",
            "eligible_box_count",
            "low_confidence_box_count",
            "empty_normalized_box_count",
            "normalization_version",
            "normalization_config_version",
            "normalization_config_digest",
            "effective_min_confidence",
        ):
            with self.subTest(field=field_name):
                self.assertEqual(getattr(offline, field_name), getattr(online, field_name))
        self.assertEqual(online.to_json(), source_before)
        self.assertEqual(offline.raw_boxes, online.raw_boxes)
        self.assertEqual(offline.raw_text, online.raw_text)
        self.assertEqual(offline.exact_hash, online.exact_hash)

    def test_invalid_bbox_is_strict_failure_and_tolerant_issue(self):
        source = self.make_screen(suffix="bbox")
        source = replace(
            source,
            raw_boxes=(replace(source.raw_boxes[0], bbox=(0, (1, 2), 3, 4)),),
        )

        with self.assertRaises(OcrReplayError) as caught:
            replay_screen_normalization(source, manifest=self.manifest)
        self.assertEqual(caught.exception.error_type, "layout_degraded")

        tolerant = replay_screen_normalization(
            source,
            manifest=self.manifest,
            strict=False,
        )
        self.assertEqual(tolerant.issue.error_type, "layout_degraded")
        self.assertEqual(tolerant.normalized.normalization_status, NormalizationStatus.FAILED)

    def test_strict_mode_raises_with_corrupted_middle_line_number(self):
        path = self.run_dir / "screens.jsonl"
        first = self.make_screen(suffix="1")
        third = self.make_screen(suffix="3")
        path.write_text(
            first.to_json() + "\n" + "{broken middle}\n" + third.to_json() + "\n",
            encoding="utf-8",
        )
        reader = OcrRunReader(self.run_dir, strict=True)

        with self.assertRaises(OcrReplayError) as caught:
            list(reader.iter_screens())

        self.assertEqual(caught.exception.line_number, 2)
        self.assertEqual(caught.exception.error_type, "JSONDecodeError")

    def test_tolerant_mode_skips_corrupted_middle_and_reports_issue(self):
        path = self.run_dir / "screens.jsonl"
        first = self.make_screen(suffix="1")
        third = self.make_screen(suffix="3")
        path.write_text(
            first.to_json() + "\n" + "not-json\n" + third.to_json() + "\n",
            encoding="utf-8",
        )
        reader = OcrRunReader(self.run_dir, strict=False)

        records = list(reader.iter_screens())

        self.assertEqual(records, [first, third])
        self.assertEqual(len(reader.issues), 1)
        self.assertEqual(reader.issues[0].line_number, 2)

    def test_tolerant_mode_skips_truncated_last_line_and_reports_it(self):
        path = self.run_dir / "screens.jsonl"
        first = self.make_screen()
        path.write_text(first.to_json() + "\n" + '{"record_type":', encoding="utf-8")
        reader = OcrRunReader(self.run_dir, strict=False)

        records = list(reader.iter_screens())

        self.assertEqual(records, [first])
        self.assertEqual(len(reader.issues), 1)
        self.assertEqual(reader.issues[0].line_number, 2)
        self.assertEqual(reader.issues[0].error_type, "JSONDecodeError")

    def test_candidate_run_and_record_type_filters(self):
        first = self.make_screen("candidate-1", "1")
        second = self.make_screen("candidate-2", "2")
        foreign = OcrScreenRecord.from_dict({
            **second.to_dict(),
            "run_id": "other-run",
            "screen_id": "foreign",
        })
        self.write_records(self.run_dir / "screens.jsonl", [first, second, foreign])
        reader = OcrRunReader(self.run_dir)

        selected = list(reader.iter_screens(
            run_id="run-replay",
            candidate_record_id="candidate-2",
            record_type="ocr_screen",
        ))
        absent = list(reader.iter_screens(record_type="storage_error"))

        self.assertEqual(selected, [second])
        self.assertEqual(absent, [])

    def test_error_filter_uses_sanitized_candidate_context(self):
        errors = [
            {
                "record_type": "storage_error",
                "storage_schema_version": STORAGE_SCHEMA_VERSION,
                "run_id": "run-replay",
                "candidate_record_id": None,
                "error_type": "SyntheticError",
                "context": {"candidate_record_id": "candidate-2"},
            }
        ]
        (self.run_dir / "errors.jsonl").write_text(
            "\n".join(json.dumps(item) for item in errors) + "\n",
            encoding="utf-8",
        )
        reader = OcrRunReader(self.run_dir)

        selected = list(reader.iter_errors(candidate_record_id="candidate-2"))

        self.assertEqual(selected, errors)

    def test_tolerant_manifest_failure_is_sanitized(self):
        (self.run_dir / "run.json").write_text("not-json", encoding="utf-8")
        reader = OcrRunReader(self.run_dir, strict=False)

        manifest = reader.read_manifest()

        self.assertIsNone(manifest)
        self.assertEqual(reader.issues[0].line_number, 1)
        self.assertEqual(reader.issues[0].error_type, "JSONDecodeError")

    def test_tolerant_manifest_version_failure_is_structured(self):
        manifest = self.manifest.to_dict()
        manifest["storage_schema_version"] = "2.0.0"
        path = self.run_dir / "run.json"
        path.write_text(
            json.dumps(manifest, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        reader = OcrRunReader(self.run_dir, strict=False)

        restored = reader.read_manifest()

        self.assertIsNone(restored)
        self.assertEqual(len(reader.issues), 1)
        issue = reader.issues[0]
        self.assertEqual(issue.path, path)
        self.assertEqual(issue.line_number, 1)
        self.assertEqual(issue.error_type, "UnsupportedVersionError")
        self.assertEqual(issue.version_field, "storage_schema_version")
        self.assertEqual(issue.actual_version, "2.0.0")
        self.assertEqual(
            issue.supported_versions,
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )

    def test_strict_mode_validates_every_restored_record_version_contract(self):
        screen = self.make_screen()
        candidate = self.make_candidate(screen)
        sources = (
            (
                "run.json",
                self.manifest.to_dict(),
                "storage_schema_version",
                lambda reader: reader.read_manifest(),
            ),
            (
                "screens.jsonl",
                screen.to_dict(),
                "storage_schema_version",
                lambda reader: list(reader.iter_screens()),
            ),
            (
                "candidates.jsonl",
                candidate.to_dict(),
                "storage_schema_version",
                lambda reader: list(reader.iter_candidates()),
            ),
            (
                "candidates.jsonl",
                candidate.to_dict(),
                "document_version",
                lambda reader: list(reader.iter_candidates()),
            ),
            (
                "errors.jsonl",
                {
                    "record_type": "storage_error",
                    "storage_schema_version": STORAGE_SCHEMA_VERSION,
                    "run_id": "run-replay",
                    "error_type": "SyntheticError",
                    "context": {},
                },
                "storage_schema_version",
                lambda reader: list(reader.iter_errors()),
            ),
        )
        violations = (
            ("missing", None, "MissingVersionError", None),
            ("non-string", 2, "InvalidVersionTypeError", "<int>"),
            (
                "future",
                "future-v99",
                "UnsupportedVersionError",
                "future-v99",
            ),
        )

        for file_name, base, field, read in sources:
            for label, value, error_type, actual in violations:
                with self.subTest(file=file_name, field=field, case=label):
                    record = json.loads(json.dumps(base))
                    if value is None:
                        record.pop(field)
                    else:
                        record[field] = value
                    path = self.run_dir / file_name
                    path.write_text(
                        json.dumps(record, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    reader = OcrRunReader(self.run_dir, strict=True)
                    with self.assertRaises(OcrReplayError) as caught:
                        read(reader)
                    error = caught.exception
                    self.assertEqual(error.path, path)
                    self.assertEqual(error.line_number, 1)
                    self.assertEqual(error.error_type, error_type)
                    self.assertEqual(error.version_field, field)
                    self.assertEqual(error.actual_version, actual)
                    expected = (
                        SUPPORTED_DOCUMENT_VERSIONS
                        if field == "document_version"
                        else SUPPORTED_STORAGE_SCHEMA_VERSIONS
                    )
                    self.assertEqual(error.supported_versions, expected)
                    message = str(error)
                    self.assertIn(str(path), message)
                    self.assertIn(error_type, message)
                    self.assertIn("supported=", message)

    def test_strict_version_error_never_echoes_candidate_ocr_content(self):
        candidate = self.make_candidate(self.make_screen()).to_dict()
        private_text = "候选人隐私 private@example.test 13800138000"
        candidate["screens"][0]["raw_text"] = private_text
        candidate["screens"][0]["raw_boxes"][0]["raw_text"] = private_text
        candidate["document_version"] = "future-private-contract"
        path = self.run_dir / "candidates.jsonl"
        path.write_text(
            json.dumps(candidate, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        with self.assertRaises(OcrReplayError) as caught:
            list(OcrRunReader(self.run_dir).iter_candidates())

        self.assertNotIn(private_text, str(caught.exception))
        self.assertEqual(
            caught.exception.actual_version,
            "future-private-contract",
        )

    def test_tolerant_mode_skips_incompatible_lines_and_continues(self):
        first = self.make_screen("candidate-1", "1").to_dict()
        incompatible = self.make_screen("candidate-bad", "2").to_dict()
        incompatible["storage_schema_version"] = "2.0.0"
        third = self.make_screen("candidate-3", "3").to_dict()
        path = self.run_dir / "screens.jsonl"
        path.write_text(
            "".join(
                json.dumps(record, ensure_ascii=False) + "\n"
                for record in (first, incompatible, third)
            ),
            encoding="utf-8",
        )
        reader = OcrRunReader(self.run_dir, strict=False)

        records = list(reader.iter_screens())

        self.assertEqual(
            [record.candidate_record_id for record in records],
            ["candidate-1", "candidate-3"],
        )
        self.assertEqual(len(reader.issues), 1)
        issue = reader.issues[0]
        self.assertEqual(issue.path, path)
        self.assertEqual(issue.line_number, 2)
        self.assertEqual(issue.error_type, "UnsupportedVersionError")
        self.assertEqual(issue.version_field, "storage_schema_version")
        self.assertEqual(issue.actual_version, "2.0.0")
        self.assertEqual(
            issue.supported_versions,
            SUPPORTED_STORAGE_SCHEMA_VERSIONS,
        )

    def test_r06_online_store_replay_and_sidecar_are_identical_for_synthetic_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = JsonlOcrRecordStore(
                Path(temporary), run_id="run-r06-replay",
                aggregation_mode="record", similarity_mode="record",
            )
            builder = CandidateOcrBuilder(
                "run-r06-replay", 1, candidate_record_id="candidate-r06-replay",
                created_at="2026-07-30T12:00:00+08:00",
                aggregation_mode="record", similarity_mode="record",
            )
            screens = []
            for index, text in enumerate(("历史 C++ 内容", "历史 C++ 内容 新增"), 1):
                screen_id = "r06-replay-{0}".format(index)
                item = OCRItem(
                    text, 0.95,
                    ((0, 0), (160, 0), (160, 20), (0, 20)),
                )
                normalization = normalize_ocr_text((NormalizationBox(
                    "{0}:box:0".format(screen_id), item.text, item.box, 0,
                    item.confidence,
                ),))
                screens.append(builder.build_screen_record(
                    (item,), capture_type=CaptureType.FORMAL_SCREEN,
                    is_formal_screen=True, screen_index=index, screen_id=screen_id,
                    captured_at="2026-07-30T12:00:0{0}+08:00".format(index),
                    normalization=normalization, ocr_min_confidence=0.85,
                ))
            candidate = builder.finalize(
                CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            )
            for screen in screens:
                self.assertTrue(store.save_screen(screen))
            self.assertTrue(store.save_candidate(candidate))
            aggregation_replay = replay_candidate_aggregation(candidate, store.manifest)
            self.assertEqual(aggregation_replay.rebuilt, candidate)
            replay = replay_candidate_similarity(candidate, store.manifest)
            self.assertEqual(replay.rebuilt, candidate)
            with self.assertRaises(OcrReplayError):
                replay_candidate_similarity(
                    candidate, store.manifest,
                    similarity_config=DEFAULT_OCR_SIMILARITY_CONFIG,
                )
            tolerant = replay_candidate_similarity(
                candidate, store.manifest, strict=False,
                similarity_config=DEFAULT_OCR_SIMILARITY_CONFIG,
            )
            self.assertIsNone(tolerant.rebuilt)
            self.assertEqual(tolerant.issues[0].error_type, "SimilarityConfigOverrideError")
            sidecar = write_similarity_sidecar(
                store.run_dir, store.manifest, (candidate,), strict=True,
            )
            lines = sidecar.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 3)
            self.assertIn("r06_sidecar_manifest", lines[0])
            self.assertNotIn("历史 C++ 内容", "\n".join(lines))
            statistics = similarity_statistics((candidate,))
            self.assertEqual(statistics["sample_count"], 2)
            self.assertNotIn("历史 C++ 内容", str(statistics))
            overridden = write_similarity_sidecar(
                store.run_dir,
                store.manifest,
                (candidate,),
                similarity_config=OcrSimilarityConfig(high_similarity_threshold=0.84),
            )
            self.assertNotEqual(overridden, sidecar)
            self.assertEqual(candidate, replay.rebuilt)
            with self.assertRaises(ValueError):
                write_similarity_sidecar(store.run_dir, store.manifest, (candidate,))
            store.close()

    def test_r06_legacy_replay_advances_required_stages_without_guessing(self):
        builder = CandidateOcrBuilder(
            "run-replay", 1, candidate_record_id="legacy-r06",
            created_at="2026-07-30T12:00:00+08:00",
        )
        item = OCRItem(
            "legacy synthetic C++", 0.95,
            ((0, 0), (160, 0), (160, 20), (0, 20)),
        )
        builder.build_screen_record(
            (item,), capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True, screen_index=1, screen_id="legacy-r06-screen",
            captured_at="2026-07-30T12:00:00+08:00",
        )
        raw = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            completed_at="2026-07-30T12:01:00+08:00",
        ).to_dict()
        raw["storage_schema_version"] = LEGACY_STORAGE_SCHEMA_VERSION
        raw["document_version"] = DOCUMENT_VERSION
        raw["screens"][0]["storage_schema_version"] = LEGACY_STORAGE_SCHEMA_VERSION
        legacy = CandidateOcrDocument.from_dict(raw)
        replay = replay_candidate_similarity(
            legacy,
            similarity_config=DEFAULT_OCR_SIMILARITY_CONFIG,
            aggregation_config=DEFAULT_OCR_AGGREGATION_CONFIG,
            normalization_config=DEFAULT_OCR_NORMALIZATION_CONFIG,
        )
        self.assertIsNotNone(replay.rebuilt)
        self.assertEqual(replay.rebuilt.storage_schema_version, STORAGE_SCHEMA_VERSION)
        self.assertIsNotNone(replay.rebuilt.similarity_summary)

    def test_dynamic_end_replay_is_candidate_level_pure_and_keeps_prediction_nullables(self):
        first = replace(
            self.make_screen("candidate-r07", "r07-1"),
            screen_index=1,
            position_status="initial",
            dynamic_end_version="r07-v1",
        )
        same = replace(
            self.make_screen("candidate-r07", "r07-2"),
            screen_index=2,
            position_status="same",
            page_change_status="same",
            reference_screen_id=first.screen_id,
            dynamic_end_version="r07-v1",
            prediction_reason="exact_same",
        )
        candidate = self.make_candidate_for_screens(
            (first, same),
            dynamic_end_mode="shadow",
            dynamic_end_reason=None,
            first_predicted_end_screen=2,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_would_miss_content=None,
            prediction_would_miss_rule_match=None,
            prediction_observation_complete=True,
            prediction_evidence_complete=True,
        )
        source_before = candidate.to_json()

        replay = replay_dynamic_end(candidate)

        self.assertEqual(replay.position_statuses, ("initial", "same"))
        self.assertEqual(replay.offline_bottom_status, "possible_scroll_bottom")
        self.assertIsNone(replay.recorded_dynamic_end_reason)
        self.assertIsNone(replay.prediction_would_miss_content)
        self.assertIsNone(replay.prediction_would_miss_rule_match)
        self.assertEqual(candidate.to_json(), source_before)

    def test_dynamic_end_replay_replays_no_new_and_never_confirms_bottom(self):
        builder = CandidateOcrBuilder(
            "run-replay", 1, candidate_record_id="candidate-no-new",
            created_at="2026-07-30T12:00:00+08:00",
            aggregation_mode="record", similarity_mode="record",
        )
        for index in range(1, 4):
            screen_id = "no-new-{0}".format(index)
            item = OCRItem("历史 C++ 内容", 0.95,
                           ((0, 0), (160, 0), (160, 20), (0, 20)))
            normalization = normalize_ocr_text((NormalizationBox(
                "{0}:box".format(screen_id), item.text, item.box, 0,
                item.confidence,
            ),))
            builder.build_screen_record(
                (item,), capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True, screen_index=index, screen_id=screen_id,
                captured_at="2026-07-30T12:00:0{0}+08:00".format(index),
                normalization=normalization, ocr_min_confidence=0.85,
            )
        source = builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
        )
        # The builder above gives us real R05/R06-shaped records.  Freeze the
        # persisted result projection expected by the full no-new predicate;
        # the replay must read it, never recompute it.
        for index, screen in enumerate(source.screens):
            object.__setattr__(screen, "dynamic_end_version", "r07-v1")
            object.__setattr__(
                screen, "position_status", "initial" if index == 0 else "changed",
            )
            if index:
                result = replace(
                    screen.similarity_result,
                    similarity_status=SimilarityStatus.COMPLETED,
                    effective_new_status=EffectiveNewStatus.NONE,
                    has_effective_new_text=False,
                    effective_new_segment_count=0,
                    ineffective_new_segment_count=0,
                    possible_new_segment_count=0,
                    effective_new_char_count=0,
                    possible_new_char_count=0,
                    effective_new_decisions=(),
                    comparison_class=ComparisonClass.CHANGED_WITHOUT_EFFECTIVE_NEW,
                    warning_codes=(),
                )
                object.__setattr__(screen, "aggregation_status", AggregationStatus.COMPLETED)
                object.__setattr__(screen, "similarity_result", result)
                object.__setattr__(screen, "has_effective_new_text", False)
                object.__setattr__(screen, "uncertain_segment_ids", ())
                object.__setattr__(screen, "uncertain_segment_count", 0)
                object.__setattr__(screen, "uncertain_char_count", 0)
                object.__setattr__(screen, "aggregation_warning_codes", ())
                object.__setattr__(screen, "aggregation_duplicate_risk", None)
        object.__setattr__(source, "dynamic_end_mode", "shadow")
        candidate = source

        replay = replay_dynamic_end(candidate)

        self.assertTrue(replay.no_new_text_candidate)
        self.assertGreaterEqual(replay.consecutive_no_new_count, 2)
        self.assertEqual(replay.offline_bottom_status, "insufficient_evidence")
        self.assertNotEqual(replay.offline_bottom_status, "scroll_bottom")

    def test_dynamic_end_replay_handles_legacy_rule_store_failure_and_platform_purely(self):
        first = replace(
            self.make_screen("candidate-r07", "legacy-1"),
            screen_index=1,
            position_status="initial",
            dynamic_end_version="r07-v1",
        )
        confirmation = replace(
            self.make_screen("candidate-r07", "legacy-2"),
            screen_index=2,
            is_formal_screen=False,
            capture_type=CaptureType.RULE_CONFIRMATION,
            position_status="same",
            dynamic_end_version="r07-v1",
        )
        object.__setattr__(confirmation, "legacy_match", True)
        candidate = self.make_candidate_for_screens(
            (first, confirmation),
            dynamic_end_mode="shadow",
            dynamic_end_reason=None,
            first_predicted_end_screen=1,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=False,
            prediction_evidence_complete=False,
        )
        before = candidate.to_json()
        with patch("sys.platform", "win32"):
            windows = replay_dynamic_end(candidate)
        with patch("sys.platform", "darwin"):
            macos = replay_dynamic_end(candidate)

        self.assertEqual(windows, macos)
        self.assertTrue(windows.legacy_rule_completed)
        self.assertTrue(windows.prediction_would_miss_rule_match)
        self.assertIsNone(windows.prediction_would_miss_content)
        self.assertIsNone(windows.recorded_dynamic_end_reason)
        self.assertEqual(candidate.to_json(), before)

        store_failed = replace(candidate, abort_reason="store_failed")
        failed_replay = replay_dynamic_end(store_failed)
        self.assertEqual(failed_replay.offline_bottom_status, "insufficient_evidence")
        self.assertTrue(failed_replay.insufficient_evidence)
        self.assertIsNone(failed_replay.prediction_would_miss_content)
        self.assertIsNone(failed_replay.prediction_would_miss_rule_match)

    def test_dynamic_end_replay_legacy_schema_and_output_do_not_expose_ocr_text(self):
        private_text = "候选人 13800138000 secret@example.com"
        screen = replace(
            self.make_screen("candidate-r07", "private"),
            raw_text=private_text,
            raw_boxes=(replace(self.make_screen("candidate-r07", "private").raw_boxes[0], raw_text=private_text),),
        )
        raw = self.make_candidate(screen).to_dict()
        raw["storage_schema_version"] = LEGACY_STORAGE_SCHEMA_VERSION
        raw["screens"][0]["storage_schema_version"] = LEGACY_STORAGE_SCHEMA_VERSION
        legacy = CandidateOcrDocument.from_dict(raw)

        replay = replay_dynamic_end(legacy)

        self.assertEqual(replay.position_statuses, ("initial",))
        self.assertTrue(replay.insufficient_evidence)
        self.assertIsNone(replay.first_predicted_end_screen)
        self.assertNotIn(private_text, str(replay))
        self.assertNotIn("13800138000", str(replay))
        self.assertNotIn("secret@example.com", str(replay))

    # ── R07-IMPL-001: Replay rule completion only from rule_confirmation ──

    def test_impl001_first_pass_rule_hit_is_not_confirmed_completion(self):
        """Only rule_confirmation + legacy_match=True is a completed rule."""
        first = replace(
            self.make_screen("candidate-r07", "001-1"),
            screen_index=1,
            position_status="initial",
            dynamic_end_version="r07-v1",
        )
        formal_hit = replace(
            self.make_screen("candidate-r07", "001-2"),
            screen_index=2,
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            position_status="same",
            dynamic_end_version="r07-v1",
        )
        object.__setattr__(formal_hit, "legacy_match", True)
        confirmation_fail = replace(
            self.make_screen("candidate-r07", "001-3"),
            screen_index=2,
            capture_type=CaptureType.RULE_CONFIRMATION,
            is_formal_screen=False,
            position_status="same",
            dynamic_end_version="r07-v1",
        )
        object.__setattr__(confirmation_fail, "legacy_match", False)
        candidate = self.make_candidate_for_screens(
            (first, formal_hit, confirmation_fail),
            dynamic_end_mode="shadow",
            dynamic_end_reason=None,
            first_predicted_end_screen=1,
            first_predicted_end_reason="possible_scroll_bottom",
        )
        replay = replay_dynamic_end(candidate)
        # G1: formal_screen.legacy_match alone does NOT confirm legacy rule
        self.assertFalse(replay.legacy_rule_completed)
        self.assertIsNone(replay.prediction_would_miss_rule_match)

    def test_impl001_confirmed_rule_hit_is_completion(self):
        first = replace(
            self.make_screen("candidate-r07", "001-conf-1"),
            screen_index=1,
            position_status="initial",
            dynamic_end_version="r07-v1",
        )
        confirmed = replace(
            self.make_screen("candidate-r07", "001-conf-2"),
            screen_index=1,
            capture_type=CaptureType.RULE_CONFIRMATION,
            is_formal_screen=False,
            position_status="same",
            dynamic_end_version="r07-v1",
        )
        object.__setattr__(confirmed, "legacy_match", True)
        candidate = self.make_candidate_for_screens(
            (first, confirmed),
            dynamic_end_mode="shadow",
            dynamic_end_reason=None,
            first_predicted_end_screen=1,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=False,
            prediction_evidence_complete=False,
        )
        replay = replay_dynamic_end(candidate)
        self.assertTrue(replay.legacy_rule_completed)
        self.assertTrue(replay.prediction_would_miss_rule_match)

    def test_impl001_no_first_prediction_no_rule_miss_claim(self):
        first = self.make_screen("candidate-r07", "001-no-pred")
        candidate = self.make_candidate_for_screens(
            (first,),
            dynamic_end_mode="shadow",
            dynamic_end_reason=None,
            first_predicted_end_screen=None,
            first_predicted_end_reason=None,
        )
        replay = replay_dynamic_end(candidate)
        self.assertFalse(replay.legacy_rule_completed)
        self.assertIsNone(replay.prediction_would_miss_rule_match)
        self.assertIsNone(replay.prediction_would_miss_content)

    def test_impl001_legacy_schema_no_confirmation_record(self):
        private = "候选人 13800138011"
        screen = replace(
            self.make_screen("candidate-r07", "001-legacy"),
            raw_text=private,
            raw_boxes=(replace(
                self.make_screen("candidate-r07", "001-legacy").raw_boxes[0],
                raw_text=private,
            ),),
        )
        object.__setattr__(screen, "storage_schema_version", LEGACY_STORAGE_SCHEMA_VERSION)
        raw = self.make_candidate(screen).to_dict()
        raw["storage_schema_version"] = LEGACY_STORAGE_SCHEMA_VERSION
        raw["screens"][0]["storage_schema_version"] = LEGACY_STORAGE_SCHEMA_VERSION
        legacy = CandidateOcrDocument.from_dict(raw)
        replay = replay_dynamic_end(legacy)
        self.assertFalse(replay.legacy_rule_completed)
        self.assertTrue(replay.insufficient_evidence)

    def test_impl001_source_object_is_not_mutated(self):
        first = replace(
            self.make_screen("candidate-r07", "001-mut-1"),
            screen_index=1,
            position_status="initial",
            dynamic_end_version="r07-v1",
        )
        candidate = self.make_candidate_for_screens(
            (first,),
            dynamic_end_mode="shadow",
            dynamic_end_reason=None,
            first_predicted_end_screen=1,
            first_predicted_end_reason="possible_scroll_bottom",
        )
        before = candidate.to_json()
        replay_dynamic_end(candidate)
        self.assertEqual(candidate.to_json(), before)

    # ── R07-IMPL-002: Replay evidence completeness gate ──

    def test_impl002_incomplete_evidence_is_insufficient(self):
        first = replace(
            self.make_screen("candidate-r07", "002-1"),
            screen_index=1,
            position_status="initial",
            dynamic_end_version="r07-v1",
        )
        second = replace(
            self.make_screen("candidate-r07", "002-2"),
            screen_index=2,
            position_status="same",
            dynamic_end_version="r07-v1",
        )
        candidate = self.make_candidate_for_screens(
            (first, second),
            dynamic_end_mode="shadow",
            dynamic_end_reason=None,
            first_predicted_end_screen=2,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=False,
            prediction_evidence_complete=False,
        )
        replay = replay_dynamic_end(candidate)
        self.assertEqual(replay.offline_bottom_status, "insufficient_evidence")
        self.assertTrue(replay.insufficient_evidence)

    def test_impl002_observation_false_evidence_true_is_insufficient(self):
        first = replace(
            self.make_screen("candidate-r07", "002-obs1"),
            screen_index=1, position_status="initial",
            dynamic_end_version="r07-v1",
        )
        second = replace(
            self.make_screen("candidate-r07", "002-obs2"),
            screen_index=2, position_status="same",
            dynamic_end_version="r07-v1",
        )
        candidate = self.make_candidate_for_screens(
            (first, second),
            first_predicted_end_screen=2,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=False,
            prediction_evidence_complete=True,
        )
        replay = replay_dynamic_end(candidate)
        self.assertEqual(replay.offline_bottom_status, "insufficient_evidence")
        self.assertTrue(replay.insufficient_evidence)

    def test_impl002_observation_true_evidence_false_is_insufficient(self):
        first = replace(
            self.make_screen("candidate-r07", "002-oe1"),
            screen_index=1, position_status="initial",
            dynamic_end_version="r07-v1",
        )
        second = replace(
            self.make_screen("candidate-r07", "002-oe2"),
            screen_index=2, position_status="same",
            dynamic_end_version="r07-v1",
        )
        candidate = self.make_candidate_for_screens(
            (first, second),
            first_predicted_end_screen=2,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=True,
            prediction_evidence_complete=False,
        )
        replay = replay_dynamic_end(candidate)
        self.assertEqual(replay.offline_bottom_status, "insufficient_evidence")
        self.assertTrue(replay.insufficient_evidence)

    def test_impl002_both_complete_true_is_possible(self):
        first = replace(
            self.make_screen("candidate-r07", "002-g-1"),
            screen_index=1, position_status="initial",
            dynamic_end_version="r07-v1",
        )
        second = replace(
            self.make_screen("candidate-r07", "002-g-2"),
            screen_index=2, position_status="same",
            dynamic_end_version="r07-v1",
        )
        candidate = self.make_candidate_for_screens(
            (first, second),
            first_predicted_end_screen=2,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=True,
            prediction_evidence_complete=True,
        )
        replay = replay_dynamic_end(candidate)
        self.assertEqual(replay.offline_bottom_status, "possible_scroll_bottom")
        self.assertFalse(replay.insufficient_evidence)

    def test_impl002_null_completeness_old_schema_is_insufficient(self):
        first = replace(
            self.make_screen("candidate-r07", "002-old-1"),
            screen_index=1, position_status="initial",
            dynamic_end_version="r07-v1",
        )
        candidate = self.make_candidate_for_screens(
            (first,),
            first_predicted_end_screen=1,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=None,
            prediction_evidence_complete=None,
        )
        replay = replay_dynamic_end(candidate)
        self.assertEqual(replay.offline_bottom_status, "insufficient_evidence")
        self.assertTrue(replay.insufficient_evidence)

    def test_impl002_store_failure_no_abort_is_insufficient(self):
        first = replace(
            self.make_screen("candidate-r07", "002-sf-1"),
            screen_index=1, position_status="initial",
            dynamic_end_version="r07-v1",
        )
        second = replace(
            self.make_screen("candidate-r07", "002-sf-2"),
            screen_index=2, position_status="same",
            dynamic_end_version="r07-v1",
        )
        candidate = self.make_candidate_for_screens(
            (first, second),
            first_predicted_end_screen=2,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=False,
            prediction_evidence_complete=False,
        )
        replay = replay_dynamic_end(candidate)
        self.assertEqual(replay.offline_bottom_status, "insufficient_evidence")
        self.assertTrue(replay.insufficient_evidence)

    def test_impl002_source_object_not_mutated(self):
        first = replace(
            self.make_screen("candidate-r07", "002-mut-1"),
            screen_index=1, position_status="initial",
            dynamic_end_version="r07-v1",
        )
        candidate = self.make_candidate_for_screens(
            (first,),
            first_predicted_end_screen=2,
            first_predicted_end_reason="possible_scroll_bottom",
            prediction_observation_complete=False,
            prediction_evidence_complete=False,
        )
        before = candidate.to_json()
        replay_dynamic_end(candidate)
        self.assertEqual(candidate.to_json(), before)


if __name__ == "__main__":
    unittest.main()
