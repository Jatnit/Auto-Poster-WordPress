from wp_auto_poster.content.validation import (
    count_words,
    get_content_auto_retry_attempts,
    get_min_valid_words,
    strip_html_text,
    validate_generated_content,
)


def test_strip_html_text_normalizes_tags_and_spaces():
    assert strip_html_text("<p>Hello   <strong>world</strong></p>") == "Hello world"


def test_count_words_ignores_html_tags():
    assert count_words("<p>one two</p><h2>three</h2>") == 3


def test_min_valid_words_uses_default_and_lower_bound():
    assert get_min_valid_words({}) == 1401
    assert get_min_valid_words({"content_min_valid_words": "0"}) == 1
    assert get_min_valid_words({"content_min_valid_words": "1405"}) == 1405


def test_auto_retry_attempts_uses_default_and_lower_bound():
    assert get_content_auto_retry_attempts({}) == 2
    assert get_content_auto_retry_attempts({"content_auto_rerender_retries": "-3"}) == 0
    assert get_content_auto_retry_attempts({"content_auto_rerender_retries": "4"}) == 4


def test_validate_generated_content_returns_legacy_tuple_for_short_content():
    ok, cleaned, words, reason = validate_generated_content("<p>short text</p>", min_valid_words=3)
    assert ok is False
    assert cleaned == "<p>short text</p>"
    assert words == 2
    assert "2/3" in reason


def test_validate_generated_content_passes_when_word_count_is_enough():
    ok, cleaned, words, reason = validate_generated_content("one two three", min_valid_words=3)
    assert ok is True
    assert cleaned == "one two three"
    assert words == 3
    assert reason == ""
