"""
Atomic Structured JSON State Repository for Weekly Orchestration.
Machine source-of-truth ensuring crash-resilient persistence for weeks, reels, runs, and queue jobs.
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ReelsAIFactory.StateRepository")

from .models import (
    WeekPlan,
    PublishingSlot,
    ReelState,
    ReelPlatformStatus,
    InstagramScheduledJob,
    RunReport
)


class StateRepository:
    """
    Manages structured state under workspace/state/ with atomic writes.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = (base_dir or Path(".").resolve())
        self.state_root = self.base_dir / "workspace" / "state"
        self.weeks_dir = self.state_root / "weeks"
        self.reels_dir = self.state_root / "reels"
        self.runs_dir = self.state_root / "runs"
        self.ig_queue_dir = self.state_root / "instagram_queue"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Ensures all required subdirectories exist."""
        for d in [self.weeks_dir, self.reels_dir, self.runs_dir, self.ig_queue_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _atomic_write_json(self, target_path: Path, data: Dict[str, Any]) -> bool:
        """Writes JSON atomically using a temporary file and replace."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp_path.replace(target_path)
            return True
        except Exception as e:
            logger.error(f"[STATE REPO] Atomic write failed for {target_path.name}: {e}")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return False

    # =========================================================================
    # 1. WEEK PLANS
    # =========================================================================

    def save_week_plan(self, plan: WeekPlan) -> bool:
        """Saves a WeekPlan object to JSON."""
        path = self.weeks_dir / f"{plan.week_id}.json"
        return self._atomic_write_json(path, plan.to_dict())

    def get_week_plan(self, week_id: str) -> Optional[WeekPlan]:
        """Loads a WeekPlan object from JSON."""
        path = self.weeks_dir / f"{week_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                slots_data = data.get("slots", [])
                slots = []
                for s in slots_data:
                    slot = PublishingSlot(
                        slot_index=s.get("slot_index", 1),
                        day_number=s.get("day_number", 1),
                        date_str=s.get("date", ""),
                        time_str=s.get("time", ""),
                        scheduled_at_local=s.get("scheduled_at_local", ""),
                        scheduled_at_utc=s.get("scheduled_at_utc", ""),
                        reel_id=s.get("reel_id"),
                        youtube_status=s.get("youtube_status", "NOT_STARTED"),
                        tiktok_status=s.get("tiktok_status", "NOT_STARTED"),
                        instagram_status=s.get("instagram_status", "NOT_STARTED"),
                        qc_status=s.get("qc_status", "PENDING")
                    )
                    slots.append(slot)

                return WeekPlan(
                    week_id=data.get("week_id", week_id),
                    start_date=data.get("start_date", ""),
                    timezone=data.get("timezone", "Europe/Istanbul"),
                    target_reels=data.get("target_reels", 14),
                    slots_per_day=data.get("slots_per_day", 2),
                    slot_times=data.get("slot_times", ["19:30", "22:00"]),
                    platforms=data.get("platforms", ["youtube", "tiktok", "instagram"]),
                    status=data.get("status", "PLANNED"),
                    approved=data.get("approved", False),
                    slots=slots,
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", "")
                )
        except Exception as e:
            logger.error(f"[STATE REPO] Error loading week plan {week_id}: {e}")
            return None

    # =========================================================================
    # 2. REEL STATES & TEST COMPLETED MIGRATION
    # =========================================================================

    def save_reel_state(self, reel: ReelState) -> bool:
        """Saves a ReelState object to JSON."""
        path = self.reels_dir / f"{reel.reel_id}.json"
        return self._atomic_write_json(path, reel.to_dict())

    def get_reel_state(self, reel_id: str) -> Optional[ReelState]:
        """Loads a ReelState object from JSON."""
        path = self.reels_dir / f"{reel_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return ReelState.from_dict(data)
        except Exception as e:
            logger.error(f"[STATE REPO] Error loading reel state {reel_id}: {e}")
            return None

    def list_all_reels(self) -> List[ReelState]:
        """Lists all stored ReelState objects."""
        results = []
        for p in self.reels_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append(ReelState.from_dict(data))
            except Exception:
                continue
        return results

    def mark_reel_test_completed(self, reel_id: str) -> bool:
        """
        Marks a Reel (e.g. REEL-2026-0010) as TEST_COMPLETED so it is excluded from weekly batches.
        """
        existing = self.get_reel_state(reel_id)
        if existing is None:
            existing = ReelState(
                reel_id=reel_id,
                youtube_status=ReelPlatformStatus.TEST_COMPLETED,
                tiktok_status=ReelPlatformStatus.TEST_COMPLETED,
                instagram_status=ReelPlatformStatus.TEST_COMPLETED
            )
        else:
            existing.youtube_status = ReelPlatformStatus.TEST_COMPLETED
            existing.tiktok_status = ReelPlatformStatus.TEST_COMPLETED
            existing.instagram_status = ReelPlatformStatus.TEST_COMPLETED

        return self.save_reel_state(existing)

    def is_reel_available_for_new_batch(self, reel_id: str) -> bool:
        """
        Returns True if the Reel is available for a new batch, and False if it has already
        been used, scheduled, published, or marked as TEST_COMPLETED.
        """
        if reel_id == "REEL-2026-0010":
            return False

        state = self.get_reel_state(reel_id)
        if state is None:
            return True

        # Check if already completed or assigned
        if state.youtube_status in [ReelPlatformStatus.SCHEDULED, ReelPlatformStatus.PUBLISHED, ReelPlatformStatus.TEST_COMPLETED]:
            return False
        if state.tiktok_status in [ReelPlatformStatus.SCHEDULED, ReelPlatformStatus.PUBLISHED, ReelPlatformStatus.TEST_COMPLETED]:
            return False
        if state.instagram_status in [ReelPlatformStatus.SCHEDULED, ReelPlatformStatus.PUBLISHED, ReelPlatformStatus.TEST_COMPLETED]:
            return False

        return True

    # =========================================================================
    # 3. RUN REPORTS
    # =========================================================================

    def save_run_report(self, report: RunReport) -> bool:
        """Saves a RunReport object to JSON."""
        path = self.runs_dir / f"{report.run_id}.json"
        return self._atomic_write_json(path, report.to_dict())

    # =========================================================================
    # 4. INSTAGRAM QUEUE JOBS
    # =========================================================================

    def save_instagram_job(self, job: InstagramScheduledJob) -> bool:
        """Saves an InstagramScheduledJob object to JSON."""
        path = self.ig_queue_dir / f"{job.job_id}.json"
        return self._atomic_write_json(path, job.to_dict())

    def get_instagram_job(self, job_id: str) -> Optional[InstagramScheduledJob]:
        """Loads an InstagramScheduledJob object from JSON."""
        path = self.ig_queue_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return InstagramScheduledJob.from_dict(data)
        except Exception as e:
            logger.error(f"[STATE REPO] Error loading instagram job {job_id}: {e}")
            return None

    def list_instagram_jobs(self, week_id: Optional[str] = None) -> List[InstagramScheduledJob]:
        """Lists InstagramScheduledJob objects, optionally filtered by week_id."""
        results = []
        for p in self.ig_queue_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    job = InstagramScheduledJob.from_dict(data)
                    if week_id is None or job.week_id == week_id:
                        results.append(job)
            except Exception:
                continue
        return results
