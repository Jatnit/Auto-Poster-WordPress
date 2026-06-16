"""JSON-backed app configuration storage."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Mapping, Optional

LogFunc = Optional[Callable[[str, str], None]]


def load_app_config(
    path: str,
    defaults: Mapping[str, Any],
) -> Dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                if isinstance(data, dict):
                    merged = dict(defaults)
                    merged.update(data)
                    return merged
        except Exception:
            pass
    return dict(defaults)


def save_app_config(config: Mapping[str, Any], path: str, log_func: LogFunc = None) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(dict(config), handle, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:
        if log_func:
            log_func(f"Error saving config: {exc}", "error")
        return False
