import inspect
import json
import unittest

import ai_screening_contract
from ai_screening_contract import (
    AIScreeningContractError,
    validate_ai_screening_response,
)
from screening_profile import Criterion


class AIScreeningContractTests(unittest.TestCase):
    CRITERIA = (
        Criterion("C001", "First Criterion"),
        Criterion("C002", "Second Criterion"),
        Criterion("C003", "Third Criterion"),
    )

    def raw_response(self, results):
        return json.dumps({
            "criteria_results": [
                {"criterion_id": criterion_id, "passed": passed}
                for criterion_id, passed in results
            ],
        })

    def valid_results(self):
        return (("C001", True), ("C002", False), ("C003", True))

    def assert_contract_error(self, raw_response, criteria=None):
        with self.assertRaises(AIScreeningContractError) as raised:
            validate_ai_screening_response(
                raw_response,
                self.CRITERIA if criteria is None else criteria,
            )
        return raised.exception

    def test_valid_complete_mixed_response_succeeds(self):
        result = validate_ai_screening_response(
            self.raw_response(self.valid_results()),
            self.CRITERIA,
        )

        self.assertEqual(
            result,
            {"C001": True, "C002": False, "C003": True},
        )
        self.assertEqual(list(result), ["C001", "C002", "C003"])

    def test_valid_all_true_and_all_false_responses_succeed(self):
        all_true = validate_ai_screening_response(
            self.raw_response((("C001", True), ("C002", True), ("C003", True))),
            self.CRITERIA,
        )
        all_false = validate_ai_screening_response(
            self.raw_response((("C001", False), ("C002", False), ("C003", False))),
            self.CRITERIA,
        )

        self.assertEqual(all_true, {"C001": True, "C002": True, "C003": True})
        self.assertEqual(all_false, {"C001": False, "C002": False, "C003": False})
        self.assertTrue(all(type(value) is bool for value in all_true.values()))
        self.assertTrue(all(type(value) is bool for value in all_false.values()))

    def test_reordered_results_and_json_grammar_whitespace_succeed(self):
        raw_response = " \n\t" + self.raw_response((
            ("C003", True),
            ("C001", True),
            ("C002", False),
        )) + "\r\n "

        result = validate_ai_screening_response(raw_response, self.CRITERIA)

        self.assertEqual(
            result,
            {"C001": True, "C002": False, "C003": True},
        )
        self.assertEqual(list(result), ["C001", "C002", "C003"])

    def test_full_input_json_failures_are_rejected(self):
        valid = self.raw_response(self.valid_results())
        cases = {
            "prose before": "Result: " + valid,
            "prose after": valid + " end",
            "fenced JSON": "```json\n" + valid + "\n```",
            "malformed JSON": '{"criteria_results":[}',
            "multiple values": valid + " {}",
        }

        for name, raw_response in cases.items():
            with self.subTest(name=name):
                self.assert_contract_error(raw_response)

    def test_duplicate_json_members_are_rejected_at_all_object_levels(self):
        self.assert_contract_error(
            '{"criteria_results":[],"criteria_results":[]}'
        )
        self.assert_contract_error(
            '{"criteria_results":[{"criterion_id":"C001",'
            '"criterion_id":"C001","passed":true}]}'
        )

    def test_top_level_and_item_schema_failures_are_rejected(self):
        cases = {
            "top-level list": "[]",
            "top-level string": '"response"',
            "top-level null": "null",
            "missing criteria_results": "{}",
            "extra top-level field": (
                '{"criteria_results":[],"extra":true}'
            ),
            "criteria_results object": '{"criteria_results":{}}',
            "item string": '{"criteria_results":["item"]}',
            "missing criterion_id": (
                '{"criteria_results":[{"passed":true}]}'
            ),
            "missing passed": (
                '{"criteria_results":[{"criterion_id":"C001"}]}'
            ),
            "extra item field": (
                '{"criteria_results":[{"criterion_id":"C001",'
                '"passed":true,"extra":0}]}'
            ),
        }

        for name, raw_response in cases.items():
            with self.subTest(name=name):
                self.assert_contract_error(raw_response)

    def test_only_exact_booleans_are_accepted(self):
        for value in ("true", "false", 1, 0, None, {}, []):
            with self.subTest(value=value):
                self.assert_contract_error(
                    self.raw_response((("C001", value),))
                )

        result = validate_ai_screening_response(
            self.raw_response(self.valid_results()),
            self.CRITERIA,
        )
        self.assertTrue(all(type(value) is bool for value in result.values()))

    def test_criterion_identity_failures_are_rejected_without_normalization(self):
        cases = {
            "unknown": (("C001", True), ("C002", False), ("C999", True)),
            "missing": (("C001", True), ("C002", False)),
            "duplicate": (("C001", True), ("C002", False), ("C001", True)),
            "different case": (("c001", True), ("C002", False), ("C003", True)),
            "trailing space": (("C001 ", True), ("C002", False), ("C003", True)),
            "leading space": ((" C001", True), ("C002", False), ("C003", True)),
            "rewritten": (("Criterion C001", True), ("C002", False), ("C003", True)),
        }

        before_ids = tuple(criterion.criterion_id for criterion in self.CRITERIA)
        for name, results in cases.items():
            with self.subTest(name=name):
                self.assert_contract_error(self.raw_response(results))
        self.assertEqual(
            tuple(criterion.criterion_id for criterion in self.CRITERIA),
            before_ids,
        )

    def test_complete_mapping_and_failure_paths_never_escape_partial_or_false_data(self):
        complete = validate_ai_screening_response(
            self.raw_response(self.valid_results()),
            self.CRITERIA,
        )
        self.assertEqual(set(complete), {"C001", "C002", "C003"})

        invalid_cases = (
            (("C001", True), ("C002", "false"), ("C003", True)),
            (("C001", False), ("C002", False)),
            (("C001", True), ("C002", False), ("C001", False)),
        )
        for results in invalid_cases:
            with self.subTest(results=results):
                self.assert_contract_error(self.raw_response(results))

    def test_validation_is_deterministic_for_success_and_failure(self):
        valid = self.raw_response(self.valid_results())
        invalid = self.raw_response((("C001", True),))

        self.assertEqual(
            validate_ai_screening_response(valid, self.CRITERIA),
            validate_ai_screening_response(valid, self.CRITERIA),
        )
        failures = []
        for _ in range(2):
            try:
                validate_ai_screening_response(invalid, self.CRITERIA)
            except AIScreeningContractError as error:
                failures.append((type(error), str(error)))
        self.assertEqual(failures[0], failures[1])

    def test_non_json_constants_are_rejected(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                self.assert_contract_error(
                    '{"criteria_results":[{"criterion_id":"C001",'
                    '"passed":' + constant + "}]}"
                )

    def test_public_argument_type_checks(self):
        with self.assertRaises(TypeError):
            validate_ai_screening_response({}, self.CRITERIA)
        for criteria in (
            [],
            (),
            ("C001",),
        ):
            with self.subTest(criteria=criteria):
                with self.assertRaises(TypeError):
                    validate_ai_screening_response("{}", criteria)

    def test_successful_mapping_is_directly_r06_compatible(self):
        from screening_rule_engine import (
            ScreeningRule,
            ScreeningRuleSet,
            evaluate_rule_set,
        )

        result = validate_ai_screening_response(
            self.raw_response(self.valid_results()),
            self.CRITERIA,
        )

        self.assertFalse(
            evaluate_rule_set(
                ScreeningRuleSet((ScreeningRule("C001 AND C002 AND C003"),)),
                result,
            )
        )

    def test_validator_has_no_r06_or_provider_runtime_dependency(self):
        source = inspect.getsource(ai_screening_contract)

        self.assertNotIn("screening_rule_engine", source)
        self.assertNotIn("llm_provider_runtime", source)
        self.assertNotIn("ai_provider", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("socket", source)
        self.assertEqual(
            validate_ai_screening_response(
                self.raw_response(self.valid_results()),
                self.CRITERIA,
            ),
            {"C001": True, "C002": False, "C003": True},
        )


if __name__ == "__main__":
    unittest.main()
