"""Targeted offline tests for the AM7-R03 Change 1 provider runtime."""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigIOError,
    AIProviderConfigStore,
    ConnectionVerificationStatus,
    PROVIDER_ALIYUN_BAILIAN,
    PROVIDER_DEEPSEEK,
)
import llm_provider_runtime as runtime


def make_config(
    provider: str = PROVIDER_DEEPSEEK,
    *,
    api_key: str = "test-key",
    base_url: str = "https://provider.example/v1",
    model: str = "test-model",
) -> AIProviderConfig:
    return AIProviderConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def make_client(
    *,
    models_response: object | None = None,
    models_side_effect: Exception | None = None,
    completion_response: object | None = None,
    completion_side_effect: Exception | None = None,
) -> Mock:
    client = Mock()
    client.models.list.return_value = models_response
    client.models.list.side_effect = models_side_effect
    client.chat.completions.create.return_value = completion_response
    client.chat.completions.create.side_effect = completion_side_effect
    return client


def make_status_error(
    error_type: type[APIStatusError],
    status_code: int,
    *,
    body: object | None = None,
    headers: dict[str, str] | None = None,
) -> APIStatusError:
    request = httpx.Request("GET", "https://provider.example/models")
    response = httpx.Response(
        status_code,
        request=request,
        headers=headers,
    )
    return error_type("provider detail must not be public", response=response, body=body)


def make_completion_response(
    *,
    content: object = "accepted",
    model: object = "provider-model",
    usage: object = None,
    finish_reason: object = "stop",
    response_id: object = "completion-id",
    request_id: object = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
        model=model,
        usage=usage,
        id=response_id,
        _request_id=request_id,
    )


class RuntimeContractTests(unittest.TestCase):
    def test_public_enums_have_the_frozen_values(self) -> None:
        self.assertEqual(
            [member.value for member in runtime.LLMOperation],
            ["list_models", "test_connection", "complete"],
        )
        self.assertEqual(
            [member.value for member in runtime.LLMMessageRole],
            ["system", "user", "assistant"],
        )
        self.assertEqual(
            [member.value for member in runtime.LLMRuntimeErrorCode],
            [
                "authentication",
                "timeout",
                "network",
                "rate_limit",
                "quota_or_billing",
                "invalid_request",
                "model_unavailable",
                "capability_unavailable",
                "provider_server_error",
                "malformed_response",
                "unsupported_provider",
                "unknown",
            ],
        )
        self.assertEqual(runtime.LLM_REQUEST_TIMEOUT_SECONDS, 120.0)

    def test_request_and_result_dataclasses_are_immutable_and_exact(self) -> None:
        message = runtime.LLMMessage(runtime.LLMMessageRole.USER, "hello")
        request = runtime.LLMCompletionRequest((message,))
        result = runtime.LLMCompletionResult(
            content="done",
            provider=PROVIDER_DEEPSEEK,
            model="test-model",
            input_tokens=1,
            output_tokens=2,
            total_tokens=3,
            finish_reason="stop",
            request_id="request-id",
        )
        connection_result = runtime.LLMConnectionTestResult(
            provider=PROVIDER_DEEPSEEK,
            completed_at=datetime.now(timezone.utc),
            verification_writeback_applied=True,
        )
        self.assertEqual([field.name for field in fields(runtime.LLMMessage)], ["role", "content"])
        self.assertEqual([field.name for field in fields(runtime.LLMCompletionRequest)], ["messages"])
        self.assertEqual(
            [field.name for field in fields(runtime.LLMCompletionResult)],
            [
                "content",
                "provider",
                "model",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "finish_reason",
                "request_id",
            ],
        )
        with self.assertRaisesRegex(AttributeError, "cannot assign"):
            message.content = "changed"  # type: ignore[misc]
        with self.assertRaisesRegex(AttributeError, "cannot assign"):
            request.messages = ()  # type: ignore[misc]
        with self.assertRaisesRegex(AttributeError, "cannot assign"):
            result.content = "changed"  # type: ignore[misc]
        with self.assertRaisesRegex(AttributeError, "cannot assign"):
            connection_result.provider = "changed"  # type: ignore[misc]

    def test_runtime_error_preserves_only_safe_public_fields(self) -> None:
        error = runtime.LLMRuntimeError(
            code=runtime.LLMRuntimeErrorCode.NETWORK,
            provider=PROVIDER_DEEPSEEK,
            operation=runtime.LLMOperation.LIST_MODELS,
            message="Provider network request failed.",
            status_code=503,
            request_id="request-id",
        )
        self.assertEqual(str(error), "Provider network request failed.")
        self.assertEqual(error.args, ("Provider network request failed.",))
        self.assertEqual(error.code, runtime.LLMRuntimeErrorCode.NETWORK)
        self.assertEqual(error.operation, runtime.LLMOperation.LIST_MODELS)
        self.assertIsNone(error.verification_writeback_applied)
        self.assertIsNone(error.verification_writeback_error)


class ReadinessTests(unittest.TestCase):
    def test_list_rejects_non_config_without_constructing_client(self) -> None:
        with patch.object(runtime, "OpenAI") as openai:
            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                runtime.list_models(object())  # type: ignore[arg-type]
        self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.INVALID_REQUEST)
        self.assertEqual(raised.exception.operation, runtime.LLMOperation.LIST_MODELS)
        self.assertIsNone(raised.exception.provider)
        openai.assert_not_called()

    def test_list_rejects_empty_provider_before_client(self) -> None:
        with patch.object(runtime, "OpenAI") as openai:
            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                runtime.list_models(make_config(provider="", model=""))
        self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.INVALID_REQUEST)
        self.assertIsNone(raised.exception.provider)
        openai.assert_not_called()

    def test_unknown_provider_is_unsupported_before_client(self) -> None:
        with patch.object(runtime, "OpenAI") as openai:
            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                runtime.list_models(make_config(provider="other-provider"))
        self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.UNSUPPORTED_PROVIDER)
        self.assertEqual(raised.exception.provider, "other-provider")
        openai.assert_not_called()

    def test_list_requires_key_and_base_url_but_not_model(self) -> None:
        for config in (
            make_config(api_key="", model=""),
            make_config(base_url="", model=""),
        ):
            with self.subTest(config=config):
                with patch.object(runtime, "OpenAI") as openai:
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.list_models(config)
                self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.INVALID_REQUEST)
                self.assertEqual(raised.exception.provider, PROVIDER_DEEPSEEK)
                openai.assert_not_called()

    def test_complete_requires_a_complete_config_before_request_or_client(self) -> None:
        request = runtime.LLMCompletionRequest(())
        with patch.object(runtime, "OpenAI") as openai:
            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                runtime.complete(make_config(model=""), request)
        self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.INVALID_REQUEST)
        self.assertEqual(raised.exception.operation, runtime.LLMOperation.COMPLETE)
        openai.assert_not_called()


class ListModelsTests(unittest.TestCase):
    def test_deepseek_list_constructs_one_configured_client_and_returns_ids(self) -> None:
        config = make_config(model="")
        client = make_client(
            models_response=SimpleNamespace(
                data=[SimpleNamespace(id="deepseek-chat"), SimpleNamespace(id="deepseek-reasoner")]
            )
        )
        with patch.object(runtime, "OpenAI", return_value=client) as openai:
            result = runtime.list_models(config)
        self.assertEqual(result, ("deepseek-chat", "deepseek-reasoner"))
        openai.assert_called_once_with(
            api_key="test-key",
            base_url="https://provider.example/v1",
            timeout=120.0,
            max_retries=0,
        )
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()

    def test_qwen_list_uses_the_same_best_effort_sdk_path(self) -> None:
        client = make_client(models_response=SimpleNamespace(data=[]))
        with patch.object(runtime, "OpenAI", return_value=client):
            result = runtime.list_models(make_config(provider=PROVIDER_ALIYUN_BAILIAN, model=""))
        self.assertEqual(result, ())
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()

    def test_list_normalizes_blanks_duplicates_and_preserves_provider_order(self) -> None:
        response = SimpleNamespace(
            data=[
                SimpleNamespace(id=" "),
                SimpleNamespace(id="beta"),
                SimpleNamespace(id="alpha"),
                SimpleNamespace(id="beta"),
                SimpleNamespace(id="  provider-value  "),
                SimpleNamespace(id=""),
            ]
        )
        client = make_client(models_response=response)
        with patch.object(runtime, "OpenAI", return_value=client):
            result = runtime.list_models(make_config(model=""))
        self.assertEqual(result, ("beta", "alpha", "  provider-value  "))

    def test_list_allows_empty_collection(self) -> None:
        client = make_client(models_response=SimpleNamespace(data=()))
        with patch.object(runtime, "OpenAI", return_value=client):
            self.assertEqual(runtime.list_models(make_config(model="")), ())

    def test_list_rejects_malformed_response_shapes(self) -> None:
        malformed_responses = (
            SimpleNamespace(data={"not": "a collection"}),
            SimpleNamespace(data=[SimpleNamespace(id=123)]),
            SimpleNamespace(data=[object()]),
            object(),
        )
        for response in malformed_responses:
            with self.subTest(response=response):
                client = make_client(models_response=response)
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.list_models(make_config(model=""))
                self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.MALFORMED_RESPONSE)
                client.models.list.assert_called_once_with()
                client.chat.completions.create.assert_not_called()

    def test_qwen_list_404_and_405_are_capability_unavailable(self) -> None:
        for status_code in (404, 405):
            with self.subTest(status_code=status_code):
                client = make_client(
                    models_side_effect=make_status_error(APIStatusError, status_code)
                )
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.list_models(
                            make_config(provider=PROVIDER_ALIYUN_BAILIAN, model="")
                        )
                self.assertEqual(
                    raised.exception.code,
                    runtime.LLMRuntimeErrorCode.CAPABILITY_UNAVAILABLE,
                )
                self.assertEqual(raised.exception.status_code, status_code)
                client.models.list.assert_called_once_with()
                client.chat.completions.create.assert_not_called()

    def test_deepseek_list_404_is_not_capability_unavailable(self) -> None:
        client = make_client(models_side_effect=make_status_error(APIStatusError, 404))
        with patch.object(runtime, "OpenAI", return_value=client):
            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                runtime.list_models(make_config(model=""))
        self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.INVALID_REQUEST)

    def test_list_maps_auth_timeout_network_rate_and_server_errors(self) -> None:
        request = httpx.Request("GET", "https://provider.example/models")
        cases = (
            (
                AuthenticationError(
                    "secret-key", response=httpx.Response(401, request=request), body=None
                ),
                runtime.LLMRuntimeErrorCode.AUTHENTICATION,
            ),
            (APITimeoutError(request=request), runtime.LLMRuntimeErrorCode.TIMEOUT),
            (APIConnectionError(request=request), runtime.LLMRuntimeErrorCode.NETWORK),
            (
                RateLimitError(
                    "detail", response=httpx.Response(429, request=request), body=None
                ),
                runtime.LLMRuntimeErrorCode.RATE_LIMIT,
            ),
            (
                InternalServerError(
                    "detail", response=httpx.Response(503, request=request), body=None
                ),
                runtime.LLMRuntimeErrorCode.PROVIDER_SERVER_ERROR,
            ),
        )
        for exception, expected_code in cases:
            with self.subTest(exception=type(exception).__name__):
                client = make_client(models_side_effect=exception)
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.list_models(make_config(model=""))
                self.assertEqual(raised.exception.code, expected_code)
                self.assertNotIn("secret-key", str(raised.exception))
                client.models.list.assert_called_once_with()

    def test_list_uses_qwen_billing_override_and_safe_request_id(self) -> None:
        exception = make_status_error(
            BadRequestError,
            400,
            body={"error": {"code": "Arrearage"}},
            headers={"X-Request-ID": "header-request-id"},
        )
        client = make_client(models_side_effect=exception)
        with patch.object(runtime, "OpenAI", return_value=client):
            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                runtime.list_models(make_config(provider=PROVIDER_ALIYUN_BAILIAN, model=""))
        self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.QUOTA_OR_BILLING)
        self.assertEqual(raised.exception.request_id, "header-request-id")
        self.assertNotIn("Arrearage", str(raised.exception))

    def test_list_maps_deepseek_402_to_quota_or_billing(self) -> None:
        client = make_client(models_side_effect=make_status_error(APIStatusError, 402))
        with patch.object(runtime, "OpenAI", return_value=client):
            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                runtime.list_models(make_config(model=""))
        self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.QUOTA_OR_BILLING)


class TestConnectionTests(unittest.TestCase):
    def _store_with_config(self, path: Path, config: AIProviderConfig) -> AIProviderConfigStore:
        store = AIProviderConfigStore(path)
        store.save(config)
        return store

    def test_connection_readiness_failures_do_not_create_client_or_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")
            cases = (
                (object(), store),
                (make_config(model=""), object()),
                (make_config(api_key="", model=""), store),
                (make_config(provider="other-provider", model=""), store),
            )
            for config, supplied_store in cases:
                with self.subTest(config=config, store=supplied_store):
                    with patch.object(runtime, "OpenAI") as openai:
                        with patch.object(
                            store,
                            "record_connection_verification",
                            wraps=store.record_connection_verification,
                        ) as writeback:
                            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                                runtime.test_connection(config, supplied_store)  # type: ignore[arg-type]
                    self.assertIn(
                        raised.exception.code,
                        {
                            runtime.LLMRuntimeErrorCode.INVALID_REQUEST,
                            runtime.LLMRuntimeErrorCode.UNSUPPORTED_PROVIDER,
                        },
                    )
                    self.assertEqual(
                        raised.exception.operation,
                        runtime.LLMOperation.TEST_CONNECTION,
                    )
                    openai.assert_not_called()
                    writeback.assert_not_called()

    def test_connection_success_writes_verified_with_utc_time(self) -> None:
        config = make_config(model="")
        client = make_client(models_response=SimpleNamespace(data=[SimpleNamespace(id="deepseek-chat")]))
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            with patch.object(
                store,
                "record_connection_verification",
                wraps=store.record_connection_verification,
            ) as writeback:
                with patch.object(runtime, "OpenAI", return_value=client) as openai:
                    result = runtime.test_connection(config, store)
            persisted = store.load().config

        self.assertEqual(result.provider, PROVIDER_DEEPSEEK)
        self.assertTrue(result.verification_writeback_applied)
        self.assertIs(result.completed_at.tzinfo, timezone.utc)
        self.assertEqual(persisted.connection_verification_status, ConnectionVerificationStatus.VERIFIED)
        self.assertEqual(persisted.last_verification_time, result.completed_at)
        openai.assert_called_once_with(
            api_key="test-key",
            base_url="https://provider.example/v1",
            timeout=120.0,
            max_retries=0,
        )
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()
        writeback.assert_called_once_with(
            checked_provider=PROVIDER_DEEPSEEK,
            checked_api_key="test-key",
            checked_base_url="https://provider.example/v1",
            status=ConnectionVerificationStatus.VERIFIED,
            completed_at=result.completed_at,
        )

    def test_connection_empty_models_still_writes_verified(self) -> None:
        config = make_config(model="")
        client = make_client(models_response=SimpleNamespace(data=[]))
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            with patch.object(runtime, "OpenAI", return_value=client):
                result = runtime.test_connection(config, store)
            persisted = store.load().config

        self.assertTrue(result.verification_writeback_applied)
        self.assertEqual(persisted.connection_verification_status, ConnectionVerificationStatus.VERIFIED)
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()

    def test_connection_remote_failure_writes_failed_and_preserves_error(self) -> None:
        config = make_config(model="")
        exception = make_status_error(
            AuthenticationError,
            401,
            headers={"X-Request-ID": "remote-request-id"},
        )
        client = make_client(models_side_effect=exception)
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            with self.assertRaises(runtime.LLMRuntimeError) as raised:
                with patch.object(runtime, "OpenAI", return_value=client):
                    runtime.test_connection(config, store)
            persisted = store.load().config

        error = raised.exception
        self.assertEqual(error.code, runtime.LLMRuntimeErrorCode.AUTHENTICATION)
        self.assertEqual(error.status_code, 401)
        self.assertEqual(error.request_id, "remote-request-id")
        self.assertTrue(error.verification_writeback_applied)
        self.assertIsNone(error.verification_writeback_error)
        self.assertEqual(persisted.connection_verification_status, ConnectionVerificationStatus.FAILED)
        self.assertIs(persisted.last_verification_time.tzinfo, timezone.utc)
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()

    def test_connection_qwen_capability_unavailable_does_not_write_verification(self) -> None:
        config = make_config(provider=PROVIDER_ALIYUN_BAILIAN, model="")
        client = make_client(models_side_effect=make_status_error(APIStatusError, 404))
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            with patch.object(
                store,
                "record_connection_verification",
                wraps=store.record_connection_verification,
            ) as writeback:
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.test_connection(config, store)
            persisted = store.load().config

        self.assertEqual(
            raised.exception.code,
            runtime.LLMRuntimeErrorCode.CAPABILITY_UNAVAILABLE,
        )
        self.assertIsNone(raised.exception.verification_writeback_applied)
        self.assertIsNone(raised.exception.verification_writeback_error)
        self.assertEqual(persisted.connection_verification_status, ConnectionVerificationStatus.UNVERIFIED)
        self.assertIsNone(persisted.last_verification_time)
        writeback.assert_not_called()
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()

    def test_connection_stale_success_returns_false_without_overwriting_current_config(self) -> None:
        checked_config = make_config(api_key="checked-key", model="")
        current_config = make_config(api_key="current-key", model="")
        client = make_client(models_response=SimpleNamespace(data=[]))
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", current_config)
            with patch.object(runtime, "OpenAI", return_value=client):
                result = runtime.test_connection(checked_config, store)
            persisted = store.load().config

        self.assertFalse(result.verification_writeback_applied)
        self.assertEqual(persisted, current_config)
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()

    def test_connection_stale_failure_preserves_remote_error_and_current_config(self) -> None:
        checked_config = make_config(api_key="checked-key", model="")
        current_config = make_config(api_key="current-key", model="")
        client = make_client(models_side_effect=make_status_error(RateLimitError, 429))
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", current_config)
            with patch.object(runtime, "OpenAI", return_value=client):
                with self.assertRaises(runtime.LLMRuntimeError) as raised:
                    runtime.test_connection(checked_config, store)
            persisted = store.load().config

        self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.RATE_LIMIT)
        self.assertFalse(raised.exception.verification_writeback_applied)
        self.assertIsNone(raised.exception.verification_writeback_error)
        self.assertEqual(persisted, current_config)
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()

    def test_connection_remote_failure_with_local_writeback_error_preserves_remote_fields(self) -> None:
        config = make_config(model="")
        client = make_client(
            models_side_effect=make_status_error(
                RateLimitError,
                429,
                headers={"X-Request-ID": "remote-request-id"},
            )
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            with patch.object(
                store,
                "record_connection_verification",
                side_effect=AIProviderConfigIOError("local path detail"),
            ) as writeback:
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.test_connection(config, store)

        error = raised.exception
        self.assertEqual(error.code, runtime.LLMRuntimeErrorCode.RATE_LIMIT)
        self.assertEqual(error.status_code, 429)
        self.assertEqual(error.request_id, "remote-request-id")
        self.assertIsNone(error.verification_writeback_applied)
        self.assertEqual(error.verification_writeback_error, "verification write-back failed locally")
        self.assertIn("Provider check failed", str(error))
        self.assertNotIn("local path detail", str(error))
        writeback.assert_called_once()
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()

    def test_connection_remote_success_with_local_writeback_error_is_unknown_local_failure(self) -> None:
        config = make_config(model="")
        client = make_client(models_response=SimpleNamespace(data=[]))
        with tempfile.TemporaryDirectory() as tmp:
            store = self._store_with_config(Path(tmp) / "ai_provider.json", config)
            with patch.object(
                store,
                "record_connection_verification",
                side_effect=AIProviderConfigIOError("local path detail"),
            ) as writeback:
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.test_connection(config, store)

        error = raised.exception
        self.assertEqual(error.code, runtime.LLMRuntimeErrorCode.UNKNOWN)
        self.assertEqual(error.operation, runtime.LLMOperation.TEST_CONNECTION)
        self.assertIsNone(error.verification_writeback_applied)
        self.assertEqual(error.verification_writeback_error, "verification write-back failed locally")
        self.assertEqual(
            str(error),
            "Provider check succeeded, but verification write-back failed locally.",
        )
        self.assertNotIn("local path detail", str(error))
        writeback.assert_called_once()
        client.models.list.assert_called_once_with()
        client.chat.completions.create.assert_not_called()


class CompletionTests(unittest.TestCase):
    def test_complete_rejects_invalid_request_shapes_before_client(self) -> None:
        invalid_requests = (
            object(),
            runtime.LLMCompletionRequest([]),  # type: ignore[arg-type]
            runtime.LLMCompletionRequest(()),
            runtime.LLMCompletionRequest((object(),)),  # type: ignore[arg-type]
            runtime.LLMCompletionRequest((runtime.LLMMessage("user", "hello"),)),  # type: ignore[arg-type]
            runtime.LLMCompletionRequest((runtime.LLMMessage(runtime.LLMMessageRole.USER, 3),)),  # type: ignore[arg-type]
            runtime.LLMCompletionRequest((runtime.LLMMessage(runtime.LLMMessageRole.USER, " \t"),)),
        )
        for request in invalid_requests:
            with self.subTest(request=request):
                with patch.object(runtime, "OpenAI") as openai:
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.complete(make_config(), request)  # type: ignore[arg-type]
                self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.INVALID_REQUEST)
                self.assertEqual(raised.exception.operation, runtime.LLMOperation.COMPLETE)
                openai.assert_not_called()

    def test_complete_sends_exact_sdk_kwargs_and_preserves_message_content_order(self) -> None:
        request = runtime.LLMCompletionRequest(
            (
                runtime.LLMMessage(runtime.LLMMessageRole.SYSTEM, " system "),
                runtime.LLMMessage(runtime.LLMMessageRole.USER, "user"),
                runtime.LLMMessage(runtime.LLMMessageRole.ASSISTANT, "assistant"),
            )
        )
        client = make_client(completion_response=make_completion_response())
        with patch.object(runtime, "OpenAI", return_value=client) as openai:
            result = runtime.complete(make_config(), request)
        self.assertEqual(result.content, "accepted")
        openai.assert_called_once_with(
            api_key="test-key",
            base_url="https://provider.example/v1",
            timeout=120.0,
            max_retries=0,
        )
        client.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=[
                {"role": "system", "content": " system "},
                {"role": "user", "content": "user"},
                {"role": "assistant", "content": "assistant"},
            ],
            stream=False,
        )
        client.models.list.assert_not_called()

    def test_complete_extracts_all_result_fields(self) -> None:
        response = make_completion_response(
            content=" provider content ",
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=5, total_tokens=9),
            finish_reason="length",
            response_id="completion-id",
            request_id="transport-id",
        )
        client = make_client(completion_response=response)
        with patch.object(runtime, "OpenAI", return_value=client):
            result = runtime.complete(
                make_config(),
                runtime.LLMCompletionRequest(
                    (runtime.LLMMessage(runtime.LLMMessageRole.USER, "prompt"),)
                ),
            )
        self.assertEqual(result.content, " provider content ")
        self.assertEqual(result.provider, PROVIDER_DEEPSEEK)
        self.assertEqual(result.model, "provider-model")
        self.assertEqual(result.input_tokens, 4)
        self.assertEqual(result.output_tokens, 5)
        self.assertEqual(result.total_tokens, 9)
        self.assertEqual(result.finish_reason, "length")
        self.assertEqual(result.request_id, "completion-id")

    def test_complete_uses_fallbacks_and_validates_each_usage_value(self) -> None:
        response = make_completion_response(
            model="",
            usage=SimpleNamespace(prompt_tokens=True, completion_tokens=-1, total_tokens="9"),
            finish_reason=3,
            response_id="",
            request_id="transport-id",
        )
        client = make_client(completion_response=response)
        with patch.object(runtime, "OpenAI", return_value=client):
            result = runtime.complete(
                make_config(),
                runtime.LLMCompletionRequest(
                    (runtime.LLMMessage(runtime.LLMMessageRole.USER, "prompt"),)
                ),
            )
        self.assertEqual(result.model, "test-model")
        self.assertIsNone(result.input_tokens)
        self.assertIsNone(result.output_tokens)
        self.assertIsNone(result.total_tokens)
        self.assertIsNone(result.finish_reason)
        self.assertEqual(result.request_id, "transport-id")

    def test_complete_allows_missing_usage(self) -> None:
        client = make_client(completion_response=make_completion_response(usage=None))
        with patch.object(runtime, "OpenAI", return_value=client):
            result = runtime.complete(
                make_config(),
                runtime.LLMCompletionRequest(
                    (runtime.LLMMessage(runtime.LLMMessageRole.USER, "prompt"),)
                ),
            )
        self.assertEqual((result.input_tokens, result.output_tokens, result.total_tokens), (None, None, None))

    def test_complete_rejects_missing_or_empty_content_as_malformed_response(self) -> None:
        malformed_responses = (
            SimpleNamespace(choices=[]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=""))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" \n"))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))]),
        )
        request = runtime.LLMCompletionRequest(
            (runtime.LLMMessage(runtime.LLMMessageRole.USER, "prompt"),)
        )
        for response in malformed_responses:
            with self.subTest(response=response):
                client = make_client(completion_response=response)
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.complete(make_config(), request)
                self.assertEqual(raised.exception.code, runtime.LLMRuntimeErrorCode.MALFORMED_RESPONSE)
                client.chat.completions.create.assert_called_once_with(
                    model="test-model",
                    messages=[{"role": "user", "content": "prompt"}],
                    stream=False,
                )

    def test_complete_maps_model_unavailable_and_qwen_model_override(self) -> None:
        cases = (
            (
                PROVIDER_DEEPSEEK,
                make_status_error(APIStatusError, 404),
                runtime.LLMRuntimeErrorCode.MODEL_UNAVAILABLE,
            ),
            (
                PROVIDER_ALIYUN_BAILIAN,
                make_status_error(
                    BadRequestError,
                    400,
                    body={"code": "model_not_supported"},
                ),
                runtime.LLMRuntimeErrorCode.MODEL_UNAVAILABLE,
            ),
        )
        request = runtime.LLMCompletionRequest(
            (runtime.LLMMessage(runtime.LLMMessageRole.USER, "prompt"),)
        )
        for provider, exception, expected_code in cases:
            with self.subTest(provider=provider):
                client = make_client(completion_side_effect=exception)
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.complete(make_config(provider=provider), request)
                self.assertEqual(raised.exception.code, expected_code)
                client.chat.completions.create.assert_called_once_with(
                    model="test-model",
                    messages=[{"role": "user", "content": "prompt"}],
                    stream=False,
                )
                client.models.list.assert_not_called()

    def test_complete_maps_auth_timeout_network_and_rate_errors(self) -> None:
        request = httpx.Request("POST", "https://provider.example/chat/completions")
        cases = (
            (
                AuthenticationError(
                    "secret-key", response=httpx.Response(401, request=request), body=None
                ),
                runtime.LLMRuntimeErrorCode.AUTHENTICATION,
            ),
            (APITimeoutError(request=request), runtime.LLMRuntimeErrorCode.TIMEOUT),
            (APIConnectionError(request=request), runtime.LLMRuntimeErrorCode.NETWORK),
            (
                RateLimitError(
                    "detail", response=httpx.Response(429, request=request), body=None
                ),
                runtime.LLMRuntimeErrorCode.RATE_LIMIT,
            ),
        )
        completion_request = runtime.LLMCompletionRequest(
            (runtime.LLMMessage(runtime.LLMMessageRole.USER, "prompt"),)
        )
        for exception, expected_code in cases:
            with self.subTest(exception=type(exception).__name__):
                client = make_client(completion_side_effect=exception)
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.complete(make_config(), completion_request)
                self.assertEqual(raised.exception.code, expected_code)
                self.assertNotIn("secret-key", str(raised.exception))
                client.chat.completions.create.assert_called_once_with(
                    model="test-model",
                    messages=[{"role": "user", "content": "prompt"}],
                    stream=False,
                )
                client.models.list.assert_not_called()

    def test_complete_maps_invalid_server_unknown_and_deepseek_quota_errors(self) -> None:
        cases = (
            (
                make_status_error(BadRequestError, 400),
                runtime.LLMRuntimeErrorCode.INVALID_REQUEST,
            ),
            (
                make_status_error(InternalServerError, 503),
                runtime.LLMRuntimeErrorCode.PROVIDER_SERVER_ERROR,
            ),
            (make_status_error(APIStatusError, 418), runtime.LLMRuntimeErrorCode.UNKNOWN),
            (make_status_error(APIStatusError, 402), runtime.LLMRuntimeErrorCode.QUOTA_OR_BILLING),
        )
        request = runtime.LLMCompletionRequest(
            (runtime.LLMMessage(runtime.LLMMessageRole.USER, "prompt"),)
        )
        for exception, expected_code in cases:
            with self.subTest(status=exception.status_code):
                client = make_client(completion_side_effect=exception)
                with patch.object(runtime, "OpenAI", return_value=client):
                    with self.assertRaises(runtime.LLMRuntimeError) as raised:
                        runtime.complete(make_config(), request)
                self.assertEqual(raised.exception.code, expected_code)
                client.chat.completions.create.assert_called_once_with(
                    model="test-model",
                    messages=[{"role": "user", "content": "prompt"}],
                    stream=False,
                )
                client.models.list.assert_not_called()

    def test_complete_makes_one_call_without_retry_or_inference_fallback(self) -> None:
        exception = make_status_error(APIStatusError, 500)
        client = make_client(completion_side_effect=exception)
        request = runtime.LLMCompletionRequest(
            (runtime.LLMMessage(runtime.LLMMessageRole.USER, "prompt"),)
        )
        with patch.object(runtime, "OpenAI", return_value=client):
            with self.assertRaises(runtime.LLMRuntimeError):
                runtime.complete(make_config(), request)
        client.chat.completions.create.assert_called_once_with(
            model="test-model",
            messages=[{"role": "user", "content": "prompt"}],
            stream=False,
        )
        client.models.list.assert_not_called()


if __name__ == "__main__":
    unittest.main()
