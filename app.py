#!/usr/bin/env python3

import os
import random
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from typing import Optional

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

from config.settings import (
    state, add_log, wait_if_paused,
    load_site_presets, save_site_presets, save_app_config,
)
from config.prompts import PROMPT_PART1, PROMPT_PART2, CONTACT_SECTION, clean_gemini_content
from ai_providers.ollama import (
    generate_content_ollama as _generate_content_ollama,
    check_ollama, OLLAMA_AVAILABLE
)
from ai_providers.gemini_api import (
    generate_content_gemini as _generate_content_gemini,
    GEMINI_AVAILABLE
)

try:
    from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# WRAPPER FUNCTIONS (to pass state.config and add_log)

def generate_content_ollama(title: str, keyword: str) -> Optional[str]:
    return _generate_content_ollama(title, keyword, state.config, add_log)

def generate_content_gemini(title: str, keyword: str) -> Optional[str]:
    return _generate_content_gemini(
        title, keyword, 
        state.config.get("gemini_api_key", ""),
        add_log
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


def _gemini_response_text(html_or_text: str) -> str:
    """Strip HTML tags để đếm từ thật (không tính thẻ)."""
    if not html_or_text:
        return ""
    text = re.sub(r"<[^>]*>", " ", html_or_text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_min_valid_words() -> int:
    try:
        configured = int(state.config.get("content_min_valid_words", 1401))
    except Exception:
        configured = 1401
    return max(1, configured)


def _get_content_auto_retry_attempts() -> int:
    try:
        configured = int(state.config.get("content_auto_rerender_retries", 2))
    except Exception:
        configured = 2
    return max(0, configured)


def _count_words(content: Optional[str]) -> int:
    if not content:
        return 0
    return len(_gemini_response_text(content).split())


def _find_content_row_by_post_index(post_index: int) -> Optional[int]:
    for idx, item in enumerate(state.content_list):
        if int(item.get("post_index", -1)) == post_index:
            return idx
    return None


def _upsert_content_row(
    post_index: int,
    topic: dict,
    content: str,
    status: str = "success",
    error_reason: str = "",
    attempts: int = 1,
) -> int:
    cleaned_content = clean_gemini_content(content or "")
    word_count = _count_words(cleaned_content)
    row = {
        "post_index": post_index,
        "title": topic.get("title", ""),
        "keyword": topic.get("keyword", ""),
        "content": cleaned_content,
        "word_count": word_count,
        "status": status,
        "error_reason": error_reason,
        "attempts": attempts,
    }
    row_index = _find_content_row_by_post_index(post_index)
    if row_index is None:
        state.content_list.append(row)
        state.content_list.sort(key=lambda x: int(x.get("post_index", 10**9)))
        row_index = _find_content_row_by_post_index(post_index)
        if row_index is None:
            row_index = len(state.content_list) - 1
    else:
        state.content_list[row_index] = row

    state.current_content = cleaned_content
    return row_index


def _queue_content_rerender(post_index: int) -> bool:
    for item in state.retry_queue:
        if item.get("action") == "rerender_content" and int(item.get("post_index", -1)) == post_index:
            return False
    state.retry_queue.append({"action": "rerender_content", "post_index": post_index})
    return True


def _generate_content_by_provider(provider: str, topic: dict, page=None) -> Optional[str]:
    if provider == "gemini_web":
        return generate_content_gemini_web(page, topic["title"], topic["keyword"])
    if provider == "chatgpt_web":
        return generate_content_chatgpt_web(page, topic["title"], topic["keyword"])
    return generate_content(topic["title"], topic["keyword"])


def _validate_generated_content(content: Optional[str]) -> tuple:
    if not content:
        return False, "", 0, "Không thể tạo nội dung (rỗng)"

    cleaned_content = clean_gemini_content(content)
    words = _count_words(cleaned_content)
    min_valid_words = _get_min_valid_words()
    if words < min_valid_words:
        return False, cleaned_content, words, f"chỉ có {words}/{min_valid_words} từ"
    return True, cleaned_content, words, ""


def _generate_content_with_min_word_retries(
    provider: str,
    topic: dict,
    post_index: int,
    page=None,
    source: str = "initial",
) -> Optional[str]:
    auto_retries = _get_content_auto_retry_attempts()
    total_attempts = 1 + auto_retries
    title = topic.get("title", "")
    last_cleaned = ""
    last_reason = "Không thể tạo nội dung (rỗng)"

    for attempt in range(1, total_attempts + 1):
        if attempt == 1:
            add_log(f"[CONTENT][POST:{post_index + 1}] Bắt đầu tạo nội dung: {title}", "info")
        else:
            add_log(
                f"[CONTENT][POST:{post_index + 1}] Tạo lại nội dung thiếu: {title} "
                f"(lần {attempt}/{total_attempts})",
                "warning",
            )

        if state.is_paused and not wait_if_paused():
            return None
        if not state.is_running:
            return None

        content = _generate_content_by_provider(provider, topic, page=page)
        is_valid, cleaned_content, _, reason = _validate_generated_content(content)

        if is_valid:
            _upsert_content_row(
                post_index,
                topic,
                cleaned_content,
                status="success",
                error_reason="",
                attempts=attempt,
            )
            if attempt > 1:
                add_log(
                    f"Đã tạo lại thành công cho tiêu đề: {title} (sau {attempt} lần)",
                    "success",
                )
            return cleaned_content

        last_cleaned = cleaned_content or ""
        last_reason = reason
        add_log(
            f"Nội dung cho '{title}' không hợp lệ ({reason}) "
            f"[{attempt}/{total_attempts}]",
            "error",
        )

    _upsert_content_row(
        post_index,
        topic,
        last_cleaned,
        status="failed",
        error_reason=last_reason,
        attempts=total_attempts,
    )
    add_log(
        f"Không thể tạo lại nội dung cho tiêu đề: {title} "
        f"(đã thử {total_attempts} lần)",
        "error",
    )
    return None


def _process_content_retry_queue(provider: str, total_topics: int, page=None):
    if not state.retry_queue:
        return
    if state.current_phase not in ("generating_content", "retry_content_queue"):
        return

    state.current_phase = "retry_content_queue"
    while state.retry_queue and state.is_running:
        item = state.retry_queue.pop(0)
        if item.get("action") != "rerender_content":
            continue

        post_index = int(item.get("post_index", -1))
        if post_index < 0 or post_index >= len(state.topics):
            add_log("Yêu cầu rend lại không hợp lệ (index ngoài phạm vi)", "warning")
            continue

        topic = state.topics[post_index]
        add_log(
            f"[RETRY][CONTENT][POST:{post_index + 1}] Bắt đầu xử lý lại theo hàng chờ: {topic['title']}",
            "warning",
        )
        state.current_task = f"Re-render content {post_index + 1}/{total_topics}..."

        if not wait_if_paused():
            add_log("Stopped while paused", "warning")
            return

        validated = _generate_content_with_min_word_retries(
            provider,
            topic,
            post_index,
            page=page,
            source="queue",
        )
        if post_index < len(state.generated_contents):
            state.generated_contents[post_index] = validated

    state.current_phase = "generating_content"


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
    if not md:
        return ""

    # Inline transforms (chỉ áp dụng lên text đã extract, không lên HTML pass-through).
    def _inline(s: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)

    # Dòng đã là HTML block-level → giữ nguyên (idempotency).
    html_block_re = re.compile(
        r"^\s*</?(?:h[1-6]|p|ul|ol|li|div|section|article|header|footer|"
        r"blockquote|pre|table|thead|tbody|tr|td|th|figure|figcaption)\b",
        re.IGNORECASE,
    )

    lines = md.splitlines()
    out: list = []
    paragraph_buf: list = []

    def flush_paragraph():
        if paragraph_buf:
            joined = " ".join(s.strip() for s in paragraph_buf if s.strip())
            if joined:
                out.append(f"<p>{_inline(joined)}</p>")
            paragraph_buf.clear()

    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        # Dòng trống → kết thúc paragraph hiện tại.
        if not stripped:
            flush_paragraph()
            i += 1
            continue

        # Heading ### (kiểm tra trước ## để '###' không khớp '## ').
        if stripped.startswith("### "):
            flush_paragraph()
            out.append(f"<h3>{_inline(stripped[4:].strip())}</h3>")
            i += 1
            continue

        # Heading ##
        if stripped.startswith("## "):
            flush_paragraph()
            out.append(f"<h2>{_inline(stripped[3:].strip())}</h2>")
            i += 1
            continue

        # List: gom các dòng '- X' liên tiếp thành 1 <ul>.
        if stripped.startswith("- "):
            flush_paragraph()
            items: list = []
            while i < n and lines[i].strip().startswith("- "):
                item_text = lines[i].strip()[2:].strip()
                items.append(f"<li>{_inline(item_text)}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # Đã là HTML block → pass through để idempotent.
        if html_block_re.match(stripped):
            flush_paragraph()
            out.append(raw)
            i += 1
            continue

        # Mặc định: text thường → tích vào paragraph buffer.
        paragraph_buf.append(stripped)
        i += 1

    flush_paragraph()
    return "\n".join(out)


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


def generate_content(title: str, keyword: str, page=None) -> Optional[str]:
    provider = state.config.get("ai_provider", "ollama")
    
    if provider == "ollama":
        # Check if Ollama is running
        if not check_ollama():
            add_log("Ollama is not running! Please start Ollama first.", "error")
            add_log("Run: ollama serve", "info")
            return None
        return generate_content_ollama(title, keyword)
    elif provider == "gemini_web":
        if page is None:
            add_log("Gemini Web requires browser page", "error")
            return None
        return generate_content_gemini_web(page, title, keyword)
    elif provider == "chatgpt_web":
        if page is None:
            add_log("ChatGPT Web requires browser page", "error")
            return None
        return generate_content_chatgpt_web(page, title, keyword)
    else:
        return generate_content_gemini(title, keyword)


def _click_first_visible(page, selectors, timeout: int = 1500, require_enabled: bool = False) -> bool:
    """Click selector đầu tiên đang visible. Trả về True nếu click thành công."""
    for sel in selectors:
        try:
            el = page.locator(sel).last
            if el.is_visible(timeout=timeout):
                if require_enabled and not el.is_enabled():
                    continue
                el.click()
                return True
        except Exception:
            continue
    return False


def _click_visible_by_text(page, labels) -> bool:
    """Best-effort click phần tử visible có text chứa một trong các label."""
    try:
        return bool(page.evaluate(
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
            labels,
        ))
    except Exception:
        return False


def _delete_current_gemini_session(page) -> bool:
    """Xóa session Gemini hiện tại (best-effort)."""
    try:
        current_url = page.url or ""
        if not re.search(r"gemini\.google\.com/(?:app|gem)/[^/?#]+", current_url):
            add_log("Gemini: không thấy session cụ thể để xóa (bỏ qua)", "info")
            return False

        add_log("Gemini: đang xóa session chat vừa dùng...", "info")
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

        opened_menu = _click_first_visible(page, menu_selectors, timeout=1500)
        if not opened_menu:
            try:
                page.mouse.move(190, 210)
                time.sleep(0.4)
            except Exception:
                pass
            opened_menu = _click_first_visible(page, menu_selectors, timeout=1200)

        if not opened_menu:
            add_log("Gemini: không mở được menu session để xóa", "warning")
            return False

        time.sleep(0.5)
        deleted = _click_first_visible(page, delete_selectors, timeout=1200)
        if not deleted:
            deleted = _click_visible_by_text(page, ["delete", "xóa", "xoá", "remove"])
        if not deleted:
            add_log("Gemini: không tìm thấy nút Delete/Xóa", "warning")
            return False

        time.sleep(0.6)
        _click_first_visible(page, confirm_selectors, timeout=1000, require_enabled=True)
        _click_visible_by_text(page, ["delete", "xóa", "xoá", "confirm", "xác nhận"])

        for _ in range(8):
            time.sleep(0.4)
            try:
                if page.url != old_url:
                    add_log("Gemini: đã xóa session chat", "success")
                    return True
            except Exception:
                break

        add_log("Gemini: đã gửi lệnh xóa session (không xác minh được URL)", "info")
        return True
    except Exception as e:
        add_log(f"Gemini: lỗi khi xóa session chat: {e}", "warning")
        return False


def _delete_current_chatgpt_session(page) -> bool:
    """Xóa session ChatGPT hiện tại (best-effort)."""
    try:
        current_url = page.url or ""
        if not re.search(r"chatgpt\.com/c/[^/?#]+", current_url):
            add_log("ChatGPT: không thấy session /c/<id> để xóa (bỏ qua)", "info")
            return False

        add_log("ChatGPT: đang xóa session chat vừa dùng...", "info")
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

        opened_menu = _click_first_visible(page, menu_selectors, timeout=1500)
        if not opened_menu:
            add_log("ChatGPT: không mở được menu session để xóa", "warning")
            return False

        time.sleep(0.5)
        deleted = _click_first_visible(page, delete_selectors, timeout=1200)
        if not deleted:
            deleted = _click_visible_by_text(page, ["delete chat", "delete", "xóa", "xoá"])
        if not deleted:
            add_log("ChatGPT: không tìm thấy nút Delete/Xóa", "warning")
            return False

        time.sleep(0.6)
        _click_first_visible(page, confirm_selectors, timeout=1000, require_enabled=True)
        _click_visible_by_text(page, ["delete chat", "delete", "confirm", "xóa", "xác nhận"])

        for _ in range(8):
            time.sleep(0.4)
            try:
                if page.url != old_url:
                    add_log("ChatGPT: đã xóa session chat", "success")
                    return True
            except Exception:
                break

        add_log("ChatGPT: đã gửi lệnh xóa session (không xác minh được URL)", "info")
        return True
    except Exception as e:
        add_log(f"ChatGPT: lỗi khi xóa session chat: {e}", "warning")
        return False


def cleanup_provider_chat_session(page, provider: str) -> bool:
    """Xóa session chat hiện tại của provider sau khi render xong nội dung."""
    if provider == "gemini_web":
        return _delete_current_gemini_session(page)
    if provider == "chatgpt_web":
        return _delete_current_chatgpt_session(page)
    return False

# WORDPRESS AUTOMATION
 
def wait_for_network_idle(page: Page, timeout: int = 10000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except:
        pass

def _join_url(base: str, path: str) -> str:
    """Nối base URL và path, xử lý trailing slash dư."""
    return base.rstrip("/") + "/" + path.lstrip("/")


def _sync_config_domain_from_url(current_url: str) -> None:
    """
    Sau khi login, server WordPress có thể redirect từ www → non-www
    (hoặc ngược lại). Cập nhật wp_admin_url / wp_login_url trong state.config
    (chỉ trong bộ nhớ) để các navigate sau dùng đúng domain có cookie.
    """
    try:
        from urllib.parse import urlparse
        parsed = urlparse(current_url)
        if not parsed.scheme or not parsed.netloc:
            return
        real_origin = f"{parsed.scheme}://{parsed.netloc}"

        for key in ("wp_admin_url", "wp_login_url"):
            old = state.config.get(key, "")
            if not old:
                continue
            old_parsed = urlparse(old)
            if not old_parsed.netloc:
                continue
            if old_parsed.netloc != parsed.netloc:
                # Giữ nguyên path, chỉ đổi scheme+host
                new_url = real_origin + old_parsed.path
                state.config[key] = new_url
                add_log(
                    f"Cập nhật {key}: {old_parsed.netloc} → {parsed.netloc}",
                    "info",
                )
    except Exception as e:
        add_log(f"Không sync được domain sau login: {e}", "warning")


def _safe_navigate(page: Page, url: str, timeout: int = 30000, max_retries: int = 3) -> bool:
    """
    Navigate đến URL với khả năng xử lý:
    - Dialog "Bạn có chắc muốn rời trang" (beforeunload của trang cũ như Gemini)
    - ERR_ABORTED do navigation trước chưa xong
    - Retry với nhiều chiến thuật wait_until khác nhau

    Returns True nếu điều hướng thành công, False nếu đã hết retry.
    """
    # Auto-accept bất kỳ dialog nào xuất hiện (confirm/alert/prompt/beforeunload)
    # Handler này sẽ tự gỡ sau khi navigate xong.
    def _auto_dismiss(dialog):
        try:
            dialog.accept()
        except Exception:
            try:
                dialog.dismiss()
            except Exception:
                pass

    page.on("dialog", _auto_dismiss)

    # Các chiến thuật wait_until theo thứ tự — nếu 1 cái fail thì thử cái tiếp
    strategies = ["domcontentloaded", "load", "commit"]

    last_err: Optional[Exception] = None
    try:
        for attempt in range(1, max_retries + 1):
            wait_until = strategies[min(attempt - 1, len(strategies) - 1)]
            try:
                # Trước khi goto, cố gắng "hạ cánh" trang cũ xuống about:blank
                # để cắt hoàn toàn beforeunload và XHR còn dở của trang trước.
                if attempt > 1:
                    try:
                        page.goto("about:blank", wait_until="load", timeout=5000)
                        time.sleep(0.5)
                    except Exception:
                        pass

                add_log(
                    f"Điều hướng tới {url} (lần {attempt}/{max_retries}, wait_until={wait_until})...",
                    "info",
                )
                page.goto(url, wait_until=wait_until, timeout=timeout)
                time.sleep(0.8)
                return True

            except Exception as e:
                last_err = e
                msg = str(e)
                if "ERR_ABORTED" in msg or "TimeoutError" in type(e).__name__:
                    add_log(
                        f"Navigate bị abort/timeout ({attempt}/{max_retries}): {msg[:120]}",
                        "warning",
                    )
                    time.sleep(2)
                    continue
                # Lỗi khác — không retry vô nghĩa
                add_log(f"Lỗi navigate: {msg[:180]}", "error")
                return False

        # Fallback cuối: nạp URL qua window.location (tránh beforeunload của trang cũ)
        try:
            add_log("Thử fallback: set window.location qua JS...", "info")
            page.evaluate(f"() => {{ window.location.replace({url!r}); }}")
            try:
                page.wait_for_load_state("domcontentloaded", timeout=timeout)
            except Exception:
                pass
            time.sleep(1.5)
            if url.split("://", 1)[-1].split("/", 1)[0] in (page.url or ""):
                add_log("Fallback thành công!", "info")
                return True
        except Exception as e:
            add_log(f"Fallback cũng thất bại: {e}", "warning")

        add_log(
            f"Không thể điều hướng tới {url} sau {max_retries} lần thử",
            "error",
        )
        return False

    finally:
        try:
            page.remove_listener("dialog", _auto_dismiss)
        except Exception:
            pass


def login_to_wordpress(page: Page) -> bool:
    try:
        add_log("Logging into WordPress...", "info")
        
        login_url = state.config.get("wp_login_url", "")
        username = state.config.get("wp_username", "")
        password = state.config.get("wp_password", "")
        
        add_log(f"Login URL: {login_url}", "info")
        add_log(f"Username: {username}", "info")
        
        if not login_url or not username or not password:
            add_log("Missing login credentials!", "error")
            return False

        # Navigate to login page — với retry & dialog handling để chống
        # ERR_ABORTED khi chuyển từ gemini.google.com sang WordPress
        if not _safe_navigate(page, login_url, timeout=30000, max_retries=3):
            return False
        time.sleep(1)
        
        current_url = page.url
        add_log(f"Current URL: {current_url}", "info")
        
        # Check if already logged in
        if "wp-admin" in current_url and "wp-login" not in current_url:
            add_log("Already logged in!", "success")
            return True
        
        # Wait for login form - try multiple selectors
        login_form_found = False
        form_selectors = ["#user_login", "#loginform", "input[name='log']", "#username"]
        
        for selector in form_selectors:
            try:
                if page.locator(selector).first.is_visible(timeout=3000):
                    login_form_found = True
                    add_log(f"Tìm thấy form đăng nhập: {selector}", "info")
                    break
            except:
                continue
        
        if not login_form_found:
            add_log("Could not find login form!", "error")
            page.screenshot(path="/tmp/wp_login_error.png")
            add_log("Screenshot saved to /tmp/wp_login_error.png", "info")
            return False
        
        # Fill login form - try different selectors
        username_selectors = ["#user_login", "input[name='log']", "#username"]
        password_selectors = ["#user_pass", "input[name='pwd']", "#password"]
        
        # Fill username
        for selector in username_selectors:
            try:
                input_field = page.locator(selector).first
                if input_field.is_visible(timeout=2000):
                    input_field.click()
                    input_field.fill("")
                    input_field.fill(username)
                    add_log(f"Filled username in {selector}", "info")
                    break
            except:
                continue
        
        time.sleep(0.3)
        
        # Fill password
        for selector in password_selectors:
            try:
                input_field = page.locator(selector).first
                if input_field.is_visible(timeout=2000):
                    input_field.click()
                    input_field.fill("")
                    input_field.fill(password)
                    add_log(f"Filled password in {selector}", "info")
                    break
            except:
                continue
        
        time.sleep(0.3)
        
        # Click submit button
        submit_selectors = ["#wp-submit", "input[type='submit']", "button[type='submit']", ".login-submit button"]
        
        for selector in submit_selectors:
            try:
                submit_btn = page.locator(selector).first
                if submit_btn.is_visible(timeout=2000):
                    submit_btn.click()
                    add_log(f"Clicked submit: {selector}", "info")
                    break
            except:
                continue
        
        # Wait for navigation
        add_log("Đang chờ đăng nhập...", "info")
        time.sleep(2)
        
        # Try waiting for wp-admin URL
        try:
            page.wait_for_url("**/wp-admin/**", timeout=10000)
        except:
            time.sleep(1)
        
        # Check if login was successful
        current_url = page.url
        add_log(f"After login URL: {current_url}", "info")
        
        # Success indicators
        if "wp-admin" in current_url and "wp-login" not in current_url:
            add_log("Successfully logged into WordPress!", "success")
            _sync_config_domain_from_url(current_url)
            wait_for_network_idle(page)
            return True
        
        # Check for error message on login page
        error_selectors = ["#login_error", ".login-error", ".message.error"]
        for selector in error_selectors:
            try:
                error_msg = page.locator(selector).first
                if error_msg.is_visible(timeout=1000):
                    error_text = error_msg.inner_text()
                    add_log(f"Login error: {error_text[:100]}", "error")
                    return False
            except:
                continue
        
        # If we're still on login page
        if "wp-login" in current_url or "login" in current_url.lower():
            add_log("Login failed: Still on login page", "error")
            page.screenshot(path="/tmp/wp_login_failed.png")
            add_log("Screenshot saved to /tmp/wp_login_failed.png", "info")
            return False
        
        # Assume success if no errors detected
        add_log("Login appears successful", "success")
        return True
        
    except Exception as e:
        add_log(f"Login failed: {e}", "error")
        try:
            page.screenshot(path="/tmp/wp_login_exception.png")
        except:
            pass
        return False

def navigate_to_new_post(page: Page) -> bool:
    try:
        target_url = _join_url(state.config['wp_admin_url'], 'post-new.php')
        if not _safe_navigate(page, target_url, timeout=30000, max_retries=3):
            return False
        wait_for_network_idle(page, timeout=15000)
        time.sleep(2)
        
        # Wait for Classic Editor to load - check for title field
        try:
            page.wait_for_selector("#title, input[name='post_title']", timeout=10000)
            add_log("Classic Editor loaded", "info")
        except:
            add_log("Editor may not have loaded properly", "warning")
        
        # Dismiss any notices
        try:
            dismiss_btns = page.locator(".notice-dismiss, .wp-core-ui .notice-dismiss").all()
            for btn in dismiss_btns:
                if btn.is_visible():
                    btn.click()
                    time.sleep(0.2)
        except:
            pass
        
        add_log("Navigated to new post editor", "info")
        return True
        
    except Exception as e:
        add_log(f"Failed to navigate to new post: {e}", "error")
        return False

def set_post_title(page: Page, title: str) -> bool:
    try:
        # Classic Editor title field - ID is always "title"
        title_input = page.locator("#title")
        
        if title_input.is_visible(timeout=5000):
            title_input.click()
            title_input.fill("")  # Clear first
            title_input.fill(title)
            add_log(f"Set title: {title[:50]}...", "info")
            return True
        else:
            add_log("Title field not visible", "error")
            return False
            
    except Exception as e:
        add_log(f"Failed to set title: {e}", "error")
        return False

def set_post_content(page: Page, content: str) -> bool:
    """Đẩy HTML content vào WordPress Classic Editor.

    Root cause của bug "bài save rỗng": Classic Editor khi submit form luôn gọi
    ``tinymce.triggerSave()`` để đồng bộ iframe → textarea trước khi POST. Nếu
    TinyMCE iframe đang trống (vì mới fill textarea xong, chưa switch Visual,
    hoặc switch Visual mà ``wpautop`` parse fail trên HTML "biên"), thì
    ``triggerSave`` ghi rỗng đè textarea → DB lưu content rỗng.

    Fix: ưu tiên set content thẳng vào TinyMCE qua API
    (``tinymce.get('content').setContent(html)`` + ``.save()``). Thao tác này
    bypass wpautop, đồng thời ``save()`` đẩy HTML xuống textarea ngay → cả
    Text lẫn Visual mode đều có content đúng. Nếu TinyMCE chưa init kịp, fall
    back về textarea + sync ngược lên iframe để đảm bảo bất biến: cả textarea
    và iframe phải có cùng nội dung trước khi publish.
    """
    try:
        add_log("Đang thêm nội dung...", "info")
        time.sleep(0.5)

        content_added = False

        # Method 1 (primary): TinyMCE API → setContent + save (sync vào textarea)
        try:
            # Đợi TinyMCE init xong (best-effort, ~5s). Nếu trang chưa load
            # editor thì wait_for_function sẽ raise → bắt và fallback Method 2.
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
                        ed.save();  // ghi xuống <textarea#content>
                        const ta = document.getElementById('content');
                        if (ta) {
                            // Belt-and-suspenders: đảm bảo textarea có nguyên
                            // bản HTML (ed.save() đôi khi chạy serializer).
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
                add_log("Content set via TinyMCE API", "success")
        except Exception as e:
            add_log(f"TinyMCE API method skipped: {e}", "warning")

        # Method 2 (fallback): switch Text mode → fill textarea → push lên TinyMCE
        if not content_added:
            try:
                text_tab = page.locator("#content-html").first
                if text_tab.is_visible(timeout=3000):
                    text_tab.click()
                    time.sleep(0.5)
                    add_log("Đã chuyển sang chế độ Text/HTML", "info")

                content_textarea = page.locator("#content").first
                if content_textarea.is_visible(timeout=3000):
                    content_textarea.click()
                    content_textarea.fill("")
                    content_textarea.fill(content)

                    # Quan trọng: push content lên TinyMCE iframe để
                    # triggerSave() lúc publish không ghi rỗng đè textarea.
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
                    add_log("Content set via textarea + TinyMCE sync", "success")
            except Exception as e:
                add_log(f"Textarea method failed: {e}", "warning")

        # Method 3 (last resort): pure JS injection cho cả textarea và TinyMCE
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
                    add_log("Content set via JavaScript injection", "success")
            except Exception as e:
                add_log(f"JavaScript method failed: {e}", "warning")

        if content_added:
            return True
        else:
            add_log("Failed to add content - all methods failed", "error")
            return False

    except Exception as e:
        add_log(f"Failed to set content: {e}", "error")
        return False

def set_rank_math_keyword(page: Page, keyword: str) -> bool:
    try:
        add_log(f"Setting Rank Math keyword: {keyword}", "info")
        
        # Scroll down to Rank Math section
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(1)
        
        # Look for Rank Math focus keyword input
        keyword_selectors = [
            "input[placeholder*='Rank Math']",
            "input.rank-math-focus-keyword",
            "#rank-math-focus-keyword",
            "input[name*='rank_math'][name*='keyword']",
            ".rank-math-focus-keyword input",
            "input[placeholder*='khóa chính']",
            "input[placeholder*='focus keyword']"
        ]
        
        keyword_input = None
        for selector in keyword_selectors:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1000):
                    keyword_input = el
                    break
            except:
                continue
        
        if keyword_input:
            keyword_input.click()
            keyword_input.fill("")
            keyword_input.fill(keyword)
            # Press Enter to add the keyword
            keyword_input.press("Enter")
            time.sleep(0.5)
            add_log(f"Rank Math keyword set: {keyword}", "success")
            return True
        else:
            # Try JavaScript method
            try:
                page.evaluate("""
                    (keyword) => {
                        var inputs = document.querySelectorAll('input[placeholder*="Rank Math"], input.rank-math-focus-keyword');
                        if (inputs.length > 0) {
                            inputs[0].value = keyword;
                            inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
                            return true;
                        }
                        return false;
                    }
                """, keyword)
                add_log(f"Rank Math keyword set via JS: {keyword}", "success")
                return True
            except:
                add_log("Rank Math keyword field not found", "warning")
                return False
        
    except Exception as e:
        add_log(f"Error setting Rank Math keyword: {e}", "warning")
        return False

# ===== Image Insertion Reliability Constants (bugfix: image-insertion-reliability-fix) =====
MAX_RETRY_ROUNDS = 2           # Phase 2 outer retry rounds
MAX_SLOT_RETRIES = 2           # Per-slot internal retries for flaky sub-steps
MEDIA_LIB_POLL_TIMEOUT = 15000  # ms total polling visible attachments
MEDIA_LIB_POLL_INTERVAL = 500  # ms per check
MEDIA_MODAL_TIMEOUT = 5000     # ms (giữ nguyên giá trị cũ)
ADD_MEDIA_BTN_TIMEOUT = 3000   # ms (tăng nhẹ từ 2000ms cũ)
MEDIA_CLICK_TIMEOUT = 1500     # ms; tránh Playwright chờ 30-60s với element ẩn
INSERT_VERIFY_TIMEOUT = 5000   # ms; WordPress đôi khi chèn ảnh hơi trễ
INSERT_VERIFY_INTERVAL = 250   # ms
INLINE_IMAGE_RANDOM_POOL_SIZE = 50
INLINE_IMAGE_HEADING_SELECTOR = "h2, h3"


def _count_imgs_in_iframe(page: Page) -> int:
    """Đếm số <img> hiện hữu trong TinyMCE iframe (#content_ifr).

    Dùng JS evaluate để tránh stale locator giữa các iteration —
    1 round-trip duy nhất, nhanh hơn locator.count().

    Returns 0 nếu iframe chưa sẵn sàng (best-effort, không raise).
    """
    try:
        return int(
            page.frame_locator("#content_ifr").locator("body").evaluate(
                "() => document.querySelectorAll('img').length"
            )
        )
    except Exception:
        return 0


def _get_h2_elements_in_iframe(page: Page) -> list:
    """Re-fetch heading elements an toàn từ TinyMCE iframe.

    Sleep 0.3s để DOM settle, tránh stale locator sau modal close.

    Returns: list of Playwright locators (có thể rỗng nếu iframe chưa sẵn sàng).
    """
    try:
        time.sleep(0.3)
        return page.frame_locator("#content_ifr").locator(INLINE_IMAGE_HEADING_SELECTOR).all()
    except Exception:
        return []


def _img_is_after_h2(page: Page, h2_index: int) -> bool:
    """Verify ảnh nằm dưới H2 thứ h2_index thông qua DOM sibling check.

    Duyệt tối đa 2 sibling kế tiếp của H2 (TinyMCE thường wrap <img> trong <p>),
    trả True nếu thấy <img> trực tiếp hoặc descendant trong sibling đó.

    Returns False nếu h2_index out of range hoặc lỗi evaluate.
    """
    try:
        return page.frame_locator("#content_ifr").locator("body").evaluate(
            """(_, idx) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const allHeadings = Array.from(document.querySelectorAll('h2, h3'));
                const contactIndex = allHeadings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                const h2s = contactIndex >= 0 ?
                    allHeadings.slice(0, contactIndex) : allHeadings;
                if (idx >= h2s.length) return false;
                const h2 = h2s[idx];
                let cur = h2.nextElementSibling;
                for (let i = 0; i < 2 && cur; i++) {
                    if (cur.tagName === 'IMG') return true;
                    if (cur.querySelector && cur.querySelector('img')) return true;
                    cur = cur.nextElementSibling;
                }
                return false;
            }""",
            h2_index,
        )
    except Exception:
        return False


def _get_heading_count_in_iframe(page: Page) -> int:
    try:
        return int(
            page.frame_locator("#content_ifr").locator("body").evaluate(
                """() => {
                    const headings = Array.from(document.querySelectorAll('h2, h3'));
                    const contactIndex = headings.findIndex((heading) =>
                        /th[oô]ng tin li[eê]n h[eệ]|thong tin lien he/i.test(
                            (heading.textContent || '').trim()
                        )
                    );
                    return contactIndex >= 0 ? contactIndex : headings.length;
                }"""
            )
        )
    except Exception:
        return 0


def _get_contact_heading_index(page: Page) -> Optional[int]:
    try:
        index = page.frame_locator("#content_ifr").locator("body").evaluate(
            """() => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const headings = Array.from(document.querySelectorAll('h2, h3'));
                const idx = headings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                return idx >= 0 ? idx : null;
            }"""
        )
        return int(index) if index is not None else None
    except Exception:
        return None


def _get_safe_heading_count_for_images(page: Page) -> int:
    return _get_heading_count_in_iframe(page)


def _pick_evenly_spaced_indices(total: int, slots: int) -> list:
    if total <= 0 or slots <= 0:
        return []
    if total <= slots:
        return list(range(total))
    if slots == 1:
        return [total // 2]

    picked = []
    used = set()
    for pos in range(slots):
        raw = int((pos * (total - 1) / (slots - 1)) + 0.5)
        candidates = [raw]
        for offset in range(1, total):
            candidates.append(raw - offset)
            candidates.append(raw + offset)
        for candidate in candidates:
            if 0 <= candidate < total and candidate not in used:
                picked.append(candidate)
                used.add(candidate)
                break
    return sorted(picked)


def _select_even_candidates(indices: list, limit: int) -> list:
    ordered = sorted(set(indices))
    if limit <= 0 or not ordered:
        return []
    if len(ordered) <= limit:
        return ordered
    return [ordered[idx] for idx in _pick_evenly_spaced_indices(len(ordered), limit)]


def _format_heading_targets(indices: list) -> str:
    if not indices:
        return "none"
    return ", ".join(f"#{idx + 1}" for idx in indices)


def _switch_to_visual_mode(page: Page) -> None:
    """Click `#content-tmce` để chuyển TinyMCE sang Visual mode.

    Best-effort: nếu tab không visible hoặc click fail thì chỉ log warning,
    không raise. Behavior giữ nguyên từ logic gốc trong insert_images_after_h2
    để đảm bảo preservation (Clause 3.4).
    """
    try:
        visual_tab = page.locator("#content-tmce").first
        if visual_tab.is_visible(timeout=2000):
            visual_tab.click()
            time.sleep(1)
            add_log("Switched to Visual mode", "info")
    except Exception as e:
        add_log(f"Could not switch to Visual mode: {e}", "warning")


def _click_first_selector_resilient(
    page: Page,
    selectors: list,
    label: str,
    timeout_ms: int = MEDIA_CLICK_TIMEOUT,
) -> bool:
    """Click nhanh bằng locator, rồi fallback JS để tránh kẹt vì viewport/overlay."""
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
                add_log(f"Clicked {label}", "info")
                return True
            except Exception:
                try:
                    target.click(force=True, timeout=timeout_ms)
                    add_log(f"Force-clicked {label}", "info")
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
            selectors,
        )
        if clicked_selector:
            add_log(f"JS-clicked {label}", "info")
            return True
    except Exception:
        pass

    return False


def _select_visible_media_attachment(page: Page, label: str) -> bool:
    """Select ảnh từ pool Media Library rộng hơn và tránh trùng trong phiên chạy."""
    try:
        if not hasattr(state, "used_inline_images"):
            state.used_inline_images = set()

        result = page.evaluate(
            """async ({ usedIds, poolSize }) => {
                const used = new Set((usedIds || []).map(String));
                const pickIndex = (max) => {
                    if (max <= 1) return 0;
                    if (window.crypto && crypto.getRandomValues) {
                        const bytes = new Uint32Array(1);
                        crypto.getRandomValues(bytes);
                        return bytes[0] % max;
                    }
                    return Math.floor(Math.random() * max);
                };
                const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 1 &&
                        rect.height > 1 &&
                        rect.bottom > 0 &&
                        rect.right > 0 &&
                        rect.top < window.innerHeight &&
                        rect.left < window.innerWidth &&
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        style.opacity !== '0';
                };
                const normalizeMedia = (data, modelIndex, model) => {
                    if (!data) return null;
                    if (data.type && data.type !== 'image') return null;
                    const sizes = data.sizes || {};
                    const preferred = sizes.large || sizes.medium_large ||
                        sizes.medium || sizes.full || null;
                    const url = (preferred && preferred.url) || data.url || '';
                    if (!url) return null;
                    const id = String(data.id || data.ID || url);
                    return {
                        id,
                        url,
                        alt: data.alt || '',
                        title: data.title || data.filename || '',
                        modelIndex,
                        model
                    };
                };
                const rememberAndSelect = (entry, entries, source, reused) => {
                    if (!entry) return null;
                    try {
                        const frame = window.wp && wp.media && wp.media.frame;
                        const frameState = frame && frame.state && frame.state();
                        const selection = frameState && frameState.get &&
                            frameState.get('selection');
                        if (selection && entry.model) {
                            selection.reset([entry.model]);
                        }
                    } catch (e) {}

                    try {
                        const el = Array.from(document.querySelectorAll('.attachment'))
                            .find((node) => String(node.getAttribute('data-id') || node.dataset.id || '') === entry.id);
                        if (el) {
                            try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
                            el.click();
                        }
                    } catch (e) {}

                    const selected = {
                        id: entry.id,
                        url: entry.url,
                        alt: entry.alt,
                        title: entry.title,
                        index: entry.modelIndex,
                        pool: entries.length,
                        source,
                        reused
                    };
                    window.__autoPosterSelectedImage = selected;
                    return { ok: true, selected };
                };

                try {
                    const frame = window.wp && wp.media && wp.media.frame;
                    const frameState = frame && frame.state && frame.state();
                    const library = frameState && frameState.get &&
                        frameState.get('library');
                    if (library && Array.isArray(library.models)) {
                        const deadline = Date.now() + 12000;
                        let stagnant = 0;
                        while (library.models.length < poolSize && Date.now() < deadline) {
                            let canLoadMore = true;
                            try {
                                if (typeof library.hasMore === 'function') {
                                    canLoadMore = !!library.hasMore();
                                }
                            } catch (e) {}
                            if (!canLoadMore || typeof library.more !== 'function') break;

                            const before = library.models.length;
                            try {
                                const req = library.more();
                                await new Promise((resolve) => {
                                    if (req && typeof req.always === 'function') {
                                        req.always(resolve);
                                    } else if (req && typeof req.then === 'function') {
                                        req.then(resolve, resolve);
                                    } else {
                                        setTimeout(resolve, 700);
                                    }
                                });
                            } catch (e) {
                                await sleep(700);
                            }

                            if (library.models.length <= before) {
                                stagnant += 1;
                                const scroller = document.querySelector(
                                    '.attachments-browser .attachments, ' +
                                    '.media-frame-content, .media-modal-content'
                                );
                                if (scroller) scroller.scrollTop = scroller.scrollHeight;
                                await sleep(500);
                                if (stagnant >= 2) break;
                            } else {
                                stagnant = 0;
                            }
                        }

                        const models = library.models.slice(0, Math.min(poolSize, library.models.length));
                        const entries = models
                            .map((model, index) => normalizeMedia(
                                model && model.toJSON && model.toJSON(),
                                index,
                                model
                            ))
                            .filter(Boolean);
                        if (entries.length) {
                            const unused = entries.filter((entry) =>
                                !used.has(entry.id) && !used.has(entry.url)
                            );
                            const pool = unused.length ? unused : entries;
                            const entry = pool[pickIndex(pool.length)];
                            return rememberAndSelect(
                                entry,
                                entries,
                                'wp.media',
                                unused.length === 0
                            );
                        }
                    }
                } catch (e) {}

                const all = Array.from(document.querySelectorAll(
                    '.media-modal .attachments .attachment, ' +
                    '.media-frame .attachments .attachment, ' +
                    '.attachments li.attachment, li.attachment'
                )).filter((el) => !el.classList.contains('uploading'));

                let visible = all.filter(isVisible);
                if (!visible.length) {
                    const scroller = document.querySelector(
                        '.attachments-browser .attachments, .media-frame-content, .media-modal-content'
                    );
                    if (scroller) scroller.scrollTop = 0;
                    visible = all.filter(isVisible);
                }
                if (!visible.length) {
                    return { ok: false, reason: 'no_visible_attachments', total: all.length };
                }

                const entries = visible
                    .slice(0, Math.min(visible.length, poolSize))
                    .map((el, index) => {
                        const id = String(el.getAttribute('data-id') || el.dataset.id || '');
                        const img = el.querySelector('img');
                        const url = img && (img.currentSrc || img.src || '');
                        if (!url && !id) return null;
                        return {
                            id: id || url,
                            url,
                            alt: img ? (img.alt || '') : '',
                            title: img ? (img.alt || '') : '',
                            modelIndex: index,
                            element: el
                        };
                    })
                    .filter(Boolean);
                if (!entries.length) {
                    return { ok: false, reason: 'no_usable_visible_attachments', total: all.length };
                }

                const unused = entries.filter((entry) =>
                    !used.has(entry.id) && !used.has(entry.url)
                );
                const pool = unused.length ? unused : entries;
                const localIndex = pickIndex(pool.length);
                const el = pool[localIndex];
                try { el.element.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
                el.element.click();
                window.__autoPosterSelectedImage = {
                    id: el.id,
                    url: el.url,
                    alt: el.alt,
                    title: el.title,
                    index: el.modelIndex,
                    pool: entries.length,
                    source: 'dom-visible',
                    reused: unused.length === 0
                };
                return { ok: true, selected: window.__autoPosterSelectedImage };
            }""",
            {
                "usedIds": list(state.used_inline_images),
                "poolSize": INLINE_IMAGE_RANDOM_POOL_SIZE,
            },
        )
        selected = result.get("selected") if result else None
        if result and result.get("ok") and selected:
            selected_key = str(selected.get("id") or selected.get("url") or "")
            if selected_key:
                state.used_inline_images.add(selected_key)
            add_log(
                f"Selected image {int(selected.get('index', 0)) + 1} "
                f"from {selected.get('pool', 0)} pool "
                f"({selected.get('source', 'media')}, "
                f"{'reused' if selected.get('reused') else 'unused'}) for {label}",
                "info",
            )
            time.sleep(0.8)
            return True

        reason = result.get("reason") if result else "no_result"
        total = result.get("total") if result else 0
        add_log(f"Select image fail for {label}: {reason} (total={total})", "warning")
        return False
    except Exception as e:
        add_log(f"Select image fail for {label}: {e}", "warning")
        return False


def _get_media_attachment_status(page: Page) -> dict:
    try:
        return page.evaluate(
            """() => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 1 &&
                        rect.height > 1 &&
                        rect.bottom > 0 &&
                        rect.right > 0 &&
                        rect.top < window.innerHeight &&
                        rect.left < window.innerWidth &&
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        style.opacity !== '0';
                };

                const all = Array.from(document.querySelectorAll(
                    '.media-modal .attachments .attachment, ' +
                    '.media-frame .attachments .attachment, ' +
                    '.attachments li.attachment, li.attachment'
                )).filter((el) => !el.classList.contains('uploading'));

                const visible = all.filter(isVisible);
                const loading = !!document.querySelector(
                    '.media-frame .spinner.is-active, ' +
                    '.media-modal .spinner.is-active, ' +
                    '.attachments-browser .spinner.is-active'
                );
                const noItems = !!document.querySelector(
                    '.media-frame .no-media, .media-modal .no-media, .attachments .no-media'
                );
                let libraryCount = 0;
                try {
                    const frame = window.wp && wp.media && wp.media.frame;
                    const frameState = frame && frame.state && frame.state();
                    const library = frameState && frameState.get &&
                        frameState.get('library');
                    libraryCount = library && Array.isArray(library.models) ?
                        library.models.length : 0;
                } catch (e) {}

                return {
                    total: all.length,
                    visible: visible.length,
                    libraryCount,
                    loading,
                    noItems
                };
            }"""
        ) or {"total": 0, "visible": 0, "libraryCount": 0, "loading": False, "noItems": False}
    except Exception:
        return {"total": 0, "visible": 0, "libraryCount": 0, "loading": False, "noItems": False}


def _get_selected_media_image(page: Page, fallback_alt: str) -> Optional[dict]:
    try:
        image = page.evaluate(
            """(fallbackAlt) => {
                const normalize = (data, id) => {
                    if (!data) return null;
                    const sizes = data.sizes || {};
                    const preferred = sizes.large || sizes.medium_large ||
                        sizes.medium || sizes.full || null;
                    const url = (preferred && preferred.url) || data.url || '';
                    if (!url) return null;
                    return {
                        id: id || data.id || '',
                        url,
                        alt: data.alt || fallbackAlt,
                        title: data.title || data.filename || fallbackAlt
                    };
                };

                if (window.__autoPosterSelectedImage &&
                    window.__autoPosterSelectedImage.url) {
                    return {
                        id: window.__autoPosterSelectedImage.id || '',
                        url: window.__autoPosterSelectedImage.url,
                        alt: window.__autoPosterSelectedImage.alt || fallbackAlt,
                        title: window.__autoPosterSelectedImage.title || fallbackAlt
                    };
                }

                try {
                    const frame = window.wp && wp.media && wp.media.frame;
                    const selection = frame && frame.state &&
                        frame.state().get('selection');
                    const model = selection && selection.first && selection.first();
                    const data = model && model.toJSON && model.toJSON();
                    const fromFrame = normalize(data, data && data.id);
                    if (fromFrame) return fromFrame;
                } catch (e) {}

                const selected = document.querySelector(
                    '.attachment.selected, .attachment[aria-checked="true"]'
                );
                const id = selected && (
                    selected.getAttribute('data-id') || selected.dataset.id
                );
                try {
                    if (id && window.wp && wp.media && wp.media.attachment) {
                        const data = wp.media.attachment(id).toJSON();
                        const fromAttachment = normalize(data, id);
                        if (fromAttachment) return fromAttachment;
                    }
                } catch (e) {}

                const detailImg = document.querySelector(
                    '.attachment-details .thumbnail img, ' +
                    '.attachment-info .thumbnail img, ' +
                    '.media-sidebar .thumbnail img, ' +
                    '.attachment.selected img'
                );
                const url = detailImg && (detailImg.currentSrc || detailImg.src);
                if (url) {
                    return {
                        id: id || '',
                        url,
                        alt: detailImg.alt || fallbackAlt,
                        title: detailImg.alt || fallbackAlt
                    };
                }

                return null;
            }""",
            fallback_alt,
        )
        if image and image.get("url"):
            return image
    except Exception as e:
        add_log(f"Could not read selected media image: {e}", "warning")
    return None


def _sync_editor_after_direct_insert(page: Page) -> None:
    try:
        page.evaluate(
            """() => {
                if (window.tinymce) {
                    const ed = tinymce.get('content');
                    if (ed) {
                        try { ed.nodeChanged(); } catch (e) {}
                        try { ed.save(); } catch (e) {}
                        try {
                            const ta = document.getElementById('content');
                            if (ta) ta.value = ed.getContent({ format: 'html' });
                        } catch (e) {}
                    }
                    try { tinymce.triggerSave(); } catch (e) {}
                }
                const ta = document.getElementById('content');
                if (ta) {
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                    ta.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }"""
        )
    except Exception:
        pass


def _insert_selected_image_after_h2_direct(
    page: Page,
    h2_index: int,
    image: dict,
    keyword: str,
) -> bool:
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body, args) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const allHeadings = Array.from(body.querySelectorAll('h2, h3'));
                const contactIndex = allHeadings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                const h2s = contactIndex >= 0 ?
                    allHeadings.slice(0, contactIndex) : allHeadings;
                if (args.h2Index >= h2s.length) {
                    return { ok: false, reason: 'h2_not_found', count: h2s.length };
                }
                const doc = body.ownerDocument;
                const wrapper = doc.createElement('p');
                const img = doc.createElement('img');
                img.src = args.url;
                img.alt = args.alt || args.keyword;
                img.title = args.title || args.keyword;
                img.loading = 'lazy';
                img.decoding = 'async';
                img.className = 'aligncenter size-full wp-image-auto-poster';
                wrapper.appendChild(img);
                h2s[args.h2Index].insertAdjacentElement('afterend', wrapper);
                return { ok: true, count: body.querySelectorAll('img').length };
            }""",
            {
                "h2Index": h2_index,
                "url": image.get("url", ""),
                "alt": image.get("alt") or keyword,
                "title": image.get("title") or keyword,
                "keyword": keyword,
            },
        )
        if result and result.get("ok"):
            _sync_editor_after_direct_insert(page)
            add_log(
                f"Inserted selected image directly under H2 #{h2_index + 1}",
                "success",
            )
            return True
        reason = result.get("reason") if result else "no_result"
        add_log(f"Direct insert under H2 #{h2_index + 1} failed: {reason}", "warning")
    except Exception as e:
        add_log(f"Direct insert under H2 #{h2_index + 1} failed: {e}", "warning")
    return False


def _insert_selected_image_after_paragraph_direct(
    page: Page,
    slot_hint: str,
    image: dict,
    keyword: str,
) -> bool:
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body, args) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const contactHeading = Array.from(body.querySelectorAll('h2, h3'))
                    .find((heading) =>
                        normalize(heading.textContent).includes('thong tin lien he')
                    );
                const isBeforeContact = (node) => {
                    if (!contactHeading) return true;
                    return !!(node.compareDocumentPosition(contactHeading) &
                        Node.DOCUMENT_POSITION_FOLLOWING);
                };
                const paragraphs = Array.from(body.querySelectorAll('p'))
                    .filter(isBeforeContact);
                if (!paragraphs.length) {
                    return { ok: false, reason: 'no_safe_paragraphs_before_contact' };
                }
                let target = paragraphs[0];
                if (args.slot === 'middle') {
                    target = paragraphs[Math.floor(paragraphs.length / 2)];
                } else if (args.slot === 'bottom') {
                    target = paragraphs[paragraphs.length - 1];
                }
                const doc = body.ownerDocument;
                const wrapper = doc.createElement('p');
                const img = doc.createElement('img');
                img.src = args.url;
                img.alt = args.alt || args.keyword;
                img.title = args.title || args.keyword;
                img.loading = 'lazy';
                img.decoding = 'async';
                img.className = 'aligncenter size-full wp-image-auto-poster';
                wrapper.appendChild(img);
                target.insertAdjacentElement('afterend', wrapper);
                return { ok: true, count: body.querySelectorAll('img').length };
            }""",
            {
                "slot": slot_hint,
                "url": image.get("url", ""),
                "alt": image.get("alt") or keyword,
                "title": image.get("title") or keyword,
                "keyword": keyword,
            },
        )
        if result and result.get("ok"):
            _sync_editor_after_direct_insert(page)
            add_log(
                f"Fallback ({slot_hint}): inserted selected image directly",
                "success",
            )
            return True
        reason = result.get("reason") if result else "no_result"
        add_log(f"Fallback ({slot_hint}) direct insert failed: {reason}", "warning")
    except Exception as e:
        add_log(f"Fallback ({slot_hint}) direct insert failed: {e}", "warning")
    return False


def _switch_to_media_library_tab(page: Page, label: str) -> None:
    tab_selectors = [
        ".media-menu-item:has-text('Thư viện Media')",
        ".media-menu-item:has-text('Thư viện')",
        ".media-menu-item:has-text('Media Library')",
        ".media-menu-item:has-text('Library')",
        ".media-menu-item:has-text('Chọn từ thư viện')",
        ".media-router a:has-text('Thư viện')",
        ".media-router a:has-text('Media Library')",
    ]
    if _click_first_selector_resilient(
        page,
        tab_selectors,
        f"Media Library tab for {label}",
        timeout_ms=1000,
    ):
        time.sleep(0.5)


def _wait_for_visible_media_attachments(
    page: Page,
    label: str,
    timeout_ms: int = MEDIA_LIB_POLL_TIMEOUT,
) -> bool:
    deadline = time.time() + (timeout_ms / 1000)
    last_status = {"total": 0, "visible": 0, "libraryCount": 0, "loading": False, "noItems": False}
    switched_tab = False

    while time.time() < deadline:
        if not switched_tab:
            _switch_to_media_library_tab(page, label)
            switched_tab = True

        last_status = _get_media_attachment_status(page)
        if (
            int(last_status.get("visible", 0)) > 0 or
            int(last_status.get("libraryCount", 0)) > 0
        ):
            return True

        if last_status.get("noItems"):
            break

        time.sleep(MEDIA_LIB_POLL_INTERVAL / 1000)

    add_log(
        f"No visible images in media library for {label} sau khi chờ {timeout_ms}ms "
        f"(total={last_status.get('total', 0)}, "
        f"visible={last_status.get('visible', 0)}, "
        f"library={last_status.get('libraryCount', 0)}, "
        f"loading={last_status.get('loading', False)})",
        "warning",
    )
    return False


def _wait_for_img_count_increase(
    page: Page,
    count_before: int,
    timeout_ms: int = INSERT_VERIFY_TIMEOUT,
) -> int:
    deadline = time.time() + (timeout_ms / 1000)
    latest = count_before
    while time.time() < deadline:
        latest = _count_imgs_in_iframe(page)
        if latest > count_before:
            return latest
        time.sleep(INSERT_VERIFY_INTERVAL / 1000)
    return latest


def _finalize(page: Page, max_images: int, reason: str) -> bool:
    """Đóng modal, log final count theo DOM, return bool dựa trên DOM count.

    Gọi `close_all_modals(page)` trước khi đếm để đảm bảo Clause 3.7.
    Return True nếu DOM có ít nhất 1 ảnh; ngược lại False.
    `reason` chỉ dùng cho log diagnostic ("done", "no_h2", "stopped", ...).
    """
    close_all_modals(page)
    final = _count_imgs_in_iframe(page)
    if final > max_images:
        add_log(
            f"Total images inserted: {max_images}/{max_images} "
            f"(DOM currently has {final}; stopped at cap)",
            "warning",
        )
    elif final >= max_images:
        add_log(f"Total images inserted: {final}/{max_images}", "success")
    else:
        add_log(
            f"Total images inserted: {final}/{max_images} "
            f"(reason={reason}) — proceeding without blocking post",
            "warning",
        )
    return final > 0


def _try_insert_image_at_h2(
    page: Page,
    h2_index: int,
    keyword: str,
    max_images: Optional[int] = None,
) -> bool:
    """Atomic insert một ảnh tại vị trí H2 thứ h2_index (0-based).

    Thực hiện sub-flow Add Media → select → alt → link → Insert
    với internal retry MAX_SLOT_RETRIES cho các sub-step yếu (Add Media btn,
    media modal, attachments load) và DOM-based verification ở bước cuối.

    Returns:
        True nếu DOM count <img> tăng sau khi click Insert
        (verify qua _count_imgs_in_iframe). False ngược lại — caller có thể
        retry vị trí này ở vòng outer retry kế tiếp.

    Respect stop/pause flags trước mỗi sub-step nặng. Không raise — bất kỳ
    exception nào trong sub-step đều được bắt và log warning.
    """
    for attempt in range(MAX_SLOT_RETRIES + 1):
        # Stop/Pause check trước mỗi attempt
        if not state.is_running:
            return False
        if state.is_paused and not wait_if_paused():
            return False
        if max_images is not None and _count_imgs_in_iframe(page) >= max_images:
            return True

        try:
            if attempt > 0:
                add_log(
                    f"Slot retry {attempt}/{MAX_SLOT_RETRIES} cho H2 #{h2_index + 1}",
                    "info",
                )
                close_all_modals(page)
                _switch_to_visual_mode(page)

            # === Step 1: Position cursor at end of H2 ===
            h2_elements = _get_h2_elements_in_iframe(page)
            if h2_index >= len(h2_elements):
                add_log(
                    f"H2 #{h2_index + 1} không tồn tại (chỉ có {len(h2_elements)} H2)",
                    "warning",
                )
                return False
            h2_element = h2_elements[h2_index]
            try:
                h2_element.scroll_into_view_if_needed()
                time.sleep(0.3)
                h2_element.click()
                time.sleep(0.2)
                page.keyboard.press("End")
                page.keyboard.press("Enter")
                time.sleep(0.3)
            except Exception as e:
                add_log(f"Position cursor fail at H2 #{h2_index + 1}: {e}", "warning")
                continue  # retry attempt

            # === Step 2: Click Add Media với polling ===
            add_btn = page.locator("#insert-media-button, .add_media").first
            btn_visible = False
            poll_start = time.time()
            while (time.time() - poll_start) * 1000 < ADD_MEDIA_BTN_TIMEOUT:
                try:
                    if add_btn.is_visible(timeout=500):
                        btn_visible = True
                        break
                except Exception:
                    pass
                time.sleep(0.3)
            if not btn_visible:
                add_log(
                    f"Add Media button not visible cho H2 #{h2_index + 1} "
                    f"(attempt {attempt + 1})",
                    "warning",
                )
                continue
            if not _click_first_selector_resilient(
                page,
                ["#insert-media-button", ".add_media"],
                "Add Media button",
            ):
                add_log("Click Add Media fail", "warning")
                continue

            # === Step 3: Wait media modal ===
            try:
                page.wait_for_selector(".media-modal", timeout=MEDIA_MODAL_TIMEOUT)
                time.sleep(1.0)
            except Exception:
                add_log(
                    f"Media modal không xuất hiện cho H2 #{h2_index + 1} "
                    f"(attempt {attempt + 1})",
                    "warning",
                )
                close_all_modals(page)
                continue

            # === Step 4: Wait until the media grid has a visible attachment ===
            media_label = f"H2 #{h2_index + 1} (attempt {attempt + 1})"
            if not _wait_for_visible_media_attachments(page, media_label):
                close_all_modals(page)
                continue

            # === Step 4b: Pick random visible image (JS avoids hidden locator timeout) ===
            if not _select_visible_media_attachment(page, f"H2 #{h2_index + 1}"):
                close_all_modals(page)
                continue

            # === Step 5: Set alt text = keyword ===
            try:
                alt_selectors = [
                    "input[data-setting='alt']",
                    "#attachment-details-alt-text",
                    ".attachment-details input[type='text']",
                    "input.attachment-alt-text",
                ]
                for alt_sel in alt_selectors:
                    try:
                        alt = page.locator(alt_sel).first
                        if alt.is_visible(timeout=800):
                            alt.click()
                            alt.fill("")
                            time.sleep(0.1)
                            alt.fill(keyword)
                            add_log(f"Alt text set: {keyword}", "info")
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            # === Step 5b: Set link to attachment page ===
            try:
                link = page.locator("select[data-setting='link']").first
                if link.is_visible(timeout=500):
                    link.select_option("post")
            except Exception:
                pass

            # === Step 6: Read selected image URL + insert directly into TinyMCE ===
            selected_image = _get_selected_media_image(page, keyword)
            if not selected_image:
                add_log(
                    f"Không đọc được URL ảnh đã chọn cho H2 #{h2_index + 1}",
                    "warning",
                )
                close_all_modals(page)
                continue

            if not _insert_selected_image_after_h2_direct(
                page,
                h2_index,
                selected_image,
                keyword,
            ):
                close_all_modals(page)
                continue

            # === Step 7: Position verify (best-effort, không undo) ===
            if not _img_is_after_h2(page, h2_index):
                add_log(
                    f"Image inserted but not directly under H2 #{h2_index + 1} "
                    f"— outer retry sẽ thử slot khác nếu cần",
                    "warning",
                )
                # Vẫn return True vì DOM count đã tăng (ảnh có trong bài).
                # Outer retry sẽ tự nhiên thử slot khác nếu chưa đủ max_images
                # vì _find_unfilled_target_h2 sẽ thấy H2 này vẫn unfilled.
            else:
                add_log(
                    f"Inserted image under H2 #{h2_index + 1} (verified)",
                    "success",
                )

            # === Cleanup: close modal + switch back Visual mode ===
            close_all_modals(page)
            time.sleep(0.5)
            _switch_to_visual_mode(page)
            return True

        except Exception as e:
            add_log(
                f"Unexpected error trong _try_insert_image_at_h2 "
                f"H2 #{h2_index + 1} (attempt {attempt + 1}): {e}",
                "warning",
            )
            close_all_modals(page)
            continue

    return False


def _find_unfilled_target_h2(page: Page, target_indices: list) -> list:
    """Trả về subset của target_indices chưa có ảnh sibling phía sau.

    Filter các index thoả: idx < len(h2_elements) AND not _img_is_after_h2(page, idx).
    Giữ thứ tự gốc của target_indices.

    Args:
        page: Playwright page
        target_indices: list 0-based H2 index muốn check (vd [0, 2, 4])

    Returns:
        list[int] các index unfilled, theo thứ tự gốc.
    """
    h2_elements = _get_h2_elements_in_iframe(page)
    n = len(h2_elements)
    unfilled = []
    for idx in target_indices:
        if idx >= n:
            continue
        if not _img_is_after_h2(page, idx):
            unfilled.append(idx)
    return unfilled


def _find_other_unfilled_h2(page: Page, exclude_indices: set) -> list:
    """Trả về list H2 index khác (ngoài exclude_indices) chưa có <img> kế tiếp.

    Sắp xếp ascending (range tăng dần — ưu tiên 1, 3 trước index lớn hơn).
    Dùng cho phase outer retry khi target H2 đã đầy hoặc out of range.

    Args:
        page: Playwright page
        exclude_indices: set các H2 index cần loại trừ (thường là target_h2_indices)

    Returns:
        list[int] các index H2 còn trống ngoài exclude_indices, ascending.
    """
    h2_elements = _get_h2_elements_in_iframe(page)
    n = len(h2_elements)
    result = []
    for idx in range(n):
        if idx in exclude_indices:
            continue
        if not _img_is_after_h2(page, idx):
            result.append(idx)
    return result


def _fallback_insert_image_no_h2(
    page: Page,
    keyword: str,
    slot_hint: str,
    max_images: Optional[int] = None,
) -> bool:
    """Chèn 1 ảnh khi bài KHÔNG có H2. Position cursor vào paragraph theo slot_hint.

    Args:
        page: Playwright page
        keyword: alt text cho ảnh
        slot_hint: 'top' (paragraph đầu), 'middle' (paragraph giữa), 'bottom' (paragraph cuối)

    Returns:
        True nếu DOM count <img> tăng sau click Insert; False ngược lại.
        KHÔNG verify position (không có H2 anchor).
    """
    if not state.is_running:
        return False
    if state.is_paused and not wait_if_paused():
        return False
    if max_images is not None and _count_imgs_in_iframe(page) >= max_images:
        return True

    try:
        # === Step 1: Position cursor vào paragraph theo slot_hint ===
        try:
            paragraphs = page.frame_locator("#content_ifr").locator("p").all()
        except Exception:
            paragraphs = []

        if not paragraphs:
            add_log(
                f"Fallback ({slot_hint}): no paragraph in iframe — skip",
                "warning",
            )
            return False

        if slot_hint == "top":
            target = paragraphs[0]
        elif slot_hint == "middle":
            target = paragraphs[len(paragraphs) // 2]
        elif slot_hint == "bottom":
            target = paragraphs[-1]
        else:
            add_log(f"Invalid slot_hint: {slot_hint}", "warning")
            return False

        try:
            target.scroll_into_view_if_needed()
            time.sleep(0.3)
            target.click()
            time.sleep(0.2)
            page.keyboard.press("End")
            page.keyboard.press("Enter")
            time.sleep(0.3)
        except Exception as e:
            add_log(f"Fallback ({slot_hint}) position cursor fail: {e}", "warning")
            return False

        # === Step 2: Click Add Media với polling ===
        add_btn = page.locator("#insert-media-button, .add_media").first
        btn_visible = False
        poll_start = time.time()
        while (time.time() - poll_start) * 1000 < ADD_MEDIA_BTN_TIMEOUT:
            try:
                if add_btn.is_visible(timeout=500):
                    btn_visible = True
                    break
            except Exception:
                pass
            time.sleep(0.3)
        if not btn_visible:
            add_log(f"Fallback ({slot_hint}): Add Media btn not visible", "warning")
            return False
        if not _click_first_selector_resilient(
            page,
            ["#insert-media-button", ".add_media"],
            f"Fallback ({slot_hint}) Add Media button",
        ):
            add_log(f"Fallback ({slot_hint}) click Add Media fail", "warning")
            return False

        # === Step 3: Wait media modal ===
        try:
            page.wait_for_selector(".media-modal", timeout=MEDIA_MODAL_TIMEOUT)
            time.sleep(1.0)
        except Exception:
            add_log(f"Fallback ({slot_hint}): media modal không xuất hiện", "warning")
            close_all_modals(page)
            return False

        # === Step 4: Wait until the media grid has a visible attachment ===
        media_label = f"fallback {slot_hint}"
        if not _wait_for_visible_media_attachments(page, media_label):
            close_all_modals(page)
            return False

        # === Step 4b: Pick random visible image (JS avoids hidden locator timeout) ===
        if not _select_visible_media_attachment(page, f"fallback {slot_hint}"):
            close_all_modals(page)
            return False

        # === Step 5: Set alt text ===
        try:
            alt_selectors = [
                "input[data-setting='alt']",
                "#attachment-details-alt-text",
                ".attachment-details input[type='text']",
                "input.attachment-alt-text",
            ]
            for alt_sel in alt_selectors:
                try:
                    alt = page.locator(alt_sel).first
                    if alt.is_visible(timeout=800):
                        alt.click()
                        alt.fill("")
                        time.sleep(0.1)
                        alt.fill(keyword)
                        add_log(f"Alt text set: {keyword}", "info")
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # === Step 5b: Set link to attachment page ===
        try:
            link = page.locator("select[data-setting='link']").first
            if link.is_visible(timeout=500):
                link.select_option("post")
        except Exception:
            pass

        # === Step 6: Read selected image URL + insert directly into TinyMCE ===
        selected_image = _get_selected_media_image(page, keyword)
        if not selected_image:
            add_log(f"Fallback ({slot_hint}): không đọc được URL ảnh đã chọn", "warning")
            close_all_modals(page)
            return False

        if not _insert_selected_image_after_paragraph_direct(
            page,
            slot_hint,
            selected_image,
            keyword,
        ):
            close_all_modals(page)
            return False

        close_all_modals(page)
        time.sleep(0.5)
        _switch_to_visual_mode(page)
        return True

    except Exception as e:
        add_log(f"Fallback ({slot_hint}) unexpected error: {e}", "warning")
        close_all_modals(page)
        return False


def _rebalance_auto_images_to_targets(page: Page, target_indices: list) -> int:
    if not target_indices:
        return 0
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body, targetIndices) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const allHeadings = Array.from(body.querySelectorAll('h2, h3'));
                const contactIndex = allHeadings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                const headings = contactIndex >= 0 ?
                    allHeadings.slice(0, contactIndex) : allHeadings;
                const validTargets = targetIndices.filter((idx) => idx < headings.length);
                const wrapperFor = (img) => img.closest('p, figure') || img;
                const contactHeading = contactIndex >= 0 ? allHeadings[contactIndex] : null;
                const isBeforeContact = (node) => {
                    if (!contactHeading) return true;
                    return !!(node.compareDocumentPosition(contactHeading) &
                        Node.DOCUMENT_POSITION_FOLLOWING);
                };
                const imageNearHeading = (idx) => {
                    const heading = headings[idx];
                    let cur = heading ? heading.nextElementSibling : null;
                    for (let i = 0; i < 2 && cur; i++) {
                        if (cur.matches && cur.matches('img')) return cur;
                        const img = cur.querySelector && cur.querySelector('img');
                        if (img) return img;
                        cur = cur.nextElementSibling;
                    }
                    return null;
                };

                const usedWrappers = new Set();
                const missing = [];
                for (const idx of validTargets) {
                    const img = imageNearHeading(idx);
                    if (img) {
                        usedWrappers.add(wrapperFor(img));
                    } else {
                        missing.push(idx);
                    }
                }

                if (!missing.length) {
                    return { moved: 0, missing: 0, available: 0 };
                }

                const autoWrappers = Array.from(
                    body.querySelectorAll('img.wp-image-auto-poster')
                )
                    .map(wrapperFor)
                    .filter((node, idx, arr) => node && arr.indexOf(node) === idx);
                const afterContact = autoWrappers.filter((node) => !isBeforeContact(node));
                const beforeContactSpare = autoWrappers.filter((node) =>
                    isBeforeContact(node) && !usedWrappers.has(node)
                );
                const spare = afterContact.concat(beforeContactSpare);

                let moved = 0;
                for (const idx of missing) {
                    const node = spare.shift();
                    if (!node) break;
                    headings[idx].insertAdjacentElement('afterend', node);
                    moved += 1;
                }
                return { moved, missing: missing.length, available: autoWrappers.length };
            }""",
            target_indices,
        )
        moved = int((result or {}).get("moved", 0))
        if moved:
            _sync_editor_after_direct_insert(page)
            add_log(f"Final scan rebalanced {moved} image(s) to target headings", "success")
        return moved
    except Exception as e:
        add_log(f"Final image rebalance failed: {e}", "warning")
        return 0


def _remove_or_move_images_after_contact(page: Page, target_indices: list) -> int:
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body, targetIndices) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const headings = Array.from(body.querySelectorAll('h2, h3'));
                const contactIndex = headings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                if (contactIndex < 0) {
                    return { moved: 0, removed: 0, after: 0 };
                }
                const contactHeading = headings[contactIndex];
                const safeHeadings = headings.slice(0, contactIndex);
                const wrapperFor = (img) => img.closest('p, figure') || img;
                const isAfterContact = (node) => {
                    return !!(node.compareDocumentPosition(contactHeading) &
                        Node.DOCUMENT_POSITION_PRECEDING);
                };
                const imageNearHeading = (idx) => {
                    const heading = safeHeadings[idx];
                    let cur = heading ? heading.nextElementSibling : null;
                    for (let i = 0; i < 2 && cur; i++) {
                        if (cur.matches && cur.matches('img')) return cur;
                        const img = cur.querySelector && cur.querySelector('img');
                        if (img) return img;
                        cur = cur.nextElementSibling;
                    }
                    return null;
                };
                const afterWrappers = Array.from(
                    body.querySelectorAll('img.wp-image-auto-poster')
                )
                    .map(wrapperFor)
                    .filter((node, idx, arr) =>
                        node && arr.indexOf(node) === idx && isAfterContact(node)
                    );
                let moved = 0;
                let removed = 0;
                for (const node of afterWrappers) {
                    const target = targetIndices.find((idx) =>
                        idx < safeHeadings.length && !imageNearHeading(idx)
                    );
                    if (target !== undefined) {
                        safeHeadings[target].insertAdjacentElement('afterend', node);
                        moved += 1;
                    } else {
                        node.remove();
                        removed += 1;
                    }
                }
                return { moved, removed, after: afterWrappers.length };
            }""",
            target_indices,
        ) or {}
        changed = int(result.get("moved", 0)) + int(result.get("removed", 0))
        if changed:
            _sync_editor_after_direct_insert(page)
            add_log(
                f"Contact boundary cleanup: moved {result.get('moved', 0)}, "
                f"removed {result.get('removed', 0)} image(s) after contact section",
                "success",
            )
        return changed
    except Exception as e:
        add_log(f"Contact boundary cleanup failed: {e}", "warning")
        return 0


def _final_scan_and_repair_images(
    page: Page,
    keyword: str,
    max_images: int,
    target_h2_indices: list,
) -> bool:
    add_log("Final image scan: checking full article image distribution...", "info")
    close_all_modals(page)
    _switch_to_visual_mode(page)

    heading_count = _get_safe_heading_count_for_images(page)
    valid_targets = [idx for idx in target_h2_indices if idx < heading_count]
    _remove_or_move_images_after_contact(page, valid_targets)
    if valid_targets:
        _rebalance_auto_images_to_targets(page, valid_targets)

    current_count = _count_imgs_in_iframe(page)
    missing_targets = _find_unfilled_target_h2(page, valid_targets)
    add_log(
        f"Final image scan: {current_count}/{max_images} images, "
        f"targets={_format_heading_targets(valid_targets)}, "
        f"missing={_format_heading_targets(missing_targets)}",
        "info",
    )

    # 1) Bù vào các heading mục tiêu trước, để phân bố đều từ đầu tới cuối.
    while current_count < max_images and missing_targets:
        if not state.is_running:
            return False
        if state.is_paused and not wait_if_paused():
            return False
        remaining = max_images - current_count
        for h2_idx in _select_even_candidates(missing_targets, remaining):
            if _count_imgs_in_iframe(page) >= max_images:
                break
            _try_insert_image_at_h2(
                page,
                h2_idx,
                keyword,
                max_images=max_images,
            )
        new_count = _count_imgs_in_iframe(page)
        new_missing = _find_unfilled_target_h2(page, valid_targets)
        if new_count == current_count and new_missing == missing_targets:
            break
        current_count = new_count
        missing_targets = new_missing

    # 2) Nếu target chính vẫn chưa đủ ảnh, chọn các heading còn trống khác theo phân bố đều.
    if current_count < max_images:
        remaining = max_images - current_count
        other_indices = _find_other_unfilled_h2(page, exclude_indices=set(valid_targets))
        for h2_idx in _select_even_candidates(other_indices, remaining):
            if _count_imgs_in_iframe(page) >= max_images:
                break
            if not state.is_running:
                return False
            if state.is_paused and not wait_if_paused():
                return False
            _try_insert_image_at_h2(
                page,
                h2_idx,
                keyword,
                max_images=max_images,
            )

    # 3) Nếu bài ít heading hoặc Media Library fail ở heading, fallback paragraph theo 3 vùng.
    current_count = _count_imgs_in_iframe(page)
    if current_count < max_images:
        remaining = max_images - current_count
        for slot_hint in ("top", "middle", "bottom")[:remaining]:
            if _count_imgs_in_iframe(page) >= max_images:
                break
            if not state.is_running:
                return False
            if state.is_paused and not wait_if_paused():
                return False
            _fallback_insert_image_no_h2(
                page,
                keyword,
                slot_hint,
                max_images=max_images,
            )

    final_count = _count_imgs_in_iframe(page)
    final_missing = _find_unfilled_target_h2(page, valid_targets)
    if final_count >= max_images and not final_missing:
        add_log(
            f"Final image scan passed: {final_count}/{max_images} images "
            "with balanced heading targets",
            "success",
        )
    elif final_count >= max_images:
        add_log(
            f"Final image scan has enough images ({final_count}/{max_images}) "
            f"but target gaps remain: {_format_heading_targets(final_missing)}",
            "warning",
        )
    else:
        add_log(
            f"Final image scan still short: {final_count}/{max_images} images",
            "warning",
        )
    return final_count > 0


def insert_images_after_h2(page: Page, keyword: str, max_images: int = 3) -> bool:
    """Insert images after H2 headings using Visual Editor.

    Inserts up to `max_images` images after H2/H3 headings distributed across
    the whole article. Sử dụng DOM-based verification (`_count_imgs_in_iframe`)
    và per-slot retry (`_try_insert_image_at_h2`). Khi bài không có H2,
    fallback chèn vào sau paragraph top/middle/bottom (`_fallback_insert_image_no_h2`).

    Phase 2 outer retry rounds (cover library/modal flakiness, thiếu H2)
    chạy tối đa MAX_RETRY_ROUNDS lần sau Phase 1 nếu DOM count < max_images.

    Returns True nếu DOM iframe có >= 1 ảnh sau khi xử lý; False ngược lại.
    """
    try:
        add_log("Đang chèn hình vào bài viết...", "info")
        close_all_modals(page)
        _switch_to_visual_mode(page)

        # ----- PHASE 1: Initial pass over target H2 indices -----
        h2_elements = _get_h2_elements_in_iframe(page)
        safe_heading_count = _get_safe_heading_count_for_images(page)
        contact_idx = _get_contact_heading_index(page)
        target_h2_indices = _pick_evenly_spaced_indices(safe_heading_count, max_images)
        add_log(
            f"Image heading targets distributed: {_format_heading_targets(target_h2_indices)} "
            f"of {safe_heading_count} safe heading(s)"
            f"{' before contact section' if contact_idx is not None else ''}",
            "info",
        )

        # Early branch: bài không có H2 → fallback paragraph
        if safe_heading_count <= 0:
            add_log("No H2 elements found — using paragraph fallback", "warning")
            for slot_hint in ("top", "middle", "bottom"):
                if not state.is_running:
                    return _finalize(page, max_images, "stopped")
                if state.is_paused and not wait_if_paused():
                    return _finalize(page, max_images, "stopped")
                if _count_imgs_in_iframe(page) >= max_images:
                    break
                _fallback_insert_image_no_h2(
                    page,
                    keyword,
                    slot_hint,
                    max_images=max_images,
                )
            _final_scan_and_repair_images(page, keyword, max_images, target_h2_indices)
            return _finalize(page, max_images, "no_h2")

        # Phase 1 main loop: chèn vào target H2 indices
        for target_index in target_h2_indices:
            if _count_imgs_in_iframe(page) >= max_images:
                break
            if not state.is_running:
                add_log("Stopped while inserting images", "warning")
                return _finalize(page, max_images, "stopped")
            if state.is_paused and not wait_if_paused():
                return _finalize(page, max_images, "stopped")

            if target_index >= safe_heading_count:
                add_log(
                    f"H2 #{target_index + 1} not found "
                    f"(only {safe_heading_count} safe H2/H3s) — will fallback later",
                    "info",
                )
                continue

            _try_insert_image_at_h2(
                page,
                target_index,
                keyword,
                max_images=max_images,
            )

        # ----- PHASE 2: Outer retry rounds với fallback (Clause 2.8) -----
        for round_idx in range(MAX_RETRY_ROUNDS):
            current_count = _count_imgs_in_iframe(page)
            if current_count >= max_images:
                break
            if not state.is_running:
                return _finalize(page, max_images, "stopped")
            if state.is_paused and not wait_if_paused():
                return _finalize(page, max_images, "stopped")

            add_log(
                f"Retry round {round_idx + 1}/{MAX_RETRY_ROUNDS}: "
                f"have {current_count}/{max_images} — scanning for unfilled slots",
                "info",
            )

            # 2a) Re-attempt target headings that are still unfilled
            unfilled_targets = _find_unfilled_target_h2(page, target_h2_indices)

            # 2b) Then other headings, also selected evenly across the article
            remaining_slots = max_images - _count_imgs_in_iframe(page)
            other_indices = _select_even_candidates(
                _find_other_unfilled_h2(
                    page, exclude_indices=set(target_h2_indices)
                ),
                remaining_slots,
            )

            candidate_order = unfilled_targets + other_indices
            for h2_idx in candidate_order:
                if _count_imgs_in_iframe(page) >= max_images:
                    break
                if not state.is_running:
                    return _finalize(page, max_images, "stopped")
                if state.is_paused and not wait_if_paused():
                    return _finalize(page, max_images, "stopped")
                _try_insert_image_at_h2(
                    page,
                    h2_idx,
                    keyword,
                    max_images=max_images,
                )

            # 2c) If still short and H2 list exhausted, paragraph fallback
            if _count_imgs_in_iframe(page) < max_images:
                remaining = max_images - _count_imgs_in_iframe(page)
                slot_hints = ("top", "middle", "bottom")[:remaining]
                for slot_hint in slot_hints:
                    if not state.is_running:
                        break
                    if state.is_paused and not wait_if_paused():
                        break
                    if _count_imgs_in_iframe(page) >= max_images:
                        break
                    _fallback_insert_image_no_h2(
                        page,
                        keyword,
                        slot_hint,
                        max_images=max_images,
                    )

        _final_scan_and_repair_images(page, keyword, max_images, target_h2_indices)
        return _finalize(page, max_images, "done")

    except Exception as e:
        add_log(f"Error in insert_images_after_h2: {e}", "error")
        close_all_modals(page)
        return False


def close_all_modals(page: Page, max_attempts: int = 2):
    try:
        for _ in range(max_attempts):
            # Quick Escape key press
            page.keyboard.press("Escape")
            time.sleep(0.15)
            
            # Try close buttons
            for selector in [".media-modal-close", "button[aria-label='Close']", ".media-frame-close"]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=300):
                        btn.click()
                        time.sleep(0.15)
                        break
                except:
                    continue
            
            # Check if modal is gone
            try:
                if not page.locator(".media-modal").first.is_visible(timeout=300):
                    return
            except:
                return
    except:
        pass

# Alias for compatibility
force_close_all_modals = close_all_modals

def select_random_image_for_content(page: Page, alt_text: str) -> bool:
    try:
        # Wait for media modal
        page.wait_for_selector(".media-modal", timeout=10000)
        if not _wait_for_visible_media_attachments(page, "content body"):
            close_all_modals(page)
            return False

        if not _select_visible_media_attachment(page, "content body"):
            close_all_modals(page)
            return False

        # Set alt text with keyword
        time.sleep(0.5)  # Wait for details panel to load
        alt_selectors = [
            "input[data-setting='alt']",
            "#attachment-details-alt-text",
            ".attachment-details input[type='text']",
            "input[name='alt']",
            ".setting input[type='text'][data-setting='alt']"
        ]
        
        alt_set = False
        for alt_sel in alt_selectors:
            try:
                alt_input = page.locator(alt_sel).first
                if alt_input.is_visible(timeout=1000):
                    alt_input.click()
                    alt_input.fill("")  # Clear first
                    time.sleep(0.1)
                    alt_input.fill(alt_text)
                    add_log(f"Alt text đã set: {alt_text}", "info")
                    alt_set = True
                    time.sleep(0.3)
                    break
            except:
                continue
        
        if not alt_set:
            add_log("Không thể set alt text", "warning")
        
        selected_image = _get_selected_media_image(page, alt_text)
        if selected_image and _insert_selected_image_after_paragraph_direct(
            page,
            "bottom",
            selected_image,
            alt_text,
        ):
            close_all_modals(page)
            return True
        
        # Close modal if insert failed
        close_all_modals(page)
        
        return False
        
    except Exception as e:
        add_log(f"Error selecting image for content: {e}", "warning")
        close_all_modals(page)
        return False

def select_first_category(page: Page) -> bool:
    """Tick category cấu hình (hoặc fallback) trong Classic Editor.

    Bulletproof timeout: mọi locator action đều bound timeout (≤ 1.5s) để
    không hang khi DOM checklist có nhiều cấp con / element bị overlap.
    """
    add_log("Đang chọn danh mục...", "info")
    deadline = time.time() + 15  # tổng deadline 15s — quá thì bỏ qua

    try:
        def normalize_text(value: str) -> str:
            value = (value or "").strip().lower()
            value = "".join(
                c for c in unicodedata.normalize("NFD", value)
                if unicodedata.category(c) != "Mn"
            )
            return re.sub(r"\s+", " ", value)

        configured_category = (state.config.get("category_name") or "Tin tức").strip()
        preferred_names = [configured_category]
        if normalize_text(configured_category) != normalize_text("Tin tức"):
            preferred_names.append("Tin tức")

        # Switch to "All categories" tab to avoid selecting from "Most Used".
        try:
            all_tab = page.locator("#category-tabs a[href='#category-all']").first
            if all_tab.count() > 0:
                all_tab.click(timeout=1500)
                time.sleep(0.3)
        except Exception:
            pass

        # Đọc 1 lần qua JS — nhanh, không bị multiple round-trip locator,
        # không bao giờ hang vì JS chạy synchronously trong page context.
        try:
            rows_data = page.evaluate(
                """() => {
                    const out = [];
                    const lists = ['#categorychecklist', '#categorychecklist-pop'];
                    for (const sel of lists) {
                        const root = document.querySelector(sel);
                        if (!root) continue;
                        const items = root.querySelectorAll('li');
                        items.forEach((li, idx) => {
                            const cb = li.querySelector("input[type='checkbox']");
                            const lb = li.querySelector('label');
                            if (!cb || !lb) return;
                            out.push({
                                listSel: sel,
                                index: idx,
                                cbId: cb.id || '',
                                cbValue: cb.value || '',
                                checked: !!cb.checked,
                                label: (lb.textContent || '').trim(),
                            });
                        });
                    }
                    return out;
                }"""
            ) or []
        except Exception as e:
            add_log(f"Không đọc được danh sách category: {e}", "warning")
            return False

        if not rows_data:
            add_log("No categories found", "warning")
            return False

        add_log(f"Tìm thấy {len(rows_data)} danh mục", "info")

        # Match: ưu tiên exact normalize → contains
        target = None
        for target_name in preferred_names:
            target_norm = normalize_text(target_name)
            target = next(
                (r for r in rows_data if normalize_text(r["label"]) == target_norm),
                None,
            )
            if target:
                break
            target = next(
                (r for r in rows_data if target_norm in normalize_text(r["label"])),
                None,
            )
            if target:
                break

        if time.time() > deadline:
            add_log("Category selection vượt deadline — bỏ qua", "warning")
            return False

        if target:
            # Tick + uncheck others bằng JS 1 round-trip — tránh nhiều
            # locator.check() mỗi cái 30s timeout default.
            try:
                ok = page.evaluate(
                    """({ cbId, cbValue }) => {
                        const lists = ['#categorychecklist', '#categorychecklist-pop'];
                        let target = null;
                        const allCbs = [];
                        for (const sel of lists) {
                            const root = document.querySelector(sel);
                            if (!root) continue;
                            root.querySelectorAll("input[type='checkbox']").forEach(cb => {
                                allCbs.push(cb);
                                if ((cbId && cb.id === cbId) ||
                                    (cbValue && cb.value === cbValue)) {
                                    target = cb;
                                }
                            });
                        }
                        if (!target) return { ok: false, reason: 'target not found' };
                        // Uncheck all others, check target
                        for (const cb of allCbs) {
                            const want = (cb === target);
                            if (cb.checked !== want) {
                                cb.checked = want;
                                cb.dispatchEvent(new Event('change', { bubbles: true }));
                                cb.dispatchEvent(new Event('click', { bubbles: true }));
                            }
                        }
                        // Scroll target into view nhẹ nhàng
                        try { target.scrollIntoView({ block: 'center' }); } catch (e) {}
                        return { ok: target.checked, reason: 'set' };
                    }""",
                    {"cbId": target["cbId"], "cbValue": target["cbValue"]},
                )
                if ok and ok.get("ok"):
                    add_log(f"Selected category: {target['label']}", "success")
                    return True
                add_log(
                    f"JS check fail ({ok.get('reason') if ok else 'no result'}), "
                    f"thử fallback locator",
                    "warning",
                )
            except Exception as e:
                add_log(f"JS category set error: {e} — thử fallback", "warning")

            # Fallback locator-based với timeout chặt
            if time.time() > deadline:
                add_log("Vượt deadline trước fallback — bỏ qua", "warning")
                return False
            try:
                cb_sel = (
                    f"#{target['cbId']}" if target["cbId"]
                    else f"input[type='checkbox'][value='{target['cbValue']}']"
                )
                cb = page.locator(cb_sel).first
                cb.scroll_into_view_if_needed(timeout=1500)
                cb.check(force=True, timeout=2000)
                add_log(f"Selected (locator): {target['label']}", "success")
                return True
            except Exception as e:
                add_log(f"Locator check fail: {e}", "warning")

        # Fallback: tick first unchecked — cũng qua JS để tránh hang
        if time.time() > deadline:
            return False
        try:
            picked_label = page.evaluate(
                """() => {
                    const lists = ['#categorychecklist', '#categorychecklist-pop'];
                    for (const sel of lists) {
                        const root = document.querySelector(sel);
                        if (!root) continue;
                        const cbs = root.querySelectorAll("input[type='checkbox']");
                        for (const cb of cbs) {
                            if (!cb.checked) {
                                cb.checked = true;
                                cb.dispatchEvent(new Event('change', { bubbles: true }));
                                cb.dispatchEvent(new Event('click', { bubbles: true }));
                                const li = cb.closest('li');
                                const lb = li ? li.querySelector('label') : null;
                                return (lb && lb.textContent || '').trim();
                            }
                        }
                    }
                    return null;
                }"""
            )
            if picked_label:
                add_log(f"Selected fallback category: {picked_label}", "success")
                return True
        except Exception:
            pass

        add_log("Category already selected hoặc không có lựa chọn khác", "info")
        return True

    except Exception as e:
        add_log(f"Error selecting category: {e}", "warning")
        return False

def add_post_tags(page: Page, tags: str) -> bool:
    """Add tags to WordPress post (Classic Editor).
    
    Args:
        page: Playwright page object
        tags: Comma-separated tags string
    """
    try:
        if not tags or not tags.strip():
            add_log("No tags to add", "info")
            return True
        
        add_log(f"Adding tags: {tags[:50]}...", "info")
        
        # Scroll to Tags section
        try:
            tags_box = page.locator("#tagsdiv-post_tag, #tagsdiv, .tagsdiv").first
            if tags_box.is_visible(timeout=2000):
                tags_box.scroll_into_view_if_needed()
                time.sleep(0.5)
        except:
            pass
        
        # Find the tags input field
        tag_input_selectors = [
            "#new-tag-post_tag",
            "input.newtag",
            "#newtag",
            "input[name='newtag[post_tag]']",
            ".tagsdiv input[type='text']"
        ]
        
        tag_input = None
        for selector in tag_input_selectors:
            try:
                input_el = page.locator(selector).first
                if input_el.is_visible(timeout=1000):
                    tag_input = input_el
                    add_log(f"Found tags input: {selector}", "info")
                    break
            except:
                continue
        
        if not tag_input:
            add_log("Could not find tags input field", "warning")
            return False
        
        # Clear and fill the tags input
        tag_input.click()
        tag_input.fill("")
        time.sleep(0.2)
        tag_input.fill(tags.strip())
        time.sleep(0.3)
        
        # Click the "Add" / "Thêm" button
        add_button_selectors = [
            "input.tagadd",
            "button.tagadd",
            "#tagsdiv-post_tag .tagadd",
            "input[value='Thêm']",
            "input[value='Add']",
            ".tagsdiv input[type='button']"
        ]
        
        for selector in add_button_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    add_log("Clicked Add tags button", "success")
                    time.sleep(0.5)
                    
                    # Verify tags were added by checking tag cloud
                    try:
                        tag_cloud = page.locator(".tagchecklist, .the-tags").first
                        if tag_cloud.is_visible(timeout=1000):
                            add_log("Tags added successfully", "success")
                    except:
                        pass
                    
                    return True
            except:
                continue
        
        # Try JavaScript fallback to click the add button
        try:
            page.evaluate("""
                () => {
                    const addBtn = document.querySelector('.tagadd, input.tagadd');
                    if (addBtn) addBtn.click();
                }
            """)
            add_log("Clicked Add tags button via JS", "success")
            time.sleep(0.5)
            return True
        except:
            pass
        
        add_log("Could not find Add tags button", "warning")
        return False
        
    except Exception as e:
        add_log(f"Error adding tags: {e}", "warning")
        return False


def set_featured_image(page: Page, keyword: str) -> bool:
    """Set featured image using JavaScript to open media modal.
    
    New approach:
    1. Use JavaScript to trigger WordPress media frame
    2. Wait for modal with multiple fallbacks
    3. Select random unused image
    4. Set alt text = keyword
    5. Click set featured image button
    """
    try:
        add_log("Setting featured image...", "info")
        
        # First, close any open modals
        force_close_all_modals(page)
        time.sleep(0.5)
        
        # Method 1: Try JavaScript click on the link
        modal_opened = False
        
        try:
            # Use JavaScript to click the link and trigger the modal
            result = page.evaluate("""
                () => {
                    // Try clicking the set featured image link via JavaScript
                    const link = document.querySelector('#set-post-thumbnail') || 
                                 document.querySelector('a[href*="type=set-post-thumbnail"]') ||
                                 document.querySelector('#postimagediv a');
                    if (link) {
                        link.click();
                        return 'clicked';
                    }
                    return 'not_found';
                }
            """)
            add_log(f"JS click result: {result}", "info")
            time.sleep(3)
            
            # Debug: Check what modal elements exist
            modal_info = page.evaluate("""
                () => {
                    const modals = [];
                    if (document.querySelector('.media-modal')) modals.push('media-modal');
                    if (document.querySelector('.media-frame')) modals.push('media-frame');
                    if (document.querySelector('#TB_window')) modals.push('TB_window');
                    if (document.querySelector('.media-modal-content')) modals.push('media-modal-content');
                    if (document.querySelector('.attachment-details')) modals.push('attachment-details');
                    return modals.length > 0 ? modals.join(', ') : 'none';
                }
            """)
            add_log(f"Modal elements found: {modal_info}", "info")
            
            # Check if any modal opened
            if modal_info != 'none':
                modal_opened = True
                add_log("Modal detected via JS check", "info")
            else:
                try:
                    page.wait_for_selector(".media-modal, .media-frame, #TB_window", timeout=3000)
                    modal_opened = True
                    add_log("Media modal opened via JS click", "info")
                except:
                    pass
        except Exception as e:
            add_log(f"JS click failed: {e}", "warning")
        
        # Method 2: Try direct Playwright click with force
        if not modal_opened:
            try:
                link = page.locator("#set-post-thumbnail, #postimagediv a").first
                if link.is_visible(timeout=2000):
                    link.click(force=True)
                    time.sleep(3)
                    # Check for both media-modal and thickbox
                    try:
                        page.wait_for_selector(".media-modal, #TB_window, .media-frame", timeout=5000)
                        modal_opened = True
                        add_log("Modal opened via force click", "info")
                    except:
                        pass
            except:
                pass
        
        # Method 3: Try triggering the WordPress media frame directly
        if not modal_opened:
            try:
                result = page.evaluate("""
                    () => {
                        if (typeof wp !== 'undefined' && wp.media) {
                            // Create a new media frame for featured image
                            const frame = wp.media({
                                title: 'Chọn ảnh đại diện',
                                button: { text: 'Đặt ảnh đại diện' },
                                library: { type: 'image' },
                                multiple: false
                            });
                            frame.open();
                            return 'opened';
                        }
                        return 'wp_not_found';
                    }
                """)
                add_log(f"WP media frame: {result}", "info")
                time.sleep(3)
                
                # Check for modal with multiple selectors
                try:
                    page.wait_for_selector(".media-modal, #TB_window, .media-frame, .media-modal-content", timeout=8000)
                    modal_opened = True
                    add_log("Modal opened via wp.media", "info")
                except:
                    # Try waiting a bit more
                    time.sleep(2)
                    if page.locator(".media-modal, .media-frame").count() > 0:
                        modal_opened = True
                        add_log("Modal found after extra wait", "info")
            except Exception as e:
                add_log(f"WP media frame failed: {e}", "warning")
        
        if not modal_opened:
            add_log("Could not open media modal - skipping featured image", "warning")
            return False
        
        # Wait for images to load
        time.sleep(3)
        
        # Click on Media Library tab if available
        try:
            media_lib_tab = page.locator(".media-menu-item:has-text('Thư viện Media'), .media-menu-item:has-text('Media Library'), .media-menu-item:has-text('Chọn từ thư viện')").first
            if media_lib_tab.is_visible(timeout=1000):
                media_lib_tab.click()
                time.sleep(2)
                add_log("Switched to Media Library", "info")
        except:
            pass
        
        # Wait for images to fully load
        time.sleep(2)
        
        # Use JavaScript to select a random image (more reliable than visibility check)
        try:
            import random
            
            # Get total number of images and select random one via JS
            result = page.evaluate("""
                (usedIndices) => {
                    const attachments = document.querySelectorAll('.attachments .attachment, li.attachment, .attachment');
                    if (attachments.length === 0) return { success: false, error: 'no_images' };
                    
                    // Get available indices (not in usedIndices)
                    const availableIndices = [];
                    for (let i = 0; i < Math.min(attachments.length, 30); i++) {
                        if (!usedIndices.includes(i)) {
                            availableIndices.push(i);
                        }
                    }
                    
                    // If all used, reset to all indices
                    const indicesToUse = availableIndices.length > 0 ? availableIndices : 
                                        Array.from({length: Math.min(attachments.length, 30)}, (_, i) => i);
                    
                    // Pick random index
                    const randomIndex = indicesToUse[Math.floor(Math.random() * indicesToUse.length)];
                    const img = attachments[randomIndex];
                    
                    if (img) {
                        img.click();
                        return { success: true, index: randomIndex, total: attachments.length, available: indicesToUse.length };
                    }
                    return { success: false, error: 'click_failed' };
                }
            """, list(state.used_featured_images))
            
            if result.get('success'):
                selected_idx = result.get('index', 0)
                state.used_featured_images.add(selected_idx)
                add_log(f"Selected image #{selected_idx + 1} via JS ({result.get('available')} available of {result.get('total')})", "info")
                time.sleep(1)
            else:
                add_log(f"Could not select image: {result.get('error')}", "warning")
                force_close_all_modals(page)
                return False
                
        except Exception as e:
            add_log(f"Error selecting image via JS: {e}", "warning")
            force_close_all_modals(page)
            return False
        
        # Set alt text = keyword using JavaScript (more reliable)
        time.sleep(1)
        try:
            page.evaluate("""
                (keyword) => {
                    // Try multiple selectors for alt input
                    const altInput = document.querySelector("input[data-setting='alt']") ||
                                    document.querySelector("#attachment-details-alt-text") ||
                                    document.querySelector(".attachment-details input[type='text']");
                    if (altInput) {
                        altInput.value = keyword;
                        altInput.dispatchEvent(new Event('input', { bubbles: true }));
                        altInput.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }
            """, keyword)
            add_log(f"Alt text: {keyword}", "info")
        except:
            pass  # Alt text is optional
        
        # Click "Đặt ảnh đại diện" button
        button_selectors = [
            "button.media-button-select",
            "button:has-text('Đặt ảnh đại diện')",
            "button:has-text('Set featured image')",
            ".media-button-select",
        ]
        
        button_clicked = False
        for selector in button_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    add_log("Featured image set!", "success")
                    button_clicked = True
                    time.sleep(1)
                    break
            except:
                continue
        
        if not button_clicked:
            # Try JavaScript click as fallback
            try:
                page.evaluate("""
                    () => {
                        const btn = document.querySelector('.media-button-select') || 
                                   document.querySelector('button.button-primary');
                        if (btn) btn.click();
                    }
                """)
                add_log("Featured image set via JS!", "success")
                button_clicked = True
                time.sleep(1)
            except:
                pass
        
        if not button_clicked:
            add_log("Could not click Set Featured Image button", "warning")
            force_close_all_modals(page)
            return False
        
        # Close any remaining modals
        time.sleep(0.5)
        force_close_all_modals(page)
        
        return True
        
    except Exception as e:
        add_log(f"Error setting featured image: {e}", "warning")
        force_close_all_modals(page)
        return False

def publish_or_schedule_post(page: Page, is_schedule: bool, publish_date: datetime = None) -> bool:
    try:
        # Pre-publish sync: ép TinyMCE flush nội dung iframe → textarea trước
        # khi submit form. Classic Editor tự gọi triggerSave() lúc submit, nhưng
        # nếu iframe đang Visual mode mà chưa fully init, hoặc user vừa edit
        # qua DOM (insert ảnh, ...), bước này đảm bảo textarea có HTML mới nhất.
        try:
            page.evaluate(
                """() => {
                    if (window.tinymce) {
                        try { tinymce.triggerSave(); } catch (e) {}
                        const ed = tinymce.get('content');
                        if (ed) {
                            try { ed.save(); } catch (e) {}
                        }
                    }
                }"""
            )
        except Exception:
            pass

        # Cuộn lên đầu trang — nút Publish của Classic Editor nằm ở sidebar
        # góc trên phải; cuộn về đầu đảm bảo cả khu Publish meta box đều visible.
        try:
            page.evaluate("window.scrollTo({ top: 0, behavior: 'instant' })")
        except Exception:
            try:
                page.evaluate("window.scrollTo(0, 0)")
            except Exception:
                pass
        time.sleep(0.4)

        # For scheduling in Classic Editor
        if is_schedule and publish_date:
            # Click "Chỉnh sửa" next to "Xuất bản ngay lập tức" to open date picker
            if _click_first_selector_resilient(
                page,
                [".edit-timestamp", "a.edit-timestamp", "#timestamp a"],
                "timestamp edit link",
                timeout_ms=1500,
            ):
                time.sleep(0.5)
                
                # Fill in date fields
                # Month dropdown
                month_select = page.locator("#mm, select[name='mm']").first
                if month_select.is_visible(timeout=2000):
                    month_select.select_option(str(publish_date.month).zfill(2))
                
                # Day input
                day_input = page.locator("#jj, input[name='jj']").first
                if day_input.is_visible(timeout=2000):
                    day_input.fill(str(publish_date.day))
                
                # Year input
                year_input = page.locator("#aa, input[name='aa']").first
                if year_input.is_visible(timeout=2000):
                    year_input.fill(str(publish_date.year))
                
                # Hour input
                hour_input = page.locator("#hh, input[name='hh']").first
                if hour_input.is_visible(timeout=2000):
                    hour_input.fill(str(publish_date.hour).zfill(2))
                
                # Minute input
                minute_input = page.locator("#mn, input[name='mn']").first
                if minute_input.is_visible(timeout=2000):
                    minute_input.fill("00")
                
                # Click OK button to confirm date. Classic Editor can report this
                # button visible but outside viewport, so use the resilient helper.
                if _click_first_selector_resilient(
                    page,
                    ["a.save-timestamp", ".save-timestamp"],
                    "timestamp OK button",
                    timeout_ms=1500,
                ):
                    time.sleep(0.5)
                else:
                    add_log("Could not confirm timestamp OK button", "warning")
        
        # Click Publish/Schedule button - in Classic Editor it's just #publish
        add_log("Preparing to publish...", "info")

        # Đảm bảo đã ở đầu trang (phòng trường hợp date picker kéo scroll xuống)
        try:
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass
        time.sleep(0.4)

        publish_btn = page.locator("#publish, input#publish, #publishing-action input[type='submit']").first

        # Cuộn nút Publish vào viewport — đây là điểm bạn hay phải thao tác tay.
        # scroll_into_view_if_needed hoạt động kể cả với element ngoài viewport.
        try:
            publish_btn.scroll_into_view_if_needed(timeout=3000)
            add_log("Đã cuộn tới nút Publish", "info")
            time.sleep(0.3)
        except Exception as scroll_err:
            add_log(f"Không scroll được tới nút Publish: {scroll_err}", "warning")

        # Thử 3 cách click theo thứ tự ưu tiên
        clicked = False

        # 1) Playwright click (respect visibility/position)
        try:
            publish_btn.click(timeout=3000)
            clicked = True
            add_log("Clicked publish button", "info")
        except Exception as click_err:
            add_log(f"Click trực tiếp fail: {click_err}", "warning")

        # 2) Force click (bỏ qua overlay)
        if not clicked:
            try:
                publish_btn.click(force=True, timeout=2000)
                clicked = True
                add_log("Force-clicked publish button", "info")
            except Exception as force_err:
                add_log(f"Force click fail: {force_err}", "warning")

        # 3) JS click — fallback cuối
        if not clicked:
            try:
                page.evaluate(
                    "document.getElementById('publish')?.click() "
                    "|| document.querySelector('#publishing-action input[type=submit]')?.click()"
                )
                clicked = True
                add_log("JS-clicked publish button", "info")
            except Exception as js_err:
                add_log(f"JS click fail: {js_err}", "error")

        if not clicked:
            add_log("Không thể click nút Publish", "error")
            return False
        
        # Wait for page to reload - this is critical
        add_log("Đang lưu bài viết...", "info")
        time.sleep(4)
        
        # Multiple ways to check for success
        success_detected = False
        
        # Method 1: Check for success message
        try:
            success_selectors = [
                "#message.updated",
                ".notice-success", 
                "#message.notice",
                ".updated.notice",
                "div.updated"
            ]
            for selector in success_selectors:
                success_msg = page.locator(selector).first
                if success_msg.is_visible(timeout=2000):
                    success_detected = True
                    add_log("Success message detected", "info")
                    break
        except:
            pass
        
        # Method 2: Check URL for post.php (means we're on edit page of saved post)
        if not success_detected:
            current_url = page.url
            if "post.php" in current_url and "action=edit" in current_url:
                success_detected = True
                add_log("Post saved - now on edit page", "info")
        
        # Method 3: Check URL for message parameter
        if not success_detected:
            current_url = page.url
            if "message=" in current_url:
                success_detected = True
                add_log("Post saved - message in URL", "info")
        
        # Method 4: Check if View Post link exists
        if not success_detected:
            try:
                view_post = page.locator("a:has-text('View post'), a:has-text('Xem bài viết')").first
                if view_post.is_visible(timeout=2000):
                    success_detected = True
                    add_log("View post link found", "info")
            except:
                pass
        
        # Method 5: Check if post ID exists in URL (meaning post was created)
        if not success_detected:
            current_url = page.url
            if "post=" in current_url:
                success_detected = True
                add_log("Post ID found in URL", "info")
        
        if success_detected:
            action = "Scheduled" if is_schedule else "Published"
            add_log(f"{action} successfully!", "success")
            return True
        else:
            add_log("Could not confirm publish status, but continuing...", "warning")
            # Return True anyway since the click happened
            return True
        
    except Exception as e:
        add_log(f"Error publishing: {e}", "error")
        return False

def create_single_post(page: Page, index: int, topic: dict, content: str, start_date: datetime) -> bool:
    title = topic["title"]
    keyword = topic["keyword"]
    
    add_log(f"Đang tạo bài {index + 1}: {title}", "info")
    
    try:
        schedule_end = state.config.get("schedule_end_date", "")
        total_topics = len(state.topics)
        
        if schedule_end and total_topics > 0:
            try:
                end_date = datetime.strptime(schedule_end, "%Y-%m-%d")
                total_days = (end_date - start_date).days + 1
                if total_days < 1:
                    total_days = 1
            except ValueError:
                total_days = max(1, (total_topics + 1) // 2)
            
            posts_per_day_base = total_topics // total_days
            extra_posts = total_topics % total_days
            
            cumulative = 0
            days_offset = 0
            slot_in_day = 0
            posts_today = posts_per_day_base + (1 if 0 < extra_posts else 0)
            
            for d in range(total_days):
                ppd = posts_per_day_base + (1 if d < extra_posts else 0)
                if cumulative + ppd > index:
                    days_offset = d
                    slot_in_day = index - cumulative
                    posts_today = ppd
                    break
                cumulative += ppd
            
            posts_per_day = posts_today
        else:
            posts_per_day = state.config.get("posts_per_day", 2)
            days_offset = index // posts_per_day
            slot_in_day = index % posts_per_day
            posts_today = posts_per_day
        
        start_hour = 8
        end_hour = 21
        if posts_today == 1:
            hour = 9
        elif posts_today == 2:
            hour = [9, 15][slot_in_day]
        elif posts_today == 3:
            hour = [8, 13, 18][slot_in_day]
        elif posts_today == 4:
            hour = [8, 12, 16, 20][slot_in_day]
        else:
            interval = (end_hour - start_hour) / max(posts_today - 1, 1)
            hour = int(start_hour + (slot_in_day * interval))
        
        publish_date = start_date + timedelta(days=days_offset)
        publish_date = publish_date.replace(hour=hour, minute=0, second=0)
        
        now = datetime.now()
        has_schedule = bool(state.config.get("schedule_start_date", ""))
        is_schedule = publish_date > now
        
        add_log(f"Ngày đăng: {publish_date.strftime('%Y-%m-%d %H:%M')} (Ngày {days_offset + 1}, Slot {slot_in_day + 1}/{posts_today})", "info")
        
        if not state.is_running:
            return False
        if state.is_paused:
            if not wait_if_paused():
                return False
        
        if not navigate_to_new_post(page):
            return False
        
        if not set_post_title(page, title):
            return False
        
        if not state.is_running:
            return False
        if state.is_paused:
            if not wait_if_paused():
                return False
        
        if not set_post_content(page, content):
            add_log("Content may not have been added properly", "warning")

        auto_set_seo_keyword = bool(state.config.get("auto_set_seo_keyword", True))
        auto_insert_inline_images = bool(state.config.get("auto_insert_inline_images", True))
        auto_set_featured_image_cfg = bool(state.config.get("auto_set_featured_image", False))
        auto_select_category_cfg = bool(state.config.get("auto_select_category", True))
        auto_add_tags_cfg = bool(state.config.get("auto_add_tags", True))

        if auto_set_seo_keyword:
            set_rank_math_keyword(page, keyword)
        else:
            add_log("Skip SEO keyword (auto_set_seo_keyword = OFF)", "info")
        
        if not state.is_running:
            return False
        if state.is_paused:
            if not wait_if_paused():
                return False
        
        if auto_insert_inline_images:
            insert_images_after_h2(page, keyword, max_images=3)
        else:
            add_log("Skip inline images (auto_insert_inline_images = OFF)", "info")

        if auto_set_featured_image_cfg:
            set_featured_image(page, keyword)
        else:
            add_log("Skip featured image (auto_set_featured_image = OFF)", "info")

        if auto_select_category_cfg:
            select_first_category(page)
        else:
            add_log("Skip category selection (auto_select_category = OFF)", "info")

        tags = topic.get("tags", "")
        if auto_add_tags_cfg and tags:
            add_post_tags(page, tags)
        elif not auto_add_tags_cfg:
            add_log("Skip tags (auto_add_tags = OFF)", "info")
        
        if not state.is_running:
            return False
        if state.is_paused:
            if not wait_if_paused():
                return False
        
        if has_schedule:
            if not publish_or_schedule_post(page, True, publish_date):
                return False
        else:
            if not publish_or_schedule_post(page, is_schedule, publish_date if is_schedule else None):
                return False
        
        return True
        
    except Exception as e:
        add_log(f"Error creating post: {e}", "error")
        return False

def run_automation():
    if not PLAYWRIGHT_AVAILABLE:
        add_log("Playwright not available. Please install it first.", "error")
        state.is_running = False
        state.current_phase = "stopped"
        return
    
    state.is_running = True
    state.progress = 0
    state.successful_posts = 0
    state.failed_posts = 0
    state.logs = []
    state.retry_queue = []
    state.skip_post_indices = set()
    state.current_phase = "initializing"
    
    add_log("Starting WordPress Auto Poster...", "info")
    
    provider = state.config.get("ai_provider", "ollama")
    total_topics = len(state.topics)
    state.total_tasks = total_topics * 2
    state.generated_contents = []
    
    # For non-browser providers (ollama, gemini API), generate content first
    is_browser_provider = provider in ("gemini_web", "chatgpt_web")
    if not is_browser_provider:
        add_log(f"Phase 1: Generating content with {provider.upper()}...", "info")
        state.current_task = "Generating content..."
        state.current_phase = "generating_content"
        
        for i, topic in enumerate(state.topics):
            if not state.is_running:
                add_log("Stopped by user", "warning")
                return
            
            # Check if paused
            if not wait_if_paused():
                add_log("Stopped while paused", "warning")
                return
            
            state.current_task = f"Generating content {i+1}/{total_topics}..."
            validated_content = _generate_content_with_min_word_retries(
                provider,
                topic,
                i,
                source="initial",
            )
            state.generated_contents.append(validated_content)
            state.progress = ((i + 1) / state.total_tasks) * 100
            
            if i < len(state.topics) - 1 and state.is_running:
                time.sleep(state.config["delay_between_requests"])

        _process_content_retry_queue(provider, total_topics)
        
        successful_gen = sum(1 for c in state.generated_contents if c is not None)
        add_log(f"Generated {successful_gen}/{total_topics} articles", "success")
        
        if successful_gen == 0:
            add_log("No content generated. Stopping.", "error")
            state.is_running = False
            return
    else:
        provider_label = "Gemini Web Chat" if provider == "gemini_web" else "ChatGPT Web"
        add_log(f"{provider_label}: Content will be generated in browser...", "info")
    
    add_log("Phase 2: WordPress Automation...", "info")
    state.current_task = "Starting browser..."
    
    schedule_start = state.config.get("schedule_start_date", "")
    if schedule_start:
        try:
            start_date = datetime.strptime(schedule_start, "%Y-%m-%d")
            add_log(f"Schedule: {schedule_start} -> {state.config.get('schedule_end_date', '')}", "info")
        except ValueError:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    with sync_playwright() as p:
        add_log("Starting Brave browser...", "info")
        
        # Use persistent context to save login sessions
        import os
        user_data_dir = os.path.expanduser("~/.gemini/browser_data")
        os.makedirs(user_data_dir, exist_ok=True)
        
        brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        
        # Launch persistent context (saves cookies, login sessions, etc.)
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=brave_path,
            headless=state.config["headless_mode"],
            viewport={"width": 1920, "height": 1080},
            locale="vi-VN",
            slow_mo=100,
            ignore_https_errors=True,  # Một số WP site dùng cert self-signed / expired
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--ignore-certificate-errors",
                "--allow-insecure-localhost",
            ]
        )
        
        add_log("Brave browser started (login sessions saved)", "success")
        
        # Get existing page or create new one
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
        
        page.set_default_timeout(60000)
        
        try:
            # For browser-based providers (Gemini Web / ChatGPT Web),
            # generate content using the same context.
            if provider in ("gemini_web", "chatgpt_web"):
                provider_label = (
                    "Gemini Web Chat" if provider == "gemini_web" else "ChatGPT Web"
                )
                add_log(
                    f"Phase 1: Generating content with {provider_label}...",
                    "info",
                )
                state.current_phase = "generating_content"
                
                for i, topic in enumerate(state.topics):
                    if not state.is_running:
                        add_log("Stopped by user", "warning")
                        break
                    
                    # Check if paused
                    if not wait_if_paused():
                        add_log("Stopped while paused", "warning")
                        break
                    
                    state.current_task = (
                        f"Generating content {i+1}/{total_topics} via {provider_label}..."
                    )
                    state.current_title = topic["title"]
                    state.current_keyword = topic["keyword"]
                    
                    validated_content = _generate_content_with_min_word_retries(
                        provider,
                        topic,
                        i,
                        page=page,
                        source="initial",
                    )
                    state.generated_contents.append(validated_content)
                    
                    state.progress = ((i + 1) / state.total_tasks) * 100
                    
                    if i < len(state.topics) - 1 and state.is_running:
                        time.sleep(3)  # Short delay between requests

                _process_content_retry_queue(provider, total_topics, page=page)
                
                successful_gen = sum(1 for c in state.generated_contents if c is not None)
                add_log(
                    f"Generated {successful_gen}/{total_topics} articles via {provider_label}",
                    "success",
                )
                
                if successful_gen == 0:
                    add_log("No content generated. Stopping.", "error")
                    state.is_running = False
                    context.close()
                    return

                # Dọn session chat AI vừa dùng để tránh rối lịch sử hội thoại.
                try:
                    cleanup_provider_chat_session(page, provider)
                except Exception as e:
                    add_log(f"Không thể dọn session chat: {e}", "warning")

                # Tách tab: đóng tab AI đang chạy, mở tab mới sạch cho WordPress.
                # Service worker + beforeunload handler trên Gemini/ChatGPT có
                # thể gây ERR_ABORTED khi navigate sang domain khác.
                try:
                    add_log("Mở tab mới sạch cho WordPress...", "info")
                    new_page = context.new_page()
                    new_page.set_default_timeout(60000)
                    old_page = page
                    page = new_page
                    try:
                        old_page.close()
                    except Exception:
                        pass
                except Exception as e:
                    add_log(f"Không tạo được tab mới: {e} — tiếp tục với tab cũ", "warning")

            # Now login to WordPress
            if not login_to_wordpress(page):
                add_log("Failed to login. Exiting...", "error")
                state.is_running = False
                state.current_phase = "stopped"
                context.close()
                return
            
            state.current_phase = "creating_posts"
            for i, (topic, content) in enumerate(zip(state.topics, state.generated_contents)):
                if not state.is_running:
                    add_log("Stopped by user", "warning")
                    break
                
                # Check if paused
                if not wait_if_paused():
                    add_log("Stopped while paused", "warning")
                    break
                
                if i in state.skip_post_indices:
                    add_log(f"Skipping post {i+1} theo yêu cầu người dùng", "warning")
                    state.failed_posts += 1
                    continue

                if content is None:
                    add_log(f"Skipping post {i+1} - no content", "warning")
                    state.failed_posts += 1
                    continue
                
                state.current_task = f"Creating post {i+1}/{total_topics}..."
                
                max_retries = 2
                success = False
                for attempt in range(max_retries + 1):
                    try:
                        if attempt > 0:
                            add_log(f"Thử lại lần {attempt}/{max_retries} cho bài {i+1}...", "warning")
                            time.sleep(10)
                        
                        if not state.is_running:
                            break
                        
                        success = create_single_post(page, i, topic, content, start_date)
                        if success:
                            break
                        
                        if attempt < max_retries:
                            add_log(f"Bài {i+1} thất bại, sẽ thử lại...", "warning")
                        
                    except Exception as e:
                        add_log(f"Lỗi bài {i+1} (lần {attempt+1}/{max_retries+1}): {e}", "error")
                        if attempt < max_retries:
                            add_log(f"Sẽ thử lại sau 10 giây...", "warning")
                            time.sleep(10)
                
                if success:
                    state.successful_posts += 1
                else:
                    add_log(f"Bỏ qua bài {i+1} sau {max_retries + 1} lần thử", "error")
                    state.failed_posts += 1
                
                state.progress = ((total_topics + i + 1) / state.total_tasks) * 100
                
                if i < len(state.topics) - 1:
                    time.sleep(3)
            
            # Summary
            add_log(f"SUMMARY: {state.successful_posts} successful, {state.failed_posts} failed", "success")
            
        except Exception as e:
            add_log(f"Critical error: {e}", "error")
            state.current_phase = "error"
        finally:
            time.sleep(2)
            context.close()
    
    if state.is_running:
        state.current_task = "Completed!"
        state.progress = 100
        state.current_phase = "completed"
        add_log("WordPress Auto Poster completed!", "success")
    elif state.current_phase not in ("error", "stopped"):
        state.current_phase = "stopped"
    state.is_running = False

# FLASK ROUTES

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    # Return content_list without full content for performance
    content_list_summary = [
        {
            "post_index": c.get("post_index", 0),
            "title": c["title"],
            "keyword": c["keyword"],
            "word_count": c["word_count"],
            "status": c.get("status", "success"),
            "error_reason": c.get("error_reason", ""),
            "attempts": c.get("attempts", 1),
        }
        for c in state.content_list
    ]
    return jsonify({
        "is_running": state.is_running,
        "is_paused": state.is_paused,
        "pause_reason": state.pause_reason,
        "current_task": state.current_task,
        "progress": state.progress,
        "successful_posts": state.successful_posts,
        "failed_posts": state.failed_posts,
        "logs": state.logs,
        "gemini_available": GEMINI_AVAILABLE,
        "ollama_available": check_ollama(),
        "playwright_available": PLAYWRIGHT_AVAILABLE,
        "current_phase": state.current_phase,
        "retry_queue_count": len(state.retry_queue),
        "content_list": content_list_summary,
        "content_count": len(state.content_list)
    })

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        data = request.json
        if "content_min_valid_words" in data:
            try:
                data["content_min_valid_words"] = max(1, int(data["content_min_valid_words"]))
            except (TypeError, ValueError):
                data["content_min_valid_words"] = 1401
        if "content_auto_rerender_retries" in data:
            try:
                data["content_auto_rerender_retries"] = max(0, int(data["content_auto_rerender_retries"]))
            except (TypeError, ValueError):
                data["content_auto_rerender_retries"] = 2
        state.config.update(data)
        if save_app_config(state.config):
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Could not save config"}), 500
    return jsonify(state.config)

@app.route('/api/topics', methods=['GET', 'POST'])
def handle_topics():
    if request.method == 'POST':
        state.topics = request.json.get('topics', [])
        return jsonify({"success": True, "count": len(state.topics)})
    return jsonify(state.topics)

@app.route('/api/presets', methods=['GET'])
def list_presets():
    presets = load_site_presets()
    return jsonify({"success": True, "presets": list(presets.keys())})

@app.route('/api/presets/<name>', methods=['GET', 'PUT', 'DELETE'])
def manage_preset(name):
    presets = load_site_presets()
    
    if request.method == 'GET':
        if name in presets:
            return jsonify({"success": True, "data": presets[name]})
        return jsonify({"success": False, "message": "Preset not found"})
    
    elif request.method == 'PUT':
        data = request.json
        try:
            content_min_valid_words = max(1, int(data.get("content_min_valid_words", 1401)))
        except (TypeError, ValueError):
            content_min_valid_words = 1401
        presets[name] = {
            "wp_username": data.get("wp_username", ""),
            "wp_password": data.get("wp_password", ""),
            "wp_login_url": data.get("wp_login_url", ""),
            "wp_admin_url": data.get("wp_admin_url", ""),
            "category_name": data.get("category_name", "Tin tức"),
            "gemini_prompt": data.get("gemini_prompt", ""),
            "auto_set_seo_keyword": data.get("auto_set_seo_keyword", True),
            "auto_insert_inline_images": data.get("auto_insert_inline_images", True),
            "auto_set_featured_image": data.get("auto_set_featured_image", False),
            "auto_select_category": data.get("auto_select_category", True),
            "auto_add_tags": data.get("auto_add_tags", True),
            "content_min_valid_words": content_min_valid_words,
        }
        if save_site_presets(presets):
            return jsonify({"success": True, "message": f"Preset '{name}' saved"})
        return jsonify({"success": False, "message": "Could not save preset"})
    
    elif request.method == 'DELETE':
        if name in presets:
            del presets[name]
            if save_site_presets(presets):
                return jsonify({"success": True, "message": f"Preset '{name}' deleted"})
        return jsonify({"success": False, "message": "Preset not found"})

@app.route('/api/content/<int:index>')
def get_content(index):
    if 0 <= index < len(state.content_list):
        return jsonify({
            "success": True,
            "data": state.content_list[index]
        })
    return jsonify({"success": False, "message": "Content not found"})

@app.route('/api/content/<int:index>', methods=['PUT'])
def update_content(index):
    if 0 <= index < len(state.content_list):
        data = request.json
        if 'content' in data:
            new_content = data['content']
            # Recalculate word count
            text_only = re.sub(r'<[^>]*>', ' ', new_content)
            word_count = len(text_only.split())
            
            state.content_list[index]['content'] = new_content
            state.content_list[index]['word_count'] = word_count
            min_valid_words = _get_min_valid_words()
            if word_count < min_valid_words:
                state.content_list[index]['status'] = "failed"
                state.content_list[index]['error_reason'] = (
                    f"chỉ có {word_count}/{min_valid_words} từ (cập nhật thủ công)"
                )
            else:
                state.content_list[index]['status'] = "success"
                state.content_list[index]['error_reason'] = ""
            state.content_list[index]['attempts'] = state.content_list[index].get('attempts', 1)
            
            # Also update generated_contents for WordPress posting
            post_index = int(state.content_list[index].get("post_index", index))
            if 0 <= post_index < len(state.generated_contents):
                state.generated_contents[post_index] = new_content
            
            add_log(f"Content #{index + 1} đã được cập nhật ({word_count} từ)", "info")
            return jsonify({"success": True, "word_count": word_count})
    return jsonify({"success": False, "message": "Content not found"})

@app.route('/api/content/<int:index>', methods=['DELETE'])
def delete_content(index):
    if 0 <= index < len(state.content_list):
        row = state.content_list[index]
        deleted_title = row['title']
        post_index = int(row.get("post_index", index))
        del state.content_list[index]
        
        # Also remove from generated_contents/topics by real post index
        if 0 <= post_index < len(state.generated_contents):
            del state.generated_contents[post_index]
        
        if 0 <= post_index < len(state.topics):
            del state.topics[post_index]

        # Re-index content rows after deletion
        for item in state.content_list:
            item_post_index = int(item.get("post_index", -1))
            if item_post_index > post_index:
                item["post_index"] = item_post_index - 1
        
        add_log(f"Đã xóa: {deleted_title}", "warning")
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Content not found"})


def _handle_rerender_request(content_row_index: int, skip_post: bool):
    if not state.is_running:
        return {"success": False, "message": "Chỉ có thể rend lại khi automation đang chạy"}, 400

    if not (0 <= content_row_index < len(state.content_list)):
        return {"success": False, "message": "Content không tồn tại"}, 404

    row = state.content_list[content_row_index]
    post_index = int(row.get("post_index", content_row_index))
    phase = state.current_phase or ""

    if phase in ("generating_content", "retry_content_queue"):
        if _queue_content_rerender(post_index):
            add_log(
                f"Đã thêm vào hàng chờ rend lại content: bài {post_index + 1} - {row.get('title', '')}",
                "warning",
            )
            return {"success": True, "queued": True, "message": "Đã thêm vào hàng chờ rend lại"}, 200
        return {"success": True, "queued": False, "message": "Bài này đã có trong hàng chờ rend lại"}, 200

    if phase in ("creating_posts", "retry_post_queue"):
        if not skip_post:
            return {
                "success": False,
                "requires_confirmation": True,
                "message": "Đang trong quá trình đăng bài. Bạn có muốn bỏ qua bài này để không đăng không?"
            }, 409

        state.skip_post_indices.add(post_index)
        if 0 <= post_index < len(state.generated_contents):
            state.generated_contents[post_index] = None
        add_log(
            f"Đánh dấu bỏ qua đăng bài {post_index + 1} theo yêu cầu người dùng",
            "warning",
        )
        return {
            "success": True,
            "queued": False,
            "message": "Đã đánh dấu bỏ qua đăng bài này. Hãy rend lại ở pha tạo content."
        }, 200

    return {
        "success": False,
        "message": "Chỉ có thể thêm hàng chờ rend lại khi đang ở pha tạo content"
    }, 400


@app.route('/api/content/<int:index>/rerender', methods=['POST'])
def rerender_content(index):
    data = request.get_json(silent=True) or {}
    skip_post = bool(data.get("skip_post", False))
    payload, status_code = _handle_rerender_request(index, skip_post)
    return jsonify(payload), status_code


@app.route('/api/retry-queue', methods=['POST'])
def enqueue_retry_action():
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    try:
        post_index = int(data.get("post_index", 0)) - 1
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "post_index không hợp lệ"}), 400
    skip_post = bool(data.get("skip_post", False))

    if action != "content":
        return jsonify({"success": False, "message": "Hiện chỉ hỗ trợ retry content"}), 400
    if post_index < 0:
        return jsonify({"success": False, "message": "post_index không hợp lệ"}), 400

    row_index = _find_content_row_by_post_index(post_index)
    if row_index is None:
        return jsonify({"success": False, "message": "Không tìm thấy content tương ứng"}), 404
    payload, status_code = _handle_rerender_request(row_index, skip_post)
    return jsonify(payload), status_code

@app.route('/api/start', methods=['POST'])
def start_automation():
    if state.is_running:
        return jsonify({"success": False, "message": "Already running"})
    
    if not state.topics:
        return jsonify({"success": False, "message": "No topics configured"})
    
    provider = state.config.get("ai_provider", "ollama")
    
    if provider == "ollama":
        if not check_ollama():
            return jsonify({"success": False, "message": "Ollama is not running! Please start Ollama first (run: ollama serve)"})
    elif provider == "gemini":
        if not state.config.get("gemini_api_key"):
            return jsonify({"success": False, "message": "Gemini API key not configured"})
    
    if not state.config.get("wp_username"):
        return jsonify({"success": False, "message": "WordPress credentials not configured"})
    
    data = request.get_json() or {}
    state.config["schedule_start_date"] = data.get("schedule_start_date", "")
    state.config["schedule_end_date"] = data.get("schedule_end_date", "")
    
    state.content_list = []
    state.retry_queue = []
    state.skip_post_indices = set()
    state.current_phase = "initializing"
    state.is_paused = False
    state.pause_reason = ""
    
    thread = threading.Thread(target=run_automation)
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "message": "Started"})

@app.route('/api/stop', methods=['POST'])
def stop_automation():
    state.is_running = False
    state.is_paused = False
    state.pause_reason = ""
    state.current_phase = "stopped"
    add_log("Đã dừng bởi người dùng", "warning")
    return jsonify({"success": True})

@app.route('/api/pause', methods=['POST'])
def pause_automation():
    if not state.is_running:
        return jsonify({"success": False, "message": "Not running"})
    state.is_paused = True
    state.pause_reason = "Tạm dừng bởi người dùng"
    add_log("Đã tạm dừng", "warning")
    return jsonify({"success": True})

@app.route('/api/resume', methods=['POST'])
def resume_automation():
    if not state.is_running:
        return jsonify({"success": False, "message": "Not running"})
    state.is_paused = False
    state.pause_reason = ""
    add_log("Tiếp tục thực thi...", "success")
    return jsonify({"success": True})

@app.route('/api/ollama/start', methods=['POST'])
def start_ollama():
    try:
        import subprocess
        result = subprocess.run(
            ["brew", "services", "start", "ollama"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            # Wait a moment for service to start
            time.sleep(3)
            if check_ollama():
                return jsonify({"success": True, "message": "Ollama service started successfully"})
            else:
                return jsonify({"success": False, "message": "Ollama started but not responding yet. Please wait a moment."})
        else:
            return jsonify({"success": False, "message": f"Failed to start Ollama: {result.stderr}"})
            
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "message": "Timeout starting Ollama service"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/ollama/stop', methods=['POST'])
def stop_ollama():
    try:
        import subprocess
        result = subprocess.run(
            ["brew", "services", "stop", "ollama"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            time.sleep(2)
            return jsonify({"success": True, "message": "Ollama service stopped"})
        else:
            return jsonify({"success": False, "message": f"Failed to stop Ollama: {result.stderr}"})
            
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "message": "Timeout stopping Ollama service"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/ollama/status', methods=['GET'])
def ollama_status():
    is_running = check_ollama()
    return jsonify({
        "running": is_running,
        "status": "running" if is_running else "stopped"
    })

def clear_terminal_for_run():
    """Clear terminal once before printing the startup banner."""
    try:
        command = "cls" if os.name == "nt" else "clear"
        os.system(command)
    except Exception:
        pass

if __name__ == '__main__':
    # Create templates folder if not exists
    os.makedirs('templates', exist_ok=True)
    clear_terminal_for_run()
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     WordPress Auto Poster - Web Interface               ║
    ║     ─────────────────────────────────────────────────   ║
    ║     Open http://localhost:5001 in your browser          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    app.run(debug=True, port=5001, threaded=True)
