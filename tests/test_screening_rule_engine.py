import inspect
import unittest
from dataclasses import FrozenInstanceError, fields
from types import MappingProxyType

from screening_rule_engine import (
    ScreeningRule,
    ScreeningRuleInputError,
    ScreeningRuleSet,
    ScreeningRuleValidationError,
    evaluate_rule_set,
)


def rule_set(*expressions):
    return ScreeningRuleSet(tuple(
        ScreeningRule(expression) for expression in expressions
    ))


class ScreeningRuleEngineTests(unittest.TestCase):
    def test_public_value_shapes_are_frozen_and_constructor_only_checks_shape(self):
        rule = ScreeningRule("C001ANDC002")
        duplicate_rule_set = ScreeningRuleSet((rule, rule))

        self.assertEqual(
            tuple(field.name for field in fields(ScreeningRule)),
            ("expression",),
        )
        self.assertEqual(
            tuple(field.name for field in fields(ScreeningRuleSet)),
            ("rules",),
        )
        self.assertEqual(duplicate_rule_set.rules, (rule, rule))
        with self.assertRaises(FrozenInstanceError):
            rule.expression = "C001"
        with self.assertRaises(FrozenInstanceError):
            duplicate_rule_set.rules = ()

        for expression in (None, "", " \t\n"):
            with self.subTest(expression=expression):
                with self.assertRaises(ScreeningRuleValidationError):
                    ScreeningRule(expression)
        for rules in ((), [rule], ("C001",)):
            with self.subTest(rules=rules):
                with self.assertRaises(ScreeningRuleValidationError):
                    ScreeningRuleSet(rules)

    def test_evaluate_requires_the_public_rule_set_and_mapping_types(self):
        valid_rule_set = rule_set("C001")

        self.assertTrue(evaluate_rule_set(
            valid_rule_set,
            MappingProxyType({"C001": True}),
        ))
        with self.assertRaises(ScreeningRuleValidationError):
            evaluate_rule_set("C001", {"C001": True})
        with self.assertRaises(ScreeningRuleInputError):
            evaluate_rule_set(valid_rule_set, [("C001", True)])

    def test_single_rule_and_r05_criterion_id_forms(self):
        for criterion_id in ("C001", "C025", "C999", "C1000"):
            with self.subTest(criterion_id=criterion_id):
                self.assertTrue(evaluate_rule_set(
                    rule_set(criterion_id),
                    {criterion_id: True},
                ))

        self.assertTrue(evaluate_rule_set(
            rule_set("C0001"),
            {"C0001": True},
        ))
        with self.assertRaises(ScreeningRuleInputError):
            evaluate_rule_set(rule_set("C0001"), {"C001": True})

    def test_boolean_mapping_and_insertion_order(self):
        rules = rule_set("C001 OR C002")
        first = {"C001": False, "C002": True}
        second = {"C002": True, "C001": False}

        self.assertTrue(evaluate_rule_set(rules, first))
        self.assertEqual(
            evaluate_rule_set(rules, first),
            evaluate_rule_set(rules, second),
        )

    def test_and_truth_table(self):
        rules = rule_set("C001 AND C002")
        for left, right, expected in (
            (False, False, False),
            (False, True, False),
            (True, False, False),
            (True, True, True),
        ):
            with self.subTest(left=left, right=right):
                self.assertIs(
                    evaluate_rule_set(
                        rules,
                        {"C001": left, "C002": right},
                    ),
                    expected,
                )

    def test_or_truth_table(self):
        rules = rule_set("C001 OR C002")
        for left, right, expected in (
            (False, False, False),
            (False, True, True),
            (True, False, True),
            (True, True, True),
        ):
            with self.subTest(left=left, right=right):
                self.assertIs(
                    evaluate_rule_set(
                        rules,
                        {"C001": left, "C002": right},
                    ),
                    expected,
                )

    def test_parenthesized_grouping(self):
        self.assertTrue(evaluate_rule_set(
            rule_set("C001 AND (C002 OR C003)"),
            {"C001": True, "C002": False, "C003": True},
        ))

    def test_and_precedence_and_parentheses_override(self):
        values = {"C001": True, "C002": False, "C003": False}

        self.assertTrue(evaluate_rule_set(
            rule_set("C001 OR C002 AND C003"),
            values,
        ))
        self.assertFalse(evaluate_rule_set(
            rule_set("(C001 OR C002) AND C003"),
            values,
        ))

    def test_multiple_rules_use_fixed_any(self):
        values = {"C001": True, "C002": False, "C003": True}
        rules = rule_set("C001 AND C002", "C001 AND C003")

        self.assertTrue(evaluate_rule_set(rules, values))
        self.assertTrue(evaluate_rule_set(
            rule_set("C001 AND C003", "C001 AND C002"),
            values,
        ))
        self.assertFalse(evaluate_rule_set(
            rule_set("C001 AND C002", "C002 AND C003"),
            values,
        ))

    def test_one_rule_represents_all_mandatory_conditions(self):
        self.assertTrue(evaluate_rule_set(
            rule_set("C001 AND C002 AND C003"),
            {"C001": True, "C002": True, "C003": True},
        ))
        with self.assertRaises(ScreeningRuleValidationError):
            evaluate_rule_set(rule_set("ANY(C001)"), {"C001": True})

    def test_duplicate_references_rules_and_redundancy(self):
        values = {"C001": True, "C002": False}

        self.assertTrue(evaluate_rule_set(
            rule_set("C001 AND C001"),
            values,
        ))
        self.assertTrue(evaluate_rule_set(
            rule_set("C001", "C001"),
            values,
        ))
        self.assertTrue(evaluate_rule_set(
            rule_set("C001 OR (C001 AND C002)"),
            values,
        ))

    def test_not_is_rejected(self):
        with self.assertRaises(ScreeningRuleValidationError):
            evaluate_rule_set(rule_set("NOT C001"), {"C001": True})

    def test_token_boundaries_and_unsupported_syntax(self):
        values = {"C001": True, "C002": True, "C003": False}

        self.assertTrue(evaluate_rule_set(
            rule_set("C001 AND C002"),
            values,
        ))
        self.assertTrue(evaluate_rule_set(
            rule_set("C001 AND(C002 OR C003)"),
            values,
        ))
        invalid_expressions = (
            "C001ANDC002",
            "C001OR(C002)",
            "C001(C002)",
            "C01",
            "C000",
            "c001",
            "C001 and C002",
            "C001 XOR C002",
            "C001 && C002",
            "C001 || C002",
            '"C001" AND C002',
            "C001; C002",
            "SLG AND C001",
        )
        for expression in invalid_expressions:
            with self.subTest(expression=expression):
                with self.assertRaises(ScreeningRuleValidationError):
                    evaluate_rule_set(rule_set(expression), values)

    def test_malformed_and_empty_rules(self):
        for expression in ("", " \n\t"):
            with self.subTest(expression=expression):
                with self.assertRaises(ScreeningRuleValidationError):
                    ScreeningRule(expression)

        malformed_expressions = (
            "C001 AND",
            "OR C001",
            "C001 C002",
            "C001 AND OR C002",
            "(C001 OR C002",
            "C001 OR )",
            "()",
            "( )",
            "C001)",
            "(C001) C002",
        )
        values = {"C001": True, "C002": False}
        for expression in malformed_expressions:
            with self.subTest(expression=expression):
                with self.assertRaises(ScreeningRuleValidationError):
                    evaluate_rule_set(rule_set(expression), values)

    def test_empty_rule_set_is_invalid(self):
        with self.assertRaises(ScreeningRuleValidationError):
            ScreeningRuleSet(())

    def test_missing_reference_is_not_false_or_short_circuited(self):
        with self.assertRaises(ScreeningRuleInputError):
            evaluate_rule_set(rule_set("C001 OR C002"), {"C001": True})
        with self.assertRaises(ScreeningRuleInputError):
            evaluate_rule_set(
                rule_set("C001", "C002"),
                {"C001": True},
            )
        with self.assertRaises(ScreeningRuleValidationError):
            evaluate_rule_set(
                rule_set("C001", "C002 OR"),
                {"C001": True, "C002": False},
            )

    def test_complete_mapping_rejects_non_bool_values(self):
        for invalid_value in (1, 0, "true", "false", None, [], {}):
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(ScreeningRuleInputError):
                    evaluate_rule_set(
                        rule_set("C001"),
                        {"C001": True, "C999": invalid_value},
                    )
        with self.assertRaises(ScreeningRuleInputError):
            evaluate_rule_set(
                rule_set("C001"),
                {"C001": True, "C01": False},
            )

    def test_extra_valid_boolean_results_are_ignored(self):
        self.assertFalse(evaluate_rule_set(
            rule_set("C001"),
            {"C001": False, "C999": True},
        ))

    def test_success_returns_exact_bool_only(self):
        self.assertIs(type(evaluate_rule_set(
            rule_set("C001"),
            {"C001": True},
        )), bool)
        self.assertIs(type(evaluate_rule_set(
            rule_set("C001"),
            {"C001": False},
        )), bool)

    def test_evaluation_is_deterministic_and_does_not_mutate_inputs(self):
        rules = rule_set("C001 OR (C002 AND C003)")
        values = {"C001": False, "C002": True, "C003": True}
        original_values = dict(values)

        self.assertTrue(evaluate_rule_set(rules, values))
        self.assertTrue(evaluate_rule_set(rules, values))
        self.assertEqual(values, original_values)
        self.assertEqual(rules.rules[0].expression, "C001 OR (C002 AND C003)")

    def test_public_surface_has_no_deferred_rule_engine_fields(self):
        self.assertEqual(
            tuple(inspect.signature(evaluate_rule_set).parameters),
            ("rule_set", "criterion_results"),
        )
        self.assertEqual(
            set(field.name for field in fields(ScreeningRule)),
            {"expression"},
        )
        self.assertEqual(
            set(field.name for field in fields(ScreeningRuleSet)),
            {"rules"},
        )


if __name__ == "__main__":
    unittest.main()
