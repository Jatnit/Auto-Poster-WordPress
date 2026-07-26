"""JSON-backed app configuration storage."""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Optional

from wp_auto_poster.state.json_store import read_json, write_json_atomic

LogFunc = Optional[Callable[[str, str], None]]


def load_app_config(
    path: str,
    defaults: Mapping[str, Any],
) -> Dict[str, Any]:
    data = read_json(path)
    if isinstance(data, dict):
        merged = dict(defaults)
        merged.update(data)
        return merged
    return dict(defaults)


def save_app_config(config: Mapping[str, Any], path: str, log_func: LogFunc = None) -> bool:
    try:
        write_json_atomic(config, path)
        return True
    except Exception as exc:
        if log_func:
            log_func(f"Error saving config: {exc}", "error")
        return False
