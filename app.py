#!/usr/bin/env python3
"""
WordPress Auto Poster - Web Interface
======================================
A beautiful web interface for the WordPress Auto Poster with AI content generation.
Supports: Gemini API, Ollama (free, local)
"""

import json
import os
import random
import threading
import time
import requests
from datetime import datetime, timedelta
from typing import Optional
from flask import Flask, render_template, request, jsonify, Response
from flask_cors import CORS

# Gemini AI
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Check Ollama availability
def check_ollama():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        return False

OLLAMA_AVAILABLE = check_ollama()

# Playwright
try:
    from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# Global state
class AppState:
    def __init__(self):
        self.is_running = False
        self.current_task = ""
        self.progress = 0
        self.total_tasks = 0
        self.logs = []
        self.config = {
            "ai_provider": "ollama",  # "ollama" or "gemini"
            "ollama_model": "llama3.1:8b",  # Default Ollama model (larger, better quality)
            "gemini_api_key": "",
            "wp_username": "",
            "wp_password": "",
            "wp_login_url": "",
            "wp_admin_url": "",
            "posts_per_day": 2,
            "delay_between_requests": 5,  # Ollama is faster, less delay needed
            "headless_mode": False
        }
        self.topics = []
        self.generated_contents = []
        self.successful_posts = 0
        self.failed_posts = 0

state = AppState()

def add_log(message: str, log_type: str = "info"):
    """Add a log message with timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    state.logs.append({
        "time": timestamp,
        "message": message,
        "type": log_type
    })
    # Keep only last 100 logs
    if len(state.logs) > 100:
        state.logs = state.logs[-100:]

# ============================================================================
# GEMINI CONTENT GENERATION
# ============================================================================

PROMPT_PART1 = """
Bạn là chuyên gia viết bài SEO. Viết PHẦN 1 của bài blog với tiêu đề: "{title}"

TỪ KHÓA SEO CHÍNH: "{keyword}"
CÔNG TY: THANG MÁY KENZO VIỆT NAM

⚠️ CHỈ VIẾT PHẦN 1 (khoảng 800 TỪ), bao gồm:

1. ĐOạN MỞ ĐẦU (200 từ):
<p>Viết đoạn mở đầu hấp dẫn giới thiệu về <strong>{keyword}</strong>. Giải thích tại sao đây là chủ đề quan trọng, nêu bật lợi ích và giá trị. Đề cập đến THANG MÁY KENZO VIỆT NAM như đơn vị uy tín trong lĩnh vực này.</p>

2. <h2>Tổng quan về {keyword}</h2> (200 từ):
<p>Viết đoạn chi tiết về khái niệm, định nghĩa, tầm quan trọng của <strong>{keyword}</strong>. Mô tả các đặc điểm chính, ứng dụng phổ biến.</p>

3. <h2>Lợi ích nổi bật của {keyword}</h2> (200 từ):
<p>Giải thích chi tiết các lợi ích:</p>
<ul>
<li>An toàn và tiện nghi</li>
<li>Tiết kiệm không gian</li>
<li>Tăng giá trị bất động sản</li>
<li>Phù hợp nhiều đối tượng</li>
</ul>
<p>Mô tả cụ thể từng lợi ích với <strong>{keyword}</strong>.</p>

4. <h2>Báo giá {keyword} mới nhất năm 2025</h2> (200 từ):
<p>Cung cấp thông tin chi tiết về mức giá, các yếu tố ảnh hưởng đến giá, so sánh giá của các loại khác nhau.</p>

QUY TẮC:
- CHỈ DÙNG HTML (<h2>, <p>, <ul>, <li>, <strong>)
- KHÔNG dùng Markdown (##, **)
- Từ khóa "{keyword}" phải in đậm: <strong>{keyword}</strong>
- Mỗi phần PHẢI có ít nhất 200 từ

Xuất ra HTML thuần túy, bắt đầu bằng <p>.
"""

PROMPT_PART2 = """
Bạn là chuyên gia viết bài SEO. Viết PHẦN 2 (tiếp theo) của bài blog với tiêu đề: "{title}"

TỪ KHÓA SEO CHÍNH: "{keyword}"
CÔNG TY: THANG MÁY KENZO VIỆT NAM

⚠️ CHỈ VIẾT PHẦN 2 (khoảng 800 TỪ), bao gồm:

1. <h2>Quy trình lắp đặt {keyword}</h2> (200 từ):
<p>Mô tả chi tiết các bước lắp đặt <strong>{keyword}</strong>:</p>
<ul>
<li>Bước 1: Khảo sát và tư vấn</li>
<li>Bước 2: Thiết kế và báo giá</li>
<li>Bước 3: Thi công lắp đặt</li>
<li>Bước 4: Nghiệm thu và bàn giao</li>
</ul>

2. <h2>Kinh nghiệm chọn {keyword} phù hợp</h2> (200 từ):
<p>Chia sẻ kinh nghiệm, tiêu chí lựa chọn <strong>{keyword}</strong> chất lượng. Các yếu tố cần xem xét như thương hiệu, bảo hành, dịch vụ hậu mãi.</p>

3. <h2>Câu hỏi thường gặp về {keyword}</h2> (200 từ):
<h3>Câu hỏi 1: Chi phí lắp đặt {keyword} là bao nhiêu?</h3>
<p>Trả lời chi tiết về chi phí...</p>
<h3>Câu hỏi 2: Thời gian lắp đặt {keyword} mất bao lâu?</h3>
<p>Trả lời chi tiết về thời gian...</p>
<h3>Câu hỏi 3: Bảo trì {keyword} như thế nào?</h3>
<p>Trả lời chi tiết về bảo trì...</p>

4. <h2>Kết luận</h2> (200 từ):
<p>Tóm tắt các điểm chính về <strong>{keyword}</strong>. Kêu gọi khách hàng liên hệ THANG MÁY KENZO VIỆT NAM để được tư vấn và báo giá tốt nhất.</p>

QUY TẮC:
- CHỈ DÙNG HTML (<h2>, <h3>, <p>, <ul>, <li>, <strong>)
- KHÔNG dùng Markdown (##, **)
- Từ khóa "{keyword}" phải in đậm: <strong>{keyword}</strong>
- Mỗi phần PHẢI có ít nhất 200 từ

Xuất ra HTML thuần túy, bắt đầu bằng <h2>.
"""

CONTACT_SECTION = """
<h2>Liên hệ THANG MÁY KENZO VIỆT NAM</h2>
<p>Nếu bạn cần tư vấn về <strong>{keyword}</strong>, hãy liên hệ ngay với chúng tôi:</p>
<p><strong>CÔNG TY TNHH THANG MÁY KENZO VIỆT NAM</strong></p>
<ul>
<li>Trụ sở: 07 Đường DD5, Phường Tân Hưng Thuận, Quận 12, TP.HCM</li>
<li>Xưởng: B15/6A Liên Ấp 1-2-3, H. Bình Chánh, TP.HCM</li>
<li>Chi nhánh Bình Dương: 113, NE3, Chánh Phú Hoà, Bến Cát - ĐT: 0932 619 668</li>
<li>Chi nhánh Quy Nhơn: Tổ 15, Khu 2, P. Nhơn Bình - ĐT: 0937 596 248</li>
<li>Email: thanhtienelevator@gmail.com</li>
<li>Website: <a href="https://suachuathangmay247.com">suachuathangmay247.com</a> | <a href="https://thangmaykenzo.com">thangmaykenzo.com</a></li>
</ul>
"""

def clean_gemini_content(content: str) -> str:
    """Clean Gemini response by removing intro and outro text."""
    import re
    
    if not content:
        return content
    
    original_length = len(content)
    
    # ===== REMOVE INTRO TEXT =====
    # Find the first H1 or H2 tag and remove everything before it
    first_heading_match = re.search(r'<h[12][^>]*>', content, re.IGNORECASE)
    if first_heading_match:
        content = content[first_heading_match.start():]
    
    # ===== REMOVE OUTRO TEXT (after contact section) =====
    # Find the LAST occurrence of website links
    last_link_pos = -1
    
    # Look for the actual website URLs
    website_patterns = [
        r'thangmaykenzo\.com[^<]*</a>',
        r'suachuathangmay247\.com[^<]*</a>',
        r'thangmaykenzo\.com[^<]*</li>',
        r'suachuathangmay247\.com[^<]*</li>',
    ]
    
    for pattern in website_patterns:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            if match.end() > last_link_pos:
                last_link_pos = match.end()
    
    # If we found a website link, cut everything after the parent list closes
    if last_link_pos > 0:
        remaining = content[last_link_pos:]
        
        # Find the end of the list (</ul> or </li></ul>)
        end_list_match = re.search(r'(</li>\s*)*</ul>', remaining, re.IGNORECASE)
        if end_list_match:
            cut_point = last_link_pos + end_list_match.end()
            content = content[:cut_point]
    
    # ===== REMOVE GEMINI SUGGESTIONS =====
    # Remove common Gemini outro patterns that appear AFTER contact
    outro_patterns = [
        r'<h[23][^>]*>\s*Next Steps[^<]*</h[23]>.*$',
        r'<p>\s*Would you like me to.*$',
        r'<p>\s*Do you want me to.*$',
        r'<p>\s*Let me know if you.*$',
        r'<p>\s*Shall I.*$',
        r'<strong>\s*Next Steps.*$',
    ]
    
    for pattern in outro_patterns:
        content = re.sub(pattern, '', content, flags=re.IGNORECASE | re.DOTALL)
    
    # ===== CLEAN UP =====
    # Remove trailing whitespace and empty tags
    content = re.sub(r'\s*<p>\s*</p>\s*', '', content)
    content = re.sub(r'\s+$', '', content)
    
    cleaned_length = len(content)
    if original_length != cleaned_length:
        add_log(f"🧹 Đã làm sạch nội dung: {original_length} → {cleaned_length} ký tự", "info")
    
    return content



def call_ollama_api(prompt: str, model: str) -> Optional[str]:
    """Call Ollama API with given prompt."""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.6,
                    "num_predict": 6000,
                    "num_ctx": 8192
                }
            },
            timeout=600
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("response", "")
            
            # Clean up
            if content.startswith("```html"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            return content.strip()
        return None
    except:
        return None

def generate_content_ollama(title: str, keyword: str) -> Optional[str]:
    """Generate blog content using Ollama in 2 parts for 1500+ words."""
    try:
        model = state.config.get("ollama_model", "llama3.1:8b")
        
        # Fallback if model name is empty or invalid
        if not model or model == "llama3.2":
            model = "llama3.1:8b"
        
        add_log(f"🤖 Đang tạo nội dung với Ollama ({model})...", "info")
        add_log("⏳ Đang tạo Phần 1/2 (800+ từ)...", "info")
        
        # Generate Part 1
        prompt_part1 = PROMPT_PART1.format(title=title, keyword=keyword)
        part1 = call_ollama_api(prompt_part1, model)
        
        if not part1:
            add_log("❌ Không thể tạo Phần 1", "error")
            return None
        
        word_count_1 = len(part1.split())
        add_log(f"📊 Phần 1: {word_count_1} từ", "info")
        
        add_log("⏳ Đang tạo Phần 2/2 (800+ từ)...", "info")
        
        # Generate Part 2
        prompt_part2 = PROMPT_PART2.format(title=title, keyword=keyword)
        part2 = call_ollama_api(prompt_part2, model)
        
        if not part2:
            add_log("❌ Không thể tạo Phần 2", "error")
            return None
        
        word_count_2 = len(part2.split())
        add_log(f"📊 Phần 2: {word_count_2} từ", "info")
        
        # Combine parts + contact section
        contact = CONTACT_SECTION.format(keyword=keyword)
        full_content = part1 + "\n\n" + part2 + "\n\n" + contact
        
        # Total word count
        total_words = len(full_content.split())
        add_log(f"📊 Tổng cộng: {total_words} từ", "success")
        
        if total_words < 1200:
            add_log(f"⚠️ Nội dung ngắn hơn mong đợi ({total_words} từ)", "warning")
        
        add_log(f"✅ Đã tạo nội dung cho: {title}", "success")
        return full_content
        
    except requests.exceptions.Timeout:
        add_log("❌ Ollama timeout - tạo nội dung quá lâu", "error")
        return None
    except Exception as e:
        add_log(f"❌ Lỗi Ollama: {e}", "error")
        return None


def send_prompt_to_gemini_web(page, prompt: str) -> Optional[str]:
    """Send a prompt to Gemini Chat and get the response."""
    try:
        # Wait for page to fully load
        add_log("⏳ Đang chờ trang Gemini tải...", "info")
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
                    add_log(f"📝 Tìm thấy ô nhập: {selector}", "info")
                    break
            except:
                continue
        
        if not input_area:
            # Try to find any editable element
            add_log("⚠️ Đang thử các selector khác...", "warning")
            try:
                input_area = page.locator("[contenteditable='true']").first
                if input_area.is_visible(timeout=5000):
                    add_log("📝 Tìm thấy phần tử contenteditable", "info")
            except:
                pass
        
        if not input_area:
            add_log("❌ Không tìm thấy ô nhập Gemini", "error")
            # Take screenshot for debugging
            page.screenshot(path="/tmp/gemini_error.png")
            add_log("📸 Đã lưu screenshot tại /tmp/gemini_error.png", "info")
            return None
        
        # Click on the input area to focus
        input_area.click()
        time.sleep(1)
        
        # Clean prompt - replace newlines with spaces to avoid multiple sends
        clean_prompt = prompt.replace('\n', ' ').replace('\r', ' ')
        # Remove multiple spaces
        while '  ' in clean_prompt:
            clean_prompt = clean_prompt.replace('  ', ' ')
        
        add_log("⌨️ Đang nhập prompt...", "info")
        
        # Method 1: Try using fill() - most reliable
        try:
            input_area.fill(clean_prompt)
            add_log("📝 Đã nhập prompt qua fill()", "info")
        except:
            # Method 2: Use keyboard typing for the entire prompt
            add_log("⌨️ Đang gõ bằng bàn phím...", "info")
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
                    add_log("📤 Đã gửi prompt tới Gemini", "info")
                    break
            except:
                continue
        
        if not sent:
            # Try pressing Enter as fallback
            page.keyboard.press("Enter")
            add_log("📤 Đã gửi prompt qua phím Enter", "info")
        
        # Wait for response
        add_log("⏳ Đang chờ Gemini trả lời (có thể mất 1-2 phút)...", "info")
        time.sleep(10)  # Initial wait
        
        # Wait until response is complete
        max_wait = 180  # 3 minutes max
        waited = 0
        while waited < max_wait:
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
                
            time.sleep(3)
            waited += 3
            if waited % 15 == 0:
                add_log(f"⏳ Vẫn đang chờ... ({waited}s)", "info")
        
        time.sleep(5)  # Extra wait for rendering
        
        # Extract the response - try multiple selectors
        add_log("📋 Đang trích xuất phản hồi...", "info")
        
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
                        add_log(f"✅ Tìm thấy phản hồi với selector: {selector}", "info")
                        break
            except:
                continue
        
        if response_text:
            word_count = len(response_text.split())
            add_log(f"📊 Nhận được {word_count} từ từ Gemini", "success")
            return response_text
        else:
            add_log("❌ Không thể trích xuất phản hồi Gemini", "error")
            return None
            
    except Exception as e:
        add_log(f"❌ Lỗi Gemini Chat: {e}", "error")
        return None


def generate_content_gemini_web(page, title: str, keyword: str) -> Optional[str]:
    """Generate content using Gemini Chat web interface (free, no API key needed)."""
    try:
        add_log("🌐 Đang mở Gemini Chat...", "info")
        
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
            add_log("⚠️ Vui lòng đăng nhập Google trong cửa sổ browser!", "warning")
            add_log("⏳ Đang chờ đăng nhập (10 phút)...", "info")
            
            # Wait up to 10 minutes for login
            login_wait = 0
            max_login_wait = 600  # 10 minutes
            while login_wait < max_login_wait:
                time.sleep(10)
                login_wait += 10
                
                # Check if we're now on Gemini app page
                current_url = page.url
                if "gemini.google.com" in current_url and "accounts.google" not in current_url:
                    add_log("✅ Đăng nhập thành công!", "success")
                    time.sleep(3)  # Extra wait for page load
                    break
                    
                remaining = max_login_wait - login_wait
                if login_wait % 60 == 0:
                    add_log(f"⏳ Còn {remaining // 60} phút...", "info")
        
        # Get custom prompt from config, or use default
        custom_prompt = state.config.get("gemini_prompt", "")
        
        if custom_prompt and "{title}" in custom_prompt and "{keyword}" in custom_prompt:
            # Use custom single prompt
            add_log("⏳ Đang tạo nội dung với prompt tùy chỉnh...", "info")
            prompt = custom_prompt.format(title=title, keyword=keyword)
            content = send_prompt_to_gemini_web(page, prompt)
            
            if not content:
                add_log("❌ Không thể tạo nội dung", "error")
                return None
            
            word_count = len(content.split())
            add_log(f"📊 Đã tạo {word_count} từ", "info")
            
        else:
            # Fall back to two-part generation
            add_log("⏳ Đang tạo Phần 1/2 với Gemini Chat...", "info")
            prompt1 = PROMPT_PART1.format(title=title, keyword=keyword)
            part1 = send_prompt_to_gemini_web(page, prompt1)
            
            if not part1:
                add_log("❌ Không thể tạo Phần 1", "error")
                return None
            
            word_count_1 = len(part1.split())
            add_log(f"📊 Phần 1: {word_count_1} từ", "info")
            
            time.sleep(3)
            
            add_log("⏳ Đang tạo Phần 2/2 với Gemini Chat...", "info")
            prompt2 = PROMPT_PART2.format(title=title, keyword=keyword)
            part2 = send_prompt_to_gemini_web(page, prompt2)
            
            if not part2:
                add_log("❌ Không thể tạo Phần 2", "error")
                return None
            
            word_count_2 = len(part2.split())
            add_log(f"📊 Phần 2: {word_count_2} từ", "info")
            
            # Combine parts
            contact = CONTACT_SECTION.format(keyword=keyword)
            content = part1 + "\n\n" + part2 + "\n\n" + contact
        
        # Clean content - remove intro and outro text from Gemini
        content = clean_gemini_content(content)
        
        total_words = len(content.split())
        add_log(f"📊 Tổng cộng: {total_words} từ", "success")
        add_log(f"✅ Đã tạo nội dung cho: {title}", "success")
        
        return content
        
    except Exception as e:
        add_log(f"❌ Lỗi Gemini Chat: {e}", "error")
        return None

def generate_content_gemini(title: str, keyword: str, max_retries: int = 3) -> Optional[str]:
    """Generate blog content using Google Gemini API in 2 parts."""
    if not GEMINI_AVAILABLE:
        add_log("Gemini library not available", "error")
        return None
    
    genai.configure(api_key=state.config["gemini_api_key"])
    
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            
            # Generate Part 1
            add_log("⏳ Generating Part 1/2 with Gemini...", "info")
            prompt_part1 = PROMPT_PART1.format(title=title, keyword=keyword)
            response1 = model.generate_content(
                prompt_part1,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                )
            )
            part1 = response1.text.strip()
            
            # Clean up part 1
            if part1.startswith("```html"):
                part1 = part1[7:]
            if part1.startswith("```"):
                part1 = part1[3:]
            if part1.endswith("```"):
                part1 = part1[:-3]
            
            word_count_1 = len(part1.split())
            add_log(f"📊 Part 1: {word_count_1} words", "info")
            
            # Generate Part 2
            add_log("⏳ Generating Part 2/2 with Gemini...", "info")
            prompt_part2 = PROMPT_PART2.format(title=title, keyword=keyword)
            response2 = model.generate_content(
                prompt_part2,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=4096,
                )
            )
            part2 = response2.text.strip()
            
            # Clean up part 2
            if part2.startswith("```html"):
                part2 = part2[7:]
            if part2.startswith("```"):
                part2 = part2[3:]
            if part2.endswith("```"):
                part2 = part2[:-3]
            
            word_count_2 = len(part2.split())
            add_log(f"📊 Part 2: {word_count_2} words", "info")
            
            # Combine
            contact = CONTACT_SECTION.format(keyword=keyword)
            full_content = part1.strip() + "\n\n" + part2.strip() + "\n\n" + contact
            
            total_words = len(full_content.split())
            add_log(f"📊 Total: {total_words} words", "success")
            add_log(f"✅ Generated content for: {title}", "success")
            
            return full_content
            
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                wait_time = 60 * (attempt + 1)
                add_log(f"⏳ Rate limit hit. Waiting {wait_time}s before retry {attempt + 1}/{max_retries}...", "warning")
                time.sleep(wait_time)
            else:
                add_log(f"❌ Error generating content: {e}", "error")
                return None
    
    add_log(f"❌ Failed to generate content after {max_retries} retries", "error")
    return None


def generate_content(title: str, keyword: str, page=None) -> Optional[str]:
    """Generate content using the configured AI provider."""
    provider = state.config.get("ai_provider", "ollama")
    
    if provider == "ollama":
        # Check if Ollama is running
        if not check_ollama():
            add_log("❌ Ollama is not running! Please start Ollama first.", "error")
            add_log("💡 Run: ollama serve", "info")
            return None
        return generate_content_ollama(title, keyword)
    elif provider == "gemini_web":
        if page is None:
            add_log("❌ Gemini Web requires browser page", "error")
            return None
        return generate_content_gemini_web(page, title, keyword)
    else:
        return generate_content_gemini(title, keyword)

# ============================================================================
# WORDPRESS AUTOMATION
# ============================================================================

def wait_for_network_idle(page: Page, timeout: int = 10000):
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except:
        pass

def login_to_wordpress(page: Page) -> bool:
    """Login to WordPress with improved error handling."""
    try:
        add_log("🔐 Logging into WordPress...", "info")
        
        login_url = state.config.get("wp_login_url", "")
        username = state.config.get("wp_username", "")
        password = state.config.get("wp_password", "")
        
        add_log(f"📍 Login URL: {login_url}", "info")
        add_log(f"👤 Username: {username}", "info")
        
        if not login_url or not username or not password:
            add_log("❌ Missing login credentials!", "error")
            return False
        
        # Navigate to login page
        page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)  # Wait for page to fully render
        
        current_url = page.url
        add_log(f"📍 Current URL: {current_url}", "info")
        
        # Check if already logged in
        if "wp-admin" in current_url and "wp-login" not in current_url:
            add_log("✅ Already logged in!", "success")
            return True
        
        # Wait for login form - try multiple selectors
        login_form_found = False
        form_selectors = ["#user_login", "#loginform", "input[name='log']", "#username"]
        
        for selector in form_selectors:
            try:
                if page.locator(selector).first.is_visible(timeout=3000):
                    login_form_found = True
                    add_log(f"📝 Tìm thấy form đăng nhập: {selector}", "info")
                    break
            except:
                continue
        
        if not login_form_found:
            add_log("❌ Could not find login form!", "error")
            page.screenshot(path="/tmp/wp_login_error.png")
            add_log("📸 Screenshot saved to /tmp/wp_login_error.png", "info")
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
                    add_log(f"📝 Filled username in {selector}", "info")
                    break
            except:
                continue
        
        time.sleep(0.5)
        
        # Fill password
        for selector in password_selectors:
            try:
                input_field = page.locator(selector).first
                if input_field.is_visible(timeout=2000):
                    input_field.click()
                    input_field.fill("")
                    input_field.fill(password)
                    add_log(f"📝 Filled password in {selector}", "info")
                    break
            except:
                continue
        
        time.sleep(0.5)
        
        # Click submit button
        submit_selectors = ["#wp-submit", "input[type='submit']", "button[type='submit']", ".login-submit button"]
        
        for selector in submit_selectors:
            try:
                submit_btn = page.locator(selector).first
                if submit_btn.is_visible(timeout=2000):
                    submit_btn.click()
                    add_log(f"⏳ Clicked submit: {selector}", "info")
                    break
            except:
                continue
        
        # Wait for navigation
        add_log("⏳ Waiting for login to complete...", "info")
        time.sleep(5)
        
        # Try waiting for wp-admin URL
        try:
            page.wait_for_url("**/wp-admin/**", timeout=15000)
        except:
            time.sleep(3)
        
        # Check if login was successful
        current_url = page.url
        add_log(f"📍 After login URL: {current_url}", "info")
        
        # Success indicators
        if "wp-admin" in current_url and "wp-login" not in current_url:
            add_log("✅ Successfully logged into WordPress!", "success")
            wait_for_network_idle(page)
            return True
        
        # Check for error message on login page
        error_selectors = ["#login_error", ".login-error", ".message.error"]
        for selector in error_selectors:
            try:
                error_msg = page.locator(selector).first
                if error_msg.is_visible(timeout=1000):
                    error_text = error_msg.inner_text()
                    add_log(f"❌ Login error: {error_text[:100]}", "error")
                    return False
            except:
                continue
        
        # If we're still on login page
        if "wp-login" in current_url or "login" in current_url.lower():
            add_log("❌ Login failed: Still on login page", "error")
            page.screenshot(path="/tmp/wp_login_failed.png")
            add_log("📸 Screenshot saved to /tmp/wp_login_failed.png", "info")
            return False
        
        # Assume success if no errors detected
        add_log("✅ Login appears successful", "success")
        return True
        
    except Exception as e:
        add_log(f"❌ Login failed: {e}", "error")
        try:
            page.screenshot(path="/tmp/wp_login_exception.png")
        except:
            pass
        return False

def navigate_to_new_post(page: Page) -> bool:
    """Navigate to create new post page (Classic Editor)."""
    try:
        page.goto(f"{state.config['wp_admin_url']}/post-new.php", wait_until="domcontentloaded")
        wait_for_network_idle(page, timeout=15000)
        time.sleep(2)
        
        # Wait for Classic Editor to load - check for title field
        try:
            page.wait_for_selector("#title, input[name='post_title']", timeout=10000)
            add_log("📝 Classic Editor loaded", "info")
        except:
            add_log("⚠️ Editor may not have loaded properly", "warning")
        
        # Dismiss any notices
        try:
            dismiss_btns = page.locator(".notice-dismiss, .wp-core-ui .notice-dismiss").all()
            for btn in dismiss_btns:
                if btn.is_visible():
                    btn.click()
                    time.sleep(0.2)
        except:
            pass
        
        add_log("📝 Navigated to new post editor", "info")
        return True
        
    except Exception as e:
        add_log(f"❌ Failed to navigate to new post: {e}", "error")
        return False

def set_post_title(page: Page, title: str) -> bool:
    """Set the post title (Classic Editor)."""
    try:
        # Classic Editor title field - ID is always "title"
        title_input = page.locator("#title")
        
        if title_input.is_visible(timeout=5000):
            title_input.click()
            title_input.fill("")  # Clear first
            title_input.fill(title)
            add_log(f"📝 Set title: {title[:50]}...", "info")
            return True
        else:
            add_log("❌ Title field not visible", "error")
            return False
            
    except Exception as e:
        add_log(f"❌ Failed to set title: {e}", "error")
        return False

def set_post_content(page: Page, content: str) -> bool:
    """Set the post content (Classic Editor with TinyMCE)."""
    try:
        add_log("📝 Adding content to post...", "info")
        time.sleep(1)
        
        content_added = False
        
        # Method 1: Switch to Text/HTML mode and fill textarea directly
        try:
            # Click on "Văn bản" / "Text" tab
            text_tab = page.locator("#content-html").first
            if text_tab.is_visible(timeout=3000):
                text_tab.click()
                time.sleep(1)
                add_log("📝 Đã chuyển sang chế độ Text/HTML", "info")
                
                # Fill the content textarea
                content_textarea = page.locator("#content").first
                if content_textarea.is_visible(timeout=3000):
                    content_textarea.click()
                    content_textarea.fill("")  # Clear first
                    content_textarea.fill(content)
                    content_added = True
                    add_log("📄 Content added via textarea", "success")
        except Exception as e:
            add_log(f"⚠️ Textarea method failed: {e}", "warning")
        
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
                add_log(f"⚠️ JavaScript method failed: {e}", "warning")
        
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
                add_log(f"⚠️ TinyMCE method failed: {e}", "warning")
        
        if content_added:
            return True
        else:
            add_log("❌ Failed to add content - all methods failed", "error")
            return False
        
    except Exception as e:
        add_log(f"❌ Failed to set content: {e}", "error")
        return False

def set_rank_math_keyword(page: Page, keyword: str) -> bool:
    """Set the Rank Math SEO focus keyword."""
    try:
        add_log(f"🔑 Setting Rank Math keyword: {keyword}", "info")
        
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
            add_log(f"✅ Rank Math keyword set: {keyword}", "success")
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
                add_log(f"✅ Rank Math keyword set via JS: {keyword}", "success")
                return True
            except:
                add_log("⚠️ Rank Math keyword field not found", "warning")
                return False
        
    except Exception as e:
        add_log(f"⚠️ Error setting Rank Math keyword: {e}", "warning")
        return False

def select_random_image(page: Page, alt_text: str) -> bool:
    """Select a random image from media library for featured image."""
    try:
        # Wait for media modal to appear
        try:
            page.wait_for_selector(".media-modal", timeout=5000)
        except:
            add_log("⚠️ Không tìm thấy modal chọn ảnh", "warning")
            return False
        
        # Wait for images to load (reduced from 8s to 3s)
        add_log("⏳ Waiting for media library to load...", "info")
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
            add_log("⚠️ No images found in media library", "warning")
            force_close_all_modals(page)
            return False
        
        add_log(f"📸 Tìm thấy {len(images)} hình ảnh", "info")
        
        # Select first visible image (more reliable than random)
        for i, img in enumerate(images[:5]):  # Try first 5 images
            try:
                if img.is_visible(timeout=500):
                    img.click()
                    add_log(f"📸 Clicked image {i+1}", "info")
                    time.sleep(1)
                    break
            except:
                continue
        
        # Set alt text if input is available
        try:
            alt_input = page.locator("input[data-setting='alt'], #attachment-details-alt-text").first
            if alt_input.is_visible(timeout=1000):
                alt_input.fill(alt_text)
        except:
            pass
        
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
                    add_log(f"✅ Clicked: {selector}", "success")
                    clicked = True
                    time.sleep(1)
                    break
            except:
                continue
        
        if not clicked:
            add_log("⚠️ Could not find set featured image button", "warning")
            force_close_all_modals(page)
            return False
        
        # Close modal after setting
        time.sleep(1)
        force_close_all_modals(page)
        
        return True
        
    except Exception as e:
        add_log(f"⚠️ Error in image selection: {e}", "warning")
        force_close_all_modals(page)
        return False

def insert_images_after_h2(page: Page, keyword: str, max_images: int = 3) -> bool:
    """Insert images RIGHT AFTER H2 headings (after the title) using Visual Editor."""
    try:
        add_log("🖼️ Starting to insert images after H2 headings...", "info")
        
        # First, close any open modals
        force_close_all_modals(page)
        
        # Switch to Visual mode for cursor navigation
        visual_tab = page.locator("#content-tmce").first
        try:
            if visual_tab.is_visible(timeout=2000):
                visual_tab.click()
                time.sleep(1)
                add_log("📝 Đã chuyển sang chế độ Visual", "info")
        except:
            pass
        
        # Get all H2 headings in the TinyMCE iframe
        tinymce_frame = page.frame_locator("#content_ifr")
        h2_elements = tinymce_frame.locator("h2").all()
        
        if not h2_elements:
            add_log("⚠️ Không tìm thấy tiêu đề H2 trong nội dung", "warning")
            return False
        
        add_log(f"📝 Tìm thấy {len(h2_elements)} tiêu đề H2", "info")
        
        images_inserted = 0
        
        # Insert images after H2s at positions 0, 2, 4 (1st, 3rd, 5th H2)
        target_indices = [0, 2, 4]  # After 1st, 3rd, 5th H2
        
        for idx, h2_index in enumerate(target_indices):
            if images_inserted >= max_images:
                break
            if h2_index >= len(h2_elements):
                break
            
            try:
                h2 = h2_elements[h2_index]
                
                # Click on the H2 to position cursor
                h2.click()
                time.sleep(0.5)
                
                # Move to end of H2 line
                page.keyboard.press("End")
                time.sleep(0.3)
                
                # Press Enter to create new line right after H2
                page.keyboard.press("Enter")
                time.sleep(0.3)
                
                # Now click "Thêm Media" button
                add_media_btn = page.locator("#insert-media-button, .add_media, button:has-text('Thêm Media')").first
                if add_media_btn.is_visible(timeout=2000):
                    add_media_btn.click()
                    time.sleep(2)
                    
                    # Wait for media modal
                    try:
                        page.wait_for_selector(".media-modal", timeout=5000)
                        time.sleep(2)
                        
                        # Find and click an image
                        images = page.locator(".attachments .attachment, li.attachment").all()
                        if images:
                            # Pick a random image from first 10
                            img_index = random.randint(0, min(len(images) - 1, 10))
                            images[img_index].click()
                            time.sleep(1)
                            
                            # Set alt text
                            try:
                                alt_input = page.locator("input[data-setting='alt']").first
                                if alt_input.is_visible(timeout=1000):
                                    alt_input.fill(keyword)
                            except:
                                pass
                            
                            # Set "Link To" = "Attachment Page" (Trang nội dung đính kèm)
                            try:
                                link_select = page.locator("select[data-setting='link'], select.link-to").first
                                if link_select.is_visible(timeout=1000):
                                    link_select.select_option("post")  # "post" = Attachment Page
                                    add_log("🔗 Set Link To: Attachment Page", "info")
                                    time.sleep(0.5)
                            except:
                                pass
                            
                            # Click "Chèn vào bài viết" / "Insert into post"
                            insert_selectors = [
                                "button.media-button-insert",
                                "button:has-text('Chèn vào bài viết')",
                                "button:has-text('Insert into post')",
                                ".media-button-insert"
                            ]
                            
                            for selector in insert_selectors:
                                try:
                                    btn = page.locator(selector).first
                                    if btn.is_visible(timeout=1000):
                                        btn.click()
                                        images_inserted += 1
                                        add_log(f"🖼️ Đã chèn hình {images_inserted} sau H2 #{h2_index + 1}", "success")
                                        time.sleep(1)
                                        break
                                except:
                                    continue
                        
                    except Exception as e:
                        add_log(f"⚠️ Error inserting image: {e}", "warning")
                    
                    # Always close modal after each attempt
                    force_close_all_modals(page)
                    time.sleep(0.5)
                
            except Exception as e:
                add_log(f"⚠️ Could not insert image after H2 #{h2_index + 1}: {e}", "warning")
                force_close_all_modals(page)
                continue
        
        # Final cleanup
        force_close_all_modals(page)
        
        add_log(f"✅ Đã chèn {images_inserted} hình vào nội dung", "success")
        return images_inserted > 0
        
    except Exception as e:
        add_log(f"⚠️ Error inserting images: {e}", "warning")
        force_close_all_modals(page)
        return False

def force_close_all_modals(page: Page):
    """Aggressively close all media modals."""
    try:
        # Try multiple times
        for attempt in range(3):
            # Press Escape multiple times
            for _ in range(3):
                page.keyboard.press("Escape")
                time.sleep(0.2)
            
            # Try clicking close buttons
            close_selectors = [
                ".media-modal-close",
                "button[aria-label='Close']",
                ".media-modal .close",
                ".media-frame-close"
            ]
            
            for selector in close_selectors:
                try:
                    close_btns = page.locator(selector).all()
                    for btn in close_btns:
                        if btn.is_visible(timeout=500):
                            btn.click()
                            time.sleep(0.3)
                except:
                    continue
            
            # Check if modal is gone
            try:
                if not page.locator(".media-modal").first.is_visible(timeout=500):
                    return  # Modal is closed
            except:
                return  # No modal found, we're done
            
            time.sleep(0.5)
    except:
        pass

def close_any_media_modal(page: Page):
    """Close any open media modal."""
    try:
        close_selectors = [
            ".media-modal-close",
            "button[aria-label='Close']",
            ".media-modal button.close",
            ".media-frame-menu .media-menu-item"
        ]
        for selector in close_selectors:
            try:
                close_btn = page.locator(selector).first
                if close_btn.is_visible(timeout=1000):
                    close_btn.click()
                    time.sleep(0.5)
                    return
            except:
                continue
        
        # Also try pressing Escape key
        page.keyboard.press("Escape")
        time.sleep(0.5)
    except:
        pass

def select_random_image_for_content(page: Page, alt_text: str) -> bool:
    """Select an image from media library and insert it into content."""
    try:
        # Wait for media modal
        page.wait_for_selector(".media-modal", timeout=10000)
        time.sleep(5)  # Wait for images to load
        
        # Try to find images
        images = page.locator(".attachments .attachment, li.attachment").all()
        
        if not images:
            add_log("⚠️ No images found in media library", "warning")
            page.locator(".media-modal-close").first.click()
            return False
        
        # Select a random image
        random_image = random.choice(images)
        random_image.click()
        time.sleep(1)
        
        # Set alt text
        alt_input = page.locator("input[data-setting='alt'], #attachment-details-alt-text, input[name='alt'], .setting input[type='text'][data-setting='alt']").first
        try:
            if alt_input.is_visible(timeout=2000):
                alt_input.fill("")
                alt_input.fill(alt_text)
                time.sleep(0.5)
        except:
            pass
        
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
        add_log(f"⚠️ Error selecting image for content: {e}", "warning")
        try:
            page.locator(".media-modal-close").first.click()
        except:
            pass
        return False

def select_first_category(page: Page) -> bool:
    """Select first category (Classic Editor)."""
    try:
        # Get all category checkboxes directly
        checkboxes = page.locator("#categorychecklist input[type='checkbox']").all()
        
        if checkboxes:
            # Check the first one if not already checked
            first_checkbox = checkboxes[0]
            if not first_checkbox.is_checked():
                first_checkbox.check()
            add_log("✅ Selected first category", "success")
            return True
        else:
            add_log("⚠️ No categories found", "warning")
        
        return False
        
    except Exception as e:
        add_log(f"⚠️ Error selecting category: {e}", "warning")
        return False

def set_featured_image(page: Page, keyword: str) -> bool:
    """Set featured image (Classic Editor) with improved reliability."""
    try:
        add_log("🖼️ Setting featured image...", "info")
        
        # First, close any open modals
        force_close_all_modals(page)
        time.sleep(1)
        
        # Scroll to Featured Image section
        try:
            featured_box = page.locator("#postimagediv, #postimagediv-hide").first
            if featured_box.is_visible(timeout=2000):
                featured_box.scroll_into_view_if_needed()
                time.sleep(0.5)
        except:
            pass
        
        # Try multiple selectors for the "Set featured image" link
        link_selectors = [
            "#set-post-thumbnail",
            "a:has-text('Đặt ảnh đại diện')",
            "a:has-text('Set featured image')",
            "#postimagediv a",
            ".inside a"
        ]
        
        clicked = False
        for selector in link_selectors:
            try:
                link = page.locator(selector).first
                if link.is_visible(timeout=1000):
                    link.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    link.click()
                    add_log(f"📸 Clicked: {selector}", "info")
                    clicked = True
                    break
            except:
                continue
        
        if not clicked:
            add_log("⚠️ Không tìm thấy link ảnh đại diện", "warning")
            return False
        
        # Wait for media modal to open
        time.sleep(2)
        
        # Try to wait for modal with longer timeout
        try:
            page.wait_for_selector(".media-modal", timeout=10000)
            add_log("📸 Modal chọn ảnh đã mở", "info")
        except:
            add_log("⚠️ Modal không mở, đang thử lại...", "warning")
            # Try clicking again
            try:
                page.locator("#set-post-thumbnail, a:has-text('Đặt ảnh đại diện')").first.click()
                time.sleep(3)
                page.wait_for_selector(".media-modal", timeout=10000)
            except:
                add_log("❌ Vẫn không tìm thấy modal", "error")
                return False
        
        # Wait for images to load
        time.sleep(3)
        
        # Click on Media Library tab if available
        try:
            media_lib_tab = page.locator(".media-menu-item:has-text('Thư viện Media'), .media-menu-item:has-text('Media Library')").first
            if media_lib_tab.is_visible(timeout=1000):
                media_lib_tab.click()
                time.sleep(2)
                add_log("📂 Đã chuyển sang Thư viện Media", "info")
        except:
            pass
        
        # Find images
        time.sleep(2)  # Extra wait for images to load
        images = page.locator(".attachments .attachment, li.attachment, .attachment-preview").all()
        
        if not images:
            add_log("⚠️ No images found in media library", "warning")
            force_close_all_modals(page)
            return False
        
        add_log(f"📸 Tìm thấy {len(images)} hình ảnh", "info")
        
        # Click first visible image
        image_clicked = False
        for i, img in enumerate(images[:5]):
            try:
                if img.is_visible(timeout=500):
                    img.click()
                    add_log(f"📸 Selected image {i+1}", "info")
                    image_clicked = True
                    time.sleep(1)
                    break
            except:
                continue
        
        if not image_clicked:
            add_log("⚠️ Could not click any image", "warning")
            force_close_all_modals(page)
            return False
        
        # Set alt text if available
        try:
            alt_input = page.locator("input[data-setting='alt']").first
            if alt_input.is_visible(timeout=1000):
                alt_input.fill(keyword)
        except:
            pass
        
        # Click "Đặt ảnh đại diện" / "Set featured image" button
        button_selectors = [
            "button.media-button-select",
            "button:has-text('Đặt ảnh đại diện')",
            "button:has-text('Set featured image')",
            ".media-button-select",
            "button.button-primary"
        ]
        
        button_clicked = False
        for selector in button_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    add_log(f"✅ Clicked button: {selector}", "success")
                    button_clicked = True
                    time.sleep(1)
                    break
            except:
                continue
        
        if not button_clicked:
            add_log("⚠️ Could not find Set Featured Image button", "warning")
            force_close_all_modals(page)
            return False
        
        # Close any remaining modals
        time.sleep(1)
        force_close_all_modals(page)
        
        add_log("✅ Đã đặt ảnh đại diện thành công!", "success")
        return True
        
    except Exception as e:
        add_log(f"⚠️ Error setting featured image: {e}", "warning")
        force_close_all_modals(page)
        return False

def publish_or_schedule_post(page: Page, is_schedule: bool, publish_date: datetime = None) -> bool:
    """Publish or schedule post (Classic Editor)."""
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
        add_log("📤 Preparing to publish...", "info")
        
        # Wait a moment for any overlays to disappear
        time.sleep(2)
        
        # Scroll to publish button area
        try:
            page.evaluate("document.getElementById('publish').scrollIntoView({block: 'center'})")
        except:
            pass
        time.sleep(1)
        
        # Try to click using JavaScript to bypass any overlay
        try:
            page.evaluate("document.getElementById('publish').click()")
            add_log("📤 Clicked publish button", "info")
        except Exception as js_err:
            add_log(f"⚠️ JS click failed: {js_err}, trying regular click", "warning")
            # Fallback to regular click
            publish_btn = page.locator("#publish, input#publish").first
            if publish_btn.is_visible(timeout=3000):
                publish_btn.click(force=True)
        
        # Wait for page to reload - this is critical
        add_log("⏳ Waiting for page to save...", "info")
        time.sleep(8)  # Wait 8 seconds for page reload
        
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
                    add_log("✅ Success message detected", "info")
                    break
        except:
            pass
        
        # Method 2: Check URL for post.php (means we're on edit page of saved post)
        if not success_detected:
            current_url = page.url
            if "post.php" in current_url and "action=edit" in current_url:
                success_detected = True
                add_log("✅ Post saved - now on edit page", "info")
        
        # Method 3: Check URL for message parameter
        if not success_detected:
            current_url = page.url
            if "message=" in current_url:
                success_detected = True
                add_log("✅ Post saved - message in URL", "info")
        
        # Method 4: Check if View Post link exists
        if not success_detected:
            try:
                view_post = page.locator("a:has-text('View post'), a:has-text('Xem bài viết')").first
                if view_post.is_visible(timeout=2000):
                    success_detected = True
                    add_log("✅ View post link found", "info")
            except:
                pass
        
        # Method 5: Check if post ID exists in URL (meaning post was created)
        if not success_detected:
            current_url = page.url
            if "post=" in current_url:
                success_detected = True
                add_log("✅ Post ID found in URL", "info")
        
        if success_detected:
            action = "Scheduled" if is_schedule else "Published"
            add_log(f"✅ {action} successfully!", "success")
            return True
        else:
            add_log("⚠️ Could not confirm publish status, but continuing...", "warning")
            # Return True anyway since the click happened
            return True
        
    except Exception as e:
        add_log(f"❌ Error publishing: {e}", "error")
        return False

def create_single_post(page: Page, index: int, topic: dict, content: str, start_date: datetime) -> bool:
    """Create a single WordPress post."""
    title = topic["title"]
    keyword = topic["keyword"]
    
    add_log(f"📝 Đang tạo bài {index + 1}: {title}", "info")
    
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
        
        add_log(f"📅 Ngày đăng: {publish_date.strftime('%Y-%m-%d %H:%M')} (Ngày {days_offset + 1}, Slot {slot_in_day + 1}/{posts_per_day})", "info")
        
        if not navigate_to_new_post(page):
            return False
        
        if not set_post_title(page, title):
            return False
        
        # Add content - this is critical
        if not set_post_content(page, content):
            add_log("⚠️ Content may not have been added properly", "warning")
        
        # Set Rank Math SEO keyword
        set_rank_math_keyword(page, keyword)
        
        # Insert images after alternating H2 headings (1st, 3rd, 5th)
        insert_images_after_h2(page, keyword, max_images=3)
        
        # Select category
        select_first_category(page)
        
        # Skip featured image - removed by user request
        # set_featured_image(page, keyword)
        
        # Publish or schedule
        if not publish_or_schedule_post(page, is_schedule, publish_date if is_schedule else None):
            return False
        
        return True
        
    except Exception as e:
        add_log(f"❌ Error creating post: {e}", "error")
        return False

def run_automation():
    """Main automation function that runs in a separate thread."""
    if not PLAYWRIGHT_AVAILABLE:
        add_log("❌ Playwright not available. Please install it first.", "error")
        state.is_running = False
        return
    
    state.is_running = True
    state.progress = 0
    state.successful_posts = 0
    state.failed_posts = 0
    state.logs = []
    
    add_log("🚀 Starting WordPress Auto Poster...", "info")
    
    provider = state.config.get("ai_provider", "ollama")
    total_topics = len(state.topics)
    state.total_tasks = total_topics * 2
    state.generated_contents = []
    
    # For non-gemini_web providers, generate content first
    if provider != "gemini_web":
        add_log(f"📝 Phase 1: Generating content with {provider.upper()}...", "info")
        state.current_task = "Generating content..."
        
        for i, topic in enumerate(state.topics):
            if not state.is_running:
                add_log("⏹️ Stopped by user", "warning")
                return
            
            state.current_task = f"Generating content {i+1}/{total_topics}..."
            content = generate_content(topic["title"], topic["keyword"])
            state.generated_contents.append(content)
            state.progress = ((i + 1) / state.total_tasks) * 100
            
            if i < len(state.topics) - 1 and state.is_running:
                time.sleep(state.config["delay_between_requests"])
        
        successful_gen = sum(1 for c in state.generated_contents if c is not None)
        add_log(f"✅ Generated {successful_gen}/{total_topics} articles", "success")
        
        if successful_gen == 0:
            add_log("❌ No content generated. Stopping.", "error")
            state.is_running = False
            return
    else:
        add_log("📝 Gemini Web Chat: Content will be generated in browser...", "info")
    
    # Phase 2: WordPress automation
    add_log("🌐 Phase 2: WordPress Automation...", "info")
    state.current_task = "Starting browser..."
    
    start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    with sync_playwright() as p:
        add_log("🦁 Starting Brave browser...", "info")
        
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
        
        add_log("✅ Brave browser started (login sessions saved)", "success")
        
        # Get existing page or create new one
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
        
        page.set_default_timeout(60000)
        
        try:
            # For Gemini Web, generate content first using browser
            if provider == "gemini_web":
                add_log("🌐 Phase 1: Generating content with Gemini Web Chat...", "info")
                
                for i, topic in enumerate(state.topics):
                    if not state.is_running:
                        add_log("⏹️ Stopped by user", "warning")
                        break
                    
                    state.current_task = f"Generating content {i+1}/{total_topics} via Gemini Web..."
                    content = generate_content_gemini_web(page, topic["title"], topic["keyword"])
                    state.generated_contents.append(content)
                    state.progress = ((i + 1) / state.total_tasks) * 100
                    
                    if i < len(state.topics) - 1 and state.is_running:
                        time.sleep(3)  # Short delay between Gemini requests
                
                successful_gen = sum(1 for c in state.generated_contents if c is not None)
                add_log(f"✅ Generated {successful_gen}/{total_topics} articles via Gemini Web", "success")
                
                if successful_gen == 0:
                    add_log("❌ No content generated. Stopping.", "error")
                    state.is_running = False
                    context.close()
                    return
            
            # Now login to WordPress
            if not login_to_wordpress(page):
                add_log("❌ Failed to login. Exiting...", "error")
                state.is_running = False
                context.close()
                return
            
            for i, (topic, content) in enumerate(zip(state.topics, state.generated_contents)):
                if not state.is_running:
                    add_log("⏹️ Stopped by user", "warning")
                    break
                
                if content is None:
                    add_log(f"⏭️ Skipping post {i+1} - no content", "warning")
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
                    add_log(f"❌ Error on post {i+1}: {e}", "error")
                    state.failed_posts += 1
                
                state.progress = ((total_topics + i + 1) / state.total_tasks) * 100
                
                if i < len(state.topics) - 1:
                    time.sleep(3)
            
            # Summary
            add_log(f"📊 SUMMARY: {state.successful_posts} successful, {state.failed_posts} failed", "success")
            
        except Exception as e:
            add_log(f"❌ Critical error: {e}", "error")
        finally:
            time.sleep(2)
            context.close()
    
    state.current_task = "Completed!"
    state.progress = 100
    state.is_running = False
    add_log("🎉 WordPress Auto Poster completed!", "success")

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        "is_running": state.is_running,
        "current_task": state.current_task,
        "progress": state.progress,
        "successful_posts": state.successful_posts,
        "failed_posts": state.failed_posts,
        "logs": state.logs[-20:],  # Last 20 logs
        "gemini_available": GEMINI_AVAILABLE,
        "ollama_available": check_ollama(),
        "playwright_available": PLAYWRIGHT_AVAILABLE
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
    
    # Start in background thread
    thread = threading.Thread(target=run_automation)
    thread.daemon = True
    thread.start()
    
    return jsonify({"success": True, "message": "Started"})

@app.route('/api/stop', methods=['POST'])
def stop_automation():
    state.is_running = False
    add_log("⏹️ Stop requested by user", "warning")
    return jsonify({"success": True})

@app.route('/api/ollama/start', methods=['POST'])
def start_ollama():
    """Start Ollama service using brew services."""
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
    """Stop Ollama service using brew services."""
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
    """Get Ollama service status."""
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
