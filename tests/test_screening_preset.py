"""Focused AM7-R15 Preset persistence tests."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from screening_preset import (
    LastUsedRunSettings,
    ScreeningPreset,
    ScreeningPresetIOError,
    ScreeningPresetStore,
    ScreeningPresetValidationError,
)


class ScreeningPresetStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "data" / "screening_presets.json"
        self.store = ScreeningPresetStore(self.path)
        self.preset = ScreeningPreset(
            preset_name="  UI组长-SLG  ",
            screening_profile_id="sp_0123456789abcdef0123456789abcdef",
            profile_version=1,
            screening_rule_expressions=("C001 AND C002",),
        )

    def last_used(self, name="UI组长-SLG"):
        return LastUsedRunSettings(
            last_used_preset_name=name,
            last_action_mode="forward",
            last_duration_seconds=0,
            last_no_forward=True,
            last_batch_filter_enabled=False,
        )

    def test_create_persists_canonical_preset_in_strict_json(self):
        self.store.create_preset(self.preset)

        self.assertEqual(self.preset.preset_name, "UI组长-SLG")
        self.assertEqual(self.store.list_presets(), (self.preset,))
        self.assertEqual(ScreeningPresetStore(self.path).get_preset(" UI组长-SLG "), self.preset)
        self.assertIsNone(self.store.load_last_used())
        with self.path.open(encoding="utf-8") as handle:
            state = json.load(handle)
        self.assertEqual(set(state), {"presets", "last_used_run_settings"})
        self.assertIsNone(state["last_used_run_settings"])
        self.assertTrue(self.path.read_text(encoding="utf-8").endswith("\n"))

    def test_blank_duplicate_and_invalid_model_shapes_are_rejected(self):
        with self.assertRaises(ScreeningPresetValidationError):
            ScreeningPreset("  ", "sp_example", 1, ("C001",))
        with self.assertRaises(ScreeningPresetValidationError):
            ScreeningPreset("Name", "sp_example", True, ("C001",))
        with self.assertRaises(ScreeningPresetValidationError):
            ScreeningPreset("Name", "sp_example", 1, ["C001"])

        self.store.create_preset(self.preset)
        with self.assertRaises(ScreeningPresetValidationError):
            self.store.create_preset(
                ScreeningPreset(
                    "UI组长-SLG",
                    self.preset.screening_profile_id,
                    1,
                    ("C001",),
                )
            )
        self.assertEqual(self.store.list_presets(), (self.preset,))

    def test_malformed_preset_collection_exposes_no_partial_collection(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps(
                {
                    "presets": [
                        {
                            "preset_name": "healthy",
                            "screening_profile_id": self.preset.screening_profile_id,
                            "profile_version": 1,
                            "screening_rule_expressions": ["C001"],
                        },
                        {"preset_name": "invalid"},
                    ],
                    "last_used_run_settings": None,
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(ScreeningPresetValidationError):
            self.store.list_presets()

    def test_malformed_last_used_does_not_hide_healthy_presets(self):
        self.store.create_preset(self.preset)
        self.path.write_text(
            json.dumps(
                {
                    "presets": [
                        {
                            "preset_name": self.preset.preset_name,
                            "screening_profile_id": self.preset.screening_profile_id,
                            "profile_version": self.preset.profile_version,
                            "screening_rule_expressions": list(
                                self.preset.screening_rule_expressions
                            ),
                        }
                    ],
                    "last_used_run_settings": {"bad": "shape"},
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(self.store.list_presets(), (self.preset,))
        self.assertEqual(self.store.get_preset("UI组长-SLG"), self.preset)
        with self.assertRaises(ScreeningPresetValidationError):
            self.store.load_last_used()

    def test_preset_mutation_preserves_malformed_last_used_unchanged(self):
        self.store.create_preset(self.preset)
        malformed_last_used = {"unrecognized": ["opaque", "data"]}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        state["last_used_run_settings"] = malformed_last_used
        self.path.write_text(json.dumps(state), encoding="utf-8")
        replacement = ScreeningPreset(
            "Renamed",
            self.preset.screening_profile_id,
            self.preset.profile_version,
            self.preset.screening_rule_expressions,
        )

        self.store.replace_preset(self.preset.preset_name, replacement)

        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["last_used_run_settings"], malformed_last_used)
        self.assertEqual(self.store.list_presets(), (replacement,))

    def test_dangling_last_used_is_returned_without_hiding_presets(self):
        self.store.create_preset(self.preset)
        self.path.write_text(
            json.dumps(
                {
                    "presets": [
                        {
                            "preset_name": self.preset.preset_name,
                            "screening_profile_id": self.preset.screening_profile_id,
                            "profile_version": self.preset.profile_version,
                            "screening_rule_expressions": list(
                                self.preset.screening_rule_expressions
                            ),
                        }
                    ],
                    "last_used_run_settings": {
                        "last_used_preset_name": "deleted",
                        "last_action_mode": "favorite",
                        "last_duration_seconds": 0,
                        "last_no_forward": False,
                        "last_batch_filter_enabled": True,
                    },
                }
            ),
            encoding="utf-8",
        )

        self.assertEqual(self.store.list_presets(), (self.preset,))
        self.assertEqual(self.store.load_last_used().last_used_preset_name, "deleted")

    def test_rename_updates_last_used_in_the_same_state_write(self):
        self.store.create_preset(self.preset)
        self.store.save_last_used(self.last_used())
        renamed = ScreeningPreset(
            "产品设计师",
            self.preset.screening_profile_id,
            1,
            self.preset.screening_rule_expressions,
        )

        self.store.replace_preset("UI组长-SLG", renamed)

        self.assertEqual(self.store.list_presets(), (renamed,))
        self.assertEqual(
            self.store.load_last_used().last_used_preset_name,
            "产品设计师",
        )

    def test_delete_last_used_preset_clears_only_last_used_reference(self):
        self.store.create_preset(self.preset)
        self.store.save_last_used(self.last_used())

        self.store.delete_preset("UI组长-SLG")

        self.assertEqual(self.store.list_presets(), ())
        self.assertIsNone(self.store.load_last_used())

    def test_failed_atomic_replace_preserves_prior_preset_and_last_used(self):
        self.store.create_preset(self.preset)
        self.store.save_last_used(self.last_used())
        renamed = ScreeningPreset(
            "产品设计师",
            self.preset.screening_profile_id,
            1,
            self.preset.screening_rule_expressions,
        )

        with patch("screening_preset.os.replace", side_effect=OSError("blocked")):
            with self.assertRaises(ScreeningPresetIOError):
                self.store.replace_preset("UI组长-SLG", renamed)

        reloaded = ScreeningPresetStore(self.path)
        self.assertEqual(reloaded.list_presets(), (self.preset,))
        self.assertEqual(reloaded.load_last_used(), self.last_used())


if __name__ == "__main__":
    unittest.main()
