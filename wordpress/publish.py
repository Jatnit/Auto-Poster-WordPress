"""
WordPress Publish Functions
============================
Post publishing and scheduling.
"""

import time
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

# ============================================================================
# PUBLISH/SCHEDULE
# ============================================================================

def publish_or_schedule_post(page, is_schedule: bool, publish_date: datetime, log_func) -> bool:
    """Publish or schedule post (Classic Editor)."""
    try:
        # For scheduling in Classic Editor
        if is_schedule and publish_date:
            # Click "Edit" next to "Publish immediately" to open date picker
            edit_date_link = page.locator(".edit-timestamp, a.edit-timestamp, #timestamp a").first
            
            if edit_date_link.is_visible(timeout=2000):
                edit_date_link.click()
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
                
                # Click OK button to confirm date
                ok_btn = page.locator("a.save-timestamp, .save-timestamp").first
                if ok_btn.is_visible(timeout=2000):
                    ok_btn.click()
                    time.sleep(0.5)
        
        # Click Publish/Schedule button - in Classic Editor it's just #publish
        log_func("Preparing to publish...", "info")
        
        # Wait a moment for any overlays to disappear
        time.sleep(1)
        
        # Scroll to publish button area
        try:
            page.evaluate("document.getElementById('publish').scrollIntoView({block: 'center'})")
        except:
            pass
        time.sleep(0.5)
        
        # Try to click using JavaScript to bypass any overlay
        try:
            page.evaluate("document.getElementById('publish').click()")
            log_func("Clicked publish button", "info")
        except Exception as js_err:
            log_func(f"JS click failed: {js_err}, trying regular click", "warning")
            # Fallback to regular click
            publish_btn = page.locator("#publish, input#publish").first
            if publish_btn.is_visible(timeout=3000):
                publish_btn.click(force=True)
        
        # Wait for page to reload - this is critical
        log_func("Saving post...", "info")
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
                    log_func("Success message detected", "info")
                    break
        except:
            pass
        
        # Method 2: Check URL for post.php (means we're on edit page of saved post)
        if not success_detected:
            current_url = page.url
            if "post.php" in current_url and "action=edit" in current_url:
                success_detected = True
                log_func("Post saved - now on edit page", "info")
        
        # Method 3: Check URL for message parameter
        if not success_detected:
            current_url = page.url
            if "message=" in current_url:
                success_detected = True
                log_func("Post saved - message in URL", "info")
        
        # Method 4: Check if View Post link exists
        if not success_detected:
            try:
                view_post = page.locator("a:has-text('View post'), a:has-text('Xem bài viết')").first
                if view_post.is_visible(timeout=2000):
                    success_detected = True
                    log_func("View post link found", "info")
            except:
                pass
        
        # Method 5: Check if post ID exists in URL (meaning post was created)
        if not success_detected:
            current_url = page.url
            if "post=" in current_url:
                success_detected = True
                log_func("Post ID found in URL", "info")
        
        if success_detected:
            action = "Scheduled" if is_schedule else "Published"
            log_func(f"{action} successfully!", "success")
            return True
        else:
            log_func("Could not confirm publish status, but continuing...", "warning")
            # Return True anyway since the click happened
            return True
        
    except Exception as e:
        log_func(f"Error publishing: {e}", "error")
        return False
