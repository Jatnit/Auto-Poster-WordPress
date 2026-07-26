"""Ollama content provider."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Mapping, Optional

import requests

from wp_auto_poster.content.prompts import (
    PROMPT_PART1,
    PROMPT_PART2,
    format_contact_section,
    format_prompt,
    get_custom_prompt,
)

LogFunc = Callable[[str, str], None]

#: /api/status is polled once per second. Probing Ollama on every poll made
#: each request block for up to `timeout` seconds when Ollama was not running,
#: so the result is cached for a short window instead.
AVAILABILITY_CACHE_TTL = 10.0
_PROBE_TIMEOUT = 2

_availability_lock = threading.Lock()
_availability_cache: dict = {"value": None, "checked_at": 0.0}


def _probe_ollama() -> bool:
    try:
        response = requests.get(
            "http://localhost:11434/api/version",
            timeout=_PROBE_TIMEOUT,
        )
        return response.status_code == 200
    except Exception:
        return False


def check_ollama(force: bool = False, now: Optional[float] = None) -> bool:
    """Return whether the local Ollama server answers, with a short TTL cache."""
    current = time.monotonic() if now is None else now
    with _availability_lock:
        cached = _availability_cache["value"]
        fresh = (
            cached is not None
            and (current - _availability_cache["checked_at"]) < AVAILABILITY_CACHE_TTL
        )
        if fresh and not force:
            return cached

    value = _probe_ollama()
    with _availability_lock:
        _availability_cache["value"] = value
        _availability_cache["checked_at"] = current
    return value


def reset_availability_cache() -> None:
    """Drop the cached availability result (used by tests)."""
    with _availability_lock:
        _availability_cache["value"] = None
        _availability_cache["checked_at"] = 0.0


def __getattr__(name: str) -> Any:
    """Resolve ``OLLAMA_AVAILABLE`` lazily.

    It used to be a module-level constant assigned at import time, which cost
    a blocking network round-trip on every app start and every test collection.
    """
    if name == "OLLAMA_AVAILABLE":
        return check_ollama()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def clean_markdown_code_block(content: str) -> str:
    if content.startswith("```html"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def call_ollama_api(prompt: str, model: str) -> Optional[str]:
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.6, "num_predict": 6000, "num_ctx": 8192},
            },
            timeout=600,
        )

        if response.status_code == 200:
            result = response.json()
            return clean_markdown_code_block(result.get("response", ""))
        return None
    except Exception:
        return None


def generate_content_ollama(
    title: str,
    keyword: str,
    config: Mapping,
    log_func: LogFunc,
) -> Optional[str]:
    try:
        model = config.get("ollama_model", "llama3.1:8b")

        if not model or model == "llama3.2":
            model = "llama3.1:8b"

        log_func(f"Generating content with Ollama ({model})...", "info")

        custom_prompt = get_custom_prompt(config)
        if custom_prompt:
            # Honour the per-site prompt the same way the browser providers do,
            # instead of always using the built-in elevator-company template.
            log_func("Đang tạo nội dung với prompt tùy chỉnh...", "info")
            content = call_ollama_api(
                format_prompt(custom_prompt, title, keyword, config),
                model,
            )
            if not content:
                log_func("Could not generate content", "error")
                return None
            log_func(f"Đã tạo {len(content.split())} từ", "info")
            log_func(f"Generated content for: {title}", "success")
            return content

        log_func("Generating Part 1/2 (800+ words)...", "info")

        prompt_part1 = format_prompt(PROMPT_PART1, title, keyword, config)
        part1 = call_ollama_api(prompt_part1, model)

        if not part1:
            log_func("Could not generate Part 1", "error")
            return None

        word_count_1 = len(part1.split())
        log_func(f"Part 1: {word_count_1} words", "info")

        log_func("Generating Part 2/2 (800+ words)...", "info")

        prompt_part2 = format_prompt(PROMPT_PART2, title, keyword, config)
        part2 = call_ollama_api(prompt_part2, model)

        if not part2:
            log_func("Could not generate Part 2", "error")
            return None

        word_count_2 = len(part2.split())
        log_func(f"Part 2: {word_count_2} words", "info")

        contact = format_contact_section(keyword, config)
        full_content = part1 + "\n\n" + part2 + "\n\n" + contact

        total_words = len(full_content.split())
        log_func(f"Total: {total_words} words", "success")

        if total_words < 1200:
            log_func(f"Content shorter than expected ({total_words} words)", "warning")

        log_func(f"Generated content for: {title}", "success")
        return full_content

    except requests.exceptions.Timeout:
        log_func("Ollama timeout - content generation took too long", "error")
        return None
    except Exception as e:
        log_func(f"Ollama error: {e}", "error")
        return None
