"""Thin macOS system-integration boundary for Ocria."""

from .browser_window import bring_boss_foreground
from .clipboard import read_clipboard_text
from .hotkey_monitor import GlobalHotkeyMonitor
from .input import clear_selection, copy, refresh_browser, select_all
from .permissions import (
    PermissionCheckResult,
    PermissionKind,
    PermissionReport,
    PermissionStatus,
    RuntimeIdentity,
    ensure_permissions,
    format_permission_failure,
)

__all__ = [
    "bring_boss_foreground",
    "clear_selection",
    "copy",
    "ensure_permissions",
    "format_permission_failure",
    "GlobalHotkeyMonitor",
    "PermissionCheckResult",
    "PermissionKind",
    "PermissionReport",
    "PermissionStatus",
    "read_clipboard_text",
    "refresh_browser",
    "RuntimeIdentity",
    "select_all",
]
