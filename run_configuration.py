"""AM7-R15 pure Run-configuration resolution and summary rendering."""

from __future__ import annotations

from dataclasses import dataclass

from ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigIOError,
    AIProviderConfigLoadStatus,
    AIProviderConfigStore,
)
from screening_preset import (
    LastUsedRunSettings,
    ScreeningPreset,
    ScreeningPresetIOError,
    ScreeningPresetStore,
    ScreeningPresetValidationError,
)
from screening_profile import (
    ScreeningProfileIOError,
    ScreeningProfileStore,
    ScreeningProfileValidationError,
    ScreeningProfileVersion,
)
from screening_rule_engine import (
    ScreeningRule,
    ScreeningRuleInputError,
    ScreeningRuleSet,
    ScreeningRuleValidationError,
    evaluate_rule_set,
)


class RunConfigurationError(ValueError):
    """An expected R15 setup failure suitable for concise startup display."""


def _canonical_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("selected_preset_name must be a non-blank string.")
    return value.strip()


def _validate_action_mode(value: object) -> str:
    if value not in {"favorite", "forward"}:
        raise ValueError("action_mode must be favorite or forward.")
    return value


def _validate_duration(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("duration_seconds must be a non-negative non-bool integer.")
    return value


def _validate_bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field_name} must be a bool.")
    return value


@dataclass(frozen=True)
class ResolvedRunConfiguration:
    selected_preset_name: str
    exact_screening_profile_version: ScreeningProfileVersion
    run_bound_screening_rule_set: ScreeningRuleSet
    current_complete_ai_provider_config: AIProviderConfig
    action_mode: str
    duration_seconds: int
    no_forward: bool
    batch_filter_enabled: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selected_preset_name",
            _canonical_name(self.selected_preset_name),
        )
        if type(self.exact_screening_profile_version) is not ScreeningProfileVersion:
            raise ValueError(
                "exact_screening_profile_version must be a ScreeningProfileVersion."
            )
        if type(self.run_bound_screening_rule_set) is not ScreeningRuleSet:
            raise ValueError(
                "run_bound_screening_rule_set must be a ScreeningRuleSet."
            )
        if type(self.current_complete_ai_provider_config) is not AIProviderConfig:
            raise ValueError(
                "current_complete_ai_provider_config must be an AIProviderConfig."
            )
        _validate_action_mode(self.action_mode)
        _validate_duration(self.duration_seconds)
        _validate_bool(self.no_forward, "no_forward")
        _validate_bool(self.batch_filter_enabled, "batch_filter_enabled")


def parse_duration_seconds(value: str) -> int:
    """Parse the existing unlimited-or-positive-seconds interactive input."""

    if not isinstance(value, str):
        raise ValueError("duration must be text.")
    normalized = value.strip()
    if not normalized:
        return 0
    if not normalized.isascii() or not normalized.isdigit():
        raise ValueError("duration must be a non-negative integer.")
    duration = int(normalized)
    return _validate_duration(duration)


def build_all_rule_expression(profile: ScreeningProfileVersion) -> str:
    if type(profile) is not ScreeningProfileVersion:
        raise ValueError("profile must be a ScreeningProfileVersion.")
    return " AND ".join(criterion.criterion_id for criterion in profile.criteria)


def build_any_rule_expression(profile: ScreeningProfileVersion) -> str:
    if type(profile) is not ScreeningProfileVersion:
        raise ValueError("profile must be a ScreeningProfileVersion.")
    return " OR ".join(criterion.criterion_id for criterion in profile.criteria)


def build_screening_rule_set(expressions: tuple[str, ...]) -> ScreeningRuleSet:
    if not isinstance(expressions, tuple):
        raise ScreeningRuleValidationError("rule expressions must be a tuple")
    return ScreeningRuleSet(tuple(ScreeningRule(expression) for expression in expressions))


def validate_preset_definition(
    preset: ScreeningPreset,
    profile_store: ScreeningProfileStore,
) -> tuple[ScreeningProfileVersion, ScreeningRuleSet]:
    """Resolve one Preset's exact Profile and validate its R06 rules."""

    if not isinstance(preset, ScreeningPreset):
        raise RunConfigurationError("Preset is invalid.")
    if not isinstance(profile_store, ScreeningProfileStore):
        raise RunConfigurationError("ScreeningProfile store is invalid.")
    try:
        profile = profile_store.load_version(
            preset.screening_profile_id,
            preset.profile_version,
        )
        rule_set = build_screening_rule_set(preset.screening_rule_expressions)
        criterion_results = {
            criterion.criterion_id: False for criterion in profile.criteria
        }
        evaluate_rule_set(rule_set, criterion_results)
    except (
        ScreeningProfileValidationError,
        ScreeningProfileIOError,
        ScreeningRuleValidationError,
        ScreeningRuleInputError,
        ValueError,
    ) as exc:
        raise RunConfigurationError(f"Preset definition is invalid: {exc}") from exc
    return profile, rule_set


def resolve_run_configuration(
    settings: LastUsedRunSettings,
    *,
    preset_store: ScreeningPresetStore,
    profile_store: ScreeningProfileStore,
    provider_store: AIProviderConfigStore,
) -> ResolvedRunConfiguration:
    """Fail closed while resolving an R15 Pre-Run configuration once."""

    if not isinstance(settings, LastUsedRunSettings):
        raise RunConfigurationError("Run settings are invalid.")
    if not isinstance(preset_store, ScreeningPresetStore):
        raise RunConfigurationError("ScreeningPreset store is invalid.")
    if not isinstance(provider_store, AIProviderConfigStore):
        raise RunConfigurationError("AI Provider store is invalid.")
    try:
        preset = preset_store.get_preset(settings.last_used_preset_name)
        profile, rule_set = validate_preset_definition(preset, profile_store)
    except (
        ScreeningPresetValidationError,
        ScreeningPresetIOError,
        RunConfigurationError,
    ) as exc:
        raise RunConfigurationError(f"Run configuration is unavailable: {exc}") from exc

    try:
        provider_result = provider_store.load()
    except AIProviderConfigIOError as exc:
        raise RunConfigurationError(
            "AI Provider configuration cannot be read."
        ) from exc
    if (
        provider_result.status is not AIProviderConfigLoadStatus.VALID
        or provider_result.config is None
    ):
        detail = provider_result.error or provider_result.status.value
        raise RunConfigurationError(
            f"AI Provider configuration is not valid: {detail}."
        )

    try:
        return ResolvedRunConfiguration(
            selected_preset_name=preset.preset_name,
            exact_screening_profile_version=profile,
            run_bound_screening_rule_set=rule_set,
            current_complete_ai_provider_config=provider_result.config,
            action_mode=settings.last_action_mode,
            duration_seconds=settings.last_duration_seconds,
            no_forward=settings.last_no_forward,
            batch_filter_enabled=settings.last_batch_filter_enabled,
        )
    except ValueError as exc:
        raise RunConfigurationError(f"Run settings are invalid: {exc}") from exc


def _rule_display(configuration: ResolvedRunConfiguration) -> str:
    expressions = tuple(
        rule.expression for rule in configuration.run_bound_screening_rule_set.rules
    )
    profile = configuration.exact_screening_profile_version
    all_expression = build_all_rule_expression(profile)
    any_expression = build_any_rule_expression(profile)
    if len(expressions) == 1 and expressions[0] == all_expression == any_expression:
        return "SINGLE (ALL / ANY equivalent)"
    if len(expressions) == 1 and expressions[0] == all_expression:
        return "ALL"
    if len(expressions) == 1 and expressions[0] == any_expression:
        return "ANY"
    if len(expressions) > 1:
        return "CUSTOM (multiple expressions use fixed ANY)"
    return "CUSTOM"


def render_run_summary(configuration: ResolvedRunConfiguration) -> str:
    """Render an R15 Summary without state, storage, or Calibration access."""

    if not isinstance(configuration, ResolvedRunConfiguration):
        raise ValueError("configuration must be a ResolvedRunConfiguration.")
    profile = configuration.exact_screening_profile_version
    lines = [
        "Run Summary",
        f"Preset: {configuration.selected_preset_name}",
        f"Profile Version: v{profile.profile_version}",
        "Criteria:",
    ]
    lines.extend(
        f"- {criterion.criterion_id}: {criterion.criterion_text}"
        for criterion in profile.criteria
    )
    lines.append(f"Rule: {_rule_display(configuration)}")
    lines.extend(
        f"- {rule.expression}"
        for rule in configuration.run_bound_screening_rule_set.rules
    )
    provider = configuration.current_complete_ai_provider_config
    lines.extend(
        (
            f"Provider: {provider.provider}",
            f"Model: {provider.model}",
            f"Action: {configuration.action_mode.upper()}",
            "no_forward: enabled"
            if configuration.no_forward
            else "no_forward: disabled",
            "Forward side effect: suppressed"
            if configuration.action_mode == "forward" and configuration.no_forward
            else "Forward side effect: authorized"
            if configuration.action_mode == "forward"
            else "Forward side effect: not selected",
            "Batch filter: enabled"
            if configuration.batch_filter_enabled
            else "Batch filter: disabled",
            "Duration: Unlimited"
            if configuration.duration_seconds == 0
            else f"Duration: {configuration.duration_seconds} seconds",
            "Confirmation continues into the existing Calibration flow.",
        )
    )
    return "\n".join(lines)
