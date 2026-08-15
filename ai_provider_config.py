"""Local v1 AI provider configuration types and load classification."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit


AI_PROVIDER_CONFIG_VERSION = 1
DEFAULT_AI_PROVIDER_CONFIG_PATH = Path("config") / "ai_provider.json"

PROVIDER_ALIYUN_BAILIAN = "aliyun-bailian"
PROVIDER_DEEPSEEK = "deepseek"

_CONFIG_KEYS = (
    "config_version",
    "provider",
    "api_key",
    "base_url",
    "model",
    "connection_verification_status",
    "last_verification_time",
)
_RUNTIME_FIELDS = ("provider", "api_key", "base_url", "model")
_PROVIDER_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ISO_8601_OFFSET_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?[+-]\d{2}:\d{2}$"
)


class ConnectionVerificationStatus(str, Enum):
    """The latest Provider connectivity result for the current connection values."""

    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    FAILED = "failed"


class AIProviderConfigLoadStatus(str, Enum):
    """The result of interpreting the local v1 configuration file."""

    NOT_CONFIGURED = "not_configured"
    INCOMPLETE = "incomplete"
    INVALID = "invalid"
    UNSUPPORTED_VERSION = "unsupported_version"
    VALID = "valid"


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _is_valid_base_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return parsed.scheme in {"http", "https"} and parsed.hostname is not None
    except ValueError:
        return False


@dataclass(frozen=True)
class AIProviderConfig:
    """The one current AI Provider configuration, complete or incomplete."""

    config_version: int = AI_PROVIDER_CONFIG_VERSION
    provider: str = ""
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    model: str = ""
    connection_verification_status: ConnectionVerificationStatus = (
        ConnectionVerificationStatus.UNVERIFIED
    )
    last_verification_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        if type(self.config_version) is not int or self.config_version != AI_PROVIDER_CONFIG_VERSION:
            raise ValueError("config_version must be integer 1")

        for field_name in _RUNTIME_FIELDS:
            if not isinstance(getattr(self, field_name), str):
                raise ValueError(f"{field_name} must be a string")

        if self.provider and not _PROVIDER_PATTERN.fullmatch(self.provider):
            raise ValueError("provider must be lower-case kebab-case")

        if self.base_url and not _is_valid_base_url(self.base_url):
            raise ValueError("base_url must be an absolute HTTP(S) URL")

        if not isinstance(
            self.connection_verification_status, ConnectionVerificationStatus
        ):
            raise ValueError("connection_verification_status is invalid")

        if self.connection_verification_status is ConnectionVerificationStatus.UNVERIFIED:
            if self.last_verification_time is not None:
                raise ValueError(
                    "last_verification_time must be None when status is unverified"
                )
        elif not isinstance(self.last_verification_time, datetime) or not _is_timezone_aware(
            self.last_verification_time
        ):
            raise ValueError(
                "last_verification_time must be timezone-aware when status is verified or failed"
            )

    @property
    def is_complete(self) -> bool:
        return all(getattr(self, field_name) for field_name in _RUNTIME_FIELDS)

    def api_key_display(self) -> str:
        return "API Key: configured" if self.api_key else "API Key: not configured"

    def api_key_display(self) -> str:
        return "API Key: configured" if self.api_key else "API Key: not configured"


@dataclass(frozen=True)
class AIProviderConfigLoadResult:
    """A structured local configuration load result."""

    status: AIProviderConfigLoadStatus
    config: Optional[AIProviderConfig] = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, AIProviderConfigLoadStatus):
            raise ValueError("load status is invalid")
        if self.config is not None and not isinstance(self.config, AIProviderConfig):
            raise ValueError("load result config is invalid")
        if self.error is not None and not isinstance(self.error, str):
            raise ValueError("load result error is invalid")

        if self.status is AIProviderConfigLoadStatus.NOT_CONFIGURED:
            if self.config is not None or self.error is not None:
                raise ValueError("not configured result must not include config or error")
        elif self.status in {
            AIProviderConfigLoadStatus.INCOMPLETE,
            AIProviderConfigLoadStatus.VALID,
        }:
            if self.config is None or self.error is not None:
                raise ValueError("usable load result must include config and no error")
        elif self.config is not None or not self.error:
            raise ValueError("unusable load result must include only an error")


class AIProviderConfigIOError(RuntimeError):
    """A local AI Provider configuration persistence I/O failure."""


def _config_to_mapping(config: AIProviderConfig) -> dict[str, Any]:
    """Return the dedicated seven-key v1 JSON mapping for a valid config."""

    return {
        "config_version": config.config_version,
        "provider": config.provider,
        "api_key": config.api_key,
        "base_url": config.base_url,
        "model": config.model,
        "connection_verification_status": config.connection_verification_status.value,
        "last_verification_time": (
            None
            if config.last_verification_time is None
            else config.last_verification_time.isoformat()
        ),
    }


def _invalid_result(error: str) -> AIProviderConfigLoadResult:
    return AIProviderConfigLoadResult(
        status=AIProviderConfigLoadStatus.INVALID,
        error=error,
    )


def _parse_verification_time(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, str) or not _ISO_8601_OFFSET_PATTERN.fullmatch(value):
        raise ValueError("last_verification_time must include a timezone offset")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            "last_verification_time must be a valid ISO 8601 timestamp"
        ) from exc
    if not _is_timezone_aware(parsed):
        raise ValueError("last_verification_time must include a timezone offset")
    return parsed


class AIProviderConfigStore:
    """The local v1 configuration persistence and loading boundary."""

    def __init__(self, path: Path = DEFAULT_AI_PROVIDER_CONFIG_PATH) -> None:
        self.path = Path(path)

    def load(self) -> AIProviderConfigLoadResult:
        """Read and classify the current local v1 configuration without changing it."""

        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return AIProviderConfigLoadResult(
                status=AIProviderConfigLoadStatus.NOT_CONFIGURED
            )
        except OSError as exc:
            raise AIProviderConfigIOError("cannot read AI Provider configuration") from exc
        except UnicodeDecodeError:
            return _invalid_result("configuration is not valid JSON")

        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return _invalid_result("configuration is not valid JSON")

        if not isinstance(value, dict):
            return _invalid_result("configuration root must be an object")

        if "config_version" not in value or type(value["config_version"]) is not int:
            return _invalid_result("config_version must be integer 1")
        if value["config_version"] != AI_PROVIDER_CONFIG_VERSION:
            return AIProviderConfigLoadResult(
                status=AIProviderConfigLoadStatus.UNSUPPORTED_VERSION,
                error=f"unsupported config_version: {value['config_version']}",
            )

        if set(value) - set(_CONFIG_KEYS):
            return _invalid_result("unknown configuration field")

        if "connection_verification_status" not in value:
            return _invalid_result("connection_verification_status is required")
        if "last_verification_time" not in value:
            return _invalid_result("last_verification_time is required")

        status_value = value["connection_verification_status"]
        if not isinstance(status_value, str):
            return _invalid_result("connection_verification_status is invalid")
        try:
            verification_status = ConnectionVerificationStatus(status_value)
        except ValueError:
            return _invalid_result("connection_verification_status is invalid")

        try:
            verification_time = _parse_verification_time(
                value["last_verification_time"]
            )
        except ValueError as exc:
            return _invalid_result(str(exc))

        runtime_values: dict[str, str] = {}
        for field_name in _RUNTIME_FIELDS:
            field_value = value.get(field_name, "")
            if not isinstance(field_value, str):
                return _invalid_result(f"{field_name} must be a string")
            runtime_values[field_name] = field_value

        try:
            config = AIProviderConfig(
                config_version=value["config_version"],
                provider=runtime_values["provider"],
                api_key=runtime_values["api_key"],
                base_url=runtime_values["base_url"],
                model=runtime_values["model"],
                connection_verification_status=verification_status,
                last_verification_time=verification_time,
            )
        except ValueError as exc:
            return _invalid_result(str(exc))

        return AIProviderConfigLoadResult(
            status=(
                AIProviderConfigLoadStatus.VALID
                if config.is_complete
                else AIProviderConfigLoadStatus.INCOMPLETE
            ),
            config=config,
        )

    def save(self, config: AIProviderConfig) -> Path:
        """Atomically replace the local configuration with a complete JSON document."""

        if not isinstance(config, AIProviderConfig):
            raise ValueError("config must be an AIProviderConfig")

        serialized = json.dumps(
            _config_to_mapping(config),
            ensure_ascii=False,
            indent=2,
        ) + "\n"

        temporary_path: Optional[Path] = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                delete=False,
                dir=self.path.parent,
                prefix=".ai_provider.",
                suffix=".tmp",
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(serialized)
            os.replace(temporary_path, self.path)
        except OSError as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
            raise AIProviderConfigIOError("cannot save AI Provider configuration") from exc

        return self.path

    def update(
        self,
        current: AIProviderConfig,
        *,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> AIProviderConfig:
        """Persist a replacement config and invalidate connectivity when it changes."""

        if not isinstance(current, AIProviderConfig):
            raise ValueError("current config must be an AIProviderConfig")

        proposed_values = {
            "provider": current.provider if provider is None else provider,
            "api_key": current.api_key if api_key is None else api_key,
            "base_url": current.base_url if base_url is None else base_url,
            "model": current.model if model is None else model,
        }
        connection_changed = any(
            proposed_values[field_name] != getattr(current, field_name)
            for field_name in ("provider", "api_key", "base_url")
        )

        proposed = AIProviderConfig(
            provider=proposed_values["provider"],
            api_key=proposed_values["api_key"],
            base_url=proposed_values["base_url"],
            model=proposed_values["model"],
            connection_verification_status=(
                ConnectionVerificationStatus.UNVERIFIED
                if connection_changed
                else current.connection_verification_status
            ),
            last_verification_time=(
                None if connection_changed else current.last_verification_time
            ),
        )
        self.save(proposed)
        return proposed

    def record_connection_verification(
        self,
        *,
        checked_provider: str,
        checked_api_key: str,
        checked_base_url: str,
        status: ConnectionVerificationStatus,
        completed_at: datetime,
    ) -> bool:
        """Apply a matching R03 connectivity result without performing network I/O."""

        if status not in {
            ConnectionVerificationStatus.VERIFIED,
            ConnectionVerificationStatus.FAILED,
        }:
            raise ValueError("verification status must be verified or failed")
        if not isinstance(completed_at, datetime) or not _is_timezone_aware(completed_at):
            raise ValueError("completed_at must be a timezone-aware datetime")

        result = self.load()
        if result.status not in {
            AIProviderConfigLoadStatus.INCOMPLETE,
            AIProviderConfigLoadStatus.VALID,
        } or result.config is None:
            return False

        current = result.config
        if not all((current.provider, current.api_key, current.base_url)):
            return False
        if (
            current.provider != checked_provider
            or current.api_key != checked_api_key
            or current.base_url != checked_base_url
        ):
            return False

        self.save(
            replace(
                current,
                connection_verification_status=status,
                last_verification_time=completed_at,
            )
        )
        return True
