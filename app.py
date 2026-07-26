#!/usr/bin/env python3

import os
import sys
from datetime import datetime
from typing import Optional

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT_DIR, "src")
# Single bootstrap so `python app.py` works without `pip install -e .` first.
# Library modules must NOT do this — they rely on the package being importable.
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from config.settings import (  # noqa: E402
    state, add_log, wait_if_paused,
    load_site_presets, save_site_presets, save_app_config,
)
from wp_auto_poster.content.prompts import clean_gemini_content  # noqa: E402
from wp_auto_poster.content.generation import (
    generate_content as _generate_content_via_provider_router,
)
from wp_auto_poster.content.validation import (
    get_min_valid_words as _get_min_valid_words_core,
)
from wp_auto_poster.content.retry_queue import (
    ContentRetryRuntime,
    find_content_row_by_post_index as _find_content_row_by_post_index_workflow,
    generate_content_with_min_word_retries as _generate_content_with_min_word_retries_workflow,
    process_content_retry_queue as _process_content_retry_queue_workflow,
    queue_content_rerender as _queue_content_rerender_workflow,
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
)
from wp_auto_poster.wordpress.inline_images import (
    InlineImageWorkflowConfig,
    InlineImageWorkflowRuntime,
    insert_images_after_h2 as _insert_images_after_h2_workflow,
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
    close_all_modals as _close_all_modals_core,
    safe_navigate as _safe_navigate_core,
    wait_for_network_idle as _wait_for_network_idle_core,
)
from wp_auto_poster.wordpress.auth import (
    AuthRuntime,
    login_to_wordpress as _login_to_wordpress_workflow,
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
)
from wp_auto_poster.providers.chatgpt_web import (
    ChatGPTWebRuntime,
    configure_runtime as _configure_chatgpt_web_runtime,
    generate_content_chatgpt_web as _generate_content_chatgpt_web_workflow,
)
from wp_auto_poster.providers.session_cleanup import (
    cleanup_provider_chat_session as _cleanup_provider_chat_session_workflow,
)

try:
    from playwright.sync_api import Page, sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# CONTENT RETRY / CONTENT LIST COMPATIBILITY


def _get_min_valid_words() -> int:
    return _get_min_valid_words_core(state.config)


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


def _queue_content_rerender(post_index: int) -> bool:
    return _queue_content_rerender_workflow(_content_retry_runtime(), post_index)


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


def generate_content_gemini_web(page, title: str, keyword: str) -> Optional[str]:
    _configure_gemini_web_runtime(_gemini_web_runtime())
    return _generate_content_gemini_web_workflow(page, title, keyword)


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


def cleanup_provider_chat_session(page, provider: str) -> bool:
    """Xóa session chat hiện tại của provider sau khi render xong nội dung."""
    return _cleanup_provider_chat_session_workflow(page, provider, add_log)

# WORDPRESS AUTOMATION

def wait_for_network_idle(page: Page, timeout: int = 10000):
    return _wait_for_network_idle_core(page, timeout)


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


def _auth_runtime() -> AuthRuntime:
    return AuthRuntime(config=state.config, log_func=add_log)


def login_to_wordpress(page: Page) -> bool:
    return _login_to_wordpress_workflow(page, _auth_runtime())

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

# Image-insertion tuning lives with the workflow that consumes it, in
# wp_auto_poster.wordpress.inline_images.InlineImageWorkflowConfig.
INLINE_IMAGE_CONFIG = InlineImageWorkflowConfig()


def _inline_image_runtime() -> InlineImageWorkflowRuntime:
    return InlineImageWorkflowRuntime(
        state=state,
        log_func=add_log,
        wait_if_paused=wait_if_paused,
        config=INLINE_IMAGE_CONFIG,
    )


def _get_inline_image_random_pool_size(images_per_post: int = 3) -> int:
    """Pool đủ rộng để random không trùng trên toàn phiên đăng."""
    return _get_inline_image_random_pool_size_core(
        topic_count=len(getattr(state, "topics", [])),
        images_per_post=images_per_post,
        min_pool=INLINE_IMAGE_CONFIG.random_pool_min_size,
        buffer=INLINE_IMAGE_CONFIG.random_pool_buffer,
        max_pool=INLINE_IMAGE_CONFIG.random_pool_max_size,
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


HOST = os.getenv("WP_HOST", "127.0.0.1")
PORT = int(os.getenv("WP_PORT", "5001"))
DEBUG = os.getenv("WP_DEBUG") == "1"

app = create_app(
    _routes_runtime,
    import_name=__name__,
    template_folder=os.path.join(ROOT_DIR, "templates"),
    static_folder=os.path.join(ROOT_DIR, "static"),
    port=PORT,
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

    print(f"""
    ╔══════════════════════════════════════════════════════════╗
    ║     WordPress Auto Poster - Web Interface               ║
    ║     ─────────────────────────────────────────────────   ║
    ║     Open http://{HOST}:{PORT} in your browser
    ╚══════════════════════════════════════════════════════════╝
    """)

    # The reloader is disabled unconditionally: it restarts the process on any
    # file save, which would kill an automation run mid-post.
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False, threaded=True)
