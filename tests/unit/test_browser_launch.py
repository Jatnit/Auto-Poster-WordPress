import os

from wp_auto_poster.wordpress.browser_launch import (
    LEGACY_USER_DATA_DIR,
    USER_DATA_DIR,
    resolve_browser_executable,
    resolve_user_data_dir,
    screenshot_path,
)

MAC_BRAVE = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIN_BRAVE = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
LINUX_BRAVE = "/usr/bin/brave-browser"
LINUX_CHROME = "/usr/bin/google-chrome"


def only(*present):
    found = set(present)
    return lambda path: path in found


def test_explicit_config_path_wins():
    custom = "/opt/custom/browser"

    resolved = resolve_browser_executable(
        {"browser_executable_path": custom},
        platform="darwin",
        exists=only(custom, MAC_BRAVE),
    )

    assert resolved == custom


def test_missing_configured_path_falls_back_to_autodetect():
    logs = []

    resolved = resolve_browser_executable(
        {"browser_executable_path": "/nope/browser"},
        platform="darwin",
        exists=only(MAC_BRAVE),
        log_func=lambda message, level: logs.append((message, level)),
    )

    assert resolved == MAC_BRAVE
    assert logs and logs[0][1] == "warning"


def test_macos_prefers_brave_then_chrome():
    assert resolve_browser_executable({}, platform="darwin", exists=only(MAC_BRAVE)) == MAC_BRAVE
    assert resolve_browser_executable({}, platform="darwin", exists=only(MAC_CHROME)) == MAC_CHROME


def test_windows_is_supported():
    """The launcher used to be macOS-only despite the README promising Windows."""
    resolved = resolve_browser_executable({}, platform="win32", exists=only(WIN_BRAVE))

    assert resolved == WIN_BRAVE


def test_linux_is_supported():
    assert resolve_browser_executable({}, platform="linux", exists=only(LINUX_BRAVE)) == LINUX_BRAVE
    assert (
        resolve_browser_executable({}, platform="linux2", exists=only(LINUX_CHROME))
        == LINUX_CHROME
    )


def test_no_browser_found_returns_none_for_bundled_chromium():
    logs = []

    resolved = resolve_browser_executable(
        {},
        platform="darwin",
        exists=only(),
        log_func=lambda message, level: logs.append((message, level)),
    )

    assert resolved is None
    assert logs and logs[-1][1] == "warning"


# ---------------------------------------------------------------------------
# Profile directory
# ---------------------------------------------------------------------------


def test_legacy_profile_is_reused_when_present():
    """Renaming the profile dir must not drop existing Google logins."""
    legacy = os.path.expanduser(LEGACY_USER_DATA_DIR)

    resolved = resolve_user_data_dir({}, exists=only(legacy))

    assert resolved == legacy


def test_new_profile_path_used_when_legacy_absent():
    resolved = resolve_user_data_dir({}, exists=only())

    assert resolved == os.path.expanduser(USER_DATA_DIR)


def test_profile_override_is_honoured():
    resolved = resolve_user_data_dir({"browser_user_data_dir": "~/custom-profile"})

    assert resolved == os.path.expanduser("~/custom-profile")


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------


def test_screenshot_path_is_writable_and_not_hardcoded_tmp():
    path = screenshot_path("wp_login_error")

    assert path.endswith("wp_login_error.png")
    assert os.path.isdir(os.path.dirname(path))


def test_screenshot_path_does_not_double_suffix():
    assert screenshot_path("x.png").endswith("x.png")
    assert not screenshot_path("x.png").endswith("x.png.png")
