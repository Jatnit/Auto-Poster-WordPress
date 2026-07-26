from config.settings import AppState


def test_app_state_reset_clears_runtime_queues_and_image_tracking():
    state = AppState()
    state.retry_queue = [{"action": "rerender_content", "post_index": 1}]
    state.skip_post_indices = {1}
    state.used_inline_images = {"10", "https://example.com/a.jpg"}
    state.used_inline_image_count = 2
    state.progress = 77

    state.reset()

    assert state.is_running is True
    assert state.retry_queue == []
    assert state.skip_post_indices == set()
    assert state.used_inline_images == set()
    assert state.used_inline_image_count == 0
    assert state.progress == 0
    assert state.current_phase == "initializing"


def test_default_config_includes_headless_mode():
    """A fresh clone with no app_config.json must still be able to launch."""
    state = AppState()

    assert state.config["headless_mode"] is False


def test_request_stop_marks_run_as_stopped():
    state = AppState()
    state.reset()

    state.request_stop()

    assert state.stop_requested is True
    assert state.is_running is False
    assert state.is_paused is False
    assert state.current_phase == "stopped"


def test_reset_clears_stop_requested():
    state = AppState()
    state.request_stop()

    state.reset()

    assert state.stop_requested is False
    assert state.is_running is True


def test_snapshot_posting_plan_is_detached_from_live_lists():
    state = AppState()
    state.topics = [{"title": "A"}, {"title": "B"}]
    state.generated_contents = ["<p>a</p>", "<p>b</p>"]

    topics, contents = state.snapshot_posting_plan()
    # A concurrent delete must not shift the plan the runner is iterating.
    del state.topics[0]
    del state.generated_contents[0]

    assert [t["title"] for t in topics] == ["A", "B"]
    assert contents == ["<p>a</p>", "<p>b</p>"]
