"""Best-effort cleanup for browser AI provider chat sessions."""

from __future__ import annotations

import re
import time
from typing import Callable

from wp_auto_poster.wordpress.browser import click_first_visible, click_visible_by_text

LogFunc = Callable[[str, str], None]


def delete_current_gemini_session(page, log_func: LogFunc) -> bool:
    """Delete the current Gemini chat session when URL points to a concrete session."""
    try:
        current_url = page.url or ""
        if not re.search(r"gemini\.google\.com/(?:app|gem)/[^/?#]+", current_url):
            log_func("Gemini: không thấy session cụ thể để xóa (bỏ qua)", "info")
            return False

        log_func("Gemini: đang xóa session chat vừa dùng...", "info")
        old_url = current_url

        menu_selectors = [
            "[data-test-id='actions-menu-button']",
            "[data-test-id*='actions-menu']",
            "button[aria-label*='More options']",
            "button[aria-label*='More']",
            "button[aria-label*='Tùy chọn']",
            "button[aria-label*='Tuỳ chọn']",
            "button[aria-haspopup='menu']",
        ]
        delete_selectors = [
            "[role='menuitem']:has-text('Delete')",
            "button:has-text('Delete')",
            "[role='menuitem']:has-text('Xóa')",
            "button:has-text('Xóa')",
            "li:has-text('Delete')",
            "li:has-text('Xóa')",
        ]
        confirm_selectors = [
            "button:has-text('Delete')",
            "button:has-text('Xóa')",
            "[role='button']:has-text('Delete')",
            "[role='button']:has-text('Xóa')",
            "button:has-text('Confirm')",
            "button:has-text('Xác nhận')",
        ]

        opened_menu = click_first_visible(page, menu_selectors, timeout=1500)
        if not opened_menu:
            try:
                page.mouse.move(190, 210)
                time.sleep(0.4)
            except Exception:
                pass
            opened_menu = click_first_visible(page, menu_selectors, timeout=1200)

        if not opened_menu:
            log_func("Gemini: không mở được menu session để xóa", "warning")
            return False

        time.sleep(0.5)
        deleted = click_first_visible(page, delete_selectors, timeout=1200)
        if not deleted:
            deleted = click_visible_by_text(page, ["delete", "xóa", "xoá", "remove"])
        if not deleted:
            log_func("Gemini: không tìm thấy nút Delete/Xóa", "warning")
            return False

        time.sleep(0.6)
        click_first_visible(page, confirm_selectors, timeout=1000, require_enabled=True)
        click_visible_by_text(page, ["delete", "xóa", "xoá", "confirm", "xác nhận"])

        for _ in range(8):
            time.sleep(0.4)
            try:
                if page.url != old_url:
                    log_func("Gemini: đã xóa session chat", "success")
                    return True
            except Exception:
                break

        log_func("Gemini: đã gửi lệnh xóa session (không xác minh được URL)", "info")
        return True
    except Exception as exc:
        log_func(f"Gemini: lỗi khi xóa session chat: {exc}", "warning")
        return False


def delete_current_chatgpt_session(page, log_func: LogFunc) -> bool:
    """Delete the current ChatGPT chat session when URL points to a concrete session."""
    try:
        current_url = page.url or ""
        if not re.search(r"chatgpt\.com/c/[^/?#]+", current_url):
            log_func("ChatGPT: không thấy session /c/<id> để xóa (bỏ qua)", "info")
            return False

        log_func("ChatGPT: đang xóa session chat vừa dùng...", "info")
        old_url = current_url

        menu_selectors = [
            "button[data-testid='conversation-options-button']",
            "button[aria-label*='Conversation options']",
            "button[aria-label*='More']",
            "button[aria-label*='more']",
            "button[aria-haspopup='menu']",
        ]
        delete_selectors = [
            "[role='menuitem']:has-text('Delete')",
            "button:has-text('Delete')",
            "[role='menuitem']:has-text('Delete chat')",
            "button:has-text('Delete chat')",
            "[role='menuitem']:has-text('Xóa')",
            "button:has-text('Xóa')",
        ]
        confirm_selectors = [
            "button:has-text('Delete')",
            "button:has-text('Delete chat')",
            "button:has-text('Confirm')",
            "button:has-text('Xóa')",
            "button:has-text('Xác nhận')",
        ]

        opened_menu = click_first_visible(page, menu_selectors, timeout=1500)
        if not opened_menu:
            log_func("ChatGPT: không mở được menu session để xóa", "warning")
            return False

        time.sleep(0.5)
        deleted = click_first_visible(page, delete_selectors, timeout=1200)
        if not deleted:
            deleted = click_visible_by_text(page, ["delete chat", "delete", "xóa", "xoá"])
        if not deleted:
            log_func("ChatGPT: không tìm thấy nút Delete/Xóa", "warning")
            return False

        time.sleep(0.6)
        click_first_visible(page, confirm_selectors, timeout=1000, require_enabled=True)
        click_visible_by_text(page, ["delete chat", "delete", "confirm", "xóa", "xác nhận"])

        for _ in range(8):
            time.sleep(0.4)
            try:
                if page.url != old_url:
                    log_func("ChatGPT: đã xóa session chat", "success")
                    return True
            except Exception:
                break

        log_func("ChatGPT: đã gửi lệnh xóa session (không xác minh được URL)", "info")
        return True
    except Exception as exc:
        log_func(f"ChatGPT: lỗi khi xóa session chat: {exc}", "warning")
        return False


def cleanup_provider_chat_session(page, provider: str, log_func: LogFunc) -> bool:
    """Clean up the active browser provider session after content generation."""
    if provider == "gemini_web":
        return delete_current_gemini_session(page, log_func)
    if provider == "chatgpt_web":
        return delete_current_chatgpt_session(page, log_func)
    return False
