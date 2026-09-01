import inspect
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ocr_calibration import (
    CalibrationCancelled,
    ScreenRegion,
    physical_point_from_overlay,
    region_from_points,
    select_screen_region,
)


class CalibrationTests(unittest.TestCase):
    def test_region_supports_reverse_drag(self):
        self.assertEqual(
            region_from_points((500, 400), (100, 150)),
            ScreenRegion(left=100, top=150, width=400, height=250),
        )

    def test_small_region_is_rejected(self):
        with self.assertRaises(ValueError):
            region_from_points((0, 0), (10, 10), min_size=80)

    def test_smaller_focus_region_can_use_a_custom_minimum(self):
        self.assertEqual(
            region_from_points((400, 350), (501, 401), min_size=20),
            ScreenRegion(left=400, top=350, width=101, height=51),
        )

    def test_screen_region_selector_keeps_ocr_prompt_defaults(self):
        parameters = inspect.signature(select_screen_region).parameters
        self.assertEqual(parameters["min_size"].default, 80)
        self.assertEqual(
            parameters["instruction"].default,
            "拖动框选候选人详情区域 · Esc 取消",
        )
        self.assertEqual(parameters["subtitle"].default, "第一版仅支持主显示器")

    def test_overlay_points_scale_to_physical_pixels_at_150_percent(self):
        monitor = ScreenRegion(left=0, top=0, width=1920, height=1080)
        self.assertEqual(
            physical_point_from_overlay((640, 360), (1280, 720), monitor),
            (960, 540),
        )

    def test_overlay_points_include_primary_monitor_offset(self):
        monitor = ScreenRegion(left=100, top=50, width=1600, height=900)
        self.assertEqual(
            physical_point_from_overlay((800, 450), (1600, 900), monitor),
            (900, 500),
        )


class FakeTclError(Exception):
    pass


class FakeCalibrationRoot:
    def __init__(self, mode, events):
        self.mode = mode
        self.events = events
        self.bindings = {}
        self.canvas = None
        self.destroy_count = 0
        self.active = True

    def overrideredirect(self, value):
        self.events.append(("overrideredirect", value))

    def geometry(self, value):
        self.events.append(("geometry", value))

    def attributes(self, name, value):
        self.events.append(("attributes", name, value))

    def configure(self, **_kwargs):
        self.events.append(("configure",))

    def bind(self, name, callback):
        self.bindings[name] = callback

    def lift(self):
        self.events.append(("lift",))

    def focus_force(self):
        self.events.append(("focus_force",))

    def winfo_width(self):
        return 1000

    def winfo_height(self):
        return 800

    def mainloop(self):
        self.events.append(("mainloop",))
        if self.mode == "success":
            self.canvas.bindings["<ButtonPress-1>"](
                SimpleNamespace(x=100, y=100)
            )
            self.canvas.bindings["<ButtonRelease-1>"](
                SimpleNamespace(x=300, y=300)
            )
        elif self.mode == "cancel":
            self.bindings["<Escape>"]()
        else:
            raise RuntimeError("mainloop failed")

    def quit(self):
        self.events.append(("quit",))

    def grab_release(self):
        self.events.append(("grab_release",))

    def withdraw(self):
        self.events.append(("withdraw",))
        self.active = False

    def update_idletasks(self):
        self.events.append(("update_idletasks",))

    def destroy(self):
        self.events.append(("destroy",))
        self.destroy_count += 1
        self.active = False


class FakeCalibrationCanvas:
    def __init__(self, root, **_kwargs):
        self.root = root
        self.root.canvas = self
        self.bindings = {}

    def pack(self, **_kwargs):
        pass

    def create_text(self, *_args, **_kwargs):
        return "size-text"

    def create_rectangle(self, *_args, **_kwargs):
        return "selection"

    def delete(self, _item):
        pass

    def coords(self, *_args):
        pass

    def itemconfigure(self, *_args, **_kwargs):
        pass

    def bind(self, name, callback):
        self.bindings[name] = callback

    def winfo_width(self):
        return 1000

    def winfo_height(self):
        return 800


class CalibrationOverlayLifecycleTests(unittest.TestCase):
    def run_selector(self, mode, metrics_observer=None):
        events = []
        root = FakeCalibrationRoot(mode, events)
        fake_tk = SimpleNamespace(
            Tk=lambda: root,
            Canvas=FakeCalibrationCanvas,
            BOTH="both",
            TclError=FakeTclError,
        )
        monitor = ScreenRegion(left=0, top=0, width=1000, height=800)
        with (
            patch.dict(sys.modules, {"tkinter": fake_tk}),
            patch("ocr_calibration.primary_monitor_region", return_value=monitor),
        ):
            if mode == "success":
                result = select_screen_region(metrics_observer=metrics_observer)
            elif mode == "cancel":
                with self.assertRaises(CalibrationCancelled):
                    select_screen_region()
                result = None
            else:
                with self.assertRaisesRegex(RuntimeError, "mainloop failed"):
                    select_screen_region()
                result = None
        return result, root, events

    def assert_overlay_released(self, root, events):
        self.assertEqual(root.destroy_count, 1)
        self.assertFalse(root.active)
        self.assertIn(("attributes", "-topmost", False), events)
        self.assertLess(events.index(("withdraw",)), events.index(("destroy",)))
        self.assertLess(
            events.index(("update_idletasks",)),
            events.index(("destroy",)),
        )

    def test_successful_calibration_cleans_up_overlay_once(self):
        result, root, events = self.run_selector("success")

        self.assertEqual(result, ScreenRegion(100, 100, 200, 200))
        self.assert_overlay_released(root, events)

    def test_release_observes_realized_tk_sizes_not_placeholder_geometry(self):
        observations = []
        result, _root, _events = self.run_selector(
            "success",
            metrics_observer=observations.append,
        )

        self.assertEqual(result, ScreenRegion(100, 100, 200, 200))
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].canvas_size, (1000, 800))
        self.assertEqual(observations[0].root_size, (1000, 800))
        self.assertEqual(
            (observations[0].release_position.x, observations[0].release_position.y),
            (300, 300),
        )

    def test_cancelled_calibration_preserves_exception_and_cleans_up(self):
        _result, root, events = self.run_selector("cancel")

        self.assert_overlay_released(root, events)

    def test_mainloop_exception_is_preserved_and_cleans_up(self):
        _result, root, events = self.run_selector("exception")

        self.assert_overlay_released(root, events)


if __name__ == "__main__":
    unittest.main()
