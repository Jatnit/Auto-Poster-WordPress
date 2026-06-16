from datetime import datetime

from wp_auto_poster.automation.schedule import calculate_publish_schedule


def test_calculate_publish_schedule_distributes_between_start_and_end_date():
    start_date = datetime(2026, 6, 2)
    config = {
        "schedule_start_date": "2026-06-02",
        "schedule_end_date": "2026-06-06",
        "posts_per_day": 2,
    }

    schedule = calculate_publish_schedule(
        index=4,
        total_topics=10,
        start_date=start_date,
        config=config,
        now=datetime(2026, 6, 1),
    )

    assert schedule.publish_date == datetime(2026, 6, 4, 9, 0)
    assert schedule.days_offset == 2
    assert schedule.slot_in_day == 0
    assert schedule.posts_today == 2
    assert schedule.has_schedule
    assert schedule.is_schedule


def test_calculate_publish_schedule_uses_posts_per_day_without_end_date():
    start_date = datetime(2026, 6, 2)
    config = {
        "schedule_start_date": "",
        "schedule_end_date": "",
        "posts_per_day": 3,
    }

    schedule = calculate_publish_schedule(
        index=5,
        total_topics=10,
        start_date=start_date,
        config=config,
        now=datetime(2026, 6, 1),
    )

    assert schedule.publish_date == datetime(2026, 6, 3, 18, 0)
    assert schedule.days_offset == 1
    assert schedule.slot_in_day == 2
    assert schedule.posts_today == 3
    assert not schedule.has_schedule
    assert schedule.is_schedule
