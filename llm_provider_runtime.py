"""Provider-neutral runtime for the configured Qwen and DeepSeek clients."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    RateLimitError,
    UnprocessableEntityError,
)

from ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigIOError,
    AIProviderConfigStore,
    ConnectionVerificationStatus,
    PROVIDER_ALIYUN_BAILIAN,
    PROVIDER_DEEPSEEK,
)


LLM_REQUEST_TIMEOUT_SECONDS = 120.0


class LLMOperation(str, Enum):
    """The supported provider-runtime operations."""

    LIST_MODELS = "list_models"
    TEST_CONNECTION = "test_connection"
    COMPLETE = "complete"


class LLMMessageRole(str, Enum):
    """The role of a message sent to a chat completion."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMRuntimeErrorCode(str, Enum):
    """Stable classifications for local and remote runtime failures."""

    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    QUOTA_OR_BILLING = "quota_or_billing"
    INVALID_REQUEST = "invalid_request"
    MODEL_UNAVAILABLE = "model_unavailable"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    PROVIDER_SERVER_ERROR = "provider_server_error"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUPPORTED_PROVIDER = "unsupported_provider"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LLMMessage:
    """One normalized chat message."""

    role: LLMMessageRole
    content: str


@dataclass(frozen=True)
class LLMCompletionRequest:
    """The complete Runtime request surface."""

    messages: tuple[LLMMessage, ...]


@dataclass(frozen=True)
class LLMCompletionResult:
    """The normalized first-choice completion result."""

    content: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    finish_reason: str | None
    request_id: str | None


@dataclass(frozen=True)
class LLMConnectionTestResult:
    """The successful non-inference Provider connection-check result."""

    provider: str
    completed_at: datetime
    verification_writeback_applied: bool


class LLMRuntimeError(RuntimeError):
    """A safe, normalized local or Provider-runtime failure."""

    def __init__(
        self,
        *,
        code: LLMRuntimeErrorCode,
        provider: str | None,
        operation: LLMOperation,
        message: str,
        status_code: int | None = None,
        request_id: str | None = None,
        verification_writeback_applied: bool | None = None,
        verification_writeback_error: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.operation = operation
        self.status_code = status_code
        self.request_id = request_id
        self.verification_writeback_applied = verification_writeback_applied
        self.verification_writeback_error = verification_writeback_error


_SAFE_ERROR_MESSAGES = {
    LLMRuntimeErrorCode.AUTHENTICATION: "Provider authentication failed.",
    LLMRuntimeErrorCode.TIMEOUT: "Provider request timed out.",
    LLMRuntimeErrorCode.NETWORK: "Provider network request failed.",
    LLMRuntimeErrorCode.RATE_LIMIT: "Provider rate limit exceeded.",
    LLMRuntimeErrorCode.QUOTA_OR_BILLING: "Provider quota or billing is unavailable.",
    LLMRuntimeErrorCode.INVALID_REQUEST: "Provider request is invalid.",
    LLMRuntimeErrorCode.MODEL_UNAVAILABLE: "Configured model is unavailable.",
    LLMRuntimeErrorCode.CAPABILITY_UNAVAILABLE: "Provider capability is unavailable.",
    LLMRuntimeErrorCode.PROVIDER_SERVER_ERROR: "Provider server error.",
    LLMRuntimeErrorCode.MALFORMED_RESPONSE: "Provider returned a malformed response.",
    LLMRuntimeErrorCode.UNSUPPORTED_PROVIDER: "Provider is unsupported.",
    LLMRuntimeErrorCode.UNKNOWN: "Provider request failed.",
}

_QWEN_BILLING_CODES = {
    "Arrearage",
    "AllocationQuota.FreeTierOnly",
    "CommodityNotPurchased",
    "PrepaidBillOverdue",
    "PostpaidBillOverdue",
}

_QWEN_MODEL_CODES = {
    "Model.AccessDenied",
    "ModelNotFound",
    "model_not_found",
    "model_not_supported",
}


def _runtime_error(
    *,
    code: LLMRuntimeErrorCode,
    provider: str | None,
    operation: LLMOperation,
    status_code: int | None = None,
    request_id: str | None = None,
) -> LLMRuntimeError:
    return LLMRuntimeError(
        code=code,
        provider=provider,
        operation=operation,
        message=_SAFE_ERROR_MESSAGES[code],
        status_code=status_code,
        request_id=request_id,
    )


def _available_provider(config: object) -> str | None:
    if not isinstance(config, AIProviderConfig):
        return None
    provider = config.provider
    return provider if isinstance(provider, str) and provider else None


def _validate_config(
    config: object,
    operation: LLMOperation,
) -> AIProviderConfig:
    """Validate all operation readiness before creating an SDK client."""

    provider = _available_provider(config)
    if not isinstance(config, AIProviderConfig):
        raise _runtime_error(
            code=LLMRuntimeErrorCode.INVALID_REQUEST,
            provider=None,
            operation=operation,
        )

    if provider is None:
        raise _runtime_error(
            code=LLMRuntimeErrorCode.INVALID_REQUEST,
            provider=None,
            operation=operation,
        )

    if provider == PROVIDER_ALIYUN_BAILIAN:
        pass
    elif provider == PROVIDER_DEEPSEEK:
        pass
    else:
        raise _runtime_error(
            code=LLMRuntimeErrorCode.UNSUPPORTED_PROVIDER,
            provider=provider,
            operation=operation,
        )

    if operation in {LLMOperation.LIST_MODELS, LLMOperation.TEST_CONNECTION}:
        required_values = (config.api_key, config.base_url)
        if not all(isinstance(value, str) and value for value in required_values):
            raise _runtime_error(
                code=LLMRuntimeErrorCode.INVALID_REQUEST,
                provider=provider,
                operation=operation,
            )
    elif operation is LLMOperation.COMPLETE:
        required_values = (
            config.provider,
            config.api_key,
            config.base_url,
            config.model,
        )
        if config.is_complete is not True or not all(
            isinstance(value, str) and value for value in required_values
        ):
            raise _runtime_error(
                code=LLMRuntimeErrorCode.INVALID_REQUEST,
                provider=provider,
                operation=operation,
            )

    return config


def _new_client(config: AIProviderConfig) -> OpenAI:
    return OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=LLM_REQUEST_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _structured_error_code(exception: OpenAIError) -> str | None:
    body = getattr(exception, "body", None)
    if not isinstance(body, Mapping):
        return None

    root_code = body.get("code")
    if isinstance(root_code, str):
        return root_code

    error = body.get("error")
    if not isinstance(error, Mapping):
        return None
    nested_code = error.get("code")
    return nested_code if isinstance(nested_code, str) else None


def _usable_status_code(exception: OpenAIError) -> int | None:
    status_code = getattr(exception, "status_code", None)
    if isinstance(status_code, int) and not isinstance(status_code, bool):
        return status_code
    return None


def _nonempty_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _exception_request_id(exception: OpenAIError) -> str | None:
    request_id = _nonempty_string(getattr(exception, "request_id", None))
    if request_id is not None:
        return request_id

    response = getattr(exception, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        try:
            for key, value in headers.items():
                if isinstance(key, str) and key.lower() == "x-request-id":
                    request_id = _nonempty_string(value)
                    if request_id is not None:
                        return request_id
        except (AttributeError, TypeError):
            pass

    body = getattr(exception, "body", None)
    if isinstance(body, Mapping):
        return _nonempty_string(body.get("request_id"))
    return None


def _normalize_openai_error(
    exception: OpenAIError,
    *,
    provider: str,
    operation: LLMOperation,
) -> LLMRuntimeError:
    """Convert an SDK failure to the frozen public error contract."""

    status_code = _usable_status_code(exception)
    request_id = _exception_request_id(exception)
    structured_code = _structured_error_code(exception)

    if provider == PROVIDER_DEEPSEEK and status_code == 402:
        code = LLMRuntimeErrorCode.QUOTA_OR_BILLING
    elif provider == PROVIDER_ALIYUN_BAILIAN and structured_code in _QWEN_BILLING_CODES:
        code = LLMRuntimeErrorCode.QUOTA_OR_BILLING
    elif (
        provider == PROVIDER_ALIYUN_BAILIAN
        and operation is LLMOperation.COMPLETE
        and structured_code in _QWEN_MODEL_CODES
    ):
        code = LLMRuntimeErrorCode.MODEL_UNAVAILABLE
    elif (
        provider == PROVIDER_ALIYUN_BAILIAN
        and operation in {LLMOperation.LIST_MODELS, LLMOperation.TEST_CONNECTION}
        and status_code in {404, 405}
    ):
        code = LLMRuntimeErrorCode.CAPABILITY_UNAVAILABLE
    elif isinstance(exception, APITimeoutError) or status_code == 408:
        code = LLMRuntimeErrorCode.TIMEOUT
    elif isinstance(exception, APIConnectionError):
        code = LLMRuntimeErrorCode.NETWORK
    elif isinstance(exception, AuthenticationError) or status_code in {401, 403}:
        code = LLMRuntimeErrorCode.AUTHENTICATION
    elif isinstance(exception, RateLimitError) or status_code == 429:
        code = LLMRuntimeErrorCode.RATE_LIMIT
    elif (
        isinstance(exception, (BadRequestError, UnprocessableEntityError))
        or status_code in {400, 422}
    ):
        code = LLMRuntimeErrorCode.INVALID_REQUEST
    elif isinstance(exception, InternalServerError) or (
        status_code is not None and 500 <= status_code <= 599
    ):
        code = LLMRuntimeErrorCode.PROVIDER_SERVER_ERROR
    elif operation is LLMOperation.COMPLETE and status_code == 404:
        code = LLMRuntimeErrorCode.MODEL_UNAVAILABLE
    elif status_code in {404, 405}:
        code = LLMRuntimeErrorCode.INVALID_REQUEST
    elif isinstance(exception, (APIStatusError, OpenAIError)):
        code = LLMRuntimeErrorCode.UNKNOWN
    else:
        code = LLMRuntimeErrorCode.UNKNOWN

    return _runtime_error(
        code=code,
        provider=provider,
        operation=operation,
        status_code=status_code,
        request_id=request_id,
    )


def _normalize_model_ids(
    response: Any,
    provider: str,
    operation: LLMOperation = LLMOperation.LIST_MODELS,
) -> tuple[str, ...]:
    try:
        items = response.data
    except AttributeError as exception:
        raise _runtime_error(
            code=LLMRuntimeErrorCode.MALFORMED_RESPONSE,
            provider=provider,
            operation=operation,
        ) from exception

    if not isinstance(items, (list, tuple)):
        raise _runtime_error(
            code=LLMRuntimeErrorCode.MALFORMED_RESPONSE,
            provider=provider,
            operation=operation,
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        try:
            model_id = item.id
        except AttributeError as exception:
            raise _runtime_error(
                code=LLMRuntimeErrorCode.MALFORMED_RESPONSE,
                provider=provider,
                operation=operation,
            ) from exception
        if not isinstance(model_id, str):
            raise _runtime_error(
                code=LLMRuntimeErrorCode.MALFORMED_RESPONSE,
                provider=provider,
                operation=operation,
            )
        if not model_id.strip() or model_id in seen:
            continue
        seen.add(model_id)
        normalized.append(model_id)
    return tuple(normalized)


def list_models(config: AIProviderConfig) -> tuple[str, ...]:
    """Return real Provider model identifiers without inference or caching."""

    ready_config = _validate_config(config, LLMOperation.LIST_MODELS)
    try:
        response = _new_client(ready_config).models.list()
    except OpenAIError as exception:
        raise _normalize_openai_error(
            exception,
            provider=ready_config.provider,
            operation=LLMOperation.LIST_MODELS,
        ) from exception
    return _normalize_model_ids(response, ready_config.provider)


def _writeback_error(
    remote_error: LLMRuntimeError,
    *,
    message: str,
) -> LLMRuntimeError:
    return LLMRuntimeError(
        code=remote_error.code,
        provider=remote_error.provider,
        operation=remote_error.operation,
        message=message,
        status_code=remote_error.status_code,
        request_id=remote_error.request_id,
        verification_writeback_applied=None,
        verification_writeback_error="verification write-back failed locally",
    )


def _remote_error_with_writeback(
    remote_error: LLMRuntimeError,
    applied: bool,
) -> LLMRuntimeError:
    return LLMRuntimeError(
        code=remote_error.code,
        provider=remote_error.provider,
        operation=remote_error.operation,
        message=str(remote_error),
        status_code=remote_error.status_code,
        request_id=remote_error.request_id,
        verification_writeback_applied=applied,
    )


def test_connection(
    config: AIProviderConfig,
    store: AIProviderConfigStore,
) -> LLMConnectionTestResult:
    """Run one non-inference models check and record its R02 verification result."""

    ready_config = _validate_config(config, LLMOperation.TEST_CONNECTION)
    if not isinstance(store, AIProviderConfigStore):
        raise _runtime_error(
            code=LLMRuntimeErrorCode.INVALID_REQUEST,
            provider=ready_config.provider,
            operation=LLMOperation.TEST_CONNECTION,
        )

    checked_provider = ready_config.provider
    checked_api_key = ready_config.api_key
    checked_base_url = ready_config.base_url

    try:
        try:
            response = _new_client(ready_config).models.list()
        except OpenAIError as exception:
            raise _normalize_openai_error(
                exception,
                provider=checked_provider,
                operation=LLMOperation.TEST_CONNECTION,
            ) from exception
        _normalize_model_ids(
            response,
            checked_provider,
            operation=LLMOperation.TEST_CONNECTION,
        )
    except LLMRuntimeError as remote_error:
        if remote_error.code is LLMRuntimeErrorCode.CAPABILITY_UNAVAILABLE:
            raise

        completed_at = datetime.now(timezone.utc)
        try:
            applied = store.record_connection_verification(
                checked_provider=checked_provider,
                checked_api_key=checked_api_key,
                checked_base_url=checked_base_url,
                status=ConnectionVerificationStatus.FAILED,
                completed_at=completed_at,
            )
        except AIProviderConfigIOError as exception:
            raise _writeback_error(
                remote_error,
                message="Provider check failed and verification write-back failed locally.",
            ) from exception
        raise _remote_error_with_writeback(remote_error, applied) from remote_error

    completed_at = datetime.now(timezone.utc)
    try:
        applied = store.record_connection_verification(
            checked_provider=checked_provider,
            checked_api_key=checked_api_key,
            checked_base_url=checked_base_url,
            status=ConnectionVerificationStatus.VERIFIED,
            completed_at=completed_at,
        )
    except AIProviderConfigIOError as exception:
        raise LLMRuntimeError(
            code=LLMRuntimeErrorCode.UNKNOWN,
            provider=checked_provider,
            operation=LLMOperation.TEST_CONNECTION,
            message="Provider check succeeded, but verification write-back failed locally.",
            verification_writeback_error="verification write-back failed locally",
        ) from exception

    return LLMConnectionTestResult(
        provider=checked_provider,
        completed_at=completed_at,
        verification_writeback_applied=applied,
    )


def _validate_completion_request(
    request: object,
    provider: str,
) -> tuple[dict[str, str], ...]:
    if not isinstance(request, LLMCompletionRequest):
        raise _runtime_error(
            code=LLMRuntimeErrorCode.INVALID_REQUEST,
            provider=provider,
            operation=LLMOperation.COMPLETE,
        )

    messages = request.messages
    if not isinstance(messages, tuple) or not messages:
        raise _runtime_error(
            code=LLMRuntimeErrorCode.INVALID_REQUEST,
            provider=provider,
            operation=LLMOperation.COMPLETE,
        )

    normalized: list[dict[str, str]] = []
    for message in messages:
        if (
            not isinstance(message, LLMMessage)
            or not isinstance(message.role, LLMMessageRole)
            or not isinstance(message.content, str)
            or not message.content.strip()
        ):
            raise _runtime_error(
                code=LLMRuntimeErrorCode.INVALID_REQUEST,
                provider=provider,
                operation=LLMOperation.COMPLETE,
            )
        normalized.append(
            {
                "role": message.role.value,
                "content": message.content,
            }
        )
    return tuple(normalized)


def _usable_token_count(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _completion_result(response: Any, config: AIProviderConfig) -> LLMCompletionResult:
    try:
        choices = response.choices
        first_choice = choices[0]
        content = first_choice.message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exception:
        raise _runtime_error(
            code=LLMRuntimeErrorCode.MALFORMED_RESPONSE,
            provider=config.provider,
            operation=LLMOperation.COMPLETE,
        ) from exception

    if not isinstance(content, str) or not content.strip():
        raise _runtime_error(
            code=LLMRuntimeErrorCode.MALFORMED_RESPONSE,
            provider=config.provider,
            operation=LLMOperation.COMPLETE,
        )

    model = getattr(response, "model", None)
    usage = getattr(response, "usage", None)
    return LLMCompletionResult(
        content=content,
        provider=config.provider,
        model=model if isinstance(model, str) and model else config.model,
        input_tokens=_usable_token_count(getattr(usage, "prompt_tokens", None)),
        output_tokens=_usable_token_count(getattr(usage, "completion_tokens", None)),
        total_tokens=_usable_token_count(getattr(usage, "total_tokens", None)),
        finish_reason=(
            first_choice.finish_reason
            if isinstance(getattr(first_choice, "finish_reason", None), str)
            else None
        ),
        request_id=(
            _nonempty_string(getattr(response, "id", None))
            or _nonempty_string(getattr(response, "_request_id", None))
        ),
    )


def complete(
    config: AIProviderConfig,
    request: LLMCompletionRequest,
) -> LLMCompletionResult:
    """Perform one non-streaming chat completion using the configured model."""

    ready_config = _validate_config(config, LLMOperation.COMPLETE)
    normalized_messages = _validate_completion_request(request, ready_config.provider)
    try:
        response = _new_client(ready_config).chat.completions.create(
            model=ready_config.model,
            messages=list(normalized_messages),
            stream=False,
        )
    except OpenAIError as exception:
        raise _normalize_openai_error(
            exception,
            provider=ready_config.provider,
            operation=LLMOperation.COMPLETE,
        ) from exception
    return _completion_result(response, ready_config)
