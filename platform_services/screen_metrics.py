"""Runtime observations for the first-version macOS coordinate model.

These records deliberately describe measurements only.  They are not a
general coordinate-space abstraction and do not transform production input.
"""

from dataclasses import dataclass
import math
from typing import Any, Optional, Sequence, Tuple


DEFAULT_SCALE_TOLERANCE = 0.01


class ScreenMetricError(RuntimeError):
    """Raised when a required screen observation cannot be collected safely."""


class CaptureGeometryInvariantError(ScreenMetricError):
    """Raised when an MSS frame disagrees with the current session model."""


@dataclass(frozen=True)
class ObservedPoint:
    x: int
    y: int


@dataclass(frozen=True)
class ObservedBounds:
    left: float
    top: float
    width: float
    height: float
    is_primary: Optional[bool] = None


@dataclass(frozen=True)
class NativeScreenMetrics:
    frame: ObservedBounds
    visible_frame: Optional[ObservedBounds]
    backing_scale_factor: float


@dataclass(frozen=True)
class ScreenMetricsSnapshot:
    pyautogui_size: Tuple[int, int]
    pyautogui_position: ObservedPoint
    mss_virtual_monitor: ObservedBounds
    mss_primary_monitor: ObservedBounds
    native_screen: NativeScreenMetrics


@dataclass(frozen=True)
class OverlayMetrics:
    canvas_size: Tuple[int, int]
    root_size: Tuple[int, int]
    release_position: ObservedPoint
    mss_monitor: ObservedBounds
    overlay_to_mss_scale_x: float
    overlay_to_mss_scale_y: float
    scale_relation: str
    event_within_bounds: bool


@dataclass(frozen=True)
class CaptureMetrics:
    requested_bounds: ObservedBounds
    screenshot_size: Tuple[int, int]
    ndarray_shape: Tuple[int, ...]
    capture_scale_x: float
    capture_scale_y: float
    scale_relation: str


def _number(value: Any) -> float:
    return float(value() if callable(value) else value)


def _pair(value: Any) -> Tuple[float, float]:
    """Read a PyObjC point/size represented as attributes or a pair."""

    first_name, second_name = (
        ("x", "y") if hasattr(value, "x") or hasattr(value, "y") else ("width", "height")
    )
    if hasattr(value, first_name) and hasattr(value, second_name):
        return (_number(getattr(value, first_name)), _number(getattr(value, second_name)))
    return (float(value[0]), float(value[1]))


def _native_rect(value: Any) -> ObservedBounds:
    """Normalize an NSRect without depending on one PyObjC representation."""

    if hasattr(value, "origin") and hasattr(value, "size"):
        left, top = _pair(value.origin)
        width, height = _pair(value.size)
    else:
        origin, size = value
        left, top = _pair(origin)
        width, height = _pair(size)
    return ObservedBounds(
        left=left,
        top=top,
        width=width,
        height=height,
    )


def mss_bounds(value: Any) -> ObservedBounds:
    """Normalize one mapping returned by ``mss.MSS().monitors``."""

    try:
        return ObservedBounds(
            left=int(value["left"]),
            top=int(value["top"]),
            width=int(value["width"]),
            height=int(value["height"]),
            is_primary=(
                bool(value["is_primary"])
                if "is_primary" in value
                else None
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ScreenMetricError("invalid MSS monitor geometry") from exc


def select_primary_mss_monitor(monitors: Sequence[Any]) -> Any:
    """Select the same first-version primary monitor used by calibration."""

    physical_monitors = list(monitors[1:])
    if not physical_monitors:
        raise ScreenMetricError("no physical MSS monitor is available")
    return next(
        (
            monitor
            for monitor in physical_monitors
            if bool(monitor.get("is_primary", False))
        ),
        physical_monitors[0],
    )


def observe_native_screen(screen: Any) -> NativeScreenMetrics:
    """Read current NSScreen geometry; the scale remains evidence only."""

    if screen is None:
        raise ScreenMetricError("NSScreen.mainScreen() is unavailable")
    frame_value = screen.frame() if callable(screen.frame) else screen.frame
    visible_value = None
    if hasattr(screen, "visibleFrame"):
        source = screen.visibleFrame
        visible_value = source() if callable(source) else source
    scale_source = screen.backingScaleFactor
    scale = _number(scale_source)
    if not math.isfinite(scale) or scale <= 0:
        raise ScreenMetricError("native backing scale factor is invalid")
    return NativeScreenMetrics(
        frame=_native_rect(frame_value),
        visible_frame=(
            _native_rect(visible_value) if visible_value is not None else None
        ),
        backing_scale_factor=scale,
    )


def collect_screen_metrics(
    *,
    pyautogui_module: Any = None,
    mss_factory: Any = None,
    native_screen: Any = None,
) -> ScreenMetricsSnapshot:
    """Collect one cross-library snapshot without applying transformations."""

    if pyautogui_module is None:
        import pyautogui as pyautogui_module
    if mss_factory is None:
        import mss

        mss_factory = mss.MSS
    if native_screen is None:
        from AppKit import NSScreen

        native_screen = NSScreen.mainScreen()

    size = pyautogui_module.size()
    position = pyautogui_module.position()
    size_pair = (int(size[0]), int(size[1]))
    position_point = ObservedPoint(int(position[0]), int(position[1]))

    with mss_factory() as capture:
        monitors = list(capture.monitors)
    if not monitors:
        raise ScreenMetricError("MSS returned no monitor geometry")
    virtual = mss_bounds(monitors[0])
    primary = mss_bounds(select_primary_mss_monitor(monitors))

    return ScreenMetricsSnapshot(
        pyautogui_size=size_pair,
        pyautogui_position=position_point,
        mss_virtual_monitor=virtual,
        mss_primary_monitor=primary,
        native_screen=observe_native_screen(native_screen),
    )


def classify_scale_relation(
    scale_x: float,
    scale_y: float,
    *,
    tolerance: float = DEFAULT_SCALE_TOLERANCE,
) -> str:
    """Classify independent observed ratios without averaging or guessing."""

    if (
        not math.isfinite(scale_x)
        or not math.isfinite(scale_y)
        or scale_x <= 0
        or scale_y <= 0
    ):
        return "unavailable"
    if not math.isclose(scale_x, scale_y, rel_tol=tolerance, abs_tol=tolerance):
        return "asymmetric"
    if math.isclose(scale_x, 1.0, rel_tol=tolerance, abs_tol=tolerance):
        return "1x"
    if math.isclose(scale_x, 2.0, rel_tol=tolerance, abs_tol=tolerance):
        return "2x"
    if not math.isclose(scale_x, round(scale_x), abs_tol=tolerance):
        return "fractional"
    return "uniform-scaled"


def observe_overlay(
    *,
    canvas_width: int,
    canvas_height: int,
    root_width: int,
    root_height: int,
    event_x: int,
    event_y: int,
    monitor: Any,
    boundary_tolerance: int = 1,
) -> OverlayMetrics:
    """Record realized Tk geometry at release time and validate the event."""

    dimensions = (canvas_width, canvas_height, root_width, root_height)
    if any(int(value) <= 0 for value in dimensions):
        raise ScreenMetricError("realized Tk overlay dimensions must be positive")
    monitor_bounds = (
        monitor if isinstance(monitor, ObservedBounds) else ObservedBounds(
            left=int(monitor.left),
            top=int(monitor.top),
            width=int(monitor.width),
            height=int(monitor.height),
        )
    )
    if monitor_bounds.width <= 0 or monitor_bounds.height <= 0:
        raise ScreenMetricError("MSS monitor dimensions must be positive")
    scale_x = monitor_bounds.width / int(canvas_width)
    scale_y = monitor_bounds.height / int(canvas_height)
    within = (
        -boundary_tolerance <= int(event_x) <= int(canvas_width) + boundary_tolerance
        and -boundary_tolerance <= int(event_y) <= int(canvas_height) + boundary_tolerance
    )
    return OverlayMetrics(
        canvas_size=(int(canvas_width), int(canvas_height)),
        root_size=(int(root_width), int(root_height)),
        release_position=ObservedPoint(int(event_x), int(event_y)),
        mss_monitor=monitor_bounds,
        overlay_to_mss_scale_x=scale_x,
        overlay_to_mss_scale_y=scale_y,
        scale_relation=classify_scale_relation(scale_x, scale_y),
        event_within_bounds=within,
    )


def _screenshot_size(screenshot: Any) -> Tuple[int, int]:
    try:
        width = int(screenshot.width)
        height = int(screenshot.height)
    except (AttributeError, TypeError, ValueError) as exc:
        raise CaptureGeometryInvariantError(
            "MSS screenshot dimensions are unavailable"
        ) from exc
    return (width, height)


def observe_capture(region: Any, screenshot: Any, array: Any) -> CaptureMetrics:
    """Measure an MSS screenshot and its exact NumPy conversion result."""

    requested = ObservedBounds(
        left=int(region.left),
        top=int(region.top),
        width=int(region.width),
        height=int(region.height),
    )
    actual_width, actual_height = _screenshot_size(screenshot)
    shape = tuple(int(value) for value in getattr(array, "shape", ()))
    if requested.width <= 0 or requested.height <= 0:
        raise CaptureGeometryInvariantError("requested capture dimensions are invalid")
    if actual_width <= 0 or actual_height <= 0:
        raise CaptureGeometryInvariantError("actual capture dimensions are invalid")
    scale_x = actual_width / requested.width
    scale_y = actual_height / requested.height
    return CaptureMetrics(
        requested_bounds=requested,
        screenshot_size=(actual_width, actual_height),
        ndarray_shape=shape,
        capture_scale_x=scale_x,
        capture_scale_y=scale_y,
        scale_relation=classify_scale_relation(scale_x, scale_y),
    )


@dataclass(frozen=True)
class CaptureFrameInvariant:
    """The measured MSS raster relation for one process/display session."""

    expected_scale_x: float
    expected_scale_y: float
    tolerance: float = DEFAULT_SCALE_TOLERANCE

    @classmethod
    def establish(
        cls,
        metrics: CaptureMetrics,
        *,
        tolerance: float = DEFAULT_SCALE_TOLERANCE,
    ) -> "CaptureFrameInvariant":
        invariant = cls(
            expected_scale_x=metrics.capture_scale_x,
            expected_scale_y=metrics.capture_scale_y,
            tolerance=tolerance,
        )
        invariant.validate(metrics)
        return invariant

    def validate(self, metrics: CaptureMetrics) -> None:
        """Fail closed when screenshot, ndarray, or X/Y scale diverges."""

        width, height = metrics.screenshot_size
        shape = metrics.ndarray_shape
        if width <= 0 or height <= 0:
            raise CaptureGeometryInvariantError("actual capture dimensions are invalid")
        if (
            len(shape) != 3
            or shape[2] < 3
            or shape[1] != width
            or shape[0] != height
        ):
            raise CaptureGeometryInvariantError(
                "NumPy raster dimensions disagree with the MSS screenshot"
            )
        if classify_scale_relation(
            metrics.capture_scale_x,
            metrics.capture_scale_y,
            tolerance=self.tolerance,
        ) == "asymmetric":
            raise CaptureGeometryInvariantError("capture X/Y scale is asymmetric")
        if not math.isclose(
            metrics.capture_scale_x,
            self.expected_scale_x,
            rel_tol=self.tolerance,
            abs_tol=self.tolerance,
        ) or not math.isclose(
            metrics.capture_scale_y,
            self.expected_scale_y,
            rel_tol=self.tolerance,
            abs_tol=self.tolerance,
        ):
            raise CaptureGeometryInvariantError(
                "capture scale disagrees with the session expectation"
            )
