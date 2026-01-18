from typing import Optional
from config.settings import add_log, BROWSER_DATA_DIR

_playwright = None
_browser = None
_context = None
PLAYWRIGHT_AVAILABLE = False


def _init_playwright():
    global _playwright, PLAYWRIGHT_AVAILABLE
    if _playwright is None:
        try:
            from playwright.sync_api import sync_playwright
            _playwright = sync_playwright().start()
            PLAYWRIGHT_AVAILABLE = True
            add_log("Playwright initialized", "info")
        except ImportError:
            add_log("Playwright not available", "error")
            PLAYWRIGHT_AVAILABLE = False
    return _playwright


def get_browser(headless: bool = True):
    global _browser
    
    playwright = _init_playwright()
    if playwright is None:
        return None
    
    if _browser is None or not _browser.is_connected():
        try:
            _browser = playwright.chromium.launch_persistent_context(
                BROWSER_DATA_DIR,
                headless=headless,
                viewport={"width": 1280, "height": 800},
                locale="vi-VN",
                timezone_id="Asia/Ho_Chi_Minh",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )
            add_log("Browser launched", "info")
        except Exception as e:
            add_log(f"Failed to launch browser: {e}", "error")
            return None
    
    return _browser


def get_page(headless: bool = True):
    browser = get_browser(headless)
    if browser is None:
        return None
    
    try:
        page = browser.new_page()
        return page
    except Exception as e:
        add_log(f"Failed to create page: {e}", "error")
        return None


def close_browser():
    global _browser, _playwright
    
    if _browser:
        try:
            _browser.close()
            add_log("Browser closed", "info")
        except:
            pass
        _browser = None
    
    if _playwright:
        try:
            _playwright.stop()
        except:
            pass
        _playwright = None


def is_playwright_available():
    global PLAYWRIGHT_AVAILABLE
    if not PLAYWRIGHT_AVAILABLE:
        _init_playwright()
    return PLAYWRIGHT_AVAILABLE
