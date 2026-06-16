from wp_auto_poster.wordpress.browser import (
    click_first_visible,
    close_all_modals,
    join_url,
    wait_for_network_idle,
)


def test_join_url_normalizes_slashes():
    assert join_url("https://example.com/wp-admin/", "/post-new.php") == (
        "https://example.com/wp-admin/post-new.php"
    )


class FakeElement:
    def __init__(self, visible=True, enabled=True):
        self.visible = visible
        self.enabled = enabled
        self.clicked = False

    def is_visible(self, timeout=0):
        return self.visible

    def is_enabled(self):
        return self.enabled

    def click(self, **kwargs):
        self.clicked = True


class FakeLocator:
    def __init__(self, element):
        self.first = element
        self.last = element


class FakePage:
    def __init__(self, elements):
        self.elements = elements

    def locator(self, selector):
        return FakeLocator(self.elements[selector])


def test_click_first_visible_skips_disabled_when_required():
    first = FakeElement(visible=True, enabled=False)
    second = FakeElement(visible=True, enabled=True)
    page = FakePage({"#disabled": first, "#enabled": second})

    assert click_first_visible(page, ["#disabled", "#enabled"], require_enabled=True)
    assert not first.clicked
    assert second.clicked


def test_wait_for_network_idle_swallows_page_errors():
    class ErrorPage:
        def wait_for_load_state(self, *args, **kwargs):
            raise RuntimeError("network never idle")

    wait_for_network_idle(ErrorPage())


def test_close_all_modals_swallows_page_errors():
    class ErrorKeyboard:
        def press(self, *args, **kwargs):
            raise RuntimeError("keyboard unavailable")

    class ErrorPage:
        keyboard = ErrorKeyboard()

    close_all_modals(ErrorPage())
