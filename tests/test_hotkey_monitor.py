from pathlib import Path
import threading
import unittest
from unittest.mock import Mock

from platform_services import hotkey_monitor


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class FakeCGEventBackend:
    KEY_DOWN = 10
    KEY_UP = 11
    TAP_DISABLED = -1

    def __init__(self):
        self.available = True
        self.listen_access = True
        self.event_tap = "event-tap"
        self.source = "run-loop-source"
        self.run_loop_value = "run-loop"
        self.callback = None
        self.create_count = 0
        self.run_entered = threading.Event()
        self.run_release = threading.Event()
        self.events = []

    def is_available(self):
        return self.available

    def has_listen_access(self):
        self.events.append("preflight")
        return self.listen_access

    def create_event_tap(self, callback):
        self.events.append("create_tap")
        self.create_count += 1
        self.callback = callback
        return self.event_tap

    def create_run_loop_source(self, event_tap):
        self.events.append(("create_source", event_tap))
        return self.source

    def current_run_loop(self):
        return self.run_loop_value

    def add_run_loop_source(self, run_loop, source):
        self.events.append(("add_source", run_loop, source))

    def enable_event_tap(self, event_tap, enabled):
        self.events.append(("enable", event_tap, enabled))

    def run_loop(self):
        self.events.append("run")
        self.run_entered.set()
        self.run_release.wait(2.0)

    def stop_run_loop(self, run_loop):
        self.events.append(("stop", run_loop))
        self.run_release.set()

    def cleanup(self, run_loop, source, event_tap):
        self.events.append(("cleanup", run_loop, source, event_tap))

    def event_keycode(self, event):
        return event["keycode"]

    def is_key_down(self, event_type):
        return event_type == self.KEY_DOWN

    def is_key_up(self, event_type):
        return event_type == self.KEY_UP

    def is_tap_disabled(self, event_type):
        return event_type == self.TAP_DISABLED

    def emit(self, event_type, keycode):
        event = {"keycode": keycode}
        return self.callback(None, event_type, event, None)


class GlobalHotkeyMonitorTests(unittest.TestCase):
    def make_monitor(self, backend=None):
        self.backend = backend or FakeCGEventBackend()
        self.on_escape = Mock()
        self.on_space = Mock()
        self.on_failure = Mock()
        self.logger = Mock()
        monitor = hotkey_monitor.GlobalHotkeyMonitor(
            on_escape=self.on_escape,
            on_space=self.on_space,
            on_failure=self.on_failure,
            logger=self.logger,
            backend=self.backend,
            startup_timeout=0.5,
            stop_timeout=0.5,
        )
        self.addCleanup(monitor.stop)
        return monitor

    def test_escape_raw_keycode_requests_stop_once(self):
        monitor = self.make_monitor()
        self.assertTrue(monitor.start())

        returned = self.backend.emit(
            self.backend.KEY_DOWN,
            hotkey_monitor.ESCAPE_KEYCODE,
        )

        self.assertEqual(
            returned,
            {"keycode": hotkey_monitor.ESCAPE_KEYCODE},
        )
        self.on_escape.assert_called_once_with()
        self.on_space.assert_not_called()

    def test_space_raw_keycode_toggles_once(self):
        monitor = self.make_monitor()
        self.assertTrue(monitor.start())

        self.backend.emit(
            self.backend.KEY_DOWN,
            hotkey_monitor.SPACE_KEYCODE,
        )

        self.on_space.assert_called_once_with()
        self.on_escape.assert_not_called()

    def test_unrelated_raw_keycode_has_no_effect(self):
        monitor = self.make_monitor()
        self.assertTrue(monitor.start())

        self.backend.emit(self.backend.KEY_DOWN, 12)

        self.on_escape.assert_not_called()
        self.on_space.assert_not_called()

    def test_repeated_space_keydown_is_suppressed_until_keyup(self):
        monitor = self.make_monitor()
        self.assertTrue(monitor.start())

        self.backend.emit(
            self.backend.KEY_DOWN,
            hotkey_monitor.SPACE_KEYCODE,
        )
        self.backend.emit(
            self.backend.KEY_DOWN,
            hotkey_monitor.SPACE_KEYCODE,
        )
        self.on_space.assert_called_once_with()

        self.backend.emit(
            self.backend.KEY_UP,
            hotkey_monitor.SPACE_KEYCODE,
        )
        self.backend.emit(
            self.backend.KEY_DOWN,
            hotkey_monitor.SPACE_KEYCODE,
        )
        self.assertEqual(self.on_space.call_count, 2)

    def test_start_success_reports_running(self):
        monitor = self.make_monitor()

        self.assertTrue(monitor.start())

        self.assertTrue(monitor.is_running())
        self.assertTrue(self.backend.run_entered.wait(0.5))
        self.logger.info.assert_any_call(
            "event=global_hotkey_monitor_start result=success"
        )

    def test_event_tap_creation_failure_returns_false(self):
        backend = FakeCGEventBackend()
        backend.event_tap = None
        monitor = self.make_monitor(backend)

        self.assertFalse(monitor.start())

        self.assertFalse(monitor.is_running())
        self.assertNotIn("run", backend.events)
        self.logger.error.assert_called_once_with(
            "event=global_hotkey_monitor_start result=failed reason=%s",
            "event_tap_unavailable",
        )

    def test_permission_unavailable_returns_false_before_tap_creation(self):
        backend = FakeCGEventBackend()
        backend.listen_access = False
        monitor = self.make_monitor(backend)

        self.assertFalse(monitor.start())

        self.assertEqual(backend.create_count, 0)
        self.assertFalse(monitor.is_running())

    def test_stop_exits_thread_and_clears_running_state(self):
        monitor = self.make_monitor()
        self.assertTrue(monitor.start())

        self.assertTrue(monitor.stop())

        self.assertFalse(monitor.is_running())
        self.assertIn(("stop", self.backend.run_loop_value), self.backend.events)
        self.assertIn(
            (
                "cleanup",
                self.backend.run_loop_value,
                self.backend.source,
                self.backend.event_tap,
            ),
            self.backend.events,
        )

    def test_repeated_start_does_not_create_duplicate_tap(self):
        monitor = self.make_monitor()

        self.assertTrue(monitor.start())
        self.assertTrue(monitor.start())

        self.assertEqual(self.backend.create_count, 1)

    def test_repeated_stop_is_idempotent(self):
        monitor = self.make_monitor()
        self.assertTrue(monitor.start())

        self.assertTrue(monitor.stop())
        self.assertTrue(monitor.stop())

        stop_events = [
            event
            for event in self.backend.events
            if isinstance(event, tuple) and event[0] == "stop"
        ]
        self.assertEqual(len(stop_events), 1)

    def test_disabled_event_tap_is_reenabled_without_hotkey_action(self):
        monitor = self.make_monitor()
        self.assertTrue(monitor.start())

        self.backend.emit(self.backend.TAP_DISABLED, 0)

        self.assertIn(
            ("enable", self.backend.event_tap, True),
            self.backend.events,
        )
        self.on_escape.assert_not_called()
        self.on_space.assert_not_called()


class HotkeyArchitectureTests(unittest.TestCase):
    def test_verified_raw_keycodes_are_fixed(self):
        self.assertEqual(hotkey_monitor.ESCAPE_KEYCODE, 53)
        self.assertEqual(hotkey_monitor.SPACE_KEYCODE, 49)

    def test_production_has_no_pynput_keyboard_listener(self):
        source_files = list(REPOSITORY_ROOT.glob("*.py"))
        source_files.extend(
            (REPOSITORY_ROOT / "platform_services").glob("*.py")
        )
        production_source = "\n".join(
            path.read_text(encoding="utf-8") for path in source_files
        )
        for forbidden in (
            "keyboard.Listener",
            "pynput.keyboard",
            "from pynput import keyboard",
        ):
            self.assertNotIn(forbidden, production_source)

    def test_hotkey_module_has_no_character_or_layout_translation(self):
        source = (
            REPOSITORY_ROOT / "platform_services" / "hotkey_monitor.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "Unicode",
            "CGEventKeyboardGetUnicodeString",
            "TISCopyCurrentKeyboardInputSource",
            "UCKeyTranslate",
            "TSMGetInputSourceProperty",
        ):
            self.assertNotIn(forbidden, source)

    def test_pynput_is_not_a_declared_dependency(self):
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        ).lower()
        self.assertNotIn("pynput", requirements)
        self.assertIn("pyobjc-framework-quartz>=12.2.2", requirements)


if __name__ == "__main__":
    unittest.main()
