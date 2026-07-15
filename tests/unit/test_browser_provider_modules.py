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


def test_chatgpt_wait_does_not_finish_before_min_words(monkeypatch):
    logs = []
    state = SimpleNamespace(is_running=True, is_paused=False)
    chatgpt_web.configure_runtime(
        chatgpt_web.ChatGPTWebRuntime(
            state=state,
            add_log=lambda message, level: logs.append((message, level)),
            wait_if_paused=lambda: True,
        )
    )

    calls = {"count": 0}

    def fake_extract(_page):
        calls["count"] += 1
        if calls["count"] < 9:
            return "<p>one two</p>"
        return "<p>one two three four five</p>"

    monkeypatch.setattr(chatgpt_web, "_chatgpt_extract_response", fake_extract)
    monkeypatch.setattr(chatgpt_web, "_chatgpt_is_streaming", lambda _page: False)
    monkeypatch.setattr(chatgpt_web.time, "sleep", lambda *_args, **_kwargs: None)

    response = chatgpt_web._wait_for_chatgpt_response(object(), max_wait=90, min_words=5)

    assert "five" in response
    assert calls["count"] >= 10


def test_gemini_wait_does_not_finish_before_min_words(monkeypatch):
    logs = []
    state = SimpleNamespace(is_running=True, is_paused=False)
    gemini_web.configure_runtime(
        gemini_web.GeminiWebRuntime(
            state=state,
            add_log=lambda message, level: logs.append((message, level)),
            wait_if_paused=lambda: True,
        )
    )

    calls = {"count": 0}

    def fake_extract(_page):
        calls["count"] += 1
        if calls["count"] < 9:
            return "<p>one two</p>"
        return "<p>one two three four five</p>"

    class EmptyLocator:
        def all(self):
            return []

    class Page:
        def locator(self, *_args, **_kwargs):
            return EmptyLocator()

    monkeypatch.setattr(gemini_web, "_extract_gemini_response", fake_extract)
    monkeypatch.setattr(gemini_web.time, "sleep", lambda *_args, **_kwargs: None)

    response = gemini_web._wait_for_gemini_response(Page(), max_wait=90, min_words=5)

    assert "five" in response
    assert calls["count"] >= 10
