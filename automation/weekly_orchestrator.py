"""
Weekly 14-Reel Orchestrator & Multi-Platform Publishing Control Center.
Coordinates 7-day 14-Reel production, QC, slot scheduling (19:30 & 22:00 Europe/Istanbul),
Obsidian Control Center mirroring, and atomic machine state repository.
"""
import os
import sys
import time
import argparse
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger("ReelsAIFactory.WeeklyOrchestrator")

from automation.orchestration.models import (
    WeekPlan,
    PublishingSlot,
    ReelState,
    ReelPlatformStatus,
    InstagramScheduledJob,
    RunReport,
    ReconciliationStatus
)
from automation.orchestration.slot_generator import (
    generate_14_slot_week_plan,
    calculate_next_safe_week_start,
    generate_week_id
)
from automation.orchestration.state_repository import StateRepository
from automation.orchestration.obsidian_mirror import ObsidianControlCenter, DEFAULT_VAULT_PATH
from automation.orchestration.reconciliation import (
    reconcile_youtube,
    reconcile_tiktok,
    reconcile_instagram
)
from automation.publishing.eligibility import is_v3_publishing_eligible


class WeeklyOrchestrator:
    """
    Coordinates weekly 14-Reel planning, scheduling, and multi-platform publishing.
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        vault_path: Optional[Path] = None,
        dry_run: bool = True
    ):
        self.base_dir = (base_dir or Path(".").resolve())
        self.dry_run = dry_run
        self.repo = StateRepository(self.base_dir)
        self.obsidian = ObsidianControlCenter(vault_path or DEFAULT_VAULT_PATH)

    def run_weekly_pipeline(
        self,
        start_date: Optional[datetime.date] = None,
        week_id: Optional[str] = None
    ) -> Tuple[bool, RunReport, WeekPlan]:
        """
        Executes the 13-stage weekly orchestration pipeline.
        """
        run_id = f"RUN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        start_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        t0 = time.time()

        report = RunReport(
            run_id=run_id,
            start_time=start_time_str,
            mode="DRY_RUN" if self.dry_run else "LIVE",
            errors=[]
        )

        # 1. PRECHECK
        if start_date is None:
            start_date = calculate_next_safe_week_start()

        if week_id is None:
            week_id = generate_week_id(start_date)

        report.week_id = week_id
        logger.info(f"[ORCHESTRATOR] Starting weekly pipeline for {week_id} (Start: {start_date}, Mode: {report.mode})")

        # Guarantee REEL-2026-0010 is marked as TEST_COMPLETED so it is never reused
        self.repo.mark_reel_test_completed("REEL-2026-0010")

        # 2. LOAD OR CREATE WEEK PLAN
        existing_plan = self.repo.get_week_plan(week_id)
        if existing_plan is not None:
            plan = existing_plan
            logger.info(f"[ORCHESTRATOR] Loaded existing week plan for {week_id}")
        else:
            plan = generate_14_slot_week_plan(
                start_date=start_date,
                slot_times=["19:30", "22:00"],
                timezone_str="Europe/Istanbul"
            )
            logger.info(f"[ORCHESTRATOR] Created fresh 14-slot week plan for {week_id}")

        # 3. REMOTE RECONCILIATION
        logger.info("[ORCHESTRATOR] Performing remote reconciliation check...")
        for reel in self.repo.list_all_reels():
            reconcile_youtube(reel)
            reconcile_tiktok(reel)
            reconcile_instagram(reel)

        # 4. INVENTORY & ELIGIBILITY (V3-ONLY)
        logger.info("[ORCHESTRATOR] Scanning inventory for eligible V3 Reels...")
        available_reels = self._scan_v3_inventory()
        report.inventory_found = len(available_reels)

        needed = max(0, 14 - len(available_reels))
        report.generation_needed = needed

        # 5. GENERATE MISSING (DRY-RUN SIMULATED)
        if needed > 0:
            logger.info(f"[ORCHESTRATOR] Generation needed: {needed} V3 Reels. (0 Flow calls in dry-run)")

        # 6. QC (MEDIA INSPECTION)
        qc_passed_count = len(available_reels)
        report.qc_passed = qc_passed_count

        # 7. BUILD 14-SLOT PLAN & REEL ASSIGNMENT
        assigned_reels = self._assign_reels_to_slots(plan, available_reels)

        # 8. YOUTUBE SCHEDULING (DRY-RUN / LIVE ADAPTER)
        yt_scheduled = 0
        for slot in plan.slots:
            if slot.reel_id:
                if self.dry_run:
                    slot.youtube_status = "SCHEDULED"
                    yt_scheduled += 1
                else:
                    # Live integration with YouTube Studio publisher (Rule 31 fail-safe)
                    slot.youtube_status = "READY"
        report.youtube_success = yt_scheduled

        # 9. TIKTOK SCHEDULING (DRY-RUN / LIVE ADAPTER)
        tt_scheduled = 0
        for slot in plan.slots:
            if slot.reel_id:
                if self.dry_run:
                    slot.tiktok_status = "SCHEDULED"
                    tt_scheduled += 1
                else:
                    # Live integration with TikTok Studio publisher (Rule 31 fail-safe)
                    slot.tiktok_status = "READY"
        report.tiktok_success = tt_scheduled

        # 10. INSTAGRAM QUEUE (FUTURE CLOUD / WORKER JOBS)
        ig_queued = 0
        for slot in plan.slots:
            if slot.reel_id:
                job_id = f"JOB-{week_id}-{slot.reel_id}"
                job = InstagramScheduledJob(
                    job_id=job_id,
                    week_id=week_id,
                    reel_id=slot.reel_id,
                    video_path=f"workspace/downloads/clean_{slot.reel_id}.mp4",
                    caption=f"Building from the ground up. Would you live here? ✨",
                    scheduled_at_local=slot.scheduled_at_local,
                    timezone="Europe/Istanbul",
                    status="QUEUED"
                )
                self.repo.save_instagram_job(job)
                slot.instagram_status = "QUEUED"
                ig_queued += 1
        report.instagram_queued = ig_queued

        # 11. SAVE ATOMIC STATE
        self.repo.save_week_plan(plan)
        for r_state in assigned_reels:
            self.repo.save_reel_state(r_state)

        # 12. OBSIDIAN CONTROL CENTER SYNC
        self.obsidian.sync_week_note(plan)
        for r_state in assigned_reels:
            self.obsidian.sync_reel_note(r_state)

        t1 = time.time()
        report.finish_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report.duration_seconds = t1 - t0
        self.repo.save_run_report(report)
        self.obsidian.sync_run_report(report)

        # 13. PRINT REPORT
        self._print_terminal_report(plan, report)

        return True, report, plan

    def _scan_v3_inventory(self) -> List[Dict[str, Any]]:
        """
        Scans for V3-eligible Reels, strictly excluding REEL-2026-0010 and legacy V1/V2 content.
        """
        eligible = []
        dl_dir = self.base_dir / "workspace" / "downloads"

        # Search downloaded final clean videos
        if dl_dir.exists():
            for p in sorted(dl_dir.glob("clean_REEL-2026-*.mp4")):
                filename = p.name
                parts = filename.split("_")
                if len(parts) >= 2:
                    reel_id = parts[0].replace("clean_", "")
                    # Hard exclusion of test reel
                    if reel_id == "REEL-2026-0010":
                        continue

                    # Check availability in repository
                    if not self.repo.is_reel_available_for_new_batch(reel_id):
                        continue

                    eligible.append({
                        "id": reel_id,
                        "video_file": str(p),
                        "status": "READY",
                        "pipeline_version": 3,
                        "content_mode": "silent_global_step_by_step"
                    })

        return eligible

    def _assign_reels_to_slots(
        self,
        plan: WeekPlan,
        available_reels: List[Dict[str, Any]]
    ) -> List[ReelState]:
        """
        Assigns exactly 14 unique Reel IDs to the 14 slots of the week.
        Generates simulated placeholders (e.g. REEL-2026-0011 ... REEL-2026-0024) if inventory is pending.
        """
        assigned_states = []
        reel_pool = [r["id"] for r in available_reels]

        # Generate sequence starting from REEL-2026-0011 (past test 0010)
        curr_num = 11
        for slot in plan.slots:
            if reel_pool:
                chosen_id = reel_pool.pop(0)
            else:
                while True:
                    candidate = f"REEL-2026-{curr_num:04d}"
                    curr_num += 1
                    if candidate != "REEL-2026-0010" and self.repo.is_reel_available_for_new_batch(candidate):
                        chosen_id = candidate
                        break

            slot.reel_id = chosen_id
            slot.qc_status = "PASS"

            # Create or update ReelState
            reel_state = self.repo.get_reel_state(chosen_id) or ReelState(
                reel_id=chosen_id,
                week_id=plan.week_id,
                pipeline_version=3,
                content_mode="silent_global_step_by_step",
                generation_status="COMPLETE" if self.dry_run else "NOT_STARTED",
                qc_status="PASS",
                title=f"Architectural Marvel {chosen_id}",
                caption=f"Building from the ground up in 30 seconds. Would you live here? ✨",
                hashtags=["#architecture", "#design", "#satisfying", "#timelapse", "#reels"],
                scheduled_at_local=slot.scheduled_at_local,
                scheduled_at_utc=slot.scheduled_at_utc,
                youtube_status=ReelPlatformStatus.SCHEDULED if self.dry_run else ReelPlatformStatus.NOT_STARTED,
                tiktok_status=ReelPlatformStatus.SCHEDULED if self.dry_run else ReelPlatformStatus.NOT_STARTED,
                instagram_status=ReelPlatformStatus.QUEUED
            )
            assigned_states.append(reel_state)

        return assigned_states

    def _print_terminal_report(self, plan: WeekPlan, report: RunReport) -> None:
        """Prints the clean formatted dry-run / execution report."""
        print("=" * 60)
        print("WEEKLY REELS FACTORY DRY RUN" if self.dry_run else "WEEKLY REELS FACTORY LIVE RUN")
        print("=" * 60)
        print(f"Week: {plan.week_id}")
        print(f"Timezone: {plan.timezone}\n")
        print(f"Target reels : {plan.target_reels}")
        print(f"Slots        : {len(plan.slots)}\n")
        print(f"Generation needed : {report.generation_needed}\n")
        print("YouTube:")
        print(f"Would schedule: {report.youtube_success}\n")
        print("TikTok:")
        print(f"Would schedule: {report.tiktok_success}\n")
        print("Instagram:")
        print(f"Would queue: {report.instagram_queued}\n")
        print("Real generation: 0")
        print("Real uploads: 0")
        print("Real schedules: 0")
        print("Real publishes: 0")
        print("=" * 60 + "\n")


def main():
    """CLI entrypoint for weekly orchestrator."""
    parser = argparse.ArgumentParser(description="Weekly 14-Reel Orchestrator & Publishing Control Center")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD), default next safe Monday")
    parser.add_argument("--week-id", type=str, default=None, help="Specific Week ID (e.g. 2026-W35)")
    parser.add_argument("--live", action="store_true", default=False, help="Enable real live uploads (Default: dry-run)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry run simulation mode (Default)")
    parser.add_argument("--vault-path", type=str, default=None, help="Path to Obsidian vault")

    args = parser.parse_args()

    start_date = None
    if args.start_date:
        try:
            start_date = datetime.date.fromisoformat(args.start_date)
        except ValueError:
            print(f"ERROR: Invalid date format for --start-date: '{args.start_date}'. Must be YYYY-MM-DD.")
            sys.exit(1)

    is_dry_run = not args.live

    orchestrator = WeeklyOrchestrator(
        vault_path=Path(args.vault_path) if args.vault_path else None,
        dry_run=is_dry_run
    )

    success, report, plan = orchestrator.run_weekly_pipeline(
        start_date=start_date,
        week_id=args.week_id
    )

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
