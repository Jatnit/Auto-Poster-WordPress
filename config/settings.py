import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

TIMEOUT_SHORT = 1000
TIMEOUT_MEDIUM = 3000
TIMEOUT_LONG = 5000
TIMEOUT_NETWORK = 10000
TIMEOUT_LOGIN = 60000

SLEEP_SHORT = 0.5
SLEEP_MEDIUM = 1
SLEEP_LONG = 2
SLEEP_EXTRA_LONG = 5

PRESETS_FILE = "wp_site_presets.json"
BROWSER_DATA_DIR = os.path.expanduser("~/.wp_autoposter_browser")

DEFAULT_CONFIG = {
    "wp_username": "",
    "wp_password": "",
    "wp_login_url": "",
    "wp_admin_url": "",
    "gemini_api_key": "",
    "gemini_prompt": "",
    "ollama_model": "llama3.2",
    "ai_provider": "gemini_web",
    "delay_between_requests": 3,
    "posts_per_day": 2,
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


state = AppState()


def add_log(message: str, log_type: str = "info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    state.logs.append({"time": timestamp, "message": message, "type": log_type})
    print(f"[{timestamp}] [{log_type.upper()}] {message}")


def wait_if_paused() -> bool:
    import time
    while state.is_paused and state.is_running:
        time.sleep(0.5)
    return state.is_running


def pause_on_error(error_msg: str):
    state.is_paused = True
    state.pause_reason = error_msg
    add_log(f"PAUSED: {error_msg}", "warning")
    add_log("Fix the issue and click 'Resume' to continue", "info")


def load_site_presets() -> Dict[str, Any]:
    if os.path.exists(PRESETS_FILE):
        try:
            with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_site_presets(presets: Dict[str, Any]):
    try:
        with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(presets, f, indent=2, ensure_ascii=False)
    except Exception as e:
        add_log(f"Error saving presets: {e}", "error")
