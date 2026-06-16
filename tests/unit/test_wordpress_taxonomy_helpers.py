import wp_auto_poster.wordpress.taxonomy as taxonomy_module
from wp_auto_poster.wordpress.taxonomy import (
    TaxonomyRuntime,
    add_post_tags,
    select_first_category,
)


def make_runtime(config=None):
    logs = []

    def log(message, level):
        logs.append((message, level))

    runtime = TaxonomyRuntime(
        config=config or {"category_name": "Tin tức"},
        log_func=log,
    )
    return runtime, logs


class CountZeroLocator:
    @property
    def first(self):
        return self

    def count(self):
        return 0


def test_select_first_category_prefers_configured_category(monkeypatch):
    runtime, logs = make_runtime({"category_name": "Blog"})
    evaluate_calls = []

    class FakePage:
        def locator(self, selector):
            return CountZeroLocator()

        def evaluate(self, script, *args):
            evaluate_calls.append(args)
            if not args:
                return [
                    {"cbId": "cat-1", "cbValue": "1", "label": "Tin tức"},
                    {"cbId": "cat-2", "cbValue": "2", "label": "BLOG"},
                ]
            return {"ok": True, "reason": "set"}

    monkeypatch.setattr(taxonomy_module.time, "sleep", lambda *_args, **_kwargs: None)

    assert select_first_category(FakePage(), runtime)
    assert evaluate_calls[-1] == ({"cbId": "cat-2", "cbValue": "2"},)
    assert ("Selected category: BLOG", "success") in logs


def test_add_post_tags_returns_true_when_tags_empty():
    runtime, logs = make_runtime()

    assert add_post_tags(object(), "   ", runtime)
    assert ("No tags to add", "info") in logs
