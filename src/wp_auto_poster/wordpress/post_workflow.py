"""Post creation orchestration for WordPress automation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from wp_auto_poster.automation.schedule import calculate_publish_schedule

LogFunc = Callable[[str, str], None]


@dataclass
class PostWorkflowRuntime:
    state: Any
    log_func: LogFunc
    wait_if_paused: Callable[[], bool]
    navigate_to_new_post: Callable[[Any], bool]
    set_post_title: Callable[[Any, str], bool]
    set_post_content: Callable[[Any, str], bool]
    set_rank_math_keyword: Callable[[Any, str], bool]
    insert_images_after_h2: Callable[..., bool]
    set_featured_image: Callable[[Any, str], bool]
    select_first_category: Callable[[Any], bool]
    add_post_tags: Callable[[Any, str], bool]
    publish_or_schedule_post: Callable[[Any, bool, Optional[datetime]], bool]

    def log(self, message: str, level: str = "info") -> None:
        self.log_func(message, level)


def create_single_post(
    page: Any,
    index: int,
    topic: dict,
    content: str,
    start_date: datetime,
    runtime: PostWorkflowRuntime,
) -> bool:
    title = topic["title"]
    keyword = topic["keyword"]
    
    runtime.log(f"Đang tạo bài {index + 1}: {title}", "info")
    
    try:
        schedule = calculate_publish_schedule(
            index=index,
            total_topics=len(runtime.state.topics),
            start_date=start_date,
            config=runtime.state.config,
        )
        publish_date = schedule.publish_date
        days_offset = schedule.days_offset
        slot_in_day = schedule.slot_in_day
        posts_today = schedule.posts_today
        has_schedule = schedule.has_schedule
        is_schedule = schedule.is_schedule

        runtime.log(
            f"Ngày đăng: {publish_date.strftime('%Y-%m-%d %H:%M')} "
            f"(Ngày {days_offset + 1}, Slot {slot_in_day + 1}/{posts_today})",
            "info",
        )
        
        if not runtime.state.is_running:
            return False
        if runtime.state.is_paused:
            if not runtime.wait_if_paused():
                return False
        
        if not runtime.navigate_to_new_post(page):
            return False
        
        if not runtime.set_post_title(page, title):
            return False
        
        if not runtime.state.is_running:
            return False
        if runtime.state.is_paused:
            if not runtime.wait_if_paused():
                return False
        
        if not runtime.set_post_content(page, content):
            runtime.log("Content may not have been added properly", "warning")

        auto_set_seo_keyword = bool(runtime.state.config.get("auto_set_seo_keyword", True))
        auto_insert_inline_images = bool(runtime.state.config.get("auto_insert_inline_images", True))
        auto_set_featured_image_cfg = bool(runtime.state.config.get("auto_set_featured_image", False))
        auto_select_category_cfg = bool(runtime.state.config.get("auto_select_category", True))
        auto_add_tags_cfg = bool(runtime.state.config.get("auto_add_tags", True))

        if auto_set_seo_keyword:
            runtime.set_rank_math_keyword(page, keyword)
        else:
            runtime.log("Skip SEO keyword (auto_set_seo_keyword = OFF)", "info")
        
        if not runtime.state.is_running:
            return False
        if runtime.state.is_paused:
            if not runtime.wait_if_paused():
                return False
        
        if auto_insert_inline_images:
            runtime.insert_images_after_h2(page, keyword, max_images=3)
        else:
            runtime.log("Skip inline images (auto_insert_inline_images = OFF)", "info")

        if auto_set_featured_image_cfg:
            runtime.set_featured_image(page, keyword)
        else:
            runtime.log("Skip featured image (auto_set_featured_image = OFF)", "info")

        if auto_select_category_cfg:
            runtime.select_first_category(page)
        else:
            runtime.log("Skip category selection (auto_select_category = OFF)", "info")

        tags = topic.get("tags", "")
        if auto_add_tags_cfg and tags:
            runtime.add_post_tags(page, tags)
        elif not auto_add_tags_cfg:
            runtime.log("Skip tags (auto_add_tags = OFF)", "info")
        
        if not runtime.state.is_running:
            return False
        if runtime.state.is_paused:
            if not runtime.wait_if_paused():
                return False
        
        if has_schedule:
            if not runtime.publish_or_schedule_post(page, True, publish_date):
                return False
        else:
            if not runtime.publish_or_schedule_post(page, is_schedule, publish_date if is_schedule else None):
                return False
        
        return True
        
    except Exception as e:
        runtime.log(f"Error creating post: {e}", "error")
        return False
