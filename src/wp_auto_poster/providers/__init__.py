"""WP Auto Poster package."""
"""AI provider implementations."""

from wp_auto_poster.providers.gemini_api import GEMINI_AVAILABLE, generate_content_gemini
from wp_auto_poster.providers.ollama import (
    OLLAMA_AVAILABLE,
    call_ollama_api,
    check_ollama,
    generate_content_ollama,
)

__all__ = [
    "GEMINI_AVAILABLE",
    "OLLAMA_AVAILABLE",
    "call_ollama_api",
    "check_ollama",
    "generate_content_gemini",
    "generate_content_ollama",
]
