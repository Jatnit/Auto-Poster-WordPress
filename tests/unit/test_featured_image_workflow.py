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
        def evaluate(self, script, used_indices):
            assert used_indices == []
            return {"success": True, "index": 4, "available": 30, "total": 42}

    monkeypatch.setattr(featured_module.time, "sleep", lambda *_args, **_kwargs: None)

    assert select_featured_attachment(FakePage(), runtime)
    assert runtime.state.used_featured_images == {4}
    assert ("Selected image #5 via JS (30 available of 42)", "info") in logs


def test_set_featured_image_returns_false_when_modal_cannot_open(monkeypatch):
    runtime, logs = make_runtime()

    monkeypatch.setattr(featured_module, "open_featured_image_modal", lambda page, runtime: False)

    assert not set_featured_image(object(), "keyword", runtime)
    assert ("Could not open media modal - skipping featured image", "warning") in logs
