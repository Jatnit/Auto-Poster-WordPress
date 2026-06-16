import wp_auto_poster.wordpress.inline_images as inline_module
from wp_auto_poster.wordpress.inline_images import (
    InlineImageWorkflowConfig,
    InlineImageWorkflowRuntime,
    _select_visible_media_attachment,
    insert_images_after_h2,
    select_random_image_for_content,
)


class State:
    def __init__(self):
        self.is_running = True
        self.is_paused = False
        self.topics = [{"title": f"Post {i}"} for i in range(10)]


def make_runtime(state=None, config=None):
    logs = []

    def log(message, level):
        logs.append((message, level))

    runtime = InlineImageWorkflowRuntime(
        state=state or State(),
        log_func=log,
        wait_if_paused=lambda: True,
        config=config or InlineImageWorkflowConfig(),
    )
    return runtime, logs


def test_runtime_pool_size_uses_topic_count_and_buffer():
    runtime, _ = make_runtime()

    assert runtime.inline_image_random_pool_size() == 50


def test_runtime_pool_size_can_grow_for_large_batches():
    state = State()
    state.topics = [{"title": f"Post {i}"} for i in range(30)]
    runtime, _ = make_runtime(state=state)

    assert runtime.inline_image_random_pool_size() == 100


def test_select_visible_media_attachment_initializes_and_updates_state(monkeypatch):
    state = State()
    runtime, _ = make_runtime(state=state)

    def fake_select(page, label, used, count, pool_size, log_func=None):
        used.add("media-id")
        return True, 7

    monkeypatch.setattr(inline_module, "select_visible_media_attachment", fake_select)

    assert _select_visible_media_attachment(object(), "H2 #1", runtime)
    assert state.used_inline_images == {"media-id"}
    assert state.used_inline_image_count == 7


def test_insert_images_after_h2_stops_cleanly_when_runtime_not_running(monkeypatch):
    state = State()
    state.is_running = False
    runtime, logs = make_runtime(state=state)

    monkeypatch.setattr(inline_module, "close_all_modals", lambda page: None)
    monkeypatch.setattr(inline_module, "switch_to_visual_mode", lambda *args, **kwargs: None)
    monkeypatch.setattr(inline_module, "remove_non_auto_images_from_editor", lambda *args, **kwargs: 0)
    monkeypatch.setattr(inline_module, "get_safe_heading_count_for_images", lambda page: 0)
    monkeypatch.setattr(inline_module, "get_contact_heading_index", lambda page: None)
    monkeypatch.setattr(inline_module, "count_imgs_in_iframe", lambda page: 0)
    monkeypatch.setattr(inline_module, "finalize_inline_image_insert", lambda *args, **kwargs: False)

    assert not insert_images_after_h2(object(), "keyword", runtime, max_images=3)
    assert ("Đang chèn hình vào bài viết...", "info") in logs
    assert ("No H2 elements found — using paragraph fallback", "warning") in logs


def test_select_random_image_for_content_uses_shared_pool_and_direct_insert(monkeypatch):
    runtime, logs = make_runtime()
    close_calls = []
    inserted = []

    class FakeLocator:
        @property
        def first(self):
            return self

        def is_visible(self, timeout=0):
            return False

    class FakePage:
        def wait_for_selector(self, *args, **kwargs):
            return True

        def locator(self, *args, **kwargs):
            return FakeLocator()

    monkeypatch.setattr(inline_module.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        inline_module,
        "_wait_for_visible_media_attachments",
        lambda page, label, runtime: True,
    )
    monkeypatch.setattr(
        inline_module,
        "_select_visible_media_attachment",
        lambda page, label, runtime: True,
    )
    monkeypatch.setattr(
        inline_module,
        "get_selected_media_image",
        lambda page, fallback_alt, log_func=None: {"id": "img-1", "url": "https://example.test/img.jpg"},
    )

    def fake_insert(page, slot_hint, image, keyword, log_func=None):
        inserted.append((slot_hint, image["id"], keyword))
        return True

    monkeypatch.setattr(inline_module, "insert_selected_image_after_paragraph_direct", fake_insert)
    monkeypatch.setattr(inline_module, "close_all_modals", lambda page: close_calls.append(page))

    page = FakePage()

    assert select_random_image_for_content(page, "main keyword", runtime)
    assert inserted == [("bottom", "img-1", "main keyword")]
    assert close_calls == [page]
    assert ("Không thể set alt text", "warning") in logs
