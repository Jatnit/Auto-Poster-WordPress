from datetime import datetime

from wp_auto_poster.wordpress.post_workflow import PostWorkflowRuntime, create_single_post


class State:
    def __init__(self):
        self.is_running = True
        self.is_paused = False
        self.topics = [{"title": "Post"}]
        self.config = {
            "schedule_start_date": "",
            "schedule_end_date": "",
            "posts_per_day": 2,
            "auto_set_seo_keyword": True,
            "auto_insert_inline_images": True,
            "auto_set_featured_image": True,
            "auto_select_category": True,
            "auto_add_tags": True,
        }


def make_runtime(state=None):
    calls = []
    logs = []
    state = state or State()

    def log(message, level):
        logs.append((message, level))

    def record(name, result=True):
        def inner(*args, **kwargs):
            calls.append((name, args, kwargs))
            return result

        return inner

    runtime = PostWorkflowRuntime(
        state=state,
        log_func=log,
        wait_if_paused=lambda: True,
        navigate_to_new_post=record("navigate"),
        set_post_title=record("title"),
        set_post_content=record("content"),
        set_rank_math_keyword=record("rank_math"),
        insert_images_after_h2=record("inline_images"),
        set_featured_image=record("featured"),
        select_first_category=record("category"),
        add_post_tags=record("tags"),
        publish_or_schedule_post=record("publish"),
    )
    return runtime, calls, logs


def test_create_single_post_orchestrates_wordpress_steps():
    runtime, calls, logs = make_runtime()
    topic = {"title": "My Post", "keyword": "focus keyword", "tags": "tag one"}

    assert create_single_post(
        object(),
        0,
        topic,
        "<p>content</p>",
        datetime(2099, 1, 1),
        runtime,
    )

    call_names = [name for name, _args, _kwargs in calls]
    assert call_names == [
        "navigate",
        "title",
        "content",
        "rank_math",
        "inline_images",
        "featured",
        "category",
        "tags",
        "publish",
    ]
    assert calls[-1][1][1] is True
    assert ("Đang tạo bài 1: My Post", "info") in logs


def test_create_single_post_stops_before_browser_when_state_not_running():
    state = State()
    state.is_running = False
    runtime, calls, _logs = make_runtime(state)

    assert not create_single_post(
        object(),
        0,
        {"title": "My Post", "keyword": "focus keyword"},
        "<p>content</p>",
        datetime(2099, 1, 1),
        runtime,
    )
    assert calls == []
