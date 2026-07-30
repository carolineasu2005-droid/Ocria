import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ocr_records import (
    CandidateOcrDocument,
    CaptureStatus,
    CaptureSummary,
    CaptureType,
    OcrBox,
    OcrScreenRecord,
    RunStatus,
)
from ocr_store import JsonlOcrRecordStore


class JsonlOcrRecordStoreTests(unittest.TestCase):
    def make_store(self, root, **kwargs):
        return JsonlOcrRecordStore(
            Path(root),
            run_id="run-test",
            action_mode="favorite",
            max_screen_count=8,
            **kwargs,
        )

    def make_screen(self, suffix="1"):
        text = "虚构候选人 {0} C++ C# .NET SLG+X 0-1 2D/3D".format(
            suffix
        )
        box = OcrBox(
            box_id="box-{0}".format(suffix),
            raw_text=text,
            confidence=0.95,
            bbox=((0, 0), (10, 0), (10, 10), (0, 10)),
            original_index=0,
            screen_index=1,
        )
        return OcrScreenRecord(
            run_id="run-test",
            candidate_record_id="candidate-test",
            screen_id="screen-{0}".format(suffix),
            screen_index=1,
            attempt_index=1,
            capture_type=CaptureType.FORMAL_SCREEN,
            is_formal_screen=True,
            captured_at="2026-07-30T12:00:00+08:00",
            raw_boxes=(box,),
            raw_text=text,
        )

    def make_document(self, screens):
        summary = CaptureSummary(
            actual_screen_count=len(screens),
            ocr_attempt_count=len(screens),
            scroll_attempt_count=max(0, len(screens) - 1),
            scroll_retry_count=0,
            end_screen_index=1 if screens else None,
            capture_status=CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
            abort_reason=None,
        )
        return CandidateOcrDocument(
            run_id="run-test",
            candidate_record_id="candidate-test",
            sequence_number=1,
            created_at="2026-07-30T12:00:00+08:00",
            completed_at="2026-07-30T12:01:00+08:00",
            capture_status=CaptureStatus.COMPLETED,
            screens=tuple(screens),
            capture_summary=summary,
        )

    def test_creates_unique_run_directory_and_fixed_file_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            first = self.make_store(temporary)
            second = JsonlOcrRecordStore(Path(temporary), run_id="run-test-2")

            self.assertTrue(first.enabled)
            self.assertTrue(second.enabled)
            self.assertNotEqual(first.run_dir, second.run_dir)
            for store in (first, second):
                self.assertTrue(store.manifest_path.is_file())
                self.assertTrue(store.screens_path.is_file())
                self.assertTrue(store.candidates_path.is_file())
                self.assertTrue(store.errors_path.is_file())
            first.close()
            second.close()

    def test_utf8_append_produces_independently_parseable_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)
            screens = [self.make_screen("一"), self.make_screen("二")]

            self.assertTrue(store.save_screen(screens[0]))
            self.assertTrue(store.save_screen(screens[1]))
            store.close()

            raw = store.screens_path.read_text(encoding="utf-8")
            lines = raw.splitlines()
            self.assertEqual(len(lines), 2)
            parsed = [json.loads(line) for line in lines]
            self.assertEqual(parsed[0]["raw_text"], screens[0].raw_text)
            self.assertEqual(parsed[1]["raw_text"], screens[1].raw_text)
            self.assertIn("虚构候选人", raw)
            self.assertTrue(raw.endswith("\n"))

    def test_candidate_append_and_manifest_statistics(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)
            screen = self.make_screen()
            self.assertTrue(store.save_screen(screen))
            self.assertTrue(store.save_candidate(self.make_document([screen])))

            self.assertTrue(store.close(RunStatus.INTERRUPTED))

            manifest = json.loads(
                store.manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "interrupted")
            self.assertIsNotNone(manifest["ended_at"])
            self.assertEqual(manifest["screen_record_count"], 1)
            self.assertEqual(manifest["candidate_record_count"], 1)
            self.assertEqual(manifest["data_files"]["screens"], "screens.jsonl")
            self.assertEqual(
                len(store.candidates_path.read_text(encoding="utf-8").splitlines()),
                1,
            )

    def test_serialization_failure_does_not_write_a_partial_line(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)

            self.assertFalse(store.save_screen({"bad": object()}))

            self.assertEqual(store.screens_path.read_bytes(), b"")
            errors = store.errors_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(errors), 1)
            self.assertEqual(json.loads(errors[0])["error_type"], "TypeError")
            store.close()

    def test_close_is_idempotent_and_manifest_update_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)

            self.assertTrue(store.close())
            first_manifest = store.manifest_path.read_text(encoding="utf-8")
            self.assertTrue(store.close())

            self.assertEqual(
                store.manifest_path.read_text(encoding="utf-8"), first_manifest
            )
            self.assertEqual(list(store.run_dir.glob(".run.*.tmp")), [])

    def test_call_after_close_is_rejected_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)
            store.close()

            self.assertFalse(store.save_screen(self.make_screen()))
            self.assertEqual(store.screens_path.read_bytes(), b"")

    def test_initialization_failure_returns_disabled_store(self):
        with tempfile.TemporaryDirectory() as temporary:
            root_file = Path(temporary) / "not-a-directory"
            root_file.write_text("occupied", encoding="utf-8")

            store = self.make_store(root_file)

            self.assertFalse(store.enabled)
            self.assertEqual(store.manifest.status, RunStatus.DISABLED)
            self.assertEqual(store.manifest.error_count, 1)
            self.assertFalse(store.save_screen(self.make_screen()))
            self.assertFalse(store.close())

    def test_repeated_disk_failures_disable_store_without_infinite_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary, consecutive_failure_limit=2)
            original_append = store._append_line
            call_count = 0

            def fail_non_error(path, value):
                nonlocal call_count
                call_count += 1
                if path == store.screens_path:
                    raise PermissionError("synthetic permission failure")
                return original_append(path, value)

            with patch.object(store, "_append_line", side_effect=fail_non_error):
                self.assertFalse(store.save_screen(self.make_screen("1")))
                self.assertFalse(store.save_screen(self.make_screen("2")))
                calls_after_disable = call_count
                self.assertFalse(store.save_screen(self.make_screen("3")))

            self.assertFalse(store.enabled)
            self.assertEqual(call_count, calls_after_disable)
            self.assertEqual(store.manifest.status, RunStatus.DISABLED)
            self.assertEqual(
                len(store.errors_path.read_text(encoding="utf-8").splitlines()),
                2,
            )
            store.close()

    def test_concurrent_appends_are_complete_and_counted(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)
            thread_count = 6
            per_thread = 20

            def append_batch(thread_index):
                for item_index in range(per_thread):
                    store.save_screen(
                        self.make_screen("{0}-{1}".format(thread_index, item_index))
                    )

            threads = [
                threading.Thread(target=append_batch, args=(index,))
                for index in range(thread_count)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            store.close()

            lines = store.screens_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), thread_count * per_thread)
            self.assertTrue(all(json.loads(line) for line in lines))
            manifest = json.loads(
                store.manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["screen_record_count"], thread_count * per_thread
            )

    def test_fsync_default_is_disabled_and_can_be_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            default = self.make_store(Path(temporary) / "default")
            durable = JsonlOcrRecordStore(
                Path(temporary) / "durable", run_id="durable", fsync=True
            )

            self.assertFalse(default.fsync_enabled)
            self.assertTrue(durable.fsync_enabled)
            default.close()
            durable.close()

    def test_error_context_discards_unapproved_text_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)

            self.assertTrue(store.save_error(
                "SyntheticError",
                "assemble_candidate",
                {
                    "candidate_record_id": "candidate-test",
                    "raw_text": "should-not-be-stored",
                    "email": "private@example.test",
                },
            ))
            store.close()

            record = json.loads(
                store.errors_path.read_text(encoding="utf-8").strip()
            )
            self.assertEqual(
                record["context"], {"candidate_record_id": "candidate-test"}
            )


if __name__ == "__main__":
    unittest.main()
