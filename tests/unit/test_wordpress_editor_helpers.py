import wp_auto_poster.wordpress.editor as editor_module
from wp_auto_poster.wordpress.editor import (
    EditorRuntime,
    set_post_title,
    set_rank_math_keyword,
)


def make_runtime():
    logs = []

    def log(message, level):
        logs.append((message, level))

    return EditorRuntime(config={"wp_admin_url": "https://example.test/wp-admin/"}, log_func=log), logs


class HiddenLocator:
    @property
    def first(self):
        return self

    def is_visible(self, timeout=0):
        return False


class VisibleLocator:
    def __init__(self):
        self.fills = []
        self.presses = []
        self.clicked = False

    @property
    def first(self):
        return self

    def is_visible(self, timeout=0):
        return True

    def click(self, *args, **kwargs):
        self.clicked = True

    def fill(self, value):
        self.fills.append(value)

    def press(self, key):
        self.presses.append(key)


def test_set_post_title_fills_classic_editor_title():
    runtime, logs = make_runtime()
    title_locator = VisibleLocator()

    class FakePage:
        def locator(self, selector):
            assert selector == "#title"
            return title_locator

    assert set_post_title(FakePage(), "My Article", runtime)
    assert title_locator.clicked
    assert title_locator.fills == ["", "My Article"]
    assert ("Set title: My Article...", "info") in logs


def test_set_rank_math_keyword_uses_js_fallback_when_inputs_hidden(monkeypatch):
    runtime, logs = make_runtime()
    evaluated = []

    class FakePage:
        def evaluate(self, script, *args):
            evaluated.append((script, args))
            return True

        def locator(self, selector):
            return HiddenLocator()

    monkeypatch.setattr(editor_module.time, "sleep", lambda *_args, **_kwargs: None)

    assert set_rank_math_keyword(FakePage(), "focus keyword", runtime)
    assert evaluated[-1][1] == ("focus keyword",)
    assert ("Rank Math keyword set via JS: focus keyword", "success") in logs
