"""Pure validation helpers for generated content."""

from __future__ import annotations

import re
from typing import Callable, Mapping, Optional, Tuple

DEFAULT_MIN_VALID_WORDS = 1401
DEFAULT_AUTO_RERENDER_RETRIES = 2


def strip_html_text(html_or_text: str) -> str:
    """Strip HTML tags and normalize whitespace for word counting."""
    if not html_or_text:
        return ""
    text = re.sub(r"<[^>]*>", " ", html_or_text)
    return re.sub(r"\s+", " ", text).strip()


def count_words(content: Optional[str]) -> int:
    """Count natural-language words after removing HTML tags."""
    if not content:
        return 0
    return len(strip_html_text(content).split())


def configured_int(config: Mapping, key: str, default: int, minimum: int = 0) -> int:
    """Read an integer config value with safe fallback and lower bound."""
    try:
        configured = int(config.get(key, default))
    except Exception:
        configured = default
    return max(minimum, configured)


def get_min_valid_words(config: Mapping) -> int:
    return configured_int(
        config,
        "content_min_valid_words",
        DEFAULT_MIN_VALID_WORDS,
        minimum=1,
    )


def get_content_auto_retry_attempts(config: Mapping) -> int:
    return configured_int(
        config,
        "content_auto_rerender_retries",
        DEFAULT_AUTO_RERENDER_RETRIES,
        minimum=0,
    )


def validate_generated_content(
    content: Optional[str],
    min_valid_words: int = DEFAULT_MIN_VALID_WORDS,
    cleaner: Optional[Callable[[str], str]] = None,
) -> Tuple[bool, str, int, str]:
    """Validate generated content and return the legacy 4-tuple contract."""
    if not content:
        return False, "", 0, "Không thể tạo nội dung (rỗng)"

    cleaned_content = cleaner(content) if cleaner else content
    words = count_words(cleaned_content)
    if words < min_valid_words:
        return False, cleaned_content, words, f"chỉ có {words}/{min_valid_words} từ"
    return True, cleaned_content, words, ""
