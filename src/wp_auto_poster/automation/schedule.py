"""Post scheduling calculation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass(frozen=True)
class PublishSchedule:
    publish_date: datetime
    days_offset: int
    slot_in_day: int
    posts_today: int
    has_schedule: bool
    is_schedule: bool


def calculate_publish_schedule(
    index: int,
    total_topics: int,
    start_date: datetime,
    config: dict,
    now: Optional[datetime] = None,
) -> PublishSchedule:
    schedule_end = config.get("schedule_end_date", "")

    if schedule_end and total_topics > 0:
        try:
            end_date = datetime.strptime(schedule_end, "%Y-%m-%d")
            total_days = (end_date - start_date).days + 1
            if total_days < 1:
                total_days = 1
        except ValueError:
            total_days = max(1, (total_topics + 1) // 2)

        posts_per_day_base = total_topics // total_days
        extra_posts = total_topics % total_days

        cumulative = 0
        days_offset = 0
        slot_in_day = 0
        posts_today = posts_per_day_base + (1 if 0 < extra_posts else 0)

        for day_index in range(total_days):
            posts_for_day = posts_per_day_base + (1 if day_index < extra_posts else 0)
            if cumulative + posts_for_day > index:
                days_offset = day_index
                slot_in_day = index - cumulative
                posts_today = posts_for_day
                break
            cumulative += posts_for_day
    else:
        posts_per_day = config.get("posts_per_day", 2)
        days_offset = index // posts_per_day
        slot_in_day = index % posts_per_day
        posts_today = posts_per_day

    start_hour = 8
    end_hour = 21
    if posts_today == 1:
        hour = 9
    elif posts_today == 2:
        hour = [9, 15][slot_in_day]
    elif posts_today == 3:
        hour = [8, 13, 18][slot_in_day]
    elif posts_today == 4:
        hour = [8, 12, 16, 20][slot_in_day]
    else:
        interval = (end_hour - start_hour) / max(posts_today - 1, 1)
        hour = int(start_hour + (slot_in_day * interval))

    publish_date = start_date + timedelta(days=days_offset)
    publish_date = publish_date.replace(hour=hour, minute=0, second=0)

    current_time = now or datetime.now()
    has_schedule = bool(config.get("schedule_start_date", ""))
    is_schedule = publish_date > current_time

    return PublishSchedule(
        publish_date=publish_date,
        days_offset=days_offset,
        slot_in_day=slot_in_day,
        posts_today=posts_today,
        has_schedule=has_schedule,
        is_schedule=is_schedule,
    )
