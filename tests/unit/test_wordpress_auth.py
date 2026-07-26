"""Tests for the WordPress login flow.

This flow was previously 146 untested lines inside app.py. It decides whether
a run may proceed at all, so each branch is pinned down here with a fake page.
"""

from wp_auto_poster.wordpress import auth
from wp_auto_poster.wordpress.auth import (
    AuthRuntime,
    is_admin_url,
    login_to_wordpress,
    sync_config_domain_from_url,
)

BASE_CONFIG = {
    "wp_login_url": "https://example.com/wp-login.php",
    "wp_admin_url": "https://example.com/wp-admin/",
    "wp_username": "admin",
    "wp_password": "secret",
}


class FakeElement:
    def __init__(self, visible=True, text=""):
        self._visible = visible
        self._text = text
        self.filled = []
        self.clicks = 0

    def is_visible(self, timeout=None):
        return self._visible

    def click(self):
        self.clicks += 1

    def fill(self, value):
        self.filled.append(value)

    def inner_text(self):
        return self._text


class FakeLocator:
    def __init__(self, element):
        self.first = element if element is not None else _MissingElement()


class _MissingElement:
    def is_visible(self, timeout=None):
        raise RuntimeError("not found")

    def click(self):
        raise RuntimeError("not found")

    def fill(self, value):
        raise RuntimeError("not found")

    def inner_text(self):
        raise RuntimeError("not found")


class FakePage:
    """Minimal Playwright page double.

    ``elements`` maps a selector to a FakeElement; anything absent behaves as
    "selector not present". ``urls`` is the sequence returned by ``page.url``.
    """

    def __init__(self, elements=None, urls=None, wait_for_url_raises=False):
        self.elements = elements or {}
        self._urls = list(urls or ["https://example.com/wp-login.php"])
        self.screenshots = []
        self.wait_for_url_calls = 0
        self._wait_for_url_raises = wait_for_url_raises

    @property
    def url(self):
        if len(self._urls) > 1:
            return self._urls.pop(0)
        return self._urls[0]

    def locator(self, selector):
        return FakeLocator(self.elements.get(selector))

    def wait_for_url(self, pattern, timeout=None):
        self.wait_for_url_calls += 1
        if self._wait_for_url_raises:
            raise RuntimeError("timeout")

    def screenshot(self, path):
        self.screenshots.append(path)

    # wait_for_network_idle touches these
    def wait_for_load_state(self, *args, **kwargs):
        return None


def make_runtime(config=None, navigate=True):
    logs = []
    runtime = AuthRuntime(
        config=dict(config if config is not None else BASE_CONFIG),
        log_func=lambda message, level: logs.append((message, level)),
        sleep=lambda seconds: None,
        navigate=lambda page, url: navigate,
    )
    return runtime, logs


def login_form_page(**kwargs):
    return FakePage(
        elements={
            "#user_login": FakeElement(),
            "#user_pass": FakeElement(),
            "#wp-submit": FakeElement(),
        },
        **kwargs,
    )


# ---------------------------------------------------------------------------
# is_admin_url
# ---------------------------------------------------------------------------


def test_is_admin_url_distinguishes_login_page_from_admin():
    assert is_admin_url("https://example.com/wp-admin/index.php") is True
    assert is_admin_url("https://example.com/wp-login.php") is False
    # A redirect_to param keeps wp-login in the URL: not yet logged in.
    assert is_admin_url("https://example.com/wp-login.php?redirect_to=/wp-admin/") is False


# ---------------------------------------------------------------------------
# Credential guards
# ---------------------------------------------------------------------------


def test_missing_password_fails_before_navigating():
    navigated = []
    logs = []
    runtime = AuthRuntime(
        config={**BASE_CONFIG, "wp_password": ""},
        log_func=lambda m, level: logs.append((m, level)),
        sleep=lambda s: None,
        navigate=lambda page, url: navigated.append(url) or True,
    )

    assert login_to_wordpress(FakePage(), runtime) is False
    assert navigated == []
    assert ("Missing login credentials!", "error") in logs


def test_password_is_never_written_to_the_log():
    page = login_form_page(urls=["https://example.com/wp-admin/"])
    runtime, logs = make_runtime()

    login_to_wordpress(page, runtime)

    assert all("secret" not in message for message, _ in logs)


def test_failed_navigation_aborts_login():
    runtime, _logs = make_runtime(navigate=False)

    assert login_to_wordpress(FakePage(), runtime) is False


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_already_logged_in_short_circuits():
    page = FakePage(urls=["https://example.com/wp-admin/"])
    runtime, logs = make_runtime()

    assert login_to_wordpress(page, runtime) is True
    assert ("Already logged in!", "success") in logs
    assert page.wait_for_url_calls == 0


def test_successful_login_fills_credentials_and_submits():
    page = login_form_page(
        urls=["https://example.com/wp-login.php", "https://example.com/wp-admin/"],
    )
    runtime, logs = make_runtime()

    assert login_to_wordpress(page, runtime) is True
    assert page.elements["#user_login"].filled == ["", "admin"]
    assert page.elements["#user_pass"].filled == ["", "secret"]
    assert page.elements["#wp-submit"].clicks == 1
    assert ("Successfully logged into WordPress!", "success") in logs


def test_fallback_selectors_are_used_when_primary_missing():
    page = FakePage(
        elements={
            "#loginform": FakeElement(),
            "input[name='log']": FakeElement(),
            "input[name='pwd']": FakeElement(),
            "input[type='submit']": FakeElement(),
        },
        urls=["https://example.com/wp-login.php", "https://example.com/wp-admin/"],
    )
    runtime, _logs = make_runtime()

    assert login_to_wordpress(page, runtime) is True
    assert page.elements["input[name='log']"].filled == ["", "admin"]


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_missing_login_form_reports_error_and_screenshots():
    page = FakePage(urls=["https://example.com/wp-login.php"])
    runtime, logs = make_runtime()

    assert login_to_wordpress(page, runtime) is False
    assert ("Could not find login form!", "error") in logs
    assert page.screenshots and "wp_login_error" in page.screenshots[0]


def test_wrong_password_surfaces_wordpress_error_message():
    page = login_form_page(
        urls=["https://example.com/wp-login.php"],
        wait_for_url_raises=True,
    )
    page.elements["#login_error"] = FakeElement(text="ERROR: The password you entered")
    runtime, logs = make_runtime()

    assert login_to_wordpress(page, runtime) is False
    assert any(
        level == "error" and "The password you entered" in message
        for message, level in logs
    )


def test_still_on_login_page_without_error_element():
    page = login_form_page(
        urls=["https://example.com/wp-login.php"],
        wait_for_url_raises=True,
    )
    runtime, logs = make_runtime()

    assert login_to_wordpress(page, runtime) is False
    assert ("Login failed: Still on login page", "error") in logs
    assert any("wp_login_failed" in shot for shot in page.screenshots)


def test_unexpected_exception_is_caught_and_reported():
    class ExplodingPage(FakePage):
        @property
        def url(self):
            raise RuntimeError("browser crashed")

    runtime, logs = make_runtime()

    assert login_to_wordpress(ExplodingPage(), runtime) is False
    assert any(level == "error" and "browser crashed" in message for message, level in logs)


def test_landing_somewhere_else_is_treated_as_success():
    """Some sites redirect to a custom dashboard rather than wp-admin."""
    page = login_form_page(
        urls=["https://example.com/wp-login.php", "https://example.com/my-dashboard"],
        wait_for_url_raises=True,
    )
    runtime, logs = make_runtime()

    assert login_to_wordpress(page, runtime) is True
    assert ("Login appears successful", "success") in logs


# ---------------------------------------------------------------------------
# Domain sync after redirect
# ---------------------------------------------------------------------------


def test_sync_rewrites_host_but_keeps_path():
    config = {
        "wp_admin_url": "https://www.example.com/wp-admin/",
        "wp_login_url": "https://www.example.com/wp-login.php",
    }
    logs = []

    sync_config_domain_from_url(
        config,
        "https://example.com/wp-admin/index.php",
        lambda m, level: logs.append((m, level)),
    )

    assert config["wp_admin_url"] == "https://example.com/wp-admin/"
    assert config["wp_login_url"] == "https://example.com/wp-login.php"
    assert len(logs) == 2


def test_sync_is_a_noop_when_host_matches():
    config = {"wp_admin_url": "https://example.com/wp-admin/"}
    logs = []

    sync_config_domain_from_url(
        config, "https://example.com/wp-admin/", lambda m, level: logs.append((m, level))
    )

    assert config["wp_admin_url"] == "https://example.com/wp-admin/"
    assert logs == []


def test_sync_ignores_unusable_url():
    config = {"wp_admin_url": "https://example.com/wp-admin/"}

    sync_config_domain_from_url(config, "not-a-url", lambda m, level: None)

    assert config["wp_admin_url"] == "https://example.com/wp-admin/"


def test_successful_login_syncs_redirected_domain():
    page = login_form_page(
        urls=["https://www.example.com/wp-login.php", "https://example.com/wp-admin/"],
    )
    runtime, _logs = make_runtime(
        config={
            **BASE_CONFIG,
            "wp_admin_url": "https://www.example.com/wp-admin/",
            "wp_login_url": "https://www.example.com/wp-login.php",
        }
    )

    assert login_to_wordpress(page, runtime) is True
    assert runtime.config["wp_admin_url"] == "https://example.com/wp-admin/"


def test_screenshot_failure_does_not_mask_the_login_result():
    class NoScreenshotPage(FakePage):
        def screenshot(self, path):
            raise RuntimeError("disk full")

    page = NoScreenshotPage(urls=["https://example.com/wp-login.php"])
    runtime, logs = make_runtime()

    assert login_to_wordpress(page, runtime) is False
    assert ("Could not find login form!", "error") in logs


def test_default_runtime_uses_real_safe_navigate(monkeypatch):
    """AuthRuntime without an injected navigate falls back to safe_navigate."""
    calls = []
    monkeypatch.setattr(
        auth,
        "safe_navigate",
        lambda page, url, **kwargs: calls.append(url) or False,
    )
    runtime = AuthRuntime(
        config=dict(BASE_CONFIG),
        log_func=lambda m, level: None,
        sleep=lambda s: None,
    )

    assert login_to_wordpress(FakePage(), runtime) is False
    assert calls == [BASE_CONFIG["wp_login_url"]]
