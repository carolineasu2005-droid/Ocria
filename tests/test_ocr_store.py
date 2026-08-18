import json
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import ocr_store
from ocr_candidate import CandidateOcrBuilder
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_records import (
    CandidateOcrDocument,
    CaptureStatus,
    CaptureSummary,
    CaptureType,
    OcrBox,
    OcrScreenRecord,
    RunStatus,
    ScreeningProfileBinding,
)
from ocr_store import JsonlOcrRecordStore
from ocr_text import OCRItem


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

    def make_r06_record_candidate(self, candidate_id, *, screen_count=1):
        builder = CandidateOcrBuilder(
            "run-test", 1, candidate_record_id=candidate_id,
            created_at="2026-07-30T12:00:00+08:00",
            aggregation_mode="record", similarity_mode="record",
        )
        screens = []
        for index in range(1, screen_count + 1):
            screen_id = "{0}-screen-{1}".format(candidate_id, index)
            item = OCRItem(
                "synthetic {0} C++".format(index), 0.95,
                ((0, 0), (100, 0), (100, 20), (0, 20)),
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
        return builder.finalize(
            CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
        ), tuple(screens)

    def test_validation_failure_releases_record_mode_candidate_digests(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary, aggregation_mode="record", similarity_mode="record",
            )
            document, screens = self.make_r06_record_candidate("candidate-failed")
            self.assertTrue(store.save_screen(screens[0]))
            mismatched_screen = replace(
                document.screens[0], captured_at="2026-08-02T10:00:00+08:00",
            )
            mismatched_document = replace(document, screens=(mismatched_screen,))

            self.assertFalse(store.save_candidate(mismatched_document))
            self.assertEqual(store.candidates_path.read_bytes(), b"")
            self.assertEqual(len(store._saved_screen_digests), 0)
            store.close()

    def test_success_releases_only_its_candidate_digests_and_keeps_other_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary, aggregation_mode="record", similarity_mode="record",
            )
            document_a, screens_a = self.make_r06_record_candidate("candidate-a")
            document_b, screens_b = self.make_r06_record_candidate("candidate-b")
            for screen in screens_a + screens_b:
                self.assertTrue(store.save_screen(screen))

            self.assertTrue(store.save_candidate(document_a))
            self.assertEqual(
                set(store._saved_screen_digests),
                {store._screen_digest_key(screen) for screen in screens_b},
            )
            self.assertTrue(store.save_candidate(document_b))
            self.assertEqual(store._saved_screen_digests, {})
            self.assertEqual(
                len(store.candidates_path.read_text(encoding="utf-8").splitlines()),
                2,
            )
            store.close()

    def test_candidate_append_failure_releases_digests_and_next_candidate_can_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary, aggregation_mode="record", similarity_mode="record",
            )
            failed_document, failed_screens = self.make_r06_record_candidate("candidate-append-failed")
            self.assertTrue(store.save_screen(failed_screens[0]))
            original_append = store._append_line

            def fail_candidate_append(path, value):
                if path == store.candidates_path:
                    raise PermissionError("synthetic append failure")
                return original_append(path, value)

            with patch.object(store, "_append_line", side_effect=fail_candidate_append):
                self.assertFalse(store.save_candidate(failed_document))
            self.assertEqual(store.candidates_path.read_bytes(), b"")
            self.assertEqual(store._saved_screen_digests, {})
            self.assertTrue(store.screens_path.read_bytes())

            next_document, next_screens = self.make_r06_record_candidate("candidate-after-append-failure")
            self.assertTrue(store.save_screen(next_screens[0]))
            self.assertTrue(store.save_candidate(next_document))
            self.assertEqual(store._saved_screen_digests, {})
            store.close()

    def test_one_hundred_validation_failures_do_not_accumulate_digest_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary,
                aggregation_mode="record",
                similarity_mode="record",
                consecutive_failure_limit=101,
            )
            for index in range(100):
                document, screens = self.make_r06_record_candidate(
                    "candidate-failure-{0}".format(index),
                )
                self.assertTrue(store.save_screen(screens[0]))
                mismatched = replace(
                    document.screens[0],
                    captured_at="2026-08-02T10:{0:02d}:00+08:00".format(index % 60),
                )
                self.assertFalse(store.save_candidate(
                    replace(document, screens=(mismatched,)),
                ))
                self.assertEqual(store._saved_screen_digests, {})
            self.assertTrue(store.enabled)
            self.assertEqual(store.candidates_path.read_bytes(), b"")
            store.close()

    def test_validation_failure_releases_only_failing_candidate_and_eight_screen_order_is_digest_safe(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary, aggregation_mode="record", similarity_mode="record",
            )
            document_a, screens_a = self.make_r06_record_candidate("candidate-a-fail")
            document_b, screens_b = self.make_r06_record_candidate(
                "candidate-b-eight", screen_count=8,
            )
            for screen in screens_a + screens_b:
                self.assertTrue(store.save_screen(screen))

            mismatched_a = replace(
                document_a.screens[0], captured_at="2026-08-02T10:00:00+08:00",
            )
            self.assertFalse(store.save_candidate(
                replace(document_a, screens=(mismatched_a,)),
            ))
            self.assertEqual(
                set(store._saved_screen_digests),
                {store._screen_digest_key(screen) for screen in screens_b},
            )

            self.assertTrue(store.save_candidate(
                replace(document_b, screens=tuple(reversed(document_b.screens))),
            ))
            self.assertEqual(store._saved_screen_digests, {})
            store.close()

    def test_missing_or_duplicate_digest_validation_failure_cleanup_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)
            first = self.make_screen("duplicate")
            second = replace(self.make_screen("second"), screen_id=first.screen_id)
            document = self.make_document((first, second))
            self.assertTrue(store.save_screen(first))

            self.assertFalse(store.save_candidate(document))
            self.assertEqual(store._saved_screen_digests, {})
            owner_key = (store.run_id, document.candidate_record_id)
            store._release_candidate_screen_digests(owner_key)
            store._release_candidate_screen_digests(owner_key)
            self.assertEqual(store._saved_screen_digests, {})
            self.assertTrue(store.close())

    def test_close_releases_unfinalized_screen_digest_cache_idempotently(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary, aggregation_mode="record", similarity_mode="record",
            )
            _, screens = self.make_r06_record_candidate("candidate-unfinalized")
            self.assertTrue(store.save_screen(screens[0]))
            self.assertEqual(len(store._saved_screen_digests), 1)

            self.assertTrue(store.close())
            self.assertEqual(store._saved_screen_digests, {})
            self.assertEqual(store._candidate_screen_digest_keys, {})
            self.assertTrue(store.close())
            self.assertEqual(store._saved_screen_digests, {})
            self.assertEqual(store._candidate_screen_digest_keys, {})

    def test_r06_audit_001_identity_matrix_releases_trusted_owner_only(self):
        """R06-AUDIT-001: forged documents cannot retain or steal owner keys."""

        variants = (
            "document_run",
            "document_candidate",
            "embedded_run",
            "embedded_candidate",
            "embedded_screen_id",
            "mixed",
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary, aggregation_mode="record", similarity_mode="record",
                consecutive_failure_limit=20,
            )
            document_b, screens_b = self.make_r06_record_candidate("candidate-b")
            document_c, screens_c = self.make_r06_record_candidate("candidate-c")
            for screen in screens_b + screens_c:
                self.assertTrue(store.save_screen(screen))
            expected_other = {
                store._screen_digest_key(screens_b[0]),
                store._screen_digest_key(screens_c[0]),
            }

            for variant in variants:
                candidate_id = "candidate-a-{0}".format(variant)
                document_a, screens_a = self.make_r06_record_candidate(candidate_id)
                self.assertTrue(store.save_screen(screens_a[0]))
                original_screen_bytes = store.screens_path.read_bytes()
                if variant == "document_run":
                    forged = replace(document_a, run_id="other-run")
                elif variant == "document_candidate":
                    forged = replace(document_a, candidate_record_id="candidate-b")
                elif variant == "embedded_run":
                    forged = replace(document_a, screens=(replace(
                        document_a.screens[0], run_id="other-run"),))
                elif variant == "embedded_candidate":
                    forged = replace(document_a, screens=(replace(
                        document_a.screens[0], candidate_record_id="candidate-b"),))
                elif variant == "embedded_screen_id":
                    # A post-validation persistence corruption can alter this
                    # identity without rebuilding the R04-derived segment IDs.
                    forged_screen = replace(document_a.screens[0])
                    object.__setattr__(
                        forged_screen, "screen_id", "candidate-b-screen-1",
                    )
                    forged = replace(document_a)
                    object.__setattr__(forged, "screens", (forged_screen,))
                else:
                    forged = replace(document_a)
                    object.__setattr__(forged, "screens", (
                        document_a.screens[0], screens_b[0],
                    ))

                self.assertFalse(store.save_candidate(
                    forged, owner_candidate_record_id=candidate_id,
                ))
                self.assertEqual(store.screens_path.read_bytes(), original_screen_bytes)
                self.assertEqual(store.candidates_path.read_bytes(), b"")
                self.assertEqual(set(store._saved_screen_digests), expected_other)
                self.assertEqual(
                    set(store._candidate_screen_digest_keys),
                    {("run-test", "candidate-b"), ("run-test", "candidate-c")},
                )

            self.assertTrue(store.save_candidate(document_b))
            self.assertEqual(
                set(store._saved_screen_digests),
                {store._screen_digest_key(screens_c[0])},
            )
            self.assertTrue(store.save_candidate(document_c))
            self.assertEqual(store._saved_screen_digests, {})
            self.assertEqual(store._candidate_screen_digest_keys, {})
            store.close()

    def test_r06_audit_002_rejects_document_owned_by_another_trusted_owner(self):
        """R06-AUDIT-002: an explicit owner binds the candidate write."""

        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary, aggregation_mode="record", similarity_mode="record",
                consecutive_failure_limit=20,
            )
            document_a, screens_a = self.make_r06_record_candidate("candidate-a")
            document_b, screens_b = self.make_r06_record_candidate("candidate-b")
            _, screens_c = self.make_r06_record_candidate("candidate-c")
            for screen in screens_a + screens_b + screens_c:
                self.assertTrue(store.save_screen(screen))
            original_screens = store.screens_path.read_bytes()

            with patch.object(
                store, "_append_line", wraps=store._append_line,
            ) as append, patch(
                "ocr_store.json_dumps", wraps=ocr_store.json_dumps,
            ) as serialize, patch.object(
                store,
                "_release_candidate_screen_digests",
                wraps=store._release_candidate_screen_digests,
            ) as release:
                self.assertFalse(store.save_candidate(
                    document_b, owner_candidate_record_id="candidate-a",
                ))

            candidate_appends = [
                call for call in append.call_args_list
                if call.args[0] == store.candidates_path
            ]
            candidate_serializations = [
                call for call in serialize.call_args_list
                if isinstance(call.args[0], CandidateOcrDocument)
            ]
            self.assertEqual(candidate_appends, [])
            self.assertEqual(candidate_serializations, [])
            release.assert_called_once_with(("run-test", "candidate-a"))
            self.assertEqual(store.candidates_path.read_bytes(), b"")
            self.assertEqual(store.screens_path.read_bytes(), original_screens)
            self.assertEqual(
                set(store._saved_screen_digests),
                {
                    store._screen_digest_key(screens_b[0]),
                    store._screen_digest_key(screens_c[0]),
                },
            )
            self.assertEqual(
                set(store._candidate_screen_digest_keys),
                {("run-test", "candidate-b"), ("run-test", "candidate-c")},
            )
            self.assertTrue(store.save_candidate(
                document_b, owner_candidate_record_id="candidate-b",
            ))
            document_c, _ = self.make_r06_record_candidate("candidate-c")
            self.assertTrue(store.save_candidate(
                document_c, owner_candidate_record_id="candidate-c",
            ))
            self.assertEqual(store._saved_screen_digests, {})
            self.assertEqual(store._candidate_screen_digest_keys, {})
            self.assertTrue(store.close())

    def test_r06_audit_002_reverse_owner_mismatch_releases_only_owner(self):
        """R06-AUDIT-002: owner B cannot write candidate A either."""

        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary, aggregation_mode="record", similarity_mode="record",
            )
            document_a, screens_a = self.make_r06_record_candidate("candidate-a")
            _, screens_b = self.make_r06_record_candidate("candidate-b")
            for screen in screens_a + screens_b:
                self.assertTrue(store.save_screen(screen))

            self.assertFalse(store.save_candidate(
                document_a, owner_candidate_record_id="candidate-b",
            ))
            self.assertEqual(
                set(store._saved_screen_digests),
                {store._screen_digest_key(screens_a[0])},
            )
            self.assertEqual(
                set(store._candidate_screen_digest_keys),
                {("run-test", "candidate-a")},
            )
            self.assertTrue(store.save_candidate(
                document_a, owner_candidate_record_id="candidate-a",
            ))
            self.assertEqual(store._saved_screen_digests, {})
            self.assertEqual(store._candidate_screen_digest_keys, {})
            self.assertTrue(store.close())

    def test_r06_audit_002_thousand_owner_document_mismatches_are_isolated(self):
        """R06-AUDIT-002: rejecting A/B cannot retain or delete B state."""

        with tempfile.TemporaryDirectory() as temporary:
            with patch("ocr_store.logger"):
                store = self.make_store(
                    temporary, aggregation_mode="record", similarity_mode="record",
                    consecutive_failure_limit=1001,
                )
                for index in range(1000):
                    owner_id = "owner-{0}".format(index)
                    document_id = "document-{0}".format(index)
                    _, owner_screens = self.make_r06_record_candidate(owner_id)
                    document, document_screens = self.make_r06_record_candidate(
                        document_id,
                    )
                    self.assertTrue(store.save_screen(owner_screens[0]))
                    self.assertTrue(store.save_screen(document_screens[0]))
                    self.assertFalse(store.save_candidate(
                        document, owner_candidate_record_id=owner_id,
                    ))
                    self.assertNotIn(
                        ("run-test", owner_id),
                        store._candidate_screen_digest_keys,
                    )
                    self.assertIn(
                        ("run-test", document_id),
                        store._candidate_screen_digest_keys,
                    )
                    self.assertTrue(store.save_candidate(
                        document, owner_candidate_record_id=document_id,
                    ))
                self.assertTrue(store.enabled)
                self.assertEqual(store._saved_screen_digests, {})
                self.assertEqual(store._candidate_screen_digest_keys, {})
                self.assertEqual(len(store.candidates_path.read_bytes().splitlines()), 1000)
                self.assertTrue(store.close())
                self.assertEqual(store._saved_screen_digests, {})
                self.assertEqual(store._candidate_screen_digest_keys, {})

    def test_r06_audit_001_thousand_terminal_paths_release_all_store_state(self):
        """R06-AUDIT-001: 1,000 terminal paths retain neither cache nor owner."""

        def assert_released(store):
            self.assertEqual(store._saved_screen_digests, {})
            self.assertEqual(store._candidate_screen_digest_keys, {})

        with tempfile.TemporaryDirectory() as temporary:
            with patch("ocr_store.logger"):
                success = self.make_store(
                    Path(temporary) / "success",
                    aggregation_mode="record", similarity_mode="record",
                    consecutive_failure_limit=1001,
                )
                for index in range(1000):
                    candidate_id = "success-{0}".format(index)
                    document, screens = self.make_r06_record_candidate(candidate_id)
                    self.assertTrue(success.save_screen(screens[0]))
                    self.assertTrue(success.save_candidate(
                        document, owner_candidate_record_id=candidate_id,
                    ))
                    assert_released(success)
                self.assertTrue(success.close())
                assert_released(success)

                digest = self.make_store(
                    Path(temporary) / "digest",
                    aggregation_mode="record", similarity_mode="record",
                    consecutive_failure_limit=1001,
                )
                for index in range(1000):
                    candidate_id = "digest-{0}".format(index)
                    document, screens = self.make_r06_record_candidate(candidate_id)
                    self.assertTrue(digest.save_screen(screens[0]))
                    forged = replace(document, screens=(replace(
                        document.screens[0],
                        captured_at="2026-08-02T10:00:00+08:00",
                    ),))
                    self.assertFalse(digest.save_candidate(
                        forged, owner_candidate_record_id=candidate_id,
                    ))
                    assert_released(digest)
                self.assertTrue(digest.enabled)
                self.assertTrue(digest.close())

                identity = self.make_store(
                    Path(temporary) / "identity",
                    aggregation_mode="record", similarity_mode="record",
                    consecutive_failure_limit=1001,
                )
                for index in range(1000):
                    candidate_id = "identity-{0}".format(index)
                    document, screens = self.make_r06_record_candidate(candidate_id)
                    self.assertTrue(identity.save_screen(screens[0]))
                    forged = replace(document, screens=(replace(
                        document.screens[0], candidate_record_id="forged",
                    ),))
                    self.assertFalse(identity.save_candidate(
                        forged, owner_candidate_record_id=candidate_id,
                    ))
                    assert_released(identity)
                self.assertTrue(identity.enabled)
                self.assertTrue(identity.close())

                append = self.make_store(
                    Path(temporary) / "append",
                    aggregation_mode="record", similarity_mode="record",
                    consecutive_failure_limit=1001,
                )
                original_append = append._append_line

                def fail_candidate_append(path, value):
                    if path == append.candidates_path:
                        raise PermissionError("synthetic append failure")
                    return original_append(path, value)

                with patch.object(
                    append, "_append_line", side_effect=fail_candidate_append,
                ):
                    for index in range(1000):
                        candidate_id = "append-{0}".format(index)
                        document, screens = self.make_r06_record_candidate(candidate_id)
                        self.assertTrue(append.save_screen(screens[0]))
                        self.assertFalse(append.save_candidate(
                            document, owner_candidate_record_id=candidate_id,
                        ))
                        assert_released(append)
                self.assertTrue(append.enabled)
                self.assertEqual(append.candidates_path.read_bytes(), b"")
                self.assertTrue(append.close())

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

    def test_profile_binding_is_written_initially_and_preserved_on_close(self):
        binding = ScreeningProfileBinding(
            screening_profile_id="sp_" + "a" * 32,
            profile_version=2,
            criteria_digest="sha256:" + "b" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(
                temporary,
                screening_profile_binding=binding,
            )
            initial = json.loads(store.manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(initial["screening_profile_binding"], binding.to_dict())
            self.assertTrue(store.close())

            closed = json.loads(store.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(closed["screening_profile_binding"], binding.to_dict())
            self.assertEqual(
                set(closed["screening_profile_binding"]),
                {"screening_profile_id", "profile_version", "criteria_digest"},
            )

    def test_unbound_technical_store_remains_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary)

            self.assertTrue(store.enabled)
            manifest = json.loads(store.manifest_path.read_text(encoding="utf-8"))
            self.assertIsNone(manifest["screening_profile_binding"])
            self.assertTrue(store.close())

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
            store = self.make_store(
                temporary,
                normalization_version="r04-v1",
                ocr_min_confidence=0.85,
            )
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
            self.assertEqual(manifest["normalization_version"], "r04-v1")
            self.assertEqual(manifest["ocr_min_confidence"], 0.85)
            self.assertEqual(
                manifest["normalization_config_version"], "r04-config-v1"
            )
            self.assertEqual(len(manifest["normalization_config_digest"]), 64)
            self.assertEqual(manifest["effective_min_confidence"], 0.85)
            self.assertEqual(manifest["rule_evaluation_mode"], "legacy_shadow")
            self.assertEqual(
                manifest["normalization_config"]["effective_min_confidence"],
                0.85,
            )
            self.assertEqual(manifest["data_files"]["screens"], "screens.jsonl")
            self.assertEqual(
                len(store.candidates_path.read_text(encoding="utf-8").splitlines()),
                1,
            )

    def test_record_mode_persists_manifest_and_final_r05_screen_before_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary, aggregation_mode="record")
            screen_id = "screen-r05-store"
            item = OCRItem(
                "候选人 R05 Store 验证 Unity C++ .NET",
                0.95,
                ((0, 0), (100, 0), (100, 20), (0, 20)),
            )
            normalization = normalize_ocr_text((NormalizationBox(
                "{0}:box:0".format(screen_id), item.text, item.box, 0,
                item.confidence,
            ),))
            builder = CandidateOcrBuilder(
                "run-test", 1, candidate_record_id="candidate-test",
                created_at="2026-07-30T12:00:00+08:00",
                aggregation_mode="record",
                similarity_mode="disabled",
            )
            screen = builder.build_screen_record(
                (item,), capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True, screen_index=1, screen_id=screen_id,
                captured_at="2026-07-30T12:00:01+08:00",
                normalization=normalization, ocr_min_confidence=0.85,
            )
            document = builder.finalize(
                CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            )

            self.assertTrue(store.save_screen(screen))
            self.assertTrue(store.save_candidate(document))
            self.assertTrue(store.close())

            manifest = json.loads(store.manifest_path.read_text(encoding="utf-8"))
            saved_screen = json.loads(store.screens_path.read_text(encoding="utf-8"))
            saved_candidate = json.loads(
                store.candidates_path.read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["aggregation_mode"], "record")
            self.assertEqual(manifest["aggregation_version"], "r05-v1")
            self.assertEqual(len(manifest["aggregation_config_digest"]), 64)
            self.assertEqual(saved_screen["aggregation_status"], "completed")
            self.assertEqual(saved_screen["new_segment_ids"], ["screen-r05-store:line:0"])
            self.assertEqual(saved_candidate["document_build_status"], "completed")
            self.assertEqual(saved_candidate["document_text"], item.text)

    def test_record_mode_allows_not_attempted_candidate_without_formal_screen(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary, aggregation_mode="record")
            builder = CandidateOcrBuilder(
                "run-test", 1, candidate_record_id="candidate-test",
                created_at="2026-07-30T12:00:00+08:00", aggregation_mode="record",
                similarity_mode="disabled",
            )
            screen = builder.build_screen_record(
                (), capture_type=CaptureType.LOAD_CHECK, is_formal_screen=False,
                screen_index=None, screen_id="screen-r05-load-check",
                captured_at="2026-07-30T12:00:01+08:00",
            )
            document = builder.finalize(
                CaptureStatus.COMPLETED, end_reason="existing_flow_completed",
            )

            self.assertTrue(store.save_screen(screen))
            self.assertTrue(store.save_candidate(document))

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
            self.assertIsNone(store.manifest.screening_profile_binding)
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
                    "failure_stage": "screen_record_validation",
                    "validation_code": "r05_segment_partition_invalid",
                    "sanitized_error_message": (
                        "aggregation segment classifications are invalid"
                    ),
                    "raw_text": "should-not-be-stored",
                    "email": "private@example.test",
                },
            ))
            store.close()

            record = json.loads(
                store.errors_path.read_text(encoding="utf-8").strip()
            )
            self.assertEqual(
                record["context"], {
                    "candidate_record_id": "candidate-test",
                    "failure_stage": "screen_record_validation",
                    "validation_code": "r05_segment_partition_invalid",
                    "sanitized_error_message": (
                        "aggregation segment classifications are invalid"
                    ),
                }
            )

            self.assertNotIn("should-not-be-stored", json.dumps(record))
            self.assertNotIn("private@example.test", json.dumps(record))

    def test_error_context_rejects_unapproved_diagnostic_message(self):
        safe = JsonlOcrRecordStore._safe_context({
            "failure_stage": "private stage",
            "validation_code": "INVALID PRIVATE CODE",
            "sanitized_error_message": "private OCR body",
        })

        self.assertEqual(safe, {})

    def test_screen_manifest_identity_mismatch_is_rejected_without_partial_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = self.make_store(temporary, effective_min_confidence=0.90)
            screen_id = "screen-config-mismatch"
            item = OCRItem(
                "虚构配置不一致",
                0.95,
                ((0, 0), (20, 0), (20, 10), (0, 10)),
            )
            result = normalize_ocr_text((NormalizationBox(
                "{0}:box:0".format(screen_id),
                item.text,
                item.box,
                0,
                item.confidence,
            ),))
            builder = CandidateOcrBuilder(
                "run-test",
                1,
                candidate_record_id="candidate-test",
            )
            screen = builder.build_screen_record(
                (item,),
                capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True,
                screen_index=1,
                screen_id=screen_id,
                normalization=result,
                ocr_min_confidence=0.85,
            )

            self.assertFalse(store.save_screen(screen))
            self.assertEqual(store.screens_path.read_bytes(), b"")
            issue = json.loads(
                store.errors_path.read_text(encoding="utf-8").strip()
            )
            self.assertEqual(
                issue["error_type"], "ScreenManifestIdentityMismatchError"
            )
            self.assertNotIn(item.text, store.errors_path.read_text(encoding="utf-8"))
            store.close()


if __name__ == "__main__":
    unittest.main()
