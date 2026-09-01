from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

import platform_services
from platform_services import clipboard, input as macos_input


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class MacOSInputTests(unittest.TestCase):
    def test_select_all_emits_command_a_once(self):
        with patch.object(macos_input.pyautogui, "hotkey") as hotkey:
            platform_services.select_all()

        hotkey.assert_called_once_with("command", "a")

    def test_copy_emits_command_c_once(self):
        with patch.object(macos_input.pyautogui, "hotkey") as hotkey:
            platform_services.copy()

        hotkey.assert_called_once_with("command", "c")

    def test_clear_selection_uses_macos_backspace_once(self):
        with patch.object(macos_input.pyautogui, "press") as press:
            platform_services.clear_selection()

        press.assert_called_once_with("backspace")

    def test_refresh_browser_emits_command_r_once(self):
        with patch.object(macos_input.pyautogui, "hotkey") as hotkey:
            platform_services.refresh_browser()

        hotkey.assert_called_once_with("command", "r")


class MacOSClipboardTests(unittest.TestCase):
    def completed_process(self, *, stdout=b"", returncode=0):
        return subprocess.CompletedProcess(
            args=["pbpaste"],
            returncode=returncode,
            stdout=stdout,
            stderr=b"",
        )

    def assert_pbpaste_invocation(self, run):
        run.assert_called_once_with(
            ["pbpaste"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=clipboard.PBPASTE_TIMEOUT_SECONDS,
        )

    def test_clipboard_success_returns_utf8_text(self):
        with patch.object(
            clipboard.subprocess,
            "run",
            return_value=self.completed_process(
                stdout="候选人@example.com".encode("utf-8")
            ),
        ) as run:
            result = platform_services.read_clipboard_text()

        self.assertEqual(result, "候选人@example.com")
        self.assert_pbpaste_invocation(run)

    def test_empty_clipboard_returns_empty_string(self):
        with patch.object(
            clipboard.subprocess,
            "run",
            return_value=self.completed_process(),
        ):
            self.assertEqual(platform_services.read_clipboard_text(), "")

    def test_nonzero_pbpaste_exit_returns_empty_without_content_leak(self):
        private_content = "private-candidate@example.invalid"
        output = io.StringIO()
        with (
            patch.object(
                clipboard.subprocess,
                "run",
                return_value=self.completed_process(
                    stdout=private_content.encode("utf-8"),
                    returncode=1,
                ),
            ),
            redirect_stdout(output),
            redirect_stderr(output),
        ):
            self.assertEqual(platform_services.read_clipboard_text(), "")

        self.assertNotIn(private_content, output.getvalue())

    def test_pbpaste_timeout_returns_empty_string(self):
        with patch.object(
            clipboard.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["pbpaste"], 1.0),
        ):
            self.assertEqual(platform_services.read_clipboard_text(), "")

    def test_pbpaste_os_error_returns_empty_string(self):
        with patch.object(
            clipboard.subprocess,
            "run",
            side_effect=OSError("pbpaste unavailable"),
        ):
            self.assertEqual(platform_services.read_clipboard_text(), "")

    def test_invalid_utf8_returns_empty_string(self):
        with patch.object(
            clipboard.subprocess,
            "run",
            return_value=self.completed_process(stdout=b"\xff\xfe"),
        ):
            self.assertEqual(platform_services.read_clipboard_text(), "")


class MacOSBranchStructureTests(unittest.TestCase):
    def test_simple_brush_import_does_not_require_windows_modules(self):
        script = textwrap.dedent(
            """
            import builtins

            blocked = {"win32gui", "win32con", "win32clipboard", "win32process"}
            original_import = builtins.__import__

            def guarded_import(name, *args, **kwargs):
                if name.split(".")[0] in blocked:
                    raise AssertionError(f"unexpected Windows import: {name}")
                return original_import(name, *args, **kwargs)

            builtins.__import__ = guarded_import
            import simple_brush
            print("IMPORT_OK")
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "IMPORT_OK")

    def test_production_code_and_requirements_have_no_pywin32_dependency(self):
        source_files = list(REPOSITORY_ROOT.glob("*.py"))
        source_files.extend(
            (REPOSITORY_ROOT / "platform_services").glob("*.py")
        )
        production_source = "\n".join(
            path.read_text(encoding="utf-8") for path in source_files
        ).lower()
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        ).lower()

        for forbidden in (
            "win32gui",
            "win32con",
            "win32clipboard",
            "win32process",
        ):
            self.assertNotIn(forbidden, production_source)
        self.assertNotIn("pywin32", requirements)
        self.assertFalse(
            (REPOSITORY_ROOT / "platform_services" / "windows.py").exists()
        )

    def test_platform_layer_has_no_runtime_os_selector(self):
        platform_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (REPOSITORY_ROOT / "platform_services").glob("*.py")
        )

        self.assertNotIn("sys.platform", platform_source)
        self.assertNotIn("platform.system", platform_source)
        self.assertNotIn("WindowsPlatformServices", platform_source)
        self.assertNotIn("UnsupportedPlatformServices", platform_source)


if __name__ == "__main__":
    unittest.main()
