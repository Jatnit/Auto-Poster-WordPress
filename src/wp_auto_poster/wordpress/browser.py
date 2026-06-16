"""Reusable browser helpers for WordPress and provider pages."""

from __future__ import annotations

import time
from typing import Callable, Optional, Sequence

LogFunc = Optional[Callable[[str, str], None]]


def _log(log_func: LogFunc, message: str, level: str) -> None:
    if log_func:
        log_func(message, level)


def wait_for_network_idle(page, timeout: int = 10000) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def join_url(base: str, path: str) -> str:
    """Join base URL and path while normalizing duplicate slashes."""
    return base.rstrip("/") + "/" + path.lstrip("/")


def click_first_visible(
    page,
    selectors: Sequence[str],
    timeout: int = 1500,
    require_enabled: bool = False,
) -> bool:
    """Click the first visible selector."""
    for selector in selectors:
        try:
            element = page.locator(selector).last
            if element.is_visible(timeout=timeout):
                if require_enabled and not element.is_enabled():
                    continue
                element.click()
                return True
        except Exception:
            continue
    return False


def click_visible_by_text(page, labels: Sequence[str]) -> bool:
    """Best-effort click for visible controls containing any label."""
    try:
        return bool(
            page.evaluate(
                """(labels) => {
                    const nodes = Array.from(
                        document.querySelectorAll(
                            "button,[role='button'],[role='menuitem'],li,div[tabindex]"
                        )
                    );
                    const isVisible = (el) => {
                        const st = window.getComputedStyle(el);
                        if (st.display === "none" || st.visibility === "hidden") return false;
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    };
                    for (const node of nodes) {
                        if (!isVisible(node)) continue;
                        const txt = (node.innerText || node.textContent || "").trim().toLowerCase();
                        if (!txt) continue;
                        if (labels.some((l) => txt.includes(String(l).toLowerCase()))) {
                            node.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                list(labels),
            )
        )
    except Exception:
        return False


def safe_navigate(
    page,
    url: str,
    log_func: LogFunc = None,
    timeout: int = 30000,
    max_retries: int = 3,
) -> bool:
    """Navigate with retry and dialog handling."""

    def auto_dismiss(dialog):
        try:
            dialog.accept()
        except Exception:
            try:
                dialog.dismiss()
            except Exception:
                pass

    page.on("dialog", auto_dismiss)

    strategies = ["domcontentloaded", "load", "commit"]

    try:
        for attempt in range(1, max_retries + 1):
            wait_until = strategies[min(attempt - 1, len(strategies) - 1)]
            try:
                if attempt > 1:
                    try:
                        page.goto("about:blank", wait_until="load", timeout=5000)
                        time.sleep(0.5)
                    except Exception:
                        pass

                _log(
                    log_func,
                    f"Điều hướng tới {url} (lần {attempt}/{max_retries}, wait_until={wait_until})...",
                    "info",
                )
                page.goto(url, wait_until=wait_until, timeout=timeout)
                time.sleep(0.8)
                return True

            except Exception as e:
                msg = str(e)
                if "ERR_ABORTED" in msg or "TimeoutError" in type(e).__name__:
                    _log(
                        log_func,
                        f"Navigate bị abort/timeout ({attempt}/{max_retries}): {msg[:120]}",
                        "warning",
                    )
                    time.sleep(2)
                    continue
                _log(log_func, f"Lỗi navigate: {msg[:180]}", "error")
                return False

        try:
            _log(log_func, "Thử fallback: set window.location qua JS...", "info")
            page.evaluate(f"() => {{ window.location.replace({url!r}); }}")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except Exception:
                pass
            time.sleep(1.5)
            if url.split("://", 1)[-1].split("/", 1)[0] in (page.url or ""):
                _log(log_func, "Fallback thành công!", "info")
                return True
        except Exception as e:
            _log(log_func, f"Fallback cũng thất bại: {e}", "warning")

        _log(log_func, f"Không thể điều hướng tới {url} sau {max_retries} lần thử", "error")
        return False

    finally:
        try:
            page.remove_listener("dialog", auto_dismiss)
        except Exception:
            pass


def click_first_selector_resilient(
    page,
    selectors: Sequence[str],
    label: str,
    log_func: LogFunc = None,
    timeout_ms: int = 1500,
) -> bool:
    """Click via locator first, then fallback to JS for viewport/overlay issues."""
    for selector in selectors:
        try:
            target = page.locator(selector).first
            if not target.is_visible(timeout=timeout_ms):
                continue
            try:
                target.scroll_into_view_if_needed(timeout=timeout_ms)
            except Exception:
                pass
            try:
                target.click(timeout=timeout_ms)
                _log(log_func, f"Clicked {label}", "info")
                return True
            except Exception:
                try:
                    target.click(force=True, timeout=timeout_ms)
                    _log(log_func, f"Force-clicked {label}", "info")
                    return True
                except Exception:
                    continue
        except Exception:
            continue

    try:
        clicked_selector = page.evaluate(
            """(selectors) => {
                const canClick = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 &&
                        rect.height > 0 &&
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        style.opacity !== '0';
                };
                for (const selector of selectors) {
                    let el = null;
                    try { el = document.querySelector(selector); } catch (e) {}
                    if (!el) continue;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
                    if (!canClick(el)) continue;
                    try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
                    el.click();
                    return selector;
                }
                return null;
            }""",
            list(selectors),
        )
        if clicked_selector:
            _log(log_func, f"JS-clicked {label}", "info")
            return True
    except Exception:
        pass

    return False


def close_all_modals(page, max_attempts: int = 2) -> None:
    try:
        for _ in range(max_attempts):
            page.keyboard.press("Escape")
            time.sleep(0.15)

            for selector in [".media-modal-close", "button[aria-label='Close']", ".media-frame-close"]:
                try:
                    button = page.locator(selector).first
                    if button.is_visible(timeout=300):
                        button.click()
                        time.sleep(0.15)
                        break
                except Exception:
                    continue

            try:
                if not page.locator(".media-modal").first.is_visible(timeout=300):
                    return
            except Exception:
                return
    except Exception:
        pass
