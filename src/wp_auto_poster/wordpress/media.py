"""Media editor helpers for WordPress Classic Editor/TinyMCE."""

from __future__ import annotations

import time
from typing import Callable, Optional

from wp_auto_poster.wordpress.browser import click_first_selector_resilient, close_all_modals
from wp_auto_poster.wordpress.image_policy import get_inset_heading_candidates

LogFunc = Optional[Callable[[str, str], None]]

DEFAULT_MEDIA_STATUS = {
    "total": 0,
    "visible": 0,
    "libraryCount": 0,
    "loading": False,
    "noItems": False,
}

MEDIA_LIBRARY_TAB_SELECTORS = [
    ".media-menu-item:has-text('Thư viện Media')",
    ".media-menu-item:has-text('Thư viện')",
    ".media-menu-item:has-text('Media Library')",
    ".media-menu-item:has-text('Library')",
    ".media-menu-item:has-text('Chọn từ thư viện')",
    ".media-router a:has-text('Thư viện')",
    ".media-router a:has-text('Media Library')",
]


def _log(log_func: LogFunc, message: str, level: str) -> None:
    if log_func:
        log_func(message, level)


def format_heading_targets(indices: list) -> str:
    if not indices:
        return "none"
    return ", ".join(f"#{idx + 1}" for idx in indices)


def switch_to_visual_mode(page, log_func: LogFunc = None) -> None:
    """Best-effort switch to TinyMCE visual mode."""
    try:
        visual_tab = page.locator("#content-tmce").first
        if visual_tab.is_visible(timeout=2000):
            visual_tab.click()
            time.sleep(1)
            _log(log_func, "Switched to Visual mode", "info")
    except Exception as e:
        _log(log_func, f"Could not switch to Visual mode: {e}", "warning")


def select_visible_media_attachment(
    page,
    label: str,
    used_inline_images: set,
    used_inline_image_count: int,
    pool_size: int,
    log_func: LogFunc = None,
) -> tuple[bool, int]:
    """Select a random unused image from the WordPress media modal."""
    try:
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
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 1 &&
                        rect.height > 1 &&
                        rect.bottom > 0 &&
                        rect.right > 0 &&
                        rect.top < window.innerHeight &&
                        rect.left < window.innerWidth &&
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        style.opacity !== '0';
                };
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
                const rememberAndSelect = (entry, entries, source) => {
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
                    window.__autoPosterSelectedImage = selected;
                    return { ok: true, selected };
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
                                    ok: false,
                                    reason: 'no_unused_images_in_wp_media_pool',
                                    pool: entries.length,
                                    used: used.size
                                };
                            }
                            const pool = unused;
                            const entry = pool[pickIndex(pool.length)];
                            return rememberAndSelect(
                                entry,
                                entries,
                                'wp.media'
                            );
                        }
                    }
                } catch (e) {}

                const all = Array.from(document.querySelectorAll(
                    '.media-modal .attachments .attachment, ' +
                    '.media-frame .attachments .attachment, ' +
                    '.attachments li.attachment, li.attachment'
                )).filter((el) => !el.classList.contains('uploading'));

                let visible = all.filter(isVisible);
                if (!visible.length) {
                    const scroller = document.querySelector(
                        '.attachments-browser .attachments, .media-frame-content, .media-modal-content'
                    );
                    if (scroller) scroller.scrollTop = 0;
                    visible = all.filter(isVisible);
                }
                if (!visible.length) {
                    return { ok: false, reason: 'no_visible_attachments', total: all.length };
                }

                const entries = visible
                    .slice(0, Math.min(visible.length, poolSize))
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
                if (!entries.length) {
                    return { ok: false, reason: 'no_usable_visible_attachments', total: all.length };
                }

                const unused = entries.filter((entry) =>
                    !used.has(entry.id) && !used.has(entry.url)
                );
                if (!unused.length) {
                    return {
                        ok: false,
                        reason: 'no_unused_images_in_visible_pool',
                        pool: entries.length,
                        used: used.size
                    };
                }
                const pool = unused;
                const localIndex = pickIndex(pool.length);
                const el = pool[localIndex];
                try { el.element.scrollIntoView({ block: 'center', inline: 'center' }); } catch (e) {}
                el.element.click();
                window.__autoPosterSelectedImage = {
                    id: el.id,
                    url: el.url,
                    alt: el.alt,
                    title: el.title,
                    index: el.modelIndex,
                    pool: entries.length,
                    source: 'dom-visible'
                };
                return { ok: true, selected: window.__autoPosterSelectedImage };
            }""",
            {
                "usedIds": list(used_inline_images),
                "poolSize": pool_size,
            },
        )
        selected = result.get("selected") if result else None
        if result and result.get("ok") and selected:
            selected_id = str(selected.get("id") or "")
            selected_url = str(selected.get("url") or "")
            if selected_id:
                used_inline_images.add(selected_id)
            if selected_url:
                used_inline_images.add(selected_url)
            used_inline_image_count += 1
            _log(
                log_func,
                f"Selected unique inline image #{used_inline_image_count}: "
                f"media item {int(selected.get('index', 0)) + 1} "
                f"from {selected.get('pool', 0)}/{pool_size} pool "
                f"({selected.get('source', 'media')}) for {label}",
                "info",
            )
            time.sleep(0.8)
            return True, used_inline_image_count

        reason = result.get("reason") if result else "no_result"
        total = (result.get("total") or result.get("pool") or 0) if result else 0
        _log(
            log_func,
            f"Select image fail for {label}: {reason} "
            f"(pool={total}/{pool_size}, selected unique images={used_inline_image_count})",
            "warning",
        )
        return False, used_inline_image_count
    except Exception as e:
        _log(log_func, f"Select image fail for {label}: {e}", "warning")
        return False, used_inline_image_count


def get_media_attachment_status(page) -> dict:
    try:
        return page.evaluate(
            """() => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 1 &&
                        rect.height > 1 &&
                        rect.bottom > 0 &&
                        rect.right > 0 &&
                        rect.top < window.innerHeight &&
                        rect.left < window.innerWidth &&
                        style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        style.opacity !== '0';
                };

                const all = Array.from(document.querySelectorAll(
                    '.media-modal .attachments .attachment, ' +
                    '.media-frame .attachments .attachment, ' +
                    '.attachments li.attachment, li.attachment'
                )).filter((el) => !el.classList.contains('uploading'));

                const visible = all.filter(isVisible);
                const loading = !!document.querySelector(
                    '.media-frame .spinner.is-active, ' +
                    '.media-modal .spinner.is-active, ' +
                    '.attachments-browser .spinner.is-active'
                );
                const noItems = !!document.querySelector(
                    '.media-frame .no-media, .media-modal .no-media, .attachments .no-media'
                );
                let libraryCount = 0;
                try {
                    const frame = window.wp && wp.media && wp.media.frame;
                    const frameState = frame && frame.state && frame.state();
                    const library = frameState && frameState.get &&
                        frameState.get('library');
                    libraryCount = library && Array.isArray(library.models) ?
                        library.models.length : 0;
                } catch (e) {}

                return {
                    total: all.length,
                    visible: visible.length,
                    libraryCount,
                    loading,
                    noItems
                };
            }"""
        ) or DEFAULT_MEDIA_STATUS.copy()
    except Exception:
        return DEFAULT_MEDIA_STATUS.copy()


def switch_to_media_library_tab(
    page,
    label: str,
    log_func: LogFunc = None,
    timeout_ms: int = 1000,
) -> None:
    if click_first_selector_resilient(
        page,
        MEDIA_LIBRARY_TAB_SELECTORS,
        f"Media Library tab for {label}",
        log_func=log_func,
        timeout_ms=timeout_ms,
    ):
        time.sleep(0.5)


def wait_for_visible_media_attachments(
    page,
    label: str,
    timeout_ms: int,
    poll_interval_ms: int,
    log_func: LogFunc = None,
) -> bool:
    deadline = time.time() + (timeout_ms / 1000)
    last_status = DEFAULT_MEDIA_STATUS.copy()
    switched_tab = False

    while time.time() < deadline:
        if not switched_tab:
            switch_to_media_library_tab(page, label, log_func=log_func)
            switched_tab = True

        last_status = get_media_attachment_status(page)
        if (
            int(last_status.get("visible", 0)) > 0 or
            int(last_status.get("libraryCount", 0)) > 0
        ):
            return True

        if last_status.get("noItems"):
            break

        time.sleep(poll_interval_ms / 1000)

    _log(
        log_func,
        f"No visible images in media library for {label} sau khi chờ {timeout_ms}ms "
        f"(total={last_status.get('total', 0)}, "
        f"visible={last_status.get('visible', 0)}, "
        f"library={last_status.get('libraryCount', 0)}, "
        f"loading={last_status.get('loading', False)})",
        "warning",
    )
    return False


def count_imgs_in_iframe(page) -> int:
    """Count valid app-inserted images in the TinyMCE iframe."""
    try:
        return int(
            page.frame_locator("#content_ifr").locator("body").evaluate(
                "() => document.querySelectorAll('img.wp-image-auto-poster').length"
            )
        )
    except Exception:
        return 0


def get_h2_elements_in_iframe(page, heading_selector: str) -> list:
    """Re-fetch safe heading locators from the TinyMCE iframe."""
    try:
        time.sleep(0.3)
        return page.frame_locator("#content_ifr").locator(heading_selector).all()
    except Exception:
        return []


def img_is_after_h2(page, h2_index: int) -> bool:
    """Return True when an auto image is immediately after a safe H2/H3."""
    try:
        return page.frame_locator("#content_ifr").locator("body").evaluate(
            """(_, idx) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const allHeadings = Array.from(document.querySelectorAll('h2, h3'));
                const contactIndex = allHeadings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                const h2s = contactIndex >= 0 ?
                    allHeadings.slice(0, contactIndex) : allHeadings;
                if (idx >= h2s.length) return false;
                const h2 = h2s[idx];
                let cur = h2.nextElementSibling;
                for (let i = 0; i < 2 && cur; i++) {
                    if (cur.matches && cur.matches('img.wp-image-auto-poster')) return true;
                    if (cur.querySelector && cur.querySelector('img.wp-image-auto-poster')) return true;
                    cur = cur.nextElementSibling;
                }
                return false;
            }""",
            h2_index,
        )
    except Exception:
        return False


def get_heading_count_in_iframe(page) -> int:
    try:
        return int(
            page.frame_locator("#content_ifr").locator("body").evaluate(
                """() => {
                    const headings = Array.from(document.querySelectorAll('h2, h3'));
                    const contactIndex = headings.findIndex((heading) =>
                        /th[oô]ng tin li[eê]n h[eệ]|thong tin lien he/i.test(
                            (heading.textContent || '').trim()
                        )
                    );
                    return contactIndex >= 0 ? contactIndex : headings.length;
                }"""
            )
        )
    except Exception:
        return 0


def get_contact_heading_index(page) -> Optional[int]:
    try:
        index = page.frame_locator("#content_ifr").locator("body").evaluate(
            """() => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const headings = Array.from(document.querySelectorAll('h2, h3'));
                const idx = headings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                return idx >= 0 ? idx : null;
            }"""
        )
        return int(index) if index is not None else None
    except Exception:
        return None


def get_safe_heading_count_for_images(page) -> int:
    return get_heading_count_in_iframe(page)


def find_unfilled_target_h2(page, target_indices: list, heading_selector: str) -> list:
    h2_elements = get_h2_elements_in_iframe(page, heading_selector)
    n = len(h2_elements)
    unfilled = []
    for idx in target_indices:
        if idx >= n:
            continue
        if not img_is_after_h2(page, idx):
            unfilled.append(idx)
    return unfilled


def find_other_unfilled_h2(page, exclude_indices: set) -> list:
    total = get_safe_heading_count_for_images(page)
    candidates = get_inset_heading_candidates(total)
    result = []
    for idx in candidates:
        if idx in exclude_indices:
            continue
        if not img_is_after_h2(page, idx):
            result.append(idx)
    return result


def rebalance_auto_images_to_targets(
    page,
    target_indices: list,
    log_func: LogFunc = None,
) -> int:
    if not target_indices:
        return 0
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body, targetIndices) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const allHeadings = Array.from(body.querySelectorAll('h2, h3'));
                const contactIndex = allHeadings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                const headings = contactIndex >= 0 ?
                    allHeadings.slice(0, contactIndex) : allHeadings;
                const validTargets = targetIndices.filter((idx) => idx < headings.length);
                const wrapperFor = (img) => img.closest('p, figure') || img;
                const contactHeading = contactIndex >= 0 ? allHeadings[contactIndex] : null;
                const isBeforeContact = (node) => {
                    if (!contactHeading) return true;
                    return !!(node.compareDocumentPosition(contactHeading) &
                        Node.DOCUMENT_POSITION_FOLLOWING);
                };
                const imageNearHeading = (idx) => {
                    const heading = headings[idx];
                    let cur = heading ? heading.nextElementSibling : null;
                    for (let i = 0; i < 2 && cur; i++) {
                        if (cur.matches && cur.matches('img.wp-image-auto-poster')) return cur;
                        const img = cur.querySelector && cur.querySelector('img.wp-image-auto-poster');
                        if (img) return img;
                        cur = cur.nextElementSibling;
                    }
                    return null;
                };

                const usedWrappers = new Set();
                const missing = [];
                for (const idx of validTargets) {
                    const img = imageNearHeading(idx);
                    if (img) {
                        usedWrappers.add(wrapperFor(img));
                    } else {
                        missing.push(idx);
                    }
                }

                if (!missing.length) {
                    return { moved: 0, missing: 0, available: 0 };
                }

                const autoWrappers = Array.from(
                    body.querySelectorAll('img.wp-image-auto-poster')
                )
                    .map(wrapperFor)
                    .filter((node, idx, arr) => node && arr.indexOf(node) === idx);
                const afterContact = autoWrappers.filter((node) => !isBeforeContact(node));
                const beforeContactSpare = autoWrappers.filter((node) =>
                    isBeforeContact(node) && !usedWrappers.has(node)
                );
                const spare = afterContact.concat(beforeContactSpare);

                let moved = 0;
                for (const idx of missing) {
                    const node = spare.shift();
                    if (!node) break;
                    headings[idx].insertAdjacentElement('afterend', node);
                    moved += 1;
                }
                return { moved, missing: missing.length, available: autoWrappers.length };
            }""",
            target_indices,
        )
        moved = int((result or {}).get("moved", 0))
        if moved:
            sync_editor_after_direct_insert(page)
            _log(log_func, f"Final scan rebalanced {moved} image(s) to target headings", "success")
        return moved
    except Exception as e:
        _log(log_func, f"Final image rebalance failed: {e}", "warning")
        return 0


def remove_or_move_images_after_contact(
    page,
    target_indices: list,
    log_func: LogFunc = None,
) -> int:
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body, targetIndices) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\\s+/g, ' ')
                    .trim();
                const headings = Array.from(body.querySelectorAll('h2, h3'));
                const contactIndex = headings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                if (contactIndex < 0) {
                    return { moved: 0, removed: 0, after: 0 };
                }
                const contactHeading = headings[contactIndex];
                const safeHeadings = headings.slice(0, contactIndex);
                const wrapperFor = (img) => img.closest('p, figure') || img;
                const isAfterContact = (node) => {
                    return !!(node.compareDocumentPosition(contactHeading) &
                        Node.DOCUMENT_POSITION_PRECEDING);
                };
                const imageNearHeading = (idx) => {
                    const heading = safeHeadings[idx];
                    let cur = heading ? heading.nextElementSibling : null;
                    for (let i = 0; i < 2 && cur; i++) {
                        if (cur.matches && cur.matches('img.wp-image-auto-poster')) return cur;
                        const img = cur.querySelector && cur.querySelector('img.wp-image-auto-poster');
                        if (img) return img;
                        cur = cur.nextElementSibling;
                    }
                    return null;
                };
                const afterWrappers = Array.from(
                    body.querySelectorAll('img.wp-image-auto-poster')
                )
                    .map(wrapperFor)
                    .filter((node, idx, arr) =>
                        node && arr.indexOf(node) === idx && isAfterContact(node)
                    );
                let moved = 0;
                let removed = 0;
                for (const node of afterWrappers) {
                    const target = targetIndices.find((idx) =>
                        idx < safeHeadings.length && !imageNearHeading(idx)
                    );
                    if (target !== undefined) {
                        safeHeadings[target].insertAdjacentElement('afterend', node);
                        moved += 1;
                    } else {
                        node.remove();
                        removed += 1;
                    }
                }
                return { moved, removed, after: afterWrappers.length };
            }""",
            target_indices,
        ) or {}
        changed = int(result.get("moved", 0)) + int(result.get("removed", 0))
        if changed:
            sync_editor_after_direct_insert(page)
            _log(
                log_func,
                f"Contact boundary cleanup: moved {result.get('moved', 0)}, "
                f"removed {result.get('removed', 0)} image(s) after contact section",
                "success",
            )
        return changed
    except Exception as e:
        _log(log_func, f"Contact boundary cleanup failed: {e}", "warning")
        return 0


def wait_for_img_count_increase(
    page,
    count_before: int,
    timeout_ms: int,
    interval_ms: int,
) -> int:
    deadline = time.time() + (timeout_ms / 1000)
    latest = count_before
    while time.time() < deadline:
        latest = count_imgs_in_iframe(page)
        if latest > count_before:
            return latest
        time.sleep(interval_ms / 1000)
    return latest


def finalize_inline_image_insert(
    page,
    max_images: int,
    reason: str,
    log_func: LogFunc = None,
) -> bool:
    """Close media modal, remove invalid images, and report final image count."""
    close_all_modals(page)
    remove_non_auto_images_from_editor(page, f"finalize {reason}", log_func=log_func)
    final = count_imgs_in_iframe(page)
    if final > max_images:
        _log(
            log_func,
            f"Total images inserted: {max_images}/{max_images} "
            f"(DOM currently has {final}; stopped at cap)",
            "warning",
        )
    elif final >= max_images:
        _log(log_func, f"Total images inserted: {final}/{max_images}", "success")
    else:
        _log(
            log_func,
            f"Total images inserted: {final}/{max_images} "
            f"(reason={reason}) — proceeding without blocking post",
            "warning",
        )
    return final > 0


def get_selected_media_image(page, fallback_alt: str, log_func: LogFunc = None) -> Optional[dict]:
    try:
        image = page.evaluate(
            """(fallbackAlt) => {
                const normalize = (data, id) => {
                    if (!data) return null;
                    const sizes = data.sizes || {};
                    const preferred = sizes.large || sizes.medium_large ||
                        sizes.medium || sizes.full || null;
                    const url = (preferred && preferred.url) || data.url || '';
                    if (!url) return null;
                    return {
                        id: id || data.id || '',
                        url,
                        alt: data.alt || fallbackAlt,
                        title: data.title || data.filename || fallbackAlt
                    };
                };

                if (window.__autoPosterSelectedImage &&
                    window.__autoPosterSelectedImage.url) {
                    return {
                        id: window.__autoPosterSelectedImage.id || '',
                        url: window.__autoPosterSelectedImage.url,
                        alt: window.__autoPosterSelectedImage.alt || fallbackAlt,
                        title: window.__autoPosterSelectedImage.title || fallbackAlt
                    };
                }

                try {
                    const frame = window.wp && wp.media && wp.media.frame;
                    const selection = frame && frame.state &&
                        frame.state().get('selection');
                    const model = selection && selection.first && selection.first();
                    const data = model && model.toJSON && model.toJSON();
                    const fromFrame = normalize(data, data && data.id);
                    if (fromFrame) return fromFrame;
                } catch (e) {}

                const selected = document.querySelector(
                    '.attachment.selected, .attachment[aria-checked="true"]'
                );
                const id = selected && (
                    selected.getAttribute('data-id') || selected.dataset.id
                );
                try {
                    if (id && window.wp && wp.media && wp.media.attachment) {
                        const data = wp.media.attachment(id).toJSON();
                        const fromAttachment = normalize(data, id);
                        if (fromAttachment) return fromAttachment;
                    }
                } catch (e) {}

                const detailImg = document.querySelector(
                    '.attachment-details .thumbnail img, ' +
                    '.attachment-info .thumbnail img, ' +
                    '.media-sidebar .thumbnail img, ' +
                    '.attachment.selected img'
                );
                const url = detailImg && (detailImg.currentSrc || detailImg.src);
                if (url) {
                    return {
                        id: id || '',
                        url,
                        alt: detailImg.alt || fallbackAlt,
                        title: detailImg.alt || fallbackAlt
                    };
                }

                return null;
            }""",
            fallback_alt,
        )
        if image and image.get("url"):
            return image
    except Exception as e:
        _log(log_func, f"Could not read selected media image: {e}", "warning")
    return None


def sync_editor_after_direct_insert(page) -> None:
    try:
        page.evaluate(
            """() => {
                if (window.tinymce) {
                    const ed = tinymce.get('content');
                    if (ed) {
                        try { ed.nodeChanged(); } catch (e) {}
                        try { ed.save(); } catch (e) {}
                        try {
                            const ta = document.getElementById('content');
                            if (ta) ta.value = ed.getContent({ format: 'html' });
                        } catch (e) {}
                    }
                    try { tinymce.triggerSave(); } catch (e) {}
                }
                const ta = document.getElementById('content');
                if (ta) {
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                    ta.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }"""
        )
    except Exception:
        pass


def remove_non_auto_images_from_editor(
    page,
    reason: str = "scan",
    log_func: LogFunc = None,
) -> int:
    """Remove generated/logo images so only app-inserted images count as valid."""
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body) => {
                const autoSelector = 'img.wp-image-auto-poster';
                let removed = 0;

                const removeNode = (node) => {
                    if (!node || !node.parentNode) return false;
                    node.remove();
                    removed += 1;
                    return true;
                };

                const nonAutoImages = Array.from(body.querySelectorAll('img'))
                    .filter((img) => !img.classList.contains('wp-image-auto-poster'));
                for (const img of nonAutoImages) {
                    const mediaWrapper = img.closest('picture, figure');
                    if (mediaWrapper && !mediaWrapper.querySelector(autoSelector)) {
                        removeNode(mediaWrapper);
                    } else {
                        removeNode(img);
                    }
                }

                for (const svg of Array.from(body.querySelectorAll('svg'))) {
                    const mediaWrapper = svg.closest('picture, figure');
                    if (mediaWrapper && !mediaWrapper.querySelector(autoSelector)) {
                        removeNode(mediaWrapper);
                    } else {
                        removeNode(svg);
                    }
                }

                // Clean up empty wrappers/anchors left behind after logo removal.
                for (const node of Array.from(body.querySelectorAll('p, figure, picture, a'))) {
                    if (!node.parentNode || node.querySelector(autoSelector)) continue;
                    const text = (node.textContent || '').replace(/\u00a0/g, ' ').trim();
                    const hasMedia = node.querySelector('img, svg, picture, figure');
                    if (!text && !hasMedia) {
                        node.remove();
                    }
                }

                return {
                    removed,
                    valid: body.querySelectorAll(autoSelector).length,
                    all: body.querySelectorAll('img').length
                };
            }"""
        ) or {}
        removed = int(result.get("removed", 0))
        if removed:
            sync_editor_after_direct_insert(page)
            _log(
                log_func,
                f"Removed {removed} non-auto/logo image(s) from editor ({reason}); "
                f"valid auto images={result.get('valid', 0)}",
                "warning",
            )
        return removed
    except Exception:
        return 0


def insert_selected_image_after_h2_direct(
    page,
    h2_index: int,
    image: dict,
    keyword: str,
    log_func: LogFunc = None,
) -> bool:
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body, args) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\u0300-\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\s+/g, ' ')
                    .trim();
                const allHeadings = Array.from(body.querySelectorAll('h2, h3'));
                const contactIndex = allHeadings.findIndex((heading) =>
                    normalize(heading.textContent).includes('thong tin lien he')
                );
                const h2s = contactIndex >= 0 ?
                    allHeadings.slice(0, contactIndex) : allHeadings;
                if (args.h2Index >= h2s.length) {
                    return { ok: false, reason: 'h2_not_found', count: h2s.length };
                }
                const doc = body.ownerDocument;
                const wrapper = doc.createElement('p');
                const img = doc.createElement('img');
                img.src = args.url;
                img.alt = args.alt || args.keyword;
                img.title = args.title || args.keyword;
                img.loading = 'lazy';
                img.decoding = 'async';
                img.className = 'aligncenter size-full wp-image-auto-poster';
                wrapper.appendChild(img);
                h2s[args.h2Index].insertAdjacentElement('afterend', wrapper);
                return { ok: true, count: body.querySelectorAll('img.wp-image-auto-poster').length };
            }""",
            {
                "h2Index": h2_index,
                "url": image.get("url", ""),
                "alt": image.get("alt") or keyword,
                "title": image.get("title") or keyword,
                "keyword": keyword,
            },
        )
        if result and result.get("ok"):
            sync_editor_after_direct_insert(page)
            _log(log_func, f"Inserted selected image directly under H2 #{h2_index + 1}", "success")
            return True
        reason = result.get("reason") if result else "no_result"
        _log(log_func, f"Direct insert under H2 #{h2_index + 1} failed: {reason}", "warning")
    except Exception as e:
        _log(log_func, f"Direct insert under H2 #{h2_index + 1} failed: {e}", "warning")
    return False


def insert_selected_image_after_paragraph_direct(
    page,
    slot_hint: str,
    image: dict,
    keyword: str,
    log_func: LogFunc = None,
) -> bool:
    try:
        result = page.frame_locator("#content_ifr").locator("body").evaluate(
            """(body, args) => {
                const normalize = (value) => (value || '')
                    .normalize('NFD')
                    .replace(/[\u0300-\u036f]/g, '')
                    .toLowerCase()
                    .replace(/\s+/g, ' ')
                    .trim();
                const contactHeading = Array.from(body.querySelectorAll('h2, h3'))
                    .find((heading) =>
                        normalize(heading.textContent).includes('thong tin lien he')
                    );
                const isBeforeContact = (node) => {
                    if (!contactHeading) return true;
                    return !!(node.compareDocumentPosition(contactHeading) &
                        Node.DOCUMENT_POSITION_FOLLOWING);
                };
                const paragraphs = Array.from(body.querySelectorAll('p'))
                    .filter(isBeforeContact);
                if (!paragraphs.length) {
                    return { ok: false, reason: 'no_safe_paragraphs_before_contact' };
                }
                let target = paragraphs[0];
                if (args.slot === 'middle') {
                    target = paragraphs[Math.floor(paragraphs.length / 2)];
                } else if (args.slot === 'bottom') {
                    target = paragraphs[paragraphs.length - 1];
                }
                const doc = body.ownerDocument;
                const wrapper = doc.createElement('p');
                const img = doc.createElement('img');
                img.src = args.url;
                img.alt = args.alt || args.keyword;
                img.title = args.title || args.keyword;
                img.loading = 'lazy';
                img.decoding = 'async';
                img.className = 'aligncenter size-full wp-image-auto-poster';
                wrapper.appendChild(img);
                target.insertAdjacentElement('afterend', wrapper);
                return { ok: true, count: body.querySelectorAll('img.wp-image-auto-poster').length };
            }""",
            {
                "slot": slot_hint,
                "url": image.get("url", ""),
                "alt": image.get("alt") or keyword,
                "title": image.get("title") or keyword,
                "keyword": keyword,
            },
        )
        if result and result.get("ok"):
            sync_editor_after_direct_insert(page)
            _log(log_func, f"Fallback ({slot_hint}): inserted selected image directly", "success")
            return True
        reason = result.get("reason") if result else "no_result"
        _log(log_func, f"Fallback ({slot_hint}) direct insert failed: {reason}", "warning")
    except Exception as e:
        _log(log_func, f"Fallback ({slot_hint}) direct insert failed: {e}", "warning")
    return False
