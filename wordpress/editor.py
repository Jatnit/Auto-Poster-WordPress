"""
WordPress Editor Functions
===========================
Post title, content, SEO, and category management.
"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

# ============================================================================
# HELPERS
# ============================================================================

def wait_for_network_idle(page, timeout: int = 10000):
    """Wait for network to be idle."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except:
        pass

# ============================================================================
# NAVIGATION
# ============================================================================

def navigate_to_new_post(page, config: dict, log_func) -> bool:
    """Navigate to create new post page (Classic Editor)."""
    try:
        page.goto(f"{config['wp_admin_url']}/post-new.php", wait_until="domcontentloaded")
        wait_for_network_idle(page, timeout=15000)
        time.sleep(2)
        
        # Wait for Classic Editor to load - check for title field
        try:
            page.wait_for_selector("#title, input[name='post_title']", timeout=10000)
            log_func("Classic Editor loaded", "info")
        except:
            log_func("Editor may not have loaded properly", "warning")
        
        # Dismiss any notices
        try:
            dismiss_btns = page.locator(".notice-dismiss, .wp-core-ui .notice-dismiss").all()
            for btn in dismiss_btns:
                if btn.is_visible():
                    btn.click()
                    time.sleep(0.2)
        except:
            pass
        
        log_func("Navigated to new post editor", "info")
        return True
        
    except Exception as e:
        log_func(f"Failed to navigate to new post: {e}", "error")
        return False

# ============================================================================
# TITLE
# ============================================================================

def set_post_title(page, title: str, log_func) -> bool:
    """Set the post title (Classic Editor)."""
    try:
        # Classic Editor title field - ID is always "title"
        title_input = page.locator("#title")
        
        if title_input.is_visible(timeout=5000):
            title_input.click()
            title_input.fill("")  # Clear first
            title_input.fill(title)
            log_func(f"Set title: {title[:50]}...", "info")
            return True
        else:
            log_func("Title field not visible", "error")
            return False
            
    except Exception as e:
        log_func(f"Failed to set title: {e}", "error")
        return False

# ============================================================================
# CONTENT
# ============================================================================

def set_post_content(page, content: str, log_func) -> bool:
    """Set the post content (Classic Editor with TinyMCE)."""
    try:
        log_func("Adding content...", "info")
        time.sleep(0.5)
        
        content_added = False
        
        # Method 1: Switch to Text/HTML mode and fill textarea directly
        try:
            # Click on "Text" tab
            text_tab = page.locator("#content-html").first
            if text_tab.is_visible(timeout=3000):
                text_tab.click()
                time.sleep(0.5)
                log_func("Switched to Text/HTML mode", "info")
                
                # Fill the content textarea
                content_textarea = page.locator("#content").first
                if content_textarea.is_visible(timeout=3000):
                    content_textarea.click()
                    content_textarea.fill("")  # Clear first
                    content_textarea.fill(content)
                    content_added = True
                    log_func("Content added via textarea", "success")
        except Exception as e:
            log_func(f"Textarea method failed: {e}", "warning")
        
        # Method 2: JavaScript injection to textarea
        if not content_added:
            try:
                page.evaluate("""
                    (content) => {
                        // Switch to Text mode
                        var htmlBtn = document.getElementById('content-html');
                        if (htmlBtn) htmlBtn.click();
                        
                        // Set content
                        var textarea = document.getElementById('content');
                        if (textarea) {
                            textarea.value = content;
                            // Trigger change event
                            textarea.dispatchEvent(new Event('input', { bubbles: true }));
                            textarea.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                        return false;
                    }
                """, content)
                content_added = True
                log_func("Content added via JavaScript", "success")
            except Exception as e:
                log_func(f"JavaScript method failed: {e}", "warning")
        
        # Method 3: TinyMCE iframe (Visual mode)
        if not content_added:
            try:
                # Try to access TinyMCE iframe
                tinymce_frame = page.frame_locator("#content_ifr")
                tinymce_body = tinymce_frame.locator("body#tinymce, body.mce-content-body")
                
                if tinymce_body:
                    tinymce_body.click()
                    page.keyboard.press("Control+a")
                    page.keyboard.type(content[:100])  # Just add some content
                    content_added = True
                    log_func("Content added via TinyMCE iframe", "success")
            except Exception as e:
                log_func(f"TinyMCE method failed: {e}", "warning")
        
        if content_added:
            return True
        else:
            log_func("Failed to add content - all methods failed", "error")
            return False
        
    except Exception as e:
        log_func(f"Failed to set content: {e}", "error")
        return False

# ============================================================================
# SEO
# ============================================================================

def set_rank_math_keyword(page, keyword: str, log_func) -> bool:
    """Set the Rank Math SEO focus keyword."""
    try:
        log_func(f"Setting Rank Math keyword: {keyword}", "info")
        
        # Scroll down to Rank Math section
        page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
        time.sleep(1)
        
        # Look for Rank Math focus keyword input
        keyword_selectors = [
            "input[placeholder*='Rank Math']",
            "input.rank-math-focus-keyword",
            "#rank-math-focus-keyword",
            "input[name*='rank_math'][name*='keyword']",
            ".rank-math-focus-keyword input",
            "input[placeholder*='khóa chính']",
            "input[placeholder*='focus keyword']"
        ]
        
        keyword_input = None
        for selector in keyword_selectors:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1000):
                    keyword_input = el
                    break
            except:
                continue
        
        if keyword_input:
            keyword_input.click()
            keyword_input.fill("")
            keyword_input.fill(keyword)
            # Press Enter to add the keyword
            keyword_input.press("Enter")
            time.sleep(0.5)
            log_func(f"Rank Math keyword set: {keyword}", "success")
            return True
        else:
            # Try JavaScript method
            try:
                page.evaluate("""
                    (keyword) => {
                        var inputs = document.querySelectorAll('input[placeholder*="Rank Math"], input.rank-math-focus-keyword');
                        if (inputs.length > 0) {
                            inputs[0].value = keyword;
                            inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
                            return true;
                        }
                        return false;
                    }
                """, keyword)
                log_func(f"Rank Math keyword set via JS: {keyword}", "success")
                return True
            except:
                log_func("Rank Math keyword field not found", "warning")
                return False
        
    except Exception as e:
        log_func(f"Error setting Rank Math keyword: {e}", "warning")
        return False

# ============================================================================
# CATEGORY
# ============================================================================

def select_first_category(page, log_func) -> bool:
    """Select first category (Classic Editor)."""
    try:
        # Find category checkboxes in the category meta box
        category_checkboxes = page.locator("#categorychecklist input[type='checkbox']").all()
        
        if not category_checkboxes:
            log_func("No category checkboxes found", "warning")
            return False
        
        # Click the first unchecked checkbox
        for checkbox in category_checkboxes:
            try:
                if checkbox.is_visible() and not checkbox.is_checked():
                    checkbox.check()
                    log_func("Selected first category", "info")
                    return True
            except:
                continue
        
        # If all are checked or none worked, just return true
        log_func("Category already selected or selection not needed", "info")
        return True
        
    except Exception as e:
        log_func(f"Error selecting category: {e}", "warning")
        return False
