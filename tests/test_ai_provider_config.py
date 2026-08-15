from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import ai_provider_config
from ai_provider_config import (
    AI_PROVIDER_CONFIG_VERSION,
    AIProviderConfig,
    AIProviderConfigIOError,
    AIProviderConfigLoadResult,
    AIProviderConfigLoadStatus,
    AIProviderConfigStore,
    ConnectionVerificationStatus,
    DEFAULT_AI_PROVIDER_CONFIG_PATH,
    PROVIDER_ALIYUN_BAILIAN,
    PROVIDER_DEEPSEEK,
)


VERIFIED_AT = datetime(2026, 8, 15, 14, 30, tzinfo=timezone(timedelta(hours=8)))


def valid_payload(**overrides):
    payload = {
        "config_version": 1,
        "provider": PROVIDER_ALIYUN_BAILIAN,
        "api_key": "synthetic-r02-key-value",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-flash",
        "connection_verification_status": "verified",
        "last_verification_time": VERIFIED_AT.isoformat(),
    }
    payload.update(overrides)
    return payload


def complete_config(**overrides):
    values = {
        "provider": PROVIDER_ALIYUN_BAILIAN,
        "api_key": "synthetic-r02-key-value",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-flash",
        "connection_verification_status": ConnectionVerificationStatus.VERIFIED,
        "last_verification_time": VERIFIED_AT,
    }
    values.update(overrides)
    return AIProviderConfig(**values)


class AIProviderConfigDataContractTests(unittest.TestCase):
    def test_constants_and_enums_are_frozen(self):
        self.assertEqual(AI_PROVIDER_CONFIG_VERSION, 1)
        self.assertEqual(PROVIDER_ALIYUN_BAILIAN, "aliyun-bailian")
        self.assertEqual(PROVIDER_DEEPSEEK, "deepseek")
        self.assertEqual(
            [status.value for status in ConnectionVerificationStatus],
            ["unverified", "verified", "failed"],
        )
        self.assertEqual(
            [status.value for status in AIProviderConfigLoadStatus],
            ["not_configured", "incomplete", "invalid", "unsupported_version", "valid"],
        )

    def test_v1_mapping_has_exactly_seven_keys_in_canonical_order(self):
        config = AIProviderConfig(
            provider=PROVIDER_ALIYUN_BAILIAN,
            api_key="synthetic-r02-key-value",
            base_url="https://example.test/v1",
            model="model-a",
            connection_verification_status=ConnectionVerificationStatus.VERIFIED,
            last_verification_time=VERIFIED_AT,
        )

        mapping = ai_provider_config._config_to_mapping(config)

        self.assertEqual(
            list(mapping),
            [
                "config_version",
                "provider",
                "api_key",
                "base_url",
                "model",
                "connection_verification_status",
                "last_verification_time",
            ],
        )
        self.assertEqual(mapping["connection_verification_status"], "verified")
        self.assertEqual(mapping["last_verification_time"], VERIFIED_AT.isoformat())

    def test_provider_validation_allows_only_empty_or_lower_case_kebab_case(self):
        for value in ("", "deepseek", "provider-2"):
            with self.subTest(value=value):
                self.assertEqual(AIProviderConfig(provider=value).provider, value)

        for value in ("DeepSeek", "deep_seek", "deepseek-", "-deepseek"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "provider"):
                    AIProviderConfig(provider=value)

    def test_base_url_validation_accepts_basic_http_urls_and_rejects_other_values(self):
        for value in ("http://localhost:8080/v1", "https://example.test/v1"):
            with self.subTest(value=value):
                self.assertEqual(AIProviderConfig(base_url=value).base_url, value)

        for value in ("not-a-url", "ftp://example.test/v1", "https:///v1"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "base_url"):
                    AIProviderConfig(base_url=value)

    def test_verification_time_requires_a_timezone_aware_datetime_for_checked_statuses(self):
        config = AIProviderConfig(
            connection_verification_status=ConnectionVerificationStatus.FAILED,
            last_verification_time=VERIFIED_AT,
        )
        self.assertEqual(config.last_verification_time, VERIFIED_AT)

        with self.assertRaisesRegex(ValueError, "last_verification_time"):
            AIProviderConfig(
                connection_verification_status=ConnectionVerificationStatus.VERIFIED,
                last_verification_time=datetime(2026, 8, 15, 14, 30),
            )
        with self.assertRaisesRegex(ValueError, "last_verification_time"):
            AIProviderConfig(last_verification_time=VERIFIED_AT)

    def test_api_key_is_retained_but_excluded_from_config_repr(self):
        config = AIProviderConfig(api_key="synthetic-r02-key-value")
        self.assertEqual(config.api_key, "synthetic-r02-key-value")
        self.assertNotIn("synthetic-r02-key-value", repr(config))
        self.assertNotIn("synthetic-r02-key-value", str(config))


class AIProviderConfigLoadTests(unittest.TestCase):
    def test_load_classification_matrix(self):
        cases = (
            ("missing", None, AIProviderConfigLoadStatus.NOT_CONFIGURED, False),
            (
                "incomplete",
                valid_payload(
                    api_key="",
                    connection_verification_status="unverified",
                    last_verification_time=None,
                ),
                AIProviderConfigLoadStatus.INCOMPLETE,
                True,
            ),
            ("invalid JSON", "{\"config_version\":", AIProviderConfigLoadStatus.INVALID, False),
            (
                "invalid schema",
                valid_payload(connection_verification_status="unknown"),
                AIProviderConfigLoadStatus.INVALID,
                False,
            ),
            (
                "unsupported",
                valid_payload(config_version=2),
                AIProviderConfigLoadStatus.UNSUPPORTED_VERSION,
                False,
            ),
            ("valid", valid_payload(), AIProviderConfigLoadStatus.VALID, True),
        )

        for label, content, expected_status, has_config in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "ai_provider.json"
                if isinstance(content, dict):
                    path.write_text(json.dumps(content), encoding="utf-8")
                elif isinstance(content, str):
                    path.write_text(content, encoding="utf-8")

                result = AIProviderConfigStore(path).load()

                self.assertEqual(result.status, expected_status)
                self.assertEqual(result.config is not None, has_config)
                self.assertEqual(result.error is None, has_config or expected_status is AIProviderConfigLoadStatus.NOT_CONFIGURED)

    def test_missing_runtime_fields_are_normalized_to_empty_strings(self):
        payload = valid_payload(
            connection_verification_status="unverified",
            last_verification_time=None,
        )
        for key in ("provider", "api_key", "base_url", "model"):
            payload.pop(key)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_provider.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            result = AIProviderConfigStore(path).load()

        self.assertEqual(result.status, AIProviderConfigLoadStatus.INCOMPLETE)
        self.assertEqual(result.config, AIProviderConfig())

    def test_load_rejects_unknown_key_and_representative_invalid_values(self):
        cases = (
            ("unknown field", valid_payload(extra="not allowed")),
            ("bool version", valid_payload(config_version=True)),
            ("null runtime field", valid_payload(api_key=None)),
            ("invalid base URL", valid_payload(base_url="not-a-url")),
            ("missing verification time", {key: value for key, value in valid_payload().items() if key != "last_verification_time"}),
            ("naive verification time", valid_payload(last_verification_time="2026-08-15T14:30:00")),
        )

        for label, payload in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "ai_provider.json"
                path.write_text(json.dumps(payload), encoding="utf-8")

                result = AIProviderConfigStore(path).load()

                self.assertEqual(result.status, AIProviderConfigLoadStatus.INVALID)
                self.assertIsNone(result.config)
                self.assertIsInstance(result.error, str)

    def test_load_rejects_non_object_json_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_provider.json"
            path.write_text("[]", encoding="utf-8")

            result = AIProviderConfigStore(path).load()

        self.assertEqual(result.status, AIProviderConfigLoadStatus.INVALID)
        self.assertEqual(result.error, "configuration root must be an object")

    def test_load_error_reason_does_not_include_api_key_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_provider.json"
            path.write_text(
                json.dumps(valid_payload(base_url="not-a-url")), encoding="utf-8"
            )

            result = AIProviderConfigStore(path).load()

        self.assertEqual(result.status, AIProviderConfigLoadStatus.INVALID)
        self.assertNotIn("synthetic-r02-key-value", result.error)

    def test_load_wraps_non_missing_read_io_errors(self):
        store = AIProviderConfigStore(Path("unreadable-ai-provider.json"))
        with patch.object(Path, "read_text", side_effect=PermissionError):
            with self.assertRaises(AIProviderConfigIOError):
                store.load()


class AIProviderConfigPersistenceTests(unittest.TestCase):
    def test_save_writes_valid_json_and_loads_it(self):
        config = complete_config()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / "ai_provider.json"
            store = AIProviderConfigStore(path)

            self.assertEqual(store.save(config), path)

            raw = path.read_text(encoding="utf-8")
            self.assertTrue(raw.endswith("\n"))
            self.assertEqual(json.loads(raw), ai_provider_config._config_to_mapping(config))
            self.assertEqual(store.load().config, config)

    def test_new_store_instance_reloads_saved_configuration(self):
        config = complete_config()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / "ai_provider.json"
            AIProviderConfigStore(path).save(config)

            result = AIProviderConfigStore(path).load()

        self.assertEqual(result.status, AIProviderConfigLoadStatus.VALID)
        self.assertEqual(result.config, config)

    def test_replace_failure_preserves_existing_target_and_cleans_temp_file(self):
        original = complete_config()
        replacement = complete_config(model="qwen3.7-plus")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / "ai_provider.json"
            store = AIProviderConfigStore(path)
            store.save(original)
            original_bytes = path.read_bytes()

            with patch.object(
                ai_provider_config.os,
                "replace",
                side_effect=PermissionError("synthetic replacement failure"),
            ):
                with self.assertRaises(AIProviderConfigIOError):
                    store.save(replacement)

            self.assertEqual(path.read_bytes(), original_bytes)
            self.assertEqual(AIProviderConfigStore(path).load().config, original)
            self.assertEqual(list(path.parent.glob(".ai_provider.*.tmp")), [])

    def test_replace_failure_without_target_leaves_no_target_or_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / "ai_provider.json"
            store = AIProviderConfigStore(path)

            with patch.object(
                ai_provider_config.os,
                "replace",
                side_effect=PermissionError("synthetic replacement failure"),
            ):
                with self.assertRaises(AIProviderConfigIOError):
                    store.save(complete_config())

            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.glob(".ai_provider.*.tmp")), [])


class AIProviderConfigUpdateTests(unittest.TestCase):
    def test_connection_field_changes_invalidate_verification(self):
        cases = (
            ("provider", "another-provider"),
            ("api_key", "replacement-key"),
            ("base_url", "https://replacement.example.test/v1"),
        )
        current = complete_config()

        for field_name, value in cases:
            with self.subTest(field=field_name), tempfile.TemporaryDirectory() as tmp:
                store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")

                updated = store.update(current, **{field_name: value})

                self.assertEqual(
                    updated.connection_verification_status,
                    ConnectionVerificationStatus.UNVERIFIED,
                )
                self.assertIsNone(updated.last_verification_time)
                self.assertEqual(store.load().config, updated)

    def test_model_only_change_preserves_verification(self):
        current = complete_config()
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")

            updated = store.update(current, model="qwen3.7-plus")

        self.assertEqual(updated.model, "qwen3.7-plus")
        self.assertEqual(
            updated.connection_verification_status,
            ConnectionVerificationStatus.VERIFIED,
        )
        self.assertEqual(updated.last_verification_time, VERIFIED_AT)

    def test_no_op_preserves_verification(self):
        current = complete_config()
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")

            updated = store.update(
                current,
                provider=current.provider,
                api_key=current.api_key,
                base_url=current.base_url,
                model=current.model,
            )

        self.assertEqual(updated, current)

    def test_multi_field_change_with_connection_field_invalidates_verification(self):
        current = complete_config()
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")

            updated = store.update(
                current,
                api_key="replacement-key",
                model="qwen3.7-plus",
            )

        self.assertEqual(updated.model, "qwen3.7-plus")
        self.assertEqual(
            updated.connection_verification_status,
            ConnectionVerificationStatus.UNVERIFIED,
        )
        self.assertIsNone(updated.last_verification_time)

    def test_clearing_connection_field_makes_config_incomplete_and_unverified(self):
        current = complete_config()
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")

            updated = store.update(current, base_url="")

        self.assertFalse(updated.is_complete)
        self.assertEqual(
            updated.connection_verification_status,
            ConnectionVerificationStatus.UNVERIFIED,
        )
        self.assertIsNone(updated.last_verification_time)

    def test_clearing_model_makes_config_incomplete_and_preserves_verification(self):
        current = complete_config()
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")

            updated = store.update(current, model="")

        self.assertFalse(updated.is_complete)
        self.assertEqual(
            updated.connection_verification_status,
            ConnectionVerificationStatus.VERIFIED,
        )
        self.assertEqual(updated.last_verification_time, VERIFIED_AT)


class AIProviderConfigVerificationWriteBackTests(unittest.TestCase):
    def _write_current(self, store, config):
        store.save(config)
        return config

    def test_matching_verified_result_is_written_back(self):
        current = complete_config(
            connection_verification_status=ConnectionVerificationStatus.UNVERIFIED,
            last_verification_time=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")
            self._write_current(store, current)

            applied = store.record_connection_verification(
                checked_provider=current.provider,
                checked_api_key=current.api_key,
                checked_base_url=current.base_url,
                status=ConnectionVerificationStatus.VERIFIED,
                completed_at=VERIFIED_AT,
            )
            result = store.load()

        self.assertTrue(applied)
        self.assertEqual(
            result.config.connection_verification_status,
            ConnectionVerificationStatus.VERIFIED,
        )
        self.assertEqual(result.config.last_verification_time, VERIFIED_AT)

    def test_matching_failed_result_is_written_back(self):
        current = complete_config(
            connection_verification_status=ConnectionVerificationStatus.UNVERIFIED,
            last_verification_time=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")
            self._write_current(store, current)

            applied = store.record_connection_verification(
                checked_provider=current.provider,
                checked_api_key=current.api_key,
                checked_base_url=current.base_url,
                status=ConnectionVerificationStatus.FAILED,
                completed_at=VERIFIED_AT,
            )
            result = store.load()

        self.assertTrue(applied)
        self.assertEqual(
            result.config.connection_verification_status,
            ConnectionVerificationStatus.FAILED,
        )
        self.assertEqual(result.config.last_verification_time, VERIFIED_AT)

    def test_stale_connection_tuple_is_not_written_back(self):
        current = complete_config(
            api_key="current-key",
            connection_verification_status=ConnectionVerificationStatus.UNVERIFIED,
            last_verification_time=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")
            self._write_current(store, current)

            applied = store.record_connection_verification(
                checked_provider=current.provider,
                checked_api_key="stale-key",
                checked_base_url=current.base_url,
                status=ConnectionVerificationStatus.VERIFIED,
                completed_at=VERIFIED_AT,
            )
            result = store.load()

        self.assertFalse(applied)
        self.assertEqual(result.config, current)

    def test_model_only_changed_config_allows_matching_write_back(self):
        original = complete_config(
            connection_verification_status=ConnectionVerificationStatus.UNVERIFIED,
            last_verification_time=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = AIProviderConfigStore(Path(tmp) / "ai_provider.json")
            self._write_current(store, original)
            current = store.update(original, model="qwen3.7-plus")

            applied = store.record_connection_verification(
                checked_provider=original.provider,
                checked_api_key=original.api_key,
                checked_base_url=original.base_url,
                status=ConnectionVerificationStatus.VERIFIED,
                completed_at=VERIFIED_AT,
            )
            result = store.load()

        self.assertTrue(applied)
        self.assertEqual(result.config.model, "qwen3.7-plus")
        self.assertEqual(
            result.config.connection_verification_status,
            ConnectionVerificationStatus.VERIFIED,
        )

    def test_write_back_rejects_unverified_status_and_naive_completion_time(self):
        store = AIProviderConfigStore(Path("unused-ai-provider.json"))
        with self.assertRaisesRegex(ValueError, "verification status"):
            store.record_connection_verification(
                checked_provider="provider",
                checked_api_key="key",
                checked_base_url="https://example.test",
                status=ConnectionVerificationStatus.UNVERIFIED,
                completed_at=VERIFIED_AT,
            )
        with self.assertRaisesRegex(ValueError, "completed_at"):
            store.record_connection_verification(
                checked_provider="provider",
                checked_api_key="key",
                checked_base_url="https://example.test",
                status=ConnectionVerificationStatus.VERIFIED,
                completed_at=datetime(2026, 8, 15, 14, 30),
            )


class AIProviderConfigSafetyTests(unittest.TestCase):
    def test_api_key_display_has_only_the_two_frozen_messages(self):
        configured = AIProviderConfig(api_key="synthetic-r02-key-value")

        self.assertEqual(configured.api_key, "synthetic-r02-key-value")
        self.assertEqual(configured.api_key_display(), "API Key: configured")
        self.assertEqual(
            AIProviderConfig().api_key_display(),
            "API Key: not configured",
        )

    def test_config_and_load_result_representations_do_not_expose_api_key(self):
        config = AIProviderConfig(api_key="synthetic-r02-key-value")
        result = AIProviderConfigLoadResult(
            status=AIProviderConfigLoadStatus.INCOMPLETE,
            config=config,
        )

        for output in (repr(config), str(config), repr(result)):
            with self.subTest(output=output):
                self.assertNotIn("synthetic-r02-key-value", output)

    def test_load_validation_and_persistence_errors_do_not_expose_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config" / "ai_provider.json"
            path.parent.mkdir()
            path.write_text(
                json.dumps(valid_payload(base_url="not-a-url")), encoding="utf-8"
            )
            load_result = AIProviderConfigStore(path).load()

            with self.assertRaises(ValueError) as validation_error:
                AIProviderConfig(
                    api_key="synthetic-r02-key-value",
                    base_url="not-a-url",
                )

            with patch.object(
                ai_provider_config.os,
                "replace",
                side_effect=PermissionError("synthetic replacement failure"),
            ):
                with self.assertRaises(AIProviderConfigIOError) as persistence_error:
                    AIProviderConfigStore(path).save(
                        AIProviderConfig(api_key="synthetic-r02-key-value")
                    )

        for output in (
            load_result.error,
            str(validation_error.exception),
            str(persistence_error.exception),
        ):
            with self.subTest(output=output):
                self.assertNotIn("synthetic-r02-key-value", output)

    def test_default_path_remains_the_frozen_local_config_path(self):
        self.assertEqual(
            DEFAULT_AI_PROVIDER_CONFIG_PATH,
            Path("config") / "ai_provider.json",
        )


if __name__ == "__main__":
    unittest.main()
