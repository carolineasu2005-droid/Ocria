"""Focused AM7-R15 startup, confirmation, and handoff tests."""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigLoadResult,
    AIProviderConfigLoadStatus,
    AIProviderConfigStore,
)
from screening_preset import (
    LastUsedRunSettings,
    ScreeningPreset,
    ScreeningPresetIOError,
    ScreeningPresetStore,
)
from screening_preset_cli import (
    apply_invocation_safety_overrides,
    choose_preset_and_run,
    choose_startup_action,
    quick_start,
    run_screening_preset_management,
)
from screening_profile import ScreeningProfileStore
from run_configuration import ResolvedRunConfiguration, resolve_run_configuration
import simple_brush


class Am7R15StartupTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.profile_store = ScreeningProfileStore(root / "profiles")
        self.preset_store = ScreeningPresetStore(root / "screening_presets.json")
        draft = self.profile_store.create_draft()
        self.profile_store.add_criterion(draft, "Python experience")
        self.profile = self.profile_store.save_draft(draft)
        self.preset = ScreeningPreset(
            "Normal Run",
            self.profile.screening_profile_id,
            self.profile.profile_version,
            ("C001",),
        )
        self.preset_store.create_preset(self.preset)
        self.settings = LastUsedRunSettings(
            "Normal Run", "forward", 90, False, True
        )
        self.provider_config = AIProviderConfig(
            provider="deepseek",
            api_key="test-api-key",
            base_url="https://example.invalid",
            model="test-model",
        )
        self.provider_store = Mock(spec=AIProviderConfigStore)
        self.provider_store.load.return_value = AIProviderConfigLoadResult(
            status=AIProviderConfigLoadStatus.VALID,
            config=self.provider_config,
        )

    def test_top_level_menu_has_only_the_frozen_actions(self):
        output = io.StringIO()
        with patch("builtins.input", side_effect=["bad", "0"]), redirect_stdout(output):
            self.assertEqual(choose_startup_action(), "exit")

        text = output.getvalue()
        self.assertIn("1. Quick Start", text)
        self.assertIn("2. Choose ScreeningPreset and Run", text)
        self.assertIn("3. ScreeningPreset Management", text)
        self.assertIn("4. AI Provider Configuration", text)
        self.assertIn("5. Calibration", text)
        self.assertIn("6. Advanced", text)
        self.assertIn("0. Exit", text)
        self.assertNotIn("Prepare Profile", text)

    def test_preset_management_creates_an_exact_profile_binding_after_human_save(self):
        with patch(
            "builtins.input",
            side_effect=["2", "Saved Preset", "1", "1", "ALL", "y", "0"],
        ):
            run_screening_preset_management(
                preset_store=self.preset_store,
                profile_store=self.profile_store,
            )

        saved = self.preset_store.get_preset("Saved Preset")
        self.assertEqual(saved.screening_profile_id, self.profile.screening_profile_id)
        self.assertEqual(saved.profile_version, self.profile.profile_version)
        self.assertEqual(saved.screening_rule_expressions, ("C001",))

    def test_quick_start_confirm_writes_once_before_same_value_handoff(self):
        self.preset_store.save_last_used(self.settings)
        received = []

        def handoff(configuration):
            self.assertEqual(self.preset_store.load_last_used(), self.settings)
            received.append(configuration)

        with patch("builtins.input", side_effect=["c"]):
            self.assertTrue(
                quick_start(
                    preset_store=self.preset_store,
                    profile_store=self.profile_store,
                    provider_store=self.provider_store,
                    cli_args={},
                    on_confirm=handoff,
                )
            )

        self.assertEqual(len(received), 1)
        configuration = received[0]
        self.assertEqual(configuration.exact_screening_profile_version, self.profile)
        self.assertEqual(configuration.run_bound_screening_rule_set.rules[0].expression, "C001")
        self.assertIs(configuration.current_complete_ai_provider_config, self.provider_config)
        self.assertEqual(configuration.action_mode, "forward")
        self.assertEqual(configuration.duration_seconds, 90)
        self.assertFalse(configuration.no_forward)
        self.assertTrue(configuration.batch_filter_enabled)

    def test_cancel_and_edit_do_not_write_last_used_or_handoff(self):
        received = Mock()
        with patch.object(self.preset_store, "save_last_used") as save_last_used:
            with patch("builtins.input", side_effect=["1", "", "", "", "", "0"]):
                self.assertFalse(
                    choose_preset_and_run(
                        preset_store=self.preset_store,
                        profile_store=self.profile_store,
                        provider_store=self.provider_store,
                        cli_args={},
                        on_confirm=received,
                    )
                )

        save_last_used.assert_not_called()
        received.assert_not_called()

    def test_quick_start_failure_does_not_hide_healthy_choose_preset_path(self):
        self.preset_store.path.write_text(
            json.dumps(
                {
                    "presets": [
                        {
                            "preset_name": self.preset.preset_name,
                            "screening_profile_id": self.preset.screening_profile_id,
                            "profile_version": self.preset.profile_version,
                            "screening_rule_expressions": ["C001"],
                        }
                    ],
                    "last_used_run_settings": {"malformed": True},
                }
            ),
            encoding="utf-8",
        )
        received = Mock()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertFalse(
                quick_start(
                    preset_store=self.preset_store,
                    profile_store=self.profile_store,
                    provider_store=self.provider_store,
                    cli_args={},
                    on_confirm=received,
                )
            )
        self.assertEqual(self.preset_store.list_presets(), (self.preset,))
        self.assertIn("Quick Start is unavailable", output.getvalue())

        with patch("builtins.input", side_effect=["1", "", "", "", "", "0"]):
            self.assertFalse(
                choose_preset_and_run(
                    preset_store=self.preset_store,
                    profile_store=self.profile_store,
                    provider_store=self.provider_store,
                    cli_args={},
                    on_confirm=received,
                )
            )
        received.assert_not_called()

    def test_confirmed_run_continues_after_last_used_io_failure_and_forces_safety(self):
        self.preset_store.save_last_used(self.settings)
        received = []
        output = io.StringIO()
        with patch.object(
            self.preset_store,
            "save_last_used",
            side_effect=ScreeningPresetIOError("blocked"),
        ):
            with patch("builtins.input", side_effect=["c"]), redirect_stdout(output):
                self.assertTrue(
                    quick_start(
                        preset_store=self.preset_store,
                        profile_store=self.profile_store,
                        provider_store=self.provider_store,
                        cli_args={"no_forward": True, "no_batch_filter": True},
                        on_confirm=received.append,
                    )
                )

        self.assertEqual(len(received), 1)
        self.assertTrue(received[0].no_forward)
        self.assertFalse(received[0].batch_filter_enabled)
        self.assertIn("Warning: Quick Start settings were not updated.", output.getvalue())
        self.assertEqual(
            apply_invocation_safety_overrides(self.settings, {"no_forward": True}),
            LastUsedRunSettings("Normal Run", "forward", 90, True, True),
        )

    def test_summary_edit_can_switch_preset_and_re_resolves_without_a_write(self):
        alternate = ScreeningPreset(
            "Alternate Run",
            self.profile.screening_profile_id,
            self.profile.profile_version,
            ("C001",),
        )
        self.preset_store.create_preset(alternate)
        self.preset_store.save_last_used(self.settings)
        handoff = Mock()
        with patch.object(self.preset_store, "save_last_used") as save_last_used:
            with patch(
                "builtins.input",
                side_effect=["e", "2", "1", "", "", "", "", "0"],
            ):
                self.assertFalse(
                    quick_start(
                        preset_store=self.preset_store,
                        profile_store=self.profile_store,
                        provider_store=self.provider_store,
                        cli_args={},
                        on_confirm=handoff,
                    )
                )

        save_last_used.assert_not_called()
        handoff.assert_not_called()
        self.assertEqual(self.provider_store.load.call_count, 2)

    def test_resolved_run_path_is_exclusive_and_uses_only_carried_values(self):
        configuration = resolve_run_configuration(
            self.settings,
            preset_store=self.preset_store,
            profile_store=self.profile_store,
            provider_store=self.provider_store,
        )
        self.assertIsInstance(configuration, ResolvedRunConfiguration)
        previous_stop_event = simple_brush.stop_event
        simple_brush.stop_event = True
        try:
            with self.assertRaises(TypeError):
                simple_brush.run(
                    screening_profile_id=self.profile.screening_profile_id,
                    run_bound_rule_set=configuration.run_bound_screening_rule_set,
                    resolved_run_configuration=configuration,
                )
            self.assertTrue(simple_brush.stop_event)

            simple_brush.forward_keywords = [object()]
            simple_brush.forward_enabled = True
            cli_args = {
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": False,
                "no_batch_filter": False,
                "simple_mouse": False,
                "auto": False,
                "action_mode": None,
                "calibration_profile": "",
                "screening_profile_id": "",
                "screening_rules": [],
            }
            with (
                patch.object(simple_brush, "parse_args", return_value=cli_args),
                patch.object(simple_brush, "_prepare_interactive_runtime_inputs") as prepare,
                patch.object(simple_brush, "ScreeningProfileStore") as profile_store,
                patch.object(simple_brush, "AIProviderConfigStore") as provider_store,
                patch.object(simple_brush, "initialize_run_ocr_storage", return_value=None),
            ):
                self.assertEqual(
                    simple_brush.run(resolved_run_configuration=configuration),
                    2,
                )

            profile_store.assert_not_called()
            provider_store.assert_not_called()
            prepare.assert_called_once_with(
                action_mode_value=configuration.action_mode,
                no_forward=configuration.no_forward,
                duration_seconds_value=configuration.duration_seconds,
                batch_filter_enabled_choice=configuration.batch_filter_enabled,
            )
            self.assertEqual(simple_brush.forward_keywords, [])
            self.assertFalse(simple_brush.forward_enabled)
        finally:
            simple_brush.stop_event = previous_stop_event


if __name__ == "__main__":
    unittest.main()
