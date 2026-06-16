from wp_auto_poster.content.html_convert import markdown_to_html_minimal


def test_markdown_to_html_minimal_converts_headings_lists_and_strong():
    source = "## Title\n\nParagraph with **bold** text.\n\n- One\n- Two\n\n### Child"
    html = markdown_to_html_minimal(source)

    assert "<h2>Title</h2>" in html
    assert "<p>Paragraph with <strong>bold</strong> text.</p>" in html
    assert "<ul><li>One</li><li>Two</li></ul>" in html
    assert "<h3>Child</h3>" in html


def test_markdown_to_html_minimal_preserves_existing_html_block():
    assert markdown_to_html_minimal("<h2>Already HTML</h2>") == "<h2>Already HTML</h2>"
