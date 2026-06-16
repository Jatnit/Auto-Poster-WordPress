"""Minimal markdown-to-HTML conversion for rescued AI responses."""

from __future__ import annotations

import re


def markdown_to_html_minimal(md: str) -> str:
    """Convert a small markdown subset to HTML while preserving HTML blocks."""
    if not md:
        return ""

    def inline(value: str) -> str:
        return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)

    html_block_re = re.compile(
        r"^\s*</?(?:h[1-6]|p|ul|ol|li|div|section|article|header|footer|"
        r"blockquote|pre|table|thead|tbody|tr|td|th|figure|figcaption)\b",
        re.IGNORECASE,
    )

    lines = md.splitlines()
    out: list[str] = []
    paragraph_buf: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buf:
            joined = " ".join(s.strip() for s in paragraph_buf if s.strip())
            if joined:
                out.append(f"<p>{inline(joined)}</p>")
            paragraph_buf.clear()

    i = 0
    line_count = len(lines)
    while i < line_count:
        raw = lines[i]
        stripped = raw.strip()

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        if stripped.startswith("### "):
            flush_paragraph()
            out.append(f"<h3>{inline(stripped[4:].strip())}</h3>")
            i += 1
            continue

        if stripped.startswith("## "):
            flush_paragraph()
            out.append(f"<h2>{inline(stripped[3:].strip())}</h2>")
            i += 1
            continue

        if stripped.startswith("- "):
            flush_paragraph()
            items: list[str] = []
            while i < line_count and lines[i].strip().startswith("- "):
                item_text = lines[i].strip()[2:].strip()
                items.append(f"<li>{inline(item_text)}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        if html_block_re.match(stripped):
            flush_paragraph()
            out.append(raw)
            i += 1
            continue

        paragraph_buf.append(stripped)
        i += 1

    flush_paragraph()
    return "\n".join(out)
