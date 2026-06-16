#!/usr/bin/env python3

import os
import re
import sys
import time
from datetime import datetime
from typing import Optional

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from config.settings import (
    state, add_log, wait_if_paused,
    load_site_presets, save_site_presets, save_app_config,
)
from config.prompts import clean_gemini_content
from wp_auto_poster.content.generation import (
    generate_content as _generate_content_via_provider_router,
)
from wp_auto_poster.content.validation import (
    count_words as _count_words_core,
    get_min_valid_words as _get_min_valid_words_core,
    validate_generated_content as _validate_generated_content_core,
)
from wp_auto_poster.content.retry_queue import (
    ContentRetryRuntime,
    find_content_row_by_post_index as _find_content_row_by_post_index_workflow,
    generate_content_with_min_word_retries as _generate_content_with_min_word_retries_workflow,
    process_content_retry_queue as _process_content_retry_queue_workflow,
    queue_content_rerender as _queue_content_rerender_workflow,
    upsert_content_row as _upsert_content_row_workflow,
)
from wp_auto_poster.automation.runner import (
    AutomationRuntime,
    run_automation as _run_automation_workflow,
)
from wp_auto_poster.web.app_factory import create_app
from wp_auto_poster.web.routes import RouteRuntime
from wp_auto_poster.wordpress.post_workflow import (
    PostWorkflowRuntime,
    create_single_post as _create_single_post_workflow,
)
from wp_auto_poster.wordpress.image_policy import (
    get_inline_image_random_pool_size as _get_inline_image_random_pool_size_core,
    get_inset_heading_candidates as _get_inset_heading_candidates_core,
    pick_evenly_spaced_indices as _pick_evenly_spaced_indices_core,
    pick_inset_evenly_spaced_indices as _pick_inset_evenly_spaced_indices_core,
    select_even_candidates as _select_even_candidates_core,
)
from wp_auto_poster.wordpress.inline_images import (
    InlineImageWorkflowConfig,
    InlineImageWorkflowRuntime,
    fallback_insert_image_no_h2 as _fallback_insert_image_no_h2_workflow,
    final_scan_and_repair_images as _final_scan_and_repair_images_workflow,
    insert_images_after_h2 as _insert_images_after_h2_workflow,
    select_random_image_for_content as _select_random_image_for_content_workflow,
    try_insert_image_at_h2 as _try_insert_image_at_h2_workflow,
)
from wp_auto_poster.wordpress.featured_image import (
    FeaturedImageRuntime,
    set_featured_image as _set_featured_image_workflow,
)
from wp_auto_poster.wordpress.editor import (
    EditorRuntime,
    navigate_to_new_post as _navigate_to_new_post_workflow,
    set_post_content as _set_post_content_workflow,
    set_post_title as _set_post_title_workflow,
    set_rank_math_keyword as _set_rank_math_keyword_workflow,
)
from wp_auto_poster.wordpress.taxonomy import (
    TaxonomyRuntime,
    add_post_tags as _add_post_tags_workflow,
    select_first_category as _select_first_category_workflow,
)
from wp_auto_poster.wordpress.publisher import (
    PublisherRuntime,
    publish_or_schedule_post as _publish_or_schedule_post_workflow,
)
from wp_auto_poster.wordpress.browser import (
    click_first_selector_resilient as _click_first_selector_resilient_core,
    click_first_visible as _click_first_visible_core,
    click_visible_by_text as _click_visible_by_text_core,
    close_all_modals as _close_all_modals_core,
    join_url as _join_url_core,
    safe_navigate as _safe_navigate_core,
    wait_for_network_idle as _wait_for_network_idle_core,
)
from wp_auto_poster.wordpress.media import (
    count_imgs_in_iframe as _count_imgs_in_iframe_core,
    find_other_unfilled_h2 as _find_other_unfilled_h2_core,
    find_unfilled_target_h2 as _find_unfilled_target_h2_core,
    finalize_inline_image_insert as _finalize_inline_image_insert_core,
    format_heading_targets as _format_heading_targets_core,
    get_contact_heading_index as _get_contact_heading_index_core,
    get_h2_elements_in_iframe as _get_h2_elements_in_iframe_core,
    get_heading_count_in_iframe as _get_heading_count_in_iframe_core,
    get_media_attachment_status as _get_media_attachment_status_core,
    get_safe_heading_count_for_images as _get_safe_heading_count_for_images_core,
    get_selected_media_image as _get_selected_media_image_core,
    img_is_after_h2 as _img_is_after_h2_core,
    insert_selected_image_after_h2_direct as _insert_selected_image_after_h2_direct_core,
    insert_selected_image_after_paragraph_direct as _insert_selected_image_after_paragraph_direct_core,
    rebalance_auto_images_to_targets as _rebalance_auto_images_to_targets_core,
    remove_non_auto_images_from_editor as _remove_non_auto_images_from_editor_core,
    remove_or_move_images_after_contact as _remove_or_move_images_after_contact_core,
    select_visible_media_attachment as _select_visible_media_attachment_core,
    switch_to_media_library_tab as _switch_to_media_library_tab_core,
    switch_to_visual_mode as _switch_to_visual_mode_core,
    sync_editor_after_direct_insert as _sync_editor_after_direct_insert_core,
    wait_for_img_count_increase as _wait_for_img_count_increase_core,
    wait_for_visible_media_attachments as _wait_for_visible_media_attachments_core,
)
from wp_auto_poster.providers.ollama import (
    generate_content_ollama as _generate_content_ollama,
    check_ollama,
)
from wp_auto_poster.providers.gemini_api import (
    generate_content_gemini as _generate_content_gemini,
    GEMINI_AVAILABLE
)
from wp_auto_poster.providers.gemini_web import (
    GeminiWebRuntime,
    configure_runtime as _configure_gemini_web_runtime,
    generate_content_gemini_web as _generate_content_gemini_web_workflow,
    send_prompt_to_gemini_web as _send_prompt_to_gemini_web_workflow,
)
from wp_auto_poster.providers.chatgpt_web import (
    ChatGPTWebRuntime,
    configure_runtime as _configure_chatgpt_web_runtime,
    generate_content_chatgpt_web as _generate_content_chatgpt_web_workflow,
    send_prompt_to_chatgpt_web as _send_prompt_to_chatgpt_web_workflow,
)
from wp_auto_poster.providers.session_cleanup import (
    cleanup_provider_chat_session as _cleanup_provider_chat_session_workflow,
    delete_current_chatgpt_session as _delete_current_chatgpt_session_workflow,
    delete_current_gemini_session as _delete_current_gemini_session_workflow,
)

try:
    from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# CONTENT RETRY / CONTENT LIST COMPATIBILITY


def _get_min_valid_words() -> int:
    return _get_min_valid_words_core(state.config)


def _count_words(content: Optional[str]) -> int:
    return _count_words_core(content)


def _content_retry_runtime() -> ContentRetryRuntime:
    return ContentRetryRuntime(
        state=state,
        add_log=add_log,
        wait_if_paused=wait_if_paused,
        generate_content=generate_content,
        clean_content=clean_gemini_content,
    )


def _find_content_row_by_post_index(post_index: int) -> Optional[int]:
    return _find_content_row_by_post_index_workflow(
        _content_retry_runtime(),
        post_index,
    )


def _upsert_content_row(
    post_index: int,
    topic: dict,
    content: str,
    status: str = "success",
    error_reason: str = "",
    attempts: int = 1,
) -> int:
    return _upsert_content_row_workflow(
        _content_retry_runtime(),
        post_index,
        topic,
        content,
        status=status,
        error_reason=error_reason,
        attempts=attempts,
    )


def _queue_content_rerender(post_index: int) -> bool:
    return _queue_content_rerender_workflow(_content_retry_runtime(), post_index)


def _validate_generated_content(content: Optional[str]) -> tuple:
    return _validate_generated_content_core(
        content,
        min_valid_words=_get_min_valid_words(),
        cleaner=clean_gemini_content,
    )


def _generate_content_with_min_word_retries(
    provider: str,
    topic: dict,
    post_index: int,
    page=None,
    source: str = "initial",
) -> Optional[str]:
    return _generate_content_with_min_word_retries_workflow(
        _content_retry_runtime(),
        provider,
        topic,
        post_index,
        page=page,
        source=source,
    )


def _process_content_retry_queue(provider: str, total_topics: int, page=None):
    return _process_content_retry_queue_workflow(
        _content_retry_runtime(),
        provider,
        total_topics,
        page=page,
    )


# BROWSER AI PROVIDERS


def _gemini_web_runtime() -> GeminiWebRuntime:
    return GeminiWebRuntime(
        state=state,
        add_log=add_log,
        wait_if_paused=wait_if_paused,
    )


def _chatgpt_web_runtime() -> ChatGPTWebRuntime:
    return ChatGPTWebRuntime(
        state=state,
        add_log=add_log,
        wait_if_paused=wait_if_paused,
    )


def _configure_browser_provider_runtimes() -> None:
    _configure_gemini_web_runtime(_gemini_web_runtime())
    _configure_chatgpt_web_runtime(_chatgpt_web_runtime())


def send_prompt_to_gemini_web(
    page,
    prompt: str,
    min_words: int = 300,
    max_retries: Optional[int] = None,
) -> Optional[str]:
    _configure_gemini_web_runtime(_gemini_web_runtime())
    return _send_prompt_to_gemini_web_workflow(page, prompt, min_words, max_retries)


def generate_content_gemini_web(page, title: str, keyword: str) -> Optional[str]:
    _configure_gemini_web_runtime(_gemini_web_runtime())
    return _generate_content_gemini_web_workflow(page, title, keyword)


def send_prompt_to_chatgpt_web(
    page,
    prompt: str,
    min_words: int = 300,
    max_retries: Optional[int] = None,
) -> Optional[str]:
    _configure_chatgpt_web_runtime(_chatgpt_web_runtime())
    return _send_prompt_to_chatgpt_web_workflow(page, prompt, min_words, max_retries)


def generate_content_chatgpt_web(page, title: str, keyword: str) -> Optional[str]:
    _configure_chatgpt_web_runtime(_chatgpt_web_runtime())
    return _generate_content_chatgpt_web_workflow(page, title, keyword)

def generate_content(
    title: str,
    keyword: str,
    page=None,
    provider_override: Optional[str] = None,
) -> Optional[str]:
    return _generate_content_via_provider_router(
        provider_override or state.config.get("ai_provider", "ollama"),
        title,
        keyword,
        state.config,
        add_log,
        page=page,
        gemini_web_func=generate_content_gemini_web,
        chatgpt_web_func=generate_content_chatgpt_web,
        ollama_check_func=check_ollama,
        ollama_func=_generate_content_ollama,
        gemini_api_func=_generate_content_gemini,
    )


def _click_first_visible(page, selectors, timeout: int = 1500, require_enabled: bool = False) -> bool:
    """Click selector đầu tiên đang visible. Trả về True nếu click thành công."""
    return _click_first_visible_core(page, selectors, timeout, require_enabled)


def _click_visible_by_text(page, labels) -> bool:
    """Best-effort click phần tử visible có text chứa một trong các label."""
    return _click_visible_by_text_core(page, labels)


def _delete_current_gemini_session(page) -> bool:
    """Xóa session Gemini hiện tại (best-effort)."""
    return _delete_current_gemini_session_workflow(page, add_log)


def _delete_current_chatgpt_session(page) -> bool:
    """Xóa session ChatGPT hiện tại (best-effort)."""
    return _delete_current_chatgpt_session_workflow(page, add_log)


def cleanup_provider_chat_session(page, provider: str) -> bool:
    """Xóa session chat hiện tại của provider sau khi render xong nội dung."""
    return _cleanup_provider_chat_session_workflow(page, provider, add_log)

# WORDPRESS AUTOMATION
 
def wait_for_network_idle(page: Page, timeout: int = 10000):
    return _wait_for_network_idle_core(page, timeout)

def _join_url(base: str, path: str) -> str:
    """Nối base URL và path, xử lý trailing slash dư."""
    return _join_url_core(base, path)


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
    return _safe_navigate_core(
        page,
        url,
        log_func=add_log,
        timeout=timeout,
        max_retries=max_retries,
    )


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

def _editor_runtime() -> EditorRuntime:
    return EditorRuntime(config=state.config, log_func=add_log)


def navigate_to_new_post(page: Page) -> bool:
    return _navigate_to_new_post_workflow(page, _editor_runtime())


def set_post_title(page: Page, title: str) -> bool:
    return _set_post_title_workflow(page, title, _editor_runtime())


def set_post_content(page: Page, content: str) -> bool:
    return _set_post_content_workflow(page, content, _editor_runtime())


def set_rank_math_keyword(page: Page, keyword: str) -> bool:
    return _set_rank_math_keyword_workflow(page, keyword, _editor_runtime())

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
INLINE_IMAGE_RANDOM_POOL_MIN_SIZE = 50
INLINE_IMAGE_RANDOM_POOL_BUFFER = 10
INLINE_IMAGE_RANDOM_POOL_MAX_SIZE = 500
INLINE_IMAGE_HEADING_SELECTOR = "h2, h3"


def _inline_image_runtime() -> InlineImageWorkflowRuntime:
    return InlineImageWorkflowRuntime(
        state=state,
        log_func=add_log,
        wait_if_paused=wait_if_paused,
        config=InlineImageWorkflowConfig(
            max_retry_rounds=MAX_RETRY_ROUNDS,
            max_slot_retries=MAX_SLOT_RETRIES,
            media_lib_poll_timeout=MEDIA_LIB_POLL_TIMEOUT,
            media_lib_poll_interval=MEDIA_LIB_POLL_INTERVAL,
            media_modal_timeout=MEDIA_MODAL_TIMEOUT,
            add_media_btn_timeout=ADD_MEDIA_BTN_TIMEOUT,
            media_click_timeout=MEDIA_CLICK_TIMEOUT,
            heading_selector=INLINE_IMAGE_HEADING_SELECTOR,
            random_pool_min_size=INLINE_IMAGE_RANDOM_POOL_MIN_SIZE,
            random_pool_buffer=INLINE_IMAGE_RANDOM_POOL_BUFFER,
            random_pool_max_size=INLINE_IMAGE_RANDOM_POOL_MAX_SIZE,
        ),
    )


def _get_inline_image_random_pool_size(images_per_post: int = 3) -> int:
    """Pool đủ rộng để random không trùng trên toàn phiên đăng."""
    return _get_inline_image_random_pool_size_core(
        topic_count=len(getattr(state, "topics", [])),
        images_per_post=images_per_post,
        min_pool=INLINE_IMAGE_RANDOM_POOL_MIN_SIZE,
        buffer=INLINE_IMAGE_RANDOM_POOL_BUFFER,
        max_pool=INLINE_IMAGE_RANDOM_POOL_MAX_SIZE,
    )


def _count_imgs_in_iframe(page: Page) -> int:
    """Đếm số ảnh hợp lệ do app tự chèn trong TinyMCE iframe (#content_ifr)."""
    return _count_imgs_in_iframe_core(page)

def _get_h2_elements_in_iframe(page: Page) -> list:
    """Re-fetch heading elements an toàn từ TinyMCE iframe."""
    return _get_h2_elements_in_iframe_core(page, INLINE_IMAGE_HEADING_SELECTOR)

def _img_is_after_h2(page: Page, h2_index: int) -> bool:
    """Verify ảnh auto hợp lệ nằm dưới H2 thứ h2_index qua DOM sibling check."""
    return _img_is_after_h2_core(page, h2_index)

def _get_heading_count_in_iframe(page: Page) -> int:
    return _get_heading_count_in_iframe_core(page)

def _get_contact_heading_index(page: Page) -> Optional[int]:
    return _get_contact_heading_index_core(page)

def _get_safe_heading_count_for_images(page: Page) -> int:
    return _get_safe_heading_count_for_images_core(page)

def _pick_evenly_spaced_indices(total: int, slots: int) -> list:
    return _pick_evenly_spaced_indices_core(total, slots)


def _get_inset_heading_candidates(total: int) -> list:
    """Candidate H2/H3 indices for inline images, avoiding article edges.

    Khi có từ 3 heading an toàn trở lên, bỏ qua heading đầu và cuối để ảnh
    không nằm quá sát mở bài hoặc sát phần cuối/liên hệ. Nếu bài quá ít heading
    thì dùng những heading hiện có để flow vẫn có cơ hội chèn ảnh.
    """
    return _get_inset_heading_candidates_core(total)


def _pick_inset_evenly_spaced_indices(total: int, slots: int) -> list:
    return _pick_inset_evenly_spaced_indices_core(total, slots)


def _select_even_candidates(indices: list, limit: int) -> list:
    return _select_even_candidates_core(indices, limit)


def _format_heading_targets(indices: list) -> str:
    return _format_heading_targets_core(indices)

def _switch_to_visual_mode(page: Page) -> None:
    """Click `#content-tmce` để chuyển TinyMCE sang Visual mode."""
    return _switch_to_visual_mode_core(page, log_func=add_log)

def _click_first_selector_resilient(
    page: Page,
    selectors: list,
    label: str,
    timeout_ms: int = MEDIA_CLICK_TIMEOUT,
) -> bool:
    """Click nhanh bằng locator, rồi fallback JS để tránh kẹt vì viewport/overlay."""
    return _click_first_selector_resilient_core(
        page,
        selectors,
        label,
        log_func=add_log,
        timeout_ms=timeout_ms,
    )


def _select_visible_media_attachment(page: Page, label: str) -> bool:
    """Select ảnh từ pool Media Library rộng hơn và tránh trùng trong phiên chạy."""
    if not hasattr(state, "used_inline_images"):
        state.used_inline_images = set()
    if not hasattr(state, "used_inline_image_count"):
        state.used_inline_image_count = 0

    ok, selected_count = _select_visible_media_attachment_core(
        page,
        label,
        state.used_inline_images,
        state.used_inline_image_count,
        _get_inline_image_random_pool_size(),
        log_func=add_log,
    )
    state.used_inline_image_count = selected_count
    return ok

def _get_media_attachment_status(page: Page) -> dict:
    return _get_media_attachment_status_core(page)

def _get_selected_media_image(page: Page, fallback_alt: str) -> Optional[dict]:
    return _get_selected_media_image_core(page, fallback_alt, log_func=add_log)

def _sync_editor_after_direct_insert(page: Page) -> None:
    return _sync_editor_after_direct_insert_core(page)

def _remove_non_auto_images_from_editor(page: Page, reason: str = "scan") -> int:
    return _remove_non_auto_images_from_editor_core(page, reason, log_func=add_log)

def _insert_selected_image_after_h2_direct(
    page: Page,
    h2_index: int,
    image: dict,
    keyword: str,
) -> bool:
    return _insert_selected_image_after_h2_direct_core(
        page,
        h2_index,
        image,
        keyword,
        log_func=add_log,
    )

def _insert_selected_image_after_paragraph_direct(
    page: Page,
    slot_hint: str,
    image: dict,
    keyword: str,
) -> bool:
    return _insert_selected_image_after_paragraph_direct_core(
        page,
        slot_hint,
        image,
        keyword,
        log_func=add_log,
    )

def _switch_to_media_library_tab(page: Page, label: str) -> None:
    return _switch_to_media_library_tab_core(page, label, log_func=add_log)

def _wait_for_visible_media_attachments(
    page: Page,
    label: str,
    timeout_ms: int = MEDIA_LIB_POLL_TIMEOUT,
) -> bool:
    return _wait_for_visible_media_attachments_core(
        page,
        label,
        timeout_ms,
        MEDIA_LIB_POLL_INTERVAL,
        log_func=add_log,
    )

def _wait_for_img_count_increase(
    page: Page,
    count_before: int,
    timeout_ms: int = INSERT_VERIFY_TIMEOUT,
) -> int:
    return _wait_for_img_count_increase_core(
        page,
        count_before,
        timeout_ms,
        INSERT_VERIFY_INTERVAL,
    )

def _finalize(page: Page, max_images: int, reason: str) -> bool:
    """Đóng modal, cleanup và log final count theo DOM."""
    return _finalize_inline_image_insert_core(
        page,
        max_images,
        reason,
        log_func=add_log,
    )

def _try_insert_image_at_h2(
    page: Page,
    h2_index: int,
    keyword: str,
    max_images: Optional[int] = None,
) -> bool:
    return _try_insert_image_at_h2_workflow(
        page,
        h2_index,
        keyword,
        _inline_image_runtime(),
        max_images=max_images,
    )

def _find_unfilled_target_h2(page: Page, target_indices: list) -> list:
    return _find_unfilled_target_h2_core(
        page,
        target_indices,
        INLINE_IMAGE_HEADING_SELECTOR,
    )

def _find_other_unfilled_h2(page: Page, exclude_indices: set) -> list:
    return _find_other_unfilled_h2_core(page, exclude_indices)

def _fallback_insert_image_no_h2(
    page: Page,
    keyword: str,
    slot_hint: str,
    max_images: Optional[int] = None,
) -> bool:
    return _fallback_insert_image_no_h2_workflow(
        page,
        keyword,
        slot_hint,
        _inline_image_runtime(),
        max_images=max_images,
    )

def _rebalance_auto_images_to_targets(page: Page, target_indices: list) -> int:
    return _rebalance_auto_images_to_targets_core(page, target_indices, log_func=add_log)

def _remove_or_move_images_after_contact(page: Page, target_indices: list) -> int:
    return _remove_or_move_images_after_contact_core(page, target_indices, log_func=add_log)

def _final_scan_and_repair_images(
    page: Page,
    keyword: str,
    max_images: int,
    target_h2_indices: list,
) -> bool:
    return _final_scan_and_repair_images_workflow(
        page,
        keyword,
        max_images,
        target_h2_indices,
        _inline_image_runtime(),
    )

def insert_images_after_h2(page: Page, keyword: str, max_images: int = 3) -> bool:
    return _insert_images_after_h2_workflow(
        page,
        keyword,
        _inline_image_runtime(),
        max_images=max_images,
    )

def close_all_modals(page: Page, max_attempts: int = 2):
    return _close_all_modals_core(page, max_attempts)

# Alias for compatibility
force_close_all_modals = close_all_modals

def select_random_image_for_content(page: Page, alt_text: str) -> bool:
    return _select_random_image_for_content_workflow(
        page,
        alt_text,
        _inline_image_runtime(),
    )

def _taxonomy_runtime() -> TaxonomyRuntime:
    return TaxonomyRuntime(config=state.config, log_func=add_log)


def select_first_category(page: Page) -> bool:
    return _select_first_category_workflow(page, _taxonomy_runtime())


def add_post_tags(page: Page, tags: str) -> bool:
    return _add_post_tags_workflow(page, tags, _taxonomy_runtime())

def _featured_image_runtime() -> FeaturedImageRuntime:
    return FeaturedImageRuntime(state=state, log_func=add_log)


def set_featured_image(page: Page, keyword: str) -> bool:
    return _set_featured_image_workflow(page, keyword, _featured_image_runtime())

def _publisher_runtime() -> PublisherRuntime:
    return PublisherRuntime(log_func=add_log)


def publish_or_schedule_post(page: Page, is_schedule: bool, publish_date: datetime = None) -> bool:
    return _publish_or_schedule_post_workflow(
        page,
        is_schedule,
        publish_date,
        _publisher_runtime(),
    )

def _post_workflow_runtime() -> PostWorkflowRuntime:
    return PostWorkflowRuntime(
        state=state,
        log_func=add_log,
        wait_if_paused=wait_if_paused,
        navigate_to_new_post=navigate_to_new_post,
        set_post_title=set_post_title,
        set_post_content=set_post_content,
        set_rank_math_keyword=set_rank_math_keyword,
        insert_images_after_h2=insert_images_after_h2,
        set_featured_image=set_featured_image,
        select_first_category=select_first_category,
        add_post_tags=add_post_tags,
        publish_or_schedule_post=publish_or_schedule_post,
    )


def create_single_post(page: Page, index: int, topic: dict, content: str, start_date: datetime) -> bool:
    return _create_single_post_workflow(
        page,
        index,
        topic,
        content,
        start_date,
        _post_workflow_runtime(),
    )

def _automation_runtime() -> AutomationRuntime:
    return AutomationRuntime(
        state=state,
        add_log=add_log,
        wait_if_paused=wait_if_paused,
        playwright_available=PLAYWRIGHT_AVAILABLE,
        sync_playwright=sync_playwright,
        get_inline_image_random_pool_size=_get_inline_image_random_pool_size,
        generate_content_with_min_word_retries=_generate_content_with_min_word_retries,
        process_content_retry_queue=_process_content_retry_queue,
        cleanup_provider_chat_session=cleanup_provider_chat_session,
        login_to_wordpress=login_to_wordpress,
        create_single_post=create_single_post,
    )


def run_automation():
    return _run_automation_workflow(_automation_runtime())

# FLASK ROUTES

def _routes_runtime() -> RouteRuntime:
    return RouteRuntime(
        state=state,
        add_log=add_log,
        load_site_presets=load_site_presets,
        save_site_presets=save_site_presets,
        save_app_config=save_app_config,
        check_ollama=check_ollama,
        run_automation=run_automation,
        get_min_valid_words=_get_min_valid_words,
        find_content_row_by_post_index=_find_content_row_by_post_index,
        queue_content_rerender=_queue_content_rerender,
        gemini_available=GEMINI_AVAILABLE,
        playwright_available=PLAYWRIGHT_AVAILABLE,
    )


app = create_app(
    _routes_runtime,
    import_name=__name__,
    template_folder=os.path.join(ROOT_DIR, "templates"),
    static_folder=os.path.join(ROOT_DIR, "static"),
)

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
