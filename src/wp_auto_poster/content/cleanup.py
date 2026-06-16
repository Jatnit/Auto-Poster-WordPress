"""Content cleanup utilities for generated SEO articles."""

from __future__ import annotations

import re
from typing import Callable, Optional

LogFunc = Optional[Callable[[str, str], None]]


def clean_generated_content(content: str, log_func: LogFunc = None) -> str:
    """Clean generated HTML while preserving article text and valid links.

    AI/web-generated snippets sometimes include linked logos, inline SVGs, or
    media preview markup. Those media blocks must not count as valid WordPress
    article images, so this function strips them before the content reaches the
    editor.
    """
    if not content:
        return content

    original_length = len(content)

    first_heading_match = re.search(r"<h[12][^>]*>", content, re.IGNORECASE)
    if first_heading_match:
        content = content[first_heading_match.start():]

    generated_media_removed = 0

    def remove_media_markup(pattern: str, text: str) -> str:
        nonlocal generated_media_removed
        matches = re.findall(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        generated_media_removed += len(matches)
        return re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)

    def remove_media_figure(match: re.Match) -> str:
        nonlocal generated_media_removed
        block = match.group(0)
        if re.search(r"<(?:img|svg|picture)\b", block, flags=re.IGNORECASE):
            generated_media_removed += 1
            return ""
        return block

    content = remove_media_markup(r"<picture\b[^>]*>.*?</picture>", content)
    content = re.sub(
        r"<figure\b[^>]*>.*?</figure>",
        remove_media_figure,
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    content = remove_media_markup(r"<a\b[^>]*>\s*<img\b[^>]*>\s*</a>", content)
    content = remove_media_markup(r"<img\b[^>]*>", content)
    content = remove_media_markup(r"<svg\b[^>]*>.*?</svg>", content)
    content = re.sub(
        r"<p\b[^>]*>\s*(?:<a\b[^>]*>\s*</a>\s*)?</p>",
        "",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if generated_media_removed and log_func:
        log_func(
            f"Removed {generated_media_removed} generated/logo media block(s) from content",
            "info",
        )

    last_link_pos = -1
    website_patterns = [
        r"thangmaykenzo\.com[^<]*</a>",
        r"suachuathangmay247\.com[^<]*</a>",
        r"thangmaykenzo\.com[^<]*</li>",
        r"suachuathangmay247\.com[^<]*</li>",
    ]

    for pattern in website_patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            if match.end() > last_link_pos:
                last_link_pos = match.end()

    if last_link_pos > 0:
        remaining = content[last_link_pos:]
        end_list_match = re.search(r"(</li>\s*)*</ul>", remaining, re.IGNORECASE)
        if end_list_match:
            cut_point = last_link_pos + end_list_match.end()
            content = content[:cut_point]

    outro_patterns = [
        r"<h[23][^>]*>\s*Next Steps[^<]*</h[23]>.*$",
        r"<p>\s*Would you like me to.*$",
        r"<p>\s*Do you want me to.*$",
        r"<p>\s*Let me know if you.*$",
        r"<p>\s*Shall I.*$",
        r"<strong>\s*Next Steps.*$",
        r"\(Lưu ý:.*?\)",
        r"\(Ghi chú:.*?\)",
        r"\(Chú ý:.*?\)",
        r"\(Tham khảo:.*?\)",
        r"\(Note:.*?\)",
        r"</ul>\s*\n*\s*\(.*?\)\s*$",
        r"</p>\s*\n*\s*\(.*?\)\s*$",
        r"<p>\s*\(.*?SEO.*?\)\s*</p>\s*$",
        r"<p>\s*\(.*?bài viết.*?\)\s*</p>\s*$",
        r"<p>\s*\(.*?từ khóa.*?\)\s*</p>\s*$",
        r"\(.*?1500.*?chữ.*?\)",
        r"\(.*?phân bố rải rác.*?\)",
        r"\s*\([^)]{50,}\)\s*$",
    ]

    for pattern in outro_patterns:
        content = re.sub(pattern, "", content, flags=re.IGNORECASE | re.DOTALL)

    lines = content.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue
        if stripped.startswith("(") and stripped.endswith(")"):
            continue
        meta_keywords = [
            "để bài viết đạt",
            "SEO",
            "từ khóa",
            "tỷ lệ từ khóa",
            "mật độ từ khóa",
            "phân bố rải rác",
            "lịch sử loài",
            "có thể bổ sung thêm",
            "để đảm bảo",
            "sức mạnh SEO",
        ]
        is_meta = stripped.startswith("(") and any(
            kw.lower() in stripped.lower() for kw in meta_keywords
        )
        if is_meta:
            continue
        cleaned_lines.append(line)

    content = "\n".join(cleaned_lines)
    content = re.sub(r"\s*<p>\s*</p>\s*", "", content)
    content = re.sub(r"\s+$", "", content)
    content = re.sub(r"\s*\([^)]*$", "", content)

    cleaned_length = len(content)
    if original_length != cleaned_length and log_func:
        removed = original_length - cleaned_length
        log_func(f"Cleaned content: {original_length} -> {cleaned_length} chars (-{removed})", "info")

    return content
