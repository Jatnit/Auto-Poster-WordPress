"""ChatGPT Web browser content provider.

This module keeps the legacy browser automation behavior but moves it out of
`app.py`. Configure it with `ChatGPTWebRuntime` before calling public functions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from config.prompts import CONTACT_SECTION, PROMPT_PART1, PROMPT_PART2, clean_gemini_content
from wp_auto_poster.content.validation import strip_html_text as _strip_html_text_core

LogFunc = Callable[[str, str], None]


@dataclass
class ChatGPTWebRuntime:
    state: Any
    add_log: LogFunc
    wait_if_paused: Callable[[], bool]


_runtime: Optional[ChatGPTWebRuntime] = None


def configure_runtime(runtime: ChatGPTWebRuntime) -> None:
    global _runtime
    _runtime = runtime


def _require_runtime() -> ChatGPTWebRuntime:
    if _runtime is None:
        raise RuntimeError("ChatGPT Web runtime has not been configured")
    return _runtime


class _StateProxy:
    def __getattr__(self, name):
        return getattr(_require_runtime().state, name)

    def __setattr__(self, name, value):
        setattr(_require_runtime().state, name, value)


state = _StateProxy()


def add_log(message: str, log_type: str = "info") -> None:
    _require_runtime().add_log(message, log_type)


def wait_if_paused() -> bool:
    return _require_runtime().wait_if_paused()


def _gemini_response_text(html_or_text: str) -> str:
    """Strip HTML tags để đếm từ thật (không tính thẻ)."""
    return _strip_html_text_core(html_or_text)

# ===== CHATGPT WEB (Browser-based, no API key) =====

# Selectors / phrases tương đương cho ChatGPT. ChatGPT không có "Canvas mode"
# kiểu Gemini nhưng có "Canvas" panel khi dùng GPT-4o canvas. Tạm thời chỉ
# bắt error phrase và validate word count — đủ cho use-case sinh bài blog.
_CHATGPT_ERROR_PHRASES = [
    "something went wrong",
    "an error occurred",
    "please try again",
    "i can't help",
    "i'm not able to help",
    "tôi không thể",
    "đã xảy ra lỗi",
    "rate limit",
    "too many requests",
]


def _chatgpt_find_input(page) -> Optional[object]:
    """Tìm ô nhập prompt ChatGPT (ProseMirror contenteditable)."""
    selectors = [
        "#prompt-textarea",
        "div#prompt-textarea[contenteditable='true']",
        "div.ProseMirror[contenteditable='true']",
        "textarea[data-id='root']",
        "textarea[placeholder*='Message']",
        "textarea[placeholder*='Send a message']",
        "div[contenteditable='true'][role='textbox']",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=2500):
                return el
        except Exception:
            continue
    # Fallback: bất kỳ contenteditable nào
    try:
        el = page.locator("[contenteditable='true']").first
        if el.is_visible(timeout=3000):
            return el
    except Exception:
        pass
    return None


def _chatgpt_extract_response(page) -> str:
    """Lấy HTML của message cuối từ assistant."""
    selectors = [
        "[data-message-author-role='assistant'] .markdown",
        "[data-message-author-role='assistant'] [data-message-id]",
        "[data-message-author-role='assistant']",
        "div.markdown.prose",
        "div.agent-turn .markdown",
    ]
    for sel in selectors:
        try:
            nodes = page.locator(sel).all()
            if nodes:
                last = nodes[-1]
                html = last.inner_html() or ""
                if html and len(html) > 100:
                    return html
        except Exception:
            continue
    return ""


def _chatgpt_is_streaming(page) -> bool:
    """ChatGPT đang stream nếu có nút Stop hoặc data-streaming attr."""
    indicators = [
        "button[data-testid='stop-button']",
        "button[aria-label*='Stop']",
        "button[aria-label*='stop']",
        "[data-streaming='true']",
        "div.result-streaming",
    ]
    for sel in indicators:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=300):
                return True
        except Exception:
            continue
    return False


def _wait_for_chatgpt_response(page, max_wait: int = 240) -> str:
    """Chờ ChatGPT hoàn tất stream tương tự Gemini.

    - Mỗi 3s extract response, đếm từ.
    - Khi hết indicator streaming và word count ổn định ≥ 6s → coi xong.
    - Timeout cứng `max_wait`.
    """
    add_log("Đang chờ ChatGPT trả lời...", "info")
    time.sleep(3)

    last_word_count = 0
    stable_since = 0
    waited = 0
    last_html = ""

    while waited < max_wait:
        if not state.is_running:
            return last_html
        if state.is_paused:
            if not wait_if_paused():
                return last_html

        current_html = _chatgpt_extract_response(page)
        if current_html:
            last_html = current_html
            current_words = len(_gemini_response_text(current_html).split())
        else:
            current_words = 0

        streaming = _chatgpt_is_streaming(page)

        if current_words > last_word_count:
            last_word_count = current_words
            stable_since = 0
        else:
            stable_since += 3

        if not streaming and current_words > 0 and stable_since >= 6:
            add_log(
                f"ChatGPT đã hoàn tất: {current_words} từ", "info"
            )
            break

        if current_words > 0 and stable_since >= 18:
            add_log(
                f"Response ổn định {stable_since}s — coi như hoàn tất "
                f"({current_words} từ)",
                "info",
            )
            break

        time.sleep(3)
        waited += 3
        if waited % 15 == 0:
            add_log(
                f"Vẫn đang chờ ChatGPT... ({waited}s, {current_words} từ)",
                "info",
            )

    if waited >= max_wait:
        add_log(f"Timeout {max_wait}s khi chờ ChatGPT", "warning")

    time.sleep(2)
    return _chatgpt_extract_response(page) or last_html


def _validate_chatgpt_response(content: Optional[str], min_words: int) -> tuple:
    """(is_valid, reason, word_count). Logic tương tự Gemini, không có Canvas."""
    if not content:
        return False, "response rỗng hoặc không extract được", 0

    text = _gemini_response_text(content)
    word_count = len(text.split())
    lower = text.lower()
    for phrase in _CHATGPT_ERROR_PHRASES:
        if phrase in lower:
            return False, f"ChatGPT báo lỗi ('{phrase}')", word_count

    if word_count < min_words:
        return False, f"chỉ có {word_count}/{min_words} từ", word_count

    return True, "OK", word_count


def _send_prompt_to_chatgpt_once(page, prompt: str, fresh_page: bool = False) -> Optional[str]:
    """Gửi 1 prompt tới ChatGPT, không retry."""
    try:
        if fresh_page:
            add_log("Reload ChatGPT để reset state (giữ cùng conversation)...", "info")
            page.reload(wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

        input_area = _chatgpt_find_input(page)
        if not input_area:
            add_log("Không tìm thấy ô nhập ChatGPT", "error")
            try:
                page.screenshot(path="/tmp/chatgpt_error.png")
            except Exception:
                pass
            return None

        input_area.click()
        time.sleep(0.7)

        clean_prompt = prompt.replace("\r", " ")
        # ChatGPT ProseMirror chấp nhận newline nhưng để an toàn dùng fill()
        try:
            input_area.fill(clean_prompt)
        except Exception:
            page.keyboard.press("Meta+A")
            page.keyboard.press("Backspace")
            time.sleep(0.3)
            page.keyboard.type(clean_prompt, delay=0)

        time.sleep(1.5)

        # Click send button hoặc Enter
        send_selectors = [
            "button[data-testid='send-button']",
            "button[aria-label*='Send prompt']",
            "button[aria-label*='Send']",
            "button[aria-label*='Gửi']",
        ]
        sent = False
        for sel in send_selectors:
            try:
                btn = page.locator(sel).last
                if btn.is_visible(timeout=2000) and btn.is_enabled():
                    btn.click()
                    sent = True
                    add_log("Đã gửi prompt tới ChatGPT", "info")
                    break
            except Exception:
                continue

        if not sent:
            page.keyboard.press("Enter")
            add_log("Đã gửi prompt qua Enter", "info")

        response_html = _wait_for_chatgpt_response(page, max_wait=240)
        if not response_html:
            add_log("Không trích xuất được phản hồi ChatGPT", "error")
            return None

        words = len(_gemini_response_text(response_html).split())
        add_log(f"Nhận {words} từ từ ChatGPT", "success")
        return response_html

    except Exception as e:
        add_log(f"Lỗi khi gửi prompt ChatGPT: {e}", "error")
        return None


def send_prompt_to_chatgpt_web(
    page,
    prompt: str,
    min_words: int = 300,
    max_retries: Optional[int] = None,
) -> Optional[str]:
    """Gửi prompt đến ChatGPT với auto-retry (mirror Gemini Web)."""
    if max_retries is None:
        max_retries = int(state.config.get("chatgpt_max_prompt_retries", 2))

    total_attempts = max_retries + 1
    for attempt in range(1, total_attempts + 1):
        if not state.is_running:
            return None
        if state.is_paused and not wait_if_paused():
            return None

        if attempt > 1:
            add_log(f"Thử lại prompt ChatGPT lần {attempt}/{total_attempts}...", "warning")
            time.sleep(3)

        response = _send_prompt_to_chatgpt_once(
            page, prompt, fresh_page=(attempt > 1)
        )
        is_valid, reason, word_count = _validate_chatgpt_response(response, min_words)
        if is_valid:
            add_log(
                f"Response ChatGPT hợp lệ ({word_count} từ) sau {attempt} lần thử",
                "success",
            )
            return response

        add_log(
            f"Response ChatGPT không hợp lệ ({reason}). "
            f"{'Sẽ thử lại...' if attempt < total_attempts else 'Đã hết retry.'}",
            "warning",
        )

    add_log(f"Thất bại sau {total_attempts} lần thử ChatGPT", "error")
    return None


def _is_chatgpt_chat_ready(page) -> bool:
    """True khi đang ở ChatGPT chat và ô nhập prompt khả dụng."""
    try:
        current_url = page.url or ""
    except Exception:
        return False

    if "chatgpt.com" not in current_url:
        return False
    if "/auth/" in current_url or "auth0" in current_url:
        return False

    return _chatgpt_find_input(page) is not None


def generate_content_chatgpt_web(page, title: str, keyword: str) -> Optional[str]:
    """Sinh bài viết bằng ChatGPT Web (chat.openai.com / chatgpt.com).

    Login: nếu chưa đăng nhập, chờ user thao tác trong browser tối đa 10 phút,
    giống flow của Gemini Web. Cookie được persistent context lưu lại nên các
    lần sau không cần login lại.
    """
    try:
        if _is_chatgpt_chat_ready(page):
            add_log("Tiếp tục dùng cùng session ChatGPT hiện tại...", "info")
        else:
            add_log("Đang mở ChatGPT...", "info")
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)

            # Detect login: ChatGPT redirect /auth/login khi chưa đăng nhập
            needs_login = False
            try:
                cur = page.url
                if "/auth/login" in cur or "auth0" in cur or "login" in cur:
                    needs_login = True
                else:
                    # Có nút "Log in" / "Sign up" trên landing → cần login
                    login_btn = page.locator(
                        "a[href*='login'], button:has-text('Log in'), "
                        "button:has-text('Đăng nhập')"
                    ).first
                    if login_btn.is_visible(timeout=2000):
                        # Vẫn còn input area thì có thể là guest mode → check thêm
                        if not _chatgpt_find_input(page):
                            needs_login = True
            except Exception:
                pass

            if needs_login:
                add_log("Vui lòng đăng nhập ChatGPT trong cửa sổ browser!", "warning")
                add_log("Đang chờ đăng nhập (10 phút)...", "info")

                login_wait = 0
                max_login_wait = 600
                while login_wait < max_login_wait and state.is_running:
                    if state.is_paused and not wait_if_paused():
                        return None

                    time.sleep(5)
                    login_wait += 5

                    if not state.is_running:
                        return None

                    cur = page.url
                    if (
                        "chatgpt.com" in cur
                        and "/auth/" not in cur
                        and "login" not in cur
                    ):
                        if _chatgpt_find_input(page):
                            add_log("Đăng nhập ChatGPT thành công!", "success")
                            time.sleep(3)
                            break

                    if login_wait % 60 == 0:
                        remaining = (max_login_wait - login_wait) // 60
                        add_log(f"Còn {remaining} phút...", "info")

        if not _chatgpt_find_input(page):
            add_log("ChatGPT chưa sẵn sàng ô nhập prompt", "error")
            return None

        custom_prompt = state.config.get("gemini_prompt", "")
        min_words_full = int(state.config.get("gemini_min_words_full", 600))
        min_words_part = int(state.config.get("gemini_min_words_part", 300))

        if custom_prompt and "{title}" in custom_prompt and "{keyword}" in custom_prompt:
            if not state.is_running or (state.is_paused and not wait_if_paused()):
                return None

            add_log("Đang tạo nội dung với prompt tùy chỉnh (ChatGPT)...", "info")
            prompt = custom_prompt.format(title=title, keyword=keyword)
            content = send_prompt_to_chatgpt_web(page, prompt, min_words=min_words_full)

            if not content:
                add_log("Không thể tạo nội dung với ChatGPT", "error")
                return None

            word_count = len(_gemini_response_text(content).split())
            add_log(f"ChatGPT tạo {word_count} từ", "info")
        else:
            if not state.is_running or (state.is_paused and not wait_if_paused()):
                return None

            add_log("Đang tạo Phần 1/2 với ChatGPT...", "info")
            prompt1 = PROMPT_PART1.format(title=title, keyword=keyword)
            part1 = send_prompt_to_chatgpt_web(page, prompt1, min_words=min_words_part)
            if not part1:
                add_log("Không thể tạo Phần 1 (ChatGPT)", "error")
                return None
            add_log(f"Phần 1: {len(_gemini_response_text(part1).split())} từ", "info")

            if not state.is_running or (state.is_paused and not wait_if_paused()):
                return None

            time.sleep(3)
            add_log("Đang tạo Phần 2/2 với ChatGPT...", "info")
            prompt2 = PROMPT_PART2.format(title=title, keyword=keyword)
            part2 = send_prompt_to_chatgpt_web(page, prompt2, min_words=min_words_part)
            if not part2:
                add_log("Không thể tạo Phần 2 (ChatGPT)", "error")
                return None
            add_log(f"Phần 2: {len(_gemini_response_text(part2).split())} từ", "info")

            contact = CONTACT_SECTION.format(keyword=keyword)
            content = part1 + "\n\n" + part2 + "\n\n" + contact

        # Tận dụng cleaner sẵn có — cùng heuristic cắt intro/outro hoạt động OK
        # với output ChatGPT vì cũng là HTML/markdown.
        content = clean_gemini_content(content)

        final_words = len(_gemini_response_text(content).split())
        min_valid_words = int(state.config.get("content_min_valid_words", 1401))
        if final_words < min_valid_words:
            add_log(
                f"Sau clean còn {final_words}/{min_valid_words} từ — bỏ qua bài này", "error"
            )
            return None

        add_log(f"Tổng cộng (ChatGPT): {final_words} từ", "success")
        add_log(f"Đã tạo nội dung cho: {title}", "success")
        return content

    except Exception as e:
        add_log(f"Lỗi ChatGPT Web: {e}", "error")
        return None
