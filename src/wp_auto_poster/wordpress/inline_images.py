"""Stateful inline image insertion workflow for WordPress posts."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from wp_auto_poster.wordpress.browser import close_all_modals, click_first_selector_resilient
from wp_auto_poster.wordpress.image_policy import (
    INLINE_IMAGE_RANDOM_POOL_BUFFER,
    INLINE_IMAGE_RANDOM_POOL_MAX_SIZE,
    INLINE_IMAGE_RANDOM_POOL_MIN_SIZE,
    get_inline_image_random_pool_size,
    pick_inset_evenly_spaced_indices,
    select_even_candidates,
)
from wp_auto_poster.wordpress.media import (
    count_imgs_in_iframe,
    finalize_inline_image_insert,
    find_other_unfilled_h2,
    find_unfilled_target_h2,
    format_heading_targets,
    get_contact_heading_index,
    get_h2_elements_in_iframe,
    get_safe_heading_count_for_images,
    get_selected_media_image,
    img_is_after_h2,
    insert_selected_image_after_h2_direct,
    insert_selected_image_after_paragraph_direct,
    rebalance_auto_images_to_targets,
    remove_non_auto_images_from_editor,
    remove_or_move_images_after_contact,
    select_visible_media_attachment,
    switch_to_visual_mode,
    wait_for_visible_media_attachments,
)

LogFunc = Callable[[str, str], None]
WaitIfPausedFunc = Callable[[], bool]


@dataclass
class InlineImageWorkflowConfig:
    max_retry_rounds: int = 2
    max_slot_retries: int = 2
    media_lib_poll_timeout: int = 15000
    media_lib_poll_interval: int = 500
    media_modal_timeout: int = 5000
    add_media_btn_timeout: int = 3000
    media_click_timeout: int = 1500
    heading_selector: str = "h2, h3"
    random_pool_min_size: int = INLINE_IMAGE_RANDOM_POOL_MIN_SIZE
    random_pool_buffer: int = INLINE_IMAGE_RANDOM_POOL_BUFFER
    random_pool_max_size: int = INLINE_IMAGE_RANDOM_POOL_MAX_SIZE


@dataclass
class InlineImageWorkflowRuntime:
    state: Any
    log_func: LogFunc
    wait_if_paused: WaitIfPausedFunc
    config: InlineImageWorkflowConfig = field(default_factory=InlineImageWorkflowConfig)

    @property
    def is_running(self) -> bool:
        return bool(getattr(self.state, "is_running", False))

    @property
    def is_paused(self) -> bool:
        return bool(getattr(self.state, "is_paused", False))

    def log(self, message: str, level: str = "info") -> None:
        self.log_func(message, level)

    def ensure_image_tracking(self) -> None:
        if not hasattr(self.state, "used_inline_images"):
            self.state.used_inline_images = set()
        if not hasattr(self.state, "used_inline_image_count"):
            self.state.used_inline_image_count = 0

    def inline_image_random_pool_size(self, images_per_post: int = 3) -> int:
        return get_inline_image_random_pool_size(
            topic_count=len(getattr(self.state, "topics", [])),
            images_per_post=images_per_post,
            min_pool=self.config.random_pool_min_size,
            buffer=self.config.random_pool_buffer,
            max_pool=self.config.random_pool_max_size,
        )


def _select_visible_media_attachment(page, label: str, runtime: InlineImageWorkflowRuntime) -> bool:
    runtime.ensure_image_tracking()
    ok, selected_count = select_visible_media_attachment(
        page,
        label,
        runtime.state.used_inline_images,
        runtime.state.used_inline_image_count,
        runtime.inline_image_random_pool_size(),
        log_func=runtime.log_func,
    )
    runtime.state.used_inline_image_count = selected_count
    return ok


def _wait_for_visible_media_attachments(page, label: str, runtime: InlineImageWorkflowRuntime) -> bool:
    return wait_for_visible_media_attachments(
        page,
        label,
        runtime.config.media_lib_poll_timeout,
        runtime.config.media_lib_poll_interval,
        log_func=runtime.log_func,
    )


def _click_first_selector_resilient(
    page,
    selectors: list,
    label: str,
    runtime: InlineImageWorkflowRuntime,
    timeout_ms: Optional[int] = None,
) -> bool:
    return click_first_selector_resilient(
        page,
        selectors,
        label,
        log_func=runtime.log_func,
        timeout_ms=timeout_ms or runtime.config.media_click_timeout,
    )


def try_insert_image_at_h2(
    page,
    h2_index: int,
    keyword: str,
    runtime: InlineImageWorkflowRuntime,
    max_images: Optional[int] = None,
) -> bool:
    """Atomic insert one image under a 0-based H2/H3 index."""
    for attempt in range(runtime.config.max_slot_retries + 1):
        if not runtime.is_running:
            return False
        if runtime.is_paused and not runtime.wait_if_paused():
            return False
        if max_images is not None and count_imgs_in_iframe(page) >= max_images:
            return True

        try:
            if attempt > 0:
                runtime.log(
                    f"Slot retry {attempt}/{runtime.config.max_slot_retries} cho H2 #{h2_index + 1}",
                    "info",
                )
                close_all_modals(page)
                switch_to_visual_mode(page, log_func=runtime.log_func)

            h2_elements = get_h2_elements_in_iframe(page, runtime.config.heading_selector)
            if h2_index >= len(h2_elements):
                runtime.log(
                    f"H2 #{h2_index + 1} không tồn tại (chỉ có {len(h2_elements)} H2)",
                    "warning",
                )
                return False
            h2_element = h2_elements[h2_index]
            try:
                h2_element.scroll_into_view_if_needed()
                time.sleep(0.3)
                h2_element.click()
                time.sleep(0.2)
                page.keyboard.press("End")
                page.keyboard.press("Enter")
                time.sleep(0.3)
            except Exception as e:
                runtime.log(f"Position cursor fail at H2 #{h2_index + 1}: {e}", "warning")
                continue

            add_btn = page.locator("#insert-media-button, .add_media").first
            btn_visible = False
            poll_start = time.time()
            while (time.time() - poll_start) * 1000 < runtime.config.add_media_btn_timeout:
                try:
                    if add_btn.is_visible(timeout=500):
                        btn_visible = True
                        break
                except Exception:
                    pass
                time.sleep(0.3)
            if not btn_visible:
                runtime.log(
                    f"Add Media button not visible cho H2 #{h2_index + 1} "
                    f"(attempt {attempt + 1})",
                    "warning",
                )
                continue
            if not _click_first_selector_resilient(
                page,
                ["#insert-media-button", ".add_media"],
                "Add Media button",
                runtime,
            ):
                runtime.log("Click Add Media fail", "warning")
                continue

            try:
                page.wait_for_selector(".media-modal", timeout=runtime.config.media_modal_timeout)
                time.sleep(1.0)
            except Exception:
                runtime.log(
                    f"Media modal không xuất hiện cho H2 #{h2_index + 1} "
                    f"(attempt {attempt + 1})",
                    "warning",
                )
                close_all_modals(page)
                continue

            media_label = f"H2 #{h2_index + 1} (attempt {attempt + 1})"
            if not _wait_for_visible_media_attachments(page, media_label, runtime):
                close_all_modals(page)
                continue

            if not _select_visible_media_attachment(page, f"H2 #{h2_index + 1}", runtime):
                close_all_modals(page)
                continue

            try:
                alt_selectors = [
                    "input[data-setting='alt']",
                    "#attachment-details-alt-text",
                    ".attachment-details input[type='text']",
                    "input.attachment-alt-text",
                ]
                for alt_sel in alt_selectors:
                    try:
                        alt = page.locator(alt_sel).first
                        if alt.is_visible(timeout=800):
                            alt.click()
                            alt.fill("")
                            time.sleep(0.1)
                            alt.fill(keyword)
                            runtime.log(f"Alt text set: {keyword}", "info")
                            break
                    except Exception:
                        continue
            except Exception:
                pass

            try:
                link = page.locator("select[data-setting='link']").first
                if link.is_visible(timeout=500):
                    link.select_option("post")
            except Exception:
                pass

            selected_image = get_selected_media_image(page, keyword, log_func=runtime.log_func)
            if not selected_image:
                runtime.log(
                    f"Không đọc được URL ảnh đã chọn cho H2 #{h2_index + 1}",
                    "warning",
                )
                close_all_modals(page)
                continue

            if not insert_selected_image_after_h2_direct(
                page,
                h2_index,
                selected_image,
                keyword,
                log_func=runtime.log_func,
            ):
                close_all_modals(page)
                continue

            if not img_is_after_h2(page, h2_index):
                runtime.log(
                    f"Image inserted but not directly under H2 #{h2_index + 1} "
                    f"— outer retry sẽ thử slot khác nếu cần",
                    "warning",
                )
            else:
                runtime.log(
                    f"Inserted image under H2 #{h2_index + 1} (verified)",
                    "success",
                )

            close_all_modals(page)
            time.sleep(0.5)
            switch_to_visual_mode(page, log_func=runtime.log_func)
            return True

        except Exception as e:
            runtime.log(
                f"Unexpected error trong _try_insert_image_at_h2 "
                f"H2 #{h2_index + 1} (attempt {attempt + 1}): {e}",
                "warning",
            )
            close_all_modals(page)
            continue

    return False


def fallback_insert_image_no_h2(
    page,
    keyword: str,
    slot_hint: str,
    runtime: InlineImageWorkflowRuntime,
    max_images: Optional[int] = None,
) -> bool:
    """Insert one image after a paragraph when safe H2/H3 anchors are unavailable."""
    if not runtime.is_running:
        return False
    if runtime.is_paused and not runtime.wait_if_paused():
        return False
    if max_images is not None and count_imgs_in_iframe(page) >= max_images:
        return True

    try:
        try:
            paragraphs = page.frame_locator("#content_ifr").locator("p").all()
        except Exception:
            paragraphs = []

        if not paragraphs:
            runtime.log(f"Fallback ({slot_hint}): no paragraph in iframe — skip", "warning")
            return False

        if slot_hint == "top":
            target = paragraphs[0]
        elif slot_hint == "middle":
            target = paragraphs[len(paragraphs) // 2]
        elif slot_hint == "bottom":
            target = paragraphs[-1]
        else:
            runtime.log(f"Invalid slot_hint: {slot_hint}", "warning")
            return False

        try:
            target.scroll_into_view_if_needed()
            time.sleep(0.3)
            target.click()
            time.sleep(0.2)
            page.keyboard.press("End")
            page.keyboard.press("Enter")
            time.sleep(0.3)
        except Exception as e:
            runtime.log(f"Fallback ({slot_hint}) position cursor fail: {e}", "warning")
            return False

        add_btn = page.locator("#insert-media-button, .add_media").first
        btn_visible = False
        poll_start = time.time()
        while (time.time() - poll_start) * 1000 < runtime.config.add_media_btn_timeout:
            try:
                if add_btn.is_visible(timeout=500):
                    btn_visible = True
                    break
            except Exception:
                pass
            time.sleep(0.3)
        if not btn_visible:
            runtime.log(f"Fallback ({slot_hint}): Add Media btn not visible", "warning")
            return False
        if not _click_first_selector_resilient(
            page,
            ["#insert-media-button", ".add_media"],
            f"Fallback ({slot_hint}) Add Media button",
            runtime,
        ):
            runtime.log(f"Fallback ({slot_hint}) click Add Media fail", "warning")
            return False

        try:
            page.wait_for_selector(".media-modal", timeout=runtime.config.media_modal_timeout)
            time.sleep(1.0)
        except Exception:
            runtime.log(f"Fallback ({slot_hint}): media modal không xuất hiện", "warning")
            close_all_modals(page)
            return False

        media_label = f"fallback {slot_hint}"
        if not _wait_for_visible_media_attachments(page, media_label, runtime):
            close_all_modals(page)
            return False

        if not _select_visible_media_attachment(page, f"fallback {slot_hint}", runtime):
            close_all_modals(page)
            return False

        try:
            alt_selectors = [
                "input[data-setting='alt']",
                "#attachment-details-alt-text",
                ".attachment-details input[type='text']",
                "input.attachment-alt-text",
            ]
            for alt_sel in alt_selectors:
                try:
                    alt = page.locator(alt_sel).first
                    if alt.is_visible(timeout=800):
                        alt.click()
                        alt.fill("")
                        time.sleep(0.1)
                        alt.fill(keyword)
                        runtime.log(f"Alt text set: {keyword}", "info")
                        break
                except Exception:
                    continue
        except Exception:
            pass

        try:
            link = page.locator("select[data-setting='link']").first
            if link.is_visible(timeout=500):
                link.select_option("post")
        except Exception:
            pass

        selected_image = get_selected_media_image(page, keyword, log_func=runtime.log_func)
        if not selected_image:
            runtime.log(f"Fallback ({slot_hint}): không đọc được URL ảnh đã chọn", "warning")
            close_all_modals(page)
            return False

        if not insert_selected_image_after_paragraph_direct(
            page,
            slot_hint,
            selected_image,
            keyword,
            log_func=runtime.log_func,
        ):
            close_all_modals(page)
            return False

        close_all_modals(page)
        time.sleep(0.5)
        switch_to_visual_mode(page, log_func=runtime.log_func)
        return True

    except Exception as e:
        runtime.log(f"Fallback ({slot_hint}) unexpected error: {e}", "warning")
        close_all_modals(page)
        return False


def select_random_image_for_content(
    page,
    alt_text: str,
    runtime: InlineImageWorkflowRuntime,
) -> bool:
    """Select one random media-library image and insert it near article bottom.

    This keeps the legacy fallback behavior used by older content flows, but
    shares the same no-repeat media pool and direct-insert path as inline H2
    images.
    """
    try:
        page.wait_for_selector(".media-modal", timeout=10000)
        if not _wait_for_visible_media_attachments(page, "content body", runtime):
            close_all_modals(page)
            return False

        if not _select_visible_media_attachment(page, "content body", runtime):
            close_all_modals(page)
            return False

        time.sleep(0.5)
        alt_selectors = [
            "input[data-setting='alt']",
            "#attachment-details-alt-text",
            ".attachment-details input[type='text']",
            "input[name='alt']",
            ".setting input[type='text'][data-setting='alt']",
        ]

        alt_set = False
        for alt_sel in alt_selectors:
            try:
                alt_input = page.locator(alt_sel).first
                if alt_input.is_visible(timeout=1000):
                    alt_input.click()
                    alt_input.fill("")
                    time.sleep(0.1)
                    alt_input.fill(alt_text)
                    runtime.log(f"Alt text đã set: {alt_text}", "info")
                    alt_set = True
                    time.sleep(0.3)
                    break
            except Exception:
                continue

        if not alt_set:
            runtime.log("Không thể set alt text", "warning")

        selected_image = get_selected_media_image(page, alt_text, log_func=runtime.log_func)
        if selected_image and insert_selected_image_after_paragraph_direct(
            page,
            "bottom",
            selected_image,
            alt_text,
            log_func=runtime.log_func,
        ):
            close_all_modals(page)
            return True

        close_all_modals(page)
        return False

    except Exception as e:
        runtime.log(f"Error selecting image for content: {e}", "warning")
        close_all_modals(page)
        return False


def final_scan_and_repair_images(
    page,
    keyword: str,
    max_images: int,
    target_h2_indices: list,
    runtime: InlineImageWorkflowRuntime,
) -> bool:
    runtime.log("Final image scan: checking full article image distribution...", "info")
    close_all_modals(page)
    switch_to_visual_mode(page, log_func=runtime.log_func)
    remove_non_auto_images_from_editor(page, "final scan", log_func=runtime.log_func)

    heading_count = get_safe_heading_count_for_images(page)
    valid_targets = [idx for idx in target_h2_indices if idx < heading_count]
    remove_or_move_images_after_contact(page, valid_targets, log_func=runtime.log_func)
    if valid_targets:
        rebalance_auto_images_to_targets(page, valid_targets, log_func=runtime.log_func)

    current_count = count_imgs_in_iframe(page)
    missing_targets = find_unfilled_target_h2(page, valid_targets, runtime.config.heading_selector)
    runtime.log(
        f"Final image scan: {current_count}/{max_images} images, "
        f"targets={format_heading_targets(valid_targets)}, "
        f"missing={format_heading_targets(missing_targets)}",
        "info",
    )

    while current_count < max_images and missing_targets:
        if not runtime.is_running:
            return False
        if runtime.is_paused and not runtime.wait_if_paused():
            return False
        remaining = max_images - current_count
        for h2_idx in select_even_candidates(missing_targets, remaining):
            if count_imgs_in_iframe(page) >= max_images:
                break
            try_insert_image_at_h2(
                page,
                h2_idx,
                keyword,
                runtime,
                max_images=max_images,
            )
        new_count = count_imgs_in_iframe(page)
        new_missing = find_unfilled_target_h2(page, valid_targets, runtime.config.heading_selector)
        if new_count == current_count and new_missing == missing_targets:
            break
        current_count = new_count
        missing_targets = new_missing

    if current_count < max_images:
        remaining = max_images - current_count
        other_indices = find_other_unfilled_h2(page, exclude_indices=set(valid_targets))
        for h2_idx in select_even_candidates(other_indices, remaining):
            if count_imgs_in_iframe(page) >= max_images:
                break
            if not runtime.is_running:
                return False
            if runtime.is_paused and not runtime.wait_if_paused():
                return False
            try_insert_image_at_h2(
                page,
                h2_idx,
                keyword,
                runtime,
                max_images=max_images,
            )

    current_count = count_imgs_in_iframe(page)
    if current_count < max_images:
        remaining = max_images - current_count
        for slot_hint in ("top", "middle", "bottom")[:remaining]:
            if count_imgs_in_iframe(page) >= max_images:
                break
            if not runtime.is_running:
                return False
            if runtime.is_paused and not runtime.wait_if_paused():
                return False
            fallback_insert_image_no_h2(
                page,
                keyword,
                slot_hint,
                runtime,
                max_images=max_images,
            )

    for repair_round in range(2):
        remove_non_auto_images_from_editor(
            page,
            f"strict final repair {repair_round + 1}",
            log_func=runtime.log_func,
        )
        remove_or_move_images_after_contact(page, valid_targets, log_func=runtime.log_func)
        if valid_targets:
            rebalance_auto_images_to_targets(page, valid_targets, log_func=runtime.log_func)

        current_count = count_imgs_in_iframe(page)
        if current_count >= max_images:
            break

        before_round = current_count
        runtime.log(
            f"Strict image repair {repair_round + 1}/2: "
            f"valid auto images {current_count}/{max_images}, retrying safe slots",
            "info",
        )

        remaining = max_images - current_count
        repair_candidates = find_unfilled_target_h2(page, valid_targets, runtime.config.heading_selector)
        if not repair_candidates:
            repair_candidates = find_other_unfilled_h2(
                page,
                exclude_indices=set(valid_targets),
            )

        for h2_idx in select_even_candidates(repair_candidates, remaining):
            if count_imgs_in_iframe(page) >= max_images:
                break
            if not runtime.is_running:
                return False
            if runtime.is_paused and not runtime.wait_if_paused():
                return False
            try_insert_image_at_h2(
                page,
                h2_idx,
                keyword,
                runtime,
                max_images=max_images,
            )

        current_count = count_imgs_in_iframe(page)
        if current_count < max_images:
            remaining = max_images - current_count
            for slot_hint in ("top", "middle", "bottom")[:remaining]:
                if count_imgs_in_iframe(page) >= max_images:
                    break
                if not runtime.is_running:
                    return False
                if runtime.is_paused and not runtime.wait_if_paused():
                    return False
                fallback_insert_image_no_h2(
                    page,
                    keyword,
                    slot_hint,
                    runtime,
                    max_images=max_images,
                )

        if count_imgs_in_iframe(page) <= before_round:
            break

    final_count = count_imgs_in_iframe(page)
    final_missing = find_unfilled_target_h2(page, valid_targets, runtime.config.heading_selector)
    if final_count >= max_images and not final_missing:
        runtime.log(
            f"Final image scan passed: {final_count}/{max_images} images "
            "with balanced heading targets",
            "success",
        )
    elif final_count >= max_images:
        runtime.log(
            f"Final image scan has enough images ({final_count}/{max_images}) "
            f"but target gaps remain: {format_heading_targets(final_missing)}",
            "warning",
        )
    else:
        runtime.log(
            f"Final image scan still short: {final_count}/{max_images} images",
            "warning",
        )
    return final_count > 0


def insert_images_after_h2(
    page,
    keyword: str,
    runtime: InlineImageWorkflowRuntime,
    max_images: int = 3,
) -> bool:
    """Insert inline images distributed across safe H2/H3 headings."""
    try:
        runtime.log("Đang chèn hình vào bài viết...", "info")
        close_all_modals(page)
        switch_to_visual_mode(page, log_func=runtime.log_func)
        remove_non_auto_images_from_editor(page, "before image insert", log_func=runtime.log_func)

        safe_heading_count = get_safe_heading_count_for_images(page)
        contact_idx = get_contact_heading_index(page)
        target_h2_indices = pick_inset_evenly_spaced_indices(
            safe_heading_count,
            max_images,
        )
        runtime.log(
            f"Image heading targets distributed with edge spacing: "
            f"{format_heading_targets(target_h2_indices)} "
            f"of {safe_heading_count} safe heading(s)"
            f"{' before contact section' if contact_idx is not None else ''}",
            "info",
        )

        if safe_heading_count <= 0:
            runtime.log("No H2 elements found — using paragraph fallback", "warning")
            for slot_hint in ("top", "middle", "bottom"):
                if not runtime.is_running:
                    return finalize_inline_image_insert(page, max_images, "stopped", log_func=runtime.log_func)
                if runtime.is_paused and not runtime.wait_if_paused():
                    return finalize_inline_image_insert(page, max_images, "stopped", log_func=runtime.log_func)
                if count_imgs_in_iframe(page) >= max_images:
                    break
                fallback_insert_image_no_h2(
                    page,
                    keyword,
                    slot_hint,
                    runtime,
                    max_images=max_images,
                )
            final_scan_and_repair_images(page, keyword, max_images, target_h2_indices, runtime)
            return finalize_inline_image_insert(page, max_images, "no_h2", log_func=runtime.log_func)

        for target_index in target_h2_indices:
            if count_imgs_in_iframe(page) >= max_images:
                break
            if not runtime.is_running:
                runtime.log("Stopped while inserting images", "warning")
                return finalize_inline_image_insert(page, max_images, "stopped", log_func=runtime.log_func)
            if runtime.is_paused and not runtime.wait_if_paused():
                return finalize_inline_image_insert(page, max_images, "stopped", log_func=runtime.log_func)

            if target_index >= safe_heading_count:
                runtime.log(
                    f"H2 #{target_index + 1} not found "
                    f"(only {safe_heading_count} safe H2/H3s) — will fallback later",
                    "info",
                )
                continue

            try_insert_image_at_h2(
                page,
                target_index,
                keyword,
                runtime,
                max_images=max_images,
            )

        for round_idx in range(runtime.config.max_retry_rounds):
            current_count = count_imgs_in_iframe(page)
            if current_count >= max_images:
                break
            if not runtime.is_running:
                return finalize_inline_image_insert(page, max_images, "stopped", log_func=runtime.log_func)
            if runtime.is_paused and not runtime.wait_if_paused():
                return finalize_inline_image_insert(page, max_images, "stopped", log_func=runtime.log_func)

            runtime.log(
                f"Retry round {round_idx + 1}/{runtime.config.max_retry_rounds}: "
                f"have {current_count}/{max_images} — scanning for unfilled slots",
                "info",
            )

            unfilled_targets = find_unfilled_target_h2(
                page,
                target_h2_indices,
                runtime.config.heading_selector,
            )
            remaining_slots = max_images - count_imgs_in_iframe(page)
            other_indices = select_even_candidates(
                find_other_unfilled_h2(page, exclude_indices=set(target_h2_indices)),
                remaining_slots,
            )

            candidate_order = unfilled_targets + other_indices
            for h2_idx in candidate_order:
                if count_imgs_in_iframe(page) >= max_images:
                    break
                if not runtime.is_running:
                    return finalize_inline_image_insert(page, max_images, "stopped", log_func=runtime.log_func)
                if runtime.is_paused and not runtime.wait_if_paused():
                    return finalize_inline_image_insert(page, max_images, "stopped", log_func=runtime.log_func)
                try_insert_image_at_h2(
                    page,
                    h2_idx,
                    keyword,
                    runtime,
                    max_images=max_images,
                )

            if count_imgs_in_iframe(page) < max_images:
                remaining = max_images - count_imgs_in_iframe(page)
                slot_hints = ("top", "middle", "bottom")[:remaining]
                for slot_hint in slot_hints:
                    if not runtime.is_running:
                        break
                    if runtime.is_paused and not runtime.wait_if_paused():
                        break
                    if count_imgs_in_iframe(page) >= max_images:
                        break
                    fallback_insert_image_no_h2(
                        page,
                        keyword,
                        slot_hint,
                        runtime,
                        max_images=max_images,
                    )

        final_scan_and_repair_images(page, keyword, max_images, target_h2_indices, runtime)
        return finalize_inline_image_insert(page, max_images, "done", log_func=runtime.log_func)

    except Exception as e:
        runtime.log(f"Error in insert_images_after_h2: {e}", "error")
        close_all_modals(page)
        return False
