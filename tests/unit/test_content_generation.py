from wp_auto_poster.content.generation import generate_content


def make_logger():
    logs = []

    def log(message, level):
        logs.append((message, level))

    return logs, log


def test_ollama_not_running_returns_none_and_logs_hint():
    logs, log = make_logger()

    result = generate_content(
        "ollama",
        "Title",
        "keyword",
        {"ai_provider": "ollama"},
        log,
        ollama_check_func=lambda: False,
    )

    assert result is None
    assert ("Ollama is not running! Please start Ollama first.", "error") in logs
    assert ("Run: ollama serve", "info") in logs


def test_ollama_provider_uses_config_provider_when_running():
    logs, log = make_logger()

    result = generate_content(
        "ollama",
        "Title",
        "keyword",
        {"ai_provider": "ollama", "ollama_model": "custom"},
        log,
        ollama_check_func=lambda: True,
        ollama_func=lambda title, keyword, config, log_func: f"{title}|{keyword}|{config['ollama_model']}",
    )

    assert result == "Title|keyword|custom"
    assert logs == []


def test_gemini_web_requires_browser_page():
    logs, log = make_logger()

    result = generate_content(
        "gemini_web",
        "Title",
        "keyword",
        {},
        log,
        page=None,
        gemini_web_func=lambda page, title, keyword: "content",
    )

    assert result is None
    assert ("Gemini Web requires browser page", "error") in logs


def test_chatgpt_web_calls_browser_provider_callback():
    logs, log = make_logger()
    page = object()

    result = generate_content(
        "chatgpt_web",
        "Title",
        "keyword",
        {},
        log,
        page=page,
        chatgpt_web_func=lambda callback_page, title, keyword: (
            "ok" if callback_page is page and title == "Title" and keyword == "keyword" else "bad"
        ),
    )

    assert result == "ok"
    assert logs == []


def test_gemini_provider_routes_to_gemini_api():
    logs, log = make_logger()

    result = generate_content(
        "gemini",
        "Title",
        "keyword",
        {"gemini_api_key": "secret"},
        log,
        gemini_api_func=lambda title, keyword, api_key, log_func, config=None: f"{title}|{keyword}|{api_key}",
    )

    assert result == "Title|keyword|secret"
    assert logs == []


def test_gemini_api_alias_routes_to_gemini_api():
    logs, log = make_logger()

    result = generate_content(
        "gemini_api",
        "Title",
        "keyword",
        {"gemini_api_key": "secret"},
        log,
        gemini_api_func=lambda title, keyword, api_key, log_func, config=None: "ok",
    )

    assert result == "ok"
    assert logs == []


def test_unknown_provider_errors_instead_of_falling_through():
    """A typo in ai_provider must not silently bill the Gemini API."""
    logs, log = make_logger()
    called = []

    result = generate_content(
        "gemni_web",  # typo
        "Title",
        "keyword",
        {"gemini_api_key": "secret"},
        log,
        gemini_api_func=lambda *args, **kwargs: called.append(1),
    )

    assert result is None
    assert called == []
    assert logs and logs[-1][1] == "error"
    assert "gemni_web" in logs[-1][0]
