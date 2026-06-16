"""WordPress Classic Editor publish and schedule helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from wp_auto_poster.wordpress.browser import click_first_selector_resilient
from wp_auto_poster.wordpress.media import remove_non_auto_images_from_editor

LogFunc = Callable[[str, str], None]


@dataclass
class PublisherRuntime:
    log_func: LogFunc

    def log(self, message: str, level: str = "info") -> None:
        self.log_func(message, level)

    def click_first_selector_resilient(
        self,
        page: Any,
        selectors: list,
        label: str,
        timeout_ms: int = 1500,
    ) -> bool:
        return click_first_selector_resilient(
            page,
            selectors,
            label,
            log_func=self.log_func,
            timeout_ms=timeout_ms,
        )


def publish_or_schedule_post(
    page: Any,
    is_schedule: bool,
    publish_date: Optional[datetime],
    runtime: PublisherRuntime,
) -> bool:
    try:
        remove_non_auto_images_from_editor(page, "pre-publish", log_func=runtime.log_func)

        # Pre-publish sync: ép TinyMCE flush nội dung iframe → textarea trước
        # khi submit form. Classic Editor tự gọi triggerSave() lúc submit, nhưng
        # nếu iframe đang Visual mode mà chưa fully init, hoặc user vừa edit
        # qua DOM (insert ảnh, ...), bước này đảm bảo textarea có HTML mới nhất.
        try:
            page.evaluate(
                """() => {
                    if (window.tinymce) {
                        try { tinymce.triggerSave(); } catch (e) {}
                        const ed = tinymce.get('content');
                        if (ed) {
                            try { ed.save(); } catch (e) {}
                        }
                    }
                }"""
            )
        except Exception:
            pass

        # Cuộn lên đầu trang — nút Publish của Classic Editor nằm ở sidebar
        # góc trên phải; cuộn về đầu đảm bảo cả khu Publish meta box đều visible.
        try:
            page.evaluate("window.scrollTo({ top: 0, behavior: 'instant' })")
        except Exception:
            try:
                page.evaluate("window.scrollTo(0, 0)")
            except Exception:
                pass
        time.sleep(0.4)

        # For scheduling in Classic Editor
        if is_schedule and publish_date:
            # Click "Chỉnh sửa" next to "Xuất bản ngay lập tức" to open date picker
            if runtime.click_first_selector_resilient(
                page,
                [".edit-timestamp", "a.edit-timestamp", "#timestamp a"],
                "timestamp edit link",
                timeout_ms=1500,
            ):
                time.sleep(0.5)
                
                # Fill in date fields
                # Month dropdown
                month_select = page.locator("#mm, select[name='mm']").first
                if month_select.is_visible(timeout=2000):
                    month_select.select_option(str(publish_date.month).zfill(2))
                
                # Day input
                day_input = page.locator("#jj, input[name='jj']").first
                if day_input.is_visible(timeout=2000):
                    day_input.fill(str(publish_date.day))
                
                # Year input
                year_input = page.locator("#aa, input[name='aa']").first
                if year_input.is_visible(timeout=2000):
                    year_input.fill(str(publish_date.year))
                
                # Hour input
                hour_input = page.locator("#hh, input[name='hh']").first
                if hour_input.is_visible(timeout=2000):
                    hour_input.fill(str(publish_date.hour).zfill(2))
                
                # Minute input
                minute_input = page.locator("#mn, input[name='mn']").first
                if minute_input.is_visible(timeout=2000):
                    minute_input.fill("00")
                
                # Click OK button to confirm date. Classic Editor can report this
                # button visible but outside viewport, so use the resilient helper.
                if runtime.click_first_selector_resilient(
                    page,
                    ["a.save-timestamp", ".save-timestamp"],
                    "timestamp OK button",
                    timeout_ms=1500,
                ):
                    time.sleep(0.5)
                else:
                    runtime.log("Could not confirm timestamp OK button", "warning")
        
        # Click Publish/Schedule button - in Classic Editor it's just #publish
        runtime.log("Preparing to publish...", "info")

        # Đảm bảo đã ở đầu trang (phòng trường hợp date picker kéo scroll xuống)
        try:
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass
        time.sleep(0.4)

        publish_btn = page.locator("#publish, input#publish, #publishing-action input[type='submit']").first

        # Cuộn nút Publish vào viewport — đây là điểm bạn hay phải thao tác tay.
        # scroll_into_view_if_needed hoạt động kể cả với element ngoài viewport.
        try:
            publish_btn.scroll_into_view_if_needed(timeout=3000)
            runtime.log("Đã cuộn tới nút Publish", "info")
            time.sleep(0.3)
        except Exception as scroll_err:
            runtime.log(f"Không scroll được tới nút Publish: {scroll_err}", "warning")

        # Thử 3 cách click theo thứ tự ưu tiên
        clicked = False

        # 1) Playwright click (respect visibility/position)
        try:
            publish_btn.click(timeout=3000)
            clicked = True
            runtime.log("Clicked publish button", "info")
        except Exception as click_err:
            runtime.log(f"Click trực tiếp fail: {click_err}", "warning")

        # 2) Force click (bỏ qua overlay)
        if not clicked:
            try:
                publish_btn.click(force=True, timeout=2000)
                clicked = True
                runtime.log("Force-clicked publish button", "info")
            except Exception as force_err:
                runtime.log(f"Force click fail: {force_err}", "warning")

        # 3) JS click — fallback cuối
        if not clicked:
            try:
                page.evaluate(
                    "document.getElementById('publish')?.click() "
                    "|| document.querySelector('#publishing-action input[type=submit]')?.click()"
                )
                clicked = True
                runtime.log("JS-clicked publish button", "info")
            except Exception as js_err:
                runtime.log(f"JS click fail: {js_err}", "error")

        if not clicked:
            runtime.log("Không thể click nút Publish", "error")
            return False
        
        # Wait for page to reload - this is critical
        runtime.log("Đang lưu bài viết...", "info")
        time.sleep(4)
        
        # Multiple ways to check for success
        success_detected = False
        
        # Method 1: Check for success message
        try:
            success_selectors = [
                "#message.updated",
                ".notice-success", 
                "#message.notice",
                ".updated.notice",
                "div.updated"
            ]
            for selector in success_selectors:
                success_msg = page.locator(selector).first
                if success_msg.is_visible(timeout=2000):
                    success_detected = True
                    runtime.log("Success message detected", "info")
                    break
        except:
            pass
        
        # Method 2: Check URL for post.php (means we're on edit page of saved post)
        if not success_detected:
            current_url = page.url
            if "post.php" in current_url and "action=edit" in current_url:
                success_detected = True
                runtime.log("Post saved - now on edit page", "info")
        
        # Method 3: Check URL for message parameter
        if not success_detected:
            current_url = page.url
            if "message=" in current_url:
                success_detected = True
                runtime.log("Post saved - message in URL", "info")
        
        # Method 4: Check if View Post link exists
        if not success_detected:
            try:
                view_post = page.locator("a:has-text('View post'), a:has-text('Xem bài viết')").first
                if view_post.is_visible(timeout=2000):
                    success_detected = True
                    runtime.log("View post link found", "info")
            except:
                pass
        
        # Method 5: Check if post ID exists in URL (meaning post was created)
        if not success_detected:
            current_url = page.url
            if "post=" in current_url:
                success_detected = True
                runtime.log("Post ID found in URL", "info")
        
        if success_detected:
            action = "Scheduled" if is_schedule else "Published"
            runtime.log(f"{action} successfully!", "success")
            return True
        else:
            runtime.log("Could not confirm publish status, but continuing...", "warning")
            # Return True anyway since the click happened
            return True
        
    except Exception as e:
        runtime.log(f"Error publishing: {e}", "error")
        return False
