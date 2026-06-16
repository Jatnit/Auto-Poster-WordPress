"""Gemini Web browser content provider.

This module keeps the legacy browser automation behavior but moves it out of
`app.py`. Configure it with `GeminiWebRuntime` before calling public functions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from config.prompts import CONTACT_SECTION, PROMPT_PART1, PROMPT_PART2, clean_gemini_content
from wp_auto_poster.content.validation import strip_html_text as _strip_html_text_core

LogFunc = Callable[[str, str], None]


@dataclass
class GeminiWebRuntime:
    state: Any
    add_log: LogFunc
    wait_if_paused: Callable[[], bool]


_runtime: Optional[GeminiWebRuntime] = None


def configure_runtime(runtime: GeminiWebRuntime) -> None:
    global _runtime
    _runtime = runtime


def _require_runtime() -> GeminiWebRuntime:
    if _runtime is None:
        raise RuntimeError("Gemini Web runtime has not been configured")
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

import re

from wp_auto_poster.content.html_convert import (
    markdown_to_html_minimal as _markdown_to_html_minimal_core,
)

# GEMINI WEB CONTENT GENERATION (Browser-based, free, no API key)

# Các cụm báo lỗi của Gemini — nếu response chứa 1 trong các cụm này thì coi như lỗi, phải retry
_GEMINI_ERROR_PHRASES = [
    "something went wrong",
    "xin vui lòng thử lại",
    "đã xảy ra lỗi",
    "please try again",
    "i can't help",
    "i'm not able to help",
    "tôi không thể",
    "unable to generate",
    "try again later",
]

# Số lần retry tối đa khi phát hiện Gemini chuyển sang Canvas mode (tách
# khỏi gemini_max_prompt_retries hiện có để dễ tune).
GEMINI_CANVAS_MAX_RETRIES = 2

# Cụm phrase điển hình xuất hiện khi inline response chỉ là mô tả Canvas.
# So sánh case-insensitive với text đã strip HTML.
#
# IMPORTANT: chỉ giữ phrase đặc trưng cho Canvas / file attachment / PDF — KHÔNG
# liệt kê các cụm SEO chung (ví dụ "seo meta description", "từ khóa chính:",
# "cấu trúc nội dung:") vì bài blog inline thực tế hoàn toàn có thể chứa các
# cụm này. False-positive ở phần này sẽ chặn nhầm bài hợp lệ.
_GEMINI_CANVAS_PHRASES = [
    # Vietnamese — Canvas / Document panel markers
    "định dạng: pdf",
    "đã tạo tài liệu",
    "tài liệu đính kèm",
    "tài liệu này có thể tải",
    "có thể tải tệp pdf",
    "bạn có thể tải tệp pdf",
    "bài viết blog chuẩn seo của bạn đã được khởi tạo",
    "pdf chuyên nghiệp",
    # English fallback
    "format: pdf",
    "document attached",
    "i've created a document",
    "i have created a document",
    "the document is ready",
]

# DOM selector best-effort cho Canvas / Document panel + file attachment chip.
# OR-combine: chỉ cần 1 selector visible là tín hiệu Canvas.
_GEMINI_CANVAS_DOM_SELECTORS = [
    "immersive-panel",
    "[data-test-id*='canvas']",
    ".canvas-panel",
    "[aria-label*='Canvas']",
    "[aria-label*='canvas']",
    "[aria-label*='Document']",
    "[aria-label*='tài liệu']",
    "[role='complementary'] [class*='document']",
    "[role='complementary'] [class*='attachment']",
    # File attachment chip xuất hiện trong inline response
    ".model-response-text a[href*='document']",
    ".model-response-text [class*='attachment-chip']",
    ".model-response-text [class*='file-attachment']",
    ".model-response-text [aria-label*='PDF']",
]

# Ngưỡng heuristic structural
_GEMINI_CANVAS_MIN_HEADINGS = 2     # < 2 H2/H3 + có phrase Canvas → suspect
_GEMINI_CANVAS_SUSPECT_WORDS = 100  # text >= 100 từ mới áp dụng structural fail


def _anti_canvas_suffix() -> str:
    """
    Trả về đoạn chỉ thị Anti-Canvas bằng tiếng Việt + English fallback.
    Append vào cuối prompt TẠI RUNTIME trước khi gửi tới Gemini Web.
    KHÔNG sửa template gốc trong config/prompts.py.
    """
    return (
        "\n\n"
        "QUAN TRỌNG (BẮT BUỘC):\n"
        "- Trả lời TRỰC TIẾP trong khung chat dưới dạng HTML thuần.\n"
        "- KHÔNG tạo Canvas, KHÔNG tạo Document, KHÔNG tạo file PDF, "
        "KHÔNG tạo file đính kèm dưới bất kỳ hình thức nào.\n"
        "- KHÔNG gọi tool Canvas/Document/Immersive.\n"
        "- KHÔNG mô tả tài liệu, KHÔNG nói 'đã tạo tài liệu', "
        "KHÔNG nói 'Định dạng: PDF', KHÔNG kèm icon file.\n"
        "- Toàn bộ nội dung bài viết PHẢI xuất hiện inline ngay trong tin "
        "nhắn chat, đầy đủ các thẻ <h2>, <h3>, <p>, <ul>, <li>, <strong>.\n"
        "\n"
        "IMPORTANT (MANDATORY):\n"
        "- Reply DIRECTLY in the chat as plain HTML.\n"
        "- DO NOT create a Canvas, Document, PDF, or any attached file.\n"
        "- DO NOT invoke any Canvas/Document/Immersive tool.\n"
        "- The full article must appear inline in this chat message.\n"
    )


def _markdown_to_html_minimal(md: str) -> str:
    """
    Convert markdown rất tối thiểu sang HTML cho rescue Canvas.

    Rules:
        - '## X'  → <h2>X</h2>
        - '### X' → <h3>X</h3>
        - Các dòng liên tiếp bắt đầu '- ' → 1 <ul> chứa nhiều <li>X</li>
        - Block ngăn cách bằng dòng trống (không phải heading/list) → <p>...</p>
        - Inline '**X**' → <strong>X</strong>

    Idempotent: dòng đã là HTML block-level (<h2>/<h3>/<p>/<ul>/<li>...)
    được pass through nguyên trạng để không double-wrap.

    Không xử lý code block / link / image phức tạp — đủ cho rescue Canvas.
    """
    return _markdown_to_html_minimal_core(md)


def _is_canvas_response(page, html_content: Optional[str]) -> tuple:
    """
    Phát hiện response của Gemini có phải đang ở Canvas / Document mode hay
    chỉ là mô tả meta về tài liệu hay không.

    Returns:
        (is_canvas: bool, reason: str)
        - (True, reason) nếu nghi ngờ Canvas.
        - (False, "")    nếu không.

    Heuristic:
      H1. DOM check  : tìm Canvas panel / file attachment chip qua selector.
                       Đây là tín hiệu **deterministic** từ DOM thực tế của
                       Gemini Web, không có false positive.

    Lưu ý: phiên bản trước có thêm phrase + structural fallback, nhưng nó
    sinh quá nhiều false positive trên bài blog SEO bình thường (ví dụ bài
    có "<!-- SEO Meta Description -->", "Định dạng: ...", "Từ khóa chính:"
    trong nội dung) khi `.model-response-text` trả markdown / text thuần.
    Layer 1 (anti-canvas suffix trong prompt) + Layer 3 (rescue khi DOM
    panel xuất hiện) đã đủ để chặn Canvas thực sự. Nhánh phrase+structural
    được bỏ để nhường ưu tiên cho preservation (clauses 3.1, 3.3).

    Edge cases:
      - page=None              → bỏ qua H1 → (False, "").
      - html_content rỗng/None → vẫn chạy H1 trên page; H1 âm → (False, "").
      - Mọi page.locator call đều bọc try/except → hàm không bao giờ raise.
    """
    # --- H1: DOM check (best-effort, không raise) ---
    if page is not None:
        for selector in _GEMINI_CANVAS_DOM_SELECTORS:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=500):
                    return (
                        True,
                        f"phát hiện Canvas/Document panel qua DOM ({selector})",
                    )
            except Exception:
                continue

    # Phrase + structural fallback đã bị disable (xem docstring). Chỉ DOM
    # check là tín hiệu Canvas; nếu không match → response được coi là
    # inline hợp lệ, để các layer phía sau (validate word count / error
    # phrase) xử lý tiếp.
    return False, ""


def _try_extract_canvas_content(page) -> Optional[str]:
    """
    Best-effort: đọc nội dung HTML/Markdown thực từ Canvas / Document panel
    của Gemini Web. Trả về HTML khả dụng (đủ heading + paragraph) hoặc None
    nếu không trích được nội dung dùng được.

    Chiến lược:
      1. Iterate `canvas_containers` selector list.
      2. Với mỗi selector visible, đọc inner_html() và inner_text() (try/except).
      3. Nếu inner_html đã là HTML có ≥ 2 <h2>/<h3> và ≥ 200 từ → return luôn.
      4. Else thử convert inner_text qua `_markdown_to_html_minimal`; nếu kết
         quả có ≥ 2 heading và ≥ 200 từ → return.
      5. Hết list → return None.

    Mọi page.locator / inner_html / inner_text call đều bọc try/except nên
    hàm không bao giờ raise.
    """
    canvas_containers = [
        "immersive-panel",
        "[data-test-id*='canvas'] [class*='content']",
        ".canvas-panel",
        "[role='complementary']",
    ]

    for sel in canvas_containers:
        # Step 1+2: locate + read raw content (best-effort, không raise)
        html = ""
        txt = ""
        try:
            el = page.locator(sel).first
            if not el.is_visible(timeout=500):
                continue
            try:
                html = el.inner_html() or ""
            except Exception:
                html = ""
            try:
                txt = el.inner_text() or ""
            except Exception:
                txt = ""
        except Exception:
            continue

        if not html and not txt:
            continue

        # Step 3: nếu inner_html đã có structure → dùng luôn
        if html:
            heading_count = len(
                re.findall(r"<h[23][^>]*>", html, flags=re.IGNORECASE)
            )
            if heading_count >= 2 and len(_gemini_response_text(html).split()) >= 200:
                add_log(
                    f"Rescue Canvas: đọc được {heading_count} heading từ '{sel}'",
                    "success",
                )
                return html

        # Step 4: fallback convert markdown → HTML tối thiểu
        if txt:
            try:
                converted = _markdown_to_html_minimal(txt)
            except Exception:
                converted = ""
            if converted:
                heading_count = len(
                    re.findall(r"<h[23][^>]*>", converted, flags=re.IGNORECASE)
                )
                if (
                    heading_count >= 2
                    and len(_gemini_response_text(converted).split()) >= 200
                ):
                    add_log(
                        f"Rescue Canvas: convert markdown từ '{sel}' "
                        f"({heading_count} heading)",
                        "success",
                    )
                    return converted

    # Step 5: hết list → fail
    return None


def _validate_gemini_response(content: Optional[str], min_words: int, page=None) -> tuple:
    """
    Kiểm tra response của Gemini có hợp lệ không.
    Returns: (is_valid: bool, reason: str, word_count: int)

    Thứ tự check (đảm bảo preservation khi page=None):
      0. content rỗng                     -> invalid (như cũ)
      1. NEW: Canvas check (chỉ khi page) -> invalid với reason Canvas
      2. error phrase                     -> invalid (như cũ)
      3. word count < min_words           -> invalid (như cũ)
      4. -> valid
    """
    if not content:
        return False, "response rỗng hoặc không extract được", 0

    # NEW: Layer 2 detection — chỉ chạy khi có page (backward-compatible
    # với caller cũ truyền 2 arg / page=None).
    if page is not None:
        is_canvas, canvas_reason = _is_canvas_response(page, content)
        if is_canvas:
            word_count = len(_gemini_response_text(content).split())
            return False, f"Canvas mode: {canvas_reason}", word_count

    text = _gemini_response_text(content)
    word_count = len(text.split())

    # Check 1: Gemini trả về câu báo lỗi
    lower = text.lower()
    for phrase in _GEMINI_ERROR_PHRASES:
        if phrase in lower:
            return False, f"Gemini trả thông báo lỗi ('{phrase}')", word_count

    # Check 2: Quá ngắn
    if word_count < min_words:
        return False, f"chỉ có {word_count}/{min_words} từ", word_count

    return True, "OK", word_count


def _find_input_area(page):
    """Tìm ô nhập prompt của Gemini, thử nhiều selector."""
    input_selectors = [
        "p[contenteditable='true']",
        "div[contenteditable='true']",
        "rich-textarea p[contenteditable='true']",
        "rich-textarea div[contenteditable='true']",
        ".ql-editor p",
        "textarea[placeholder*='prompt']",
        "textarea[placeholder*='Prompt']",
        "[data-placeholder*='Enter']",
        "[aria-label*='Enter a prompt']",
        "[aria-label*='prompt']",
    ]
    for selector in input_selectors:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=3000):
                add_log(f"Tìm thấy ô nhập: {selector}", "info")
                return el
        except:
            continue
    # Fallback: bất kỳ contenteditable nào
    try:
        el = page.locator("[contenteditable='true']").first
        if el.is_visible(timeout=5000):
            add_log("Tìm thấy phần tử contenteditable (fallback)", "info")
            return el
    except:
        pass
    return None


def _is_gemini_chat_ready(page) -> bool:
    """True khi đang ở Gemini chat và ô nhập prompt khả dụng."""
    try:
        current_url = page.url or ""
    except Exception:
        return False

    if "gemini.google.com" not in current_url or "accounts.google" in current_url:
        return False

    return _find_input_area(page) is not None


def _extract_gemini_response(page) -> str:
    """Trích xuất nội dung response cuối cùng, thử nhiều selector."""
    response_selectors = [
        ".model-response-text",
        ".response-content",
        ".markdown-content",
        "[data-message-author-role='model']",
        ".message-content",
    ]
    for selector in response_selectors:
        try:
            responses = page.locator(selector).all()
            if responses:
                last_response = responses[-1]
                html = last_response.inner_html()
                if html and len(html) > 100:
                    return html
        except:
            continue
    return ""


def _wait_for_gemini_response(page, max_wait: int = 240) -> str:
    """
    Chờ Gemini trả lời xong theo chiến thuật:
    - Mỗi 3s extract response hiện tại và đếm từ
    - Nếu word count không tăng trong 15s liên tiếp -> coi như đã xong
    - Hoặc khi không còn loading indicator cũng dừng
    - Timeout tối đa max_wait giây

    Returns HTML của response (có thể rỗng nếu timeout).
    """
    add_log("Đang chờ Gemini trả lời...", "info")
    time.sleep(3)  # Chờ response bắt đầu streaming

    last_word_count = 0
    stable_since = 0  # giây đã qua mà word count không tăng
    waited = 0
    last_html = ""

    while waited < max_wait:
        if not state.is_running:
            add_log("Stopped while waiting for Gemini", "warning")
            return last_html
        if state.is_paused:
            add_log("Paused - waiting...", "info")
            if not wait_if_paused():
                return last_html
            add_log("Resuming Gemini wait...", "info")

        current_html = _extract_gemini_response(page)
        if current_html:
            last_html = current_html
            current_words = len(_gemini_response_text(current_html).split())
        else:
            current_words = 0

        # Check loading indicator
        any_loading = False
        try:
            loading_indicators = page.locator(
                ".loading, .thinking, [aria-busy='true'], .response-streaming"
            ).all()
            for indicator in loading_indicators:
                try:
                    if indicator.is_visible(timeout=300):
                        any_loading = True
                        break
                except:
                    continue
        except:
            pass

        # Điều kiện kết thúc: không còn loading VÀ word count không tăng trong 6s
        if current_words > last_word_count:
            last_word_count = current_words
            stable_since = 0
        else:
            stable_since += 3

        if not any_loading and current_words > 0 and stable_since >= 6:
            add_log(
                f"Gemini đã hoàn tất: {current_words} từ (ổn định {stable_since}s)",
                "info",
            )
            break

        # Stable lâu nhưng có text -> cũng coi là xong (phòng khi loading indicator bị stuck)
        if current_words > 0 and stable_since >= 18:
            add_log(
                f"Response đã ổn định {stable_since}s -> coi như hoàn tất ({current_words} từ)",
                "info",
            )
            break

        time.sleep(3)
        waited += 3
        if waited % 15 == 0:
            add_log(
                f"Vẫn đang chờ... ({waited}s, đã có {current_words} từ)", "info"
            )

    if waited >= max_wait:
        add_log(f"Timeout {max_wait}s khi chờ Gemini", "warning")

    time.sleep(2)  # buffer cho render cuối
    return _extract_gemini_response(page) or last_html


def _send_prompt_once(page, prompt: str, fresh_page: bool = True) -> Optional[str]:
    """Gửi prompt 1 lần (không retry). Trả về HTML response hoặc None nếu lỗi."""
    try:
        if fresh_page:
            add_log("Reload Gemini để đảm bảo state sạch...", "info")
            page.reload(wait_until="domcontentloaded")
            time.sleep(5)

        input_area = _find_input_area(page)
        if not input_area:
            add_log("Không tìm thấy ô nhập Gemini", "error")
            try:
                page.screenshot(path="/tmp/gemini_error.png")
                add_log("Đã lưu screenshot tại /tmp/gemini_error.png", "info")
            except:
                pass
            return None

        input_area.click()
        time.sleep(1)

        # Clean prompt - thay newline bằng space để tránh gửi sớm
        clean_prompt = prompt.replace("\n", " ").replace("\r", " ")
        while "  " in clean_prompt:
            clean_prompt = clean_prompt.replace("  ", " ")

        add_log("Đang nhập prompt...", "info")
        try:
            input_area.fill(clean_prompt)
            add_log("Đã nhập prompt qua fill()", "info")
        except:
            add_log("Đang gõ bằng bàn phím...", "info")
            page.keyboard.press("Meta+A")
            page.keyboard.press("Backspace")
            time.sleep(0.3)
            page.keyboard.type(clean_prompt, delay=0)

        time.sleep(2)

        # Gửi prompt
        send_selectors = [
            "button[aria-label*='Send']",
            "button[aria-label*='Gửi']",
            "button.send-button",
            "[data-test-id='send-button']",
            "button:has-text('Send')",
        ]
        sent = False
        for selector in send_selectors:
            try:
                send_btn = page.locator(selector).last
                if send_btn.is_visible(timeout=2000):
                    send_btn.click()
                    sent = True
                    add_log("Đã gửi prompt tới Gemini", "info")
                    break
            except:
                continue

        if not sent:
            page.keyboard.press("Enter")
            add_log("Đã gửi prompt qua phím Enter", "info")

        # Chờ & trích response (logic tăng cường)
        response_html = _wait_for_gemini_response(page, max_wait=240)
        if not response_html:
            add_log("Không thể trích xuất phản hồi Gemini", "error")
            return None

        # Layer 3 — nếu phát hiện Canvas, thử rescue trước khi giao về validate
        is_canvas, reason = _is_canvas_response(page, response_html)
        if is_canvas:
            add_log(
                f"Phát hiện Canvas mode ({reason}) — đang thử rescue...",
                "warning",
            )
            rescued = _try_extract_canvas_content(page)
            if rescued:
                words = len(_gemini_response_text(rescued).split())
                add_log(f"Rescue Canvas thành công: {words} từ", "success")
                return rescued
            add_log(
                "Rescue Canvas thất bại — sẽ retry với prompt nhấn mạnh",
                "warning",
            )
            # Trả response_html nguyên gốc; validate sẽ invalidate vì Canvas
            # → caller retry với prompt nhấn mạnh hơn.
            return response_html

        words = len(_gemini_response_text(response_html).split())
        add_log(f"Nhận được {words} từ từ Gemini", "success")
        return response_html

    except Exception as e:
        add_log(f"Lỗi khi gửi prompt: {e}", "error")
        return None


def send_prompt_to_gemini_web(
    page,
    prompt: str,
    min_words: int = 300,
    max_retries: Optional[int] = None,
) -> Optional[str]:
    """
    Gửi prompt tới Gemini Web với auto-retry.

    Retry trong các trường hợp:
    - Không extract được response (rỗng / mất ô nhập)
    - Gemini trả thông báo lỗi
    - Số từ < min_words (response bị cắt hoặc quá ngắn)

    Args:
        page: Playwright page
        prompt: nội dung prompt
        min_words: ngưỡng số từ tối thiểu chấp nhận
        max_retries: số lần thử lại (None = đọc từ config)

    Returns HTML của response hợp lệ, hoặc None nếu đã hết retry.
    """
    if max_retries is None:
        max_retries = int(state.config.get("gemini_max_prompt_retries", 2))

    canvas_failures = 0  # Đếm riêng số lần fail vì Canvas mode
    current_prompt = prompt  # Sẽ bị escalate khi gặp Canvas, giữ nguyên prompt gốc cho non-Canvas
    total_attempts = max_retries + 1
    for attempt in range(1, total_attempts + 1):
        # Check stop/pause trước mỗi attempt
        if not state.is_running:
            return None
        if state.is_paused and not wait_if_paused():
            return None

        if attempt > 1:
            add_log(
                f"Thử lại prompt lần {attempt}/{total_attempts}...", "warning"
            )
            time.sleep(3)

        # Lần đầu không cần reload (đã navigate), từ lần 2 trở đi reload để reset state
        response = _send_prompt_once(page, current_prompt, fresh_page=(attempt > 1))

        is_valid, reason, word_count = _validate_gemini_response(
            response, min_words, page=page
        )
        if is_valid:
            add_log(
                f"Response hợp lệ ({word_count} từ) sau {attempt} lần thử",
                "success",
            )
            return response

        # Canvas mode: đếm + escalate prompt; non-Canvas branches giữ nguyên flow cũ
        if reason.startswith("Canvas mode"):
            canvas_failures += 1
            if canvas_failures > GEMINI_CANVAS_MAX_RETRIES:
                add_log(
                    f"Gemini chuyển Canvas {canvas_failures} lần liên tiếp, "
                    f"bỏ qua bài này",
                    "error",
                )
                return None
            current_prompt = (
                "**LẦN TRƯỚC BẠN ĐÃ DÙNG CANVAS / TẠO FILE PDF — ĐIỀU NÀY SAI.** "
                "Lần này TUYỆT ĐỐI không được dùng Canvas, Document, hay tạo "
                "file PDF/đính kèm. Trả lời inline trong chat.\n\n"
                + prompt
                + _anti_canvas_suffix()
            )

        add_log(
            f"Response không hợp lệ ({reason}). "
            f"{'Sẽ thử lại...' if attempt < total_attempts else 'Đã hết lượt retry.'}",
            "warning",
        )

    add_log(f"Thất bại sau {total_attempts} lần thử prompt", "error")
    return None


def generate_content_gemini_web(page, title: str, keyword: str) -> Optional[str]:
    try:
        if _is_gemini_chat_ready(page):
            add_log("Tiếp tục dùng cùng session Gemini hiện tại...", "info")
        else:
            add_log("Đang mở Gemini Chat...", "info")

            # Chỉ navigate khi chưa có session sẵn sàng
            page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)  # Wait for page to fully load

            # Check if need to login
            needs_login = False
            try:
                if "accounts.google.com" in page.url:
                    needs_login = True
                elif page.locator("a[href*='accounts.google'], button:has-text('Sign in'), button:has-text('Đăng nhập')").first.is_visible(timeout=3000):
                    needs_login = True
            except:
                pass

            if needs_login:
                add_log("Vui lòng đăng nhập Google trong cửa sổ browser!", "warning")
                add_log("Đang chờ đăng nhập (10 phút)...", "info")

                # Wait up to 10 minutes for login
                login_wait = 0
                max_login_wait = 600  # 10 minutes
                while login_wait < max_login_wait and state.is_running:
                    # Check if paused
                    if state.is_paused:
                        if not wait_if_paused():
                            add_log("Stopped while waiting for login", "warning")
                            return None

                    time.sleep(5)
                    login_wait += 5

                    # Check if stopped
                    if not state.is_running:
                        add_log("Stopped by user", "warning")
                        return None

                    # Check if we're now on Gemini app page
                    current_url = page.url
                    if "gemini.google.com" in current_url and "accounts.google" not in current_url:
                        add_log("Đăng nhập thành công!", "success")
                        time.sleep(3)  # Extra wait for page load
                        break

                    remaining = max_login_wait - login_wait
                    if login_wait % 60 == 0:
                        add_log(f"Còn {remaining // 60} phút...", "info")

        if not _find_input_area(page):
            add_log("Gemini chưa sẵn sàng ô nhập prompt", "error")
            return None
        
        # Get custom prompt from config, or use default
        custom_prompt = state.config.get("gemini_prompt", "")

        # Ngưỡng số từ tối thiểu (đọc từ config)
        min_words_full = int(state.config.get("gemini_min_words_full", 600))
        min_words_part = int(state.config.get("gemini_min_words_part", 300))

        if custom_prompt and "{title}" in custom_prompt and "{keyword}" in custom_prompt:
            # Check stop/pause before generating
            if not state.is_running:
                return None
            if state.is_paused:
                if not wait_if_paused():
                    return None

            # Use custom single prompt
            add_log("Đang tạo nội dung với prompt tùy chỉnh...", "info")
            prompt = custom_prompt.format(title=title, keyword=keyword) + _anti_canvas_suffix()
            content = send_prompt_to_gemini_web(page, prompt, min_words=min_words_full)

            if not content:
                add_log("Không thể tạo nội dung (đã hết retry)", "error")
                return None

            word_count = len(_gemini_response_text(content).split())
            add_log(f"Đã tạo {word_count} từ", "info")

        else:
            # Fall back to two-part generation
            # Check stop/pause
            if not state.is_running:
                return None
            if state.is_paused:
                if not wait_if_paused():
                    return None

            add_log("Đang tạo Phần 1/2 với Gemini Chat...", "info")
            prompt1 = PROMPT_PART1.format(title=title, keyword=keyword) + _anti_canvas_suffix()
            part1 = send_prompt_to_gemini_web(page, prompt1, min_words=min_words_part)

            if not part1:
                add_log("Không thể tạo Phần 1 (đã hết retry)", "error")
                return None

            word_count_1 = len(_gemini_response_text(part1).split())
            add_log(f"Phần 1: {word_count_1} từ", "info")

            # Check stop/pause before part 2
            if not state.is_running:
                return None
            if state.is_paused:
                if not wait_if_paused():
                    return None

            time.sleep(3)

            add_log("Đang tạo Phần 2/2 với Gemini Chat...", "info")
            prompt2 = PROMPT_PART2.format(title=title, keyword=keyword) + _anti_canvas_suffix()
            part2 = send_prompt_to_gemini_web(page, prompt2, min_words=min_words_part)

            if not part2:
                add_log("Không thể tạo Phần 2 (đã hết retry)", "error")
                return None

            word_count_2 = len(_gemini_response_text(part2).split())
            add_log(f"Phần 2: {word_count_2} từ", "info")

            # Combine parts
            contact = CONTACT_SECTION.format(keyword=keyword)
            content = part1 + "\n\n" + part2 + "\n\n" + contact

        # Clean content - remove intro and outro text from Gemini
        content = clean_gemini_content(content)

        # Validate lần cuối sau khi clean (phòng khi clean cắt nhiều quá)
        final_words = len(_gemini_response_text(content).split())
        min_valid_words = int(state.config.get("content_min_valid_words", 1401))
        if final_words < min_valid_words:
            add_log(
                f"Sau khi clean chỉ còn {final_words}/{min_valid_words} từ (quá ngắn) - bỏ qua bài này",
                "error",
            )
            return None

        add_log(f"Tổng cộng: {final_words} từ", "success")
        add_log(f"Đã tạo nội dung cho: {title}", "success")

        return content

    except Exception as e:
        add_log(f"Lỗi Gemini Chat: {e}", "error")
        return None
