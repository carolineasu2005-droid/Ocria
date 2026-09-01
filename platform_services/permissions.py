"""Fail-closed macOS privacy-permission checks for automation startup."""

from dataclasses import dataclass, replace
from enum import Enum
import os
from pathlib import Path
import sys
from typing import Any, Callable, Optional, Tuple

try:
    import AppKit as _AppKit
except ImportError:  # Identity diagnostics still have a safe Python fallback.
    _AppKit = None

try:
    import ApplicationServices as _ApplicationServices
except ImportError:  # A missing native binding must fail closed, not fail import.
    _ApplicationServices = None

try:
    import Quartz as _Quartz
except ImportError:  # A missing native binding must fail closed, not fail import.
    _Quartz = None


PACKAGED_PERMISSION_VALIDATION = "pending"


class PermissionKind(str, Enum):
    SCREEN_RECORDING = "screen_recording"
    ACCESSIBILITY = "accessibility"
    INPUT_MONITORING = "input_monitoring"


class PermissionStatus(str, Enum):
    GRANTED = "granted"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


_PERMISSION_LABELS = {
    PermissionKind.SCREEN_RECORDING: "屏幕录制",
    PermissionKind.ACCESSIBILITY: "辅助功能",
    PermissionKind.INPUT_MONITORING: "输入监控",
}

_PERMISSION_PURPOSES = {
    PermissionKind.SCREEN_RECORDING: "用于 OCR 屏幕截图。",
    PermissionKind.ACCESSIBILITY: "用于发现、激活和控制 Chrome/BOSS 窗口及自动输入。",
    PermissionKind.INPUT_MONITORING: "用于全局监听 ESC 安全停止和 Space 暂停/继续。",
}


@dataclass(frozen=True)
class PermissionCheckResult:
    kind: PermissionKind
    status: PermissionStatus
    detail: Optional[str] = None

    @property
    def granted(self) -> bool:
        return self.status is PermissionStatus.GRANTED

    @property
    def label(self) -> str:
        return _PERMISSION_LABELS[self.kind]

    @property
    def purpose(self) -> str:
        return _PERMISSION_PURPOSES[self.kind]


@dataclass(frozen=True)
class RuntimeIdentity:
    runtime_mode: str
    executable_path: str
    executable_name: str
    process_name: str
    bundle_identifier: Optional[str]
    bundle_path: Optional[str]
    executable_in_app_bundle: bool
    frozen: bool


@dataclass(frozen=True)
class PermissionReport:
    results: Tuple[PermissionCheckResult, ...]
    runtime_identity: RuntimeIdentity
    request_attempts: Tuple[PermissionKind, ...] = ()
    request_errors: Tuple[Tuple[PermissionKind, str], ...] = ()

    @property
    def all_required(self) -> bool:
        required_kinds = set(PermissionKind)
        reported_kinds = {result.kind for result in self.results}
        return (
            len(self.results) == len(required_kinds)
            and reported_kinds == required_kinds
            and all(result.granted for result in self.results)
        )

    @property
    def blocking_results(self) -> Tuple[PermissionCheckResult, ...]:
        return tuple(result for result in self.results if not result.granted)

    @property
    def missing_kinds(self) -> Tuple[PermissionKind, ...]:
        return tuple(result.kind for result in self.blocking_results)

    @property
    def packaged_permission_validation(self) -> str:
        return PACKAGED_PERMISSION_VALIDATION

    def result_for(self, kind: PermissionKind) -> PermissionCheckResult:
        for result in self.results:
            if result.kind is kind:
                return result
        raise KeyError(kind)


class NativeMacOSPermissionBackend:
    """Mockable adapter over the three native macOS permission families."""

    def __init__(
        self,
        *,
        quartz: Any = _Quartz,
        accessibility: Any = _ApplicationServices,
    ):
        self.quartz = quartz
        self.accessibility = accessibility

    def screen_recording_check_available(self) -> bool:
        return callable(
            getattr(self.quartz, "CGPreflightScreenCaptureAccess", None)
        )

    def screen_recording_request_available(self) -> bool:
        return callable(
            getattr(self.quartz, "CGRequestScreenCaptureAccess", None)
        )

    def check_screen_recording(self) -> bool:
        return bool(self.quartz.CGPreflightScreenCaptureAccess())

    def request_screen_recording(self) -> bool:
        return bool(self.quartz.CGRequestScreenCaptureAccess())

    def accessibility_check_available(self) -> bool:
        return (
            callable(
                getattr(
                    self.accessibility,
                    "AXIsProcessTrustedWithOptions",
                    None,
                )
            )
            and getattr(
                self.accessibility,
                "kAXTrustedCheckOptionPrompt",
                None,
            )
            is not None
        )

    def accessibility_request_available(self) -> bool:
        return self.accessibility_check_available()

    def check_accessibility(self) -> bool:
        options = {
            self.accessibility.kAXTrustedCheckOptionPrompt: False,
        }
        return bool(
            self.accessibility.AXIsProcessTrustedWithOptions(options)
        )

    def request_accessibility(self) -> bool:
        options = {
            self.accessibility.kAXTrustedCheckOptionPrompt: True,
        }
        # Apple's prompt is asynchronous. The Boolean remains current trust
        # state and is deliberately ignored by the permission service.
        return bool(
            self.accessibility.AXIsProcessTrustedWithOptions(options)
        )

    def input_monitoring_check_available(self) -> bool:
        return callable(
            getattr(self.quartz, "CGPreflightListenEventAccess", None)
        )

    def input_monitoring_request_available(self) -> bool:
        return callable(
            getattr(self.quartz, "CGRequestListenEventAccess", None)
        )

    def check_input_monitoring(self) -> bool:
        return bool(self.quartz.CGPreflightListenEventAccess())

    def request_input_monitoring(self) -> bool:
        return bool(self.quartz.CGRequestListenEventAccess())


class RuntimeIdentityProvider:
    """Discover the current process identity without constructing a TCC ID."""

    def __init__(self, *, sys_module: Any = sys, appkit: Any = _AppKit):
        self.sys_module = sys_module
        self.appkit = appkit

    def detect(self) -> RuntimeIdentity:
        raw_executable = str(
            getattr(self.sys_module, "executable", "") or ""
        )
        executable_path = (
            os.path.abspath(raw_executable) if raw_executable else ""
        )
        executable_name = Path(executable_path).name or "python"
        frozen = bool(getattr(self.sys_module, "frozen", False))
        process_name = executable_name
        bundle_identifier = None
        bundle_path = None

        if self.appkit is not None:
            try:
                process_name = str(
                    self.appkit.NSProcessInfo.processInfo().processName()
                )
            except Exception:
                pass
            try:
                bundle = self.appkit.NSBundle.mainBundle()
                detected_bundle_path = bundle.bundlePath()
                detected_bundle_id = bundle.bundleIdentifier()
                bundle_path = (
                    str(detected_bundle_path)
                    if detected_bundle_path
                    else None
                )
                bundle_identifier = (
                    str(detected_bundle_id) if detected_bundle_id else None
                )
            except Exception:
                pass

        executable_in_app_bundle = _path_is_inside_app_bundle(
            executable_path,
            bundle_path,
        )
        runtime_mode = (
            "packaged"
            if frozen or executable_in_app_bundle
            else "source"
        )
        return RuntimeIdentity(
            runtime_mode=runtime_mode,
            executable_path=executable_path,
            executable_name=executable_name,
            process_name=process_name,
            bundle_identifier=bundle_identifier,
            bundle_path=bundle_path,
            executable_in_app_bundle=executable_in_app_bundle,
            frozen=frozen,
        )


def _path_is_inside_app_bundle(
    executable_path: str,
    bundle_path: Optional[str],
) -> bool:
    if (
        not executable_path
        or not bundle_path
        or not bundle_path.lower().endswith(".app")
    ):
        return False
    executable = os.path.normcase(os.path.abspath(executable_path))
    bundle = os.path.normcase(os.path.abspath(bundle_path))
    return executable.startswith(bundle + os.sep)


def _identity_from_provider(identity_provider: Any = None) -> RuntimeIdentity:
    provider = identity_provider or RuntimeIdentityProvider()
    if callable(provider):
        return provider()
    return provider.detect()


def _check_permission(
    kind: PermissionKind,
    availability_check: Callable[[], bool],
    native_check: Callable[[], bool],
) -> PermissionCheckResult:
    try:
        if not availability_check():
            return PermissionCheckResult(
                kind,
                PermissionStatus.UNAVAILABLE,
                "native_api_unavailable",
            )
        granted = bool(native_check())
    except Exception as exc:
        return PermissionCheckResult(
            kind,
            PermissionStatus.ERROR,
            f"native_check_failed:{type(exc).__name__}",
        )
    return PermissionCheckResult(
        kind,
        PermissionStatus.GRANTED if granted else PermissionStatus.DENIED,
    )


def check_screen_recording_permission(
    backend: Optional[NativeMacOSPermissionBackend] = None,
) -> PermissionCheckResult:
    native = backend or NativeMacOSPermissionBackend()
    return _check_permission(
        PermissionKind.SCREEN_RECORDING,
        native.screen_recording_check_available,
        native.check_screen_recording,
    )


def check_accessibility_permission(
    backend: Optional[NativeMacOSPermissionBackend] = None,
) -> PermissionCheckResult:
    native = backend or NativeMacOSPermissionBackend()
    return _check_permission(
        PermissionKind.ACCESSIBILITY,
        native.accessibility_check_available,
        native.check_accessibility,
    )


def check_input_monitoring_permission(
    backend: Optional[NativeMacOSPermissionBackend] = None,
) -> PermissionCheckResult:
    native = backend or NativeMacOSPermissionBackend()
    return _check_permission(
        PermissionKind.INPUT_MONITORING,
        native.input_monitoring_check_available,
        native.check_input_monitoring,
    )


def check_permissions(
    *,
    backend: Optional[NativeMacOSPermissionBackend] = None,
    identity_provider: Any = None,
) -> PermissionReport:
    """Check all required permissions without displaying native prompts."""
    native = backend or NativeMacOSPermissionBackend()
    return PermissionReport(
        results=(
            check_screen_recording_permission(native),
            check_accessibility_permission(native),
            check_input_monitoring_permission(native),
        ),
        runtime_identity=_identity_from_provider(identity_provider),
    )


def request_missing_permissions(
    report: PermissionReport,
    *,
    backend: Optional[NativeMacOSPermissionBackend] = None,
    identity_provider: Any = None,
) -> PermissionReport:
    """Request denied permissions once, then trust only a fresh preflight."""
    native = backend or NativeMacOSPermissionBackend()
    request_attempts = []
    request_errors = []
    request_operations = {
        PermissionKind.SCREEN_RECORDING: (
            native.screen_recording_request_available,
            native.request_screen_recording,
        ),
        PermissionKind.ACCESSIBILITY: (
            native.accessibility_request_available,
            native.request_accessibility,
        ),
        PermissionKind.INPUT_MONITORING: (
            native.input_monitoring_request_available,
            native.request_input_monitoring,
        ),
    }

    for result in report.blocking_results:
        if result.status is not PermissionStatus.DENIED:
            continue
        availability_check, request = request_operations[result.kind]
        try:
            if not availability_check():
                continue
            request_attempts.append(result.kind)
            request()  # Return value never proves that permission is granted.
        except Exception as exc:
            request_errors.append(
                (result.kind, f"native_request_failed:{type(exc).__name__}")
            )

    if not request_attempts and not request_errors:
        return report

    identity = report.runtime_identity
    rechecked = check_permissions(
        backend=native,
        identity_provider=(
            identity_provider
            if identity_provider is not None
            else lambda: identity
        ),
    )
    return replace(
        rechecked,
        request_attempts=tuple(request_attempts),
        request_errors=tuple(request_errors),
    )


def ensure_permissions(
    *,
    request_missing: bool = True,
    backend: Optional[NativeMacOSPermissionBackend] = None,
    identity_provider: Any = None,
    logger: Any = None,
) -> PermissionReport:
    """Check, optionally request once, re-check, and log the final gate state."""
    native = backend or NativeMacOSPermissionBackend()
    report = check_permissions(
        backend=native,
        identity_provider=identity_provider,
    )
    if request_missing and not report.all_required:
        report = request_missing_permissions(
            report,
            backend=native,
            identity_provider=identity_provider,
        )
    if logger is not None:
        _log_permission_report(report, logger)
    return report


def _log_permission_report(report: PermissionReport, logger: Any) -> None:
    identity = report.runtime_identity
    logger.info(
        "event=runtime_identity runtime_mode=%s executable=%s process=%s "
        "bundle_id=%s executable_in_app_bundle=%s "
        "packaged_permission_validation=%s",
        identity.runtime_mode,
        identity.executable_name,
        identity.process_name,
        identity.bundle_identifier or "none",
        str(identity.executable_in_app_bundle).lower(),
        report.packaged_permission_validation,
    )
    for result in report.results:
        logger.info(
            "event=permission_check permission=%s result=%s",
            result.kind.value,
            result.status.value,
        )
    if report.all_required:
        logger.info("event=permission_gate result=passed")
        return
    logger.error(
        "event=permission_gate result=blocked missing=%s",
        ",".join(kind.value for kind in report.missing_kinds),
    )


def format_runtime_identity(identity: RuntimeIdentity) -> str:
    """Render a sanitized identity summary without the developer path."""
    return (
        f"runtime_mode={identity.runtime_mode} "
        f"executable={identity.executable_name} "
        f"process={identity.process_name} "
        f"bundle_id={identity.bundle_identifier or 'none'} "
        f"executable_in_app_bundle="
        f"{str(identity.executable_in_app_bundle).lower()}"
    )


def format_permission_failure(report: PermissionReport) -> str:
    """Return grouped, actionable CLI output for a blocked startup."""
    status_labels = {
        PermissionStatus.GRANTED: "已授权",
        PermissionStatus.DENIED: "未授权",
        PermissionStatus.UNAVAILABLE: "API 不可用",
        PermissionStatus.ERROR: "检查失败",
    }
    lines = ["macOS 权限检查未通过：", ""]
    for result in report.results:
        marker = "✓" if result.granted else "✗"
        lines.append(
            f"[{marker}] {result.label}：{status_labels[result.status]}"
        )
        if not result.granted:
            lines.append(f"    用途：{result.purpose}")
            if result.detail:
                lines.append(f"    诊断：{result.detail}")

    lines.extend(
        (
            "",
            "自动控制尚未启动。",
            "请在“系统设置 → 隐私与安全性”中授予缺失权限，",
            "然后完全退出并重新运行 Ocria。",
            "",
            f"当前运行身份：{format_runtime_identity(report.runtime_identity)}",
            "源码 Python 与未来 Ocria.app 是不同的隐私权限身份；",
            "PACKAGED_PERMISSION_VALIDATION=PENDING。",
        )
    )
    return "\n".join(lines)


__all__ = [
    "PACKAGED_PERMISSION_VALIDATION",
    "NativeMacOSPermissionBackend",
    "PermissionCheckResult",
    "PermissionKind",
    "PermissionReport",
    "PermissionStatus",
    "RuntimeIdentity",
    "RuntimeIdentityProvider",
    "check_accessibility_permission",
    "check_input_monitoring_permission",
    "check_permissions",
    "check_screen_recording_permission",
    "ensure_permissions",
    "format_permission_failure",
    "format_runtime_identity",
    "request_missing_permissions",
]
