"""
WordPress Authentication
========================
Login and session management.
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
# LOGIN
# ============================================================================

def login_to_wordpress(page, config: dict, log_func) -> bool:
    """Login to WordPress with improved error handling."""
    try:
        log_func("Logging into WordPress...", "info")
        
        login_url = config.get("wp_login_url", "")
        username = config.get("wp_username", "")
        password = config.get("wp_password", "")
        
        log_func(f"Login URL: {login_url}", "info")
        log_func(f"Username: {username}", "info")
        
        if not login_url or not username or not password:
            log_func("Missing login credentials!", "error")
            return False
        
        # Navigate to login page
        page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(1)
        
        current_url = page.url
        log_func(f"Current URL: {current_url}", "info")
        
        # Check if already logged in
        if "wp-admin" in current_url and "wp-login" not in current_url:
            log_func("Already logged in!", "success")
            return True
        
        # Wait for login form - try multiple selectors
        login_form_found = False
        form_selectors = ["#user_login", "#loginform", "input[name='log']", "#username"]
        
        for selector in form_selectors:
            try:
                if page.locator(selector).first.is_visible(timeout=3000):
                    login_form_found = True
                    log_func(f"Found login form: {selector}", "info")
                    break
            except:
                continue
        
        if not login_form_found:
            log_func("Could not find login form!", "error")
            page.screenshot(path="/tmp/wp_login_error.png")
            log_func("Screenshot saved to /tmp/wp_login_error.png", "info")
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
                    log_func(f"Filled username in {selector}", "info")
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
                    log_func(f"Filled password in {selector}", "info")
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
                    log_func(f"Clicked submit: {selector}", "info")
                    break
            except:
                continue
        
        # Wait for navigation
        log_func("Waiting for login...", "info")
        time.sleep(2)
        
        # Try waiting for wp-admin URL
        try:
            page.wait_for_url("**/wp-admin/**", timeout=10000)
        except:
            time.sleep(1)
        
        # Check if login was successful
        current_url = page.url
        log_func(f"After login URL: {current_url}", "info")
        
        # Success indicators
        if "wp-admin" in current_url and "wp-login" not in current_url:
            log_func("Successfully logged into WordPress!", "success")
            wait_for_network_idle(page)
            return True
        
        # Check for error message on login page
        error_selectors = ["#login_error", ".login-error", ".message.error"]
        for selector in error_selectors:
            try:
                error_msg = page.locator(selector).first
                if error_msg.is_visible(timeout=1000):
                    error_text = error_msg.inner_text()
                    log_func(f"Login error: {error_text[:100]}", "error")
                    return False
            except:
                continue
        
        # If we're still on login page
        if "wp-login" in current_url or "login" in current_url.lower():
            log_func("Login failed: Still on login page", "error")
            page.screenshot(path="/tmp/wp_login_failed.png")
            log_func("Screenshot saved to /tmp/wp_login_failed.png", "info")
            return False
        
        # Assume success if no errors detected
        log_func("Login appears successful", "success")
        return True
        
    except Exception as e:
        log_func(f"Login failed: {e}", "error")
        try:
            page.screenshot(path="/tmp/wp_login_exception.png")
        except:
            pass
        return False
