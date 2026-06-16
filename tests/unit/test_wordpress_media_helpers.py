import wp_auto_poster.wordpress.media as media_module
from wp_auto_poster.wordpress.media import (
    DEFAULT_MEDIA_STATUS,
    count_imgs_in_iframe,
    finalize_inline_image_insert,
    find_unfilled_target_h2,
    format_heading_targets,
    get_contact_heading_index,
    get_heading_count_in_iframe,
    get_media_attachment_status,
    get_selected_media_image,
    insert_selected_image_after_h2_direct,
    insert_selected_image_after_paragraph_direct,
    rebalance_auto_images_to_targets,
    remove_non_auto_images_from_editor,
    remove_or_move_images_after_contact,
    select_visible_media_attachment,
    sync_editor_after_direct_insert,
    switch_to_visual_mode,
    wait_for_img_count_increase,
    wait_for_visible_media_attachments,
)


def make_logger():
    logs = []

    def log(message, level):
        logs.append((message, level))

    return logs, log


class EvalNode:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def evaluate(self, script, *args):
        self.calls.append((script, args))
        if self.error:
            raise self.error
        return self.result

    def all(self):
        if isinstance(self.result, list):
            return self.result
        return []


class FrameLocator:
    def __init__(self, node):
        self.node = node

    def locator(self, selector):
        return self.node


class Page:
    def __init__(self, eval_result=None, body_result=None, eval_error=None, body_error=None):
        self.page_node = EvalNode(eval_result, eval_error)
        self.body_node = EvalNode(body_result, body_error)

    def evaluate(self, script, *args):
        return self.page_node.evaluate(script, *args)

    def frame_locator(self, selector):
        return FrameLocator(self.body_node)


def test_get_media_attachment_status_falls_back_on_error():
    page = Page(eval_error=RuntimeError("dom missing"))

    assert get_media_attachment_status(page) == DEFAULT_MEDIA_STATUS


def test_format_heading_targets():
    assert format_heading_targets([]) == "none"
    assert format_heading_targets([0, 2, 4]) == "#1, #3, #5"


def test_switch_to_visual_mode_clicks_visible_tab(monkeypatch):
    monkeypatch.setattr(media_module.time, "sleep", lambda seconds: None)

    class Tab:
        clicked = False

        def is_visible(self, timeout=0):
            return True

        def click(self):
            self.clicked = True

    class Locator:
        def __init__(self, tab):
            self.first = tab

    class VisualPage:
        def __init__(self):
            self.tab = Tab()

        def locator(self, selector):
            return Locator(self.tab)

    page = VisualPage()

    switch_to_visual_mode(page)

    assert page.tab.clicked


def test_find_unfilled_target_h2_uses_safe_heading_count(monkeypatch):
    monkeypatch.setattr(media_module, "get_h2_elements_in_iframe", lambda page, selector: [0, 1, 2])
    monkeypatch.setattr(media_module, "img_is_after_h2", lambda page, idx: idx == 1)

    assert find_unfilled_target_h2(Page(), [0, 1, 2, 3], "h2, h3") == [0, 2]


def test_get_selected_media_image_returns_window_selection():
    image = {"id": "12", "url": "https://example.com/a.jpg", "alt": "A", "title": "T"}
    page = Page(eval_result=image)

    assert get_selected_media_image(page, "fallback") == image


def test_get_selected_media_image_logs_read_error():
    logs, log = make_logger()
    page = Page(eval_error=RuntimeError("selection gone"))

    assert get_selected_media_image(page, "fallback", log_func=log) is None
    assert logs
    assert logs[0][1] == "warning"


def test_remove_non_auto_images_logs_and_syncs_when_removed():
    logs, log = make_logger()
    page = Page(body_result={"removed": 2, "valid": 3, "all": 3})

    assert remove_non_auto_images_from_editor(page, "scan", log_func=log) == 2
    assert logs == [
        ("Removed 2 non-auto/logo image(s) from editor (scan); valid auto images=3", "warning")
    ]


def test_insert_selected_image_after_h2_direct_logs_success():
    logs, log = make_logger()
    page = Page(body_result={"ok": True, "count": 1})

    assert insert_selected_image_after_h2_direct(
        page,
        1,
        {"url": "https://example.com/a.jpg"},
        "keyword",
        log_func=log,
    )
    assert ("Inserted selected image directly under H2 #2", "success") in logs


def test_insert_selected_image_after_paragraph_direct_logs_failure_reason():
    logs, log = make_logger()
    page = Page(body_result={"ok": False, "reason": "no_safe_paragraphs_before_contact"})

    assert not insert_selected_image_after_paragraph_direct(
        page,
        "bottom",
        {"url": "https://example.com/a.jpg"},
        "keyword",
        log_func=log,
    )
    assert (
        "Fallback (bottom) direct insert failed: no_safe_paragraphs_before_contact",
        "warning",
    ) in logs


def test_sync_editor_after_direct_insert_swallows_errors():
    page = Page(eval_error=RuntimeError("tinymce missing"))

    sync_editor_after_direct_insert(page)


def test_count_imgs_in_iframe_returns_auto_image_count():
    page = Page(body_result=3)

    assert count_imgs_in_iframe(page) == 3


def test_get_heading_count_and_contact_index_from_iframe():
    assert get_heading_count_in_iframe(Page(body_result=5)) == 5
    assert get_contact_heading_index(Page(body_result=4)) == 4
    assert get_contact_heading_index(Page(body_result=None)) is None


def test_rebalance_auto_images_to_targets_logs_moved_count():
    logs, log = make_logger()
    page = Page(body_result={"moved": 2})

    assert rebalance_auto_images_to_targets(page, [1, 3], log_func=log) == 2
    assert ("Final scan rebalanced 2 image(s) to target headings", "success") in logs


def test_remove_or_move_images_after_contact_logs_changed_count():
    logs, log = make_logger()
    page = Page(body_result={"moved": 1, "removed": 2})

    assert remove_or_move_images_after_contact(page, [1, 3], log_func=log) == 3
    assert (
        "Contact boundary cleanup: moved 1, removed 2 image(s) after contact section",
        "success",
    ) in logs


def test_wait_for_img_count_increase_returns_when_count_grows(monkeypatch):
    counts = iter([1, 1, 3])
    monkeypatch.setattr(media_module, "count_imgs_in_iframe", lambda page: next(counts))
    monkeypatch.setattr(media_module.time, "sleep", lambda seconds: None)

    assert wait_for_img_count_increase(Page(), 1, 100, 10) == 3


def test_finalize_inline_image_insert_logs_success_count():
    logs, log = make_logger()
    page = Page(body_result=3)

    assert finalize_inline_image_insert(page, 3, "done", log_func=log)
    assert ("Total images inserted: 3/3", "success") in logs


def test_finalize_inline_image_insert_logs_short_count():
    logs, log = make_logger()
    page = Page(body_result=1)

    assert finalize_inline_image_insert(page, 3, "no_h2", log_func=log)
    assert (
        "Total images inserted: 1/3 (reason=no_h2) — proceeding without blocking post",
        "warning",
    ) in logs


def test_select_visible_media_attachment_updates_used_pool(monkeypatch):
    monkeypatch.setattr(media_module.time, "sleep", lambda seconds: None)
    logs, log = make_logger()
    used = {"old-id"}
    page = Page(
        eval_result={
            "ok": True,
            "selected": {
                "id": "44",
                "url": "https://example.com/44.jpg",
                "index": 8,
                "pool": 50,
                "source": "wp.media",
            },
        }
    )

    ok, count = select_visible_media_attachment(
        page,
        "H2 #3",
        used,
        4,
        50,
        log_func=log,
    )

    assert ok is True
    assert count == 5
    assert "44" in used
    assert "https://example.com/44.jpg" in used
    assert logs == [
        ("Selected unique inline image #5: media item 9 from 50/50 pool (wp.media) for H2 #3", "info")
    ]


def test_select_visible_media_attachment_logs_failure_without_increment():
    logs, log = make_logger()
    used = {"old-id"}
    page = Page(eval_result={"ok": False, "reason": "no_visible_attachments", "total": 0})

    ok, count = select_visible_media_attachment(
        page,
        "H2 #1",
        used,
        2,
        50,
        log_func=log,
    )

    assert ok is False
    assert count == 2
    assert used == {"old-id"}
    assert logs == [
        (
            "Select image fail for H2 #1: no_visible_attachments "
            "(pool=0/50, selected unique images=2)",
            "warning",
        )
    ]


def test_wait_for_visible_media_attachments_passes_when_visible(monkeypatch):
    monkeypatch.setattr(media_module, "switch_to_media_library_tab", lambda *args, **kwargs: None)
    page = Page(
        eval_result={
            "total": 3,
            "visible": 1,
            "libraryCount": 0,
            "loading": False,
            "noItems": False,
        }
    )

    assert wait_for_visible_media_attachments(page, "H2 #1", 100, 10)


def test_wait_for_visible_media_attachments_logs_no_items(monkeypatch):
    monkeypatch.setattr(media_module, "switch_to_media_library_tab", lambda *args, **kwargs: None)
    logs, log = make_logger()
    page = Page(
        eval_result={
            "total": 0,
            "visible": 0,
            "libraryCount": 0,
            "loading": False,
            "noItems": True,
        }
    )

    assert not wait_for_visible_media_attachments(page, "H2 #9", 100, 10, log_func=log)
    assert logs == [
        (
            "No visible images in media library for H2 #9 sau khi chờ 100ms "
            "(total=0, visible=0, library=0, loading=False)",
            "warning",
        )
    ]
