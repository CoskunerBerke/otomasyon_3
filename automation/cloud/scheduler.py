"""
Background Cloud Scheduler and Coordinator.
Evaluates Day-6 Telegram approval triggers, processes due Instagram publishing jobs,
and monitors worker heartbeats in Europe/Istanbul timezone.
"""
import time
import logging
import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any

logger = logging.getLogger("ReelsAIFactory.CloudScheduler")

from .config import CloudConfig
from .database import Database
from .models import CloudWeek, CloudWeekStatus
from .approval_service import ApprovalService
from .instagram_worker import InstagramCloudWorker
from automation.orchestration.slot_generator import (
    calculate_next_safe_week_start,
    generate_week_id
)


class CloudScheduler:
    """Coordinates periodic tasks in the Cloud Control Plane."""

    def __init__(
        self,
        config: CloudConfig,
        db: Database,
        approval_service: ApprovalService,
        instagram_worker: InstagramCloudWorker
    ):
        self.config = config
        self.db = db
        self.approval_service = approval_service
        self.instagram_worker = instagram_worker

    def get_current_local_datetime(self) -> datetime.datetime:
        """Returns current datetime in Europe/Istanbul timezone."""
        try:
            tz = ZoneInfo(self.config.timezone_str)
        except Exception:
            tz = datetime.timezone(datetime.timedelta(hours=3))
        return datetime.datetime.now(tz)

    def check_day6_approvals(self) -> int:
        """
        Checks active weeks to see if Day-6 approval is due today in Europe/Istanbul.
        Dispatches Telegram interactive message once per week.
        """
        now_local = self.get_current_local_datetime()
        today = now_local.date()
        current_time_str = now_local.strftime("%H:%M")

        approval_time_target = self.config.weekly_approval_local_time or "12:00"

        active_weeks = self.db.list_active_weeks()
        dispatched_count = 0

        for week in active_weeks:
            try:
                start_date = datetime.date.fromisoformat(week.start_date)
            except ValueError:
                continue

            # Day 6 = start_date + 5 days
            day6_date = start_date + datetime.timedelta(days=5)

            # Check if today is Day 6 (or past Day 6 if not sent yet) and time has reached target
            if today >= day6_date and week.approval_status == "PENDING" and week.approval_sent_at is None:
                if current_time_str >= approval_time_target:
                    # Calculate next week ID
                    next_start = start_date + datetime.timedelta(days=7)
                    next_week_id = generate_week_id(next_start)

                    # Ensure next week record exists in DB
                    next_week = self.db.get_week(next_week_id)
                    if not next_week:
                        next_end = next_start + datetime.timedelta(days=6)
                        next_week = CloudWeek(
                            week_id=next_week_id,
                            start_date=next_start.isoformat(),
                            end_date=next_end.isoformat(),
                            timezone=self.config.timezone_str,
                            status=CloudWeekStatus.PLANNED
                        )
                        self.db.save_week(next_week)

                    logger.info(f"[SCHEDULER] Day-6 reached for {week.week_id}. Sending approval for {next_week_id}...")
                    ok, _ = self.approval_service.create_and_send_approval(week.week_id, next_week_id)
                    if ok:
                        dispatched_count += 1

        return dispatched_count

    def run_iteration(self) -> Dict[str, Any]:
        """Runs a single scheduler evaluation iteration."""
        approvals_sent = self.check_day6_approvals()
        ig_jobs_processed = self.instagram_worker.process_due_jobs()

        return {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "approvals_sent": approvals_sent,
            "instagram_jobs_processed": ig_jobs_processed
        }
