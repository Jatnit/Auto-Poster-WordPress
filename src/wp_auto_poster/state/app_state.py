"""Application runtime state and default configuration."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

DEFAULT_CONFIG = {
    "wp_username": "",
    "wp_password": "",
    "wp_login_url": "",
    "wp_admin_url": "",
    "category_name": "Tin tức",
    "gemini_api_key": "",
    "gemini_prompt": "",
    "ollama_model": "llama3.2",
    "ai_provider": "gemini_web",
    "delay_between_requests": 3,
    "posts_per_day": 2,
    "auto_set_seo_keyword": True,
    "auto_insert_inline_images": True,
    "auto_set_featured_image": False,
    "auto_select_category": True,
    "auto_add_tags": True,
    "gemini_min_words_full": 600,
    "gemini_min_words_part": 300,
    "gemini_max_prompt_retries": 2,
    "chatgpt_max_prompt_retries": 2,
    "content_min_valid_words": 1401,
    "content_auto_rerender_retries": 2,
}


class AppState:
    """Mutable in-memory state for a single automation process."""

    def __init__(self):
        self.is_running: bool = False
        self.is_paused: bool = False
        self.pause_reason: str = ""
        self.current_task: str = ""
        self.progress: float = 0
        self.total_tasks: int = 0
        self.logs: List[Dict[str, str]] = []
        self.config: Dict[str, Any] = DEFAULT_CONFIG.copy()
        self.topics: List[Dict[str, str]] = []
        self.successful_posts: int = 0
        self.failed_posts: int = 0
        self.generated_contents: List[Optional[str]] = []
        self.current_content: str = ""
        self.current_title: str = ""
        self.current_keyword: str = ""
        self.content_list: List[Dict[str, Any]] = []
        self.used_featured_images: set = set()
        self.used_inline_images: set = set()
        self.used_inline_image_count: int = 0
        self.current_phase: str = ""
        self.retry_queue: List[Dict[str, Any]] = []
        self.skip_post_indices: set = set()

    def reset(self):
        self.is_running = True
        self.is_paused = False
        self.pause_reason = ""
        self.current_task = ""
        self.progress = 0
        self.total_tasks = 0
        self.successful_posts = 0
        self.failed_posts = 0
        self.logs = []
        self.generated_contents = []
        self.content_list = []
        self.current_content = ""
        self.current_title = ""
        self.current_keyword = ""
        self.used_featured_images = set()
        self.used_inline_images = set()
        self.used_inline_image_count = 0
        self.current_phase = "initializing"
        self.retry_queue = []
        self.skip_post_indices = set()
