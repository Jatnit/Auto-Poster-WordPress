import threading
from types import SimpleNamespace

from flask import Flask

from wp_auto_poster.web.routes import RouteRuntime, register_routes


def make_state():
    state = SimpleNamespace(
        is_running=True,
        is_paused=False,
        pause_reason="",
        current_task="Idle",
        progress=0,
        successful_posts=0,
        failed_posts=0,
        logs=[],
        log_seq=0,
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
        config={
            "ai_provider": "ollama",
            "wp_username": "admin",
            "wp_password": "stored-secret",
        },
        topics=[{"title": "Title", "keyword": "Keyword"}],
        generated_contents=["<p>content</p>"],
        skip_post_indices=set(),
        stop_requested=False,
        reset=lambda: None,
    )
    state.lock = threading.RLock()
    state.mutation = lambda: state.lock

    def request_stop():
        state.stop_requested = True
        state.is_running = False
        state.is_paused = False
        state.pause_reason = ""
        state.current_phase = "stopped"

    state.request_stop = request_stop
    return state


def make_app(state=None, presets=None):
    state = state or make_state()
    logs = []
    queued = []
    presets = presets if presets is not None else {
        "default": {"wp_username": "admin", "wp_password": "preset-secret"}
    }

    def add_log(message, level):
        logs.append((message, level))

    runtime = RouteRuntime(
        state=state,
        add_log=add_log,
        load_site_presets=lambda: presets,
        save_site_presets=lambda saved: True,
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
    assert response.get_json()["success"] is True
    assert state.config["content_min_valid_words"] == 1
    assert state.config["content_auto_rerender_retries"] == 0


def test_config_get_never_exposes_secrets():
    app, _state, _logs, _queued = make_app()

    data = app.test_client().get("/api/config").get_json()

    assert "wp_password" not in data
    assert "gemini_api_key" not in data
    assert data["wp_password_set"] is True
    assert data["wp_username"] == "admin"


def test_config_post_with_blank_password_keeps_stored_secret():
    app, state, _logs, _queued = make_app()

    response = app.test_client().post("/api/config", json={"wp_password": ""})

    assert response.status_code == 200
    assert state.config["wp_password"] == "stored-secret"


def test_config_post_with_new_password_replaces_stored_secret():
    app, state, _logs, _queued = make_app()

    app.test_client().post("/api/config", json={"wp_password": "brand-new"})

    assert state.config["wp_password"] == "brand-new"


def test_preset_get_never_exposes_password():
    app, _state, _logs, _queued = make_app()

    data = app.test_client().get("/api/presets/default").get_json()["data"]

    assert "wp_password" not in data
    assert data["wp_password_set"] is True


def test_apply_preset_copies_secret_server_side():
    app, state, _logs, _queued = make_app()

    response = app.test_client().post("/api/presets/default/apply")

    assert response.status_code == 200
    payload = response.get_json()
    # Secret lands in the live config but never in the HTTP response.
    assert state.config["wp_password"] == "preset-secret"
    assert "wp_password" not in payload["data"]
    assert payload["data"]["wp_password_set"] is True


def test_apply_unknown_preset_returns_404():
    app, _state, _logs, _queued = make_app()

    response = app.test_client().post("/api/presets/nope/apply")

    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_preset_put_with_blank_password_falls_back_to_live_config():
    saved = {}
    app, _state, _logs, _queued = make_app(presets=saved)

    app.test_client().put("/api/presets/newsite", json={"wp_username": "admin"})

    # Saving current settings as a brand-new preset should capture the
    # password the user is actually working with.
    assert saved["newsite"]["wp_password"] == "stored-secret"


def test_rerender_endpoint_queues_content_during_generation_phase():
    app, _state, logs, queued = make_app()

    response = app.test_client().post("/api/content/0/rerender", json={})

    assert response.status_code == 200
    assert response.get_json()["queued"] is True
    assert queued == [0]
    assert logs[-1][1] == "warning"


# ---------------------------------------------------------------------------
# Index integrity around deletion
# ---------------------------------------------------------------------------


def _state_with_three_posts():
    state = make_state()
    state.topics = [{"title": f"T{i}", "keyword": "k"} for i in range(3)]
    state.generated_contents = ["<p>0</p>", "<p>1</p>", "<p>2</p>"]
    state.content_list = [
        {
            "post_index": i,
            "title": f"T{i}",
            "keyword": "k",
            "word_count": 1500,
            "status": "success",
            "attempts": 1,
            "content": f"<p>{i}</p>",
        }
        for i in range(3)
    ]
    return state


def test_delete_reindexes_skip_post_indices():
    state = _state_with_three_posts()
    state.skip_post_indices = {0, 2}
    app, _state, _logs, _queued = make_app(state=state)

    assert app.test_client().delete("/api/content/1").status_code == 200

    # Post 2 shifted down to 1; post 0 is unaffected.
    assert state.skip_post_indices == {0, 1}


def test_delete_drops_and_reindexes_retry_queue_entries():
    state = _state_with_three_posts()
    state.retry_queue = [
        {"action": "rerender_content", "post_index": 1},
        {"action": "rerender_content", "post_index": 2},
    ]
    app, _state, _logs, _queued = make_app(state=state)

    app.test_client().delete("/api/content/1")

    # The entry for the deleted post is dropped, the later one shifts down.
    assert state.retry_queue == [{"action": "rerender_content", "post_index": 1}]


def test_delete_reindexes_content_rows_and_shrinks_lists():
    state = _state_with_three_posts()
    app, _state, _logs, _queued = make_app(state=state)

    app.test_client().delete("/api/content/1")

    assert [row["post_index"] for row in state.content_list] == [0, 1]
    assert [row["title"] for row in state.content_list] == ["T0", "T2"]
    assert state.generated_contents == ["<p>0</p>", "<p>2</p>"]
    assert [t["title"] for t in state.topics] == ["T0", "T2"]


def test_delete_is_blocked_while_publishing():
    state = _state_with_three_posts()
    state.current_phase = "creating_posts"
    app, _state, _logs, _queued = make_app(state=state)

    response = app.test_client().delete("/api/content/1")

    assert response.status_code == 409
    assert len(state.content_list) == 3


def test_topics_post_is_blocked_while_publishing():
    state = _state_with_three_posts()
    state.current_phase = "creating_posts"
    app, _state, _logs, _queued = make_app(state=state)

    response = app.test_client().post("/api/topics", json={"topics": []})

    assert response.status_code == 409
    assert len(state.topics) == 3


def test_topics_post_allowed_while_generating():
    state = _state_with_three_posts()
    state.current_phase = "generating_content"
    app, _state, _logs, _queued = make_app(state=state)

    response = app.test_client().post("/api/topics", json={"topics": [{"title": "New"}]})

    assert response.status_code == 200
    assert state.topics == [{"title": "New"}]


# ---------------------------------------------------------------------------
# Status payload size / cost
# ---------------------------------------------------------------------------


def test_status_returns_only_logs_newer_than_since():
    state = make_state()
    state.logs = [
        {"seq": 1, "time": "10:00:00", "message": "one", "type": "info"},
        {"seq": 2, "time": "10:00:01", "message": "two", "type": "info"},
        {"seq": 3, "time": "10:00:02", "message": "three", "type": "info"},
    ]
    state.log_seq = 3
    app, _state, _logs, _queued = make_app(state=state)

    data = app.test_client().get("/api/status?since=2").get_json()

    assert [entry["message"] for entry in data["logs"]] == ["three"]
    assert data["log_seq"] == 3


def test_status_without_since_returns_full_buffer():
    """Backwards compatible for clients that do not track a cursor."""
    state = make_state()
    state.logs = [
        {"seq": 1, "time": "10:00:00", "message": "one", "type": "info"},
        {"seq": 2, "time": "10:00:01", "message": "two", "type": "info"},
    ]
    state.log_seq = 2
    app, _state, _logs, _queued = make_app(state=state)

    data = app.test_client().get("/api/status").get_json()

    assert len(data["logs"]) == 2


def test_status_skips_ollama_probe_for_other_providers():
    """Probing Ollama costs a blocking HTTP round-trip on every poll."""
    state = make_state()
    state.config["ai_provider"] = "chatgpt_web"
    probes = []

    app, _state, _logs, _queued = make_app(state=state)
    # Rebuild with an instrumented probe.
    runtime = RouteRuntime(
        state=state,
        add_log=lambda message, level: None,
        load_site_presets=lambda: {},
        save_site_presets=lambda presets: True,
        save_app_config=lambda config: True,
        check_ollama=lambda: probes.append(1) or True,
        run_automation=lambda: None,
        get_min_valid_words=lambda: 1401,
        find_content_row_by_post_index=lambda post_index: None,
        queue_content_rerender=lambda post_index: False,
        gemini_available=True,
        playwright_available=True,
    )
    app = Flask(__name__)
    register_routes(app, runtime)

    data = app.test_client().get("/api/status").get_json()

    assert probes == []
    assert data["ollama_available"] is False


def test_status_probes_ollama_when_it_is_the_provider():
    state = make_state()
    state.config["ai_provider"] = "ollama"
    app, _state, _logs, _queued = make_app(state=state)

    data = app.test_client().get("/api/status").get_json()

    assert data["ollama_available"] is True


def test_stop_sets_stop_requested_flag():
    app, state, _logs, _queued = make_app()

    assert app.test_client().post("/api/stop").status_code == 200

    assert state.stop_requested is True
    assert state.is_running is False
    assert state.current_phase == "stopped"
