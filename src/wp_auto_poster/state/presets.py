"""JSON-backed WordPress site preset storage."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from wp_auto_poster.state.json_store import read_json, write_json_atomic

LogFunc = Optional[Callable[[str, str], None]]


def load_site_presets(path: str) -> Dict[str, Any]:
    data = read_json(path)
    return data if isinstance(data, dict) else {}


def save_site_presets(presets: Mapping[str, Any], path: str, log_func: LogFunc = None) -> bool:
    try:
        write_json_atomic(presets, path)
        return True
    except Exception as exc:
        if log_func:
            log_func(f"Error saving presets: {exc}", "error")
        return False
