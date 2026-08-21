from dataclasses import FrozenInstanceError, fields
import inspect
import unittest

import ai_candidate_input
from ai_candidate_input import AICandidateInput, build_ai_candidate_input
from ocr_candidate import CandidateOcrBuilder
from ocr_detector import RuleComparisonResult
from ocr_normalization import NormalizationBox, normalize_ocr_text
from ocr_records import CandidateOcrDocument, CaptureStatus, CaptureType
from ocr_text import OCRItem


class AICandidateInputTests(unittest.TestCase):
    def make_candidate(
        self,
        texts=("Candidate evidence text",),
        *,
        candidate_record_id="candidate-r09",
        metadata=None,
        rule_comparison=None,
        aggregation_mode="record",
    ):
        builder = CandidateOcrBuilder(
            "run-r09",
            1,
            candidate_record_id=candidate_record_id,
            created_at="2026-08-21T12:00:00+08:00",
            metadata={} if metadata is None else metadata,
            aggregation_mode=aggregation_mode,
            similarity_mode="disabled",
        )
        for index, text in enumerate(texts, start=1):
            screen_id = "screen-r09-{0}".format(index)
            item = OCRItem(
                text,
                0.99,
                ((0, 0), (240, 0), (240, 20), (0, 20)),
            )
            normalization = normalize_ocr_text((NormalizationBox(
                "{0}:box:0".format(screen_id),
                item.text,
                item.box,
                0,
                item.confidence,
            ),))
            builder.build_screen_record(
                (item,),
                capture_type=CaptureType.FORMAL_SCREEN,
                is_formal_screen=True,
                screen_index=index,
                screen_id=screen_id,
                captured_at="2026-08-21T12:00:{0:02d}+08:00".format(index),
                normalization=normalization,
                ocr_min_confidence=0.85,
                rule_comparison=(
                    rule_comparison if index == 1 else None
                ),
            )
        return builder.finalize(
            CaptureStatus.COMPLETED,
            end_reason="existing_flow_completed",
            completed_at="2026-08-21T12:01:00+08:00",
        )

    def make_missing_text_candidate(self, *, with_screen=False):
        return self.make_candidate(
            ("Screen raw fallback evidence",) if with_screen else (),
            aggregation_mode="disabled",
        )

    def test_non_blank_candidate_document_builds_input(self):
        candidate = self.make_candidate()

        result = build_ai_candidate_input(candidate)

        self.assertIsInstance(result, AICandidateInput)
        self.assertEqual(result.candidate_record_id, candidate.candidate_record_id)
        self.assertEqual(result.resume_text, candidate.document_text)

    def test_candidate_record_id_is_copied_exactly(self):
        candidate = self.make_candidate(candidate_record_id="candidate: exact id")

        result = build_ai_candidate_input(candidate)

        self.assertEqual(result.candidate_record_id, "candidate: exact id")
        self.assertEqual(result.candidate_record_id, candidate.candidate_record_id)

    def test_resume_text_is_copied_exactly(self):
        candidate = self.make_candidate(("Exact candidate text",))

        result = build_ai_candidate_input(candidate)

        self.assertEqual(result.resume_text, candidate.document_text)

    def test_leading_and_trailing_whitespace_is_preserved(self):
        candidate = self.make_candidate()
        source_text = "\n  Candidate resume text  \n"
        object.__setattr__(candidate, "document_text", source_text)

        result = build_ai_candidate_input(candidate)

        self.assertEqual(result.resume_text, source_text)

    def test_internal_newlines_and_multiscreen_text_are_preserved(self):
        candidate = self.make_candidate((
            "First Candidate screen evidence",
            "Second Candidate screen evidence",
        ))

        result = build_ai_candidate_input(candidate)

        self.assertIn("\n", candidate.document_text)
        self.assertEqual(result.resume_text, candidate.document_text)
        self.assertIn("First Candidate screen evidence", result.resume_text)
        self.assertIn("Second Candidate screen evidence", result.resume_text)

    def test_none_document_text_raises_value_error(self):
        candidate = self.make_missing_text_candidate()

        with self.assertRaisesRegex(
            ValueError,
            "^resume_text must contain non-whitespace text$",
        ):
            build_ai_candidate_input(candidate)

    def test_empty_document_text_raises_value_error(self):
        candidate = self.make_candidate()
        object.__setattr__(candidate, "document_text", "")

        with self.assertRaisesRegex(
            ValueError,
            "^resume_text must contain non-whitespace text$",
        ):
            build_ai_candidate_input(candidate)

    def test_whitespace_only_document_text_raises_value_error(self):
        candidate = self.make_candidate()
        object.__setattr__(candidate, "document_text", " \t\r\n")

        with self.assertRaisesRegex(
            ValueError,
            "^resume_text must contain non-whitespace text$",
        ):
            build_ai_candidate_input(candidate)

    def test_any_non_whitespace_character_allows_success(self):
        for source_text in ("x", " \n x \n "):
            with self.subTest(source_text=source_text):
                candidate = self.make_candidate()
                object.__setattr__(candidate, "document_text", source_text)

                result = build_ai_candidate_input(candidate)

                self.assertEqual(result.resume_text, source_text)

    def test_missing_text_never_falls_back_to_screen_raw_text(self):
        candidate = self.make_missing_text_candidate(with_screen=True)

        self.assertIsNone(candidate.document_text)
        self.assertIn("Screen raw fallback evidence", candidate.screens[0].raw_text)
        with self.assertRaisesRegex(
            ValueError,
            "^resume_text must contain non-whitespace text$",
        ):
            build_ai_candidate_input(candidate)

    def test_missing_text_never_falls_back_to_document_segments(self):
        candidate = self.make_candidate(("Segment fallback evidence",))
        self.assertTrue(candidate.document_segments)
        object.__setattr__(candidate, "document_text", None)

        with self.assertRaisesRegex(
            ValueError,
            "^resume_text must contain non-whitespace text$",
        ):
            build_ai_candidate_input(candidate)

    def test_repeated_build_is_deterministic(self):
        candidate = self.make_candidate()

        self.assertEqual(
            build_ai_candidate_input(candidate),
            build_ai_candidate_input(candidate),
        )

        object.__setattr__(candidate, "document_text", "")
        failures = []
        for _ in range(2):
            try:
                build_ai_candidate_input(candidate)
            except ValueError as exc:
                failures.append((type(exc), str(exc)))
        self.assertEqual(
            failures,
            [
                (ValueError, "resume_text must contain non-whitespace text"),
                (ValueError, "resume_text must contain non-whitespace text"),
            ],
        )

    def test_output_value_shape_and_constructor_contract_are_frozen(self):
        self.assertEqual(
            [field.name for field in fields(AICandidateInput)],
            ["candidate_record_id", "resume_text"],
        )
        value = AICandidateInput("candidate-r09", "resume text")
        with self.assertRaises(FrozenInstanceError):
            value.resume_text = "changed"
        with self.assertRaisesRegex(
            ValueError,
            "^candidate_record_id must be a string$",
        ):
            AICandidateInput(1, "resume text")
        for text in (None, 1, "", " \t\r\n"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(
                    ValueError,
                    "^resume_text must contain non-whitespace text$",
                ):
                    AICandidateInput("candidate-r09", text)

    def test_source_candidate_document_is_not_mutated(self):
        candidate = self.make_candidate(("Immutable Candidate evidence",))
        before_document = candidate.to_dict()
        before_screens = candidate.screens
        before_segments = candidate.document_segments
        before_metadata = dict(candidate.metadata)

        build_ai_candidate_input(candidate)

        self.assertEqual(candidate.to_dict(), before_document)
        self.assertIs(candidate.screens, before_screens)
        self.assertIs(candidate.document_segments, before_segments)
        self.assertEqual(candidate.metadata, before_metadata)

    def test_excluded_metadata_and_lifecycle_fields_do_not_affect_output(self):
        first = self.make_candidate(metadata={"source": "first"})
        second = self.make_candidate(metadata={"source": "second"})
        object.__setattr__(second, "dynamic_end_mode", "safe")
        object.__setattr__(second, "dynamic_end_reason", "scroll_bottom")
        object.__setattr__(second, "scan_slot_count", 8)

        self.assertEqual(first.candidate_record_id, second.candidate_record_id)
        self.assertEqual(first.document_text, second.document_text)
        self.assertNotEqual(first.metadata, second.metadata)
        self.assertEqual(
            build_ai_candidate_input(first),
            build_ai_candidate_input(second),
        )

    def test_legacy_comparison_fields_do_not_affect_output(self):
        comparison = RuleComparisonResult(
            rule_evaluation_mode="legacy_shadow",
            legacy_match=False,
            r04_match=True,
            comparison_outcome="r04_only",
            legacy_rule_index=None,
            r04_rule_index=1,
        )
        plain = self.make_candidate()
        legacy = self.make_candidate(rule_comparison=comparison)

        self.assertNotEqual(plain.screens[0].r04_match, legacy.screens[0].r04_match)
        self.assertEqual(plain.candidate_record_id, legacy.candidate_record_id)
        self.assertEqual(plain.document_text, legacy.document_text)
        self.assertEqual(
            build_ai_candidate_input(plain),
            build_ai_candidate_input(legacy),
        )

    def test_wrong_source_and_malformed_identity_fail_clearly(self):
        candidate = self.make_candidate()
        for source in ({}, "raw candidate text", [], candidate.screens[0]):
            with self.subTest(source=type(source).__name__):
                with self.assertRaisesRegex(
                    TypeError,
                    "^candidate must be a CandidateOcrDocument$",
                ):
                    build_ai_candidate_input(source)

        object.__setattr__(candidate, "candidate_record_id", 123)
        with self.assertRaisesRegex(
            ValueError,
            "^candidate_record_id must be a string$",
        ):
            build_ai_candidate_input(candidate)

    def test_output_has_exactly_two_fields_and_no_hash(self):
        result = build_ai_candidate_input(self.make_candidate())

        self.assertEqual(tuple(result.__dict__), (
            "candidate_record_id",
            "resume_text",
        ))
        for name in (
            "input_text_hash",
            "digest",
            "replay_hash",
            "cache_key",
            "version",
            "timestamp",
            "run_id",
            "capture_status",
            "warnings",
            "metadata",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(result, name))
                self.assertFalse(hasattr(ai_candidate_input, name))

    def test_projection_is_local_and_side_effect_free(self):
        candidate = self.make_candidate(("Local projection evidence",))
        before_document = candidate.to_dict()

        result = build_ai_candidate_input(candidate)

        self.assertEqual(candidate.to_dict(), before_document)
        self.assertEqual(result.candidate_record_id, candidate.candidate_record_id)
        self.assertEqual(result.resume_text, candidate.document_text)

    def test_public_api_has_no_screen_or_raw_text_builder(self):
        signature = inspect.signature(build_ai_candidate_input)
        parameters = tuple(signature.parameters.values())

        self.assertEqual(len(parameters), 1)
        self.assertEqual(parameters[0].name, "candidate")
        self.assertIs(parameters[0].annotation, CandidateOcrDocument)
        self.assertIs(signature.return_annotation, AICandidateInput)
        for name in (
            "build_from_screen",
            "build_from_raw_text",
            "build_from_screens",
        ):
            self.assertFalse(hasattr(ai_candidate_input, name))


if __name__ == "__main__":
    unittest.main()
