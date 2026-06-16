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
