"""Immutable ScreeningProfile versions and their in-memory drafts."""

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Any, Mapping, Sequence


RULE_MUST_MATCH = "must_match"
DEFAULT_SCREENING_PROFILE_ROOT = Path("data") / "screening_profiles"

_CRITERION_ID_PATTERN = re.compile(r"C([0-9]{3,})\Z")
_PROFILE_ID_PATTERN = re.compile(r"sp_[0-9a-f]{32}\Z")
_VERSION_FILENAME_PATTERN = re.compile(r"([1-9][0-9]*)\.json\Z")


class ScreeningProfileValidationError(ValueError):
    """Raised when ScreeningProfile data violates its formal contract."""


class ScreeningProfileIOError(RuntimeError):
    """Raised when ScreeningProfile persistence encounters an I/O failure."""


def _require_exact_keys(
    data: Mapping[str, Any],
    expected_keys: set[str],
    object_name: str,
) -> None:
    if not isinstance(data, Mapping) or set(data) != expected_keys:
        raise ScreeningProfileValidationError(
            "{0} must contain exactly the formal fields.".format(object_name)
        )


def _numeric_criterion_id(criterion_id: str) -> int:
    if not isinstance(criterion_id, str):
        raise ScreeningProfileValidationError("criterion_id must be a string.")
    match = _CRITERION_ID_PATTERN.fullmatch(criterion_id)
    if match is None:
        raise ScreeningProfileValidationError(
            "criterion_id must be C followed by at least three decimal digits."
        )
    number = int(match.group(1))
    if number <= 0:
        raise ScreeningProfileValidationError("criterion_id number must be positive.")
    return number


def _validate_profile_id(screening_profile_id: str) -> None:
    if (
        not isinstance(screening_profile_id, str)
        or _PROFILE_ID_PATTERN.fullmatch(screening_profile_id) is None
    ):
        raise ScreeningProfileValidationError(
            "screening_profile_id must match sp_ followed by 32 lowercase hex digits."
        )


def _validate_profile_version(profile_version: int) -> None:
    if (
        isinstance(profile_version, bool)
        or not isinstance(profile_version, int)
        or profile_version <= 0
    ):
        raise ScreeningProfileValidationError(
            "profile_version must be a positive non-bool integer."
        )


def _validate_created_at(created_at: str) -> None:
    if not isinstance(created_at, str):
        raise ScreeningProfileValidationError(
            "created_at must be a timezone-aware ISO 8601 string."
        )
    try:
        parsed = datetime.fromisoformat(created_at)
    except ValueError as exc:
        raise ScreeningProfileValidationError(
            "created_at must be a timezone-aware ISO 8601 string."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScreeningProfileValidationError(
            "created_at must be a timezone-aware ISO 8601 string."
        )


@dataclass(frozen=True)
class Criterion:
    criterion_id: str
    criterion_text: str
    rule: str = RULE_MUST_MATCH

    def __post_init__(self) -> None:
        _numeric_criterion_id(self.criterion_id)
        if (
            not isinstance(self.criterion_text, str)
            or not self.criterion_text
            or self.criterion_text.isspace()
        ):
            raise ScreeningProfileValidationError(
                "criterion_text must be a non-empty, non-whitespace string."
            )
        if self.rule != RULE_MUST_MATCH:
            raise ScreeningProfileValidationError(
                "rule must be exactly {0}.".format(RULE_MUST_MATCH)
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "criterion_id": self.criterion_id,
            "criterion_text": self.criterion_text,
            "rule": self.rule,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Criterion":
        _require_exact_keys(
            data,
            {"criterion_id", "criterion_text", "rule"},
            "Criterion",
        )
        return cls(
            criterion_id=data["criterion_id"],
            criterion_text=data["criterion_text"],
            rule=data["rule"],
        )


def criteria_digest(criteria: Sequence[Criterion]) -> str:
    """Return the frozen R05 SHA-256 digest for Criterion semantic content."""

    validated_criteria = tuple(criteria)
    for criterion in validated_criteria:
        if not isinstance(criterion, Criterion):
            raise ScreeningProfileValidationError("criteria must contain Criterion objects.")

    canonical = [
        {
            "criterion_id": criterion.criterion_id,
            "criterion_text": criterion.criterion_text,
            "rule": criterion.rule,
        }
        for criterion in sorted(
            validated_criteria,
            key=lambda criterion: _numeric_criterion_id(criterion.criterion_id),
        )
    ]
    payload = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ScreeningProfileVersion:
    screening_profile_id: str
    profile_version: int
    criteria: tuple[Criterion, ...]
    criteria_digest: str
    created_at: str

    def __post_init__(self) -> None:
        _validate_profile_id(self.screening_profile_id)
        _validate_profile_version(self.profile_version)
        if not isinstance(self.criteria, tuple) or not self.criteria:
            raise ScreeningProfileValidationError(
                "criteria must be a non-empty tuple of Criterion objects."
            )
        if not all(isinstance(criterion, Criterion) for criterion in self.criteria):
            raise ScreeningProfileValidationError(
                "criteria must contain Criterion objects."
            )
        criterion_ids = [criterion.criterion_id for criterion in self.criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ScreeningProfileValidationError(
                "criterion_id values must be unique within a formal Version."
            )
        expected_digest = criteria_digest(self.criteria)
        if self.criteria_digest != expected_digest:
            raise ScreeningProfileValidationError(
                "criteria_digest does not match the formal criteria."
            )
        _validate_created_at(self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return {
            "screening_profile_id": self.screening_profile_id,
            "profile_version": self.profile_version,
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "criteria_digest": self.criteria_digest,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScreeningProfileVersion":
        _require_exact_keys(
            data,
            {
                "screening_profile_id",
                "profile_version",
                "criteria",
                "criteria_digest",
                "created_at",
            },
            "ScreeningProfileVersion",
        )
        raw_criteria = data["criteria"]
        if not isinstance(raw_criteria, list):
            raise ScreeningProfileValidationError("criteria must be a JSON array.")
        return cls(
            screening_profile_id=data["screening_profile_id"],
            profile_version=data["profile_version"],
            criteria=tuple(Criterion.from_dict(item) for item in raw_criteria),
            criteria_digest=data["criteria_digest"],
            created_at=data["created_at"],
        )


@dataclass
class ScreeningProfileDraft:
    screening_profile_id: str
    base_profile_version: int | None
    criteria: list[Criterion]


class ScreeningProfileStore:
    """Persistence and latest-only Draft operations for ScreeningProfiles."""

    def __init__(self, root: Path = DEFAULT_SCREENING_PROFILE_ROOT) -> None:
        self.root = Path(root)

    def list_profile_ids(self) -> tuple[str, ...]:
        try:
            if not self.root.exists():
                return ()
            if not self.root.is_dir():
                raise ScreeningProfileValidationError(
                    "screening profile root must be a directory."
                )
            profile_ids = [
                entry.name
                for entry in self.root.iterdir()
                if entry.is_dir()
                and _PROFILE_ID_PATTERN.fullmatch(entry.name) is not None
            ]
        except OSError as exc:
            raise ScreeningProfileIOError(
                "unable to list screening profile IDs."
            ) from exc
        return tuple(sorted(profile_ids))

    def list_versions(self, screening_profile_id: str) -> tuple[int, ...]:
        _validate_profile_id(screening_profile_id)
        profile_dir = self.root / screening_profile_id
        versions_dir = profile_dir / "versions"
        try:
            if not profile_dir.exists():
                return ()
            if not profile_dir.is_dir() or not versions_dir.exists() or not versions_dir.is_dir():
                raise ScreeningProfileValidationError(
                    "screening profile history is missing or invalid."
                )
            version_numbers: list[int] = []
            for entry in versions_dir.iterdir():
                if not entry.is_file():
                    continue
                if entry.suffix != ".json":
                    continue
                match = _VERSION_FILENAME_PATTERN.fullmatch(entry.name)
                if match is None:
                    raise ScreeningProfileValidationError(
                        "screening profile version filename is invalid."
                    )
                version_numbers.append(int(match.group(1)))
        except OSError as exc:
            raise ScreeningProfileIOError(
                "unable to list screening profile versions."
            ) from exc

        versions = tuple(sorted(version_numbers))
        if versions != tuple(range(1, len(versions) + 1)):
            raise ScreeningProfileValidationError(
                "screening profile version history must be contiguous from 1."
            )
        return versions

    def load_version(
        self,
        screening_profile_id: str,
        profile_version: int,
    ) -> ScreeningProfileVersion:
        _validate_profile_id(screening_profile_id)
        _validate_profile_version(profile_version)
        versions = self.list_versions(screening_profile_id)
        if not versions:
            raise ScreeningProfileValidationError("screening profile was not found.")
        if profile_version not in versions:
            raise ScreeningProfileValidationError(
                "screening profile version was not found."
            )

        path = self._version_path(screening_profile_id, profile_version)
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except OSError as exc:
            raise ScreeningProfileIOError(
                "unable to read screening profile version."
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ScreeningProfileValidationError(
                "screening profile version JSON is invalid."
            ) from exc

        if not isinstance(data, Mapping):
            raise ScreeningProfileValidationError(
                "screening profile version JSON must be an object."
            )
        version = ScreeningProfileVersion.from_dict(data)
        if version.screening_profile_id != screening_profile_id:
            raise ScreeningProfileValidationError(
                "screening profile ID does not match its storage path."
            )
        if version.profile_version != profile_version:
            raise ScreeningProfileValidationError(
                "screening profile version does not match its storage path."
            )
        return version

    def load_latest(self, screening_profile_id: str) -> ScreeningProfileVersion:
        versions = self.list_versions(screening_profile_id)
        if not versions:
            raise ScreeningProfileValidationError("screening profile was not found.")
        return self.load_version(screening_profile_id, versions[-1])

    def create_draft(self) -> ScreeningProfileDraft:
        return ScreeningProfileDraft(
            screening_profile_id="sp_" + uuid.uuid4().hex,
            base_profile_version=None,
            criteria=[],
        )

    def create_draft_from_latest(
        self,
        screening_profile_id: str,
    ) -> ScreeningProfileDraft:
        latest = self.load_latest(screening_profile_id)
        return ScreeningProfileDraft(
            screening_profile_id=latest.screening_profile_id,
            base_profile_version=latest.profile_version,
            criteria=list(latest.criteria),
        )

    def next_criterion_id(self, draft: ScreeningProfileDraft) -> str:
        self._validate_draft(draft)
        used_numbers = {
            _numeric_criterion_id(criterion.criterion_id)
            for criterion in draft.criteria
        }
        for version_number in self.list_versions(draft.screening_profile_id):
            version = self.load_version(
                draft.screening_profile_id,
                version_number,
            )
            used_numbers.update(
                _numeric_criterion_id(criterion.criterion_id)
                for criterion in version.criteria
            )
        next_number = max(used_numbers) + 1 if used_numbers else 1
        return "C{0:03d}".format(next_number)

    def add_criterion(
        self,
        draft: ScreeningProfileDraft,
        criterion_text: str,
    ) -> Criterion:
        criterion = Criterion(
            criterion_id=self.next_criterion_id(draft),
            criterion_text=criterion_text,
        )
        draft.criteria.append(criterion)
        return criterion

    def edit_criterion(
        self,
        draft: ScreeningProfileDraft,
        criterion_id: str,
        criterion_text: str,
    ) -> Criterion:
        self._validate_draft(draft)
        _numeric_criterion_id(criterion_id)
        for index, criterion in enumerate(draft.criteria):
            if criterion.criterion_id == criterion_id:
                edited = replace(criterion, criterion_text=criterion_text)
                draft.criteria[index] = edited
                return edited
        raise ScreeningProfileValidationError("criterion_id was not found in the Draft.")

    def delete_criterion(
        self,
        draft: ScreeningProfileDraft,
        criterion_id: str,
    ) -> None:
        self._validate_draft(draft)
        _numeric_criterion_id(criterion_id)
        for index, criterion in enumerate(draft.criteria):
            if criterion.criterion_id == criterion_id:
                del draft.criteria[index]
                return
        raise ScreeningProfileValidationError("criterion_id was not found in the Draft.")

    def save_draft(
        self,
        draft: ScreeningProfileDraft,
    ) -> ScreeningProfileVersion | None:
        self._validate_draft(draft)
        if not draft.criteria:
            raise ScreeningProfileValidationError(
                "a formal ScreeningProfile Version requires at least one Criterion."
            )

        versions = self.list_versions(draft.screening_profile_id)
        if draft.base_profile_version is None:
            if versions:
                raise ScreeningProfileValidationError(
                    "a new Draft cannot save over an existing screening profile."
                )
            target_version = 1
        else:
            latest = self.load_latest(draft.screening_profile_id)
            if draft.base_profile_version != latest.profile_version:
                raise ScreeningProfileValidationError(
                    "Draft base_profile_version is not the current latest version."
                )
            if tuple(draft.criteria) == latest.criteria:
                return None
            target_version = latest.profile_version + 1

        version = ScreeningProfileVersion(
            screening_profile_id=draft.screening_profile_id,
            profile_version=target_version,
            criteria=tuple(draft.criteria),
            criteria_digest=criteria_digest(draft.criteria),
            created_at=datetime.now().astimezone().isoformat(),
        )
        self._write_version(version)
        return version

    def _version_path(
        self,
        screening_profile_id: str,
        profile_version: int,
    ) -> Path:
        return self.root / screening_profile_id / "versions" / "{0}.json".format(
            profile_version
        )

    def _validate_draft(self, draft: ScreeningProfileDraft) -> None:
        if not isinstance(draft, ScreeningProfileDraft):
            raise ScreeningProfileValidationError(
                "draft must be a ScreeningProfileDraft."
            )
        _validate_profile_id(draft.screening_profile_id)
        if draft.base_profile_version is not None:
            _validate_profile_version(draft.base_profile_version)
        if not isinstance(draft.criteria, list):
            raise ScreeningProfileValidationError(
                "Draft criteria must be a mutable list of Criterion objects."
            )
        if not all(isinstance(criterion, Criterion) for criterion in draft.criteria):
            raise ScreeningProfileValidationError(
                "Draft criteria must contain Criterion objects."
            )
        criterion_ids = [criterion.criterion_id for criterion in draft.criteria]
        if len(set(criterion_ids)) != len(criterion_ids):
            raise ScreeningProfileValidationError(
                "criterion_id values must be unique within a Draft."
            )

    def _write_version(self, version: ScreeningProfileVersion) -> None:
        target_path = self._version_path(
            version.screening_profile_id,
            version.profile_version,
        )
        temporary_path: Path | None = None
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=target_path.parent,
                prefix=".{0}.".format(target_path.name),
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(
                    version.to_dict(),
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.write("\n")
            if target_path.exists():
                raise ScreeningProfileIOError(
                    "screening profile version already exists and will not be overwritten."
                )
            os.replace(temporary_path, target_path)
            temporary_path = None
        except OSError as exc:
            raise ScreeningProfileIOError(
                "unable to write screening profile version."
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
