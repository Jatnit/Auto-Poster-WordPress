from types import SimpleNamespace

from wp_auto_poster.content.retry_queue import (
    ContentRetryRuntime,
    generate_content_with_min_word_retries,
    process_content_retry_queue,
    queue_content_rerender,
)


def make_runtime(responses=None, state=None):
    logs = []
    responses = list(responses or [])

    def add_log(message, level):
        logs.append((message, level))

    def generate_content(title, keyword, page=None, provider_override=None):
        if responses:
            return responses.pop(0)
        return None

    state = state or SimpleNamespace(
        config={"content_min_valid_words": 3, "content_auto_rerender_retries": 2},
        content_list=[],
        retry_queue=[],
        topics=[{"title": "Title", "keyword": "Keyword"}],
        generated_contents=[],
        current_content="",
        current_phase="generating_content",
        current_task="",
        is_paused=False,
        is_running=True,
    )
    runtime = ContentRetryRuntime(
        state=state,
        add_log=add_log,
        wait_if_paused=lambda: True,
        generate_content=generate_content,
        clean_content=lambda content: content,
    )
    return runtime, logs


def test_queue_content_rerender_deduplicates_same_post():
    runtime, _ = make_runtime()

    assert queue_content_rerender(runtime, 2) is True
    assert queue_content_rerender(runtime, 2) is False

    assert runtime.state.retry_queue == [{"action": "rerender_content", "post_index": 2}]


def test_generate_content_retries_then_keeps_failed_row_visible():
    runtime, logs = make_runtime(responses=["one", "two", "still short"])

    result = generate_content_with_min_word_retries(
        runtime,
        "ollama",
        {"title": "Title", "keyword": "Keyword"},
        0,
    )

    assert result is None
    assert runtime.state.content_list[0]["status"] == "failed"
    assert runtime.state.content_list[0]["attempts"] == 3
    assert "chỉ có" in runtime.state.content_list[0]["error_reason"]
    assert any("đã thử 3 lần" in message for message, _ in logs)


def test_generate_content_succeeds_after_retry_and_records_attempts():
    runtime, _ = make_runtime(responses=["one", "one two three"])

    result = generate_content_with_min_word_retries(
        runtime,
        "ollama",
        {"title": "Title", "keyword": "Keyword"},
        0,
    )

    assert result == "one two three"
    assert runtime.state.content_list[0]["status"] == "success"
    assert runtime.state.content_list[0]["attempts"] == 2
    assert runtime.state.current_content == "one two three"


def test_process_content_retry_queue_updates_generated_content_slot():
    state = SimpleNamespace(
        config={"content_min_valid_words": 3, "content_auto_rerender_retries": 0},
        content_list=[],
        retry_queue=[{"action": "rerender_content", "post_index": 0}],
        topics=[{"title": "Title", "keyword": "Keyword"}],
        generated_contents=[None],
        current_content="",
        current_phase="generating_content",
        current_task="",
        is_paused=False,
        is_running=True,
    )
    runtime, _ = make_runtime(responses=["one two three"], state=state)

    process_content_retry_queue(runtime, "ollama", total_topics=1)

    assert state.generated_contents == ["one two three"]
    assert state.retry_queue == []
    assert state.current_phase == "generating_content"
