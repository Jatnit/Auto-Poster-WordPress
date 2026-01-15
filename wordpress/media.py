"""
WordPress Media Functions
==========================
Featured image, media library, and image insertion.
"""

import time
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

# ============================================================================
# MODAL MANAGEMENT
# ============================================================================

def close_all_modals(page, log_func=None, max_attempts: int = 2) -> None:
    """Close all media modals efficiently."""
    try:
        for _ in range(max_attempts):
            close_selectors = [
                ".media-modal-close",
                "button.media-modal-close",
                ".media-modal .media-modal-close"
            ]
            
            for selector in close_selectors:
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

# ============================================================================
# FEATURED IMAGE
# ============================================================================

def set_featured_image(page, keyword: str, log_func) -> bool:
    """Set featured image (Classic Editor) with improved reliability."""
    try:
        log_func("Setting featured image...", "info")
        
        # First close any open modals
        close_all_modals(page, log_func)
        time.sleep(0.3)
        
        # Click "Set featured image" link
        set_image_selectors = [
            "#set-post-thumbnail",
            "a.thickbox[title*='ảnh đại diện']",
            "a.thickbox[title*='featured image']",
            "#postimagediv a.thickbox",
            ".inside a.thickbox"
        ]
        
        clicked = False
        for selector in set_image_selectors:
            try:
                link = page.locator(selector).first
                if link.is_visible(timeout=2000):
                    link.click()
                    log_func(f"Clicked: {selector}", "info")
                    clicked = True
                    time.sleep(2)
                    break
            except:
                continue
        
        if not clicked:
            log_func("Could not find set featured image link", "warning")
            return False
        
        # Now select image
        result = select_random_image(page, keyword, log_func)
        return result
        
    except Exception as e:
        log_func(f"Error setting featured image: {e}", "warning")
        close_all_modals(page, log_func)
        return False

def select_random_image(page, alt_text: str, log_func) -> bool:
    """Select a random image from media library for featured image."""
    try:
        # Wait for media modal to appear
        try:
            page.wait_for_selector(".media-modal", timeout=5000)
        except:
            log_func("Media modal not found", "warning")
            return False
        
        # Wait for images to load
        log_func("Waiting for media library to load...", "info")
        time.sleep(3)
        
        # Click on "Media Library" tab if available
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
            log_func("No images found in media library", "warning")
            close_all_modals(page, log_func)
            return False
        
        log_func(f"Found {len(images)} images", "info")
        
        # Select first visible image
        for i, img in enumerate(images[:5]):
            try:
                if img.is_visible(timeout=500):
                    img.click()
                    log_func(f"Clicked image {i+1}", "info")
                    time.sleep(1)
                    break
            except:
                continue
        
        # Set alt text with keyword
        time.sleep(0.5)
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
                    alt_input.fill("")
                    time.sleep(0.1)
                    alt_input.fill(alt_text)
                    log_func(f"Featured image alt: {alt_text}", "info")
                    time.sleep(0.2)
                    break
            except:
                continue
        
        # Click "Set featured image" button
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
                    log_func(f"Clicked: {selector}", "success")
                    clicked = True
                    time.sleep(1)
                    break
            except:
                continue
        
        if not clicked:
            log_func("Could not find set featured image button", "warning")
            close_all_modals(page, log_func)
            return False
        
        # Close modal after setting
        time.sleep(1)
        close_all_modals(page, log_func)
        
        return True
        
    except Exception as e:
        log_func(f"Error in image selection: {e}", "warning")
        close_all_modals(page, log_func)
        return False

# ============================================================================
# INSERT IMAGES INTO CONTENT
# ============================================================================

def insert_images_after_h2(page, keyword: str, log_func, wait_if_paused_func, is_running_func, max_images: int = 3) -> bool:
    """Insert images after H2 headings using Visual Editor."""
    try:
        log_func("Inserting images into post...", "info")
        close_all_modals(page, log_func)
        
        # Switch to Visual mode
        try:
            visual_tab = page.locator("#content-tmce").first
            if visual_tab.is_visible(timeout=1000):
                visual_tab.click()
                time.sleep(0.5)
        except:
            pass
        
        # Get H2 headings
        h2_elements = page.frame_locator("#content_ifr").locator("h2").all()
        if not h2_elements:
            log_func("No H2 headings found", "warning")
            return False
        
        log_func(f"Found {len(h2_elements)} H2 headings", "info")
        images_inserted = 0
        
        # Insert after 1st, 3rd, 5th H2
        for h2_index in [0, 2, 4]:
            if images_inserted >= max_images or h2_index >= len(h2_elements):
                break
            
            # Check stop/pause
            if not is_running_func():
                log_func("Stopped while inserting images", "warning")
                return False
            if not wait_if_paused_func():
                return False
            
            try:
                h2 = h2_elements[h2_index]
                h2.click()
                time.sleep(0.3)
                page.keyboard.press("End")
                page.keyboard.press("Enter")
                
                # Click Add Media button
                try:
                    add_media = page.locator("#insert-media-button").first
                    if add_media.is_visible(timeout=1000):
                        add_media.click()
                        time.sleep(2)
                        
                        # Select and insert image
                        if select_random_image_for_content(page, keyword, log_func):
                            images_inserted += 1
                            log_func(f"Inserted image after H2 #{h2_index + 1}", "success")
                            time.sleep(1)
                except Exception as e:
                    log_func(f"Error inserting image: {e}", "warning")
                    close_all_modals(page, log_func)
                    continue
                    
            except Exception as e:
                log_func(f"Error with H2 #{h2_index + 1}: {e}", "warning")
                continue
        
        close_all_modals(page, log_func)
        log_func(f"Inserted {images_inserted} images into content", "success")
        return images_inserted > 0
        
    except Exception as e:
        log_func(f"Error inserting images: {e}", "warning")
        close_all_modals(page, log_func)
        return False

def select_random_image_for_content(page, alt_text: str, log_func) -> bool:
    """Select an image from media library and insert it into content."""
    try:
        # Wait for media modal
        page.wait_for_selector(".media-modal", timeout=10000)
        time.sleep(5)
        
        # Find images
        images = page.locator(".attachments .attachment, li.attachment").all()
        
        if not images:
            log_func("No images found in media library", "warning")
            page.locator(".media-modal-close").first.click()
            return False
        
        # Select a random image
        random_image = random.choice(images)
        random_image.click()
        time.sleep(1)
        
        # Set alt text with keyword
        time.sleep(0.5)
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
                    alt_input.fill("")
                    time.sleep(0.1)
                    alt_input.fill(alt_text)
                    log_func(f"Alt text set: {alt_text}", "info")
                    alt_set = True
                    time.sleep(0.3)
                    break
            except:
                continue
        
        if not alt_set:
            log_func("Could not set alt text", "warning")
        
        # Click "Insert into post" button
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
        log_func(f"Error selecting image for content: {e}", "warning")
        try:
            page.locator(".media-modal-close").first.click()
        except:
            pass
        return False
