"""Gemini API content provider (google-genai SDK)."""

from __future__ import annotations

import time
from typing import Any, Callable, Mapping, Optional

from wp_auto_poster.content.prompts import (
    PROMPT_PART1,
    PROMPT_PART2,
    format_contact_section,
    format_prompt,
    get_custom_prompt,
)

try:
    from google import genai
    from google.genai import types as genai_types

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    genai_types = None

LogFunc = Callable[[str, str], None]

DEFAULT_MODEL = "gemini-2.0-flash"
TEMPERATURE = 0.7
MAX_OUTPUT_TOKENS = 4096


def clean_markdown_code_block(content: str) -> str:
    if content.startswith("```html"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _is_rate_limited(error: Exception) -> bool:
    text = str(error).lower()
    return "429" in text or "quota" in text or "resource_exhausted" in text


def _generate_once(client: Any, model: str, prompt: str) -> str:
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            temperature=TEMPERATURE,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        ),
    )
    return clean_markdown_code_block((response.text or "").strip())


def generate_content_gemini(
    title: str,
    keyword: str,
    api_key: str,
    log_func: LogFunc,
    max_retries: int = 3,
    config: Optional[Mapping[str, Any]] = None,
) -> Optional[str]:
    if not GEMINI_AVAILABLE:
        log_func("Gemini library not available (pip install google-genai)", "error")
        return None
    if not api_key:
        log_func("Chưa cấu hình Gemini API key", "error")
        return None

    client = genai.Client(api_key=api_key)
    model = str((config or {}).get("gemini_model") or DEFAULT_MODEL)
    custom_prompt = get_custom_prompt(config)

    for attempt in range(max_retries):
        try:
            if custom_prompt:
                # Honour the per-site prompt the same way the browser
                # providers do, instead of always using the built-in template.
                log_func("Đang tạo nội dung với prompt tùy chỉnh...", "info")
                content = _generate_once(
                    client,
                    model,
                    format_prompt(custom_prompt, title, keyword, config),
                )
                if not content:
                    log_func("Gemini trả về nội dung rỗng", "error")
                    return None
                log_func(f"Đã tạo {len(content.split())} từ", "info")
                log_func(f"Generated content for: {title}", "success")
                return content

            log_func("Generating Part 1/2 with Gemini...", "info")
            part1 = _generate_once(
                client,
                model,
                format_prompt(PROMPT_PART1, title, keyword, config),
            )
            log_func(f"Part 1: {len(part1.split())} words", "info")

            log_func("Generating Part 2/2 with Gemini...", "info")
            part2 = _generate_once(
                client,
                model,
                format_prompt(PROMPT_PART2, title, keyword, config),
            )
            log_func(f"Part 2: {len(part2.split())} words", "info")

            contact = format_contact_section(keyword, config)
            full_content = part1 + "\n\n" + part2 + "\n\n" + contact

            log_func(f"Total: {len(full_content.split())} words", "success")
            log_func(f"Generated content for: {title}", "success")
            return full_content

        except Exception as e:
            if _is_rate_limited(e):
                wait_time = 60 * (attempt + 1)
                log_func(
                    f"Rate limit hit. Waiting {wait_time}s before retry "
                    f"{attempt + 1}/{max_retries}...",
                    "warning",
                )
                time.sleep(wait_time)
            else:
                log_func(f"Error generating content: {e}", "error")
                return None

    log_func(f"Failed to generate content after {max_retries} retries", "error")
    return None
