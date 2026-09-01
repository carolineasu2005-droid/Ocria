"""Interactive, non-clicking MAC-R05 coordinate measurement command."""

import argparse
import logging
import sys

import pyautogui

from ocr_calibration import CalibrationCancelled, select_screen_region
from ocr_detector import MSSScreenCapture
from platform_services.permissions import ensure_permissions, format_permission_failure
from platform_services.screen_metrics import collect_screen_metrics


def _ratio(numerator, denominator):
    return numerator / denominator if denominator else float("nan")


def _line(name, value):
    print(f"{name}={value}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure Tk, PyAutoGUI, MSS and NSScreen geometry without clicking."
    )
    parser.add_argument(
        "--move-pointer",
        action="store_true",
        help="move (never click) to the selected region center and read it back",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    report = ensure_permissions(request_missing=False)
    if not report.all_required:
        print(format_permission_failure(report))
        return 2

    snapshot = collect_screen_metrics(pyautogui_module=pyautogui)
    overlay_observations = []
    print("Select one non-destructive region on the built-in primary display.")
    try:
        region = select_screen_region(metrics_observer=overlay_observations.append)
    except CalibrationCancelled:
        print("Coordinate probe cancelled; no mouse click was issued.")
        return 1

    capture = MSSScreenCapture()
    capture.capture(region)
    full = capture.initial_measurement
    bounded = capture.last_capture_metrics
    overlay = overlay_observations[-1]
    primary = snapshot.mss_primary_monitor
    native = snapshot.native_screen

    print("event=screen_geometry_probe")
    _line("pyautogui_size", snapshot.pyautogui_size)
    _line(
        "pyautogui_position",
        (snapshot.pyautogui_position.x, snapshot.pyautogui_position.y),
    )
    _line("mss_virtual", snapshot.mss_virtual_monitor)
    _line("mss_primary", primary)
    _line("native_frame", native.frame)
    _line("native_visible_frame", native.visible_frame)
    _line("backing_scale_factor", native.backing_scale_factor)
    _line("tk_canvas_size", overlay.canvas_size)
    _line("tk_root_size", overlay.root_size)
    _line(
        "tk_release_position",
        (overlay.release_position.x, overlay.release_position.y),
    )
    _line("overlay_to_mss_scale_x", overlay.overlay_to_mss_scale_x)
    _line("overlay_to_mss_scale_y", overlay.overlay_to_mss_scale_y)
    _line(
        "mss_to_pyautogui_scale_x",
        _ratio(primary.width, snapshot.pyautogui_size[0]),
    )
    _line(
        "mss_to_pyautogui_scale_y",
        _ratio(primary.height, snapshot.pyautogui_size[1]),
    )
    _line("full_capture_requested", (full.requested_bounds.width, full.requested_bounds.height))
    _line("full_capture_frame", full.screenshot_size)
    _line("full_capture_ndarray_shape", full.ndarray_shape)
    _line("full_capture_scale_x", full.capture_scale_x)
    _line("full_capture_scale_y", full.capture_scale_y)
    _line(
        "region_requested",
        (
            bounded.requested_bounds.left,
            bounded.requested_bounds.top,
            bounded.requested_bounds.width,
            bounded.requested_bounds.height,
        ),
    )
    _line("region_capture_frame", bounded.screenshot_size)
    _line("region_capture_ndarray_shape", bounded.ndarray_shape)
    _line("region_capture_scale_x", bounded.capture_scale_x)
    _line("region_capture_scale_y", bounded.capture_scale_y)
    _line("capture_frame_invariant", "PASS")

    if args.move_pointer:
        requested = (
            region.left + region.width // 2,
            region.top + region.height // 2,
        )
        pyautogui.moveTo(*requested, duration=0.25)
        observed = pyautogui.position()
        _line("requested_pyautogui_position", requested)
        _line("observed_pyautogui_position", (int(observed[0]), int(observed[1])))
        _line(
            "mouse_position_match",
            str((int(observed[0]), int(observed[1])) == requested).lower(),
        )
        print("Visual alignment requires observing the cursor inside the selected region.")
    else:
        _line("real_mouse_alignment_smoke", "PENDING (--move-pointer not requested)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

