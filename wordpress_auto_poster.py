#!/usr/bin/env python3
"""
WordPress Auto Poster with Gemini Content Generation
=====================================================
Automates posting articles to WordPress with AI-generated content.

Requirements:
    pip install playwright google-generativeai
    playwright install chromium
"""

import random
import time
from datetime import datetime, timedelta
from typing import Optional
import google.generativeai as genai
from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError


# =============================================================================
# CONFIGURATION - Update these values before running
# =============================================================================

# Gemini API Configuration
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"

# WordPress Configuration
WP_USERNAME = "your_username"
WP_PASSWORD = "your_password"
WP_LOGIN_URL = "https://your-site.com/wp-login.php"
WP_ADMIN_URL = "https://your-site.com/wp-admin"

# Content Generation Prompt Template
PROMPT_TEMPLATE = """
Viết bài blog chuẩn SEO Google với tiêu đề "{title}".

THANG MÁY KENZO VIỆT NAM chuyên lắp đặt, sửa chữa, bảo trì thang máy.

Từ khóa SEO chính: "{keyword}"

YÊU CẦU BẮT BUỘC:
1. Bài viết trên 1500 từ
2. Từ khóa SEO "{keyword}" phải được IN ĐẬM bằng thẻ <strong>
3. Mật độ từ khóa SEO lặp lại KHÔNG VƯỢT QUÁ 3%
4. Định dạng bài viết với các thẻ HTML: <h2>, <h3>, <p>, <ul>, <li>, <strong>
5. Bài viết phải có:
   - Mở đầu hấp dẫn, giới thiệu vấn đề
   - Ít nhất 5 heading H2 với nội dung chi tiết
   - Mỗi H2 có các đoạn văn mô tả rõ ràng
   - Phần kết luận tóm tắt và kêu gọi hành động
6. KHÔNG thêm thẻ <h1> vì tiêu đề đã có sẵn
7. Viết bằng tiếng Việt, văn phong chuyên nghiệp

THÔNG TIN LIÊN HỆ (thêm vào cuối bài viết):
Thông tin cần tư vấn liên hệ:
<strong>CÔNG TY TNHH THANG MÁY KENZO VIỆT NAM</strong>
<ul>
<li>Trụ sở: 07 Đường DD5, Phường Tân Hưng Thuận, Quận 12, TP.HCM</li>
<li>Xưởng sản xuất: B15/6A Liên Ấp 1-2-3, H. Bình Chánh, TP.HCM</li>
<li>Chi nhánh Bình Dương: 113, NE3, Chánh Phú Hoà, Bến Cát, Bình Dương - ĐT: 0932 619 668</li>
<li>Chi nhánh Quy Nhơn: Tổ 15, Khu 2, P. Nhơn Bình, Tp. Quy Nhơn - ĐT: 0937 596 248</li>
<li>Email: thanhtienelevator@gmail.com</li>
<li>Website: <a href="https://suachuathangmay247.com">https://suachuathangmay247.com</a> | <a href="https://thangmaykenzo.com">https://thangmaykenzo.com</a></li>
</ul>

Chỉ trả về nội dung HTML, không có phần giải thích thêm.
"""

# Article Topics and Keywords
TOPICS = [
    "Hướng dẫn tối ưu SEO cho website năm 2024",
    "10 xu hướng thiết kế website hiện đại",
    "Cách xây dựng chiến lược content marketing hiệu quả",
    "Bí quyết tăng tốc độ tải trang website",
    "Hướng dẫn bảo mật website WordPress toàn diện",
    "Cách tối ưu hình ảnh cho website",
    "Chiến lược email marketing cho doanh nghiệp nhỏ",
    "Hướng dẫn sử dụng Google Analytics 4",
    "Cách xây dựng landing page chuyển đổi cao",
    "Tối ưu trải nghiệm người dùng UX/UI cho website",
]

KEYWORDS = [
    "tối ưu SEO website",
    "thiết kế website hiện đại",
    "content marketing",
    "tăng tốc độ website",
    "bảo mật WordPress",
    "tối ưu hình ảnh web",
    "email marketing",
    "Google Analytics 4",
    "landing page",
    "UX UI website",
]

# Scheduling Configuration
POSTS_PER_DAY = 2


# =============================================================================
# GEMINI CONTENT GENERATION
# =============================================================================

def configure_gemini():
    """Configure Gemini API with the provided API key."""
    genai.configure(api_key=GEMINI_API_KEY)


def generate_content(title: str, keyword: str, max_retries: int = 3) -> Optional[str]:
    """
    Generate blog content using Google Gemini API.
    
    Args:
        title: The article title
        keyword: The SEO keyword to incorporate
        max_retries: Maximum number of retry attempts
        
    Returns:
        HTML formatted blog content or None if generation fails
    """
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            prompt = PROMPT_TEMPLATE.format(title=title, keyword=keyword)
            
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                )
            )
            
            content = response.text
            
            # Clean up the content - remove markdown code blocks if present
            if content.startswith("```html"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
                
            print(f"✅ Generated content for: {title}")
            return content.strip()
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                # Rate limit error - wait and retry
                wait_time = 60 * (attempt + 1)  # 60s, 120s, 180s
                print(f"⏳ Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait_time)
            else:
                print(f"❌ Error generating content for '{title}': {e}")
                return None
    
    print(f"❌ Failed to generate content for '{title}' after {max_retries} retries")
    return None


# =============================================================================
# WORDPRESS AUTOMATION HELPERS
# =============================================================================

def wait_for_network_idle(page: Page, timeout: int = 10000):
    """Wait for network to be idle."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeoutError:
        pass  # Continue if timeout


def safe_click(page: Page, selector: str, timeout: int = 5000) -> bool:
    """Safely click an element with error handling."""
    try:
        page.wait_for_selector(selector, timeout=timeout)
        page.click(selector)
        return True
    except PlaywrightTimeoutError:
        print(f"⚠️ Element not found: {selector}")
        return False


def safe_fill(page: Page, selector: str, text: str, timeout: int = 5000) -> bool:
    """Safely fill an input with error handling."""
    try:
        page.wait_for_selector(selector, timeout=timeout)
        page.fill(selector, text)
        return True
    except PlaywrightTimeoutError:
        print(f"⚠️ Input not found: {selector}")
        return False


# =============================================================================
# WORDPRESS AUTOMATION FUNCTIONS
# =============================================================================

def login_to_wordpress(page: Page) -> bool:
    """
    Login to WordPress admin dashboard.
    
    Returns:
        True if login successful, False otherwise
    """
    try:
        print("🔐 Logging into WordPress...")
        page.goto(WP_LOGIN_URL, wait_until="domcontentloaded")
        
        # Fill login credentials
        page.fill("#user_login", WP_USERNAME)
        page.fill("#user_pass", WP_PASSWORD)
        
        # Click login button
        page.click("#wp-submit")
        
        # Wait for dashboard to load
        page.wait_for_url(f"{WP_ADMIN_URL}/**", timeout=15000)
        wait_for_network_idle(page)
        
        print("✅ Successfully logged into WordPress!")
        return True
        
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return False


def navigate_to_new_post(page: Page) -> bool:
    """Navigate to the Add New Post page."""
    try:
        page.goto(f"{WP_ADMIN_URL}/post-new.php", wait_until="domcontentloaded")
        wait_for_network_idle(page)
        time.sleep(2)  # Wait for Gutenberg to fully initialize
        
        # Close any welcome modals in Gutenberg
        try:
            close_button = page.locator("button[aria-label='Close']").first
            if close_button.is_visible(timeout=2000):
                close_button.click()
        except:
            pass
            
        print("📝 Navigated to new post editor")
        return True
        
    except Exception as e:
        print(f"❌ Failed to navigate to new post: {e}")
        return False


def set_post_title(page: Page, title: str) -> bool:
    """Set the post title in Gutenberg editor."""
    try:
        # Gutenberg title selector
        title_selector = "h1.wp-block-post-title, .editor-post-title__input, [aria-label='Add title']"
        
        page.wait_for_selector(title_selector, timeout=10000)
        title_element = page.locator(title_selector).first
        title_element.click()
        title_element.fill(title)
        
        print(f"📝 Set title: {title}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to set title: {e}")
        return False


def set_post_content(page: Page, content: str, keyword: str) -> bool:
    """
    Set the post content in Gutenberg editor with inline images after H2 headers.
    
    Args:
        page: Playwright page object
        content: HTML content to insert
        keyword: Keyword for image alt text
    """
    try:
        # Click on the content area to focus
        content_area = page.locator(".block-editor-block-list__layout").first
        content_area.click()
        
        # Use keyboard shortcut to add a Custom HTML block
        page.keyboard.press("Enter")
        time.sleep(0.5)
        
        # Type /html to insert Custom HTML block
        page.keyboard.type("/html")
        time.sleep(0.5)
        page.keyboard.press("Enter")
        time.sleep(1)
        
        # Find the HTML block textarea and paste content
        html_textarea = page.locator("textarea.block-editor-plain-text").first
        if html_textarea.is_visible(timeout=3000):
            html_textarea.fill(content)
            print("📄 Content added to post")
        else:
            # Alternative: Try to use the code editor
            page.keyboard.press("Control+Shift+Alt+M")  # Toggle to code editor
            time.sleep(1)
            code_editor = page.locator(".editor-post-text-editor").first
            if code_editor.is_visible():
                code_editor.fill(content)
                page.keyboard.press("Control+Shift+Alt+M")  # Toggle back
            
        # Insert inline images after H2 headers
        insert_inline_images(page, content, keyword)
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to set content: {e}")
        return False


def insert_inline_images(page: Page, content: str, keyword: str):
    """Insert images after each H2 header in the content."""
    try:
        # Count H2 headers in content
        h2_count = content.lower().count("<h2")
        
        if h2_count == 0:
            print("ℹ️ No H2 headers found, skipping inline images")
            return
            
        print(f"🖼️ Inserting {h2_count} inline images...")
        
        # For Gutenberg, we'll add Image blocks
        # This is a simplified approach - in production you might want more sophisticated insertion
        for i in range(min(h2_count, 3)):  # Limit to 3 inline images
            try:
                # Click at the end of content area
                page.keyboard.press("End")
                page.keyboard.press("Control+End")
                time.sleep(0.3)
                
                # Add new paragraph and image block
                page.keyboard.press("Enter")
                page.keyboard.type("/image")
                time.sleep(0.5)
                page.keyboard.press("Enter")
                time.sleep(1)
                
                # Click Media Library button
                media_library_btn = page.locator("button:has-text('Media Library'), button:has-text('Thư viện')").first
                if media_library_btn.is_visible(timeout=3000):
                    media_library_btn.click()
                    time.sleep(2)
                    
                    # Select random image from media library
                    select_random_image(page, keyword)
                    
            except Exception as e:
                print(f"⚠️ Failed to insert inline image {i+1}: {e}")
                continue
                
    except Exception as e:
        print(f"⚠️ Error inserting inline images: {e}")


def select_random_image(page: Page, alt_text: str) -> bool:
    """
    Select a random image from the Media Library modal.
    
    Args:
        page: Playwright page object
        alt_text: Alt text to set for the image
    """
    try:
        # Wait for media modal to load
        page.wait_for_selector(".media-modal", timeout=5000)
        time.sleep(1)
        
        # Get all available images in the grid
        images = page.locator(".attachments .attachment").all()
        
        if not images:
            print("⚠️ No images found in media library")
            return False
            
        # Select a random image
        random_image = random.choice(images)
        random_image.click()
        time.sleep(0.5)
        
        # Set alt text in the sidebar
        alt_input = page.locator("input[data-setting='alt'], #attachment-details-alt-text, .setting[data-setting='alt'] input").first
        if alt_input.is_visible(timeout=2000):
            alt_input.fill(alt_text)
            
        # Click Select/Insert button
        select_btn = page.locator("button.media-button-select, .media-button-insert, button:has-text('Select'), button:has-text('Chọn')").first
        if select_btn.is_visible(timeout=2000):
            select_btn.click()
            time.sleep(1)
            
        print(f"🖼️ Selected random image with alt: {alt_text}")
        return True
        
    except Exception as e:
        print(f"⚠️ Error selecting image: {e}")
        # Try to close modal if it's open
        try:
            page.locator(".media-modal-close").click()
        except:
            pass
        return False


def select_first_category(page: Page) -> bool:
    """Select the first available category in the category meta box."""
    try:
        # Open Document settings panel if not visible
        settings_btn = page.locator("button[aria-label='Settings'], button[aria-label='Cài đặt']").first
        if settings_btn.is_visible(timeout=2000):
            settings_btn.click()
            time.sleep(0.5)
        
        # Click on Post tab in sidebar
        post_tab = page.locator("button:has-text('Post'), button:has-text('Bài viết')").first
        if post_tab.is_visible(timeout=2000):
            post_tab.click()
            time.sleep(0.5)
        
        # Expand Categories panel if collapsed
        categories_panel = page.locator(".editor-post-taxonomies__hierarchical-terms-list, .components-panel__body:has-text('Categories'), .components-panel__body:has-text('Chuyên mục')")
        
        # Try to find and click Categories panel header to expand
        categories_header = page.locator("button.components-panel__body-toggle:has-text('Categories'), button.components-panel__body-toggle:has-text('Chuyên mục')").first
        if categories_header.is_visible(timeout=2000):
            # Check if panel is collapsed
            if categories_header.get_attribute("aria-expanded") == "false":
                categories_header.click()
                time.sleep(0.5)
        
        # Find and check the first category checkbox
        category_checkboxes = page.locator(".editor-post-taxonomies__hierarchical-terms-list input[type='checkbox']").all()
        
        if category_checkboxes:
            first_checkbox = category_checkboxes[0]
            if not first_checkbox.is_checked():
                first_checkbox.check()
            print("✅ Selected first category")
            return True
        else:
            print("⚠️ No categories found")
            return False
            
    except Exception as e:
        print(f"⚠️ Error selecting category: {e}")
        return False


def set_rank_math_keyword(page: Page, keyword: str) -> bool:
    """Set the focus keyword in Rank Math SEO metabox."""
    try:
        # Look for Rank Math panel in sidebar or metabox
        # Rank Math might be in different locations depending on configuration
        
        # Try sidebar first
        rank_math_btn = page.locator("button[aria-label*='Rank Math'], .rank-math-toolbar-score").first
        if rank_math_btn.is_visible(timeout=3000):
            rank_math_btn.click()
            time.sleep(1)
        
        # Find focus keyword input
        focus_keyword_selectors = [
            "#rank-math-focus-keyword",
            "input[placeholder*='Focus Keyword']",
            "input[placeholder*='Từ khóa']",
            ".rank-math-focus-keyword input",
            "[data-cy='focus-keyword'] input"
        ]
        
        for selector in focus_keyword_selectors:
            focus_input = page.locator(selector).first
            if focus_input.is_visible(timeout=1000):
                focus_input.fill(keyword)
                print(f"🔑 Set Rank Math focus keyword: {keyword}")
                return True
                
        print("⚠️ Rank Math focus keyword input not found")
        return False
        
    except Exception as e:
        print(f"⚠️ Error setting Rank Math keyword: {e}")
        return False


def set_featured_image(page: Page, keyword: str) -> bool:
    """Set featured image for the post."""
    try:
        # Open Settings panel if needed
        settings_btn = page.locator("button[aria-label='Settings'], button[aria-label='Cài đặt']").first
        if settings_btn.is_visible(timeout=2000):
            # Check if settings panel is open
            settings_panel = page.locator(".edit-post-sidebar")
            if not settings_panel.is_visible():
                settings_btn.click()
                time.sleep(0.5)
        
        # Click on Post tab
        post_tab = page.locator("button:has-text('Post'), button:has-text('Bài viết')").first
        if post_tab.is_visible(timeout=2000):
            post_tab.click()
            time.sleep(0.5)
        
        # Find and expand Featured Image panel
        featured_image_header = page.locator("button.components-panel__body-toggle:has-text('Featured image'), button.components-panel__body-toggle:has-text('Ảnh đại diện')").first
        if featured_image_header.is_visible(timeout=3000):
            if featured_image_header.get_attribute("aria-expanded") == "false":
                featured_image_header.click()
                time.sleep(0.5)
        
        # Click Set Featured Image button
        set_featured_btn = page.locator("button:has-text('Set featured image'), button:has-text('Đặt ảnh đại diện')").first
        if set_featured_btn.is_visible(timeout=2000):
            set_featured_btn.click()
            time.sleep(2)
            
            # Select random image from media library
            if select_random_image(page, keyword):
                print("✅ Featured image set")
                return True
                
        print("⚠️ Could not set featured image")
        return False
        
    except Exception as e:
        print(f"⚠️ Error setting featured image: {e}")
        return False


def set_publish_date(page: Page, publish_date: datetime) -> bool:
    """Set the publish date for the post."""
    try:
        # Open Publish panel in sidebar
        post_tab = page.locator("button:has-text('Post'), button:has-text('Bài viết')").first
        if post_tab.is_visible(timeout=2000):
            post_tab.click()
            time.sleep(0.5)
        
        # Find and click on the publish date link
        publish_link = page.locator("button.edit-post-post-schedule__toggle, .editor-post-schedule__toggle, button:has-text('Immediately'), button:has-text('Ngay lập tức')").first
        if publish_link.is_visible(timeout=3000):
            publish_link.click()
            time.sleep(0.5)
        
        # Fill in the date picker
        # Month
        month_input = page.locator("select.components-datetime__time-field-month, .components-datetime__date select").first
        if month_input.is_visible(timeout=2000):
            month_input.select_option(str(publish_date.month))
        
        # Day
        day_input = page.locator("input.components-datetime__time-field-day, input[aria-label*='Day'], input[aria-label*='Ngày']").first
        if day_input.is_visible(timeout=2000):
            day_input.fill(str(publish_date.day))
        
        # Year
        year_input = page.locator("input.components-datetime__time-field-year, input[aria-label*='Year'], input[aria-label*='Năm']").first
        if year_input.is_visible(timeout=2000):
            year_input.fill(str(publish_date.year))
        
        # Time (set to 9:00 AM for morning posts, 3:00 PM for afternoon)
        hour = 9 if publish_date.hour < 12 else 15
        hour_input = page.locator("input[aria-label*='Hours'], input[aria-label*='Giờ']").first
        if hour_input.is_visible(timeout=2000):
            hour_input.fill(str(hour))
        
        minute_input = page.locator("input[aria-label*='Minutes'], input[aria-label*='Phút']").first
        if minute_input.is_visible(timeout=2000):
            minute_input.fill("00")
        
        print(f"📅 Set publish date: {publish_date.strftime('%Y-%m-%d %H:%M')}")
        return True
        
    except Exception as e:
        print(f"⚠️ Error setting publish date: {e}")
        return False


def publish_or_schedule_post(page: Page, is_schedule: bool) -> bool:
    """Publish or schedule the post."""
    try:
        # Click the main Publish button to open publish panel
        publish_btn = page.locator("button.editor-post-publish-button, button.editor-post-publish-panel__toggle").first
        
        if publish_btn.is_visible(timeout=3000):
            publish_btn.click()
            time.sleep(1)
        
        # In the publish panel, click the final publish/schedule button
        if is_schedule:
            final_btn = page.locator("button:has-text('Schedule'), button:has-text('Lên lịch')").first
        else:
            final_btn = page.locator("button.editor-post-publish-button:has-text('Publish'), button:has-text('Xuất bản')").first
        
        if final_btn.is_visible(timeout=3000):
            final_btn.click()
            time.sleep(2)
            
            # Wait for success message or confirmation
            page.wait_for_selector(".components-snackbar, .editor-post-publish-panel__postpublish", timeout=10000)
            
            action = "Scheduled" if is_schedule else "Published"
            print(f"✅ {action} successfully!")
            return True
        else:
            print("⚠️ Publish/Schedule button not found")
            return False
            
    except Exception as e:
        print(f"❌ Error publishing/scheduling: {e}")
        return False


# =============================================================================
# MAIN WORKFLOW
# =============================================================================

def create_single_post(page: Page, index: int, title: str, keyword: str, content: str, start_date: datetime) -> bool:
    """
    Create a single WordPress post.
    
    Args:
        page: Playwright page object
        index: Post index (0-9)
        title: Post title
        keyword: SEO keyword
        content: HTML content
        start_date: Starting date for scheduling
        
    Returns:
        True if post created successfully, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"📝 Creating post {index + 1}/10: {title}")
    print(f"{'='*60}")
    
    try:
        # Calculate publish date (2 posts per day)
        days_offset = index // POSTS_PER_DAY
        publish_date = start_date + timedelta(days=days_offset)
        
        # Set time - 9 AM for first post of day, 3 PM for second
        hour = 9 if index % POSTS_PER_DAY == 0 else 15
        publish_date = publish_date.replace(hour=hour, minute=0, second=0)
        
        now = datetime.now()
        is_schedule = publish_date > now
        
        print(f"📅 Publish date: {publish_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"📌 Mode: {'Schedule' if is_schedule else 'Publish immediately'}")
        
        # Navigate to new post
        if not navigate_to_new_post(page):
            return False
        
        # Set title
        if not set_post_title(page, title):
            return False
        
        # Set content
        if not set_post_content(page, content, keyword):
            print("⚠️ Content setting had issues, continuing...")
        
        # Set category (first checkbox)
        select_first_category(page)
        
        # Set Rank Math focus keyword
        set_rank_math_keyword(page, keyword)
        
        # Set featured image
        set_featured_image(page, keyword)
        
        # Set publish date if scheduling
        if is_schedule:
            set_publish_date(page, publish_date)
        
        # Publish or schedule
        if not publish_or_schedule_post(page, is_schedule):
            return False
        
        print(f"✅ Post {index + 1} completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error creating post {index + 1}: {e}")
        return False


def main():
    """Main function to run the WordPress auto-poster."""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║     WordPress Auto Poster with Gemini AI                ║
    ║     ─────────────────────────────────────────────────   ║
    ║     Automated content generation and publishing         ║
    ╚══════════════════════════════════════════════════════════╝
    """)
    
    # Validate configuration
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        print("❌ Error: Please set your GEMINI_API_KEY in the configuration section")
        return
    
    if WP_USERNAME == "your_wordpress_username":
        print("❌ Error: Please set your WordPress credentials in the configuration section")
        return
    
    # Configure Gemini
    configure_gemini()
    
    # Pre-generate all content
    print("\n📝 Phase 1: Generating content with Gemini AI...")
    print("-" * 50)
    
    generated_contents = []
    for i, (title, keyword) in enumerate(zip(TOPICS, KEYWORDS)):
        print(f"\n[{i+1}/10] Generating content for: {title}")
        content = generate_content(title, keyword)
        generated_contents.append(content)
        time.sleep(65)  # Rate limiting - wait 65 seconds between requests for free tier
    
    # Check how many were generated successfully
    successful_generations = sum(1 for c in generated_contents if c is not None)
    print(f"\n✅ Successfully generated {successful_generations}/10 articles")
    
    if successful_generations == 0:
        print("❌ No content was generated. Please check your Gemini API key and try again.")
        return
    
    # Start browser automation
    print("\n🌐 Phase 2: WordPress Automation...")
    print("-" * 50)
    
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    with sync_playwright() as p:
        # Launch browser (set headless=False to see the automation)
        browser: Browser = p.chromium.launch(
            headless=False,  # Set to True for headless mode
            slow_mo=100  # Slow down actions for visibility
        )
        
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="vi-VN"
        )
        
        page: Page = context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # Login to WordPress
            if not login_to_wordpress(page):
                print("❌ Failed to login. Exiting...")
                return
            
            # Process each post
            successful_posts = 0
            failed_posts = 0
            
            for i, (title, keyword, content) in enumerate(zip(TOPICS, KEYWORDS, generated_contents)):
                if content is None:
                    print(f"\n⏭️ Skipping post {i+1} - no content was generated")
                    failed_posts += 1
                    continue
                
                try:
                    success = create_single_post(page, i, title, keyword, content, start_date)
                    if success:
                        successful_posts += 1
                    else:
                        failed_posts += 1
                except Exception as e:
                    print(f"❌ Unexpected error on post {i+1}: {e}")
                    failed_posts += 1
                
                # Wait between posts
                if i < len(TOPICS) - 1:
                    print("\n⏳ Waiting 3 seconds before next post...")
                    time.sleep(3)
            
            # Summary
            print("\n" + "=" * 60)
            print("📊 FINAL SUMMARY")
            print("=" * 60)
            print(f"✅ Successful posts: {successful_posts}")
            print(f"❌ Failed posts: {failed_posts}")
            print(f"📈 Success rate: {successful_posts/len(TOPICS)*100:.1f}%")
            
        except Exception as e:
            print(f"❌ Critical error: {e}")
            
        finally:
            # Keep browser open for a moment to see final state
            time.sleep(5)
            browser.close()
    
    print("\n🎉 WordPress Auto Poster completed!")


if __name__ == "__main__":
    main()
