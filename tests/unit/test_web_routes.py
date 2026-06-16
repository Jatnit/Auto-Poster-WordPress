from types import SimpleNamespace

from flask import Flask

from wp_auto_poster.web.routes import RouteRuntime, register_routes


def make_state():
    return SimpleNamespace(
        is_running=True,
        is_paused=False,
        pause_reason="",
        current_task="Idle",
        progress=0,
        successful_posts=0,
        failed_posts=0,
        logs=[],
        current_phase="generating_content",
        retry_queue=[],
        content_list=[
            {
                "post_index": 0,
                "title": "Title",
                "keyword": "Keyword",
                "word_count": 1500,
                "status": "success",
                "attempts": 1,
                "content": "<p>content</p>",
            }
        ],
        config={"ai_provider": "ollama", "wp_username": "admin"},
        topics=[{"title": "Title", "keyword": "Keyword"}],
        generated_contents=["<p>content</p>"],
        skip_post_indices=set(),
        reset=lambda: None,
    )


def make_app(state=None):
    state = state or make_state()
    logs = []
    queued = []

    def add_log(message, level):
        logs.append((message, level))

    runtime = RouteRuntime(
        state=state,
        add_log=add_log,
        load_site_presets=lambda: {"default": {"wp_username": "admin"}},
        save_site_presets=lambda presets: True,
        save_app_config=lambda config: True,
        check_ollama=lambda: True,
        run_automation=lambda: None,
        get_min_valid_words=lambda: 1401,
        find_content_row_by_post_index=lambda post_index: 0 if post_index == 0 else None,
        queue_content_rerender=lambda post_index: queued.append(post_index) or True,
        gemini_available=True,
        playwright_available=True,
    )
    app = Flask(__name__)
    register_routes(app, runtime)
    return app, state, logs, queued


def test_status_endpoint_returns_content_summary_shape():
    app, _state, _logs, _queued = make_app()

    response = app.test_client().get("/api/status")

    assert response.status_code == 200
    data = response.get_json()
    assert data["is_running"] is True
    assert data["ollama_available"] is True
    assert data["content_count"] == 1
    assert data["content_list"][0]["title"] == "Title"
    assert "content" not in data["content_list"][0]


def test_config_post_normalizes_content_thresholds():
    app, state, _logs, _queued = make_app()

    response = app.test_client().post(
        "/api/config",
        json={"content_min_valid_words": "0", "content_auto_rerender_retries": "-5"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True}
    assert state.config["content_min_valid_words"] == 1
    assert state.config["content_auto_rerender_retries"] == 0


def test_rerender_endpoint_queues_content_during_generation_phase():
    app, _state, logs, queued = make_app()

    response = app.test_client().post("/api/content/0/rerender", json={})

    assert response.status_code == 200
    assert response.get_json()["queued"] is True
    assert queued == [0]
    assert logs[-1][1] == "warning"
