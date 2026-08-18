import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from screening_profile import (
    RULE_MUST_MATCH,
    Criterion,
    ScreeningProfileDraft,
    ScreeningProfileIOError,
    ScreeningProfileStore,
    ScreeningProfileValidationError,
    ScreeningProfileVersion,
    criteria_digest,
)


class ScreeningProfileModelTests(unittest.TestCase):
    def test_criterion_and_profile_serialization_round_trip(self):
        criterion = Criterion("C001", "具有 SLG 游戏项目经验")
        version = ScreeningProfileVersion(
            screening_profile_id="sp_" + "a" * 32,
            profile_version=1,
            criteria=(criterion,),
            criteria_digest=criteria_digest((criterion,)),
            created_at=datetime(2026, 8, 18, 12, tzinfo=timezone.utc).isoformat(),
        )

        self.assertEqual(
            criterion.to_dict(),
            {
                "criterion_id": "C001",
                "criterion_text": "具有 SLG 游戏项目经验",
                "rule": RULE_MUST_MATCH,
            },
        )
        self.assertEqual(Criterion.from_dict(criterion.to_dict()), criterion)
        self.assertEqual(ScreeningProfileVersion.from_dict(version.to_dict()), version)
        self.assertEqual(
            set(version.to_dict()),
            {
                "screening_profile_id",
                "profile_version",
                "criteria",
                "criteria_digest",
                "created_at",
            },
        )

    def test_invalid_criterion_text_and_rule_are_rejected(self):
        with self.assertRaises(ScreeningProfileValidationError):
            Criterion("C001", " \t\n")
        with self.assertRaises(ScreeningProfileValidationError):
            Criterion("C001", "valid", rule="must_not_match")

    def test_criterion_id_formatting_includes_c001_and_c1000(self):
        self.assertEqual(Criterion("C001", "first").criterion_id, "C001")
        self.assertEqual(Criterion("C1000", "one thousand").criterion_id, "C1000")
        with TemporaryDirectory() as temporary_directory:
            store = ScreeningProfileStore(Path(temporary_directory))
            draft = store.create_draft()
            draft.criteria.append(Criterion("C999", "last three-digit ID"))
            self.assertEqual(store.next_criterion_id(draft), "C1000")
        with self.assertRaises(ScreeningProfileValidationError):
            Criterion("C000", "zero is not a criterion")

    def test_formal_objects_are_frozen(self):
        criterion = Criterion("C001", "immutable")
        version = ScreeningProfileVersion(
            screening_profile_id="sp_" + "b" * 32,
            profile_version=1,
            criteria=(criterion,),
            criteria_digest=criteria_digest((criterion,)),
            created_at="2026-08-18T12:00:00+00:00",
        )

        with self.assertRaises(FrozenInstanceError):
            criterion.criterion_text = "changed"
        with self.assertRaises(FrozenInstanceError):
            version.profile_version = 2

    def test_digest_is_order_independent_and_includes_rule_fixture(self):
        first = Criterion("C001", "必须具备 Python 经验")
        second = Criterion("C010", "能进行跨团队协作")

        self.assertEqual(
            criteria_digest((second, first)),
            criteria_digest((first, second)),
        )
        self.assertEqual(
            criteria_digest((first,)),
            "sha256:6e704edb034731a5c9890e08059c4bdf0618d3893444a36560d7d3b2e9fccb04",
        )

    def test_digest_preserves_whitespace_unicode_and_changes_for_content(self):
        exact = Criterion("C001", "  中文条件\n")
        normalized_looking = Criterion("C001", "中文条件")
        added = Criterion("C002", "第二项")

        self.assertEqual(exact.criterion_text, "  中文条件\n")
        self.assertNotEqual(criteria_digest((exact,)), criteria_digest((normalized_looking,)))
        self.assertNotEqual(criteria_digest((exact,)), criteria_digest((exact, added)))
        self.assertNotEqual(criteria_digest((exact, added)), criteria_digest((exact,)))
        self.assertNotEqual(
            criteria_digest((Criterion("C001", "改写条件"),)),
            criteria_digest((exact,)),
        )


class ScreeningProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name) / "screening_profiles"
        self.store = ScreeningProfileStore(self.root)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _new_saved_profile(self, *criterion_texts):
        draft = self.store.create_draft()
        for criterion_text in criterion_texts:
            self.store.add_criterion(draft, criterion_text)
        version = self.store.save_draft(draft)
        self.assertIsNotNone(version)
        return version

    def test_new_draft_saves_version_one_and_discovers_latest(self):
        version = self._new_saved_profile("第一条")

        self.assertEqual(version.profile_version, 1)
        self.assertEqual(self.store.list_profile_ids(), (version.screening_profile_id,))
        self.assertEqual(self.store.list_versions(version.screening_profile_id), (1,))
        self.assertEqual(
            self.store.load_latest(version.screening_profile_id),
            version,
        )
        path = (
            self.root
            / version.screening_profile_id
            / "versions"
            / "1.json"
        )
        self.assertTrue(path.is_file())
        self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_latest_draft_saves_v2_and_preserves_criterion_id_on_edit(self):
        version_one = self._new_saved_profile("original", "another")
        draft = self.store.create_draft_from_latest(version_one.screening_profile_id)
        edited = self.store.edit_criterion(draft, "C001", "edited text")
        version_two = self.store.save_draft(draft)

        self.assertEqual(edited.criterion_id, "C001")
        self.assertEqual(version_two.profile_version, 2)
        self.assertEqual(
            self.store.load_version(version_one.screening_profile_id, 1),
            version_one,
        )
        self.assertEqual(version_two.criteria[0].criterion_text, "edited text")

    def test_draft_ids_must_be_unique(self):
        draft = self.store.create_draft()
        self.store.add_criterion(draft, "first")
        draft.criteria.append(Criterion("C001", "duplicate"))

        with self.assertRaises(ScreeningProfileValidationError):
            self.store.next_criterion_id(draft)

    def test_deleted_formal_id_is_not_reused_but_abandoned_draft_id_is(self):
        version_one = self._new_saved_profile("first", "second")
        deletion_draft = self.store.create_draft_from_latest(
            version_one.screening_profile_id
        )
        self.store.delete_criterion(deletion_draft, "C002")
        self.store.save_draft(deletion_draft)

        later_draft = self.store.create_draft_from_latest(
            version_one.screening_profile_id
        )
        self.assertEqual(self.store.next_criterion_id(later_draft), "C003")

        abandoned_draft = self.store.create_draft()
        allocated = self.store.add_criterion(abandoned_draft, "temporary")
        self.store.delete_criterion(abandoned_draft, allocated.criterion_id)
        self.assertEqual(
            self.store.next_criterion_id(abandoned_draft),
            allocated.criterion_id,
        )

    def test_stale_historical_base_cannot_create_branch(self):
        version_one = self._new_saved_profile("first")
        latest_draft = self.store.create_draft_from_latest(
            version_one.screening_profile_id
        )
        self.store.add_criterion(latest_draft, "second")
        version_two = self.store.save_draft(latest_draft)

        historical_draft = ScreeningProfileDraft(
            screening_profile_id=version_one.screening_profile_id,
            base_profile_version=version_one.profile_version,
            criteria=list(version_one.criteria),
        )
        with self.assertRaises(ScreeningProfileValidationError):
            self.store.save_draft(historical_draft)

        self.assertEqual(
            self.store.list_versions(version_one.screening_profile_id),
            (1, 2),
        )
        self.assertEqual(
            self.store.load_latest(version_one.screening_profile_id),
            version_two,
        )

    def test_no_op_save_returns_none_without_new_version(self):
        version_one = self._new_saved_profile("unchanged")
        draft = self.store.create_draft_from_latest(version_one.screening_profile_id)

        self.assertIsNone(self.store.save_draft(draft))
        self.assertEqual(self.store.list_versions(version_one.screening_profile_id), (1,))

    def test_restart_reloads_by_id_and_version(self):
        version_one = self._new_saved_profile("first")
        draft = self.store.create_draft_from_latest(version_one.screening_profile_id)
        self.store.edit_criterion(draft, "C001", "second")
        version_two = self.store.save_draft(draft)
        restarted_store = ScreeningProfileStore(self.root)

        self.assertEqual(
            restarted_store.load_version(
                version_one.screening_profile_id,
                version_one.profile_version,
            ),
            version_one,
        )
        self.assertEqual(
            restarted_store.load_latest(version_one.screening_profile_id),
            version_two,
        )

    def test_atomic_write_failure_preserves_existing_history(self):
        version_one = self._new_saved_profile("first")
        draft = self.store.create_draft_from_latest(version_one.screening_profile_id)
        self.store.edit_criterion(draft, "C001", "changed")

        with mock.patch(
            "screening_profile.os.replace",
            side_effect=OSError("replace denied"),
        ):
            with self.assertRaises(ScreeningProfileIOError):
                self.store.save_draft(draft)

        versions_dir = self.root / version_one.screening_profile_id / "versions"
        self.assertEqual(self.store.list_versions(version_one.screening_profile_id), (1,))
        self.assertEqual(self.store.load_latest(version_one.screening_profile_id), version_one)
        self.assertFalse((versions_dir / "2.json").exists())
        self.assertEqual(
            [path for path in versions_dir.iterdir() if path.suffix == ".tmp"],
            [],
        )

    def test_missing_gapped_and_invalid_history_are_rejected(self):
        missing_id = "sp_" + "c" * 32
        with self.assertRaises(ScreeningProfileValidationError):
            self.store.load_latest(missing_id)

        gapped_id = "sp_" + "d" * 32
        gapped_dir = self.root / gapped_id / "versions"
        gapped_dir.mkdir(parents=True)
        criterion = Criterion("C001", "valid")
        gapped_version = ScreeningProfileVersion(
            screening_profile_id=gapped_id,
            profile_version=3,
            criteria=(criterion,),
            criteria_digest=criteria_digest((criterion,)),
            created_at="2026-08-18T12:00:00+00:00",
        )
        (gapped_dir / "3.json").write_text(
            json.dumps(gapped_version.to_dict()),
            encoding="utf-8",
        )
        with self.assertRaises(ScreeningProfileValidationError):
            self.store.list_versions(gapped_id)

        invalid_id = "sp_" + "e" * 32
        invalid_dir = self.root / invalid_id / "versions"
        invalid_dir.mkdir(parents=True)
        (invalid_dir / "1.json").write_text("{invalid json", encoding="utf-8")
        with self.assertRaises(ScreeningProfileValidationError):
            self.store.load_version(invalid_id, 1)


if __name__ == "__main__":
    unittest.main()
