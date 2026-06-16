from types import SimpleNamespace

from wp_auto_poster.providers import chatgpt_web, gemini_web


def test_gemini_web_validation_detects_short_content_without_runtime():
    ok, reason, words = gemini_web._validate_gemini_response("<p>one two</p>", min_words=3)

    assert ok is False
    assert words == 2
    assert "2/3" in reason


def test_chatgpt_web_validation_detects_error_phrase_without_runtime():
    ok, reason, words = chatgpt_web._validate_chatgpt_response(
        "Something went wrong while generating",
        min_words=3,
    )

    assert ok is False
    assert words == 5
    assert "ChatGPT báo lỗi" in reason


def test_gemini_web_runtime_proxy_uses_configured_state_and_logger():
    logs = []
    state = SimpleNamespace(is_running=True)

    gemini_web.configure_runtime(
        gemini_web.GeminiWebRuntime(
            state=state,
            add_log=lambda message, level: logs.append((message, level)),
            wait_if_paused=lambda: True,
        )
    )

    gemini_web.add_log("hello", "info")
    gemini_web.state.is_running = False

    assert logs == [("hello", "info")]
    assert state.is_running is False
