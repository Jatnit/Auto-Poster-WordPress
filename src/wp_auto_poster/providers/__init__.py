"""AI provider implementations.

Re-exports resolve lazily. Importing them eagerly ran ``check_ollama()`` — a
blocking network probe — and pulled in the Gemini SDK on every
``wp_auto_poster.providers.*`` import, including during test collection.
"""

from __future__ import annotations

import importlib
from typing import Any

_EXPORTS = {
    "GEMINI_AVAILABLE": "wp_auto_poster.providers.gemini_api",
    "generate_content_gemini": "wp_auto_poster.providers.gemini_api",
    "OLLAMA_AVAILABLE": "wp_auto_poster.providers.ollama",
    "call_ollama_api": "wp_auto_poster.providers.ollama",
    "check_ollama": "wp_auto_poster.providers.ollama",
    "generate_content_ollama": "wp_auto_poster.providers.ollama",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    module_path = _EXPORTS.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(module_path), name)


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS))
