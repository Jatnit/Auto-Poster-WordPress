"""WordPress Classic Editor field helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from wp_auto_poster.wordpress.browser import join_url, safe_navigate, wait_for_network_idle
from wp_auto_poster.wordpress.media import remove_non_auto_images_from_editor

LogFunc = Callable[[str, str], None]


@dataclass
class EditorRuntime:
    config: dict
    log_func: LogFunc

    def log(self, message: str, level: str = "info") -> None:
        self.log_func(message, level)


def navigate_to_new_post(page: Any, runtime: EditorRuntime) -> bool:
    try:
        target_url = join_url(runtime.config["wp_admin_url"], "post-new.php")
        if not safe_navigate(
            page,
            target_url,
            log_func=runtime.log_func,
            timeout=30000,
            max_retries=3,
        ):
            return False
        wait_for_network_idle(page, timeout=15000)
        time.sleep(2)

        try:
            page.wait_for_selector("#title, input[name='post_title']", timeout=10000)
            runtime.log("Classic Editor loaded", "info")
        except Exception:
            runtime.log("Editor may not have loaded properly", "warning")

        try:
            dismiss_btns = page.locator(".notice-dismiss, .wp-core-ui .notice-dismiss").all()
            for btn in dismiss_btns:
                if btn.is_visible():
                    btn.click()
                    time.sleep(0.2)
        except Exception:
            pass

        runtime.log("Navigated to new post editor", "info")
        return True

    except Exception as e:
        runtime.log(f"Failed to navigate to new post: {e}", "error")
        return False


def set_post_title(page: Any, title: str, runtime: EditorRuntime) -> bool:
    try:
        title_input = page.locator("#title")

        if title_input.is_visible(timeout=5000):
            title_input.click()
            title_input.fill("")
            title_input.fill(title)
            runtime.log(f"Set title: {title[:50]}...", "info")
            return True

        runtime.log("Title field not visible", "error")
        return False

    except Exception as e:
        runtime.log(f"Failed to set title: {e}", "error")
        return False


def set_post_content(page: Any, content: str, runtime: EditorRuntime) -> bool:
    """Push HTML content into Classic Editor while keeping TinyMCE synced."""
    try:
        runtime.log("Đang thêm nội dung...", "info")
        time.sleep(0.5)

        content_added = False

        try:
            page.wait_for_function(
                """() => window.tinymce
                    && tinymce.get('content')
                    && !tinymce.get('content').initializing""",
                timeout=5000,
            )

            ok = page.evaluate(
                """(html) => {
                    const ed = window.tinymce && tinymce.get('content');
                    if (!ed) return false;
                    try {
                        ed.setContent(html);
                        ed.save();
                        const ta = document.getElementById('content');
                        if (ta) {
                            ta.value = html;
                            ta.dispatchEvent(new Event('input', { bubbles: true }));
                            ta.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        return ed.getContent({ format: 'raw' }).length > 0;
                    } catch (e) {
                        return false;
                    }
                }""",
                content,
            )
            if ok:
                content_added = True
                runtime.log("Content set via TinyMCE API", "success")
        except Exception as e:
            runtime.log(f"TinyMCE API method skipped: {e}", "warning")

        if not content_added:
            try:
                text_tab = page.locator("#content-html").first
                if text_tab.is_visible(timeout=3000):
                    text_tab.click()
                    time.sleep(0.5)
                    runtime.log("Đã chuyển sang chế độ Text/HTML", "info")

                content_textarea = page.locator("#content").first
                if content_textarea.is_visible(timeout=3000):
                    content_textarea.click()
                    content_textarea.fill("")
                    content_textarea.fill(content)

                    page.evaluate(
                        """(html) => {
                            const ed = window.tinymce && tinymce.get('content');
                            if (ed) {
                                try { ed.setContent(html); ed.save(); } catch (e) {}
                            }
                            const ta = document.getElementById('content');
                            if (ta) {
                                ta.value = html;
                                ta.dispatchEvent(new Event('input', { bubbles: true }));
                                ta.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }""",
                        content,
                    )
                    content_added = True
                    runtime.log("Content set via textarea + TinyMCE sync", "success")
            except Exception as e:
                runtime.log(f"Textarea method failed: {e}", "warning")

        if not content_added:
            try:
                ok = page.evaluate(
                    """(html) => {
                        const htmlBtn = document.getElementById('content-html');
                        if (htmlBtn) htmlBtn.click();
                        const ta = document.getElementById('content');
                        if (ta) {
                            ta.value = html;
                            ta.dispatchEvent(new Event('input', { bubbles: true }));
                            ta.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                        const ed = window.tinymce && tinymce.get('content');
                        if (ed) {
                            try { ed.setContent(html); ed.save(); } catch (e) {}
                        }
                        return !!ta;
                    }""",
                    content,
                )
                if ok:
                    content_added = True
                    runtime.log("Content set via JavaScript injection", "success")
            except Exception as e:
                runtime.log(f"JavaScript method failed: {e}", "warning")

        if content_added:
            remove_non_auto_images_from_editor(
                page,
                "after content set",
                log_func=runtime.log_func,
            )
            return True

        runtime.log("Failed to add content - all methods failed", "error")
        return False

    except Exception as e:
        runtime.log(f"Failed to set content: {e}", "error")
        return False


def set_rank_math_keyword(page: Any, keyword: str, runtime: EditorRuntime) -> bool:
    try:
        runtime.log(f"Setting Rank Math keyword: {keyword}", "info")

        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(1)

        keyword_selectors = [
            "input[placeholder*='Rank Math']",
            "input.rank-math-focus-keyword",
            "#rank-math-focus-keyword",
            "input[name*='rank_math'][name*='keyword']",
            ".rank-math-focus-keyword input",
            "input[placeholder*='khóa chính']",
            "input[placeholder*='focus keyword']",
        ]

        keyword_input = None
        for selector in keyword_selectors:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1000):
                    keyword_input = el
                    break
            except Exception:
                continue

        if keyword_input:
            keyword_input.click()
            keyword_input.fill("")
            keyword_input.fill(keyword)
            keyword_input.press("Enter")
            time.sleep(0.5)
            runtime.log(f"Rank Math keyword set: {keyword}", "success")
            return True

        try:
            page.evaluate(
                """
                    (keyword) => {
                        var inputs = document.querySelectorAll('input[placeholder*="Rank Math"], input.rank-math-focus-keyword');
                        if (inputs.length > 0) {
                            inputs[0].value = keyword;
                            inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
                            return true;
                        }
                        return false;
                    }
                """,
                keyword,
            )
            runtime.log(f"Rank Math keyword set via JS: {keyword}", "success")
            return True
        except Exception:
            runtime.log("Rank Math keyword field not found", "warning")
            return False

    except Exception as e:
        runtime.log(f"Error setting Rank Math keyword: {e}", "warning")
        return False
