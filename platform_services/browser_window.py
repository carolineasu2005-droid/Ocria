"""Native macOS discovery and activation for BOSS pages in Google Chrome."""

from dataclasses import dataclass
from enum import Enum
import time
from typing import Any, Iterable, List, Optional, Tuple

try:
    import AppKit as _AppKit
    import ApplicationServices as _AX
except ImportError:  # Safe import boundary for incomplete macOS environments.
    _AppKit = None
    _AX = None


CHROME_BUNDLE_ID = "com.google.Chrome"
AX_FULLSCREEN_ATTRIBUTE = "AXFullScreen"
AX_MESSAGING_TIMEOUT_SECONDS = 1.0
ACTIVATION_VERIFY_TIMEOUT_SECONDS = 2.0
ACTIVATION_VERIFY_INTERVAL_SECONDS = 0.1
ACTIVATION_VERIFY_ATTEMPTS = (
    int(
        ACTIVATION_VERIFY_TIMEOUT_SECONDS
        / ACTIVATION_VERIFY_INTERVAL_SECONDS
    )
    + 1
)


class TitleState(str, Enum):
    """Whether AX exposed usable title metadata for a Chrome window."""

    PRESENT = "present"
    EMPTY = "empty"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ChromeWindow:
    """Opaque Chrome/AX window state used only inside the platform layer."""

    application: Any
    application_element: Any
    element: Any
    title: str
    title_state: TitleState
    minimized: Optional[bool]
    fullscreen: Optional[bool]
    focused: bool
    main: bool
    application_active: bool
    application_order: int
    window_order: int


@dataclass(frozen=True)
class ChromeWindowDiscovery:
    """One raw AX enumeration, before any BOSS identity filtering."""

    windows: Tuple[ChromeWindow, ...]
    enumeration_failed: bool


def is_boss_window_title(title: object) -> bool:
    """Match the selected tab exposed in a Chrome top-level window title.

    Background tabs are intentionally not enumerated in the MAC-R03 MVP.
    """
    if not isinstance(title, str):
        return False
    return "BOSS" in title or "zhipin" in title.lower()


class NativeMacOSBrowserAPI:
    """Small adapter around AppKit and macOS Accessibility APIs."""

    def __init__(self, appkit: Any = _AppKit, accessibility: Any = _AX):
        self.appkit = appkit
        self.accessibility = accessibility

    def is_available(self) -> bool:
        return self.appkit is not None and self.accessibility is not None

    def running_applications(self, bundle_id: str) -> List[Any]:
        applications = list(
            self.appkit.NSRunningApplication
            .runningApplicationsWithBundleIdentifier_(bundle_id)
            or []
        )
        active = []
        for application in applications:
            try:
                if not application.isTerminated():
                    active.append(application)
            except Exception:
                continue
        return sorted(active, key=self._application_sort_key)

    def accessibility_trusted(self) -> bool:
        return bool(self.accessibility.AXIsProcessTrusted())

    def enumerate_windows(
        self,
        application: Any,
        application_order: int,
    ) -> Optional[List[ChromeWindow]]:
        application_element = self.accessibility.AXUIElementCreateApplication(
            int(application.processIdentifier())
        )
        set_timeout = getattr(
            self.accessibility,
            "AXUIElementSetMessagingTimeout",
            None,
        )
        if set_timeout is not None:
            set_timeout(application_element, AX_MESSAGING_TIMEOUT_SECONDS)

        windows_ok, window_elements = self._copy_attribute(
            application_element,
            self.accessibility.kAXWindowsAttribute,
        )
        if not windows_ok or window_elements is None:
            return None

        _, focused_window = self._copy_attribute(
            application_element,
            self.accessibility.kAXFocusedWindowAttribute,
        )
        application_active = self._application_is_active(application)
        windows = []
        for window_order, element in enumerate(list(window_elements)):
            title_ok, title = self._copy_attribute(
                element,
                self.accessibility.kAXTitleAttribute,
            )
            normalized_title, title_state = _normalize_title(title_ok, title)
            minimized_ok, minimized = self._copy_attribute(
                element,
                self.accessibility.kAXMinimizedAttribute,
            )
            fullscreen_ok, fullscreen = self._copy_attribute(
                element,
                AX_FULLSCREEN_ATTRIBUTE,
            )
            _, focused = self._copy_attribute(
                element,
                self.accessibility.kAXFocusedAttribute,
            )
            _, main = self._copy_attribute(
                element,
                self.accessibility.kAXMainAttribute,
            )
            windows.append(
                ChromeWindow(
                    application=application,
                    application_element=application_element,
                    element=element,
                    title=normalized_title,
                    title_state=title_state,
                    minimized=(bool(minimized) if minimized_ok else None),
                    fullscreen=(bool(fullscreen) if fullscreen_ok else None),
                    focused=(
                        self._elements_equal(element, focused_window)
                        or bool(focused)
                    ),
                    main=bool(main),
                    application_active=application_active,
                    application_order=application_order,
                    window_order=window_order,
                )
            )
        return windows

    def elements_equal(self, left: Any, right: Any) -> bool:
        """Compare opaque AX elements without exposing them to callers."""
        return self._elements_equal(left, right)

    def restore_window(self, window: ChromeWindow) -> bool:
        error = self.accessibility.AXUIElementSetAttributeValue(
            window.element,
            self.accessibility.kAXMinimizedAttribute,
            False,
        )
        if error != self.accessibility.kAXErrorSuccess:
            return False
        minimized_ok, minimized = self._copy_attribute(
            window.element,
            self.accessibility.kAXMinimizedAttribute,
        )
        return minimized_ok and not bool(minimized)

    def activate_application(self, window: ChromeWindow) -> bool:
        options = (
            self.appkit.NSApplicationActivateAllWindows
            | self.appkit.NSApplicationActivateIgnoringOtherApps
        )
        return bool(window.application.activateWithOptions_(options))

    def raise_and_focus_window(self, window: ChromeWindow) -> bool:
        raise_error = self.accessibility.AXUIElementPerformAction(
            window.element,
            self.accessibility.kAXRaiseAction,
        )
        if raise_error != self.accessibility.kAXErrorSuccess:
            return False

        focus_errors = (
            self.accessibility.AXUIElementSetAttributeValue(
                window.application_element,
                self.accessibility.kAXFocusedWindowAttribute,
                window.element,
            ),
            self.accessibility.AXUIElementSetAttributeValue(
                window.element,
                self.accessibility.kAXMainAttribute,
                True,
            ),
            self.accessibility.AXUIElementSetAttributeValue(
                window.element,
                self.accessibility.kAXFocusedAttribute,
                True,
            ),
        )
        return self.accessibility.kAXErrorSuccess in focus_errors

    def verify_activation(self, window: ChromeWindow) -> bool:
        minimized_ok, minimized = self._copy_attribute(
            window.element,
            self.accessibility.kAXMinimizedAttribute,
        )
        if not minimized_ok or bool(minimized):
            return False

        _, frontmost = self._copy_attribute(
            window.application_element,
            self.accessibility.kAXFrontmostAttribute,
        )
        application_frontmost = (
            self._application_is_active(window.application)
            or bool(frontmost)
            or self._workspace_frontmost_matches(window.application)
        )
        if not application_frontmost:
            return False

        focused_window_ok, focused_window = self._copy_attribute(
            window.application_element,
            self.accessibility.kAXFocusedWindowAttribute,
        )
        focused_ok, focused = self._copy_attribute(
            window.element,
            self.accessibility.kAXFocusedAttribute,
        )
        main_ok, main = self._copy_attribute(
            window.element,
            self.accessibility.kAXMainAttribute,
        )
        target_has_focus = (
            (
                focused_window_ok
                and self._elements_equal(window.element, focused_window)
            )
            or (focused_ok and bool(focused))
            or (main_ok and bool(main))
        )
        fullscreen_ok, fullscreen = self._copy_attribute(
            window.element,
            AX_FULLSCREEN_ATTRIBUTE,
        )
        if window.fullscreen is not True:
            return target_has_focus

        if (
            focused_window_ok
            and focused_window is not None
            and not self._elements_equal(window.element, focused_window)
        ):
            return False

        # Chrome fullscreen windows can remain neither AXFocused nor AXMain
        # while macOS is completing the Space transition.  Once the owning
        # application is frontmost and the same target is still explicitly
        # fullscreen, the activation request has reached the intended Space.
        return fullscreen_ok and bool(fullscreen)

    def _copy_attribute(self, element: Any, attribute: str) -> Tuple[bool, Any]:
        try:
            error, value = self.accessibility.AXUIElementCopyAttributeValue(
                element,
                attribute,
                None,
            )
        except Exception:
            return False, None
        return error == self.accessibility.kAXErrorSuccess, value

    def _application_sort_key(self, application: Any) -> Tuple[bool, int]:
        try:
            process_id = int(application.processIdentifier())
        except Exception:
            process_id = 0
        return not self._application_is_active(application), process_id

    @staticmethod
    def _application_is_active(application: Any) -> bool:
        try:
            return bool(application.isActive())
        except Exception:
            return False

    def _workspace_frontmost_matches(self, application: Any) -> bool:
        try:
            frontmost = self.appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
            return int(frontmost.processIdentifier()) == int(
                application.processIdentifier()
            )
        except Exception:
            return False

    @staticmethod
    def _elements_equal(left: Any, right: Any) -> bool:
        if left is None or right is None:
            return False
        try:
            return left is right or bool(left == right)
        except Exception:
            return False


def _window_selection_key(window: ChromeWindow) -> Tuple[bool, bool, bool, int, int]:
    return (
        not window.focused,
        not window.main,
        not window.application_active,
        window.application_order,
        window.window_order,
    )


def _normalize_title(title_ok: bool, title: Any) -> Tuple[str, TitleState]:
    if not title_ok:
        return "", TitleState.UNAVAILABLE
    if title is None:
        return "", TitleState.EMPTY
    normalized = title if isinstance(title, str) else str(title)
    if not normalized.strip():
        return "", TitleState.EMPTY
    return normalized, TitleState.PRESENT


def enumerate_raw_chrome_windows(
    api: NativeMacOSBrowserAPI,
    applications: Iterable[Any],
) -> ChromeWindowDiscovery:
    """Enumerate Chrome AX windows without applying BOSS eligibility rules."""
    raw_windows = []
    enumeration_failed = False
    for application_order, application in enumerate(applications):
        windows = api.enumerate_windows(application, application_order)
        if windows is None:
            enumeration_failed = True
            continue
        raw_windows.extend(windows)
    return ChromeWindowDiscovery(
        windows=tuple(raw_windows),
        enumeration_failed=enumeration_failed,
    )


def identify_confirmed_boss_windows(
    windows: Iterable[ChromeWindow],
) -> List[ChromeWindow]:
    """Return only windows with readable BOSS/zhipin title evidence."""
    return [
        window
        for window in windows
        if window.title_state is TitleState.PRESENT
        and is_boss_window_title(window.title)
    ]


def identify_fullscreen_probe_candidates(
    windows: Iterable[ChromeWindow],
) -> List[ChromeWindow]:
    """Return fullscreen windows safe to activate only for discovery."""
    return [
        window
        for window in windows
        if window.fullscreen is True and window.minimized is not True
    ]


def _safe_bool(value: Optional[bool]) -> str:
    if value is None:
        return "unknown"
    return str(bool(value)).lower()


def _log_discovery(
    logger: Any,
    discovery: ChromeWindowDiscovery,
    *,
    stage: str,
) -> None:
    windows = discovery.windows
    logger.info(
        "event=browser_window_discovery browser=chrome stage=%s "
        "chrome_running=true raw_window_count=%s fullscreen_count=%s "
        "title_present_count=%s title_empty_count=%s "
        "title_unavailable_count=%s title_match_count=%s "
        "enumeration_failed=%s",
        stage,
        len(windows),
        sum(window.fullscreen is True for window in windows),
        sum(window.title_state is TitleState.PRESENT for window in windows),
        sum(window.title_state is TitleState.EMPTY for window in windows),
        sum(window.title_state is TitleState.UNAVAILABLE for window in windows),
        len(identify_confirmed_boss_windows(windows)),
        str(discovery.enumeration_failed).lower(),
    )
    for window_index, window in enumerate(windows):
        logger.debug(
            "event=browser_window_candidate browser=chrome stage=%s "
            "window_index=%s fullscreen=%s minimized=%s title_state=%s "
            "title_match=%s focused=%s main=%s",
            stage,
            window_index,
            _safe_bool(window.fullscreen),
            _safe_bool(window.minimized),
            window.title_state.value,
            str(
                window.title_state is TitleState.PRESENT
                and is_boss_window_title(window.title)
            ).lower(),
            str(window.focused).lower(),
            str(window.main).lower(),
        )


def _window_mode(window: ChromeWindow) -> str:
    if window.fullscreen is True:
        return "fullscreen"
    if window.fullscreen is False:
        return "windowed"
    return "unknown"


def _activate_and_verify_window(
    logger: Any,
    api: NativeMacOSBrowserAPI,
    window: ChromeWindow,
    *,
    stage: str,
    allow_unknown_minimized: bool = False,
) -> bool:
    mode = _window_mode(window)
    if window.minimized is None and not allow_unknown_minimized:
        logger.error(
            "event=browser_window_activate browser=chrome result=failed "
            "reason=window_state_unavailable stage=%s mode=%s",
            stage,
            mode,
        )
        return False

    if window.minimized:
        if not api.restore_window(window):
            logger.error(
                "event=browser_window_restore browser=chrome result=failed "
                "stage=%s mode=%s",
                stage,
                mode,
            )
            return False
        logger.info(
            "event=browser_window_restore browser=chrome result=success "
            "stage=%s mode=%s",
            stage,
            mode,
        )

    if not api.activate_application(window):
        logger.error(
            "event=browser_window_activate browser=chrome result=failed "
            "reason=application_activation_failed stage=%s mode=%s",
            stage,
            mode,
        )
        return False

    focus_request_succeeded = api.raise_and_focus_window(window)
    if not focus_request_succeeded and window.fullscreen is not True:
        logger.error(
            "event=browser_window_activate browser=chrome result=failed "
            "reason=window_raise_or_focus_failed stage=%s mode=%s",
            stage,
            mode,
        )
        return False

    for attempt in range(1, ACTIVATION_VERIFY_ATTEMPTS + 1):
        if api.verify_activation(window):
            logger.info(
                "event=browser_window_activate browser=chrome stage=%s "
                "mode=%s result=success verification_attempt=%s",
                stage,
                mode,
                attempt,
            )
            return True
        if attempt < ACTIVATION_VERIFY_ATTEMPTS:
            time.sleep(ACTIVATION_VERIFY_INTERVAL_SECONDS)

    logger.error(
        "event=browser_window_activate browser=chrome result=failed "
        "reason=verification_failed stage=%s mode=%s "
        "verification_attempts=%s",
        stage,
        mode,
        ACTIVATION_VERIFY_ATTEMPTS,
    )
    return False


def _windows_correlate(
    api: NativeMacOSBrowserAPI,
    initial: ChromeWindow,
    reacquired: ChromeWindow,
) -> bool:
    try:
        same_application = (
            initial.application is reacquired.application
            or bool(initial.application == reacquired.application)
        )
    except Exception:
        same_application = False
    if not same_application:
        try:
            same_application = int(initial.application.processIdentifier()) == int(
                reacquired.application.processIdentifier()
            )
        except Exception:
            return False
    if not same_application:
        return False
    try:
        return bool(api.elements_equal(initial.element, reacquired.element))
    except Exception:
        return False


def _post_probe_selection_key(
    api: NativeMacOSBrowserAPI,
    probe: ChromeWindow,
    window: ChromeWindow,
) -> Tuple[bool, bool, bool, bool, int, int]:
    return (
        not window.focused,
        not window.main,
        not window.application_active,
        not _windows_correlate(api, probe, window),
        window.application_order,
        window.window_order,
    )


def bring_boss_foreground(
    logger: Any,
    native_api: Optional[NativeMacOSBrowserAPI] = None,
) -> bool:
    """Find, restore, activate, and verify the active-tab BOSS Chrome window."""
    api = native_api or NativeMacOSBrowserAPI()
    try:
        if not api.is_available():
            logger.error(
                "event=browser_window_activate browser=chrome result=failed "
                "reason=native_api_unavailable"
            )
            return False

        applications = api.running_applications(CHROME_BUNDLE_ID)
        if not applications:
            logger.error(
                "event=browser_window_lookup browser=chrome result=not_running"
            )
            return False

        if not api.accessibility_trusted():
            logger.error(
                "event=browser_window_activate browser=chrome result=failed "
                "reason=accessibility_unavailable"
            )
            return False

        discovery = enumerate_raw_chrome_windows(api, applications)
        _log_discovery(logger, discovery, stage="initial")
        confirmed = identify_confirmed_boss_windows(discovery.windows)

        if confirmed:
            window = min(confirmed, key=_window_selection_key)
            logger.info(
                "event=browser_window_lookup browser=chrome result=found "
                "eligible=true path=direct mode=%s",
                _window_mode(window),
            )
            return _activate_and_verify_window(
                logger,
                api,
                window,
                stage="direct_confirmed",
            )

        if not discovery.windows:
            result = "api_failure" if discovery.enumeration_failed else "no_eligible_window"
            logger.error(
                "event=browser_window_lookup browser=chrome result=%s "
                "reason=no_ax_windows",
                result,
            )
            return False

        probe_candidates = identify_fullscreen_probe_candidates(
            discovery.windows
        )
        if not probe_candidates:
            logger.error(
                "event=browser_window_lookup browser=chrome "
                "result=no_eligible_window reason=no_fullscreen_probe_candidate"
            )
            return False
        if len(probe_candidates) > 1:
            logger.error(
                "event=browser_fullscreen_probe browser=chrome "
                "result=ambiguous_fullscreen_candidates candidate_count=%s",
                len(probe_candidates),
            )
            return False

        probe = probe_candidates[0]
        logger.info(
            "event=browser_fullscreen_probe browser=chrome result=selected "
            "candidate_count=1"
        )
        logger.info(
            "event=browser_fullscreen_probe browser=chrome "
            "result=activation_requested"
        )
        if not _activate_and_verify_window(
            logger,
            api,
            probe,
            stage="fullscreen_probe",
            allow_unknown_minimized=True,
        ):
            logger.error(
                "event=browser_fullscreen_probe browser=chrome "
                "result=confirmation_failed reason=activation_failed"
            )
            return False

        reacquired_applications = api.running_applications(CHROME_BUNDLE_ID)
        if not reacquired_applications:
            logger.error(
                "event=browser_fullscreen_probe browser=chrome "
                "result=confirmation_failed reason=chrome_not_running"
            )
            return False
        reacquired = enumerate_raw_chrome_windows(
            api,
            reacquired_applications,
        )
        _log_discovery(logger, reacquired, stage="post_probe")
        logger.info(
            "event=browser_fullscreen_probe browser=chrome result=reacquired "
            "raw_window_count=%s",
            len(reacquired.windows),
        )
        confirmed = identify_confirmed_boss_windows(reacquired.windows)
        if not confirmed:
            reason = (
                "no_ax_windows"
                if not reacquired.windows
                else "boss_title_not_confirmed"
            )
            logger.error(
                "event=browser_fullscreen_probe browser=chrome "
                "result=confirmation_failed reason=%s",
                reason,
            )
            return False

        window = min(
            confirmed,
            key=lambda candidate: _post_probe_selection_key(
                api,
                probe,
                candidate,
            ),
        )
        correlated = _windows_correlate(api, probe, window)
        if correlated and window.fullscreen is not True:
            logger.error(
                "event=browser_fullscreen_probe browser=chrome "
                "result=confirmation_failed reason=fullscreen_state_changed"
            )
            return False
        logger.info(
            "event=browser_fullscreen_probe browser=chrome "
            "result=confirmed_boss correlated=%s mode=%s",
            str(correlated).lower(),
            _window_mode(window),
        )
        return _activate_and_verify_window(
            logger,
            api,
            window,
            stage="post_probe_confirmed",
        )
    except Exception as exc:
        logger.error(
            "event=browser_window_activate browser=chrome result=failed "
            "reason=api_error error_type=%s",
            type(exc).__name__,
        )
        return False


__all__ = [
    "ACTIVATION_VERIFY_ATTEMPTS",
    "ACTIVATION_VERIFY_INTERVAL_SECONDS",
    "ACTIVATION_VERIFY_TIMEOUT_SECONDS",
    "AX_FULLSCREEN_ATTRIBUTE",
    "CHROME_BUNDLE_ID",
    "ChromeWindow",
    "ChromeWindowDiscovery",
    "NativeMacOSBrowserAPI",
    "TitleState",
    "bring_boss_foreground",
    "enumerate_raw_chrome_windows",
    "identify_confirmed_boss_windows",
    "identify_fullscreen_probe_candidates",
    "is_boss_window_title",
]
