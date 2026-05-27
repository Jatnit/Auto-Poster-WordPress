import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

PRESETS_FILE = "wp_site_presets.json"
CONFIG_FILE = "app_config.json"

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
    # Số từ tối thiểu cho 1 response Gemini Web — nếu ngắn hơn sẽ tự động retry
    "gemini_min_words_full": 600,   # prompt tùy chỉnh (bài hoàn chỉnh)
    "gemini_min_words_part": 300,   # mỗi phần của 2-part generation
    "gemini_max_prompt_retries": 2, # số lần thử lại cho mỗi prompt
    # ChatGPT Web — share min_words_full/part với Gemini cho đơn giản
    "chatgpt_max_prompt_retries": 2,
    # Nội dung hợp lệ khi số từ > 1400
    "content_min_valid_words": 1401,
    # Số lần rend lại tự động khi content chưa đạt ngưỡng
    "content_auto_rerender_retries": 2,
}


class AppState:
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
        self.current_phase: str = ""
        self.retry_queue: List[Dict[str, Any]] = []
        self.skip_post_indices: set = set()

    def reset(self):
        self.is_running = True
        self.is_paused = False
        self.pause_reason = ""
        self.progress = 0
        self.successful_posts = 0
        self.failed_posts = 0
        self.logs = []
        self.generated_contents = []
        self.content_list = []
        self.current_content = ""
        self.current_title = ""
        self.current_keyword = ""
        self.used_featured_images = set()
        self.current_phase = ""
        self.retry_queue = []
        self.skip_post_indices = set()


state = AppState()


def load_app_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    merged = DEFAULT_CONFIG.copy()
                    merged.update(data)
                    return merged
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_app_config(config: Dict[str, Any]) -> bool:
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        add_log(f"Error saving config: {e}", "error")
        return False


# Load persisted config on startup
state.config = load_app_config()


def add_log(message: str, log_type: str = "info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    state.logs.append({"time": timestamp, "message": message, "type": log_type})
    print(f"[{timestamp}] [{log_type.upper()}] {message}")


def wait_if_paused() -> bool:
    import time
    while state.is_paused and state.is_running:
        time.sleep(0.5)
    return state.is_running


def load_site_presets() -> Dict[str, Any]:
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_site_presets(presets: Dict[str, Any]) -> bool:
    try:
        with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        add_log(f"Error saving presets: {e}", "error")
        return False
