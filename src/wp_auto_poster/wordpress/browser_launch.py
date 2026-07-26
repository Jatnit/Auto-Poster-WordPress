"""Cross-platform browser discovery and profile/screenshot locations.

The launcher used to hardcode a macOS Brave path, so the app could not run on
Windows or Linux at all despite the README advertising Windows support.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional

LogFunc = Optional[Callable[[str, str], None]]

#: Candidate executables per platform, most preferred first. Brave is listed
#: before Chrome because the original setup relied on it to avoid Google
#: login friction when driving Gemini.
BROWSER_CANDIDATES = {
    "darwin": [
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "win32": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "linux": [
        "/usr/bin/brave-browser",
        "/usr/bin/brave",
        "/opt/brave.com/brave/brave",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ],
}

#: Legacy profile directory. Kept as the first choice when it already exists so
#: an existing Google/WordPress login session is not lost.
LEGACY_USER_DATA_DIR = "~/.gemini/browser_data"
USER_DATA_DIR = "~/.wp_auto_poster/browser_data"


def _platform_key(platform: Optional[str] = None) -> str:
    value = platform or sys.platform
    if value.startswith("linux"):
        return "linux"
    if value.startswith("win"):
        return "win32"
    if value == "darwin":
        return "darwin"
    return "linux"


def _expand_windows_candidates(candidates: List[str]) -> List[str]:
    """Add %LOCALAPPDATA% variants, where per-user installs land."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return candidates
    extra = [
        os.path.join(local, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
    ]
    return candidates + extra


def resolve_browser_executable(
    config: Optional[Mapping[str, Any]] = None,
    platform: Optional[str] = None,
    exists: Callable[[str], bool] = os.path.exists,
    log_func: LogFunc = None,
) -> Optional[str]:
    """Return the browser binary to launch, or ``None`` for Playwright's own.

    Order: explicit config override, then per-platform well-known locations,
    then ``None`` so Playwright falls back to its bundled Chromium.
    """
    override = str((config or {}).get("browser_executable_path") or "").strip()
    if override:
        if exists(override):
            return override
        if log_func:
            log_func(
                f"Không tìm thấy browser đã cấu hình: {override} — thử tự dò",
                "warning",
            )

    key = _platform_key(platform)
    candidates = list(BROWSER_CANDIDATES.get(key, []))
    if key == "win32":
        candidates = _expand_windows_candidates(candidates)

    for candidate in candidates:
        if exists(candidate):
            return candidate

    if log_func:
        log_func(
            "Không tìm thấy Brave/Chrome trên máy — dùng Chromium của Playwright",
            "warning",
        )
    return None


def resolve_user_data_dir(
    config: Optional[Mapping[str, Any]] = None,
    exists: Callable[[str], bool] = os.path.isdir,
) -> str:
    """Return the persistent browser profile directory.

    The legacy ``~/.gemini/browser_data`` wins when present so saved logins
    keep working after the rename.
    """
    override = str((config or {}).get("browser_user_data_dir") or "").strip()
    if override:
        return os.path.expanduser(override)

    legacy = os.path.expanduser(LEGACY_USER_DATA_DIR)
    if exists(legacy):
        return legacy
    return os.path.expanduser(USER_DATA_DIR)


def screenshot_path(name: str) -> str:
    """Return a writable screenshot path that works on every platform.

    Replaces the hardcoded ``/tmp/...`` paths, which do not exist on Windows.
    """
    directory = Path(tempfile.gettempdir()) / "wp_auto_poster"
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = name if name.endswith(".png") else f"{name}.png"
    return str(directory / safe_name)
