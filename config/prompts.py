"""Backward-compatible facade for the extracted prompt module.

The real implementation now lives in ``wp_auto_poster.content.prompts`` so the
core package no longer depends on this top-level compatibility shim.
"""

from wp_auto_poster.content.prompts import (  # noqa: F401
    CONTACT_SECTION,
    DEFAULT_COMPANY_NAME,
    PROMPT_PART1,
    PROMPT_PART2,
    clean_gemini_content,
    current_year,
    format_contact_section,
    format_prompt,
    get_company_name,
    get_contact_section_template,
    get_custom_prompt,
    safe_format,
)

__all__ = [
    "CONTACT_SECTION",
    "DEFAULT_COMPANY_NAME",
    "PROMPT_PART1",
    "PROMPT_PART2",
    "clean_gemini_content",
    "current_year",
    "format_contact_section",
    "format_prompt",
    "get_company_name",
    "get_contact_section_template",
    "get_custom_prompt",
    "safe_format",
]
