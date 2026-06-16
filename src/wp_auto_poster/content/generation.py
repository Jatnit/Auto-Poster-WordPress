"""Provider router for generated content.

This module keeps provider selection pure enough to test while allowing the
browser-based providers to stay in the current Playwright workflow during the
incremental refactor.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional

from wp_auto_poster.providers.gemini_api import generate_content_gemini
from wp_auto_poster.providers.ollama import check_ollama, generate_content_ollama

LogFunc = Callable[[str, str], None]
BrowserProviderFunc = Callable[[Any, str, str], Optional[str]]
OllamaProviderFunc = Callable[[str, str, Mapping, LogFunc], Optional[str]]
GeminiApiProviderFunc = Callable[[str, str, str, LogFunc], Optional[str]]


def generate_content(
    provider: str,
    title: str,
    keyword: str,
    config: Mapping,
    log_func: LogFunc,
    page: Any = None,
    gemini_web_func: Optional[BrowserProviderFunc] = None,
    chatgpt_web_func: Optional[BrowserProviderFunc] = None,
    ollama_check_func: Callable[[], bool] = check_ollama,
    ollama_func: OllamaProviderFunc = generate_content_ollama,
    gemini_api_func: GeminiApiProviderFunc = generate_content_gemini,
) -> Optional[str]:
    """Generate content using a normalized provider interface."""
    selected = provider or config.get("ai_provider", "ollama")

    if selected == "ollama":
        if not ollama_check_func():
            log_func("Ollama is not running! Please start Ollama first.", "error")
            log_func("Run: ollama serve", "info")
            return None
        return ollama_func(title, keyword, config, log_func)

    if selected == "gemini_web":
        if page is None:
            log_func("Gemini Web requires browser page", "error")
            return None
        if gemini_web_func is None:
            log_func("Gemini Web provider is not configured", "error")
            return None
        return gemini_web_func(page, title, keyword)

    if selected == "chatgpt_web":
        if page is None:
            log_func("ChatGPT Web requires browser page", "error")
            return None
        if chatgpt_web_func is None:
            log_func("ChatGPT Web provider is not configured", "error")
            return None
        return chatgpt_web_func(page, title, keyword)

    return gemini_api_func(title, keyword, str(config.get("gemini_api_key", "")), log_func)
