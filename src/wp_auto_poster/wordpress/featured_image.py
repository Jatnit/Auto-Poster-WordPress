"""Featured image workflow for WordPress Classic Editor."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from wp_auto_poster.wordpress.browser import close_all_modals

LogFunc = Callable[[str, str], None]


@dataclass
class FeaturedImageRuntime:
    state: Any
    log_func: LogFunc

    def log(self, message: str, level: str = "info") -> None:
        self.log_func(message, level)

    def ensure_tracking(self) -> None:
        if not hasattr(self.state, "used_featured_images"):
            self.state.used_featured_images = set()


def open_featured_image_modal(page, runtime: FeaturedImageRuntime) -> bool:
    """Open WordPress featured-image media modal using existing fallbacks."""
    close_all_modals(page)
    time.sleep(0.5)

    try:
        result = page.evaluate(
            """() => {
                const link = document.querySelector('#set-post-thumbnail') ||
                             document.querySelector('a[href*="type=set-post-thumbnail"]') ||
                             document.querySelector('#postimagediv a');
                if (link) {
                    link.click();
                    return 'clicked';
                }
                return 'not_found';
            }"""
        )
        runtime.log(f"JS click result: {result}", "info")
        time.sleep(3)

        modal_info = page.evaluate(
            """() => {
                const modals = [];
                if (document.querySelector('.media-modal')) modals.push('media-modal');
                if (document.querySelector('.media-frame')) modals.push('media-frame');
                if (document.querySelector('#TB_window')) modals.push('TB_window');
                if (document.querySelector('.media-modal-content')) modals.push('media-modal-content');
                if (document.querySelector('.attachment-details')) modals.push('attachment-details');
                return modals.length > 0 ? modals.join(', ') : 'none';
            }"""
        )
        runtime.log(f"Modal elements found: {modal_info}", "info")

        if modal_info != "none":
            runtime.log("Modal detected via JS check", "info")
            return True

        try:
            page.wait_for_selector(".media-modal, .media-frame, #TB_window", timeout=3000)
            runtime.log("Media modal opened via JS click", "info")
            return True
        except Exception:
            pass
    except Exception as e:
        runtime.log(f"JS click failed: {e}", "warning")

    try:
        link = page.locator("#set-post-thumbnail, #postimagediv a").first
        if link.is_visible(timeout=2000):
            link.click(force=True)
            time.sleep(3)
            try:
                page.wait_for_selector(".media-modal, #TB_window, .media-frame", timeout=5000)
                runtime.log("Modal opened via force click", "info")
                return True
            except Exception:
                pass
    except Exception:
        pass

    try:
        result = page.evaluate(
            """() => {
                if (typeof wp !== 'undefined' && wp.media) {
                    const frame = wp.media({
                        title: 'Chọn ảnh đại diện',
                        button: { text: 'Đặt ảnh đại diện' },
                        library: { type: 'image' },
                        multiple: false
                    });
                    frame.open();
                    return 'opened';
                }
                return 'wp_not_found';
            }"""
        )
        runtime.log(f"WP media frame: {result}", "info")
        time.sleep(3)

        try:
            page.wait_for_selector(
                ".media-modal, #TB_window, .media-frame, .media-modal-content",
                timeout=8000,
            )
            runtime.log("Modal opened via wp.media", "info")
            return True
        except Exception:
            time.sleep(2)
            if page.locator(".media-modal, .media-frame").count() > 0:
                runtime.log("Modal found after extra wait", "info")
                return True
    except Exception as e:
        runtime.log(f"WP media frame failed: {e}", "warning")

    return False


def switch_featured_media_library_tab(page, runtime: FeaturedImageRuntime) -> None:
    try:
        media_lib_tab = page.locator(
            ".media-menu-item:has-text('Thư viện Media'), "
            ".media-menu-item:has-text('Media Library'), "
            ".media-menu-item:has-text('Chọn từ thư viện')"
        ).first
        if media_lib_tab.is_visible(timeout=1000):
            media_lib_tab.click()
            time.sleep(2)
            runtime.log("Switched to Media Library", "info")
    except Exception:
        pass


def select_featured_attachment(page, runtime: FeaturedImageRuntime) -> bool:
    runtime.ensure_tracking()
    try:
        result = page.evaluate(
            """(usedIndices) => {
                const attachments = document.querySelectorAll('.attachments .attachment, li.attachment, .attachment');
                if (attachments.length === 0) return { success: false, error: 'no_images' };

                const availableIndices = [];
                for (let i = 0; i < Math.min(attachments.length, 30); i++) {
                    if (!usedIndices.includes(i)) {
                        availableIndices.push(i);
                    }
                }

                const indicesToUse = availableIndices.length > 0 ? availableIndices :
                    Array.from({length: Math.min(attachments.length, 30)}, (_, i) => i);

                const randomIndex = indicesToUse[Math.floor(Math.random() * indicesToUse.length)];
                const img = attachments[randomIndex];

                if (img) {
                    img.click();
                    return { success: true, index: randomIndex, total: attachments.length, available: indicesToUse.length };
                }
                return { success: false, error: 'click_failed' };
            }""",
            list(runtime.state.used_featured_images),
        )

        if result.get("success"):
            selected_idx = result.get("index", 0)
            runtime.state.used_featured_images.add(selected_idx)
            runtime.log(
                f"Selected image #{selected_idx + 1} via JS "
                f"({result.get('available')} available of {result.get('total')})",
                "info",
            )
            time.sleep(1)
            return True

        runtime.log(f"Could not select image: {result.get('error')}", "warning")
        return False
    except Exception as e:
        runtime.log(f"Error selecting image via JS: {e}", "warning")
        return False


def set_featured_alt_text(page, keyword: str, runtime: FeaturedImageRuntime) -> None:
    time.sleep(1)
    try:
        page.evaluate(
            """(keyword) => {
                const altInput = document.querySelector("input[data-setting='alt']") ||
                                document.querySelector("#attachment-details-alt-text") ||
                                document.querySelector(".attachment-details input[type='text']");
                if (altInput) {
                    altInput.value = keyword;
                    altInput.dispatchEvent(new Event('input', { bubbles: true }));
                    altInput.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                return false;
            }""",
            keyword,
        )
        runtime.log(f"Alt text: {keyword}", "info")
    except Exception:
        pass


def click_set_featured_image_button(page, runtime: FeaturedImageRuntime) -> bool:
    button_selectors = [
        "button.media-button-select",
        "button:has-text('Đặt ảnh đại diện')",
        "button:has-text('Set featured image')",
        ".media-button-select",
    ]

    for selector in button_selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=1000):
                button.click()
                runtime.log("Featured image set!", "success")
                time.sleep(1)
                return True
        except Exception:
            continue

    try:
        page.evaluate(
            """() => {
                const btn = document.querySelector('.media-button-select') ||
                           document.querySelector('button.button-primary');
                if (btn) btn.click();
            }"""
        )
        runtime.log("Featured image set via JS!", "success")
        time.sleep(1)
        return True
    except Exception:
        return False


def set_featured_image(page, keyword: str, runtime: FeaturedImageRuntime) -> bool:
    """Set a WordPress featured image using the existing resilient modal flow."""
    try:
        runtime.log("Setting featured image...", "info")

        if not open_featured_image_modal(page, runtime):
            runtime.log("Could not open media modal - skipping featured image", "warning")
            return False

        time.sleep(3)
        switch_featured_media_library_tab(page, runtime)
        time.sleep(2)

        if not select_featured_attachment(page, runtime):
            close_all_modals(page)
            return False

        set_featured_alt_text(page, keyword, runtime)

        if not click_set_featured_image_button(page, runtime):
            runtime.log("Could not click Set Featured Image button", "warning")
            close_all_modals(page)
            return False

        time.sleep(0.5)
        close_all_modals(page)
        return True

    except Exception as e:
        runtime.log(f"Error setting featured image: {e}", "warning")
        close_all_modals(page)
        return False
