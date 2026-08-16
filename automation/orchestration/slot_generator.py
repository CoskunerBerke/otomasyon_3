"""
Timezone-aware 14-Slot Weekly Plan Generator for YouTube, TikTok, and Instagram.
Handles month and year transitions seamlessly with Europe/Istanbul timezone.
"""
import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple, Optional

from .models import PublishingSlot, WeekPlan


def get_timezone(timezone_str: str = "Europe/Istanbul") -> datetime.tzinfo:
    """Returns ZoneInfo object with robust fallback."""
    try:
        return ZoneInfo(timezone_str)
    except Exception:
        if timezone_str == "Europe/Istanbul":
            return datetime.timezone(datetime.timedelta(hours=3))
        return datetime.timezone.utc


def calculate_next_safe_week_start(reference_date: Optional[datetime.date] = None) -> datetime.date:
    """
    Calculates the start date for the next safe publishing week (defaults to next Monday).
    If reference_date is on a weekend or Friday, picks the upcoming Monday.
    """
    if reference_date is None:
        tz = get_timezone("Europe/Istanbul")
        reference_date = datetime.datetime.now(tz).date()

    # Days until next Monday (0=Monday, 6=Sunday)
    days_ahead = (7 - reference_date.weekday()) % 7
    if days_ahead <= 1:  # If today is Sunday or Monday, give at least 3 days buffer
        days_ahead += 7

    return reference_date + datetime.timedelta(days=days_ahead)


def generate_week_id(start_date: datetime.date) -> str:
    """Generates standard ISO week ID, e.g. '2026-W35'."""
    year, week_num, _ = start_date.isocalendar()
    return f"{year}-W{week_num:02d}"


def generate_14_slot_week_plan(
    start_date: datetime.date,
    slot_times: Optional[List[str]] = None,
    timezone_str: str = "Europe/Istanbul"
) -> WeekPlan:
    """
    Generates a 7-day, 14-slot publishing plan (2 slots per day).
    Accurately handles month and year rollovers.
    """
    if slot_times is None:
        slot_times = ["19:30", "22:00"]

    if len(slot_times) != 2:
        raise ValueError(f"Weekly plan requires exactly 2 daily slots, got {len(slot_times)}: {slot_times}")

    tz = get_timezone(timezone_str)
    utc_tz = datetime.timezone.utc

    week_id = generate_week_id(start_date)
    plan = WeekPlan(
        week_id=week_id,
        start_date=start_date.isoformat(),
        timezone=timezone_str,
        target_reels=14,
        slots_per_day=2,
        slot_times=slot_times,
        platforms=["youtube", "tiktok", "instagram"],
        status="PLANNED",
        approved=False,
        slots=[]
    )

    slot_index = 1
    for day_offset in range(7):
        current_date = start_date + datetime.timedelta(days=day_offset)
        day_number = day_offset + 1

        for time_str in slot_times:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0

            # Local timezone datetime
            local_dt = datetime.datetime(
                year=current_date.year,
                month=current_date.month,
                day=current_date.day,
                hour=hour,
                minute=minute,
                second=0,
                tzinfo=tz
            )

            # UTC datetime
            utc_dt = local_dt.astimezone(utc_tz)

            scheduled_at_local = local_dt.strftime("%Y-%m-%d %H:%M:%S")
            scheduled_at_utc = utc_dt.strftime("%Y-%m-%d %H:%M:%S")

            slot = PublishingSlot(
                slot_index=slot_index,
                day_number=day_number,
                date_str=current_date.isoformat(),
                time_str=time_str,
                scheduled_at_local=scheduled_at_local,
                scheduled_at_utc=scheduled_at_utc,
                reel_id=None,
                youtube_status="NOT_STARTED",
                tiktok_status="NOT_STARTED",
                instagram_status="NOT_STARTED",
                qc_status="PENDING"
            )
            plan.slots.append(slot)
            slot_index += 1

    return plan
