"""Backward-compatible settings facade for the refactored state package."""

from typing import Any, Dict

from wp_auto_poster.state.app_state import AppState, DEFAULT_CONFIG
from wp_auto_poster.state.config_store import (
    load_app_config as _load_app_config,
    save_app_config as _save_app_config,
)
from wp_auto_poster.state.presets import (
    load_site_presets as _load_site_presets,
    save_site_presets as _save_site_presets,
)
from wp_auto_poster.utils.logging import (
    add_state_log as _add_state_log,
    wait_if_paused as _wait_if_paused,
)

PRESETS_FILE = "wp_site_presets.json"
CONFIG_FILE = "app_config.json"

state = AppState()


def load_app_config() -> Dict[str, Any]:
    return _load_app_config(CONFIG_FILE, DEFAULT_CONFIG)


def save_app_config(config: Dict[str, Any]) -> bool:
    return _save_app_config(config, CONFIG_FILE, log_func=add_log)


# Load persisted config on startup.
state.config = load_app_config()


def add_log(message: str, log_type: str = "info"):
    _add_state_log(state, message, log_type)


def wait_if_paused() -> bool:
    return _wait_if_paused(state)


def load_site_presets() -> Dict[str, Any]:
    return _load_site_presets(PRESETS_FILE)


def save_site_presets(presets: Dict[str, Any]) -> bool:
    return _save_site_presets(presets, PRESETS_FILE, log_func=add_log)
