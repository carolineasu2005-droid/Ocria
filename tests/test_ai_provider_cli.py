"""Offline staged-CLI tests for AM7-R03 Change 3."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigLoadStatus,
    AIProviderConfigStore,
    ConnectionVerificationStatus,
    PROVIDER_ALIYUN_BAILIAN,
    PROVIDER_DEEPSEEK,
)
import ai_provider_cli as cli
from llm_provider_runtime import (
    LLMConnectionTestResult,
    LLMOperation,
    LLMRuntimeError,
    LLMRuntimeErrorCode,
)


_UNSET = object()
_VERIFIED_AT = datetime(2026, 8, 15, 14, 30, tzinfo=timezone.utc)


def make_config(
    provider: str = PROVIDER_DEEPSEEK,
    *,
    api_key: str = "stored-api-key",
    base_url: str = "https://provider.example/v1",
    model: str = "stored-model",
    status: ConnectionVerificationStatus = ConnectionVerificationStatus.UNVERIFIED,
    verified_at: datetime | None = None,
) -> AIProviderConfig:
    return AIProviderConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
        connection_verification_status=status,
        last_verification_time=verified_at,
    )


class AIProviderCliTests(unittest.TestCase):
    def _store_with_config(
        self,
        path: Path,
        config: AIProviderConfig | None = None,
    ) -> AIProviderConfigStore:
        store = AIProviderConfigStore(path)
        if config is not None:
            store.save(config)
        return store

    def _run_cli(
        self,
        store: AIProviderConfigStore,
        inputs: list[str],
        *,
        passwords: list[str] | tuple[str, ...] = (),
        listed_models: object = _UNSET,
        list_error: Exception | object = _UNSET,
        test_result: object = _UNSET,
        test_error: Exception | object = _UNSET,
    ) -> tuple[str, Mock, Mock, Mock]:
        list_models = Mock()
        test_connection = Mock()
        if listed_models is not _UNSET:
            list_models.return_value = listed_models
        if list_error is not _UNSET:
            list_models.side_effect = list_error
        if test_result is not _UNSET:
            test_connection.return_value = test_result
        if test_error is not _UNSET:
            test_connection.side_effect = test_error
        getpass_mock = Mock(side_effect=passwords)
        output = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs),
            patch.object(cli.getpass, "getpass", getpass_mock),
            patch.object(cli, "list_models", list_models),
            patch.object(cli, "test_connection", test_connection),
            redirect_stdout(output),
        ):
            cli.run_ai_provider_configuration(store)
        return output.getvalue(), list_models, test_connection, getpass_mock

    def test_show_current_state_displays_only_safe_key_state(self) -> None:
        secret = "synthetic-cli-secret-key"
        config = make_config(api_key=secret, model="")
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, _, _ = self._run_cli(store, ["1", "0"])

        self.assertIn("Provider: deepseek", output)
        self.assertIn("API Key: configured", output)
        self.assertIn("Base URL: https://provider.example/v1", output)
        self.assertIn("Model: not configured", output)
        self.assertIn("Connection verification: unverified", output)
        self.assertIn("Configuration state: incomplete", output)
        self.assertNotIn(secret, output)

    def test_not_configured_state_displays_not_configured_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json")
            output, _, _, _ = self._run_cli(store, ["1", "0"])

        self.assertIn("API Key: not configured", output)
        self.assertIn("Configuration state: not_configured", output)

    def test_public_entry_constructs_default_store_when_none_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json")
            output = io.StringIO()
            with (
                patch.object(cli, "AIProviderConfigStore", return_value=store) as store_type,
                patch("builtins.input", side_effect=["0"]),
                redirect_stdout(output),
            ):
                cli.run_ai_provider_configuration()

        store_type.assert_called_once_with()

    def test_invalid_persisted_config_stays_untouched_until_explicit_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_provider.json"
            original = "{not valid JSON"
            path.write_text(original, encoding="utf-8")
            store = AIProviderConfigStore(path)
            output, _, _, _ = self._run_cli(store, ["0"])

            self.assertEqual(path.read_text(encoding="utf-8"), original)

        self.assertIn("Stored configuration is invalid", output)

    def test_change_api_key_uses_getpass_and_blank_input_preserves_value(self) -> None:
        secret = "existing-synthetic-key"
        config = make_config(api_key=secret, model="")
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, _, getpass_mock = self._run_cli(
                store,
                ["3", "8", "0"],
                passwords=[""],
            )
            persisted = store.load().config

        getpass_mock.assert_called_once_with("API Key (blank keeps current value): ")
        self.assertEqual(persisted.api_key, secret)
        self.assertNotIn(secret, output)
        self.assertIn("API Key unchanged.", output)

    def test_provider_selection_preserves_base_url_and_invalidates_verification(self) -> None:
        config = make_config(
            provider=PROVIDER_ALIYUN_BAILIAN,
            base_url="https://custom.example/compatible-mode/v1",
            status=ConnectionVerificationStatus.VERIFIED,
            verified_at=_VERIFIED_AT,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, _, _ = self._run_cli(store, ["2", "2", "8", "0"])
            persisted = store.load().config

        self.assertEqual(persisted.provider, PROVIDER_DEEPSEEK)
        self.assertEqual(persisted.base_url, "https://custom.example/compatible-mode/v1")
        self.assertEqual(persisted.connection_verification_status, ConnectionVerificationStatus.UNVERIFIED)
        self.assertIsNone(persisted.last_verification_time)
        self.assertIn("https://api.deepseek.com", output)

    def test_qwen_recommendation_does_not_override_existing_base_url(self) -> None:
        config = make_config(base_url="https://kept.example/v1")
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, _, _ = self._run_cli(store, ["2", "1", "1", "0"])

        self.assertIn("region, Workspace, and plan", output)
        self.assertIn("https://kept.example/v1", output)

    def test_base_url_change_invalidates_verification_after_save(self) -> None:
        config = make_config(
            status=ConnectionVerificationStatus.VERIFIED,
            verified_at=_VERIFIED_AT,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            _, _, _, _ = self._run_cli(
                store,
                ["4", "https://new-provider.example/v1", "8", "0"],
            )
            persisted = store.load().config

        self.assertEqual(persisted.base_url, "https://new-provider.example/v1")
        self.assertEqual(persisted.connection_verification_status, ConnectionVerificationStatus.UNVERIFIED)
        self.assertIsNone(persisted.last_verification_time)

    def test_list_models_success_populates_latest_list_for_selection(self) -> None:
        config = make_config()
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, list_models, test_connection, _ = self._run_cli(
                store,
                ["5", "6", "2", "8", "0"],
                listed_models=("first-model", "second-model"),
            )
            persisted = store.load().config

        list_models.assert_called_once_with(config)
        test_connection.assert_not_called()
        self.assertEqual(persisted.model, "second-model")
        self.assertIn("1. first-model", output)
        self.assertIn("2. second-model", output)

    def test_connection_field_change_clears_latest_models(self) -> None:
        config = make_config()
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, list_models, test_connection, _ = self._run_cli(
                store,
                ["5", "4", "https://changed-provider.example/v1", "6", "0"],
                listed_models=("available-model",),
            )

        list_models.assert_called_once_with(config)
        test_connection.assert_not_called()
        self.assertIn("No recent model list", output)

    def test_empty_list_keeps_manual_model_entry_available(self) -> None:
        config = make_config(model="old-model")
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, list_models, test_connection, _ = self._run_cli(
                store,
                ["5", "7", "manual-model", "8", "0"],
                listed_models=(),
            )
            persisted = store.load().config

        list_models.assert_called_once_with(config)
        test_connection.assert_not_called()
        self.assertEqual(persisted.model, "manual-model")
        self.assertIn("No models were returned", output)

    def test_list_failure_keeps_existing_model_and_allows_later_save(self) -> None:
        config = make_config(model="kept-model")
        error = LLMRuntimeError(
            code=LLMRuntimeErrorCode.NETWORK,
            provider=PROVIDER_DEEPSEEK,
            operation=LLMOperation.LIST_MODELS,
            message="Provider network request failed.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, list_models, test_connection, _ = self._run_cli(
                store,
                ["5", "8", "0"],
                list_error=error,
            )
            persisted = store.load().config

        list_models.assert_called_once_with(config)
        test_connection.assert_not_called()
        self.assertEqual(persisted.model, "kept-model")
        self.assertIn("Model discovery is unavailable", output)

    def test_select_latest_model_without_successful_list_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", make_config())
            output, list_models, _, _ = self._run_cli(store, ["6", "0"])

        list_models.assert_not_called()
        self.assertIn("No recent model list", output)

    def test_manual_blank_model_preserves_current_value(self) -> None:
        config = make_config(model="kept-model")
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, _, _ = self._run_cli(store, ["7", "", "8", "0"])
            persisted = store.load().config

        self.assertEqual(persisted.model, "kept-model")
        self.assertIn("Model unchanged.", output)

    def test_save_allows_connection_complete_but_model_incomplete_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json")
            _, _, _, getpass_mock = self._run_cli(
                store,
                ["2", "2", "3", "4", "https://api.deepseek.com", "8", "0"],
                passwords=["new-api-key"],
            )
            result = store.load()

        getpass_mock.assert_called_once()
        self.assertEqual(result.status, AIProviderConfigLoadStatus.INCOMPLETE)
        self.assertEqual(result.config.provider, PROVIDER_DEEPSEEK)
        self.assertEqual(result.config.base_url, "https://api.deepseek.com")
        self.assertEqual(result.config.model, "")

    def test_model_only_save_preserves_existing_verification(self) -> None:
        config = make_config(
            status=ConnectionVerificationStatus.VERIFIED,
            verified_at=_VERIFIED_AT,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            _, _, _, _ = self._run_cli(store, ["7", "new-model", "8", "0"])
            persisted = store.load().config

        self.assertEqual(persisted.model, "new-model")
        self.assertEqual(persisted.connection_verification_status, ConnectionVerificationStatus.VERIFIED)
        self.assertEqual(persisted.last_verification_time, _VERIFIED_AT)

    def test_test_connection_refusal_does_not_save_or_call_runtime(self) -> None:
        config = make_config(base_url="https://old-provider.example/v1", model="")
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, test_connection, _ = self._run_cli(
                store,
                ["4", "https://new-provider.example/v1", "9", "n", "0"],
            )
            persisted = store.load().config

        test_connection.assert_not_called()
        self.assertEqual(persisted, config)
        self.assertIn("nothing was saved and no network request was made", output)

    def test_test_connection_saves_snapshot_before_runtime_and_reports_success(self) -> None:
        config = make_config(api_key="old-key", model="")
        observed: dict[str, AIProviderConfig] = {}

        def check_saved_snapshot(snapshot: AIProviderConfig, store: AIProviderConfigStore):
            observed["snapshot"] = snapshot
            observed["persisted"] = store.load().config
            return LLMConnectionTestResult(
                provider=snapshot.provider,
                completed_at=datetime.now(timezone.utc),
                verification_writeback_applied=True,
            )

        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, test_connection, getpass_mock = self._run_cli(
                store,
                ["3", "9", "y", "0"],
                passwords=["new-key"],
                test_error=check_saved_snapshot,
            )
            persisted = store.load().config

        getpass_mock.assert_called_once()
        test_connection.assert_called_once_with(observed["snapshot"], store)
        self.assertEqual(observed["snapshot"], observed["persisted"])
        self.assertEqual(persisted.api_key, "new-key")
        self.assertIn("Provider connection check succeeded.", output)
        self.assertIn("Verification result was saved.", output)

    def test_test_connection_remote_failure_and_stale_ux(self) -> None:
        config = make_config(model="")
        error = LLMRuntimeError(
            code=LLMRuntimeErrorCode.RATE_LIMIT,
            provider=PROVIDER_DEEPSEEK,
            operation=LLMOperation.TEST_CONNECTION,
            message="Provider rate limit exceeded.",
            verification_writeback_applied=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, test_connection, _ = self._run_cli(
                store,
                ["9", "y", "0"],
                test_error=error,
            )

        test_connection.assert_called_once()
        self.assertIn("Provider operation failed: Provider rate limit exceeded.", output)
        self.assertIn("Configuration changed while checking", output)

    def test_test_connection_capability_unavailable_explains_no_failed_writeback_or_fallback(self) -> None:
        config = make_config(provider=PROVIDER_ALIYUN_BAILIAN, model="")
        error = LLMRuntimeError(
            code=LLMRuntimeErrorCode.CAPABILITY_UNAVAILABLE,
            provider=PROVIDER_ALIYUN_BAILIAN,
            operation=LLMOperation.TEST_CONNECTION,
            message="Provider capability is unavailable.",
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, test_connection, _ = self._run_cli(
                store,
                ["9", "y", "0"],
                test_error=error,
            )
            persisted = store.load().config

        test_connection.assert_called_once()
        self.assertEqual(persisted.connection_verification_status, ConnectionVerificationStatus.UNVERIFIED)
        self.assertIn("No non-inference verification capability", output)
        self.assertIn("Verification was not changed to failed", output)
        self.assertIn("no inference fallback was used", output)

    def test_test_connection_local_writeback_io_failure_is_separate_from_provider_result(self) -> None:
        config = make_config(model="")
        error = LLMRuntimeError(
            code=LLMRuntimeErrorCode.UNKNOWN,
            provider=PROVIDER_DEEPSEEK,
            operation=LLMOperation.TEST_CONNECTION,
            message="Provider check succeeded, but verification write-back failed locally.",
            verification_writeback_error="verification write-back failed locally",
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, test_connection, _ = self._run_cli(
                store,
                ["9", "y", "0"],
                test_error=error,
            )

        test_connection.assert_called_once()
        self.assertIn("Provider check succeeded, but verification write-back failed locally.", output)
        self.assertNotIn("Provider operation failed", output)

    def test_refresh_requires_confirmation_for_unsaved_changes(self) -> None:
        config = make_config(model="stored-model")
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, _, _, _ = self._run_cli(
                store,
                ["7", "staged-model", "10", "n", "1", "10", "y", "1", "0"],
            )

        self.assertIn("Refresh cancelled; staged changes were kept.", output)
        self.assertIn("Model: staged-model", output)
        self.assertIn("Model: stored-model", output)

    def test_refresh_clears_latest_models(self) -> None:
        config = make_config()
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            output, list_models, test_connection, _ = self._run_cli(
                store,
                ["5", "10", "6", "0"],
                listed_models=("available-model",),
            )

        list_models.assert_called_once_with(config)
        test_connection.assert_not_called()
        self.assertIn("No recent model list", output)

    def test_cli_never_uses_complete(self) -> None:
        config = make_config(model="")
        result = LLMConnectionTestResult(
            provider=PROVIDER_DEEPSEEK,
            completed_at=datetime.now(timezone.utc),
            verification_writeback_applied=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            with patch("llm_provider_runtime.complete") as complete:
                _, list_models, test_connection, _ = self._run_cli(
                    store,
                    ["5", "9", "y", "0"],
                    listed_models=("available-model",),
                    test_result=result,
                )

        list_models.assert_called_once_with(config)
        test_connection.assert_called_once()
        complete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
