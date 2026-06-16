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
