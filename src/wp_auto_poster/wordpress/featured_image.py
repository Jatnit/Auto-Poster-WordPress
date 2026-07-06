"""Featured image workflow for WordPress Classic Editor."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from wp_auto_poster.wordpress.browser import close_all_modals
from wp_auto_poster.wordpress.media import (
    switch_to_media_library_tab,
    wait_for_visible_media_attachments,
)

LogFunc = Callable[[str, str], None]

FEATURED_IMAGE_POOL_SIZE = 50
FEATURED_IMAGE_POOL_BUFFER = 10
FEATURED_IMAGE_POOL_MAX_SIZE = 500
FEATURED_MEDIA_POLL_TIMEOUT_MS = 20000
FEATURED_MEDIA_POLL_INTERVAL_MS = 500


@dataclass
class FeaturedImageRuntime:
    state: Any
    log_func: LogFunc

    def log(self, message: str, level: str = "info") -> None:
        self.log_func(message, level)

    def ensure_tracking(self) -> None:
        if not hasattr(self.state, "used_featured_images"):
            self.state.used_featured_images = set()

    def featured_image_pool_size(self) -> int:
        topic_count = len(getattr(self.state, "topics", []))
        desired = max(FEATURED_IMAGE_POOL_SIZE, topic_count + FEATURED_IMAGE_POOL_BUFFER)
        return min(desired, FEATURED_IMAGE_POOL_MAX_SIZE)


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
    switch_to_media_library_tab(page, "featured image", log_func=runtime.log_func)


def select_featured_attachment(page, runtime: FeaturedImageRuntime) -> bool:
    runtime.ensure_tracking()
    try:
        pool_size = runtime.featured_image_pool_size()
        result = page.evaluate(
            """async ({ usedIds, poolSize }) => {
                const used = new Set((usedIds || []).map(String));
                const pickIndex = (max) => {
                    if (max <= 1) return 0;
                    if (window.crypto && crypto.getRandomValues) {
                        const bytes = new Uint32Array(1);
                        const maxUint = 0xffffffff;
                        const limit = maxUint - (maxUint % max);
                        do {
                            crypto.getRandomValues(bytes);
                        } while (bytes[0] >= limit);
                        return bytes[0] % max;
                    }
                    return Math.floor(Math.random() * max);
                };
                const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                const normalizeMedia = (data, modelIndex, model) => {
                    if (!data) return null;
                    if (data.type && data.type !== 'image') return null;
                    const sizes = data.sizes || {};
                    const preferred = sizes.large || sizes.medium_large ||
                        sizes.medium || sizes.full || null;
                    const url = (preferred && preferred.url) || data.url || '';
                    if (!url) return null;
                    const id = String(data.id || data.ID || url);
                    return {
                        id,
                        url,
                        alt: data.alt || '',
                        title: data.title || data.filename || '',
                        modelIndex,
                        model
                    };
                };
                const selectEntry = (entry, entries, source) => {
                    if (!entry) return null;
                    try {
                        const frame = window.wp && wp.media && wp.media.frame;
                        const frameState = frame && frame.state && frame.state();
                        const selection = frameState && frameState.get &&
                            frameState.get('selection');
                        if (selection && entry.model) {
                            selection.reset([entry.model]);
                        }
                    } catch (e) {}

                    try {
                        const el = Array.from(document.querySelectorAll('.attachment'))
                            .find((node) => String(node.getAttribute('data-id') || node.dataset.id || '') === entry.id);
                        if (el) {
                            try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
                            el.click();
                        }
                    } catch (e) {}

                    const selected = {
                        id: entry.id,
                        url: entry.url,
                        alt: entry.alt,
                        title: entry.title,
                        index: entry.modelIndex,
                        pool: entries.length,
                        source
                    };
                    window.__autoPosterSelectedFeaturedImage = selected;
                    return { success: true, selected };
                };

                try {
                    const frame = window.wp && wp.media && wp.media.frame;
                    const frameState = frame && frame.state && frame.state();
                    const library = frameState && frameState.get &&
                        frameState.get('library');
                    if (library && Array.isArray(library.models)) {
                        const loadTimeout = Math.max(12000, Math.min(30000, poolSize * 120));
                        const deadline = Date.now() + loadTimeout;
                        let stagnant = 0;
                        while (library.models.length < poolSize && Date.now() < deadline) {
                            let canLoadMore = true;
                            try {
                                if (typeof library.hasMore === 'function') {
                                    canLoadMore = !!library.hasMore();
                                }
                            } catch (e) {}
                            if (!canLoadMore || typeof library.more !== 'function') break;

                            const before = library.models.length;
                            try {
                                const req = library.more();
                                await new Promise((resolve) => {
                                    if (req && typeof req.always === 'function') {
                                        req.always(resolve);
                                    } else if (req && typeof req.then === 'function') {
                                        req.then(resolve, resolve);
                                    } else {
                                        setTimeout(resolve, 700);
                                    }
                                });
                            } catch (e) {
                                await sleep(700);
                            }

                            if (library.models.length <= before) {
                                stagnant += 1;
                                const scroller = document.querySelector(
                                    '.attachments-browser .attachments, ' +
                                    '.media-frame-content, .media-modal-content'
                                );
                                if (scroller) scroller.scrollTop = scroller.scrollHeight;
                                await sleep(500);
                                if (stagnant >= 2) break;
                            } else {
                                stagnant = 0;
                            }
                        }

                        const models = library.models.slice(0, Math.min(poolSize, library.models.length));
                        const entries = models
                            .map((model, index) => normalizeMedia(
                                model && model.toJSON && model.toJSON(),
                                index,
                                model
                            ))
                            .filter(Boolean);
                        if (entries.length) {
                            const unused = entries.filter((entry) =>
                                !used.has(entry.id) && !used.has(entry.url)
                            );
                            if (!unused.length) {
                                return {
                                    success: false,
                                    error: 'no_unused_featured_images_in_wp_media_pool',
                                    pool: entries.length,
                                    used: used.size
                                };
                            }
                            const pool = unused;
                            const entry = pool[pickIndex(pool.length)];
                            return selectEntry(entry, entries, 'wp.media');
                        }
                    }
                } catch (e) {}

                const attachments = Array.from(document.querySelectorAll(
                    '.media-modal .attachments .attachment, ' +
                    '.media-frame .attachments .attachment, ' +
                    '.attachments li.attachment, li.attachment'
                )).filter((el) => !el.classList.contains('uploading'));
                if (!attachments.length) return { success: false, error: 'no_images' };

                const entries = attachments
                    .slice(0, Math.min(attachments.length, poolSize))
                    .map((el, index) => {
                        const id = String(el.getAttribute('data-id') || el.dataset.id || '');
                        const img = el.querySelector('img');
                        const url = img && (img.currentSrc || img.src || '');
                        if (!url && !id) return null;
                        return {
                            id: id || url,
                            url,
                            alt: img ? (img.alt || '') : '',
                            title: img ? (img.alt || '') : '',
                            modelIndex: index,
                            element: el
                        };
                    })
                    .filter(Boolean);
                if (!entries.length) return { success: false, error: 'no_usable_images' };

                const unused = entries.filter((entry) =>
                    !used.has(entry.id) && !used.has(entry.url)
                );
                if (!unused.length) {
                    return {
                        success: false,
                        error: 'no_unused_featured_images_in_visible_pool',
                        pool: entries.length,
                        used: used.size
                    };
                }
                const pool = unused;
                const entry = pool[pickIndex(pool.length)];
                try { entry.element.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
                entry.element.click();
                return selectEntry(entry, entries, 'dom-visible');
            }""",
            {
                "usedIds": list(runtime.state.used_featured_images),
                "poolSize": pool_size,
            },
        )

        selected = result.get("selected") if result else None
        if result and result.get("success") and selected:
            selected_id = str(selected.get("id") or "")
            selected_url = str(selected.get("url") or "")
            if selected_id:
                runtime.state.used_featured_images.add(selected_id)
            if selected_url:
                runtime.state.used_featured_images.add(selected_url)
            runtime.log(
                f"Selected featured image #{int(selected.get('index', 0)) + 1} "
                f"from {selected.get('pool', 0)}/{pool_size} pool "
                f"({selected.get('source', 'media')})",
                "info",
            )
            time.sleep(0.8)
            return True

        runtime.log(f"Could not select featured image: {result.get('error')}", "warning")
        return False
    except Exception as e:
        runtime.log(f"Error selecting featured image via JS: {e}", "warning")
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

    deadline = time.time() + 5
    while time.time() < deadline:
        for selector in button_selectors:
            try:
                button = page.locator(selector).first
                if button.is_visible(timeout=500) and button.is_enabled(timeout=300):
                    button.click(timeout=1500)
                    runtime.log("Featured image set!", "success")
                    time.sleep(1)
                    return True
            except Exception:
                continue
        time.sleep(0.3)

    try:
        clicked = page.evaluate(
            """() => {
                const btn = document.querySelector('.media-button-select') ||
                           document.querySelector('button.button-primary');
                if (!btn || btn.disabled || btn.getAttribute('aria-disabled') === 'true') {
                    return false;
                }
                btn.click();
                return true;
            }"""
        )
        if clicked:
            runtime.log("Featured image set via JS!", "success")
            time.sleep(1)
            return True
    except Exception:
        pass

    try:
        result = page.evaluate(
            """() => {
                const selected = window.__autoPosterSelectedFeaturedImage || {};
                const id = String(selected.id || '').trim();
                if (!/^\\d+$/.test(id)) {
                    return { ok: false, reason: 'missing_numeric_attachment_id', id };
                }

                let input = document.querySelector('#_thumbnail_id, input[name="_thumbnail_id"]');
                if (!input) {
                    const form = document.querySelector('form#post, form[name="post"]') ||
                        document.querySelector('form');
                    if (!form) {
                        return { ok: false, reason: 'post_form_not_found', id };
                    }
                    input = document.createElement('input');
                    input.type = 'hidden';
                    input.id = '_thumbnail_id';
                    input.name = '_thumbnail_id';
                    form.appendChild(input);
                }

                input.value = id;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));

                try {
                    if (window.wp && wp.media && wp.media.featuredImage &&
                            typeof wp.media.featuredImage.set === 'function') {
                        wp.media.featuredImage.set(id);
                    }
                } catch (e) {}

                try {
                    const url = selected.url || '';
                    const postImageBox = document.querySelector('#postimagediv .inside');
                    const setLink = document.querySelector('#set-post-thumbnail');
                    if (postImageBox && setLink && url && !setLink.querySelector('img')) {
                        const img = document.createElement('img');
                        img.src = url;
                        img.alt = selected.alt || selected.title || '';
                        img.style.maxWidth = '100%';
                        setLink.textContent = '';
                        setLink.appendChild(img);
                    }
                } catch (e) {}

                return { ok: true, id };
            }"""
        )
        if result and result.get("ok"):
            runtime.log(
                f"Featured image set via _thumbnail_id fallback: {result.get('id')}",
                "success",
            )
            time.sleep(0.5)
            return True
        if result:
            runtime.log(
                f"Featured image fallback failed: {result.get('reason')} ({result.get('id', '')})",
                "warning",
            )
    except Exception as e:
        runtime.log(f"Featured image fallback failed: {e}", "warning")

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

        if not wait_for_visible_media_attachments(
            page,
            "featured image",
            FEATURED_MEDIA_POLL_TIMEOUT_MS,
            FEATURED_MEDIA_POLL_INTERVAL_MS,
            log_func=runtime.log_func,
        ):
            close_all_modals(page)
            return False

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
