from wp_auto_poster.providers.session_cleanup import (
    cleanup_provider_chat_session,
    delete_current_chatgpt_session,
    delete_current_gemini_session,
)


class FakeElement:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    def is_visible(self, timeout=0):
        return self.selector in self.page.visible_selectors

    def is_enabled(self):
        return True

    def click(self, **kwargs):
        self.page.clicked.append(self.selector)
        if self.selector in self.page.url_after_click:
            self.page.url = self.page.url_after_click[self.selector]

    def all(self):
        return []

    def inner_text(self):
        return ""


class FakeLocator:
    def __init__(self, page, selector):
        self.first = FakeElement(page, selector)
        self.last = self.first

    def all(self):
        return []


class FakeMouse:
    def __init__(self):
        self.moves = []

    def move(self, x, y):
        self.moves.append((x, y))


class FakePage:
    def __init__(self, url, visible_selectors=None, url_after_click=None):
        self.url = url
        self.visible_selectors = set(visible_selectors or [])
        self.url_after_click = dict(url_after_click or {})
        self.clicked = []
        self.mouse = FakeMouse()

    def locator(self, selector):
        return FakeLocator(self, selector)


def make_logger():
    logs = []

    def log(message, level):
        logs.append((message, level))

    return logs, log


def test_gemini_cleanup_skips_when_url_is_not_concrete_session():
    logs, log = make_logger()
    page = FakePage("https://gemini.google.com/app")

    assert delete_current_gemini_session(page, log) is False
    assert page.clicked == []
    assert ("Gemini: không thấy session cụ thể để xóa (bỏ qua)", "info") in logs


def test_chatgpt_cleanup_skips_when_url_is_not_concrete_session():
    logs, log = make_logger()
    page = FakePage("https://chatgpt.com/")

    assert delete_current_chatgpt_session(page, log) is False
    assert page.clicked == []
    assert ("ChatGPT: không thấy session /c/<id> để xóa (bỏ qua)", "info") in logs


def test_gemini_cleanup_clicks_menu_delete_and_confirm():
    logs, log = make_logger()
    confirm_selector = "button:has-text('Delete')"
    page = FakePage(
        "https://gemini.google.com/app/abc123",
        visible_selectors={
            "[data-test-id='actions-menu-button']",
            "[role='menuitem']:has-text('Delete')",
            confirm_selector,
        },
        url_after_click={confirm_selector: "https://gemini.google.com/app"},
    )

    assert delete_current_gemini_session(page, log) is True
    assert "[data-test-id='actions-menu-button']" in page.clicked
    assert "[role='menuitem']:has-text('Delete')" in page.clicked
    assert confirm_selector in page.clicked
    assert ("Gemini: đã xóa session chat", "success") in logs


def test_chatgpt_cleanup_clicks_menu_delete_and_confirm():
    logs, log = make_logger()
    confirm_selector = "button:has-text('Delete')"
    page = FakePage(
        "https://chatgpt.com/c/abc123",
        visible_selectors={
            "button[data-testid='conversation-options-button']",
            "[role='menuitem']:has-text('Delete')",
            confirm_selector,
        },
        url_after_click={confirm_selector: "https://chatgpt.com/"},
    )

    assert delete_current_chatgpt_session(page, log) is True
    assert "button[data-testid='conversation-options-button']" in page.clicked
    assert "[role='menuitem']:has-text('Delete')" in page.clicked
    assert confirm_selector in page.clicked
    assert ("ChatGPT: đã xóa session chat", "success") in logs


def test_cleanup_provider_chat_session_dispatches_known_providers():
    logs, log = make_logger()
    page = FakePage("https://example.com")

    assert cleanup_provider_chat_session(page, "unknown", log) is False
    assert logs == []
