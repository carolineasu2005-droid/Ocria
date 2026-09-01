"""Intent-level keyboard operations for the macOS product branch."""

import pyautogui


def select_all() -> None:
    """Select the current editable content with Command+A."""
    pyautogui.hotkey("command", "a")


def copy() -> None:
    """Copy the current selection with Command+C."""
    pyautogui.hotkey("command", "c")


def clear_selection() -> None:
    """Remove the current selection using the macOS Backspace/Delete key."""
    pyautogui.press("backspace")


def refresh_browser() -> None:
    """Refresh the active browser tab with Command+R."""
    pyautogui.hotkey("command", "r")
