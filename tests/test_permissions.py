import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from platform_services import permissions


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def source_identity():
    return permissions.RuntimeIdentity(
        runtime_mode="source",
        executable_path="/opt/ocria-venv/bin/python",
        executable_name="python",
        process_name="Python",
        bundle_identifier="org.python.python",
        bundle_path="/System/Python.app",
        executable_in_app_bundle=False,
        frozen=False,
    )


class FakePermissionBackend:
    def __init__(
        self,
        *,
        screen=True,
        accessibility=True,
        input_monitoring=True,
    ):
        self.screen = screen
        self.accessibility = accessibility
        self.input_monitoring = input_monitoring
        self.requests = []
        self.request_returns = {
            permissions.PermissionKind.SCREEN_RECORDING: False,
            permissions.PermissionKind.ACCESSIBILITY: False,
            permissions.PermissionKind.INPUT_MONITORING: False,
        }
        self.available = {
            permissions.PermissionKind.SCREEN_RECORDING: True,
            permissions.PermissionKind.ACCESSIBILITY: True,
            permissions.PermissionKind.INPUT_MONITORING: True,
        }
        self.request_available = dict(self.available)

    @staticmethod
    def _next(value):
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, BaseException):
            raise value
        return bool(value)

    def screen_recording_check_available(self):
        return self.available[permissions.PermissionKind.SCREEN_RECORDING]

    def screen_recording_request_available(self):
        return self.request_available[
            permissions.PermissionKind.SCREEN_RECORDING
        ]

    def check_screen_recording(self):
        return self._next(self.screen)

    def request_screen_recording(self):
        kind = permissions.PermissionKind.SCREEN_RECORDING
        self.requests.append(kind)
        return self._next(self.request_returns[kind])

    def accessibility_check_available(self):
        return self.available[permissions.PermissionKind.ACCESSIBILITY]

    def accessibility_request_available(self):
        return self.request_available[
            permissions.PermissionKind.ACCESSIBILITY
        ]

    def check_accessibility(self):
        return self._next(self.accessibility)

    def request_accessibility(self):
        kind = permissions.PermissionKind.ACCESSIBILITY
        self.requests.append(kind)
        return self._next(self.request_returns[kind])

    def input_monitoring_check_available(self):
        return self.available[permissions.PermissionKind.INPUT_MONITORING]

    def input_monitoring_request_available(self):
        return self.request_available[
            permissions.PermissionKind.INPUT_MONITORING
        ]

    def check_input_monitoring(self):
        return self._next(self.input_monitoring)

    def request_input_monitoring(self):
        kind = permissions.PermissionKind.INPUT_MONITORING
        self.requests.append(kind)
        return self._next(self.request_returns[kind])


class PermissionCompositionTests(unittest.TestCase):
    def check(self, backend):
        return permissions.check_permissions(
            backend=backend,
            identity_provider=source_identity,
        )

    def ensure(self, backend):
        return permissions.ensure_permissions(
            backend=backend,
            identity_provider=source_identity,
        )

    def test_all_permissions_granted_allows_startup(self):
        report = self.check(FakePermissionBackend())

        self.assertTrue(report.all_required)
        self.assertEqual(report.blocking_results, ())
        self.assertTrue(
            all(result.granted for result in report.results)
        )

    def test_incomplete_report_cannot_accidentally_pass(self):
        report = permissions.PermissionReport(
            results=(
                permissions.PermissionCheckResult(
                    permissions.PermissionKind.SCREEN_RECORDING,
                    permissions.PermissionStatus.GRANTED,
                ),
            ),
            runtime_identity=source_identity(),
        )

        self.assertFalse(report.all_required)

    def test_each_single_missing_permission_blocks_startup(self):
        cases = (
            ("screen", permissions.PermissionKind.SCREEN_RECORDING),
            ("accessibility", permissions.PermissionKind.ACCESSIBILITY),
            ("input_monitoring", permissions.PermissionKind.INPUT_MONITORING),
        )
        for attribute, expected_kind in cases:
            with self.subTest(permission=expected_kind.value):
                kwargs = {attribute: False}
                report = self.check(FakePermissionBackend(**kwargs))

                self.assertFalse(report.all_required)
                self.assertEqual(report.missing_kinds, (expected_kind,))
                self.assertIs(
                    report.result_for(expected_kind).status,
                    permissions.PermissionStatus.DENIED,
                )

    def test_multiple_missing_permissions_are_reported_together(self):
        report = self.check(
            FakePermissionBackend(
                screen=False,
                accessibility=False,
                input_monitoring=False,
            )
        )

        rendered = permissions.format_permission_failure(report)

        self.assertEqual(len(report.blocking_results), 3)
        self.assertIn("屏幕录制", rendered)
        self.assertIn("辅助功能", rendered)
        self.assertIn("输入监控", rendered)
        self.assertIn("自动控制尚未启动", rendered)
        self.assertIn("系统设置 → 隐私与安全性", rendered)

    def test_native_check_exception_is_error_and_fails_closed(self):
        report = self.check(
            FakePermissionBackend(screen=RuntimeError("synthetic"))
        )
        result = report.result_for(
            permissions.PermissionKind.SCREEN_RECORDING
        )

        self.assertFalse(report.all_required)
        self.assertIs(result.status, permissions.PermissionStatus.ERROR)
        self.assertEqual(
            result.detail,
            "native_check_failed:RuntimeError",
        )

    def test_unavailable_native_api_is_explicit_and_fails_closed(self):
        backend = FakePermissionBackend()
        backend.available[
            permissions.PermissionKind.INPUT_MONITORING
        ] = False

        report = self.check(backend)

        self.assertFalse(report.all_required)
        self.assertIs(
            report.result_for(
                permissions.PermissionKind.INPUT_MONITORING
            ).status,
            permissions.PermissionStatus.UNAVAILABLE,
        )

    def test_screen_recording_request_rechecks_to_granted(self):
        backend = FakePermissionBackend(screen=[False, True])

        report = self.ensure(backend)

        self.assertTrue(report.all_required)
        self.assertEqual(
            backend.requests,
            [permissions.PermissionKind.SCREEN_RECORDING],
        )

    def test_screen_recording_request_still_denied_remains_blocked(self):
        backend = FakePermissionBackend(screen=[False, False])

        report = self.ensure(backend)

        self.assertFalse(report.all_required)
        self.assertIs(
            report.result_for(
                permissions.PermissionKind.SCREEN_RECORDING
            ).status,
            permissions.PermissionStatus.DENIED,
        )

    def test_accessibility_prompt_return_does_not_imply_granted(self):
        backend = FakePermissionBackend(accessibility=[False, False])
        backend.request_returns[
            permissions.PermissionKind.ACCESSIBILITY
        ] = True

        report = self.ensure(backend)

        self.assertFalse(report.all_required)
        self.assertEqual(
            backend.requests,
            [permissions.PermissionKind.ACCESSIBILITY],
        )
        self.assertIs(
            report.result_for(
                permissions.PermissionKind.ACCESSIBILITY
            ).status,
            permissions.PermissionStatus.DENIED,
        )

    def test_accessibility_is_granted_only_by_subsequent_check(self):
        backend = FakePermissionBackend(accessibility=[False, True])

        report = self.ensure(backend)

        self.assertTrue(report.all_required)

    def test_input_monitoring_request_rechecks_granted_and_denied(self):
        for final_state in (True, False):
            with self.subTest(final_state=final_state):
                backend = FakePermissionBackend(
                    input_monitoring=[False, final_state]
                )

                report = self.ensure(backend)

                self.assertIs(report.all_required, final_state)
                self.assertEqual(
                    backend.requests,
                    [permissions.PermissionKind.INPUT_MONITORING],
                )

    def test_granted_permissions_are_never_requested(self):
        backend = FakePermissionBackend()

        report = self.ensure(backend)

        self.assertTrue(report.all_required)
        self.assertEqual(backend.requests, [])
        self.assertEqual(report.request_attempts, ())

    def test_check_mode_never_requests_missing_permissions(self):
        backend = FakePermissionBackend(
            screen=False,
            accessibility=False,
            input_monitoring=False,
        )

        report = self.check(backend)

        self.assertFalse(report.all_required)
        self.assertEqual(backend.requests, [])

    def test_permission_logging_contains_only_structured_final_state(self):
        backend = FakePermissionBackend(input_monitoring=False)
        logger = Mock()

        report = permissions.ensure_permissions(
            backend=backend,
            identity_provider=source_identity,
            request_missing=False,
            logger=logger,
        )

        self.assertFalse(report.all_required)
        log_templates = [
            call.args[0]
            for call in logger.info.call_args_list
            + logger.error.call_args_list
        ]
        self.assertIn(
            "event=permission_check permission=%s result=%s",
            log_templates,
        )
        self.assertIn(
            "event=permission_gate result=blocked missing=%s",
            log_templates,
        )


class NativePermissionBackendTests(unittest.TestCase):
    def test_native_backend_uses_required_preflight_apis(self):
        quartz = Mock()
        quartz.CGPreflightScreenCaptureAccess.return_value = True
        quartz.CGPreflightListenEventAccess.return_value = True
        accessibility = Mock()
        accessibility.kAXTrustedCheckOptionPrompt = "prompt"
        accessibility.AXIsProcessTrustedWithOptions.return_value = True
        backend = permissions.NativeMacOSPermissionBackend(
            quartz=quartz,
            accessibility=accessibility,
        )

        report = permissions.check_permissions(
            backend=backend,
            identity_provider=source_identity,
        )

        self.assertTrue(report.all_required)
        quartz.CGPreflightScreenCaptureAccess.assert_called_once_with()
        quartz.CGPreflightListenEventAccess.assert_called_once_with()
        accessibility.AXIsProcessTrustedWithOptions.assert_called_once_with(
            {"prompt": False}
        )

    def test_native_accessibility_request_uses_prompt_true(self):
        accessibility = Mock()
        accessibility.kAXTrustedCheckOptionPrompt = "prompt"
        accessibility.AXIsProcessTrustedWithOptions.return_value = False
        backend = permissions.NativeMacOSPermissionBackend(
            quartz=Mock(),
            accessibility=accessibility,
        )

        self.assertFalse(backend.request_accessibility())

        accessibility.AXIsProcessTrustedWithOptions.assert_called_once_with(
            {"prompt": True}
        )

    def test_native_screen_and_input_requests_use_coregraphics(self):
        quartz = Mock()
        quartz.CGRequestScreenCaptureAccess.return_value = False
        quartz.CGRequestListenEventAccess.return_value = False
        backend = permissions.NativeMacOSPermissionBackend(
            quartz=quartz,
            accessibility=Mock(),
        )

        self.assertFalse(backend.request_screen_recording())
        self.assertFalse(backend.request_input_monitoring())

        quartz.CGRequestScreenCaptureAccess.assert_called_once_with()
        quartz.CGRequestListenEventAccess.assert_called_once_with()

    def test_module_import_has_no_top_level_permission_request_call(self):
        source = (
            REPOSITORY_ROOT / "platform_services" / "permissions.py"
        ).read_text(encoding="utf-8")
        module = ast.parse(source)
        top_level_calls = []
        for node in module.body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                top_level_calls.append(ast.unparse(node.value.func))

        self.assertEqual(top_level_calls, [])


class RuntimeIdentityTests(unittest.TestCase):
    @staticmethod
    def fake_appkit(bundle_path, bundle_id, process_name):
        bundle = Mock()
        bundle.bundlePath.return_value = bundle_path
        bundle.bundleIdentifier.return_value = bundle_id
        appkit = Mock()
        appkit.NSBundle.mainBundle.return_value = bundle
        appkit.NSProcessInfo.processInfo.return_value.processName.return_value = (
            process_name
        )
        return appkit

    def test_source_python_is_distinct_from_detected_python_bundle(self):
        provider = permissions.RuntimeIdentityProvider(
            sys_module=SimpleNamespace(
                executable="/opt/ocria-venv/bin/python",
                frozen=False,
            ),
            appkit=self.fake_appkit(
                "/System/Python.app",
                "org.python.python",
                "Python",
            ),
        )

        identity = provider.detect()

        self.assertEqual(identity.runtime_mode, "source")
        self.assertFalse(identity.executable_in_app_bundle)
        self.assertEqual(identity.bundle_identifier, "org.python.python")
        rendered = permissions.format_runtime_identity(identity)
        self.assertNotIn(identity.executable_path, rendered)
        self.assertNotIn("/opt/", rendered)

    def test_packaged_executable_is_detected_inside_app_bundle(self):
        provider = permissions.RuntimeIdentityProvider(
            sys_module=SimpleNamespace(
                executable="/Applications/Ocria.app/Contents/MacOS/Ocria",
                frozen=True,
            ),
            appkit=self.fake_appkit(
                "/Applications/Ocria.app",
                "com.example.ocria",
                "Ocria",
            ),
        )

        identity = provider.detect()

        self.assertEqual(identity.runtime_mode, "packaged")
        self.assertTrue(identity.executable_in_app_bundle)
        self.assertEqual(identity.executable_name, "Ocria")

    def test_packaged_permission_acceptance_is_explicitly_pending(self):
        report = permissions.check_permissions(
            backend=FakePermissionBackend(),
            identity_provider=source_identity,
        )

        self.assertEqual(
            permissions.PACKAGED_PERMISSION_VALIDATION,
            "pending",
        )
        self.assertEqual(report.packaged_permission_validation, "pending")


if __name__ == "__main__":
    unittest.main()
