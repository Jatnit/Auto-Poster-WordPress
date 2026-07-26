"""WordPress login flow.

Extracted from ``app.py`` so the riskiest part of the automation — the one
that handles credentials and decides whether a run may proceed — is covered
by tests instead of only being exercised against a live site.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, MutableMapping
from urllib.parse import urlparse

from wp_auto_poster.wordpress.browser import safe_navigate, wait_for_network_idle
from wp_auto_poster.wordpress.browser_launch import screenshot_path

LogFunc = Callable[[str, str], None]

FORM_SELECTORS = ["#user_login", "#loginform", "input[name='log']", "#username"]
USERNAME_SELECTORS = ["#user_login", "input[name='log']", "#username"]
PASSWORD_SELECTORS = ["#user_pass", "input[name='pwd']", "#password"]
SUBMIT_SELECTORS = [
    "#wp-submit",
    "input[type='submit']",
    "button[type='submit']",
    ".login-submit button",
]
ERROR_SELECTORS = ["#login_error", ".login-error", ".message.error"]


@dataclass
class AuthRuntime:
    config: MutableMapping[str, Any]
    log_func: LogFunc
    #: Injectable so tests do not pay the real waits.
    sleep: Callable[[float], None] = field(default=time.sleep)
    navigate: Callable[..., bool] = field(default=None)

    def log(self, message: str, level: str = "info") -> None:
        self.log_func(message, level)

    def go(self, page: Any, url: str) -> bool:
        if self.navigate is not None:
            return self.navigate(page, url)
        return safe_navigate(
            page,
            url,
            log_func=self.log_func,
            timeout=30000,
            max_retries=3,
        )


def is_admin_url(url: str) -> bool:
    """True when the URL looks like a logged-in wp-admin location."""
    return "wp-admin" in url and "wp-login" not in url


def sync_config_domain_from_url(
    config: MutableMapping[str, Any],
    current_url: str,
    log_func: LogFunc,
) -> None:
    """Realign configured URLs with the host WordPress actually redirected to.

    A site may bounce www -> non-www (or the reverse) during login; later
    navigations must use the host that actually holds the session cookie.
    Only the in-memory config is touched.
    """
    try:
        parsed = urlparse(current_url)
        if not parsed.scheme or not parsed.netloc:
            return
        real_origin = f"{parsed.scheme}://{parsed.netloc}"

        for key in ("wp_admin_url", "wp_login_url"):
            old = config.get(key, "")
            if not old:
                continue
            old_parsed = urlparse(old)
            if not old_parsed.netloc:
                continue
            if old_parsed.netloc != parsed.netloc:
                config[key] = real_origin + old_parsed.path
                log_func(
                    f"Cập nhật {key}: {old_parsed.netloc} → {parsed.netloc}",
                    "info",
                )
    except Exception as e:
        log_func(f"Không sync được domain sau login: {e}", "warning")


def _first_visible(page: Any, selectors, timeout: int):
    for selector in selectors:
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=timeout):
                return selector, element
        except Exception:
            continue
    return None, None


def _fill_field(page: Any, selectors, value: str, runtime: AuthRuntime, label: str) -> bool:
    selector, field_el = _first_visible(page, selectors, timeout=2000)
    if field_el is None:
        return False
    try:
        field_el.click()
        field_el.fill("")
        field_el.fill(value)
        runtime.log(f"Filled {label} in {selector}", "info")
        return True
    except Exception:
        return False


def _capture(page: Any, name: str, runtime: AuthRuntime) -> None:
    try:
        path = screenshot_path(name)
        page.screenshot(path=path)
        runtime.log(f"Screenshot saved to {path}", "info")
    except Exception:
        pass


def _read_login_error(page: Any) -> str:
    for selector in ERROR_SELECTORS:
        try:
            element = page.locator(selector).first
            if element.is_visible(timeout=1000):
                return element.inner_text()
        except Exception:
            continue
    return ""


def login_to_wordpress(page: Any, runtime: AuthRuntime) -> bool:
    try:
        runtime.log("Logging into WordPress...", "info")

        login_url = runtime.config.get("wp_login_url", "")
        username = runtime.config.get("wp_username", "")
        password = runtime.config.get("wp_password", "")

        runtime.log(f"Login URL: {login_url}", "info")
        runtime.log(f"Username: {username}", "info")

        if not login_url or not username or not password:
            runtime.log("Missing login credentials!", "error")
            return False

        # Retry + dialog handling guards against ERR_ABORTED when coming from
        # gemini.google.com / chatgpt.com.
        if not runtime.go(page, login_url):
            return False
        runtime.sleep(1)

        current_url = page.url
        runtime.log(f"Current URL: {current_url}", "info")

        if is_admin_url(current_url):
            runtime.log("Already logged in!", "success")
            return True

        selector, _ = _first_visible(page, FORM_SELECTORS, timeout=3000)
        if selector is None:
            runtime.log("Could not find login form!", "error")
            _capture(page, "wp_login_error", runtime)
            return False
        runtime.log(f"Tìm thấy form đăng nhập: {selector}", "info")

        _fill_field(page, USERNAME_SELECTORS, username, runtime, "username")
        runtime.sleep(0.3)
        _fill_field(page, PASSWORD_SELECTORS, password, runtime, "password")
        runtime.sleep(0.3)

        submit_selector, submit_btn = _first_visible(page, SUBMIT_SELECTORS, timeout=2000)
        if submit_btn is not None:
            try:
                submit_btn.click()
                runtime.log(f"Clicked submit: {submit_selector}", "info")
            except Exception:
                pass

        runtime.log("Đang chờ đăng nhập...", "info")
        runtime.sleep(2)

        try:
            page.wait_for_url("**/wp-admin/**", timeout=10000)
        except Exception:
            runtime.sleep(1)

        current_url = page.url
        runtime.log(f"After login URL: {current_url}", "info")

        if is_admin_url(current_url):
            runtime.log("Successfully logged into WordPress!", "success")
            sync_config_domain_from_url(runtime.config, current_url, runtime.log_func)
            wait_for_network_idle(page)
            return True

        error_text = _read_login_error(page)
        if error_text:
            runtime.log(f"Login error: {error_text[:100]}", "error")
            return False

        if "wp-login" in current_url or "login" in current_url.lower():
            runtime.log("Login failed: Still on login page", "error")
            _capture(page, "wp_login_failed", runtime)
            return False

        runtime.log("Login appears successful", "success")
        return True

    except Exception as e:
        runtime.log(f"Login failed: {e}", "error")
        _capture(page, "wp_login_exception", runtime)
        return False


__all__ = [
    "AuthRuntime",
    "is_admin_url",
    "login_to_wordpress",
    "sync_config_domain_from_url",
]
