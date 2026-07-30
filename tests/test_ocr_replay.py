import json
from pathlib import Path
import tempfile
import unittest

from ocr_records import (
    CandidateOcrDocument,
    CaptureStatus,
    CaptureSummary,
    CaptureType,
    DOCUMENT_VERSION,
    OcrBox,
    OcrScreenRecord,
    RunManifest,
    RunStatus,
    STORAGE_SCHEMA_VERSION,
)
from ocr_replay import OcrReplayError, OcrRunReader, load_ocr_run


class OcrRunReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.temporary.name)
        self.manifest = RunManifest(
            run_id="run-replay",
            started_at="2026-07-30T12:00:00+08:00",
            ended_at="2026-07-30T12:01:00+08:00",
            status=RunStatus.COMPLETED,
            platform="Windows",
            python_version="3.13.5",
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

    def test_normal_multiline_chinese_records_restore_core_objects(self):
        screens = [self.make_screen("candidate-1", "一"), self.make_screen("candidate-2", "二")]
        self.write_records(self.run_dir / "screens.jsonl", screens)
        candidates = [self.make_candidate(screen) for screen in screens]
        self.write_records(self.run_dir / "candidates.jsonl", candidates)

        replay = load_ocr_run(self.run_dir)

        self.assertEqual(replay.screens, screens)
        self.assertEqual(replay.candidates, candidates)
        self.assertIn("虚构候选人", replay.screens[0].raw_text)

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
            (STORAGE_SCHEMA_VERSION,),
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
                        (DOCUMENT_VERSION,)
                        if field == "document_version"
                        else (STORAGE_SCHEMA_VERSION,)
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
            (STORAGE_SCHEMA_VERSION,),
        )


if __name__ == "__main__":
    unittest.main()
