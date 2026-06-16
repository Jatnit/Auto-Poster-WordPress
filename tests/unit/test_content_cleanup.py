from wp_auto_poster.content.cleanup import clean_generated_content


def test_clean_generated_content_removes_generated_logo_media_but_keeps_text_link():
    html = '''
    Intro before heading should be removed
    <h1>Test</h1>
    <p>Text before <a href="https://example.com"><img src="logo.png"></a><a href="https://example.com">Brand</a> more text.</p>
    <figure><img src="cibes.png"><figcaption>Cibes</figcaption></figure>
    <p><svg><path /></svg> Schindler text</p>
    <h2>Next</h2><p>Body text</p>
    '''
    cleaned = clean_generated_content(html)
    lowered = cleaned.lower()

    assert cleaned.startswith("<h1>Test</h1>")
    assert "<img" not in lowered
    assert "<svg" not in lowered
    assert "<figure" not in lowered
    assert "Brand" in cleaned
    assert "Body text" in cleaned


def test_clean_generated_content_removes_meta_parenthetical_tail():
    cleaned = clean_generated_content("<h2>A</h2><p>Body</p> (Ghi chú: nội dung SEO)")
    assert "Ghi chú" not in cleaned
