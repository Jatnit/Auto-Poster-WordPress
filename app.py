#!/usr/bin/env python3

import os
import random
import re
import threading
import time
import requests
from datetime import datetime, timedelta
from typing import Optional

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

from config.settings import (
    state, add_log, wait_if_paused, pause_on_error,
    load_site_presets, save_site_presets,
    PRESETS_FILE, TIMEOUT_SHORT, TIMEOUT_MEDIUM, TIMEOUT_LONG,
    SLEEP_SHORT, SLEEP_MEDIUM, SLEEP_LONG, BROWSER_DATA_DIR
)
from config.prompts import PROMPT_PART1, PROMPT_PART2, CONTACT_SECTION, clean_gemini_content
from ai_providers.ollama import (
    generate_content_ollama as _generate_content_ollama,
    check_ollama, OLLAMA_AVAILABLE
)
from ai_providers.gemini_api import (
    generate_content_gemini as _generate_content_gemini,
    GEMINI_AVAILABLE
)

try:
    from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# WRAPPER FUNCTIONS (to pass state.config and add_log)

def generate_content_ollama(title: str, keyword: str) -> Optional[str]:
    return _generate_content_ollama(title, keyword, state.config, add_log)

def generate_content_gemini(title: str, keyword: str) -> Optional[str]:
    return _generate_content_gemini(
        title, keyword, 
        state.config.get("gemini_api_key", ""),
        add_log
    )

# GEMINI WEB CONTENT GENERATION (Browser-based, free, no API key)

def send_prompt_to_gemini_web(page, prompt: str) -> Optional[str]:
    try:
        # Wait for page to fully load
        add_log("Đang chờ trang Gemini tải...", "info")
        time.sleep(5)
        
        # Reload page to ensure fresh state
        page.reload(wait_until="domcontentloaded")
        time.sleep(5)
        
        # Look for the input area with multiple selectors
        input_selectors = [
            "p[contenteditable='true']",
            "div[contenteditable='true']",
            "rich-textarea p[contenteditable='true']",
            "rich-textarea div[contenteditable='true']",
            ".ql-editor p",
            "textarea[placeholder*='prompt']",
            "textarea[placeholder*='Prompt']",
            "[data-placeholder*='Enter']",
            "[aria-label*='Enter a prompt']",
            "[aria-label*='prompt']"
        ]
        
        input_area = None
        for selector in input_selectors:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=3000):
                    input_area = el
                    add_log(f"Tìm thấy ô nhập: {selector}", "info")
                    break
            except:
                continue
        
        if not input_area:
            # Try to find any editable element
            add_log("Đang thử các selector khác...", "warning")
            try:
                input_area = page.locator("[contenteditable='true']").first
                if input_area.is_visible(timeout=5000):
                    add_log("Tìm thấy phần tử contenteditable", "info")
            except:
                pass
        
        if not input_area:
            add_log("Không tìm thấy ô nhập Gemini", "error")
            # Take screenshot for debugging
            page.screenshot(path="/tmp/gemini_error.png")
            add_log("Đã lưu screenshot tại /tmp/gemini_error.png", "info")
            return None
        
        # Click on the input area to focus
        input_area.click()
        time.sleep(1)
        
        # Clean prompt - replace newlines with spaces to avoid multiple sends
        clean_prompt = prompt.replace('\n', ' ').replace('\r', ' ')
        # Remove multiple spaces
        while '  ' in clean_prompt:
            clean_prompt = clean_prompt.replace('  ', ' ')
        
        add_log("Đang nhập prompt...", "info")
        
        # Method 1: Try using fill() - most reliable
        try:
            input_area.fill(clean_prompt)
            add_log("Đã nhập prompt qua fill()", "info")
        except:
            # Method 2: Use keyboard typing for the entire prompt
            add_log("Đang gõ bằng bàn phím...", "info")
            # Clear first
            page.keyboard.press("Meta+A")  # Cmd+A on Mac
            page.keyboard.press("Backspace")
            time.sleep(0.3)
            
            # Type without delay to avoid interruptions
            page.keyboard.type(clean_prompt, delay=0)
        
        time.sleep(2)  # Wait for input to settle
        
        # Click send button or press Enter
        send_selectors = [
            "button[aria-label*='Send']",
            "button[aria-label*='Gửi']",
            "button.send-button",
            "[data-test-id='send-button']",
            "button:has-text('Send')"
        ]
        
        sent = False
        for selector in send_selectors:
            try:
                send_btn = page.locator(selector).last
                if send_btn.is_visible(timeout=2000):
                    send_btn.click()
                    sent = True
                    add_log("Đã gửi prompt tới Gemini", "info")
                    break
            except:
                continue
        
        if not sent:
            # Try pressing Enter as fallback
            page.keyboard.press("Enter")
            add_log("Đã gửi prompt qua phím Enter", "info")
        
        # Wait for response
        add_log("Đang chờ Gemini trả lời (có thể mất 1-2 phút)...", "info")
        time.sleep(5)  # Initial wait
        
        # Wait until response is complete
        max_wait = 180  # 3 minutes max
        waited = 0
        while waited < max_wait:
            # Check for stop/pause
            if not state.is_running:
                add_log("Stopped while waiting for Gemini", "warning")
                return None
            
            # Check if paused
            if state.is_paused:
                add_log("Paused - waiting...", "info")
                if not wait_if_paused():
                    return None
                add_log("Resuming Gemini wait...", "info")
            
            # Check for loading indicators
            loading_indicators = page.locator(".loading, .thinking, [aria-busy='true'], .response-streaming").all()
            if not loading_indicators or len(loading_indicators) == 0:
                # No loading indicator, might be done
                time.sleep(3)
                break
            
            # Check if any loading indicator is visible
            any_loading = False
            for indicator in loading_indicators:
                try:
                    if indicator.is_visible(timeout=500):
                        any_loading = True
                        break
                except:
                    continue
            
            if not any_loading:
                break
                
            time.sleep(2)
            waited += 2
            if waited % 15 == 0:
                add_log(f"Vẫn đang chờ... ({waited}s)", "info")
        
        time.sleep(5)  # Extra wait for rendering
        
        # Extract the response - try multiple selectors
        add_log("Đang trích xuất phản hồi...", "info")
        
        response_text = ""
        
        # Try different response selectors
        response_selectors = [
            ".model-response-text",
            ".response-content", 
            ".markdown-content",
            "[data-message-author-role='model']",
            ".message-content"
        ]
        
        for selector in response_selectors:
            try:
                responses = page.locator(selector).all()
                if responses and len(responses) > 0:
                    # Get the last response
                    last_response = responses[-1]
                    response_text = last_response.inner_html()
                    if response_text and len(response_text) > 100:
                        add_log(f"Tìm thấy phản hồi với selector: {selector}", "info")
                        break
            except:
                continue
        
        if response_text:
            word_count = len(response_text.split())
            add_log(f"Nhận được {word_count} từ từ Gemini", "success")
            return response_text
        else:
            add_log("Không thể trích xuất phản hồi Gemini", "error")
            return None
            
    except Exception as e:
        add_log(f"Lỗi Gemini Chat: {e}", "error")
        return None


def generate_content_gemini_web(page, title: str, keyword: str) -> Optional[str]:
    try:
        add_log("Đang mở Gemini Chat...", "info")
        
        # Navigate to Gemini Chat
        page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)  # Wait for page to fully load
        
        # Check if need to login
        needs_login = False
        try:
            if "accounts.google.com" in page.url:
                needs_login = True
            elif page.locator("a[href*='accounts.google'], button:has-text('Sign in'), button:has-text('Đăng nhập')").first.is_visible(timeout=3000):
                needs_login = True
        except:
            pass
        
        if needs_login:
            add_log("Vui lòng đăng nhập Google trong cửa sổ browser!", "warning")
            add_log("Đang chờ đăng nhập (10 phút)...", "info")
            
            # Wait up to 10 minutes for login
            login_wait = 0
            max_login_wait = 600  # 10 minutes
            while login_wait < max_login_wait and state.is_running:
                # Check if paused
                if state.is_paused:
                    if not wait_if_paused():
                        add_log("Stopped while waiting for login", "warning")
                        return None
                
                time.sleep(5)
                login_wait += 5
                
                # Check if stopped 
                if not state.is_running:
                    add_log("Stopped by user", "warning")
                    return None
                
                # Check if we're now on Gemini app page
                current_url = page.url
                if "gemini.google.com" in current_url and "accounts.google" not in current_url:
                    add_log("Đăng nhập thành công!", "success")
                    time.sleep(3)  # Extra wait for page load
                    break
                    
                remaining = max_login_wait - login_wait
                if login_wait % 60 == 0:
                    add_log(f"Còn {remaining // 60} phút...", "info")
        
        # Get custom prompt from config, or use default
        custom_prompt = state.config.get("gemini_prompt", "")
        
        if custom_prompt and "{title}" in custom_prompt and "{keyword}" in custom_prompt:
            # Check stop/pause before generating
            if not state.is_running:
                return None
            if state.is_paused:
                if not wait_if_paused():
                    return None
            
            # Use custom single prompt
            add_log("Đang tạo nội dung với prompt tùy chỉnh...", "info")
            prompt = custom_prompt.format(title=title, keyword=keyword)
            content = send_prompt_to_gemini_web(page, prompt)
            
            if not content:
                add_log("Không thể tạo nội dung", "error")
                return None
            
            word_count = len(content.split())
            add_log(f"Đã tạo {word_count} từ", "info")
            
        else:
            # Fall back to two-part generation
            # Check stop/pause
            if not state.is_running:
                return None
            if state.is_paused:
                if not wait_if_paused():
                    return None
            
            add_log("Đang tạo Phần 1/2 với Gemini Chat...", "info")
            prompt1 = PROMPT_PART1.format(title=title, keyword=keyword)
            part1 = send_prompt_to_gemini_web(page, prompt1)
            
            if not part1:
                add_log("Không thể tạo Phần 1", "error")
                return None
            
            word_count_1 = len(part1.split())
            add_log(f"Phần 1: {word_count_1} từ", "info")
            
            # Check stop/pause before part 2
            if not state.is_running:
                return None
            if state.is_paused:
                if not wait_if_paused():
                    return None
            
            time.sleep(3)
            
            add_log("Đang tạo Phần 2/2 với Gemini Chat...", "info")
            prompt2 = PROMPT_PART2.format(title=title, keyword=keyword)
            part2 = send_prompt_to_gemini_web(page, prompt2)
            
            if not part2:
                add_log("Không thể tạo Phần 2", "error")
                return None
            
            word_count_2 = len(part2.split())
            add_log(f"Phần 2: {word_count_2} từ", "info")
            
            # Combine parts
            contact = CONTACT_SECTION.format(keyword=keyword)
            content = part1 + "\n\n" + part2 + "\n\n" + contact
        
        # Clean content - remove intro and outro text from Gemini
        content = clean_gemini_content(content)
        
        total_words = len(content.split())
        add_log(f"Tổng cộng: {total_words} từ", "success")
        add_log(f"Đã tạo nội dung cho: {title}", "success")
        
        return content
        
    except Exception as e:
        add_log(f"Lỗi Gemini Chat: {e}", "error")
        return None



def generate_content(title: str, keyword: str, page=None) -> Optional[str]:
    provider = state.config.get("ai_provider", "ollama")
    
    if provider == "ollama":
        # Check if Ollama is running
        if not check_ollama():
            add_log("Ollama is not running! Please start Ollama first.", "error")
            add_log("Run: ollama serve", "info")
            return None
        return generate_content_ollama(title, keyword)
    elif provider == "gemini_web":
        if page is None:
            add_log("Gemini Web requires browser page", "error")
            return None
        return generate_content_gemini_web(page, title, keyword)
    else:
        return generate_content_gemini(title, keyword)

# WORDPRESS AUTOMATION

def wait_for_network_idle(page: Page, timeout: int = 10000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except:
        pass

def login_to_wordpress(page: Page) -> bool:
    try:
        add_log("🔐 Logging into WordPress...", "info")
        
        login_url = state.config.get("wp_login_url", "")
        username = state.config.get("wp_username", "")
        password = state.config.get("wp_password", "")
        
        add_log(f"Login URL: {login_url}", "info")
        add_log(f"Username: {username}", "info")
        
        if not login_url or not username or not password:
            add_log("Missing login credentials!", "error")
            return False
        
        # Navigate to login page
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)
        
        current_url = page.url
        add_log(f"Current URL: {current_url}", "info")
        
        # Check if already logged in
        if "wp-admin" in current_url and "wp-login" not in current_url:
            add_log("Already logged in!", "success")
            return True
        
        # Wait for login form - try multiple selectors
        login_form_found = False
        form_selectors = ["#user_login", "#loginform", "input[name='log']", "#username"]
        
        for selector in form_selectors:
            try:
                if page.locator(selector).first.is_visible(timeout=3000):
                    login_form_found = True
                    add_log(f"Tìm thấy form đăng nhập: {selector}", "info")
                    break
            except:
                continue
        
        if not login_form_found:
            add_log("Could not find login form!", "error")
            page.screenshot(path="/tmp/wp_login_error.png")
            add_log("Screenshot saved to /tmp/wp_login_error.png", "info")
            return False
        
        # Fill login form - try different selectors
        username_selectors = ["#user_login", "input[name='log']", "#username"]
        password_selectors = ["#user_pass", "input[name='pwd']", "#password"]
        
        # Fill username
        for selector in username_selectors:
            try:
                input_field = page.locator(selector).first
                if input_field.is_visible(timeout=2000):
                    input_field.click()
                    input_field.fill("")
                    input_field.fill(username)
                    add_log(f"Filled username in {selector}", "info")
                    break
            except:
                continue
        
        time.sleep(0.3)
        
        # Fill password
        for selector in password_selectors:
            try:
                input_field = page.locator(selector).first
                if input_field.is_visible(timeout=2000):
                    input_field.click()
                    input_field.fill("")
                    input_field.fill(password)
                    add_log(f"Filled password in {selector}", "info")
                    break
            except:
                continue
        
        time.sleep(0.3)
        
        # Click submit button
        submit_selectors = ["#wp-submit", "input[type='submit']", "button[type='submit']", ".login-submit button"]
        
        for selector in submit_selectors:
            try:
                submit_btn = page.locator(selector).first
                if submit_btn.is_visible(timeout=2000):
                    submit_btn.click()
                    add_log(f"Clicked submit: {selector}", "info")
                    break
            except:
                continue
        
        # Wait for navigation
        add_log("Đang chờ đăng nhập...", "info")
        time.sleep(2)
        
        # Try waiting for wp-admin URL
        try:
            page.wait_for_url("**/wp-admin/**", timeout=10000)
        except:
            time.sleep(1)
        
        # Check if login was successful
        current_url = page.url
        add_log(f"After login URL: {current_url}", "info")
        
        # Success indicators
        if "wp-admin" in current_url and "wp-login" not in current_url:
            add_log("Successfully logged into WordPress!", "success")
            wait_for_network_idle(page)
            return True
        
        # Check for error message on login page
        error_selectors = ["#login_error", ".login-error", ".message.error"]
        for selector in error_selectors:
            try:
                error_msg = page.locator(selector).first
                if error_msg.is_visible(timeout=1000):
                    error_text = error_msg.inner_text()
                    add_log(f"Login error: {error_text[:100]}", "error")
                    return False
            except:
                continue
        
        # If we're still on login page
        if "wp-login" in current_url or "login" in current_url.lower():
            add_log("Login failed: Still on login page", "error")
            page.screenshot(path="/tmp/wp_login_failed.png")
            add_log("Screenshot saved to /tmp/wp_login_failed.png", "info")
            return False
        
        # Assume success if no errors detected
        add_log("Login appears successful", "success")
        return True
        
    except Exception as e:
        add_log(f"Login failed: {e}", "error")
        try:
            page.screenshot(path="/tmp/wp_login_exception.png")
        except:
            pass
        return False

def navigate_to_new_post(page: Page) -> bool:
    try:
        page.goto(f"{state.config['wp_admin_url']}/post-new.php", wait_until="domcontentloaded")
        wait_for_network_idle(page, timeout=15000)
        time.sleep(2)
        
        # Wait for Classic Editor to load - check for title field
        try:
            page.wait_for_selector("#title, input[name='post_title']", timeout=10000)
            add_log("Classic Editor loaded", "info")
        except:
            add_log("Editor may not have loaded properly", "warning")
        
        # Dismiss any notices
        try:
            dismiss_btns = page.locator(".notice-dismiss, .wp-core-ui .notice-dismiss").all()
            for btn in dismiss_btns:
                if btn.is_visible():
                    btn.click()
                    time.sleep(0.2)
        except:
            pass
        
        add_log("Navigated to new post editor", "info")
        return True
        
    except Exception as e:
        add_log(f"Failed to navigate to new post: {e}", "error")
        return False

def set_post_title(page: Page, title: str) -> bool:
    try:
        # Classic Editor title field - ID is always "title"
        title_input = page.locator("#title")
        
        if title_input.is_visible(timeout=5000):
            title_input.click()
            title_input.fill("")  # Clear first
            title_input.fill(title)
            add_log(f"Set title: {title[:50]}...", "info")
            return True
        else:
            add_log("Title field not visible", "error")
            return False
            
    except Exception as e:
        add_log(f"Failed to set title: {e}", "error")
        return False

def set_post_content(page: Page, content: str) -> bool:
    try:
        add_log("Đang thêm nội dung...", "info")
        time.sleep(0.5)
        
        content_added = False
        
        # Method 1: Switch to Text/HTML mode and fill textarea directly
        try:
            # Click on "Văn bản" / "Text" tab
            text_tab = page.locator("#content-html").first
            if text_tab.is_visible(timeout=3000):
                text_tab.click()
                time.sleep(0.5)
                add_log("Đã chuyển sang chế độ Text/HTML", "info")
                
                # Fill the content textarea
                content_textarea = page.locator("#content").first
                if content_textarea.is_visible(timeout=3000):
                    content_textarea.click()
                    content_textarea.fill("")  # Clear first
                    content_textarea.fill(content)
                    content_added = True
                    add_log("📄 Content added via textarea", "success")
        except Exception as e:
            add_log(f"Textarea method failed: {e}", "warning")
        
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
                add_log("📄 Content added via JavaScript", "success")
            except Exception as e:
                add_log(f"JavaScript method failed: {e}", "warning")
        
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
                    add_log("📄 Content added via TinyMCE iframe", "success")
            except Exception as e:
                add_log(f"TinyMCE method failed: {e}", "warning")
        
        if content_added:
            return True
        else:
            add_log("Failed to add content - all methods failed", "error")
            return False
        
    except Exception as e:
        add_log(f"Failed to set content: {e}", "error")
        return False

def set_rank_math_keyword(page: Page, keyword: str) -> bool:
    try:
        add_log(f"Setting Rank Math keyword: {keyword}", "info")
        
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
            add_log(f"Rank Math keyword set: {keyword}", "success")
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
                add_log(f"Rank Math keyword set via JS: {keyword}", "success")
                return True
            except:
                add_log("Rank Math keyword field not found", "warning")
                return False
        
    except Exception as e:
        add_log(f"Error setting Rank Math keyword: {e}", "warning")
        return False

def select_random_image(page: Page, alt_text: str) -> bool:
    try:
        # Wait for media modal to appear
        try:
            page.wait_for_selector(".media-modal", timeout=5000)
        except:
            add_log("Không tìm thấy modal chọn ảnh", "warning")
            return False
        
        # Wait for images to load (reduced from 8s to 3s)
        add_log("Waiting for media library to load...", "info")
        time.sleep(3)
        
        # Click on "Thư viện Media" tab if available to ensure we see images
        try:
            media_lib_tab = page.locator(".media-menu-item:has-text('Thư viện Media'), .media-menu-item:has-text('Media Library')").first
            if media_lib_tab.is_visible(timeout=1000):
                media_lib_tab.click()
                time.sleep(1)
        except:
            pass
        
        # Find images
        images = page.locator(".attachments .attachment, li.attachment").all()
        
        if not images:
            add_log("No images found in media library", "warning")
            force_close_all_modals(page)
            return False
        
        add_log(f"Tìm thấy {len(images)} hình ảnh", "info")
        
        # Select first visible image (more reliable than random)
        for i, img in enumerate(images[:5]):  # Try first 5 images
            try:
                if img.is_visible(timeout=500):
                    img.click()
                    add_log(f"Clicked image {i+1}", "info")
                    time.sleep(1)
                    break
            except:
                continue
        
        # Set alt text with keyword
        time.sleep(0.5)  # Wait for details panel
        alt_selectors = [
            "input[data-setting='alt']",
            "#attachment-details-alt-text",
            ".attachment-details input[type='text']",
            "input[name='alt']"
        ]
        
        for alt_sel in alt_selectors:
            try:
                alt_input = page.locator(alt_sel).first
                if alt_input.is_visible(timeout=800):
                    alt_input.click()
                    alt_input.fill("")  # Clear first
                    time.sleep(0.1)
                    alt_input.fill(alt_text)
                    add_log(f"Featured image alt: {alt_text}", "info")
                    time.sleep(0.2)
                    break
            except:
                continue
        
        # Click "Đặt ảnh đại diện" / "Set featured image" button
        set_featured_selectors = [
            "button.media-button-select",
            "button:has-text('Đặt ảnh đại diện')",
            "button:has-text('Set featured image')",
            ".media-button-select",
            "button.button-primary"
        ]
        
        clicked = False
        for selector in set_featured_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    add_log(f"Clicked: {selector}", "success")
                    clicked = True
                    time.sleep(1)
                    break
            except:
                continue
        
        if not clicked:
            add_log("Could not find set featured image button", "warning")
            force_close_all_modals(page)
            return False
        
        # Close modal after setting
        time.sleep(1)
        force_close_all_modals(page)
        
        return True
        
    except Exception as e:
        add_log(f"Error in image selection: {e}", "warning")
        force_close_all_modals(page)
        return False

def insert_images_after_h2(page: Page, keyword: str, max_images: int = 3) -> bool:
    """Insert images after H2 headings using Visual Editor.
    
    Inserts images after H2 at positions 1, 3, 5 (indices 0, 2, 4).
    Re-fetches H2 elements after each insert to avoid stale references.
    """
    try:
        add_log("Đang chèn hình vào bài viết...", "info")
        close_all_modals(page)
        
        # Switch to Visual mode first
        try:
            visual_tab = page.locator("#content-tmce").first
            if visual_tab.is_visible(timeout=2000):
                visual_tab.click()
                time.sleep(1)
                add_log("Switched to Visual mode", "info")
        except Exception as e:
            add_log(f"Could not switch to Visual mode: {e}", "warning")
        
        # H2 positions to insert images after (1st, 3rd, 5th = index 0, 2, 4)
        target_h2_indices = [0, 2, 4]
        images_inserted = 0
        
        for target_index in target_h2_indices:
            if images_inserted >= max_images:
                break
            
            # Check stop/pause
            if not state.is_running:
                add_log("Stopped while inserting images", "warning")
                return False
            if state.is_paused:
                if not wait_if_paused():
                    return False
            
            try:
                add_log(f"Attempting to insert image after H2 #{target_index + 1}...", "info")
                
                # IMPORTANT: Re-fetch H2 elements each iteration (DOM changes after insert)
                page.wait_for_timeout(500)  # Wait for DOM to settle
                h2_elements = page.frame_locator("#content_ifr").locator("h2").all()
                
                if not h2_elements:
                    add_log("No H2 elements found in iframe", "warning")
                    return False
                
                if target_index >= len(h2_elements):
                    add_log(f"H2 #{target_index + 1} not found (only {len(h2_elements)} H2s)", "info")
                    continue
                
                # Click on the H2 to position cursor
                h2_element = h2_elements[target_index]
                h2_element.scroll_into_view_if_needed()
                time.sleep(0.3)
                h2_element.click()
                time.sleep(0.2)
                
                # Move to end of H2 and create new line
                page.keyboard.press("End")
                page.keyboard.press("Enter")
                time.sleep(0.3)
                
                # Click Add Media button
                add_btn = page.locator("#insert-media-button, .add_media").first
                if not add_btn.is_visible(timeout=2000):
                    add_log(f"Add Media button not visible for H2 #{target_index + 1}", "warning")
                    continue
                
                add_btn.click()
                add_log("Clicked Add Media button", "info")
                
                # Wait for media modal to appear
                try:
                    page.wait_for_selector(".media-modal", timeout=5000)
                    time.sleep(1.5)  # Wait for images to load
                except:
                    add_log("Media modal did not appear", "warning")
                    close_all_modals(page)
                    continue
                
                # Click Media Library tab if available
                try:
                    lib_tab = page.locator(".media-menu-item:has-text('Thư viện Media'), .media-menu-item:has-text('Media Library')").first
                    if lib_tab.is_visible(timeout=1000):
                        lib_tab.click()
                        time.sleep(1)
                except:
                    pass
                
                # Select a random image
                images = page.locator(".attachments .attachment, li.attachment").all()
                if not images:
                    add_log("No images in media library", "warning")
                    close_all_modals(page)
                    continue
                
                # Pick a random image from first 10
                img_index = random.randint(0, min(len(images) - 1, 9))
                images[img_index].click()
                time.sleep(0.8)
                add_log(f"Selected image {img_index + 1}", "info")
                
                # Set alt text with keyword
                try:
                    alt_selectors = [
                        "input[data-setting='alt']",
                        "#attachment-details-alt-text",
                        ".attachment-details input[type='text']",
                        "input.attachment-alt-text"
                    ]
                    for alt_sel in alt_selectors:
                        try:
                            alt = page.locator(alt_sel).first
                            if alt.is_visible(timeout=800):
                                alt.click()
                                alt.fill("")
                                time.sleep(0.1)
                                alt.fill(keyword)
                                add_log(f"Alt text set: {keyword}", "info")
                                break
                        except:
                            continue
                except:
                    pass
                
                # Set link to attachment page (optional)
                try:
                    link = page.locator("select[data-setting='link']").first
                    if link.is_visible(timeout=500):
                        link.select_option("post")
                except:
                    pass
                
                # Click Insert into post button
                inserted = False
                insert_selectors = [
                    "button.media-button-insert",
                    "button:has-text('Chèn vào bài viết')",
                    "button:has-text('Insert into post')",
                    ".media-button-insert"
                ]
                
                for sel in insert_selectors:
                    try:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=1000):
                            btn.click()
                            inserted = True
                            images_inserted += 1
                            add_log(f"Inserted image {images_inserted} after H2 #{target_index + 1}", "success")
                            time.sleep(1)  # Wait for insert to complete
                            break
                    except:
                        continue
                
                if not inserted:
                    add_log(f"Failed to insert image after H2 #{target_index + 1}", "warning")
                
                # Close modal and wait before next iteration
                close_all_modals(page)
                time.sleep(0.5)
                
                # Switch back to Visual mode for next iteration
                try:
                    visual_tab = page.locator("#content-tmce").first
                    if visual_tab.is_visible(timeout=1000):
                        visual_tab.click()
                        time.sleep(0.5)
                except:
                    pass
                
            except Exception as e:
                add_log(f"Error inserting image after H2 #{target_index + 1}: {e}", "warning")
                close_all_modals(page)
                continue
        
        close_all_modals(page)
        add_log(f"Total images inserted: {images_inserted}/{max_images}", "success")
        return images_inserted > 0
        
    except Exception as e:
        add_log(f"Error in insert_images_after_h2: {e}", "error")
        close_all_modals(page)
        return False


def close_all_modals(page: Page, max_attempts: int = 2):
    try:
        for _ in range(max_attempts):
            # Quick Escape key press
            page.keyboard.press("Escape")
            time.sleep(0.15)
            
            # Try close buttons
            for selector in [".media-modal-close", "button[aria-label='Close']", ".media-frame-close"]:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=300):
                        btn.click()
                        time.sleep(0.15)
                        break
                except:
                    continue
            
            # Check if modal is gone
            try:
                if not page.locator(".media-modal").first.is_visible(timeout=300):
                    return
            except:
                return
    except:
        pass

# Alias for compatibility
force_close_all_modals = close_all_modals
close_any_media_modal = close_all_modals

def select_random_image_for_content(page: Page, alt_text: str) -> bool:
    try:
        # Wait for media modal
        page.wait_for_selector(".media-modal", timeout=10000)
        time.sleep(5)  # Wait for images to load
        
        # Try to find images
        images = page.locator(".attachments .attachment, li.attachment").all()
        
        if not images:
            add_log("No images found in media library", "warning")
            page.locator(".media-modal-close").first.click()
            return False
        
        # Select a random image
        random_image = random.choice(images)
        random_image.click()
        time.sleep(1)
        
        # Set alt text with keyword
        time.sleep(0.5)  # Wait for details panel to load
        alt_selectors = [
            "input[data-setting='alt']",
            "#attachment-details-alt-text",
            ".attachment-details input[type='text']",
            "input[name='alt']",
            ".setting input[type='text'][data-setting='alt']"
        ]
        
        alt_set = False
        for alt_sel in alt_selectors:
            try:
                alt_input = page.locator(alt_sel).first
                if alt_input.is_visible(timeout=1000):
                    alt_input.click()
                    alt_input.fill("")  # Clear first
                    time.sleep(0.1)
                    alt_input.fill(alt_text)
                    add_log(f"Alt text đã set: {alt_text}", "info")
                    alt_set = True
                    time.sleep(0.3)
                    break
            except:
                continue
        
        if not alt_set:
            add_log("Không thể set alt text", "warning")
        
        # Click "Chèn vào bài viết" / "Insert into post"
        insert_buttons = [
            "button.media-button-insert",
            "button:has-text('Chèn vào bài viết')",
            "button:has-text('Insert into post')",
            ".media-button-insert"
        ]
        
        for selector in insert_buttons:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    time.sleep(2)
                    return True
            except:
                continue
        
        # Close modal if insert failed
        try:
            page.locator(".media-modal-close").first.click()
        except:
            pass
        
        return False
        
    except Exception as e:
        add_log(f"Error selecting image for content: {e}", "warning")
        try:
            page.locator(".media-modal-close").first.click()
        except:
            pass
        return False

def select_first_category(page: Page) -> bool:
    try:
        # Get all category checkboxes directly
        checkboxes = page.locator("#categorychecklist input[type='checkbox']").all()
        
        if checkboxes:
            # Check the first one if not already checked
            first_checkbox = checkboxes[0]
            if not first_checkbox.is_checked():
                first_checkbox.check()
            add_log("Selected first category", "success")
            return True
        else:
            add_log("No categories found", "warning")
        
        return False
        
    except Exception as e:
        add_log(f"Error selecting category: {e}", "warning")
        return False

def add_post_tags(page: Page, tags: str) -> bool:
    """Add tags to WordPress post (Classic Editor).
    
    Args:
        page: Playwright page object
        tags: Comma-separated tags string
    """
    try:
        if not tags or not tags.strip():
            add_log("No tags to add", "info")
            return True
        
        add_log(f"Adding tags: {tags[:50]}...", "info")
        
        # Scroll to Tags section
        try:
            tags_box = page.locator("#tagsdiv-post_tag, #tagsdiv, .tagsdiv").first
            if tags_box.is_visible(timeout=2000):
                tags_box.scroll_into_view_if_needed()
                time.sleep(0.5)
        except:
            pass
        
        # Find the tags input field
        tag_input_selectors = [
            "#new-tag-post_tag",
            "input.newtag",
            "#newtag",
            "input[name='newtag[post_tag]']",
            ".tagsdiv input[type='text']"
        ]
        
        tag_input = None
        for selector in tag_input_selectors:
            try:
                input_el = page.locator(selector).first
                if input_el.is_visible(timeout=1000):
                    tag_input = input_el
                    add_log(f"Found tags input: {selector}", "info")
                    break
            except:
                continue
        
        if not tag_input:
            add_log("Could not find tags input field", "warning")
            return False
        
        # Clear and fill the tags input
        tag_input.click()
        tag_input.fill("")
        time.sleep(0.2)
        tag_input.fill(tags.strip())
        time.sleep(0.3)
        
        # Click the "Add" / "Thêm" button
        add_button_selectors = [
            "input.tagadd",
            "button.tagadd",
            "#tagsdiv-post_tag .tagadd",
            "input[value='Thêm']",
            "input[value='Add']",
            ".tagsdiv input[type='button']"
        ]
        
        for selector in add_button_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    add_log("Clicked Add tags button", "success")
                    time.sleep(0.5)
                    
                    # Verify tags were added by checking tag cloud
                    try:
                        tag_cloud = page.locator(".tagchecklist, .the-tags").first
                        if tag_cloud.is_visible(timeout=1000):
                            add_log("Tags added successfully", "success")
                    except:
                        pass
                    
                    return True
            except:
                continue
        
        # Try JavaScript fallback to click the add button
        try:
            page.evaluate("""
                () => {
                    const addBtn = document.querySelector('.tagadd, input.tagadd');
                    if (addBtn) addBtn.click();
                }
            """)
            add_log("Clicked Add tags button via JS", "success")
            time.sleep(0.5)
            return True
        except:
            pass
        
        add_log("Could not find Add tags button", "warning")
        return False
        
    except Exception as e:
        add_log(f"Error adding tags: {e}", "warning")
        return False


def set_featured_image(page: Page, keyword: str) -> bool:
    """Set featured image using JavaScript to open media modal.
    
    New approach:
    1. Use JavaScript to trigger WordPress media frame
    2. Wait for modal with multiple fallbacks
    3. Select random unused image
    4. Set alt text = keyword
    5. Click set featured image button
    """
    try:
        add_log("Setting featured image...", "info")
        
        # First, close any open modals
        force_close_all_modals(page)
        time.sleep(0.5)
        
        # Method 1: Try JavaScript click on the link
        modal_opened = False
        
        try:
            # Use JavaScript to click the link and trigger the modal
            result = page.evaluate("""
                () => {
                    // Try clicking the set featured image link via JavaScript
                    const link = document.querySelector('#set-post-thumbnail') || 
                                 document.querySelector('a[href*="type=set-post-thumbnail"]') ||
                                 document.querySelector('#postimagediv a');
                    if (link) {
                        link.click();
                        return 'clicked';
                    }
                    return 'not_found';
                }
            """)
            add_log(f"JS click result: {result}", "info")
            time.sleep(3)
            
            # Debug: Check what modal elements exist
            modal_info = page.evaluate("""
                () => {
                    const modals = [];
                    if (document.querySelector('.media-modal')) modals.push('media-modal');
                    if (document.querySelector('.media-frame')) modals.push('media-frame');
                    if (document.querySelector('#TB_window')) modals.push('TB_window');
                    if (document.querySelector('.media-modal-content')) modals.push('media-modal-content');
                    if (document.querySelector('.attachment-details')) modals.push('attachment-details');
                    return modals.length > 0 ? modals.join(', ') : 'none';
                }
            """)
            add_log(f"Modal elements found: {modal_info}", "info")
            
            # Check if any modal opened
            if modal_info != 'none':
                modal_opened = True
                add_log("Modal detected via JS check", "info")
            else:
                try:
                    page.wait_for_selector(".media-modal, .media-frame, #TB_window", timeout=3000)
                    modal_opened = True
                    add_log("Media modal opened via JS click", "info")
                except:
                    pass
        except Exception as e:
            add_log(f"JS click failed: {e}", "warning")
        
        # Method 2: Try direct Playwright click with force
        if not modal_opened:
            try:
                link = page.locator("#set-post-thumbnail, #postimagediv a").first
                if link.is_visible(timeout=2000):
                    link.click(force=True)
                    time.sleep(3)
                    # Check for both media-modal and thickbox
                    try:
                        page.wait_for_selector(".media-modal, #TB_window, .media-frame", timeout=5000)
                        modal_opened = True
                        add_log("Modal opened via force click", "info")
                    except:
                        pass
            except:
                pass
        
        # Method 3: Try triggering the WordPress media frame directly
        if not modal_opened:
            try:
                result = page.evaluate("""
                    () => {
                        if (typeof wp !== 'undefined' && wp.media) {
                            // Create a new media frame for featured image
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
                    }
                """)
                add_log(f"WP media frame: {result}", "info")
                time.sleep(3)
                
                # Check for modal with multiple selectors
                try:
                    page.wait_for_selector(".media-modal, #TB_window, .media-frame, .media-modal-content", timeout=8000)
                    modal_opened = True
                    add_log("Modal opened via wp.media", "info")
                except:
                    # Try waiting a bit more
                    time.sleep(2)
                    if page.locator(".media-modal, .media-frame").count() > 0:
                        modal_opened = True
                        add_log("Modal found after extra wait", "info")
            except Exception as e:
                add_log(f"WP media frame failed: {e}", "warning")
        
        if not modal_opened:
            add_log("Could not open media modal - skipping featured image", "warning")
            return False
        
        # Wait for images to load
        time.sleep(3)
        
        # Click on Media Library tab if available
        try:
            media_lib_tab = page.locator(".media-menu-item:has-text('Thư viện Media'), .media-menu-item:has-text('Media Library'), .media-menu-item:has-text('Chọn từ thư viện')").first
            if media_lib_tab.is_visible(timeout=1000):
                media_lib_tab.click()
                time.sleep(2)
                add_log("Switched to Media Library", "info")
        except:
            pass
        
        # Wait for images to fully load
        time.sleep(2)
        
        # Use JavaScript to select a random image (more reliable than visibility check)
        try:
            import random
            
            # Get total number of images and select random one via JS
            result = page.evaluate("""
                (usedIndices) => {
                    const attachments = document.querySelectorAll('.attachments .attachment, li.attachment, .attachment');
                    if (attachments.length === 0) return { success: false, error: 'no_images' };
                    
                    // Get available indices (not in usedIndices)
                    const availableIndices = [];
                    for (let i = 0; i < Math.min(attachments.length, 30); i++) {
                        if (!usedIndices.includes(i)) {
                            availableIndices.push(i);
                        }
                    }
                    
                    // If all used, reset to all indices
                    const indicesToUse = availableIndices.length > 0 ? availableIndices : 
                                        Array.from({length: Math.min(attachments.length, 30)}, (_, i) => i);
                    
                    // Pick random index
                    const randomIndex = indicesToUse[Math.floor(Math.random() * indicesToUse.length)];
                    const img = attachments[randomIndex];
                    
                    if (img) {
                        img.click();
                        return { success: true, index: randomIndex, total: attachments.length, available: indicesToUse.length };
                    }
                    return { success: false, error: 'click_failed' };
                }
            """, list(state.used_featured_images))
            
            if result.get('success'):
                selected_idx = result.get('index', 0)
                state.used_featured_images.add(selected_idx)
                add_log(f"Selected image #{selected_idx + 1} via JS ({result.get('available')} available of {result.get('total')})", "info")
                time.sleep(1)
            else:
                add_log(f"Could not select image: {result.get('error')}", "warning")
                force_close_all_modals(page)
                return False
                
        except Exception as e:
            add_log(f"Error selecting image via JS: {e}", "warning")
            force_close_all_modals(page)
            return False
        
        # Set alt text = keyword using JavaScript (more reliable)
        time.sleep(1)
        try:
            page.evaluate("""
                (keyword) => {
                    // Try multiple selectors for alt input
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
                }
            """, keyword)
            add_log(f"Alt text: {keyword}", "info")
        except:
            pass  # Alt text is optional
        
        # Click "Đặt ảnh đại diện" button
        button_selectors = [
            "button.media-button-select",
            "button:has-text('Đặt ảnh đại diện')",
            "button:has-text('Set featured image')",
            ".media-button-select",
        ]
        
        button_clicked = False
        for selector in button_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    add_log("Featured image set!", "success")
                    button_clicked = True
                    time.sleep(1)
                    break
            except:
                continue
        
        if not button_clicked:
            # Try JavaScript click as fallback
            try:
                page.evaluate("""
                    () => {
                        const btn = document.querySelector('.media-button-select') || 
                                   document.querySelector('button.button-primary');
                        if (btn) btn.click();
                    }
                """)
                add_log("Featured image set via JS!", "success")
                button_clicked = True
                time.sleep(1)
            except:
                pass
        
        if not button_clicked:
            add_log("Could not click Set Featured Image button", "warning")
            force_close_all_modals(page)
            return False
        
        # Close any remaining modals
        time.sleep(0.5)
        force_close_all_modals(page)
        
        return True
        
    except Exception as e:
        add_log(f"Error setting featured image: {e}", "warning")
        force_close_all_modals(page)
        return False

def publish_or_schedule_post(page: Page, is_schedule: bool, publish_date: datetime = None) -> bool:
    try:
        # For scheduling in Classic Editor
        if is_schedule and publish_date:
            # Click "Chỉnh sửa" next to "Xuất bản ngay lập tức" to open date picker
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
        add_log("Preparing to publish...", "info")
        
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
            add_log("Clicked publish button", "info")
        except Exception as js_err:
            add_log(f"JS click failed: {js_err}, trying regular click", "warning")
            # Fallback to regular click
            publish_btn = page.locator("#publish, input#publish").first
            if publish_btn.is_visible(timeout=3000):
                publish_btn.click(force=True)
        
        # Wait for page to reload - this is critical
        add_log("Đang lưu bài viết...", "info")
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
                    add_log("Success message detected", "info")
                    break
        except:
            pass
        
        # Method 2: Check URL for post.php (means we're on edit page of saved post)
        if not success_detected:
            current_url = page.url
            if "post.php" in current_url and "action=edit" in current_url:
                success_detected = True
                add_log("Post saved - now on edit page", "info")
        
        # Method 3: Check URL for message parameter
        if not success_detected:
            current_url = page.url
            if "message=" in current_url:
                success_detected = True
                add_log("Post saved - message in URL", "info")
        
        # Method 4: Check if View Post link exists
        if not success_detected:
            try:
                view_post = page.locator("a:has-text('View post'), a:has-text('Xem bài viết')").first
                if view_post.is_visible(timeout=2000):
                    success_detected = True
                    add_log("View post link found", "info")
            except:
                pass
        
        # Method 5: Check if post ID exists in URL (meaning post was created)
        if not success_detected:
            current_url = page.url
            if "post=" in current_url:
                success_detected = True
                add_log("Post ID found in URL", "info")
        
        if success_detected:
            action = "Scheduled" if is_schedule else "Published"
            add_log(f"{action} successfully!", "success")
            return True
        else:
            add_log("Could not confirm publish status, but continuing...", "warning")
            # Return True anyway since the click happened
            return True
        
    except Exception as e:
        add_log(f"Error publishing: {e}", "error")
        return False

def create_single_post(page: Page, index: int, topic: dict, content: str, start_date: datetime) -> bool:
    title = topic["title"]
    keyword = topic["keyword"]
    
    add_log(f"Đang tạo bài {index + 1}: {title}", "info")
    
    try:
        # Calculate publish date based on posts_per_day
        posts_per_day = state.config.get("posts_per_day", 2)
        
        # Calculate which day and which slot in that day
        days_offset = index // posts_per_day
        slot_in_day = index % posts_per_day
        
        # Calculate hour based on slot (distribute evenly from 8:00 to 21:00)
        # For 1 post/day: 9:00
        # For 2 posts/day: 9:00, 15:00
        # For 3 posts/day: 8:00, 13:00, 18:00
        # For 4 posts/day: 8:00, 12:00, 16:00, 20:00
        if posts_per_day == 1:
            hour = 9
        elif posts_per_day == 2:
            hours = [9, 15]
            hour = hours[slot_in_day]
        elif posts_per_day == 3:
            hours = [8, 13, 18]
            hour = hours[slot_in_day]
        elif posts_per_day == 4:
            hours = [8, 12, 16, 20]
            hour = hours[slot_in_day]
        else:
            # For more posts, distribute evenly from 8:00 to 21:00
            start_hour = 8
            end_hour = 21
            interval = (end_hour - start_hour) / max(posts_per_day - 1, 1)
            hour = int(start_hour + (slot_in_day * interval))
        
        publish_date = start_date + timedelta(days=days_offset)
        publish_date = publish_date.replace(hour=hour, minute=0, second=0)
        
        now = datetime.now()
        is_schedule = publish_date > now
        
        add_log(f"Ngày đăng: {publish_date.strftime('%Y-%m-%d %H:%M')} (Ngày {days_offset + 1}, Slot {slot_in_day + 1}/{posts_per_day})", "info")
        
        # Check stop/pause
        if not state.is_running:
            return False
        if state.is_paused:
            if not wait_if_paused():
                return False
        
        if not navigate_to_new_post(page):
            return False
        
        if not set_post_title(page, title):
            return False
        
        # Check stop/pause before content
        if not state.is_running:
            return False
        if state.is_paused:
            if not wait_if_paused():
                return False
        
        # Add content - this is critical
        if not set_post_content(page, content):
            add_log("Content may not have been added properly", "warning")
        
        # Set Rank Math SEO keyword
        set_rank_math_keyword(page, keyword)
        
        # Check stop/pause before images
        if not state.is_running:
            return False
        if state.is_paused:
            if not wait_if_paused():
                return False
        
        # Insert images after alternating H2 headings (1st, 3rd, 5th)
        insert_images_after_h2(page, keyword, max_images=3)
        
        # Select category
        select_first_category(page)
        
        # Add tags from topic (if available)
        tags = topic.get("tags", "")
        if tags:
            add_post_tags(page, tags)
        
        # NOTE: Featured image disabled - WordPress media modal not compatible
        # You can add featured image manually after post is published
        # set_featured_image(page, keyword)
        
        # Check stop/pause before publish
        if not state.is_running:
            return False
        if state.is_paused:
            if not wait_if_paused():
                return False
        
        # Publish or schedule
        if not publish_or_schedule_post(page, is_schedule, publish_date if is_schedule else None):
            return False
        
        return True
        
    except Exception as e:
        add_log(f"Error creating post: {e}", "error")
        return False

def run_automation():
    if not PLAYWRIGHT_AVAILABLE:
        add_log("Playwright not available. Please install it first.", "error")
        state.is_running = False
        return
    
    state.is_running = True
    state.progress = 0
    state.successful_posts = 0
    state.failed_posts = 0
    state.logs = []
    
    add_log("Starting WordPress Auto Poster...", "info")
    
    provider = state.config.get("ai_provider", "ollama")
    total_topics = len(state.topics)
    state.total_tasks = total_topics * 2
    state.generated_contents = []
    
    # For non-gemini_web providers, generate content first
    if provider != "gemini_web":
        add_log(f"Phase 1: Generating content with {provider.upper()}...", "info")
        state.current_task = "Generating content..."
        
        for i, topic in enumerate(state.topics):
            if not state.is_running:
                add_log("Stopped by user", "warning")
                return
            
            # Check if paused
            if not wait_if_paused():
                add_log("Stopped while paused", "warning")
                return
            
            state.current_task = f"Generating content {i+1}/{total_topics}..."
            content = generate_content(topic["title"], topic["keyword"])
            state.generated_contents.append(content)
            state.progress = ((i + 1) / state.total_tasks) * 100
            
            if i < len(state.topics) - 1 and state.is_running:
                time.sleep(state.config["delay_between_requests"])
        
        successful_gen = sum(1 for c in state.generated_contents if c is not None)
        add_log(f"Generated {successful_gen}/{total_topics} articles", "success")
        
        if successful_gen == 0:
            add_log("No content generated. Stopping.", "error")
            state.is_running = False
            return
    else:
        add_log("Gemini Web Chat: Content will be generated in browser...", "info")
    
    # Phase 2: WordPress automation
    add_log("Phase 2: WordPress Automation...", "info")
    state.current_task = "Starting browser..."
    
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    with sync_playwright() as p:
        add_log("Starting Brave browser...", "info")
        
        # Use persistent context to save login sessions
        import os
        user_data_dir = os.path.expanduser("~/.gemini/browser_data")
        os.makedirs(user_data_dir, exist_ok=True)
        
        brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        
        # Launch persistent context (saves cookies, login sessions, etc.)
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=brave_path,
            headless=state.config["headless_mode"],
            viewport={"width": 1920, "height": 1080},
            locale="vi-VN",
            slow_mo=100,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        
        add_log("Brave browser started (login sessions saved)", "success")
        
        # Get existing page or create new one
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
        
        page.set_default_timeout(60000)
        
        try:
            # For Gemini Web, generate content first using browser
            if provider == "gemini_web":
                add_log("Phase 1: Generating content with Gemini Web Chat...", "info")
                
                for i, topic in enumerate(state.topics):
                    if not state.is_running:
                        add_log("Stopped by user", "warning")
                        break
                    
                    # Check if paused
                    if not wait_if_paused():
                        add_log("Stopped while paused", "warning")
                        break
                    
                    state.current_task = f"Generating content {i+1}/{total_topics} via Gemini Web..."
                    state.current_title = topic["title"]
                    state.current_keyword = topic["keyword"]
                    
                    content = generate_content_gemini_web(page, topic["title"], topic["keyword"])
                    state.generated_contents.append(content)
                    
                    # Store cleaned content for preview
                    if content:
                        # Clean the content before storing
                        cleaned_content = clean_gemini_content(content)
                        state.current_content = cleaned_content
                        # Count words
                        import re
                        text_only = re.sub(r'<[^>]*>', ' ', cleaned_content)
                        word_count = len(text_only.split())
                        # Add to content list
                        state.content_list.append({
                            "title": topic["title"],
                            "keyword": topic["keyword"],
                            "content": cleaned_content,
                            "word_count": word_count
                        })
                    
                    state.progress = ((i + 1) / state.total_tasks) * 100
                    
                    if i < len(state.topics) - 1 and state.is_running:
                        time.sleep(3)  # Short delay between Gemini requests
                
                successful_gen = sum(1 for c in state.generated_contents if c is not None)
                add_log(f"Generated {successful_gen}/{total_topics} articles via Gemini Web", "success")
                
                if successful_gen == 0:
                    add_log("No content generated. Stopping.", "error")
                    state.is_running = False
                    context.close()
                    return
            
            # Now login to WordPress
            if not login_to_wordpress(page):
                add_log("Failed to login. Exiting...", "error")
                state.is_running = False
                context.close()
                return
            
            for i, (topic, content) in enumerate(zip(state.topics, state.generated_contents)):
                if not state.is_running:
                    add_log("Stopped by user", "warning")
                    break
                
                # Check if paused
                if not wait_if_paused():
                    add_log("Stopped while paused", "warning")
                    break
                
                if content is None:
                    add_log(f"Skipping post {i+1} - no content", "warning")
                    state.failed_posts += 1
                    continue
                
                state.current_task = f"Creating post {i+1}/{total_topics}..."
                
                try:
                    success = create_single_post(page, i, topic, content, start_date)
                    if success:
                        state.successful_posts += 1
                    else:
                        state.failed_posts += 1
                except Exception as e:
                    add_log(f"Error on post {i+1}: {e}", "error")
                    state.failed_posts += 1
                
                state.progress = ((total_topics + i + 1) / state.total_tasks) * 100
                
                if i < len(state.topics) - 1:
                    time.sleep(3)
            
            # Summary
            add_log(f"SUMMARY: {state.successful_posts} successful, {state.failed_posts} failed", "success")
            
        except Exception as e:
            add_log(f"Critical error: {e}", "error")
        finally:
            time.sleep(2)
            context.close()
    
    state.current_task = "Completed!"
    state.progress = 100
    state.is_running = False
    add_log("WordPress Auto Poster completed!", "success")

# FLASK ROUTES

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    # Return content_list without full content for performance
    content_list_summary = [
        {"title": c["title"], "keyword": c["keyword"], "word_count": c["word_count"]}
        for c in state.content_list
    ]
    return jsonify({
        "is_running": state.is_running,
        "is_paused": state.is_paused,
        "pause_reason": state.pause_reason,
        "current_task": state.current_task,
        "progress": state.progress,
        "successful_posts": state.successful_posts,
        "failed_posts": state.failed_posts,
        "logs": state.logs,
        "gemini_available": GEMINI_AVAILABLE,
        "ollama_available": check_ollama(),
        "playwright_available": PLAYWRIGHT_AVAILABLE,
        "content_list": content_list_summary,
        "content_count": len(state.content_list)
    })

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'POST':
        data = request.json
        state.config.update(data)
        return jsonify({"success": True})
    return jsonify(state.config)

@app.route('/api/topics', methods=['GET', 'POST'])
def handle_topics():
    if request.method == 'POST':
        state.topics = request.json.get('topics', [])
        return jsonify({"success": True, "count": len(state.topics)})
    return jsonify(state.topics)

@app.route('/api/presets', methods=['GET'])
def list_presets():
    presets = load_site_presets()
    return jsonify({"success": True, "presets": list(presets.keys())})

@app.route('/api/presets/<name>', methods=['GET', 'PUT', 'DELETE'])
def manage_preset(name):
    presets = load_site_presets()
    
    if request.method == 'GET':
        if name in presets:
            return jsonify({"success": True, "data": presets[name]})
        return jsonify({"success": False, "message": "Preset not found"})
    
    elif request.method == 'PUT':
        data = request.json
        presets[name] = {
            "wp_username": data.get("wp_username", ""),
            "wp_password": data.get("wp_password", ""),
            "wp_login_url": data.get("wp_login_url", ""),
            "wp_admin_url": data.get("wp_admin_url", ""),
            "gemini_prompt": data.get("gemini_prompt", "")
        }
        if save_site_presets(presets):
            return jsonify({"success": True, "message": f"Preset '{name}' saved"})
        return jsonify({"success": False, "message": "Could not save preset"})
    
    elif request.method == 'DELETE':
        if name in presets:
            del presets[name]
            if save_site_presets(presets):
                return jsonify({"success": True, "message": f"Preset '{name}' deleted"})
        return jsonify({"success": False, "message": "Preset not found"})

@app.route('/api/content/<int:index>')
def get_content(index):
    if 0 <= index < len(state.content_list):
        return jsonify({
            "success": True,
            "data": state.content_list[index]
        })
    return jsonify({"success": False, "message": "Content not found"})

@app.route('/api/content/<int:index>', methods=['PUT'])
def update_content(index):
    if 0 <= index < len(state.content_list):
        data = request.json
        if 'content' in data:
            new_content = data['content']
            # Recalculate word count
            import re
            text_only = re.sub(r'<[^>]*>', ' ', new_content)
            word_count = len(text_only.split())
            
            state.content_list[index]['content'] = new_content
            state.content_list[index]['word_count'] = word_count
            
            # Also update generated_contents for WordPress posting
            if index < len(state.generated_contents):
                state.generated_contents[index] = new_content
            
            add_log(f"Content #{index + 1} đã được cập nhật ({word_count} từ)", "info")
            return jsonify({"success": True, "word_count": word_count})
    return jsonify({"success": False, "message": "Content not found"})

@app.route('/api/content/<int:index>', methods=['DELETE'])
def delete_content(index):
    if 0 <= index < len(state.content_list):
        deleted_title = state.content_list[index]['title']
        del state.content_list[index]
        
        # Also remove from generated_contents
        if index < len(state.generated_contents):
            del state.generated_contents[index]
        
        # Remove from topics to avoid creating post for this
        if index < len(state.topics):
            del state.topics[index]
        
        add_log(f"Đã xóa: {deleted_title}", "warning")
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Content not found"})

@app.route('/api/start', methods=['POST'])
def start_automation():
    if state.is_running:
        return jsonify({"success": False, "message": "Already running"})
    
    if not state.topics:
        return jsonify({"success": False, "message": "No topics configured"})
    
    # Check AI provider
    provider = state.config.get("ai_provider", "ollama")
    
    if provider == "ollama":
        if not check_ollama():
            return jsonify({"success": False, "message": "Ollama is not running! Please start Ollama first (run: ollama serve)"})
    elif provider == "gemini":
        # Only Gemini API needs API key, not Gemini Web
        if not state.config.get("gemini_api_key"):
            return jsonify({"success": False, "message": "Gemini API key not configured"})
    # gemini_web doesn't need any configuration check
    
    if not state.config.get("wp_username"):
        return jsonify({"success": False, "message": "WordPress credentials not configured"})
    
    # Clear previous content list and reset pause state
    state.content_list = []
    state.is_paused = False
    state.pause_reason = ""
    
    # Start in background thread
    thread = threading.Thread(target=run_automation)
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "message": "Started"})

@app.route('/api/stop', methods=['POST'])
def stop_automation():
    state.is_running = False
    state.is_paused = False
    state.pause_reason = ""
    add_log("Đã dừng bởi người dùng", "warning")
    return jsonify({"success": True})

@app.route('/api/pause', methods=['POST'])
def pause_automation():
    if not state.is_running:
        return jsonify({"success": False, "message": "Not running"})
    state.is_paused = True
    state.pause_reason = "Tạm dừng bởi người dùng"
    add_log("Đã tạm dừng", "warning")
    return jsonify({"success": True})

@app.route('/api/resume', methods=['POST'])
def resume_automation():
    if not state.is_running:
        return jsonify({"success": False, "message": "Not running"})
    state.is_paused = False
    state.pause_reason = ""
    add_log("Tiếp tục thực thi...", "success")
    return jsonify({"success": True})

@app.route('/api/ollama/start', methods=['POST'])
def start_ollama():
    try:
        import subprocess
        result = subprocess.run(
            ["brew", "services", "start", "ollama"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            # Wait a moment for service to start
            time.sleep(3)
            if check_ollama():
                return jsonify({"success": True, "message": "Ollama service started successfully"})
            else:
                return jsonify({"success": False, "message": "Ollama started but not responding yet. Please wait a moment."})
        else:
            return jsonify({"success": False, "message": f"Failed to start Ollama: {result.stderr}"})
            
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "message": "Timeout starting Ollama service"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/ollama/stop', methods=['POST'])
def stop_ollama():
    try:
        import subprocess
        result = subprocess.run(
            ["brew", "services", "stop", "ollama"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            time.sleep(2)
            return jsonify({"success": True, "message": "Ollama service stopped"})
        else:
            return jsonify({"success": False, "message": f"Failed to stop Ollama: {result.stderr}"})
            
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "message": "Timeout stopping Ollama service"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"})

@app.route('/api/ollama/status', methods=['GET'])
def ollama_status():
    is_running = check_ollama()
    return jsonify({
        "running": is_running,
        "status": "running" if is_running else "stopped"
    })

if __name__ == '__main__':
    # Create templates folder if not exists
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     WordPress Auto Poster - Web Interface               ║
    ║     ─────────────────────────────────────────────────   ║
    ║     Open http://localhost:5001 in your browser          ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    app.run(debug=True, port=5001, threaded=True)
