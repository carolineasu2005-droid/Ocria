from dataclasses import fields
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ai_screening_persistence import (
    AIAttemptErrorRecord,
    AIFinalOutcomeRecord,
    AIPersistenceIntegrityError,
    AIScreeningRecordStore,
    CandidateDecisionRecord,
)


class AIScreeningPersistenceTests(unittest.TestCase):
    def make_error_record(self, **overrides):
        values = {
            "run_id": "run-r13",
            "candidate_record_id": "candidate-r13",
            "attempt_number": 1,
            "failure_stage": "provider_runtime",
            "failure_type": "LLMRuntimeError",
            "occurred_at": "2026-08-22T12:00:00+00:00",
            "error_code": "rate_limit",
            "provider": "qwen",
            "operation": "complete",
            "status_code": 429,
            "request_id": "request-r13",
            "message": "safe failure",
        }
        values.update(overrides)
        return AIAttemptErrorRecord(**values)

    def make_result_record(self, **overrides):
        values = {
            "run_id": "run-r13",
            "candidate_record_id": "candidate-r13",
            "ai_status": "completed",
            "criteria_results": {"C001": True},
            "attempts_used": 1,
            "screening_profile_id": "sp_" + "a" * 32,
            "profile_version": 1,
            "criteria_digest": "digest-r13",
            "provider": "qwen",
            "model": "qwen-test",
        }
        values.update(overrides)
        return AIFinalOutcomeRecord(**values)

    def make_decision_record(self, **overrides):
        values = {
            "run_id": "run-r13",
            "candidate_record_id": "candidate-r13",
            "decision_status": "qualified",
        }
        values.update(overrides)
        return CandidateDecisionRecord(**values)

    def test_attempt_error_record_exact_schema_and_validation(self):
        record = self.make_error_record(
            error_code=None,
            provider=None,
            operation=None,
            status_code=None,
            request_id=None,
            message=None,
        )

        self.assertEqual(
            [field.name for field in fields(AIAttemptErrorRecord)],
            [
                "run_id",
                "candidate_record_id",
                "attempt_number",
                "failure_stage",
                "failure_type",
                "occurred_at",
                "error_code",
                "provider",
                "operation",
                "status_code",
                "request_id",
                "message",
            ],
        )
        for overrides in (
            {"run_id": ""},
            {"candidate_record_id": ""},
            {"attempt_number": True},
            {"attempt_number": 4},
            {"failure_stage": "other"},
            {"failure_type": ""},
            {"occurred_at": "2026-08-22T12:00:00"},
            {"status_code": True},
            {"status_code": 0},
            {"request_id": ""},
            {"message": "x" * 513},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self.make_error_record(**overrides)
        self.assertIsNone(record.message)

    def test_final_outcome_record_completed_failed_schemas(self):
        completed = self.make_result_record()
        failed = self.make_result_record(
            ai_status="failed",
            criteria_results=None,
            attempts_used=3,
        )

        self.assertEqual(
            [field.name for field in fields(AIFinalOutcomeRecord)],
            [
                "run_id",
                "candidate_record_id",
                "ai_status",
                "criteria_results",
                "attempts_used",
                "screening_profile_id",
                "profile_version",
                "criteria_digest",
                "provider",
                "model",
            ],
        )
        self.assertEqual(completed.criteria_results, {"C001": True})
        self.assertIsNone(failed.criteria_results)
        for overrides in (
            {"ai_status": "other"},
            {"ai_status": "completed", "criteria_results": None},
            {"ai_status": "completed", "criteria_results": {"C001": 1}},
            {"ai_status": "failed", "criteria_results": {"C001": True}},
            {"attempts_used": False},
            {"attempts_used": 0},
            {"profile_version": True},
            {"profile_version": 0},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    self.make_result_record(**overrides)

    def test_decision_record_exact_schema_and_no_action_fields(self):
        record = self.make_decision_record()

        self.assertEqual(
            [field.name for field in fields(CandidateDecisionRecord)],
            ["run_id", "candidate_record_id", "decision_status"],
        )
        for status in ("qualified", "rejected", "ai_failed"):
            self.assertEqual(
                self.make_decision_record(decision_status=status).decision_status,
                status,
            )
        with self.assertRaises(ValueError):
            self.make_decision_record(decision_status="action_failed")
        self.assertFalse(hasattr(record, "action_result"))

    def test_store_initializes_exact_three_streams_in_existing_run_dir(self):
        with TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            store = AIScreeningRecordStore(run_dir, "run-r13")

            self.assertEqual(store.run_id, "run-r13")
            self.assertEqual(
                sorted(path.name for path in run_dir.iterdir()),
                ["ai_errors.jsonl", "ai_results.jsonl", "decisions.jsonl"],
            )
            self.assertTrue(all(
                not path.read_text(encoding="utf-8")
                for path in run_dir.iterdir()
            ))
        with TemporaryDirectory() as temporary_directory:
            missing_dir = Path(temporary_directory) / "missing"
            with self.assertRaises(ValueError):
                AIScreeningRecordStore(missing_dir, "run-r13")

    def test_appends_compact_utf8_single_lines_and_acknowledges_after_close(self):
        with TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            store = AIScreeningRecordStore(run_dir, "run-r13")
            error_record = self.make_error_record(
                error_code=None,
                provider=None,
                operation=None,
                status_code=None,
                request_id=None,
                message=None,
            )
            result_record = self.make_result_record()
            decision_record = self.make_decision_record()

            self.assertIsNone(store.append_ai_error(error_record))
            self.assertIsNone(store.append_ai_result(result_record))
            self.assertIsNone(store.append_decision(decision_record))

            error_text = store.ai_errors_path.read_text(encoding="utf-8")
            result_text = store.ai_results_path.read_text(encoding="utf-8")
            decision_text = store.decisions_path.read_text(encoding="utf-8")
            self.assertEqual(
                error_text,
                '{"run_id":"run-r13","candidate_record_id":"candidate-r13",'
                '"attempt_number":1,"failure_stage":"provider_runtime",'
                '"failure_type":"LLMRuntimeError",'
                '"occurred_at":"2026-08-22T12:00:00+00:00",'
                '"error_code":null,"provider":null,"operation":null,'
                '"status_code":null,"request_id":null,"message":null}\n',
            )
            self.assertEqual(json.loads(result_text), {
                "run_id": "run-r13",
                "candidate_record_id": "candidate-r13",
                "ai_status": "completed",
                "criteria_results": {"C001": True},
                "attempts_used": 1,
                "screening_profile_id": "sp_" + "a" * 32,
                "profile_version": 1,
                "criteria_digest": "digest-r13",
                "provider": "qwen",
                "model": "qwen-test",
            })
            self.assertEqual(json.loads(decision_text), {
                "run_id": "run-r13",
                "candidate_record_id": "candidate-r13",
                "decision_status": "qualified",
            })
            with self.assertRaises(TypeError):
                store.append_ai_error(result_record)
            with self.assertRaises(ValueError):
                store.append_decision(
                    self.make_decision_record(run_id="other-run")
                )

    def test_writer_oserror_raises_integrity_error_without_retry_or_read_api(self):
        with TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            with patch.object(Path, "open", side_effect=OSError("initialize")):
                with self.assertRaises(AIPersistenceIntegrityError) as raised:
                    AIScreeningRecordStore(run_dir, "run-r13")
            self.assertEqual(raised.exception.operation, "initialize")
            self.assertEqual(raised.exception.path, run_dir / "ai_results.jsonl")
            self.assertEqual(
                str(raised.exception),
                "R13 persistence integrity failure during initialize",
            )

            store = AIScreeningRecordStore(run_dir, "run-r13")
            with patch.object(Path, "open", side_effect=OSError("write")) as open_mock:
                with self.assertRaises(AIPersistenceIntegrityError) as raised:
                    store.append_decision(self.make_decision_record())
            self.assertEqual(raised.exception.operation, "write_decision")
            self.assertEqual(raised.exception.path, store.decisions_path)
            open_mock.assert_called_once()
            for read_name in ("read", "load", "list", "query", "replay", "cache"):
                self.assertFalse(hasattr(store, read_name))


if __name__ == "__main__":
    unittest.main()
