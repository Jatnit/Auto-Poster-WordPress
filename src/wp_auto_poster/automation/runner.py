"""Automation runner orchestration."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

LogFunc = Callable[[str, str], None]


@dataclass
class AutomationRuntime:
    state: Any
    add_log: LogFunc
    wait_if_paused: Callable[[], bool]
    playwright_available: bool
    sync_playwright: Callable[[], Any]
    get_inline_image_random_pool_size: Callable[[], int]
    generate_content_with_min_word_retries: Callable[..., Any]
    process_content_retry_queue: Callable[..., Any]
    cleanup_provider_chat_session: Callable[..., bool]
    login_to_wordpress: Callable[[Any], bool]
    create_single_post: Callable[..., bool]


def run_automation(runtime: AutomationRuntime) -> None:
    if not runtime.playwright_available:
        runtime.add_log("Playwright not available. Please install it first.", "error")
        runtime.state.is_running = False
        runtime.state.current_phase = "stopped"
        return
    
    runtime.state.reset()
    
    runtime.add_log("Starting WordPress Auto Poster...", "info")
    if runtime.state.config.get("auto_insert_inline_images", True):
        expected_inline_images = len(runtime.state.topics) * 3
        inline_pool_size = runtime.get_inline_image_random_pool_size()
        runtime.add_log(
            f"Inline image random no-repeat: target {expected_inline_images} unique "
            f"image(s), scanning up to {inline_pool_size} media item(s)",
            "info",
        )
        if expected_inline_images > inline_pool_size:
            runtime.add_log(
                f"Inline image target exceeds scan cap ({expected_inline_images}>{inline_pool_size}); "
                "increase media pool cap if every post must have unique images.",
                "warning",
            )
    
    provider = runtime.state.config.get("ai_provider", "ollama")
    total_topics = len(runtime.state.topics)
    runtime.state.total_tasks = total_topics * 2
    runtime.state.generated_contents = []
    
    # For non-browser providers (ollama, gemini API), generate content first
    is_browser_provider = provider in ("gemini_web", "chatgpt_web")
    if not is_browser_provider:
        runtime.add_log(f"Phase 1: Generating content with {provider.upper()}...", "info")
        runtime.state.current_task = "Generating content..."
        runtime.state.current_phase = "generating_content"
        
        for i, topic in enumerate(runtime.state.topics):
            if not runtime.state.is_running:
                runtime.add_log("Stopped by user", "warning")
                return
            
            # Check if paused
            if not runtime.wait_if_paused():
                runtime.add_log("Stopped while paused", "warning")
                return
            
            runtime.state.current_task = f"Generating content {i+1}/{total_topics}..."
            validated_content = runtime.generate_content_with_min_word_retries(
                provider,
                topic,
                i,
                source="initial",
            )
            runtime.state.generated_contents.append(validated_content)
            runtime.state.progress = ((i + 1) / runtime.state.total_tasks) * 100
            
            if i < len(runtime.state.topics) - 1 and runtime.state.is_running:
                time.sleep(runtime.state.config["delay_between_requests"])

        runtime.process_content_retry_queue(provider, total_topics)
        
        successful_gen = sum(1 for c in runtime.state.generated_contents if c is not None)
        runtime.add_log(f"Generated {successful_gen}/{total_topics} articles", "success")
        
        if successful_gen == 0:
            runtime.add_log("No content generated. Stopping.", "error")
            runtime.state.is_running = False
            return
    else:
        provider_label = "Gemini Web Chat" if provider == "gemini_web" else "ChatGPT Web"
        runtime.add_log(f"{provider_label}: Content will be generated in browser...", "info")
    
    runtime.add_log("Phase 2: WordPress Automation...", "info")
    runtime.state.current_task = "Starting browser..."
    
    schedule_start = runtime.state.config.get("schedule_start_date", "")
    if schedule_start:
        try:
            start_date = datetime.strptime(schedule_start, "%Y-%m-%d")
            runtime.add_log(f"Schedule: {schedule_start} -> {runtime.state.config.get('schedule_end_date', '')}", "info")
        except ValueError:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    with runtime.sync_playwright() as p:
        runtime.add_log("Starting Brave browser...", "info")
        
        # Use persistent context to save login sessions
        import os
        user_data_dir = os.path.expanduser("~/.gemini/browser_data")
        os.makedirs(user_data_dir, exist_ok=True)
        
        brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        
        # Launch persistent context (saves cookies, login sessions, etc.)
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=brave_path,
            headless=runtime.state.config["headless_mode"],
            viewport={"width": 1920, "height": 1080},
            locale="vi-VN",
            slow_mo=100,
            ignore_https_errors=True,  # Một số WP site dùng cert self-signed / expired
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
                "--ignore-certificate-errors",
                "--allow-insecure-localhost",
            ]
        )
        
        runtime.add_log("Brave browser started (login sessions saved)", "success")
        
        # Get existing page or create new one
        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()
        
        page.set_default_timeout(60000)
        
        try:
            # For browser-based providers (Gemini Web / ChatGPT Web),
            # generate content using the same context.
            if provider in ("gemini_web", "chatgpt_web"):
                provider_label = (
                    "Gemini Web Chat" if provider == "gemini_web" else "ChatGPT Web"
                )
                runtime.add_log(
                    f"Phase 1: Generating content with {provider_label}...",
                    "info",
                )
                runtime.state.current_phase = "generating_content"
                
                for i, topic in enumerate(runtime.state.topics):
                    if not runtime.state.is_running:
                        runtime.add_log("Stopped by user", "warning")
                        break
                    
                    # Check if paused
                    if not runtime.wait_if_paused():
                        runtime.add_log("Stopped while paused", "warning")
                        break
                    
                    runtime.state.current_task = (
                        f"Generating content {i+1}/{total_topics} via {provider_label}..."
                    )
                    runtime.state.current_title = topic["title"]
                    runtime.state.current_keyword = topic["keyword"]
                    
                    validated_content = runtime.generate_content_with_min_word_retries(
                        provider,
                        topic,
                        i,
                        page=page,
                        source="initial",
                    )
                    runtime.state.generated_contents.append(validated_content)
                    
                    runtime.state.progress = ((i + 1) / runtime.state.total_tasks) * 100
                    
                    if i < len(runtime.state.topics) - 1 and runtime.state.is_running:
                        time.sleep(3)  # Short delay between requests

                runtime.process_content_retry_queue(provider, total_topics, page=page)
                
                successful_gen = sum(1 for c in runtime.state.generated_contents if c is not None)
                runtime.add_log(
                    f"Generated {successful_gen}/{total_topics} articles via {provider_label}",
                    "success",
                )
                
                if successful_gen == 0:
                    runtime.add_log("No content generated. Stopping.", "error")
                    runtime.state.is_running = False
                    context.close()
                    return

                # Dọn session chat AI vừa dùng để tránh rối lịch sử hội thoại.
                try:
                    runtime.cleanup_provider_chat_session(page, provider)
                except Exception as e:
                    runtime.add_log(f"Không thể dọn session chat: {e}", "warning")

                # Tách tab: đóng tab AI đang chạy, mở tab mới sạch cho WordPress.
                # Service worker + beforeunload handler trên Gemini/ChatGPT có
                # thể gây ERR_ABORTED khi navigate sang domain khác.
                try:
                    runtime.add_log("Mở tab mới sạch cho WordPress...", "info")
                    new_page = context.new_page()
                    new_page.set_default_timeout(60000)
                    old_page = page
                    page = new_page
                    try:
                        old_page.close()
                    except Exception:
                        pass
                except Exception as e:
                    runtime.add_log(f"Không tạo được tab mới: {e} — tiếp tục với tab cũ", "warning")

            # Now login to WordPress
            if not runtime.login_to_wordpress(page):
                runtime.add_log("Failed to login. Exiting...", "error")
                runtime.state.is_running = False
                runtime.state.current_phase = "stopped"
                context.close()
                return
            
            runtime.state.current_phase = "creating_posts"
            for i, (topic, content) in enumerate(zip(runtime.state.topics, runtime.state.generated_contents)):
                if not runtime.state.is_running:
                    runtime.add_log("Stopped by user", "warning")
                    break
                
                # Check if paused
                if not runtime.wait_if_paused():
                    runtime.add_log("Stopped while paused", "warning")
                    break
                
                if i in runtime.state.skip_post_indices:
                    runtime.add_log(f"Skipping post {i+1} theo yêu cầu người dùng", "warning")
                    runtime.state.failed_posts += 1
                    continue

                if content is None:
                    runtime.add_log(f"Skipping post {i+1} - no content", "warning")
                    runtime.state.failed_posts += 1
                    continue
                
                runtime.state.current_task = f"Creating post {i+1}/{total_topics}..."
                
                max_retries = 2
                success = False
                for attempt in range(max_retries + 1):
                    try:
                        if attempt > 0:
                            runtime.add_log(f"Thử lại lần {attempt}/{max_retries} cho bài {i+1}...", "warning")
                            time.sleep(10)
                        
                        if not runtime.state.is_running:
                            break
                        
                        success = runtime.create_single_post(page, i, topic, content, start_date)
                        if success:
                            break
                        
                        if attempt < max_retries:
                            runtime.add_log(f"Bài {i+1} thất bại, sẽ thử lại...", "warning")
                        
                    except Exception as e:
                        runtime.add_log(f"Lỗi bài {i+1} (lần {attempt+1}/{max_retries+1}): {e}", "error")
                        if attempt < max_retries:
                            runtime.add_log(f"Sẽ thử lại sau 10 giây...", "warning")
                            time.sleep(10)
                
                if success:
                    runtime.state.successful_posts += 1
                else:
                    runtime.add_log(f"Bỏ qua bài {i+1} sau {max_retries + 1} lần thử", "error")
                    runtime.state.failed_posts += 1
                
                runtime.state.progress = ((total_topics + i + 1) / runtime.state.total_tasks) * 100
                
                if i < len(runtime.state.topics) - 1:
                    time.sleep(3)
            
            # Summary
            runtime.add_log(f"SUMMARY: {runtime.state.successful_posts} successful, {runtime.state.failed_posts} failed", "success")
            
        except Exception as e:
            runtime.add_log(f"Critical error: {e}", "error")
            runtime.state.current_phase = "error"
        finally:
            time.sleep(2)
            context.close()
    
    if runtime.state.is_running:
        runtime.state.current_task = "Completed!"
        runtime.state.progress = 100
        runtime.state.current_phase = "completed"
        runtime.add_log("WordPress Auto Poster completed!", "success")
    elif runtime.state.current_phase not in ("error", "stopped"):
        runtime.state.current_phase = "stopped"
    runtime.state.is_running = False
