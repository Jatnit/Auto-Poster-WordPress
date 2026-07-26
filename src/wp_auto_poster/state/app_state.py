"""Application runtime state and default configuration."""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Deque, Dict, List, Optional

#: Upper bound on retained log entries. The UI polls once per second and used
#: to receive the entire history each time, which grew without limit across a
#: long run. Older entries scroll out of the in-memory buffer.
LOG_HISTORY_LIMIT = 1000

DEFAULT_CONFIG = {
    "wp_username": "",
    "wp_password": "",
    "wp_login_url": "",
    "wp_admin_url": "",
    "category_name": "Tin tức",
    "gemini_api_key": "",
    "gemini_prompt": "",
    #: Injected into the built-in prompt templates as {company}. Per-site.
    "company_name": "THANG MÁY KENZO VIỆT NAM",
    #: Optional per-site override for the contact block appended to articles.
    #: Empty means "use the built-in block".
    "contact_section_html": "",
    "ollama_model": "llama3.2",
    "ai_provider": "gemini_web",
    "delay_between_requests": 3,
    "posts_per_day": 2,
    "headless_mode": False,
    "browser_slow_mo": 100,
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
    """Mutable in-memory state for a single automation process.

    The automation runs on a background thread while Flask request threads
    read and mutate the same object. ``lock``/``mutation()`` guard the shared
    lists (``topics``, ``generated_contents``, ``content_list``,
    ``retry_queue``, ``skip_post_indices``) whose indices must stay in sync.
    """

    def __init__(self):
        #: Reentrant so a locked section can call helpers that lock again.
        self.lock = threading.RLock()
        self.is_running: bool = False
        #: Set by /api/stop. Survives a concurrent reset() so a stop request
        #: racing with start cannot be silently swallowed.
        self.stop_requested: bool = False
        self.is_paused: bool = False
        self.pause_reason: str = ""
        self.current_task: str = ""
        self.progress: float = 0
        self.total_tasks: int = 0
        self.logs: Deque[Dict[str, Any]] = deque(maxlen=LOG_HISTORY_LIMIT)
        #: Monotonic id of the last appended log entry. Clients poll with
        #: ``?since=<log_seq>`` to receive only what they have not seen.
        self.log_seq: int = 0
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

    def mutation(self):
        """Guard a block that mutates index-linked shared collections."""
        return self.lock

    def snapshot_posting_plan(self):
        """Return a stable ``(topics, contents)`` pair for the posting loop.

        Taken once under the lock so that a concurrent delete cannot shift
        indices halfway through publishing.
        """
        with self.lock:
            return list(self.topics), list(self.generated_contents)

    def request_stop(self):
        with self.lock:
            self.stop_requested = True
            self.is_running = False
            self.is_paused = False
            self.pause_reason = ""
            self.current_phase = "stopped"

    def reset(self):
        self.stop_requested = False
        self.is_running = True
        self.is_paused = False
        self.pause_reason = ""
        self.current_task = ""
        self.progress = 0
        self.total_tasks = 0
        self.successful_posts = 0
        self.failed_posts = 0
        self.logs = deque(maxlen=LOG_HISTORY_LIMIT)
        self.log_seq = 0
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
