import threading
from types import SimpleNamespace

from wp_auto_poster.web.app_factory import create_app
from wp_auto_poster.web.routes import RouteRuntime


def test_create_app_registers_core_routes():
    state = SimpleNamespace(
        is_running=False,
        is_paused=False,
        pause_reason="",
        current_task="",
        progress=0,
        successful_posts=0,
        failed_posts=0,
        logs=[],
        current_phase="stopped",
        retry_queue=[],
        content_list=[],
        config={},
        topics=[],
        generated_contents=[],
        skip_post_indices=set(),
        reset=lambda: None,
    )

    runtime = RouteRuntime(
        state=state,
        add_log=lambda message, level: None,
        load_site_presets=lambda: {},
        save_site_presets=lambda presets: True,
        save_app_config=lambda config: True,
        check_ollama=lambda: False,
        run_automation=lambda: None,
        get_min_valid_words=lambda: 1401,
        find_content_row_by_post_index=lambda post_index: None,
        queue_content_rerender=lambda post_index: False,
        gemini_available=False,
        playwright_available=True,
    )

    app = create_app(lambda: runtime)

    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/api/status" in rules
    assert "/api/start" in rules
    assert "/content-seo" in rules


def _make_app():
    state = SimpleNamespace(
        is_running=False,
        is_paused=False,
        pause_reason="",
        current_task="",
        progress=0,
        successful_posts=0,
        failed_posts=0,
        logs=[],
        log_seq=0,
        current_phase="stopped",
        retry_queue=[],
        content_list=[],
        config={},
        topics=[],
        generated_contents=[],
        skip_post_indices=set(),
        stop_requested=False,
        reset=lambda: None,
    )
    state.lock = threading.RLock()
    state.mutation = lambda: state.lock
    runtime = RouteRuntime(
        state=state,
        add_log=lambda message, level: None,
        load_site_presets=lambda: {},
        save_site_presets=lambda presets: True,
        save_app_config=lambda config: True,
        check_ollama=lambda: False,
        run_automation=lambda: None,
        get_min_valid_words=lambda: 1401,
        find_content_row_by_post_index=lambda post_index: None,
        queue_content_rerender=lambda post_index: False,
        gemini_available=False,
        playwright_available=True,
    )
    return create_app(lambda: runtime)


def test_localhost_host_header_is_accepted():
    client = _make_app().test_client()

    response = client.get("/api/status", headers={"Host": "localhost:5001"})

    assert response.status_code == 200


def test_foreign_host_header_is_rejected():
    """Blocks DNS rebinding: a public hostname resolving to 127.0.0.1."""
    client = _make_app().test_client()

    response = client.get("/api/status", headers={"Host": "evil.example.com"})

    assert response.status_code == 403
    assert response.get_json()["success"] is False


def test_security_headers_are_set():
    client = _make_app().test_client()

    response = client.get("/api/status", headers={"Host": "127.0.0.1:5001"})

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
