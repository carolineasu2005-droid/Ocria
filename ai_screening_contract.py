import json

from screening_profile import Criterion


class AIScreeningContractError(ValueError):
    """Raw AI screening response violates the Frozen R10 contract."""


def _object_without_duplicate_members(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AIScreeningContractError(
                "AI screening response contains a duplicate JSON member"
            )
        result[key] = value
    return result


def _reject_non_json_constant(constant: str) -> object:
    raise AIScreeningContractError(
        "AI screening response contains a non-JSON constant"
    )


def validate_ai_screening_response(
    raw_response: str,
    criteria: tuple[Criterion, ...],
) -> dict[str, bool]:
    if not isinstance(raw_response, str):
        raise TypeError("raw_response must be a string")
    if (
        not isinstance(criteria, tuple)
        or not criteria
        or not all(isinstance(criterion, Criterion) for criterion in criteria)
    ):
        raise TypeError(
            "criteria must be a non-empty tuple of Criterion objects"
        )

    try:
        parsed = json.loads(
            raw_response,
            object_pairs_hook=_object_without_duplicate_members,
            parse_constant=_reject_non_json_constant,
        )
    except AIScreeningContractError:
        raise
    except json.JSONDecodeError as error:
        raise AIScreeningContractError(
            "AI screening response is not valid JSON"
        ) from error

    if type(parsed) is not dict:
        raise AIScreeningContractError(
            "AI screening response must be a JSON object"
        )
    if set(parsed) != {"criteria_results"}:
        raise AIScreeningContractError(
            "AI screening response has an invalid top-level schema"
        )

    raw_results = parsed["criteria_results"]
    if type(raw_results) is not list:
        raise AIScreeningContractError(
            "AI screening response criteria_results must be a JSON array"
        )

    expected_ids = tuple(criterion.criterion_id for criterion in criteria)
    returned_results: dict[str, bool] = {}
    for raw_result in raw_results:
        if type(raw_result) is not dict:
            raise AIScreeningContractError(
                "AI screening response result items must be JSON objects"
            )
        if set(raw_result) != {"criterion_id", "passed"}:
            raise AIScreeningContractError(
                "AI screening response result items have an invalid schema"
            )

        criterion_id = raw_result["criterion_id"]
        passed = raw_result["passed"]
        if type(criterion_id) is not str:
            raise AIScreeningContractError(
                "AI screening response criterion_id must be a string"
            )
        if type(passed) is not bool:
            raise AIScreeningContractError(
                "AI screening response passed must be a Boolean"
            )
        if criterion_id in returned_results:
            raise AIScreeningContractError(
                "AI screening response contains a duplicate Criterion ID"
            )
        returned_results[criterion_id] = passed

    if set(returned_results) != set(expected_ids):
        raise AIScreeningContractError(
            "AI screening response Criterion IDs are incomplete or unknown"
        )

    return {
        criterion_id: returned_results[criterion_id]
        for criterion_id in expected_ids
    }
