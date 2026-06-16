"""JSON-backed WordPress site preset storage."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Mapping, Optional

LogFunc = Optional[Callable[[str, str], None]]


def load_site_presets(path: str) -> Dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}


def save_site_presets(presets: Mapping[str, Any], path: str, log_func: LogFunc = None) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(dict(presets), handle, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:
        if log_func:
            log_func(f"Error saving presets: {exc}", "error")
        return False
