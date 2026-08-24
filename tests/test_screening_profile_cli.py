from contextlib import redirect_stdout
import inspect
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
import uuid

import screening_profile_cli as cli
from screening_profile import (
    ScreeningProfileIOError,
    ScreeningProfileStore,
)


class ScreeningProfileCliTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.store = ScreeningProfileStore(
            Path(self.temporary_directory.name) / "screening_profiles"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _run_cli(self, store, inputs):
        output = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs) as input_mock,
            redirect_stdout(output),
        ):
            prepared = cli.run_screening_profile_configuration(store)
        return prepared, output.getvalue(), input_mock

    def _new_saved_profile(self, *criterion_texts):
        draft = self.store.create_draft()
        for criterion_text in criterion_texts:
            self.store.add_criterion(draft, criterion_text)
        return self.store.save_draft(draft)

    def _run_draft_editor(self, store, inputs, *, screening_profile_id=None):
        output = io.StringIO()
        with (
            patch("builtins.input", side_effect=inputs),
            redirect_stdout(output),
        ):
            version = cli.run_screening_profile_draft_editor(
                store,
                screening_profile_id=screening_profile_id,
            )
        return version, output.getvalue()

    def test_list_profiles_and_latest_versions(self):
        first = self._new_saved_profile("first")
        second = self._new_saved_profile("second")

        prepared, output, _ = self._run_cli(self.store, ["1", "0"])

        self.assertIsNone(prepared)
        self.assertIn(first.screening_profile_id, output)
        self.assertIn(second.screening_profile_id, output)
        self.assertEqual(output.count("latest v1"), 2)

    def test_create_add_edit_delete_show_save_and_prepare_lifecycle(self):
        profile_id = "sp_" + "1" * 32
        inputs = [
            "2",
            "4",
            "original text",
            "4",
            "delete this",
            "5",
            "C001",
            "edited text",
            "6",
            "C002",
            "7",
            "8",
            "9",
            profile_id,
        ]
        with patch(
            "screening_profile.uuid.uuid4",
            return_value=uuid.UUID(hex="1" * 32),
        ):
            prepared, output, _ = self._run_cli(self.store, inputs)

        saved = self.store.load_latest(profile_id)
        self.assertEqual(prepared, profile_id)
        self.assertEqual(
            [(criterion.criterion_id, criterion.criterion_text) for criterion in saved.criteria],
            [("C001", "edited text")],
        )
        self.assertIn("Created new Profile Draft", output)
        self.assertIn("Added Criterion C001.", output)
        self.assertIn("Updated Criterion C001.", output)
        self.assertIn("Deleted Criterion C002.", output)
        self.assertIn("C001: edited text [must_match]", output)
        self.assertIn("Saved Profile {0} v1".format(profile_id), output)
        self.assertIn("Prepared Profile {0}".format(profile_id), output)

    def test_existing_profile_edit_uses_latest_only_without_version_prompt(self):
        version_one = self._new_saved_profile("first")
        update = self.store.create_draft_from_latest(version_one.screening_profile_id)
        self.store.add_criterion(update, "second")
        version_two = self.store.save_draft(update)

        with patch.object(
            self.store,
            "create_draft_from_latest",
            wraps=self.store.create_draft_from_latest,
        ) as create_draft_from_latest:
            prepared, output, input_mock = self._run_cli(
                self.store,
                ["3", version_one.screening_profile_id, "7", "0"],
            )

        prompts = [call.args[0] for call in input_mock.call_args_list]
        self.assertIsNone(prepared)
        create_draft_from_latest.assert_called_once_with(version_one.screening_profile_id)
        self.assertIn("Editing latest v2", output)
        self.assertEqual(version_two.profile_version, 2)
        self.assertTrue(all("version" not in prompt.lower() for prompt in prompts))
        self.assertNotIn("load_version", inspect.getsource(cli))

    def test_no_op_save_reports_that_no_new_version_was_created(self):
        version_one = self._new_saved_profile("unchanged")

        prepared, output, _ = self._run_cli(
            self.store,
            ["3", version_one.screening_profile_id, "8", "0"],
        )

        self.assertIsNone(prepared)
        self.assertIn("No content changes; no new Version was created.", output)
        self.assertEqual(
            self.store.list_versions(version_one.screening_profile_id),
            (1,),
        )

    def test_invalid_input_and_store_error_remain_in_configuration_mode(self):
        prepared, output, input_mock = self._run_cli(
            self.store,
            ["unexpected", "4", "0"],
        )

        self.assertIsNone(prepared)
        self.assertIn("Invalid action.", output)
        self.assertIn("No current Draft.", output)
        self.assertEqual(input_mock.call_count, 3)

        broken_store = Mock(spec=ScreeningProfileStore)
        broken_store.list_profile_ids.side_effect = ScreeningProfileIOError("read failed")
        prepared, output, input_mock = self._run_cli(broken_store, ["1", "0"])

        self.assertIsNone(prepared)
        self.assertIn("Cannot list Profiles: read failed", output)
        self.assertEqual(input_mock.call_count, 2)
        self.assertEqual(output.count("ScreeningProfile Configuration"), 2)

    def test_configuration_cli_has_no_llm_candidate_or_page_action_path(self):
        source = inspect.getsource(cli).lower()

        for forbidden_name in (
            "llm_provider_runtime",
            "favorite",
            "forward",
            "ocr_candidate",
            "simple_brush",
        ):
            self.assertNotIn(forbidden_name, source)

    def test_draft_editor_returns_the_exact_newly_saved_version(self):
        version, output = self._run_draft_editor(
            self.store,
            ["4", "Python", "8"],
        )

        self.assertIsNotNone(version)
        self.assertEqual(version.profile_version, 1)
        self.assertEqual(
            self.store.load_version(
                version.screening_profile_id,
                version.profile_version,
            ),
            version,
        )
        self.assertIn("Saved Profile", output)

    def test_draft_editor_uses_latest_only_and_no_op_save_returns_none(self):
        version_one = self._new_saved_profile("first")

        with patch.object(
            self.store,
            "create_draft_from_latest",
            wraps=self.store.create_draft_from_latest,
        ) as create_draft_from_latest:
            version, output = self._run_draft_editor(
                self.store,
                ["8"],
                screening_profile_id=version_one.screening_profile_id,
            )

        self.assertIsNone(version)
        create_draft_from_latest.assert_called_once_with(version_one.screening_profile_id)
        self.assertIn("No content changes; no new Version was created.", output)


if __name__ == "__main__":
    unittest.main()
