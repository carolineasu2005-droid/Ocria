"""Pure Boolean combination for frozen ScreeningProfile Criterion IDs."""

from collections.abc import Mapping
from dataclasses import dataclass
import re


_CRITERION_ID_PATTERN = re.compile(r"C([0-9]{3,})\Z")


class ScreeningRuleValidationError(ValueError):
    """Raised when a Rule or RuleSet is malformed."""


class ScreeningRuleInputError(ValueError):
    """Raised when supplied Criterion Boolean results are invalid."""


@dataclass(frozen=True)
class ScreeningRule:
    expression: str

    def __post_init__(self) -> None:
        if not isinstance(self.expression, str) or not self.expression.strip():
            raise ScreeningRuleValidationError(
                "rule expression must be a non-empty string"
            )


@dataclass(frozen=True)
class ScreeningRuleSet:
    rules: tuple[ScreeningRule, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.rules, tuple) or not self.rules:
            raise ScreeningRuleValidationError(
                "rule set must contain one or more rules"
            )
        if not all(isinstance(rule, ScreeningRule) for rule in self.rules):
            raise ScreeningRuleValidationError(
                "rule set entries must be ScreeningRule values"
            )


def _is_valid_criterion_id(value: object) -> bool:
    if not isinstance(value, str):
        return False
    match = _CRITERION_ID_PATTERN.fullmatch(value)
    return match is not None and int(match.group(1)) > 0


def _is_boundary_after(source: str, index: int) -> bool:
    return (
        index >= len(source)
        or source[index].isspace()
        or source[index] in "()"
    )


def _is_boundary_before(source: str, index: int) -> bool:
    return (
        index == 0
        or source[index - 1].isspace()
        or source[index - 1] in "()"
    )


def _tokenize(expression: str) -> tuple[str, ...]:
    tokens: list[str] = []
    index = 0

    while index < len(expression):
        character = expression[index]
        if character.isspace():
            index += 1
            continue
        if character in "()":
            tokens.append(character)
            index += 1
            continue
        if character == "C":
            start = index
            index += 1
            while (
                index < len(expression)
                and "0" <= expression[index] <= "9"
            ):
                index += 1
            criterion_id = expression[start:index]
            if (
                not _is_valid_criterion_id(criterion_id)
                or not _is_boundary_after(expression, index)
            ):
                raise ScreeningRuleValidationError("invalid Criterion ID token")
            tokens.append(criterion_id)
            continue
        if character in "AO":
            operator = (
                "AND"
                if expression.startswith("AND", index)
                else "OR"
                if expression.startswith("OR", index)
                else None
            )
            if operator is None:
                raise ScreeningRuleValidationError("unsupported token")
            end = index + len(operator)
            if (
                not _is_boundary_before(expression, index)
                or not _is_boundary_after(expression, end)
            ):
                raise ScreeningRuleValidationError("invalid operator token boundary")
            tokens.append(operator)
            index = end
            continue
        raise ScreeningRuleValidationError("unsupported token")

    if not tokens:
        raise ScreeningRuleValidationError("rule expression is empty")
    return tuple(tokens)


class _RuleParser:
    def __init__(self, tokens: tuple[str, ...]) -> None:
        self._tokens = tokens
        self._index = 0
        self._referenced_ids: set[str] = set()

    def parse(self) -> tuple[tuple[str, ...], frozenset[str]]:
        postfix = self._parse_or_expression()
        if self._index != len(self._tokens):
            raise ScreeningRuleValidationError("malformed rule expression")
        return postfix, frozenset(self._referenced_ids)

    def _peek(self) -> str | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]

    def _parse_or_expression(self) -> tuple[str, ...]:
        postfix = self._parse_and_expression()
        while self._peek() == "OR":
            self._index += 1
            postfix = (
                postfix
                + self._parse_and_expression()
                + ("OR",)
            )
        return postfix

    def _parse_and_expression(self) -> tuple[str, ...]:
        postfix = self._parse_primary()
        while self._peek() == "AND":
            self._index += 1
            postfix = (
                postfix
                + self._parse_primary()
                + ("AND",)
            )
        return postfix

    def _parse_primary(self) -> tuple[str, ...]:
        token = self._peek()
        if token is None:
            raise ScreeningRuleValidationError("missing operand")
        if _is_valid_criterion_id(token):
            self._index += 1
            self._referenced_ids.add(token)
            return (token,)
        if token != "(":
            raise ScreeningRuleValidationError("expected Criterion ID or group")

        self._index += 1
        postfix = self._parse_or_expression()
        if self._peek() != ")":
            raise ScreeningRuleValidationError("missing closing parenthesis")
        self._index += 1
        return postfix


def _parse_rule(rule: ScreeningRule) -> tuple[tuple[str, ...], frozenset[str]]:
    return _RuleParser(_tokenize(rule.expression)).parse()


def _validate_rule_set(rule_set: ScreeningRuleSet) -> None:
    if not isinstance(rule_set, ScreeningRuleSet):
        raise ScreeningRuleValidationError("rule_set must be a ScreeningRuleSet")
    if not isinstance(rule_set.rules, tuple) or not rule_set.rules:
        raise ScreeningRuleValidationError(
            "rule set must contain one or more rules"
        )
    for rule in rule_set.rules:
        if not isinstance(rule, ScreeningRule):
            raise ScreeningRuleValidationError(
                "rule set entries must be ScreeningRule values"
            )
        if not isinstance(rule.expression, str) or not rule.expression.strip():
            raise ScreeningRuleValidationError(
                "rule expression must be a non-empty string"
            )


def _validated_result_snapshot(
    criterion_results: Mapping[str, bool],
) -> dict[str, bool]:
    if not isinstance(criterion_results, Mapping):
        raise ScreeningRuleInputError("criterion_results must be a Mapping")

    snapshot = tuple(criterion_results.items())
    validated_results: dict[str, bool] = {}
    for criterion_id, result in snapshot:
        if not _is_valid_criterion_id(criterion_id):
            raise ScreeningRuleInputError("invalid Criterion ID input key")
        if type(result) is not bool:
            raise ScreeningRuleInputError("Criterion result must be bool")
        validated_results[criterion_id] = result
    return validated_results


def _evaluate_postfix(
    postfix_tokens: tuple[str, ...],
    criterion_results: Mapping[str, bool],
) -> bool:
    values: list[bool] = []
    for token in postfix_tokens:
        if token == "AND":
            right = values.pop()
            left = values.pop()
            values.append(left and right)
        elif token == "OR":
            right = values.pop()
            left = values.pop()
            values.append(left or right)
        else:
            values.append(criterion_results[token])
    if len(values) != 1 or type(values[0]) is not bool:
        raise RuntimeError("internal postfix evaluation invariant failed")
    return values[0]


def evaluate_rule_set(
    rule_set: ScreeningRuleSet,
    criterion_results: Mapping[str, bool],
) -> bool:
    """Validate and deterministically evaluate a RuleSet with fixed ANY."""

    _validate_rule_set(rule_set)
    parsed_rules = tuple(_parse_rule(rule) for rule in rule_set.rules)
    validated_results = _validated_result_snapshot(criterion_results)

    referenced_ids: set[str] = set()
    for _postfix_tokens, rule_references in parsed_rules:
        referenced_ids.update(rule_references)
    if referenced_ids.difference(validated_results):
        raise ScreeningRuleInputError("missing Criterion Boolean result")

    return any(
        _evaluate_postfix(postfix_tokens, validated_results)
        for postfix_tokens, _rule_references in parsed_rules
    )
