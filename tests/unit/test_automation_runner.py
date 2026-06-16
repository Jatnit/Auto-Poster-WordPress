from types import SimpleNamespace

from wp_auto_poster.automation.runner import AutomationRuntime, run_automation


def make_state(**overrides):
    state = SimpleNamespace(
        is_running=True,
        is_paused=False,
        current_phase="idle",
        current_task="",
        progress=0,
        topics=[],
        total_tasks=0,
        generated_contents=[],
        successful_posts=0,
        failed_posts=0,
        skip_post_indices=set(),
        config={
            "ai_provider": "ollama",
            "auto_insert_inline_images": True,
            "delay_between_requests": 0,
            "schedule_start_date": "",
            "schedule_end_date": "",
            "headless_mode": True,
        },
    )
    state.reset = lambda: None
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def make_runtime(state=None, playwright_available=True, sync_playwright=None):
    logs = []

    def add_log(message, level):
        logs.append((message, level))

    runtime = AutomationRuntime(
        state=state or make_state(),
        add_log=add_log,
        wait_if_paused=lambda: True,
        playwright_available=playwright_available,
        sync_playwright=sync_playwright or (lambda: (_ for _ in ()).throw(AssertionError("browser should not start"))),
        get_inline_image_random_pool_size=lambda: 50,
        generate_content_with_min_word_retries=lambda *args, **kwargs: None,
        process_content_retry_queue=lambda *args, **kwargs: None,
        cleanup_provider_chat_session=lambda *args, **kwargs: True,
        login_to_wordpress=lambda page: True,
        create_single_post=lambda *args, **kwargs: True,
    )
    return runtime, logs


def test_run_automation_stops_when_playwright_unavailable():
    state = make_state()
    runtime, logs = make_runtime(state=state, playwright_available=False)

    run_automation(runtime)

    assert state.is_running is False
    assert state.current_phase == "stopped"
    assert ("Playwright not available. Please install it first.", "error") in logs


def test_run_automation_stops_before_browser_when_no_content_generated():
    state = make_state(topics=[{"title": "Title", "keyword": "Keyword"}])
    runtime, logs = make_runtime(state=state)

    run_automation(runtime)

    assert state.is_running is False
    assert state.generated_contents == [None]
    assert ("No content generated. Stopping.", "error") in logs
