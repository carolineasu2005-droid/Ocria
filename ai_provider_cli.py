"""Interactive local configuration for the AM7 AI Provider Runtime."""

from __future__ import annotations

from dataclasses import replace
import getpass

from ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigIOError,
    AIProviderConfigLoadResult,
    AIProviderConfigLoadStatus,
    AIProviderConfigStore,
    ConnectionVerificationStatus,
    PROVIDER_ALIYUN_BAILIAN,
    PROVIDER_DEEPSEEK,
)
from llm_provider_runtime import (
    LLMRuntimeError,
    LLMRuntimeErrorCode,
    list_models,
    test_connection,
)


_USABLE_LOAD_STATUSES = {
    AIProviderConfigLoadStatus.INCOMPLETE,
    AIProviderConfigLoadStatus.VALID,
}
_CONNECTION_FIELDS = ("provider", "api_key", "base_url")


def _connection_changed(current: AIProviderConfig, proposed: AIProviderConfig) -> bool:
    return any(
        getattr(current, field_name) != getattr(proposed, field_name)
        for field_name in _CONNECTION_FIELDS
    )


def _stage_config(current: AIProviderConfig, **changes: str) -> AIProviderConfig:
    """Apply local staged edits and invalidate only changed connection tuples."""

    proposed = replace(current, **changes)
    if _connection_changed(current, proposed):
        return replace(
            proposed,
            connection_verification_status=ConnectionVerificationStatus.UNVERIFIED,
            last_verification_time=None,
        )
    return proposed


def _connection_ready(config: AIProviderConfig) -> bool:
    return all(getattr(config, field_name) for field_name in _CONNECTION_FIELDS)


def _safe_load(store: AIProviderConfigStore) -> AIProviderConfigLoadResult | None:
    try:
        return store.load()
    except AIProviderConfigIOError:
        print("Cannot read AI Provider configuration locally.")
        return None


def _load_staged(
    store: AIProviderConfigStore,
) -> tuple[AIProviderConfig, AIProviderConfigLoadStatus, bool] | None:
    result = _safe_load(store)
    if result is None:
        return None
    if result.status in _USABLE_LOAD_STATUSES and result.config is not None:
        return result.config, result.status, False
    if result.status in {
        AIProviderConfigLoadStatus.INVALID,
        AIProviderConfigLoadStatus.UNSUPPORTED_VERSION,
    }:
        print(f"Stored configuration is {result.status.value}; starting with an empty staged configuration.")
    return AIProviderConfig(), result.status, False


def _show_state(
    config: AIProviderConfig,
    load_status: AIProviderConfigLoadStatus,
    dirty: bool,
) -> None:
    print("\nAI Provider Configuration")
    print(f"Provider: {config.provider or 'not configured'}")
    print(config.api_key_display())
    print(f"Base URL: {config.base_url or 'not configured'}")
    print(f"Model: {config.model or 'not configured'}")
    print(f"Connection verification: {config.connection_verification_status.value}")
    print(
        "Last verification time: "
        f"{config.last_verification_time.isoformat() if config.last_verification_time else 'unavailable'}"
    )
    print(f"Configuration state: {load_status.value}")
    print(f"Staged changes: {'yes' if dirty else 'no'}")


def _show_provider_recommendation(provider: str) -> None:
    if provider == PROVIDER_DEEPSEEK:
        print("DeepSeek Base URL recommendation: https://api.deepseek.com")
        return
    print("Qwen Base URL depends on your Alibaba Model Studio region, Workspace, and plan.")
    print("Example (Beijing Workspace): https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    print("Example (Singapore Workspace): https://{WorkspaceId}.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1")
    print("Example (US public compatible endpoint): https://dashscope-us.aliyuncs.com/compatible-mode/v1")


def _display_runtime_error(error: LLMRuntimeError) -> None:
    print(f"Provider operation failed: {error}")
    if error.status_code is not None:
        print(f"HTTP status: {error.status_code}")
    if error.request_id is not None:
        print(f"Request ID: {error.request_id}")


def _save_staged(
    store: AIProviderConfigStore,
    staged: AIProviderConfig,
) -> tuple[AIProviderConfig, AIProviderConfigLoadStatus] | None:
    """Persist the staged snapshot exclusively through the frozen R02 Store API."""

    current_result = _safe_load(store)
    if current_result is None:
        return None
    try:
        if current_result.status in _USABLE_LOAD_STATUSES and current_result.config is not None:
            store.update(
                current_result.config,
                provider=staged.provider,
                api_key=staged.api_key,
                base_url=staged.base_url,
                model=staged.model,
            )
        else:
            store.save(
                AIProviderConfig(
                    provider=staged.provider,
                    api_key=staged.api_key,
                    base_url=staged.base_url,
                    model=staged.model,
                )
            )
    except AIProviderConfigIOError:
        print("Cannot save AI Provider configuration locally.")
        return None

    saved_result = _safe_load(store)
    if (
        saved_result is None
        or saved_result.status not in _USABLE_LOAD_STATUSES
        or saved_result.config is None
    ):
        if saved_result is not None:
            print("Saved configuration could not be reloaded safely.")
        return None
    return saved_result.config, saved_result.status


def _select_provider(staged: AIProviderConfig) -> AIProviderConfig:
    print("1. aliyun-bailian")
    print("2. deepseek")
    choice = input("Select Provider: ").strip()
    providers = {"1": PROVIDER_ALIYUN_BAILIAN, "2": PROVIDER_DEEPSEEK}
    provider = providers.get(choice)
    if provider is None:
        print("Invalid Provider selection.")
        return staged
    proposed = _stage_config(staged, provider=provider)
    _show_provider_recommendation(provider)
    return proposed


def _change_api_key(staged: AIProviderConfig) -> AIProviderConfig:
    api_key = getpass.getpass("API Key (blank keeps current value): ")
    if not api_key:
        print("API Key unchanged.")
        return staged
    return _stage_config(staged, api_key=api_key)


def _change_base_url(staged: AIProviderConfig) -> AIProviderConfig:
    base_url = input("Base URL (blank keeps current value): ")
    if not base_url:
        print("Base URL unchanged.")
        return staged
    try:
        return _stage_config(staged, base_url=base_url)
    except ValueError:
        print("Base URL must be an absolute HTTP(S) URL.")
        return staged


def _list_models(staged: AIProviderConfig) -> tuple[str, ...] | None:
    if not _connection_ready(staged):
        print("Provider, API Key, and Base URL are required before listing models.")
        return None
    print("Listing models requires a network request.")
    try:
        models = list_models(staged)
    except LLMRuntimeError as error:
        _display_runtime_error(error)
        print("Model discovery is unavailable; you can still enter a model identifier manually.")
        return None

    if not models:
        print("No models were returned; you can still enter a model identifier manually.")
        return ()
    print("Latest models:")
    for index, model in enumerate(models, start=1):
        print(f"{index}. {model}")
    return models


def _select_latest_model(
    staged: AIProviderConfig,
    latest_models: tuple[str, ...] | None,
) -> AIProviderConfig:
    if not latest_models:
        print("No recent model list. List models first or enter a model manually.")
        return staged
    choice = input("Select model number: ").strip()
    try:
        index = int(choice) - 1
        if index < 0:
            raise ValueError
        model = latest_models[index]
    except (IndexError, ValueError):
        print("Invalid model selection.")
        return staged
    return _stage_config(staged, model=model)


def _enter_model_manually(staged: AIProviderConfig) -> AIProviderConfig:
    model = input("Model identifier (blank keeps current value): ")
    if not model:
        print("Model unchanged.")
        return staged
    return _stage_config(staged, model=model)


def _display_test_writeback(applied: bool | None) -> None:
    if applied is True:
        print("Verification result was saved.")
    elif applied is False:
        print("Configuration changed while checking; the verification result was not applied.")


def _test_connection(
    store: AIProviderConfigStore,
    staged: AIProviderConfig,
    load_status: AIProviderConfigLoadStatus,
) -> tuple[AIProviderConfig, AIProviderConfigLoadStatus, bool]:
    if not _connection_ready(staged):
        print("Provider, API Key, and Base URL are required before testing the connection.")
        return staged, load_status, False

    print("This will make a network request without inference and save the current connection fields first.")
    confirmation = input("Save and test connection? [y/N]: ").strip().lower()
    if confirmation not in {"y", "yes"}:
        print("Connection test cancelled; nothing was saved and no network request was made.")
        return staged, load_status, False

    saved = _save_staged(store, staged)
    if saved is None:
        return staged, load_status, True
    snapshot, saved_status = saved
    try:
        result = test_connection(snapshot, store)
        print("Provider connection check succeeded.")
        _display_test_writeback(result.verification_writeback_applied)
    except LLMRuntimeError as error:
        if error.code is LLMRuntimeErrorCode.CAPABILITY_UNAVAILABLE:
            print("No non-inference verification capability is available for this Provider.")
            print("Verification was not changed to failed, no inference fallback was used, and you can still enter a model manually.")
        elif (
            error.code is LLMRuntimeErrorCode.UNKNOWN
            and error.verification_writeback_error is not None
            and str(error)
            == "Provider check succeeded, but verification write-back failed locally."
        ):
            print("Provider check succeeded, but verification write-back failed locally.")
        else:
            _display_runtime_error(error)
            _display_test_writeback(error.verification_writeback_applied)
            if error.verification_writeback_error is not None:
                print("The Provider check and local verification write-back have different outcomes.")
    finally:
        reloaded = _load_staged(store)

    if reloaded is None:
        return snapshot, saved_status, False
    reloaded_config, reloaded_status, _ = reloaded
    _show_state(reloaded_config, reloaded_status, False)
    return reloaded_config, reloaded_status, False


def _refresh(
    store: AIProviderConfigStore,
    staged: AIProviderConfig,
    load_status: AIProviderConfigLoadStatus,
    dirty: bool,
) -> tuple[AIProviderConfig, AIProviderConfigLoadStatus, bool, bool]:
    if dirty:
        confirmation = input("Discard unsaved staged changes and refresh? [y/N]: ").strip().lower()
        if confirmation not in {"y", "yes"}:
            print("Refresh cancelled; staged changes were kept.")
            return staged, load_status, dirty, False
    reloaded = _load_staged(store)
    if reloaded is None:
        return staged, load_status, dirty, False
    reloaded_config, reloaded_status, _ = reloaded
    _show_state(reloaded_config, reloaded_status, False)
    return reloaded_config, reloaded_status, False, True


def run_ai_provider_configuration(store: AIProviderConfigStore | None = None) -> None:
    """Run the independent staged AI Provider Configuration CLI until Return."""

    if store is None:
        store = AIProviderConfigStore()
    loaded = _load_staged(store)
    if loaded is None:
        return
    staged, load_status, dirty = loaded
    latest_models: tuple[str, ...] | None = None

    while True:
        print("\n1. Show current state")
        print("2. Select Provider")
        print("3. Change API Key")
        print("4. Change Base URL")
        print("5. List Models")
        print("6. Select Model from latest list")
        print("7. Enter Model manually")
        print("8. Save")
        print("9. Test Connection")
        print("10. Refresh Status")
        print("0. Return to startup menu")
        choice = input("Select action: ").strip()

        if choice == "0":
            return
        if choice == "1":
            _show_state(staged, load_status, dirty)
        elif choice == "2":
            previous = staged
            staged = _select_provider(staged)
            if _connection_changed(previous, staged):
                latest_models = None
                dirty = True
        elif choice == "3":
            previous = staged
            staged = _change_api_key(staged)
            if _connection_changed(previous, staged):
                latest_models = None
                dirty = True
        elif choice == "4":
            previous = staged
            staged = _change_base_url(staged)
            if _connection_changed(previous, staged):
                latest_models = None
                dirty = True
        elif choice == "5":
            listed_models = _list_models(staged)
            if listed_models is not None:
                latest_models = listed_models
        elif choice == "6":
            previous = staged
            staged = _select_latest_model(staged, latest_models)
            if staged != previous:
                dirty = True
        elif choice == "7":
            previous = staged
            staged = _enter_model_manually(staged)
            if staged != previous:
                dirty = True
        elif choice == "8":
            saved = _save_staged(store, staged)
            if saved is not None:
                staged, load_status = saved
                dirty = False
                print("Configuration saved.")
                _show_state(staged, load_status, dirty)
        elif choice == "9":
            staged, load_status, dirty = _test_connection(store, staged, load_status)
        elif choice == "10":
            staged, load_status, dirty, refreshed = _refresh(
                store,
                staged,
                load_status,
                dirty,
            )
            if refreshed:
                latest_models = None
        else:
            print("Invalid action.")
