"""Listen-only macOS global ESC/Space monitoring through CoreGraphics."""

import threading
from typing import Any, Callable, Optional, Set

try:
    import CoreFoundation as _CoreFoundation
    import Quartz as _Quartz
except ImportError:  # Safe import boundary for incomplete macOS environments.
    _CoreFoundation = None
    _Quartz = None


# Apple Carbon Events.h virtual key constants, consumed here as raw keycodes.
ESCAPE_KEYCODE = 0x35
SPACE_KEYCODE = 0x31
STARTUP_TIMEOUT_SECONDS = 2.0
STOP_TIMEOUT_SECONDS = 2.0


class NativeCGEventBackend:
    """Narrow adapter around Quartz event taps and a Core Foundation run loop."""

    def __init__(
        self,
        quartz: Any = _Quartz,
        core_foundation: Any = _CoreFoundation,
    ):
        self.quartz = quartz
        self.core_foundation = core_foundation

    def is_available(self) -> bool:
        return self.quartz is not None and self.core_foundation is not None

    def has_listen_access(self) -> bool:
        preflight = getattr(self.quartz, "CGPreflightListenEventAccess", None)
        return True if preflight is None else bool(preflight())

    def create_event_tap(self, callback: Callable[..., Any]) -> Any:
        event_mask = (
            self.quartz.CGEventMaskBit(self.quartz.kCGEventKeyDown)
            | self.quartz.CGEventMaskBit(self.quartz.kCGEventKeyUp)
        )
        return self.quartz.CGEventTapCreate(
            self.quartz.kCGSessionEventTap,
            self.quartz.kCGHeadInsertEventTap,
            self.quartz.kCGEventTapOptionListenOnly,
            event_mask,
            callback,
            None,
        )

    def create_run_loop_source(self, event_tap: Any) -> Any:
        return self.core_foundation.CFMachPortCreateRunLoopSource(
            None,
            event_tap,
            0,
        )

    def current_run_loop(self) -> Any:
        return self.core_foundation.CFRunLoopGetCurrent()

    def add_run_loop_source(self, run_loop: Any, source: Any) -> None:
        self.core_foundation.CFRunLoopAddSource(
            run_loop,
            source,
            self.core_foundation.kCFRunLoopCommonModes,
        )

    def enable_event_tap(self, event_tap: Any, enabled: bool) -> None:
        self.quartz.CGEventTapEnable(event_tap, enabled)

    def run_loop(self) -> None:
        self.core_foundation.CFRunLoopRun()

    def stop_run_loop(self, run_loop: Any) -> None:
        self.core_foundation.CFRunLoopStop(run_loop)
        self.core_foundation.CFRunLoopWakeUp(run_loop)

    def cleanup(self, run_loop: Any, source: Any, event_tap: Any) -> None:
        if event_tap is not None:
            try:
                self.enable_event_tap(event_tap, False)
            except Exception:
                pass
        if run_loop is not None and source is not None:
            try:
                self.core_foundation.CFRunLoopRemoveSource(
                    run_loop,
                    source,
                    self.core_foundation.kCFRunLoopCommonModes,
                )
            except Exception:
                pass
        if source is not None:
            try:
                self.core_foundation.CFRunLoopSourceInvalidate(source)
            except Exception:
                pass
        if event_tap is not None:
            try:
                self.core_foundation.CFMachPortInvalidate(event_tap)
            except Exception:
                pass

    def event_keycode(self, event: Any) -> int:
        return int(
            self.quartz.CGEventGetIntegerValueField(
                event,
                self.quartz.kCGKeyboardEventKeycode,
            )
        )

    def is_key_down(self, event_type: int) -> bool:
        return event_type == self.quartz.kCGEventKeyDown

    def is_key_up(self, event_type: int) -> bool:
        return event_type == self.quartz.kCGEventKeyUp

    def is_tap_disabled(self, event_type: int) -> bool:
        return event_type in (
            self.quartz.kCGEventTapDisabledByTimeout,
            self.quartz.kCGEventTapDisabledByUserInput,
        )


class GlobalHotkeyMonitor:
    """Own one listen-only CGEventTap and its dedicated CFRunLoop thread."""

    def __init__(
        self,
        *,
        on_escape: Callable[[], Any],
        on_space: Callable[[], Any],
        on_failure: Callable[[str], Any],
        logger: Any,
        backend: Optional[NativeCGEventBackend] = None,
        startup_timeout: float = STARTUP_TIMEOUT_SECONDS,
        stop_timeout: float = STOP_TIMEOUT_SECONDS,
    ):
        self._on_escape = on_escape
        self._on_space = on_space
        self._on_failure = on_failure
        self._logger = logger
        self._backend = backend or NativeCGEventBackend()
        self._startup_timeout = startup_timeout
        self._stop_timeout = stop_timeout
        self._lock = threading.Lock()
        self._startup_event = threading.Event()
        self._stop_requested = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._run_loop: Any = None
        self._event_tap: Any = None
        self._running = False
        self._startup_success = False
        self._failure_reason = "not_started"
        self._pressed_keycodes: Set[int] = set()

    def start(self) -> bool:
        """Start once and synchronously report native setup success/failure."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self._running
            self._startup_event = threading.Event()
            self._stop_requested = threading.Event()
            self._startup_success = False
            self._failure_reason = "startup_timeout"
            self._pressed_keycodes.clear()
            self._thread = threading.Thread(
                target=self._thread_main,
                name="ocria-global-hotkey-monitor",
                daemon=True,
            )
            try:
                self._thread.start()
            except Exception as exc:
                self._thread = None
                self._failure_reason = f"thread_start_{type(exc).__name__}"
                self._log_start_failure()
                return False
            startup_event = self._startup_event

        if not startup_event.wait(self._startup_timeout):
            self.stop()
            self._log_start_failure()
            return False

        with self._lock:
            started = self._startup_success and self._running
        if started:
            self._logger.info(
                "event=global_hotkey_monitor_start result=success"
            )
            return True
        self._log_start_failure()
        return False

    def stop(self) -> bool:
        """Stop the owned run loop; repeated calls are safe."""
        with self._lock:
            thread = self._thread
            run_loop = self._run_loop
            was_active = bool(thread is not None and thread.is_alive())
            if not was_active:
                self._running = False
                return True
            self._stop_requested.set()

        if run_loop is not None:
            try:
                self._backend.stop_run_loop(run_loop)
            except Exception:
                pass
        if thread is not threading.current_thread():
            thread.join(self._stop_timeout)

        stopped = not thread.is_alive()
        if stopped:
            self._logger.info(
                "event=global_hotkey_monitor_stop result=success"
            )
            return True
        self._logger.error(
            "event=global_hotkey_monitor_stop result=failed "
            "reason=thread_exit_timeout"
        )
        return False

    def is_running(self) -> bool:
        with self._lock:
            return bool(
                self._running
                and self._thread is not None
                and self._thread.is_alive()
            )

    def _thread_main(self) -> None:
        event_tap = None
        source = None
        run_loop = None
        startup_completed = False
        runtime_failure_signaled = False
        try:
            if not self._backend.is_available():
                self._set_startup_failure("native_api_unavailable")
                return
            if not self._backend.has_listen_access():
                self._set_startup_failure("listen_access_unavailable")
                return

            event_tap = self._backend.create_event_tap(self._event_callback)
            if event_tap is None:
                self._set_startup_failure("event_tap_unavailable")
                return
            source = self._backend.create_run_loop_source(event_tap)
            if source is None:
                self._set_startup_failure("run_loop_source_unavailable")
                return
            run_loop = self._backend.current_run_loop()
            if run_loop is None:
                self._set_startup_failure("run_loop_unavailable")
                return

            self._backend.add_run_loop_source(run_loop, source)
            self._backend.enable_event_tap(event_tap, True)
            with self._lock:
                self._event_tap = event_tap
                self._run_loop = run_loop
                self._running = True
                self._startup_success = True
                self._failure_reason = "none"
                startup_completed = True
            self._startup_event.set()

            if not self._stop_requested.is_set():
                self._backend.run_loop()
        except Exception as exc:
            if not startup_completed:
                self._set_startup_failure(
                    f"native_setup_{type(exc).__name__}"
                )
            elif not self._stop_requested.is_set():
                self._signal_runtime_failure("native_run_loop_error")
                runtime_failure_signaled = True
        finally:
            self._backend.cleanup(run_loop, source, event_tap)
            with self._lock:
                self._running = False
                self._run_loop = None
                self._event_tap = None
                self._pressed_keycodes.clear()
            self._startup_event.set()
            if (
                startup_completed
                and not self._stop_requested.is_set()
                and not runtime_failure_signaled
            ):
                self._signal_runtime_failure("run_loop_exited")

    def _event_callback(
        self,
        _proxy: Any,
        event_type: int,
        event: Any,
        _refcon: Any,
    ) -> Any:
        """Read only a raw keycode, signal intent, and return the event."""
        try:
            if self._backend.is_tap_disabled(event_type):
                event_tap = self._event_tap
                if event_tap is not None:
                    self._backend.enable_event_tap(event_tap, True)
                return event
            if not (
                self._backend.is_key_down(event_type)
                or self._backend.is_key_up(event_type)
            ):
                return event

            keycode = self._backend.event_keycode(event)
            if self._backend.is_key_up(event_type):
                self._pressed_keycodes.discard(keycode)
                return event
            if keycode in self._pressed_keycodes:
                return event
            self._pressed_keycodes.add(keycode)

            if keycode == ESCAPE_KEYCODE:
                self._on_escape()
            elif keycode == SPACE_KEYCODE:
                self._on_space()
        except Exception:
            self._signal_runtime_failure("event_callback_error")
        return event

    def _set_startup_failure(self, reason: str) -> None:
        with self._lock:
            self._startup_success = False
            self._failure_reason = reason
        self._startup_event.set()

    def _signal_runtime_failure(self, reason: str) -> None:
        try:
            self._on_failure(reason)
        except Exception:
            pass

    def _log_start_failure(self) -> None:
        with self._lock:
            reason = self._failure_reason
        self._logger.error(
            "event=global_hotkey_monitor_start result=failed reason=%s",
            reason,
        )


__all__ = [
    "ESCAPE_KEYCODE",
    "GlobalHotkeyMonitor",
    "NativeCGEventBackend",
    "SPACE_KEYCODE",
]
