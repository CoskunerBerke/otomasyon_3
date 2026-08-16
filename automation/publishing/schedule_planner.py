"""
Timezone-aware scheduling planner for YouTube Shorts and TikTok Studio.
Distributes videos across daily slots and future calendar dates.
"""
import datetime
from zoneinfo import ZoneInfo
from typing import List, Tuple, Optional

class SchedulePlanner:
    """Calculates strict timezone-aware future publishing slots."""

    @staticmethod
    def generate_slots(
        start_date_str: Optional[str],
        count: int,
        daily_slots: List[str],
        timezone_str: str = "Europe/Istanbul",
        allow_past_for_testing: bool = False
    ) -> List[Tuple[str, str]]:
        """
        Generate `count` publishing slots starting from `start_date_str`.
        Returns a list of tuples: `(local_iso_str, utc_iso_str)`.
        """
        if not start_date_str:
            raise ValueError(
                "schedule_start_date is NULL/empty. "
                "Lütfen önce bir başlangıç tarihi belirleyin (Örn: '2026-08-20')."
            )

        if count < 1:
            return []

        if not daily_slots:
            daily_slots = ["18:00", "20:00"]

        try:
            tz = ZoneInfo(timezone_str)
            utc_tz = ZoneInfo("UTC")
        except Exception:
            # Resilient fallback for environments without tzdata
            if timezone_str == "Europe/Istanbul":
                tz = datetime.timezone(datetime.timedelta(hours=3))
            else:
                tz = datetime.timezone.utc
            utc_tz = datetime.timezone.utc

        now_local = datetime.datetime.now(tz)

        try:
            start_date = datetime.date.fromisoformat(start_date_str)
        except ValueError as e:
            raise ValueError(f"Geçersiz schedule_start_date formatı ('{start_date_str}'). YYYY-MM-DD olmalı: {e}")

        # Parse daily slot times
        parsed_slot_times = []
        for s in daily_slots:
            parts = s.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            parsed_slot_times.append(datetime.time(hour=hour, minute=minute))

        # Sort daily slots chronologically
        parsed_slot_times.sort()

        generated_slots: List[Tuple[str, str]] = []
        current_date = start_date

        while len(generated_slots) < count:
            for slot_time in parsed_slot_times:
                local_dt = datetime.datetime.combine(current_date, slot_time, tzinfo=tz)
                utc_dt = local_dt.astimezone(utc_tz)

                # Validate safety: must not schedule in the past
                if not allow_past_for_testing:
                    if local_dt <= now_local + datetime.timedelta(minutes=5):
                        # Slot is already in the past or too close to current time
                        continue

                local_iso = local_dt.isoformat()
                # YouTube expects ISO 8601 UTC with Z suffix (e.g. 2026-08-20T15:00:00Z)
                utc_iso = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                generated_slots.append((local_iso, utc_iso))
                if len(generated_slots) == count:
                    break

            current_date += datetime.timedelta(days=1)

        return generated_slots

    @staticmethod
    def validate_tiktok_schedule_window(
        local_iso_str: str,
        timezone_str: str = "Europe/Istanbul",
        min_minutes_ahead: int = 15,
        max_days_ahead: int = 10
    ) -> Tuple[bool, str]:
        """
        Validate that a slot falls within TikTok's allowed scheduling window:
        between min_minutes_ahead (15 mins) and max_days_ahead (10 days) in the future.
        """
        try:
            tz = ZoneInfo(timezone_str)
        except Exception:
            tz = datetime.timezone(datetime.timedelta(hours=3))

        try:
            slot_dt = datetime.datetime.fromisoformat(local_iso_str)
            if slot_dt.tzinfo is None:
                slot_dt = slot_dt.replace(tzinfo=tz)
        except Exception as e:
            return False, f"Invalid datetime string '{local_iso_str}': {e}"

        now_local = datetime.datetime.now(tz)
        min_allowed = now_local + datetime.timedelta(minutes=min_minutes_ahead)
        max_allowed = now_local + datetime.timedelta(days=max_days_ahead)

        if slot_dt < min_allowed:
            return False, f"INVALID_TIKTOK_SCHEDULE_WINDOW: Slot ({local_iso_str}) is less than {min_minutes_ahead} minutes in the future."
        if slot_dt > max_allowed:
            return False, f"INVALID_TIKTOK_SCHEDULE_WINDOW: Slot ({local_iso_str}) is more than {max_days_ahead} days in the future."

        return True, "VALID_WINDOW"
