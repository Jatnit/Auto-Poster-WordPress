"""Generated-content retry queue and content-list bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from wp_auto_poster.content.validation import (
    count_words,
    get_content_auto_retry_attempts,
    get_min_valid_words,
    validate_generated_content,
)

LogFunc = Callable[[str, str], None]
GenerateFunc = Callable[..., Optional[str]]
CleanFunc = Callable[[str], str]


@dataclass
class ContentRetryRuntime:
    state: Any
    add_log: LogFunc
    wait_if_paused: Callable[[], bool]
    generate_content: GenerateFunc
    clean_content: CleanFunc


def find_content_row_by_post_index(runtime: ContentRetryRuntime, post_index: int) -> Optional[int]:
    for idx, item in enumerate(runtime.state.content_list):
        if int(item.get("post_index", -1)) == post_index:
            return idx
    return None


def upsert_content_row(
    runtime: ContentRetryRuntime,
    post_index: int,
    topic: dict,
    content: str,
    status: str = "success",
    error_reason: str = "",
    attempts: int = 1,
) -> int:
    cleaned_content = runtime.clean_content(content or "")
    word_count = count_words(cleaned_content)
    row = {
        "post_index": post_index,
        "title": topic.get("title", ""),
        "keyword": topic.get("keyword", ""),
        "content": cleaned_content,
        "word_count": word_count,
        "status": status,
        "error_reason": error_reason,
        "attempts": attempts,
    }
    row_index = find_content_row_by_post_index(runtime, post_index)
    if row_index is None:
        runtime.state.content_list.append(row)
        runtime.state.content_list.sort(key=lambda x: int(x.get("post_index", 10**9)))
        row_index = find_content_row_by_post_index(runtime, post_index)
        if row_index is None:
            row_index = len(runtime.state.content_list) - 1
    else:
        runtime.state.content_list[row_index] = row

    runtime.state.current_content = cleaned_content
    return row_index


def queue_content_rerender(runtime: ContentRetryRuntime, post_index: int) -> bool:
    for item in runtime.state.retry_queue:
        if item.get("action") == "rerender_content" and int(item.get("post_index", -1)) == post_index:
            return False
    runtime.state.retry_queue.append({"action": "rerender_content", "post_index": post_index})
    return True


def generate_content_by_provider(
    runtime: ContentRetryRuntime,
    provider: str,
    topic: dict,
    page=None,
) -> Optional[str]:
    return runtime.generate_content(
        topic["title"],
        topic["keyword"],
        page=page,
        provider_override=provider,
    )


def validate_content(runtime: ContentRetryRuntime, content: Optional[str]) -> tuple:
    return validate_generated_content(
        content,
        min_valid_words=get_min_valid_words(runtime.state.config),
        cleaner=runtime.clean_content,
    )


def generate_content_with_min_word_retries(
    runtime: ContentRetryRuntime,
    provider: str,
    topic: dict,
    post_index: int,
    page=None,
    source: str = "initial",
) -> Optional[str]:
    auto_retries = get_content_auto_retry_attempts(runtime.state.config)
    total_attempts = 1 + auto_retries
    title = topic.get("title", "")
    last_cleaned = ""
    last_reason = "Không thể tạo nội dung (rỗng)"

    for attempt in range(1, total_attempts + 1):
        if attempt == 1:
            runtime.add_log(f"[CONTENT][POST:{post_index + 1}] Bắt đầu tạo nội dung: {title}", "info")
        else:
            runtime.add_log(
                f"[CONTENT][POST:{post_index + 1}] Tạo lại nội dung thiếu: {title} "
                f"(lần {attempt}/{total_attempts})",
                "warning",
            )

        if runtime.state.is_paused and not runtime.wait_if_paused():
            return None
        if not runtime.state.is_running:
            return None

        content = generate_content_by_provider(runtime, provider, topic, page=page)
        is_valid, cleaned_content, _, reason = validate_content(runtime, content)

        if is_valid:
            upsert_content_row(
                runtime,
                post_index,
                topic,
                cleaned_content,
                status="success",
                error_reason="",
                attempts=attempt,
            )
            if attempt > 1:
                runtime.add_log(
                    f"Đã tạo lại thành công cho tiêu đề: {title} (sau {attempt} lần)",
                    "success",
                )
            return cleaned_content

        last_cleaned = cleaned_content or ""
        last_reason = reason
        runtime.add_log(
            f"Nội dung cho '{title}' không hợp lệ ({reason}) "
            f"[{attempt}/{total_attempts}]",
            "error",
        )

    upsert_content_row(
        runtime,
        post_index,
        topic,
        last_cleaned,
        status="failed",
        error_reason=last_reason,
        attempts=total_attempts,
    )
    runtime.add_log(
        f"Không thể tạo lại nội dung cho tiêu đề: {title} "
        f"(đã thử {total_attempts} lần)",
        "error",
    )
    return None


def process_content_retry_queue(
    runtime: ContentRetryRuntime,
    provider: str,
    total_topics: int,
    page=None,
) -> None:
    if not runtime.state.retry_queue:
        return
    if runtime.state.current_phase not in ("generating_content", "retry_content_queue"):
        return

    runtime.state.current_phase = "retry_content_queue"
    while runtime.state.retry_queue and runtime.state.is_running:
        item = runtime.state.retry_queue.pop(0)
        if item.get("action") != "rerender_content":
            continue

        post_index = int(item.get("post_index", -1))
        if post_index < 0 or post_index >= len(runtime.state.topics):
            runtime.add_log("Yêu cầu rend lại không hợp lệ (index ngoài phạm vi)", "warning")
            continue

        topic = runtime.state.topics[post_index]
        runtime.add_log(
            f"[RETRY][CONTENT][POST:{post_index + 1}] Bắt đầu xử lý lại theo hàng chờ: {topic['title']}",
            "warning",
        )
        runtime.state.current_task = f"Re-render content {post_index + 1}/{total_topics}..."

        if not runtime.wait_if_paused():
            runtime.add_log("Stopped while paused", "warning")
            return

        validated = generate_content_with_min_word_retries(
            runtime,
            provider,
            topic,
            post_index,
            page=page,
            source="queue",
        )
        if post_index < len(runtime.state.generated_contents):
            runtime.state.generated_contents[post_index] = validated

    runtime.state.current_phase = "generating_content"
