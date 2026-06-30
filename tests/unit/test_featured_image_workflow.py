import wp_auto_poster.wordpress.featured_image as featured_module
from wp_auto_poster.wordpress.featured_image import (
    FeaturedImageRuntime,
    select_featured_attachment,
    set_featured_image,
)


class State:
    pass


def make_runtime(state=None):
    logs = []

    def log(message, level):
        logs.append((message, level))

    runtime = FeaturedImageRuntime(state=state or State(), log_func=log)
    return runtime, logs


def test_featured_runtime_initializes_used_image_tracking():
    state = State()
    runtime, _ = make_runtime(state)

    runtime.ensure_tracking()

    assert state.used_featured_images == set()


def test_select_featured_attachment_tracks_used_index(monkeypatch):
    runtime, logs = make_runtime()

    class FakePage:
        def evaluate(self, script, payload):
            assert payload["usedIds"] == []
            assert payload["poolSize"] == featured_module.FEATURED_IMAGE_POOL_SIZE
            return {
                "success": True,
                "selected": {
                    "id": "44",
                    "url": "https://example.test/44.jpg",
                    "index": 4,
                    "pool": 42,
                    "source": "wp.media",
                },
            }

    monkeypatch.setattr(featured_module.time, "sleep", lambda *_args, **_kwargs: None)

    assert select_featured_attachment(FakePage(), runtime)
    assert runtime.state.used_featured_images == {"44", "https://example.test/44.jpg"}
    assert ("Selected featured image #5 from 42/50 pool (wp.media)", "info") in logs


def test_click_set_featured_image_button_uses_bounded_click(monkeypatch):
    runtime, logs = make_runtime()
    clicks = []

    class Button:
        @property
        def first(self):
            return self

        def is_visible(self, timeout=0):
            return True

        def is_enabled(self, timeout=0):
            return True

        def click(self, *args, **kwargs):
            clicks.append(kwargs)

    class FakePage:
        def locator(self, selector):
            return Button()

    monkeypatch.setattr(featured_module.time, "sleep", lambda *_args, **_kwargs: None)

    assert featured_module.click_set_featured_image_button(FakePage(), runtime)
    assert clicks == [{"timeout": 1500}]
    assert ("Featured image set!", "success") in logs


def test_click_set_featured_image_button_falls_back_to_thumbnail_id(monkeypatch):
    runtime, logs = make_runtime()
    calls = []
    times = iter([100, 106])

    class DisabledButton:
        @property
        def first(self):
            return self

        def is_visible(self, timeout=0):
            return False

        def is_enabled(self, timeout=0):
            return False

    class FakePage:
        def locator(self, selector):
            return DisabledButton()

        def evaluate(self, script):
            calls.append(script)
            if "window.__autoPosterSelectedFeaturedImage" in script:
                return {"ok": True, "id": "321"}
            return False

    monkeypatch.setattr(featured_module.time, "time", lambda: next(times))
    monkeypatch.setattr(featured_module.time, "sleep", lambda *_args, **_kwargs: None)

    assert featured_module.click_set_featured_image_button(FakePage(), runtime)
    assert len(calls) == 2
    assert ("Featured image set via _thumbnail_id fallback: 321", "success") in logs


def test_set_featured_image_returns_false_when_modal_cannot_open(monkeypatch):
    runtime, logs = make_runtime()

    monkeypatch.setattr(featured_module, "open_featured_image_modal", lambda page, runtime: False)

    assert not set_featured_image(object(), "keyword", runtime)
    assert ("Could not open media modal - skipping featured image", "warning") in logs
