"""Safe text clipboard access through the macOS built-in pbpaste tool."""

import subprocess


PBPASTE_TIMEOUT_SECONDS = 1.0


def read_clipboard_text() -> str:
    """Return clipboard text, or an empty string when it cannot be read."""
    try:
        result = subprocess.run(
            ["pbpaste"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=PBPASTE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if result.returncode != 0:
        return ""
    try:
        return result.stdout.decode("utf-8")
    except (AttributeError, UnicodeDecodeError):
        return ""
