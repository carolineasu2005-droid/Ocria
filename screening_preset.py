"""AM7-R15 ScreeningPreset values and local configuration persistence."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_SCREENING_PRESET_STATE_PATH = Path("data") / "screening_presets.json"

_ROOT_KEYS = {"presets", "last_used_run_settings"}
_PRESET_KEYS = {
    "preset_name",
    "screening_profile_id",
    "profile_version",
    "screening_rule_expressions",
}
_LAST_USED_KEYS = {
    "last_used_preset_name",
    "last_action_mode",
    "last_duration_seconds",
    "last_no_forward",
    "last_batch_filter_enabled",
}


class ScreeningPresetValidationError(ValueError):
    """Raised when R15 Preset state violates its formal contract."""


class ScreeningPresetIOError(RuntimeError):
    """Raised when R15 Preset state cannot be read or written."""


def _canonical_name(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ScreeningPresetValidationError(f"{field_name} must be a string.")
    canonical = value.strip()
    if not canonical:
        raise ScreeningPresetValidationError(f"{field_name} must not be blank.")
    return canonical


@dataclass(frozen=True)
class ScreeningPreset:
    preset_name: str
    screening_profile_id: str
    profile_version: int
    screening_rule_expressions: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "preset_name",
            _canonical_name(self.preset_name, "preset_name"),
        )
        if (
            not isinstance(self.screening_profile_id, str)
            or not self.screening_profile_id
        ):
            raise ScreeningPresetValidationError(
                "screening_profile_id must be a non-empty string."
            )
        if (
            isinstance(self.profile_version, bool)
            or not isinstance(self.profile_version, int)
            or self.profile_version <= 0
        ):
            raise ScreeningPresetValidationError(
                "profile_version must be a positive non-bool integer."
            )
        if (
            not isinstance(self.screening_rule_expressions, tuple)
            or not self.screening_rule_expressions
        ):
            raise ScreeningPresetValidationError(
                "screening_rule_expressions must be a non-empty tuple."
            )
        for expression in self.screening_rule_expressions:
            if not isinstance(expression, str) or not expression.strip():
                raise ScreeningPresetValidationError(
                    "screening_rule_expressions must contain non-blank strings."
                )


@dataclass(frozen=True)
class LastUsedRunSettings:
    last_used_preset_name: str
    last_action_mode: str
    last_duration_seconds: int
    last_no_forward: bool
    last_batch_filter_enabled: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "last_used_preset_name",
            _canonical_name(self.last_used_preset_name, "last_used_preset_name"),
        )
        if self.last_action_mode not in {"favorite", "forward"}:
            raise ScreeningPresetValidationError(
                "last_action_mode must be favorite or forward."
            )
        if (
            isinstance(self.last_duration_seconds, bool)
            or not isinstance(self.last_duration_seconds, int)
            or self.last_duration_seconds < 0
        ):
            raise ScreeningPresetValidationError(
                "last_duration_seconds must be a non-negative non-bool integer."
            )
        for field_name in (
            "last_no_forward",
            "last_batch_filter_enabled",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise ScreeningPresetValidationError(
                    f"{field_name} must be a bool."
                )


def _preset_to_mapping(preset: ScreeningPreset) -> dict[str, object]:
    return {
        "preset_name": preset.preset_name,
        "screening_profile_id": preset.screening_profile_id,
        "profile_version": preset.profile_version,
        "screening_rule_expressions": list(preset.screening_rule_expressions),
    }


def _preset_from_mapping(value: object) -> ScreeningPreset:
    if not isinstance(value, Mapping) or set(value) != _PRESET_KEYS:
        raise ScreeningPresetValidationError(
            "each Preset must contain exactly the formal fields."
        )
    expressions = value["screening_rule_expressions"]
    if not isinstance(expressions, list):
        raise ScreeningPresetValidationError(
            "screening_rule_expressions must be a JSON array."
        )
    return ScreeningPreset(
        preset_name=value["preset_name"],
        screening_profile_id=value["screening_profile_id"],
        profile_version=value["profile_version"],
        screening_rule_expressions=tuple(expressions),
    )


def _last_used_to_mapping(settings: LastUsedRunSettings) -> dict[str, object]:
    return {
        "last_used_preset_name": settings.last_used_preset_name,
        "last_action_mode": settings.last_action_mode,
        "last_duration_seconds": settings.last_duration_seconds,
        "last_no_forward": settings.last_no_forward,
        "last_batch_filter_enabled": settings.last_batch_filter_enabled,
    }


def _last_used_from_mapping(value: object) -> LastUsedRunSettings | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != _LAST_USED_KEYS:
        raise ScreeningPresetValidationError(
            "last_used_run_settings must contain exactly the formal fields."
        )
    return LastUsedRunSettings(
        last_used_preset_name=value["last_used_preset_name"],
        last_action_mode=value["last_action_mode"],
        last_duration_seconds=value["last_duration_seconds"],
        last_no_forward=value["last_no_forward"],
        last_batch_filter_enabled=value["last_batch_filter_enabled"],
    )


class ScreeningPresetStore:
    """The one dedicated R15 Preset and last-used-state store."""

    def __init__(self, path: Path = DEFAULT_SCREENING_PRESET_STATE_PATH) -> None:
        self.path = Path(path)

    def _load_state(self) -> tuple[tuple[ScreeningPreset, ...], object]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return (), None
        except OSError as exc:
            raise ScreeningPresetIOError("unable to read ScreeningPreset state.") from exc
        except UnicodeDecodeError as exc:
            raise ScreeningPresetValidationError(
                "ScreeningPreset state is not valid UTF-8 JSON."
            ) from exc

        try:
            state = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ScreeningPresetValidationError(
                "ScreeningPreset state is not valid JSON."
            ) from exc
        if not isinstance(state, Mapping) or set(state) != _ROOT_KEYS:
            raise ScreeningPresetValidationError(
                "ScreeningPreset state root must contain exactly presets and last_used_run_settings."
            )
        raw_presets = state["presets"]
        if not isinstance(raw_presets, list):
            raise ScreeningPresetValidationError("presets must be a JSON array.")
        presets = tuple(_preset_from_mapping(value) for value in raw_presets)
        names = [preset.preset_name for preset in presets]
        if len(names) != len(set(names)):
            raise ScreeningPresetValidationError("Preset names must be unique.")
        return tuple(sorted(presets, key=lambda preset: preset.preset_name)), state[
            "last_used_run_settings"
        ]

    def _write_state(
        self,
        presets: tuple[ScreeningPreset, ...],
        raw_last_used: object,
    ) -> None:
        state = {
            "presets": [
                _preset_to_mapping(preset)
                for preset in sorted(presets, key=lambda preset: preset.preset_name)
            ],
            "last_used_run_settings": raw_last_used,
        }
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary_path, self.path)
        except OSError as exc:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ScreeningPresetIOError("unable to write ScreeningPreset state.") from exc

    def list_presets(self) -> tuple[ScreeningPreset, ...]:
        presets, _raw_last_used = self._load_state()
        return presets

    def get_preset(self, preset_name: str) -> ScreeningPreset:
        canonical_name = _canonical_name(preset_name, "preset_name")
        for preset in self.list_presets():
            if preset.preset_name == canonical_name:
                return preset
        raise ScreeningPresetValidationError("ScreeningPreset was not found.")

    def create_preset(self, preset: ScreeningPreset) -> None:
        if not isinstance(preset, ScreeningPreset):
            raise ScreeningPresetValidationError("preset must be a ScreeningPreset.")
        presets, raw_last_used = self._load_state()
        if any(item.preset_name == preset.preset_name for item in presets):
            raise ScreeningPresetValidationError("Preset name already exists.")
        self._write_state((*presets, preset), raw_last_used)

    def replace_preset(
        self,
        current_name: str,
        replacement: ScreeningPreset,
    ) -> None:
        canonical_current_name = _canonical_name(current_name, "current_name")
        if not isinstance(replacement, ScreeningPreset):
            raise ScreeningPresetValidationError("replacement must be a ScreeningPreset.")
        presets, raw_last_used = self._load_state()
        if not any(item.preset_name == canonical_current_name for item in presets):
            raise ScreeningPresetValidationError("ScreeningPreset was not found.")
        if (
            replacement.preset_name != canonical_current_name
            and any(item.preset_name == replacement.preset_name for item in presets)
        ):
            raise ScreeningPresetValidationError("Preset name already exists.")
        replacement_presets = tuple(
            replacement if item.preset_name == canonical_current_name else item
            for item in presets
        )
        try:
            last_used = _last_used_from_mapping(raw_last_used)
        except ScreeningPresetValidationError:
            # Preset mutation must retain malformed last-used JSON unchanged.
            last_used = None
        replacement_last_used: object = raw_last_used
        if last_used is not None and last_used.last_used_preset_name == canonical_current_name:
            replacement_last_used = _last_used_to_mapping(
                LastUsedRunSettings(
                    last_used_preset_name=replacement.preset_name,
                    last_action_mode=last_used.last_action_mode,
                    last_duration_seconds=last_used.last_duration_seconds,
                    last_no_forward=last_used.last_no_forward,
                    last_batch_filter_enabled=last_used.last_batch_filter_enabled,
                )
            )
        self._write_state(replacement_presets, replacement_last_used)

    def delete_preset(self, preset_name: str) -> None:
        canonical_name = _canonical_name(preset_name, "preset_name")
        presets, raw_last_used = self._load_state()
        if not any(item.preset_name == canonical_name for item in presets):
            raise ScreeningPresetValidationError("ScreeningPreset was not found.")
        remaining_presets = tuple(
            item for item in presets if item.preset_name != canonical_name
        )
        try:
            last_used = _last_used_from_mapping(raw_last_used)
        except ScreeningPresetValidationError:
            # Preset mutation must retain malformed last-used JSON unchanged.
            last_used = None
        replacement_last_used: object = raw_last_used
        if last_used is not None and last_used.last_used_preset_name == canonical_name:
            replacement_last_used = None
        self._write_state(remaining_presets, replacement_last_used)

    def load_last_used(self) -> LastUsedRunSettings | None:
        _presets, raw_last_used = self._load_state()
        return _last_used_from_mapping(raw_last_used)

    def save_last_used(self, settings: LastUsedRunSettings) -> None:
        if not isinstance(settings, LastUsedRunSettings):
            raise ScreeningPresetValidationError(
                "settings must be a LastUsedRunSettings."
            )
        presets, _raw_last_used = self._load_state()
        if not any(
            preset.preset_name == settings.last_used_preset_name for preset in presets
        ):
            raise ScreeningPresetValidationError(
                "last-used Preset was not found."
            )
        self._write_state(presets, _last_used_to_mapping(settings))
