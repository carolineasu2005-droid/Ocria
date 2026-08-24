"""Interactive AM7-R15 ScreeningPreset configuration helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Mapping

from ai_provider_config import AIProviderConfigStore
from run_configuration import (
    RunConfigurationError,
    build_all_rule_expression,
    build_any_rule_expression,
    parse_duration_seconds,
    render_run_summary,
    resolve_run_configuration,
    validate_preset_definition,
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
from screening_profile_cli import run_screening_profile_draft_editor


def choose_startup_action() -> str:
    """Return the selected frozen R15 top-level startup action."""

    while True:
        print("\nOcria Am7")
        print("1. Quick Start")
        print("2. Choose ScreeningPreset and Run")
        print("3. ScreeningPreset Management")
        print("4. AI Provider Configuration")
        print("5. Calibration")
        print("6. Advanced")
        print("0. Exit")
        choice = input("Select action: ").strip()
        actions = {
            "1": "quick_start",
            "2": "choose_preset",
            "3": "preset_management",
            "4": "provider_configuration",
            "5": "calibration",
            "6": "advanced",
            "0": "exit",
        }
        if choice in actions:
            return actions[choice]
        print("Invalid action.")


def choose_advanced_action() -> str:
    while True:
        print("\nAdvanced")
        print("1. Existing manual Am7 Run")
        print("2. Advanced ScreeningProfile Management")
        print("0. Return")
        choice = input("Select action: ").strip()
        actions = {
            "1": "manual_run",
            "2": "profile_management",
            "0": "return",
        }
        if choice in actions:
            return actions[choice]
        print("Invalid action.")


def choose_preset(store: ScreeningPresetStore) -> ScreeningPreset | None:
    """List deterministic Preset selectors and return one explicit selection."""

    try:
        presets = store.list_presets()
    except (ScreeningPresetValidationError, ScreeningPresetIOError) as exc:
        print("Cannot list ScreeningPresets: {0}".format(exc))
        return None
    if not presets:
        print("No saved ScreeningPresets. Create one in ScreeningPreset Management.")
        return None
    print("\nSaved ScreeningPresets:")
    for index, preset in enumerate(presets, start=1):
        print("{0}. {1}".format(index, preset.preset_name))
    selection = input("Preset name or number (blank to return): ").strip()
    if not selection:
        return None
    if selection.isdigit():
        index = int(selection)
        if 1 <= index <= len(presets):
            return presets[index - 1]
    try:
        return store.get_preset(selection)
    except (ScreeningPresetValidationError, ScreeningPresetIOError):
        print("ScreeningPreset was not found.")
        return None


def _list_presets(store: ScreeningPresetStore) -> tuple[ScreeningPreset, ...]:
    try:
        presets = store.list_presets()
    except (ScreeningPresetValidationError, ScreeningPresetIOError) as exc:
        print("Cannot list ScreeningPresets: {0}".format(exc))
        return ()
    if not presets:
        print("No saved ScreeningPresets. Create one in ScreeningPreset Management.")
        return ()
    print("\nSaved ScreeningPresets:")
    for index, preset in enumerate(presets, start=1):
        print("{0}. {1}".format(index, preset.preset_name))
    return presets


def _prompt_bool(prompt: str, default: bool) -> bool:
    while True:
        default_text = "Y" if default else "N"
        answer = input("{0} [Y/N, default {1}]: ".format(prompt, default_text)).strip()
        if not answer:
            return default
        if answer.lower() in {"y", "yes"}:
            return True
        if answer.lower() in {"n", "no"}:
            return False
        print("Please enter Y or N.")


def prompt_run_settings(
    preset_name: str,
    defaults: LastUsedRunSettings | None = None,
) -> LastUsedRunSettings:
    """Collect Run-local R15 settings without persisting them."""

    default_action = "favorite" if defaults is None else defaults.last_action_mode
    while True:
        action = input(
            "Action [favorite/forward, default {0}]: ".format(default_action)
        ).strip().lower()
        if not action:
            action = default_action
        if action in {"favorite", "forward"}:
            break
        print("Action must be favorite or forward.")
    default_duration = 0 if defaults is None else defaults.last_duration_seconds
    while True:
        raw_duration = input(
            "Duration seconds (0 = Unlimited, default {0}): ".format(
                default_duration
            )
        )
        if not raw_duration.strip():
            duration_seconds = default_duration
            break
        try:
            duration_seconds = parse_duration_seconds(raw_duration)
        except ValueError as exc:
            print(str(exc))
        else:
            break
    default_no_forward = False if defaults is None else defaults.last_no_forward
    default_batch_filter = (
        True if defaults is None else defaults.last_batch_filter_enabled
    )
    return LastUsedRunSettings(
        last_used_preset_name=preset_name,
        last_action_mode=action,
        last_duration_seconds=duration_seconds,
        last_no_forward=_prompt_bool("Suppress real forwarding", default_no_forward),
        last_batch_filter_enabled=_prompt_bool(
            "Enable batch filter", default_batch_filter
        ),
    )


def apply_invocation_safety_overrides(
    settings: LastUsedRunSettings,
    cli_args: Mapping[str, object],
) -> LastUsedRunSettings:
    """Apply existing invocation safety flags before R15 resolution."""

    if not isinstance(settings, LastUsedRunSettings):
        raise ValueError("settings must be LastUsedRunSettings.")
    return replace(
        settings,
        last_no_forward=True
        if cli_args.get("no_forward")
        else settings.last_no_forward,
        last_batch_filter_enabled=False
        if cli_args.get("no_batch_filter")
        else settings.last_batch_filter_enabled,
    )


def prompt_run_summary(configuration) -> str:
    """Display a pure Summary and return exactly confirm, edit, or cancel."""

    print("\n" + render_run_summary(configuration))
    while True:
        choice = input("Confirm, Edit, or Cancel [C/E/0]: ").strip().lower()
        if choice in {"c", "confirm"}:
            return "confirm"
        if choice in {"e", "edit"}:
            return "edit"
        if choice in {"0", "cancel", "back"}:
            return "cancel"
        print("Please choose Confirm, Edit, or Cancel.")


def _resolve_and_confirm(
    settings: LastUsedRunSettings,
    *,
    preset_store: ScreeningPresetStore,
    profile_store: ScreeningProfileStore,
    provider_store: AIProviderConfigStore,
    on_confirm: Callable[[object], None],
    edit_settings: Callable[[LastUsedRunSettings], LastUsedRunSettings | None],
) -> bool:
    """Resolve, summarize, and hand off only after an explicit confirmation."""

    while True:
        try:
            configuration = resolve_run_configuration(
                settings,
                preset_store=preset_store,
                profile_store=profile_store,
                provider_store=provider_store,
            )
        except RunConfigurationError as exc:
            print("Run configuration is unavailable: {0}".format(exc))
            return False
        summary_action = prompt_run_summary(configuration)
        if summary_action == "cancel":
            return False
        if summary_action == "edit":
            settings = edit_settings(settings)
            if settings is None:
                return False
            continue
        try:
            preset_store.save_last_used(
                LastUsedRunSettings(
                    last_used_preset_name=configuration.selected_preset_name,
                    last_action_mode=configuration.action_mode,
                    last_duration_seconds=configuration.duration_seconds,
                    last_no_forward=configuration.no_forward,
                    last_batch_filter_enabled=configuration.batch_filter_enabled,
                )
            )
        except ScreeningPresetIOError:
            print("Warning: Quick Start settings were not updated.")
        on_confirm(configuration)
        return True


def _edit_run_settings(
    current: LastUsedRunSettings,
    *,
    preset_store: ScreeningPresetStore,
    cli_args: Mapping[str, object],
) -> LastUsedRunSettings | None:
    """Collect a replacement setting value; a new Preset resolves afresh."""

    while True:
        print("\nEdit Run Summary")
        print("1. Edit action settings")
        print("2. Choose a different ScreeningPreset")
        print("0. Cancel")
        choice = input("Select action: ").strip()
        if choice == "0":
            return None
        if choice == "1":
            return apply_invocation_safety_overrides(
                prompt_run_settings(current.last_used_preset_name, current),
                cli_args,
            )
        if choice == "2":
            preset = choose_preset(preset_store)
            if preset is None:
                continue
            return apply_invocation_safety_overrides(
                prompt_run_settings(preset.preset_name),
                cli_args,
            )
        print("Invalid action.")


def quick_start(
    *,
    preset_store: ScreeningPresetStore,
    profile_store: ScreeningProfileStore,
    provider_store: AIProviderConfigStore,
    cli_args: Mapping[str, object],
    on_confirm: Callable[[object], None],
) -> bool:
    try:
        settings = preset_store.load_last_used()
    except (ScreeningPresetValidationError, ScreeningPresetIOError) as exc:
        print("Quick Start is unavailable: {0}".format(exc))
        return False
    if settings is None:
        print("Quick Start is unavailable: no confirmed Run configuration exists.")
        return False
    settings = apply_invocation_safety_overrides(settings, cli_args)
    return _resolve_and_confirm(
        settings,
        preset_store=preset_store,
        profile_store=profile_store,
        provider_store=provider_store,
        on_confirm=on_confirm,
        edit_settings=lambda current: _edit_run_settings(
            current,
            preset_store=preset_store,
            cli_args=cli_args,
        ),
    )


def choose_preset_and_run(
    *,
    preset_store: ScreeningPresetStore,
    profile_store: ScreeningProfileStore,
    provider_store: AIProviderConfigStore,
    cli_args: Mapping[str, object],
    on_confirm: Callable[[object], None],
) -> bool:
    preset = choose_preset(preset_store)
    if preset is None:
        return False
    try:
        defaults = preset_store.load_last_used()
    except (ScreeningPresetValidationError, ScreeningPresetIOError):
        defaults = None
    if defaults is not None and defaults.last_used_preset_name != preset.preset_name:
        defaults = None
    settings = apply_invocation_safety_overrides(
        prompt_run_settings(preset.preset_name, defaults),
        cli_args,
    )
    return _resolve_and_confirm(
        settings,
        preset_store=preset_store,
        profile_store=profile_store,
        provider_store=provider_store,
        on_confirm=on_confirm,
        edit_settings=lambda current: _edit_run_settings(
            current,
            preset_store=preset_store,
            cli_args=cli_args,
        ),
    )


def _choose_profile_version(
    profile_store: ScreeningProfileStore,
) -> ScreeningProfileVersion | None:
    try:
        profile_ids = profile_store.list_profile_ids()
    except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
        print("Cannot list ScreeningProfiles: {0}".format(exc))
        return None
    if not profile_ids:
        print("No saved ScreeningProfiles.")
        return None
    print("\nSaved ScreeningProfiles:")
    for index, profile_id in enumerate(profile_ids, start=1):
        try:
            latest = profile_store.load_latest(profile_id)
        except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
            print("Cannot load ScreeningProfile: {0}".format(exc))
            return None
        print("{0}. Profile v{1}".format(index, latest.profile_version))
    raw_profile = input("Profile number (blank to return): ").strip()
    if not raw_profile.isdigit() or not 1 <= int(raw_profile) <= len(profile_ids):
        return None
    profile_id = profile_ids[int(raw_profile) - 1]
    try:
        versions = profile_store.list_versions(profile_id)
    except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
        print("Cannot list Profile Versions: {0}".format(exc))
        return None
    print("Versions: {0}".format(", ".join("v{0}".format(item) for item in versions)))
    raw_version = input("Exact Profile Version: ").strip()
    if not raw_version.isdigit():
        return None
    try:
        profile = profile_store.load_version(profile_id, int(raw_version))
    except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
        print("Cannot load Profile Version: {0}".format(exc))
        return None
    print("Criteria:")
    for criterion in profile.criteria:
        print("- {0}: {1}".format(criterion.criterion_id, criterion.criterion_text))
    return profile


def _prompt_rule_expressions(profile: ScreeningProfileVersion) -> tuple[str, ...] | None:
    while True:
        choice = input("Rule mode [ALL/ANY/CUSTOM]: ").strip().upper()
        if choice == "ALL":
            return (build_all_rule_expression(profile),)
        if choice == "ANY":
            return (build_any_rule_expression(profile),)
        if choice == "CUSTOM":
            expressions: list[str] = []
            print("Enter formal R06 expressions; blank line finishes.")
            while True:
                expression = input("> ")
                if not expression.strip():
                    return tuple(expressions) if expressions else None
                expressions.append(expression)
        print("Rule mode must be ALL, ANY, or CUSTOM.")


def _print_preset_details(
    preset: ScreeningPreset,
    profile_store: ScreeningProfileStore,
) -> None:
    try:
        profile, _rule_set = validate_preset_definition(preset, profile_store)
    except RunConfigurationError as exc:
        print("Preset details are unavailable: {0}".format(exc))
        return
    print("\nScreeningPreset: {0}".format(preset.preset_name))
    print("Profile ID: {0}".format(profile.screening_profile_id))
    print("Profile Version: v{0}".format(profile.profile_version))
    print("Criteria:")
    for criterion in profile.criteria:
        print("- {0}: {1}".format(criterion.criterion_id, criterion.criterion_text))
    print("Rules:")
    for expression in preset.screening_rule_expressions:
        print("- {0}".format(expression))


def _create_preset(
    preset_store: ScreeningPresetStore,
    profile_store: ScreeningProfileStore,
) -> None:
    preset_name = input("ScreeningPreset name: ")
    profile = _choose_profile_version(profile_store)
    if profile is None:
        create_profile = input("Create a new ScreeningProfile Draft instead? [Y/N]: ").strip().lower()
        if create_profile not in {"y", "yes"}:
            return
        profile = run_screening_profile_draft_editor(profile_store)
        if profile is None:
            return
    expressions = _prompt_rule_expressions(profile)
    if expressions is None:
        print("At least one formal Rule expression is required.")
        return
    try:
        preset = ScreeningPreset(
            preset_name,
            profile.screening_profile_id,
            profile.profile_version,
            expressions,
        )
        _print_preset_details(preset, profile_store)
        validate_preset_definition(preset, profile_store)
    except (ScreeningPresetValidationError, RunConfigurationError) as exc:
        print("Cannot create ScreeningPreset: {0}".format(exc))
        return
    if input("Human Save ScreeningPreset? [Y/N]: ").strip().lower() not in {"y", "yes"}:
        return
    try:
        preset_store.create_preset(preset)
    except (ScreeningPresetValidationError, ScreeningPresetIOError) as exc:
        print("Cannot save ScreeningPreset: {0}".format(exc))
    else:
        print("Saved ScreeningPreset {0}.".format(preset.preset_name))


def _edit_preset(
    preset_store: ScreeningPresetStore,
    profile_store: ScreeningProfileStore,
) -> None:
    current = choose_preset(preset_store)
    if current is None:
        return
    replacement = current
    while True:
        print("\nEdit ScreeningPreset")
        print("1. Rename")
        print("2. Rebind exact Profile Version")
        print("3. Change Rules")
        print("4. Edit Criteria through Draft")
        print("5. Preview")
        print("6. Human Save")
        print("0. Cancel")
        choice = input("Select action: ").strip()
        if choice == "0":
            return
        if choice == "1":
            try:
                replacement = replace(
                    replacement,
                    preset_name=input("New ScreeningPreset name: "),
                )
            except ScreeningPresetValidationError as exc:
                print("Cannot rename ScreeningPreset: {0}".format(exc))
        elif choice == "2":
            profile = _choose_profile_version(profile_store)
            if profile is not None:
                replacement = replace(
                    replacement,
                    screening_profile_id=profile.screening_profile_id,
                    profile_version=profile.profile_version,
                )
        elif choice == "3":
            try:
                profile = profile_store.load_version(
                    replacement.screening_profile_id,
                    replacement.profile_version,
                )
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot load bound Profile: {0}".format(exc))
                continue
            expressions = _prompt_rule_expressions(profile)
            if expressions is not None:
                replacement = replace(
                    replacement,
                    screening_rule_expressions=expressions,
                )
        elif choice == "4":
            try:
                latest = profile_store.load_latest(replacement.screening_profile_id)
            except (ScreeningProfileValidationError, ScreeningProfileIOError) as exc:
                print("Cannot load current Profile: {0}".format(exc))
                continue
            if latest.profile_version != replacement.profile_version:
                print("Explicitly rebind this Preset to latest before criterion editing.")
                continue
            version = run_screening_profile_draft_editor(
                profile_store,
                screening_profile_id=replacement.screening_profile_id,
            )
            if version is not None:
                replacement = replace(
                    replacement,
                    screening_profile_id=version.screening_profile_id,
                    profile_version=version.profile_version,
                )
                expressions = _prompt_rule_expressions(version)
                if expressions is not None:
                    replacement = replace(
                        replacement,
                        screening_rule_expressions=expressions,
                    )
        elif choice == "5":
            _print_preset_details(replacement, profile_store)
        elif choice == "6":
            try:
                validate_preset_definition(replacement, profile_store)
                _print_preset_details(replacement, profile_store)
            except RunConfigurationError as exc:
                print("Cannot save ScreeningPreset: {0}".format(exc))
                continue
            if input("Human Save ScreeningPreset? [Y/N]: ").strip().lower() not in {"y", "yes"}:
                continue
            try:
                preset_store.replace_preset(current.preset_name, replacement)
            except (ScreeningPresetValidationError, ScreeningPresetIOError) as exc:
                print("Cannot save ScreeningPreset: {0}".format(exc))
            else:
                print("Saved ScreeningPreset {0}.".format(replacement.preset_name))
                return
        else:
            print("Invalid action.")


def run_screening_preset_management(
    preset_store: ScreeningPresetStore | None = None,
    profile_store: ScreeningProfileStore | None = None,
) -> None:
    """Run the R15 Preset management menu without entering Runtime."""

    preset_store = preset_store or ScreeningPresetStore()
    profile_store = profile_store or ScreeningProfileStore()
    while True:
        print("\nScreeningPreset Management")
        print("1. List")
        print("2. Create")
        print("3. Edit")
        print("4. Delete")
        print("5. Details")
        print("0. Return")
        choice = input("Select action: ").strip()
        if choice == "0":
            return
        if choice == "1":
            _list_presets(preset_store)
        elif choice == "2":
            _create_preset(preset_store, profile_store)
        elif choice == "3":
            _edit_preset(preset_store, profile_store)
        elif choice == "4":
            preset = choose_preset(preset_store)
            if preset is None:
                continue
            if input("Delete this ScreeningPreset? [Y/N]: ").strip().lower() not in {"y", "yes"}:
                continue
            try:
                preset_store.delete_preset(preset.preset_name)
            except (ScreeningPresetValidationError, ScreeningPresetIOError) as exc:
                print("Cannot delete ScreeningPreset: {0}".format(exc))
            else:
                print("Deleted ScreeningPreset {0}.".format(preset.preset_name))
        elif choice == "5":
            preset = choose_preset(preset_store)
            if preset is not None:
                _print_preset_details(preset, profile_store)
        else:
            print("Invalid action.")
