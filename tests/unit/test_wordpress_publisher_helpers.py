import wp_auto_poster.wordpress.publisher as publisher_module
from wp_auto_poster.wordpress.publisher import PublisherRuntime, publish_or_schedule_post


def make_runtime():
    logs = []

    def log(message, level):
        logs.append((message, level))

    return PublisherRuntime(log_func=log), logs


class PublishButton:
    @property
    def first(self):
        return self

    def scroll_into_view_if_needed(self, timeout=0):
        return None

    def click(self, *args, **kwargs):
        return None


class SuccessMessage:
    @property
    def first(self):
        return self

    def is_visible(self, timeout=0):
        return True


class HiddenLocator:
    @property
    def first(self):
        return self

    def is_visible(self, timeout=0):
        return False


def test_publish_or_schedule_post_clicks_publish_and_detects_success(monkeypatch):
    runtime, logs = make_runtime()
    cleanup_calls = []
    sleep_calls = []

    class FakePage:
        url = "https://example.test/wp-admin/post.php?post=1&action=edit"

        def evaluate(self, *args, **kwargs):
            return None

        def locator(self, selector):
            if selector == "#publish, input#publish, #publishing-action input[type='submit']":
                return PublishButton()
            if selector == "#message.updated":
                return SuccessMessage()
            return HiddenLocator()

    monkeypatch.setattr(publisher_module.time, "sleep", lambda seconds: sleep_calls.append(seconds))
    monkeypatch.setattr(
        publisher_module,
        "remove_non_auto_images_from_editor",
        lambda page, reason, log_func=None: cleanup_calls.append(reason),
    )

    assert publish_or_schedule_post(FakePage(), False, None, runtime)
    assert cleanup_calls == ["pre-publish"]
    assert ("Clicked publish button", "info") in logs
    assert ("Success message detected; chờ thêm 3 giây để chắc chắn...", "info") in logs
    assert 3 in sleep_calls
    assert ("Published successfully!", "success") in logs
