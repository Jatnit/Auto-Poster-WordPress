"""End-to-end run through the Flask API with a fake Playwright.

Covers the wiring that unit tests deliberately stub out: start -> generate ->
publish -> status reporting -> stop, with the real AppState and the real
route handlers.
"""

import threading
import time

import pytest
from flask import Flask

from wp_auto_poster.automation import runner as runner_module
from wp_auto_poster.automation.runner import AutomationRuntime, run_automation
from wp_auto_poster.state.app_state import AppState
from wp_auto_poster.utils.logging import add_state_log, wait_if_paused
from wp_auto_poster.web.routes import RouteRuntime, register_routes


class FakePage:
    def __init__(self):
        self.default_timeout = None

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    def close(self):
        return None


class FakeContext:
    def __init__(self):
        self.pages = [FakePage()]
        self.closed = False

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    def close(self):
        self.closed = True


class FakeChromium:
    def __init__(self, context):
        self._context = context
        self.launch_kwargs = None

    def launch_persistent_context(self, user_data_dir, **kwargs):
        self.launch_kwargs = {"user_data_dir": user_data_dir, **kwargs}
        return self._context


class FakePlaywright:
    def __init__(self, context):
        self.chromium = FakeChromium(context)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


#: Distinctive so a match cannot come from a tmp path or a test name.
SECRET_PASSWORD = "pw-Zq7RtVx91"


@pytest.fixture
def wired_app(tmp_path, monkeypatch):
    """Build the real routes over a real AppState with a fake browser."""
    # The runner sleeps between posts and before closing the context. Those
    # waits are real-world pacing, not behaviour under test.
    monkeypatch.setattr(runner_module.time, "sleep", lambda seconds: None)

    # This machine may or may not have Brave installed; pin the browser so the
    # launch assertions do not depend on the developer's setup.
    fake_browser = tmp_path / "fake-browser"
    fake_browser.write_text("#!/bin/sh\n", encoding="utf-8")

    state = AppState()
    state.config.update(
        {
            "ai_provider": "ollama",
            "wp_username": "admin",
            "wp_password": SECRET_PASSWORD,
            "wp_login_url": "https://example.com/wp-login.php",
            "wp_admin_url": "https://example.com/wp-admin/",
            "delay_between_requests": 0,
            "auto_insert_inline_images": False,
            "browser_executable_path": str(fake_browser),
            "browser_user_data_dir": str(tmp_path / "profile"),
        }
    )

    context = FakeContext()
    playwright = FakePlaywright(context)
    published = []

    def create_single_post(page, index, topic, content, start_date):
        published.append((index, topic["title"]))
        return True

    automation = AutomationRuntime(
        state=state,
        add_log=lambda message, level: add_state_log(state, message, level),
        wait_if_paused=lambda: wait_if_paused(state, interval=0.01),
        playwright_available=True,
        sync_playwright=lambda: playwright,
        get_inline_image_random_pool_size=lambda: 50,
        generate_content_with_min_word_retries=(
            lambda provider, topic, index, page=None, source="initial": (
                f"<p>{topic['title']} content</p>"
            )
        ),
        process_content_retry_queue=lambda *a, **kw: None,
        cleanup_provider_chat_session=lambda *a, **kw: True,
        login_to_wordpress=lambda page: True,
        create_single_post=create_single_post,
    )

    routes = RouteRuntime(
        state=state,
        add_log=lambda message, level: add_state_log(state, message, level),
        load_site_presets=lambda: {},
        save_site_presets=lambda presets: True,
        save_app_config=lambda config: True,
        check_ollama=lambda: True,
        run_automation=lambda: run_automation(automation),
        get_min_valid_words=lambda: 1,
        find_content_row_by_post_index=lambda i: None,
        queue_content_rerender=lambda i: False,
        gemini_available=False,
        playwright_available=True,
    )

    app = Flask(__name__)
    register_routes(app, routes)
    return app.test_client(), state, context, published, playwright


def wait_until(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_full_run_publishes_every_topic(wired_app):
    client, state, context, published, playwright = wired_app
    client.post("/api/topics", json={"topics": [
        {"title": "Bài 1", "keyword": "k1"},
        {"title": "Bài 2", "keyword": "k2"},
    ]})

    response = client.post("/api/start", json={})
    assert response.get_json()["success"] is True

    assert wait_until(lambda: not state.is_running), "automation did not finish"

    assert [title for _, title in published] == ["Bài 1", "Bài 2"]
    assert state.successful_posts == 2
    assert state.failed_posts == 0
    assert state.current_phase == "completed"
    assert state.progress == 100
    assert context.closed is True


def test_status_reports_progress_and_incremental_logs(wired_app):
    client, state, _context, _published, playwright = wired_app
    client.post("/api/topics", json={"topics": [{"title": "Bài 1", "keyword": "k"}]})
    client.post("/api/start", json={})
    assert wait_until(lambda: not state.is_running)

    full = client.get("/api/status?since=0").get_json()
    assert full["log_seq"] > 0
    assert len(full["logs"]) > 0
    assert full["successful_posts"] == 1

    # Polling again with the cursor returns nothing new.
    incremental = client.get(f"/api/status?since={full['log_seq']}").get_json()
    assert incremental["logs"] == []
    assert incremental["log_seq"] == full["log_seq"]


def test_start_is_rejected_without_topics(wired_app):
    client, state, _context, _published, playwright = wired_app

    payload = client.post("/api/start", json={}).get_json()

    assert payload["success"] is False
    assert state.is_running is False


def test_start_is_rejected_while_already_running(wired_app):
    client, state, _context, _published, playwright = wired_app
    state.is_running = True

    payload = client.post("/api/start", json={}).get_json()

    assert payload["success"] is False


def test_stop_request_survives_and_halts_the_run(wired_app):
    """A Stop issued right after Start must not be undone by the runner."""
    client, state, _context, published, playwright = wired_app
    client.post("/api/topics", json={"topics": [
        {"title": f"Bài {i}", "keyword": "k"} for i in range(30)
    ]})

    client.post("/api/start", json={})
    client.post("/api/stop")

    assert wait_until(lambda: not state.is_running)
    assert state.stop_requested is True
    # The runner must not have published the whole backlog after a stop.
    assert len(published) < 30


def test_browser_launch_uses_resolved_profile_and_configured_slow_mo(wired_app, tmp_path):
    client, state, _context, _published, playwright = wired_app
    state.config["browser_slow_mo"] = 0
    client.post("/api/topics", json={"topics": [{"title": "Bài 1", "keyword": "k"}]})

    client.post("/api/start", json={})
    assert wait_until(lambda: not state.is_running)

    kwargs = playwright.chromium.launch_kwargs
    assert kwargs["user_data_dir"] == str(tmp_path / "profile")
    assert kwargs["slow_mo"] == 0
    assert kwargs["headless"] is False
    # The configured browser wins over any auto-detected system install.
    assert kwargs["executable_path"] == str(tmp_path / "fake-browser")


def test_secrets_never_appear_in_any_status_or_config_response(wired_app):
    client, state, _context, _published, playwright = wired_app
    client.post("/api/topics", json={"topics": [{"title": "Bài 1", "keyword": "k"}]})
    client.post("/api/start", json={})
    assert wait_until(lambda: not state.is_running)

    for path in ("/api/status?since=0", "/api/config", "/api/topics"):
        body = client.get(path).get_data(as_text=True)
        assert SECRET_PASSWORD not in body, f"password leaked via {path}"


def test_deleting_content_is_blocked_during_publishing(wired_app):
    client, state, _context, _published, playwright = wired_app
    state.is_running = True
    state.current_phase = "creating_posts"
    state.content_list = [{
        "post_index": 0, "title": "T", "keyword": "k",
        "word_count": 10, "status": "success", "attempts": 1, "content": "x",
    }]

    response = client.delete("/api/content/0")

    assert response.status_code == 409
    assert len(state.content_list) == 1


def test_pause_and_resume_toggle_state(wired_app):
    client, state, _context, _published, playwright = wired_app
    state.is_running = True

    assert client.post("/api/pause").get_json()["success"] is True
    assert state.is_paused is True

    assert client.post("/api/resume").get_json()["success"] is True
    assert state.is_paused is False


def test_concurrent_status_polls_do_not_corrupt_state(wired_app):
    """The status handler takes the state lock; hammer it while a run works."""
    client, state, _context, _published, playwright = wired_app
    client.post("/api/topics", json={"topics": [
        {"title": f"Bài {i}", "keyword": "k"} for i in range(5)
    ]})
    errors = []

    def poll():
        try:
            for _ in range(40):
                client.get("/api/status?since=0")
        except Exception as exc:  # pragma: no cover - only on a real bug
            errors.append(exc)

    client.post("/api/start", json={})
    pollers = [threading.Thread(target=poll) for _ in range(4)]
    for t in pollers:
        t.start()
    for t in pollers:
        t.join()

    assert wait_until(lambda: not state.is_running)
    assert errors == []
    assert state.successful_posts == 5
