from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import platform_services
from platform_services import browser_window
import simple_brush


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def chrome_window(
    element,
    title,
    *,
    title_state=None,
    minimized=False,
    fullscreen=False,
    focused=False,
    main=False,
    application="chrome-app",
    application_active=False,
    application_order=0,
    window_order=0,
):
    if title_state is None:
        if title is None:
            title_state = browser_window.TitleState.UNAVAILABLE
            title = ""
        elif not str(title).strip():
            title_state = browser_window.TitleState.EMPTY
            title = ""
        else:
            title_state = browser_window.TitleState.PRESENT
    return browser_window.ChromeWindow(
        application=application,
        application_element=f"ax-{application}",
        element=element,
        title=title,
        title_state=title_state,
        minimized=minimized,
        fullscreen=fullscreen,
        focused=focused,
        main=main,
        application_active=application_active,
        application_order=application_order,
        window_order=window_order,
    )


class FakeNativeBrowserAPI:
    def __init__(self, windows=None):
        self.available = True
        self.trusted = True
        self.applications = ["chrome-app"]
        self.windows = {"chrome-app": list(windows or [])}
        self.restore_result = True
        self.activation_result = True
        self.raise_result = True
        self.verification_results = [True]
        self.enumeration_sequences = []
        self.events = []

    def is_available(self):
        self.events.append("available")
        return self.available

    def running_applications(self, bundle_id):
        self.events.append(("lookup", bundle_id))
        return list(self.applications)

    def accessibility_trusted(self):
        self.events.append("trusted")
        return self.trusted

    def enumerate_windows(self, application, application_order):
        self.events.append(("enumerate", application, application_order))
        if self.enumeration_sequences:
            value = self.enumeration_sequences.pop(0)
        else:
            value = self.windows.get(application, [])
        return None if value is None else list(value)

    @staticmethod
    def elements_equal(left, right):
        return left == right

    def restore_window(self, window):
        self.events.append(("restore", window.element))
        return self.restore_result

    def activate_application(self, window):
        self.events.append(("activate", window.element))
        return self.activation_result

    def raise_and_focus_window(self, window):
        self.events.append(("raise_focus", window.element))
        return self.raise_result

    def verify_activation(self, window):
        self.events.append(("verify", window.element))
        if len(self.verification_results) > 1:
            return self.verification_results.pop(0)
        return self.verification_results[0]


class BrowserWindowMatchingTests(unittest.TestCase):
    def test_boss_title_is_eligible(self):
        self.assertTrue(
            browser_window.is_boss_window_title(
                "BOSS直聘 - Google Chrome"
            )
        )

    def test_zhipin_title_is_case_insensitive(self):
        self.assertTrue(
            browser_window.is_boss_window_title(
                "职位详情 - ZhiPin - Google Chrome"
            )
        )

    def test_unrelated_chrome_window_is_rejected(self):
        self.assertFalse(
            browser_window.is_boss_window_title("GitHub - Google Chrome")
        )
        self.assertFalse(browser_window.is_boss_window_title(None))

    def test_fullscreen_does_not_make_an_unrelated_title_eligible(self):
        window = chrome_window(
            "github-fullscreen",
            "GitHub - Google Chrome",
            fullscreen=True,
        )

        self.assertTrue(window.fullscreen)
        self.assertFalse(browser_window.is_boss_window_title(window.title))


class BrowserWindowRawDiscoveryTests(unittest.TestCase):
    def test_raw_discovery_is_separate_from_confirmed_boss_eligibility(self):
        raw = [
            chrome_window("empty-fullscreen", "", fullscreen=True),
            chrome_window("boss", "BOSS直聘 - Google Chrome"),
        ]
        api = FakeNativeBrowserAPI(raw)

        discovery = browser_window.enumerate_raw_chrome_windows(
            api,
            api.applications,
        )

        self.assertEqual(discovery.windows, tuple(raw))
        self.assertEqual(
            browser_window.identify_confirmed_boss_windows(discovery.windows),
            [raw[1]],
        )

    def test_title_states_do_not_collapse_empty_and_unavailable(self):
        empty = chrome_window("empty", "")
        unavailable = chrome_window("unavailable", None)

        self.assertIs(empty.title_state, browser_window.TitleState.EMPTY)
        self.assertIs(
            unavailable.title_state,
            browser_window.TitleState.UNAVAILABLE,
        )
        self.assertEqual(
            browser_window.identify_confirmed_boss_windows(
                [empty, unavailable]
            ),
            [],
        )

    def test_empty_title_fullscreen_window_is_probe_only(self):
        window = chrome_window("empty-fullscreen", "", fullscreen=True)

        self.assertEqual(
            browser_window.identify_fullscreen_probe_candidates([window]),
            [window],
        )
        self.assertEqual(
            browser_window.identify_confirmed_boss_windows([window]),
            [],
        )

    def test_unavailable_title_fullscreen_window_is_probe_only(self):
        window = chrome_window("unknown-fullscreen", None, fullscreen=True)

        self.assertEqual(
            browser_window.identify_fullscreen_probe_candidates([window]),
            [window],
        )
        self.assertEqual(
            browser_window.identify_confirmed_boss_windows([window]),
            [],
        )

    def test_explicitly_minimized_fullscreen_window_is_not_probe_safe(self):
        window = chrome_window(
            "contradictory",
            "",
            fullscreen=True,
            minimized=True,
        )

        self.assertEqual(
            browser_window.identify_fullscreen_probe_candidates([window]),
            [],
        )


class BrowserWindowServiceTests(unittest.TestCase):
    def setUp(self):
        self.logger = Mock()

    def bring(self, api):
        with patch.object(browser_window.time, "sleep"):
            return browser_window.bring_boss_foreground(
                self.logger,
                native_api=api,
            )

    def test_chrome_not_running_fails_without_accessibility_or_activation(self):
        api = FakeNativeBrowserAPI()
        api.applications = []

        self.assertFalse(self.bring(api))

        self.assertEqual(
            api.events,
            ["available", ("lookup", browser_window.CHROME_BUNDLE_ID)],
        )

    def test_chrome_lookup_uses_canonical_bundle_identifier(self):
        api = FakeNativeBrowserAPI()
        api.applications = []

        self.bring(api)

        self.assertIn(
            ("lookup", "com.google.Chrome"),
            api.events,
        )

    def test_running_chrome_without_eligible_window_fails_closed(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("github", "GitHub - Google Chrome")]
        )

        self.assertFalse(self.bring(api))
        self.assertFalse(
            any(event[0] == "activate" for event in api.events if isinstance(event, tuple))
        )

    def test_boss_window_is_selected_and_activated(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("boss", "BOSS直聘 - Google Chrome")]
        )

        self.assertTrue(self.bring(api))

        self.assertIn(("activate", "boss"), api.events)
        self.assertIn(("raise_focus", "boss"), api.events)

    def test_confirmed_normal_boss_uses_direct_path_without_probe(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window("boss", "BOSS直聘 - Google Chrome"),
                chrome_window("unknown-fullscreen", "", fullscreen=True),
            ]
        )

        self.assertTrue(self.bring(api))

        self.assertIn(("activate", "boss"), api.events)
        self.assertNotIn(("activate", "unknown-fullscreen"), api.events)
        self.assertEqual(
            api.events.count(("enumerate", "chrome-app", 0)),
            1,
        )

    def test_fullscreen_boss_window_is_activated_without_exiting_fullscreen(self):
        window = chrome_window(
            "boss-fullscreen",
            "BOSS直聘 - Google Chrome",
            fullscreen=True,
        )
        api = FakeNativeBrowserAPI([window])

        self.assertTrue(self.bring(api))

        self.assertTrue(window.fullscreen)
        self.assertNotIn(("restore", "boss-fullscreen"), api.events)
        self.assertIn(("activate", "boss-fullscreen"), api.events)
        self.assertIn(("raise_focus", "boss-fullscreen"), api.events)
        self.assertIn(("verify", "boss-fullscreen"), api.events)

    def test_fullscreen_verification_allows_a_delayed_space_transition(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window(
                    "boss-fullscreen",
                    "BOSS直聘 - Google Chrome",
                    fullscreen=True,
                )
            ]
        )
        api.verification_results = [False, False, True]

        self.assertTrue(self.bring(api))

        self.assertEqual(
            api.events.count(("verify", "boss-fullscreen")),
            3,
        )

    def test_fullscreen_activation_times_out_and_fails_closed(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window(
                    "boss-fullscreen",
                    "BOSS直聘 - Google Chrome",
                    fullscreen=True,
                )
            ]
        )
        api.verification_results = [False]

        self.assertFalse(self.bring(api))

        self.assertEqual(
            api.events.count(("verify", "boss-fullscreen")),
            browser_window.ACTIVATION_VERIFY_ATTEMPTS,
        )

    def test_fullscreen_can_verify_when_ax_focus_request_is_rejected(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window(
                    "boss-fullscreen",
                    "BOSS直聘 - Google Chrome",
                    fullscreen=True,
                )
            ]
        )
        api.raise_result = False

        self.assertTrue(self.bring(api))

        self.assertIn(("raise_focus", "boss-fullscreen"), api.events)
        self.assertIn(("verify", "boss-fullscreen"), api.events)

    def test_zhipin_window_is_selected(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("zhipin", "ZHIpIn - Google Chrome")]
        )

        self.assertTrue(self.bring(api))

        self.assertIn(("activate", "zhipin"), api.events)

    def test_minimized_window_restores_before_activation_and_raise(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window(
                    "boss",
                    "BOSS直聘 - Google Chrome",
                    minimized=True,
                )
            ]
        )

        self.assertTrue(self.bring(api))

        actions = [
            event[0]
            for event in api.events
            if isinstance(event, tuple)
            and event[0] in {"restore", "activate", "raise_focus", "verify"}
        ]
        self.assertEqual(
            actions,
            ["restore", "activate", "raise_focus", "verify"],
        )

    def test_non_minimized_window_is_not_restored(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("boss", "BOSS直聘 - Google Chrome")]
        )

        self.assertTrue(self.bring(api))

        self.assertNotIn(("restore", "boss"), api.events)
        self.assertIn(("activate", "boss"), api.events)

    def test_minimized_restore_failure_prevents_activation(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window(
                    "boss",
                    "BOSS直聘 - Google Chrome",
                    minimized=True,
                )
            ]
        )
        api.restore_result = False

        self.assertFalse(self.bring(api))

        self.assertIn(("restore", "boss"), api.events)
        self.assertNotIn(("activate", "boss"), api.events)

    def test_unreadable_minimized_state_fails_closed(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window(
                    "boss",
                    "BOSS直聘 - Google Chrome",
                    minimized=None,
                )
            ]
        )

        self.assertFalse(self.bring(api))

        self.assertNotIn(("activate", "boss"), api.events)

    def test_focused_eligible_window_wins_deterministically(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window(
                    "first",
                    "BOSS first - Google Chrome",
                    window_order=0,
                ),
                chrome_window(
                    "focused",
                    "BOSS focused - Google Chrome",
                    focused=True,
                    window_order=1,
                ),
            ]
        )

        self.assertTrue(self.bring(api))

        self.assertIn(("activate", "focused"), api.events)
        self.assertNotIn(("activate", "first"), api.events)

    def test_application_activation_failure_returns_false(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("boss", "BOSS直聘 - Google Chrome")]
        )
        api.activation_result = False

        self.assertFalse(self.bring(api))

        self.assertIn(("activate", "boss"), api.events)
        self.assertNotIn(("raise_focus", "boss"), api.events)

    def test_window_raise_or_focus_failure_returns_false(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("boss", "BOSS直聘 - Google Chrome")]
        )
        api.raise_result = False

        self.assertFalse(self.bring(api))

        self.assertNotIn(("verify", "boss"), api.events)

    def test_accessibility_unavailable_fails_before_window_enumeration(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("boss", "BOSS直聘 - Google Chrome")]
        )
        api.trusted = False

        self.assertFalse(self.bring(api))

        self.assertEqual(
            api.events,
            [
                "available",
                ("lookup", browser_window.CHROME_BUNDLE_ID),
                "trusted",
            ],
        )

    def test_native_api_unavailable_returns_false(self):
        api = FakeNativeBrowserAPI()
        api.available = False

        self.assertFalse(self.bring(api))

        self.assertEqual(api.events, ["available"])

    def test_ax_window_enumeration_failure_returns_false(self):
        api = FakeNativeBrowserAPI()
        api.windows["chrome-app"] = None

        self.assertFalse(self.bring(api))

        self.assertFalse(
            any(event[0] == "activate" for event in api.events if isinstance(event, tuple))
        )

    def test_native_exception_is_contained(self):
        api = FakeNativeBrowserAPI()
        api.running_applications = Mock(side_effect=RuntimeError("AX failure"))

        self.assertFalse(self.bring(api))

        self.logger.error.assert_called_once()

    def test_activation_verification_must_succeed(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("boss", "BOSS直聘 - Google Chrome")]
        )
        api.verification_results = [False]

        self.assertFalse(self.bring(api))

        verify_events = [
            event for event in api.events if event == ("verify", "boss")
        ]
        self.assertEqual(
            len(verify_events),
            browser_window.ACTIVATION_VERIFY_ATTEMPTS,
        )

    def test_success_logs_no_complete_window_title(self):
        sensitive_title = "Candidate Name - BOSS直聘 - Google Chrome"
        api = FakeNativeBrowserAPI(
            [chrome_window("boss", sensitive_title)]
        )

        self.assertTrue(self.bring(api))

        self.assertNotIn(sensitive_title, repr(self.logger.mock_calls))

    def test_unique_empty_title_fullscreen_probe_reacquires_and_confirms_boss(self):
        initial = chrome_window("fullscreen", "", fullscreen=True)
        confirmed = chrome_window(
            "fullscreen",
            "BOSS直聘 - Google Chrome",
            fullscreen=True,
            focused=True,
            application_active=True,
        )
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [[initial], [confirmed]]

        self.assertTrue(self.bring(api))

        self.assertEqual(
            api.events.count(("enumerate", "chrome-app", 0)),
            2,
        )
        self.assertEqual(api.events.count(("activate", "fullscreen")), 2)
        logged = repr(self.logger.mock_calls)
        self.assertIn("result=selected", logged)
        self.assertIn("result=reacquired", logged)
        self.assertIn("result=confirmed_boss", logged)

    def test_unique_unavailable_title_fullscreen_probe_is_allowed(self):
        initial = chrome_window("fullscreen", None, fullscreen=True)
        confirmed = chrome_window(
            "fullscreen",
            "zhipin - Google Chrome",
            fullscreen=True,
            focused=True,
        )
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [[initial], [confirmed]]

        self.assertTrue(self.bring(api))

        self.assertIn(("activate", "fullscreen"), api.events)

    def test_probe_then_unrelated_title_fails_confirmation(self):
        initial = chrome_window("fullscreen", "", fullscreen=True)
        unrelated = chrome_window(
            "fullscreen",
            "YouTube - Google Chrome",
            fullscreen=True,
            focused=True,
        )
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [[initial], [unrelated]]

        self.assertFalse(self.bring(api))

        self.assertEqual(api.events.count(("activate", "fullscreen")), 1)
        self.assertIn("boss_title_not_confirmed", repr(self.logger.mock_calls))

    def test_probe_then_title_remains_empty_fails_confirmation(self):
        initial = chrome_window("fullscreen", "", fullscreen=True)
        still_empty = chrome_window(
            "fullscreen",
            "",
            fullscreen=True,
            focused=True,
        )
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [[initial], [still_empty]]

        self.assertFalse(self.bring(api))

        self.assertEqual(api.events.count(("activate", "fullscreen")), 1)

    def test_probe_activation_failure_stops_before_reenumeration(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("fullscreen", "", fullscreen=True)]
        )
        api.activation_result = False

        self.assertFalse(self.bring(api))

        self.assertEqual(
            api.events.count(("enumerate", "chrome-app", 0)),
            1,
        )
        self.assertIn("reason=activation_failed", repr(self.logger.mock_calls))

    def test_probe_reenumeration_failure_fails_closed(self):
        initial = chrome_window("fullscreen", "", fullscreen=True)
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [[initial], None]

        self.assertFalse(self.bring(api))

        self.assertTrue(
            any(
                call.args
                and "result=confirmation_failed reason=%s" in call.args[0]
                and call.args[1:] == ("no_ax_windows",)
                for call in self.logger.error.call_args_list
            )
        )

    def test_correlated_probe_that_leaves_fullscreen_is_rejected(self):
        initial = chrome_window("fullscreen", "", fullscreen=True)
        changed = chrome_window(
            "fullscreen",
            "BOSS直聘 - Google Chrome",
            fullscreen=False,
            focused=True,
        )
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [[initial], [changed]]

        self.assertFalse(self.bring(api))

        self.assertEqual(api.events.count(("activate", "fullscreen")), 1)
        self.assertIn("fullscreen_state_changed", repr(self.logger.mock_calls))

    def test_post_probe_multiple_confirmed_windows_use_existing_focus_ranking(self):
        initial = chrome_window("fullscreen", "", fullscreen=True)
        correlated = chrome_window(
            "fullscreen",
            "BOSS first - Google Chrome",
            fullscreen=True,
            window_order=0,
        )
        focused = chrome_window(
            "focused-boss",
            "BOSS focused - Google Chrome",
            fullscreen=True,
            focused=True,
            window_order=1,
        )
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [[initial], [correlated, focused]]

        self.assertTrue(self.bring(api))

        self.assertEqual(api.events.count(("activate", "fullscreen")), 1)
        self.assertIn(("activate", "focused-boss"), api.events)

    def test_post_probe_confirmed_target_still_requires_final_verification(self):
        initial = chrome_window("fullscreen", "", fullscreen=True)
        confirmed = chrome_window(
            "fullscreen",
            "BOSS直聘 - Google Chrome",
            fullscreen=True,
            focused=True,
        )
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [[initial], [confirmed]]
        api.verification_results = [True, False]

        self.assertFalse(self.bring(api))

        self.assertEqual(
            api.events.count(("verify", "fullscreen")),
            1 + browser_window.ACTIVATION_VERIFY_ATTEMPTS,
        )

    def test_two_unconfirmed_fullscreen_windows_fail_ambiguous_without_activation(self):
        api = FakeNativeBrowserAPI(
            [
                chrome_window("first", "", fullscreen=True),
                chrome_window("second", None, fullscreen=True),
            ]
        )

        self.assertFalse(self.bring(api))

        self.assertFalse(
            any(
                event[0] == "activate"
                for event in api.events
                if isinstance(event, tuple)
            )
        )
        self.assertIn(
            "result=ambiguous_fullscreen_candidates",
            repr(self.logger.mock_calls),
        )

    def test_one_unknown_fullscreen_plus_normal_unrelated_may_probe(self):
        initial_fullscreen = chrome_window(
            "fullscreen",
            "",
            fullscreen=True,
        )
        unrelated = chrome_window("github", "GitHub - Google Chrome")
        confirmed = chrome_window(
            "fullscreen",
            "BOSS直聘 - Google Chrome",
            fullscreen=True,
            focused=True,
        )
        api = FakeNativeBrowserAPI()
        api.enumeration_sequences = [
            [unrelated, initial_fullscreen],
            [unrelated, confirmed],
        ]

        self.assertTrue(self.bring(api))

        self.assertIn(("activate", "fullscreen"), api.events)
        self.assertNotIn(("activate", "github"), api.events)

    def test_no_confirmed_or_fullscreen_window_fails_without_activation(self):
        api = FakeNativeBrowserAPI(
            [chrome_window("github", "GitHub - Google Chrome")]
        )

        self.assertFalse(self.bring(api))

        self.assertNotIn(("activate", "github"), api.events)

    def test_discovery_diagnostics_are_counted_and_sanitized(self):
        sensitive_title = "Candidate Name - BOSS直聘 - Google Chrome"
        api = FakeNativeBrowserAPI(
            [
                chrome_window("boss", sensitive_title, fullscreen=False),
                chrome_window("empty", "", fullscreen=True),
                chrome_window("unavailable", None, fullscreen=False),
            ]
        )

        self.assertTrue(self.bring(api))

        discovery_call = next(
            call
            for call in self.logger.info.call_args_list
            if call.args
            and str(call.args[0]).startswith("event=browser_window_discovery")
        )
        self.assertEqual(
            discovery_call.args[1:8],
            ("initial", 3, 1, 1, 1, 1, 1),
        )
        self.assertNotIn(sensitive_title, repr(self.logger.mock_calls))

    def test_running_chrome_with_zero_ax_windows_logs_distinct_reason(self):
        api = FakeNativeBrowserAPI([])

        self.assertFalse(self.bring(api))

        self.assertIn("reason=no_ax_windows", repr(self.logger.mock_calls))


class NativeMacOSBrowserAPITests(unittest.TestCase):
    def setUp(self):
        self.appkit = Mock()
        self.appkit.NSApplicationActivateAllWindows = 1
        self.appkit.NSApplicationActivateIgnoringOtherApps = 2
        self.ax = Mock()
        self.ax.kAXErrorSuccess = 0
        self.ax.kAXWindowsAttribute = "AXWindows"
        self.ax.kAXFocusedWindowAttribute = "AXFocusedWindow"
        self.ax.kAXTitleAttribute = "AXTitle"
        self.ax.kAXMinimizedAttribute = "AXMinimized"
        self.ax.kAXFullScreenAttribute = "AXFullScreen"
        self.ax.kAXFocusedAttribute = "AXFocused"
        self.ax.kAXMainAttribute = "AXMain"
        self.ax.kAXFrontmostAttribute = "AXFrontmost"
        self.ax.kAXRaiseAction = "AXRaise"
        self.api = browser_window.NativeMacOSBrowserAPI(
            appkit=self.appkit,
            accessibility=self.ax,
        )

    def make_window(self, application=None):
        return chrome_window(
            "boss-window",
            "BOSS直聘 - Google Chrome",
            application=application or Mock(),
        )

    def test_running_application_lookup_uses_appkit_bundle_identity(self):
        application = Mock()
        application.isTerminated.return_value = False
        application.isActive.return_value = True
        application.processIdentifier.return_value = 42
        running_application = self.appkit.NSRunningApplication
        lookup = running_application.runningApplicationsWithBundleIdentifier_
        lookup.return_value = [application]

        self.assertEqual(
            self.api.running_applications("com.google.Chrome"),
            [application],
        )

        lookup.assert_called_once_with("com.google.Chrome")

    def test_window_enumeration_reads_accessibility_state(self):
        application = Mock()
        application.processIdentifier.return_value = 42
        application.isActive.return_value = True
        self.ax.AXUIElementCreateApplication.return_value = "ax-application"

        attributes = {
            ("ax-application", "AXWindows"): (0, ["boss-window"]),
            ("ax-application", "AXFocusedWindow"): (0, "boss-window"),
            ("boss-window", "AXTitle"): (
                0,
                "BOSS直聘 - Google Chrome",
            ),
            ("boss-window", "AXMinimized"): (0, True),
            ("boss-window", "AXFullScreen"): (0, False),
            ("boss-window", "AXFocused"): (0, False),
            ("boss-window", "AXMain"): (0, True),
        }
        self.ax.AXUIElementCopyAttributeValue.side_effect = (
            lambda element, attribute, _output: attributes[(element, attribute)]
        )

        windows = self.api.enumerate_windows(application, 0)

        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].title, "BOSS直聘 - Google Chrome")
        self.assertIs(
            windows[0].title_state,
            browser_window.TitleState.PRESENT,
        )
        self.assertTrue(windows[0].minimized)
        self.assertFalse(windows[0].fullscreen)
        self.assertTrue(windows[0].focused)
        self.assertTrue(windows[0].main)
        self.ax.AXUIElementSetMessagingTimeout.assert_called_once_with(
            "ax-application",
            browser_window.AX_MESSAGING_TIMEOUT_SECONDS,
        )

    def test_window_enumeration_distinguishes_empty_and_unavailable_titles(self):
        application = Mock()
        application.processIdentifier.return_value = 42
        application.isActive.return_value = False
        self.ax.AXUIElementCreateApplication.return_value = "ax-application"
        attributes = {
            ("ax-application", "AXWindows"): (
                0,
                ["empty-window", "unavailable-window"],
            ),
            ("ax-application", "AXFocusedWindow"): (1, None),
            ("empty-window", "AXTitle"): (0, ""),
            ("empty-window", "AXMinimized"): (0, False),
            ("empty-window", "AXFullScreen"): (0, True),
            ("empty-window", "AXFocused"): (0, False),
            ("empty-window", "AXMain"): (0, False),
            ("unavailable-window", "AXTitle"): (1, None),
            ("unavailable-window", "AXMinimized"): (0, False),
            ("unavailable-window", "AXFullScreen"): (0, True),
            ("unavailable-window", "AXFocused"): (0, False),
            ("unavailable-window", "AXMain"): (0, False),
        }
        self.ax.AXUIElementCopyAttributeValue.side_effect = (
            lambda element, attribute, _output: attributes[(element, attribute)]
        )

        windows = self.api.enumerate_windows(application, 0)

        self.assertEqual(
            [window.title_state for window in windows],
            [
                browser_window.TitleState.EMPTY,
                browser_window.TitleState.UNAVAILABLE,
            ],
        )

    def test_restore_writes_and_verifies_ax_minimized_false(self):
        window = self.make_window()
        self.ax.AXUIElementSetAttributeValue.return_value = 0
        self.ax.AXUIElementCopyAttributeValue.return_value = (0, False)

        self.assertTrue(self.api.restore_window(window))

        self.ax.AXUIElementSetAttributeValue.assert_called_once_with(
            window.element,
            "AXMinimized",
            False,
        )

    def test_activation_and_raise_use_appkit_and_ax(self):
        application = Mock()
        application.activateWithOptions_.return_value = True
        window = self.make_window(application)
        self.ax.AXUIElementPerformAction.return_value = 0
        self.ax.AXUIElementSetAttributeValue.return_value = 0

        self.assertTrue(self.api.activate_application(window))
        self.assertTrue(self.api.raise_and_focus_window(window))

        application.activateWithOptions_.assert_called_once_with(3)
        self.ax.AXUIElementPerformAction.assert_called_once_with(
            window.element,
            "AXRaise",
        )
        self.assertEqual(
            self.ax.AXUIElementSetAttributeValue.call_count,
            3,
        )

    def test_window_enumeration_reads_explicit_fullscreen_state(self):
        application = Mock()
        application.processIdentifier.return_value = 42
        application.isActive.return_value = False
        self.ax.AXUIElementCreateApplication.return_value = "ax-application"
        attributes = {
            ("ax-application", "AXWindows"): (0, ["boss-window"]),
            ("ax-application", "AXFocusedWindow"): (1, None),
            ("boss-window", "AXTitle"): (0, "BOSS直聘 - Google Chrome"),
            ("boss-window", "AXMinimized"): (0, False),
            ("boss-window", "AXFullScreen"): (0, True),
            ("boss-window", "AXFocused"): (0, False),
            ("boss-window", "AXMain"): (0, False),
        }
        self.ax.AXUIElementCopyAttributeValue.side_effect = (
            lambda element, attribute, _output: attributes[(element, attribute)]
        )

        windows = self.api.enumerate_windows(application, 0)

        self.assertEqual(len(windows), 1)
        self.assertTrue(windows[0].fullscreen)

    def test_fullscreen_verification_accepts_frontmost_space_without_ax_focus(self):
        application = Mock()
        application.isActive.return_value = True
        window = self.make_window(application)
        window = browser_window.ChromeWindow(
            **{
                **window.__dict__,
                "fullscreen": True,
            }
        )
        attributes = {
            (window.element, "AXMinimized"): (0, False),
            (window.application_element, "AXFrontmost"): (0, True),
            (window.application_element, "AXFocusedWindow"): (1, None),
            (window.element, "AXFocused"): (0, False),
            (window.element, "AXMain"): (0, False),
            (window.element, "AXFullScreen"): (0, True),
        }
        self.ax.AXUIElementCopyAttributeValue.side_effect = (
            lambda element, attribute, _output: attributes[(element, attribute)]
        )

        self.assertTrue(self.api.verify_activation(window))

    def test_fullscreen_verification_rejects_lost_fullscreen_state(self):
        application = Mock()
        application.isActive.return_value = True
        window = self.make_window(application)
        window = browser_window.ChromeWindow(
            **{
                **window.__dict__,
                "fullscreen": True,
            }
        )
        attributes = {
            (window.element, "AXMinimized"): (0, False),
            (window.application_element, "AXFrontmost"): (0, True),
            (window.application_element, "AXFocusedWindow"): (0, window.element),
            (window.element, "AXFocused"): (0, True),
            (window.element, "AXMain"): (0, True),
            (window.element, "AXFullScreen"): (0, False),
        }
        self.ax.AXUIElementCopyAttributeValue.side_effect = (
            lambda element, attribute, _output: attributes[(element, attribute)]
        )

        self.assertFalse(self.api.verify_activation(window))

    def test_fullscreen_verification_rejects_a_different_focused_window(self):
        application = Mock()
        application.isActive.return_value = True
        window = self.make_window(application)
        window = browser_window.ChromeWindow(
            **{
                **window.__dict__,
                "fullscreen": True,
            }
        )
        attributes = {
            (window.element, "AXMinimized"): (0, False),
            (window.application_element, "AXFrontmost"): (0, True),
            (window.application_element, "AXFocusedWindow"): (
                0,
                "different-window",
            ),
            (window.element, "AXFocused"): (0, False),
            (window.element, "AXMain"): (0, False),
            (window.element, "AXFullScreen"): (0, True),
        }
        self.ax.AXUIElementCopyAttributeValue.side_effect = (
            lambda element, attribute, _output: attributes[(element, attribute)]
        )

        self.assertFalse(self.api.verify_activation(window))


class BrowserWindowStructureTests(unittest.TestCase):
    def test_production_browser_path_has_no_windows_implementation(self):
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                REPOSITORY_ROOT / "simple_brush.py",
                REPOSITORY_ROOT / "platform_services" / "browser_window.py",
            )
        ).lower()
        for forbidden in (
            "chrome.exe",
            "msedge.exe",
            "win32gui",
            "win32con",
            "win32process",
            "enumwindows",
            "setforegroundwindow",
            "sw_restore",
            "kernel32",
        ):
            self.assertNotIn(forbidden, source)

    def test_business_module_has_no_appkit_or_ax_details(self):
        source = (REPOSITORY_ROOT / "simple_brush.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "AppKit",
            "ApplicationServices",
            "AXUIElement",
            "kAX",
            "NSRunningApplication",
        ):
            self.assertNotIn(forbidden, source)

    def test_only_required_pyobjc_frameworks_are_direct_dependencies(self):
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("pyobjc-framework-Cocoa>=12.2.2", requirements)
        self.assertIn(
            "pyobjc-framework-ApplicationServices>=12.2.2",
            requirements,
        )
        self.assertNotIn("\npyobjc\n", f"\n{requirements}")


class BrowserWindowApplicationIntegrationTests(unittest.TestCase):
    def test_simple_brush_entry_delegates_to_platform_service(self):
        with patch.object(
            simple_brush.platform_services,
            "bring_boss_foreground",
            return_value=True,
        ) as bring:
            self.assertTrue(simple_brush.bring_boss_foreground())

        bring.assert_called_once_with(simple_brush.logger)

    def test_platform_package_exports_browser_entry(self):
        self.assertIs(
            platform_services.bring_boss_foreground,
            browser_window.bring_boss_foreground,
        )


if __name__ == "__main__":
    unittest.main()
