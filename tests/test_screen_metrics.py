from types import SimpleNamespace
import unittest

import numpy as np

from ocr_calibration import ScreenRegion
from ocr_detector import MSSScreenCapture
from platform_services.screen_metrics import (
    CaptureFrameInvariant,
    CaptureGeometryInvariantError,
    collect_screen_metrics,
    classify_scale_relation,
    observe_capture,
    observe_overlay,
)


class FakeMSSContext:
    def __init__(self, monitors, grabber=None):
        self.monitors = monitors
        self.grabber = grabber

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def grab(self, monitor):
        return self.grabber(monitor)


class FakeScreenshot:
    def __init__(self, width, height, *, array_width=None, array_height=None):
        self.width = width
        self.height = height
        self.array = np.zeros(
            (
                height if array_height is None else array_height,
                width if array_width is None else array_width,
                4,
            ),
            dtype=np.uint8,
        )

    def __array__(self, dtype=None, copy=None):
        array = self.array if dtype is None else self.array.astype(dtype)
        return array.copy() if copy else array


class ScreenMetricCollectionTests(unittest.TestCase):
    def test_collects_pyautogui_mss_and_native_metrics_without_transforming(self):
        pyautogui = SimpleNamespace(
            size=lambda: (1440, 900),
            position=lambda: (321, 654),
        )
        monitors = [
            {"left": 0, "top": 0, "width": 3000, "height": 1800},
            {"left": 0, "top": 0, "width": 1440, "height": 900},
            {
                "left": 1440,
                "top": 0,
                "width": 1560,
                "height": 1800,
                "is_primary": True,
            },
        ]
        frame = SimpleNamespace(
            origin=SimpleNamespace(x=0, y=0),
            size=SimpleNamespace(width=1512, height=982),
        )
        visible = SimpleNamespace(
            origin=SimpleNamespace(x=0, y=37),
            size=SimpleNamespace(width=1512, height=920),
        )
        native = SimpleNamespace(
            frame=lambda: frame,
            visibleFrame=lambda: visible,
            backingScaleFactor=lambda: 2.0,
        )

        result = collect_screen_metrics(
            pyautogui_module=pyautogui,
            mss_factory=lambda: FakeMSSContext(monitors),
            native_screen=native,
        )

        self.assertEqual(result.pyautogui_size, (1440, 900))
        self.assertEqual((result.pyautogui_position.x, result.pyautogui_position.y), (321, 654))
        self.assertEqual(result.mss_virtual_monitor.width, 3000)
        self.assertEqual(result.mss_primary_monitor.left, 1440)
        self.assertTrue(result.mss_primary_monitor.is_primary)
        self.assertEqual(result.native_screen.frame.width, 1512)
        self.assertEqual(result.native_screen.visible_frame.top, 37)
        self.assertEqual(result.native_screen.backing_scale_factor, 2.0)


class ScaleObservationTests(unittest.TestCase):
    def observation(self, overlay_width, overlay_height, monitor_width, monitor_height):
        return observe_overlay(
            canvas_width=overlay_width,
            canvas_height=overlay_height,
            root_width=overlay_width,
            root_height=overlay_height,
            event_x=overlay_width,
            event_y=overlay_height,
            monitor=ScreenRegion(0, 0, monitor_width, monitor_height),
        )

    def test_one_x_relation(self):
        result = self.observation(1440, 900, 1440, 900)
        self.assertEqual((result.overlay_to_mss_scale_x, result.overlay_to_mss_scale_y), (1.0, 1.0))
        self.assertEqual(result.scale_relation, "1x")
        self.assertTrue(result.event_within_bounds)

    def test_two_x_relation_is_observed_without_coordinate_rewrite(self):
        result = self.observation(1440, 900, 2880, 1800)
        self.assertEqual((result.overlay_to_mss_scale_x, result.overlay_to_mss_scale_y), (2.0, 2.0))
        self.assertEqual(result.scale_relation, "2x")

    def test_asymmetric_relation_is_not_averaged(self):
        result = self.observation(1440, 900, 2880, 900)
        self.assertEqual(result.scale_relation, "asymmetric")
        self.assertNotEqual(result.overlay_to_mss_scale_x, result.overlay_to_mss_scale_y)

    def test_fractional_relation_is_preserved(self):
        result = self.observation(1000, 800, 1500, 1200)
        self.assertEqual((result.overlay_to_mss_scale_x, result.overlay_to_mss_scale_y), (1.5, 1.5))
        self.assertEqual(result.scale_relation, "fractional")

    def test_one_pixel_release_tolerance_and_larger_outside_release(self):
        tolerated = observe_overlay(
            canvas_width=100,
            canvas_height=80,
            root_width=100,
            root_height=80,
            event_x=101,
            event_y=-1,
            monitor=ScreenRegion(0, 0, 100, 80),
        )
        rejected = observe_overlay(
            canvas_width=100,
            canvas_height=80,
            root_width=100,
            root_height=80,
            event_x=102,
            event_y=20,
            monitor=ScreenRegion(0, 0, 100, 80),
        )
        self.assertTrue(tolerated.event_within_bounds)
        self.assertFalse(rejected.event_within_bounds)

    def test_invalid_scale_is_unavailable(self):
        self.assertEqual(classify_scale_relation(float("nan"), 1.0), "unavailable")


class CaptureInvariantTests(unittest.TestCase):
    @staticmethod
    def metrics(requested_width, requested_height, actual_width, actual_height, **array_overrides):
        region = ScreenRegion(10, 20, requested_width, requested_height)
        screenshot = FakeScreenshot(actual_width, actual_height, **array_overrides)
        return observe_capture(region, screenshot, np.asarray(screenshot))

    def test_one_x_expected_and_actual_pass(self):
        metrics = self.metrics(500, 400, 500, 400)
        CaptureFrameInvariant.establish(metrics).validate(metrics)

    def test_two_x_passes_only_when_session_expectation_is_two_x(self):
        two_x = self.metrics(500, 400, 1000, 800)
        CaptureFrameInvariant.establish(two_x).validate(two_x)
        with self.assertRaises(CaptureGeometryInvariantError):
            CaptureFrameInvariant(1.0, 1.0).validate(two_x)

    def test_ndarray_height_mismatch_fails(self):
        metrics = self.metrics(500, 400, 500, 400, array_height=399)
        with self.assertRaises(CaptureGeometryInvariantError):
            CaptureFrameInvariant(1.0, 1.0).validate(metrics)

    def test_asymmetric_scale_cannot_establish_an_invariant(self):
        metrics = self.metrics(500, 400, 1000, 400)
        with self.assertRaises(CaptureGeometryInvariantError):
            CaptureFrameInvariant.establish(metrics)

    def test_zero_requested_dimension_is_controlled_failure(self):
        with self.assertRaises(CaptureGeometryInvariantError):
            self.metrics(0, 400, 500, 400)

    def test_production_capture_establishes_from_full_monitor_and_returns_unchanged_bgr(self):
        monitors = [
            {"left": 0, "top": 0, "width": 100, "height": 80},
            {"left": 0, "top": 0, "width": 100, "height": 80, "is_primary": True},
        ]

        def grabber(monitor):
            return FakeScreenshot(monitor["width"], monitor["height"])

        capture = MSSScreenCapture(
            mss_factory=lambda: FakeMSSContext(monitors, grabber),
            numpy_module=np,
        )
        result = capture.capture(ScreenRegion(10, 20, 5, 4))

        self.assertEqual(result.shape, (4, 5, 3))
        self.assertEqual(capture.initial_measurement.screenshot_size, (100, 80))
        self.assertEqual(capture.last_capture_metrics.screenshot_size, (5, 4))

    def test_production_capture_fails_closed_before_returning_malformed_frame(self):
        monitors = [
            {"left": 0, "top": 0, "width": 100, "height": 80},
            {"left": 0, "top": 0, "width": 100, "height": 80, "is_primary": True},
        ]

        def grabber(monitor):
            if monitor["width"] == 100:
                return FakeScreenshot(100, 80)
            return FakeScreenshot(monitor["width"], monitor["height"], array_height=3)

        capture = MSSScreenCapture(
            mss_factory=lambda: FakeMSSContext(monitors, grabber),
            numpy_module=np,
        )
        with self.assertLogs("ocr_detector", level="ERROR") as logs:
            with self.assertRaises(CaptureGeometryInvariantError):
                capture.capture(ScreenRegion(10, 20, 5, 4))
        self.assertIn("event=capture_geometry_invariant result=failed", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()

