"""Focused AM7-R15 Run-configuration tests."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ai_provider_config import (
    AIProviderConfig,
    AIProviderConfigIOError,
    AIProviderConfigLoadResult,
    AIProviderConfigLoadStatus,
    AIProviderConfigStore,
)
from run_configuration import (
    RunConfigurationError,
    build_all_rule_expression,
    build_any_rule_expression,
    build_screening_rule_set,
    render_run_summary,
    resolve_run_configuration,
    validate_preset_definition,
)
from screening_preset import (
    LastUsedRunSettings,
    ScreeningPreset,
    ScreeningPresetStore,
)
from screening_profile import ScreeningProfileStore


class RunConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        root = Path(self.temporary_directory.name)
        self.profile_store = ScreeningProfileStore(root / "profiles")
        self.preset_store = ScreeningPresetStore(root / "screening_presets.json")
        draft = self.profile_store.create_draft()
        self.profile_store.add_criterion(draft, "Python experience")
        self.profile_store.add_criterion(draft, "Management experience")
        self.profile_store.add_criterion(draft, "Game industry experience")
        self.profile_v1 = self.profile_store.save_draft(draft)
        self.preset = ScreeningPreset(
            "UI组长-SLG",
            self.profile_v1.screening_profile_id,
            self.profile_v1.profile_version,
            ("C001 AND (C002 OR C003)",),
        )
        self.preset_store.create_preset(self.preset)
        self.settings = LastUsedRunSettings(
            "UI组长-SLG", "forward", 0, True, False
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

    def test_all_and_any_preserve_profile_criterion_order(self):
        self.assertEqual(
            build_all_rule_expression(self.profile_v1),
            "C001 AND C002 AND C003",
        )
        self.assertEqual(
            build_any_rule_expression(self.profile_v1),
            "C001 OR C002 OR C003",
        )
        self.assertTrue(
            validate_preset_definition(
                ScreeningPreset(
                    "all",
                    self.profile_v1.screening_profile_id,
                    1,
                    (build_all_rule_expression(self.profile_v1),),
                ),
                self.profile_store,
            )[1]
        )

    def test_custom_rule_is_preserved_and_invalid_rule_fails_closed(self):
        rule_set = build_screening_rule_set(self.preset.screening_rule_expressions)
        self.assertEqual(rule_set.rules[0].expression, "C001 AND (C002 OR C003)")
        with self.assertRaises(RunConfigurationError):
            validate_preset_definition(
                ScreeningPreset(
                    "invalid",
                    self.profile_v1.screening_profile_id,
                    1,
                    ("C001 NOT C002",),
                ),
                self.profile_store,
            )

    def test_preset_resolution_uses_exact_version_without_load_latest(self):
        draft = self.profile_store.create_draft_from_latest(
            self.profile_v1.screening_profile_id
        )
        self.profile_store.edit_criterion(draft, "C001", "Updated Python")
        profile_v2 = self.profile_store.save_draft(draft)
        self.assertEqual(profile_v2.profile_version, 2)

        with patch.object(
            self.profile_store,
            "load_latest",
            side_effect=AssertionError("Preset resolution must not load latest"),
        ):
            configuration = resolve_run_configuration(
                self.settings,
                preset_store=self.preset_store,
                profile_store=self.profile_store,
                provider_store=self.provider_store,
            )

        self.assertEqual(
            configuration.exact_screening_profile_version,
            self.profile_store.load_version(self.profile_v1.screening_profile_id, 1),
        )
        self.assertEqual(configuration.exact_screening_profile_version.profile_version, 1)
        self.assertIs(configuration.current_complete_ai_provider_config, self.provider_config)
        self.provider_store.load.assert_called_once_with()

    def test_dangling_preset_and_invalid_provider_fail_without_substitution(self):
        dangling = LastUsedRunSettings("missing", "favorite", 0, False, True)
        with self.assertRaises(RunConfigurationError):
            resolve_run_configuration(
                dangling,
                preset_store=self.preset_store,
                profile_store=self.profile_store,
                provider_store=self.provider_store,
            )
        self.provider_store.load.assert_not_called()

        for status, error in (
            (AIProviderConfigLoadStatus.NOT_CONFIGURED, None),
            (AIProviderConfigLoadStatus.INCOMPLETE, None),
            (AIProviderConfigLoadStatus.INVALID, "invalid"),
            (AIProviderConfigLoadStatus.UNSUPPORTED_VERSION, "unsupported"),
        ):
            with self.subTest(status=status):
                self.provider_store.load.return_value = AIProviderConfigLoadResult(
                    status=status,
                    config=self.provider_config
                    if status is AIProviderConfigLoadStatus.INCOMPLETE
                    else None,
                    error=error,
                )
                with self.assertRaises(RunConfigurationError):
                    resolve_run_configuration(
                        self.settings,
                        preset_store=self.preset_store,
                        profile_store=self.profile_store,
                        provider_store=self.provider_store,
                    )
        self.provider_store.load.side_effect = AIProviderConfigIOError("blocked")
        with self.assertRaises(RunConfigurationError):
            resolve_run_configuration(
                self.settings,
                preset_store=self.preset_store,
                profile_store=self.profile_store,
                provider_store=self.provider_store,
            )

    def test_summary_is_pure_uuid_free_and_displays_effective_settings(self):
        configuration = resolve_run_configuration(
            self.settings,
            preset_store=self.preset_store,
            profile_store=self.profile_store,
            provider_store=self.provider_store,
        )

        summary = render_run_summary(configuration)

        self.assertIn("Preset: UI组长-SLG", summary)
        self.assertIn("Profile Version: v1", summary)
        self.assertIn("C001: Python experience", summary)
        self.assertIn("Rule: CUSTOM", summary)
        self.assertIn("Provider: deepseek", summary)
        self.assertIn("Model: test-model", summary)
        self.assertIn("Action: FORWARD", summary)
        self.assertIn("Forward side effect: suppressed", summary)
        self.assertIn("Duration: Unlimited", summary)
        self.assertNotIn(self.profile_v1.screening_profile_id, summary)
        self.assertNotIn("test-api-key", summary)
        self.assertNotIn("Calibration profile", summary)


if __name__ == "__main__":
    unittest.main()
