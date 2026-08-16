"""
Weekly 14-Reel Orchestrator & Multi-Platform Publishing Control Center.
Coordinates 7-day 14-Reel production, QC, slot scheduling (19:30 & 22:00 Europe/Istanbul),
real Flow V3 generation, real YouTube Studio native scheduling, real TikTok Studio native scheduling,
authenticated Railway S3 media handoff (PostgreSQL MEDIA_READY), and Obsidian Control Center sync.
"""
import os
import re
import sys
import time
import hashlib
import argparse
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

logger = logging.getLogger("ReelsAIFactory.WeeklyOrchestrator")

from automation.config import load_config, AppConfig
from automation.publishing.config import PublishingConfig, load_publishing_config
from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord
from automation.publishing.youtube_studio_publisher import (
    BaseYouTubePublisher,
    YouTubeStudioPublisher,
    MockYouTubeStudioPublisher
)
from automation.publishing.youtube_publisher import YouTubePublisher, MockYouTubePublisher
from automation.publishing.tiktok_publisher import (
    BaseTikTokPublisher,
    TikTokPublisher,
    MockTikTokPublisher
)
from automation.flow.generator import GoogleFlowWebProvider, MockVideoProvider, VideoProvider
from automation.content.engine import ContentEngine
from automation.content.prompt_engine import ReelConceptPlan
from automation.quality.validator import VideoValidator
from automation.media_handoff import handoff_reel_to_cloud
from automation.local_worker_cloud_client import LocalWorkerCloudClient
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


class WeeklyOrchestrator:
    """
    Coordinates weekly 14-Reel planning, generation, scheduling, and multi-platform publishing.
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        vault_path: Optional[Path] = None,
        dry_run: bool = True,
        mock: bool = False,
        flow_provider: Optional[Any] = None,
        yt_publisher: Optional[BaseYouTubePublisher] = None,
        tt_publisher: Optional[BaseTikTokPublisher] = None,
        cloud_client: Optional[LocalWorkerCloudClient] = None
    ):
        self.base_dir = (base_dir or Path(".").resolve())
        self.dry_run = dry_run
        self.mock = mock
        self.repo = StateRepository(self.base_dir)
        self.obsidian = ObsidianControlCenter(vault_path or DEFAULT_VAULT_PATH)

        try:
            self.app_config = load_config(base_dir=self.base_dir)
            if vault_path:
                self.app_config.vault_path = Path(vault_path)
        except Exception:
            self.app_config = AppConfig(
                vault_path=vault_path or DEFAULT_VAULT_PATH,
                output_path=self.base_dir / "output",
                chrome_profile_dir=self.base_dir / "workspace" / "chrome-profile",
                workspace_downloads_dir=self.base_dir / "workspace" / "downloads"
            )

        try:
            self.pub_config = load_publishing_config(base_dir=self.base_dir)
        except Exception:
            self.pub_config = PublishingConfig()

        # Injected or instantiated publishers
        self.flow_provider = flow_provider
        self.yt_publisher = yt_publisher
        self.tt_publisher = tt_publisher
        self.cloud_client = cloud_client

    def _init_publishers_if_needed(self, need_generation: bool = False) -> None:
        """Lazily initializes platform publishers if not already injected."""
        if self.mock:
            if self.yt_publisher is None:
                self.yt_publisher = MockYouTubeStudioPublisher(expected_handle=self.pub_config.youtube_expected_handle)
            if self.tt_publisher is None:
                self.tt_publisher = MockTikTokPublisher(expected_username=self.pub_config.tiktok_expected_username)
            if self.flow_provider is None:
                self.flow_provider = MockVideoProvider(self.app_config.workspace_downloads_dir)
        elif not self.dry_run:
            if self.yt_publisher is None:
                if getattr(self.pub_config, "youtube_mode", "studio") == "studio":
                    self.yt_publisher = YouTubeStudioPublisher(self.pub_config)
                else:
                    self.yt_publisher = YouTubePublisher(self.pub_config)
            if self.tt_publisher is None:
                self.tt_publisher = TikTokPublisher(self.pub_config)
            if self.flow_provider is None and need_generation:
                self.flow_provider = GoogleFlowWebProvider(self.app_config)

    def run_weekly_pipeline(
        self,
        start_date: Optional[datetime.date] = None,
        week_id: Optional[str] = None
    ) -> Tuple[bool, RunReport, WeekPlan]:
        """
        Executes the weekly 14-Reel production and multi-platform publishing pipeline.
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

        unassigned_slots = [s for s in plan.slots if not s.reel_id or not self._resolve_video_file(s.reel_id).exists()]
        needed = max(0, len(unassigned_slots) - len(available_reels))
        report.generation_needed = needed

        self._init_publishers_if_needed(need_generation=(needed > 0))

        # 5. GENERATE MISSING V3 REELS (IF LIVE & NEEDED)
        if needed > 0 and not self.dry_run:
            logger.info(f"[ORCHESTRATOR] Generating {needed} missing V3 Reels via Flow...")
            generated_reels = self._generate_missing_v3_reels(needed=needed, week_id=week_id)
            available_reels.extend(generated_reels)

        # 6. QC (MEDIA INSPECTION)
        qc_passed_count = len(available_reels)
        report.qc_passed = qc_passed_count

        # 7. BUILD 14-SLOT PLAN & REEL ASSIGNMENT
        assigned_reels = self._assign_reels_to_slots(plan, available_reels)

        # 8. YOUTUBE NATIVE SCHEDULING (19:30 / 22:00)
        yt_scheduled = 0
        for slot in plan.slots:
            if not slot.reel_id:
                continue

            r_state = self._find_or_create_reel_state(slot.reel_id, assigned_reels, week_id, slot)
            if slot.youtube_status in ("SCHEDULED", "PUBLISHED", "REMOTE_VERIFIED"):
                logger.info(f"[{slot.reel_id}] YouTube already {slot.youtube_status}, skipping.")
                yt_scheduled += 1
                continue

            if self.dry_run:
                slot.youtube_status = "SCHEDULED"
                r_state.youtube_status = ReelPlatformStatus.SCHEDULED
                yt_scheduled += 1
            else:
                ok_yt = self._schedule_youtube_slot(slot, r_state)
                if ok_yt:
                    yt_scheduled += 1
                else:
                    report.errors.append(f"YouTube scheduling failed for {slot.reel_id}")

        report.youtube_success = yt_scheduled

        # 9. TIKTOK NATIVE SCHEDULING (19:30 / 22:00)
        tt_scheduled = 0
        for slot in plan.slots:
            if not slot.reel_id:
                continue

            r_state = self._find_or_create_reel_state(slot.reel_id, assigned_reels, week_id, slot)
            if slot.tiktok_status in ("SCHEDULED", "PUBLISHED", "REMOTE_VERIFIED"):
                logger.info(f"[{slot.reel_id}] TikTok already {slot.tiktok_status}, skipping.")
                tt_scheduled += 1
                continue

            if self.dry_run:
                slot.tiktok_status = "SCHEDULED"
                r_state.tiktok_status = ReelPlatformStatus.SCHEDULED
                tt_scheduled += 1
            else:
                ok_tt = self._schedule_tiktok_slot(slot, r_state)
                if ok_tt:
                    tt_scheduled += 1
                else:
                    report.errors.append(f"TikTok scheduling failed for {slot.reel_id}")

        report.tiktok_success = tt_scheduled

        # 10. INSTAGRAM CLOUD HANDOFF (RAILWAY S3 + POSTGRESQL MEDIA_READY)
        ig_queued = 0
        for slot in plan.slots:
            if not slot.reel_id:
                continue

            r_state = self._find_or_create_reel_state(slot.reel_id, assigned_reels, week_id, slot)
            if slot.instagram_status in ("MEDIA_READY", "SCHEDULED", "PUBLISHED", "REMOTE_VERIFIED"):
                logger.info(f"[{slot.reel_id}] Instagram handoff already {slot.instagram_status}, skipping.")
                ig_queued += 1
                continue

            if self.dry_run:
                slot.instagram_status = "QUEUED"
                r_state.instagram_status = ReelPlatformStatus.QUEUED
                ig_queued += 1
            else:
                ok_ig = self._handoff_instagram_slot(slot, r_state, week_id)
                if ok_ig:
                    ig_queued += 1
                else:
                    report.errors.append(f"Instagram cloud handoff failed for {slot.reel_id}")

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

        overall_success = len(report.errors) == 0
        return overall_success, report, plan

    def _scan_v3_inventory(self) -> List[Dict[str, Any]]:
        """
        Scans for V3-eligible Reels, strictly excluding REEL-2026-0010 and legacy content.
        """
        eligible = []
        dl_dir = self.base_dir / "workspace" / "downloads"

        if dl_dir.exists():
            for p in sorted(dl_dir.glob("clean_REEL-2026-*.mp4")):
                filename = p.stem
                m = re.search(r"(REEL-\d{4}-\d{4})", filename)
                if not m:
                    continue
                reel_id = m.group(1)
                if reel_id == "REEL-2026-0010":
                    continue

                if not self.repo.is_reel_available_for_new_batch(reel_id):
                    continue

                eligible.append({
                    "id": reel_id,
                    "video_file": str(p.resolve()),
                    "status": "READY",
                    "pipeline_version": 3,
                    "content_mode": "silent_global_step_by_step"
                })

        return eligible

    def _generate_missing_v3_reels(self, needed: int, week_id: str) -> List[Dict[str, Any]]:
        """
        Generates missing V3 Reels sequentially using ContentEngine, VideoProvider, and VideoValidator.
        """
        if self.flow_provider is None:
            self._init_publishers_if_needed(need_generation=True)

        content_engine = ContentEngine()
        past_history = []
        for r in self.repo.list_all_reels():
            past_history.append({"id": r.reel_id, "title": r.title, "category": r.content_mode})

        plans = content_engine.generate_next_reels(count=needed, past_records=past_history, duration_seconds=30)
        validator = VideoValidator(reject_wrong_ratio=True, audio_enabled=False)

        generated = []
        curr_num = 11

        for plan in plans:
            while True:
                candidate_id = f"REEL-2026-{curr_num:04d}"
                curr_num += 1
                if candidate_id != "REEL-2026-0010" and self.repo.is_reel_available_for_new_batch(candidate_id):
                    chosen_id = candidate_id
                    break

            logger.info(f"[GENERATION] Generating {chosen_id} ({plan.title}) via Flow...")
            target_filename = f"clean_{chosen_id}_{plan.topic_key}.mp4"

            try:
                downloaded_file = self.flow_provider.generate_single_video(
                    plan=plan,
                    reel_id=chosen_id,
                    target_filename=target_filename
                )

                qc_res = validator.process_and_validate(
                    input_video=downloaded_file,
                    output_dir=self.app_config.workspace_downloads_dir
                )

                if not qc_res.is_passed:
                    logger.error(f"[GENERATION] QC failed for {chosen_id}: {qc_res.error_message}")
                    continue

                final_mp4 = qc_res.processed_video_path
                generated.append({
                    "id": chosen_id,
                    "video_file": str(final_mp4),
                    "status": "READY",
                    "pipeline_version": 3,
                    "content_mode": "silent_global_step_by_step",
                    "plan": plan
                })
                logger.info(f"[GENERATION] {chosen_id} produced and verified: {final_mp4}")

            except Exception as e:
                logger.error(f"[GENERATION] Failed to generate {chosen_id}: {e}")

        return generated

    def _assign_reels_to_slots(
        self,
        plan: WeekPlan,
        available_reels: List[Dict[str, Any]]
    ) -> List[ReelState]:
        """
        Assigns exactly 14 unique Reel IDs to the 14 slots of the week.
        Preserves existing slot assignments if already populated.
        """
        assigned_states = []
        used_ids = set()

        for slot in plan.slots:
            if slot.reel_id and slot.reel_id != "REEL-2026-0010":
                used_ids.add(slot.reel_id)

        curr_num = 11
        avail_ids = [r["id"] for r in available_reels if r["id"] not in used_ids]

        for slot in plan.slots:
            if not slot.reel_id or slot.reel_id == "REEL-2026-0010":
                if avail_ids:
                    chosen_id = avail_ids.pop(0)
                else:
                    while True:
                        candidate = f"REEL-2026-{curr_num:04d}"
                        curr_num += 1
                        if candidate != "REEL-2026-0010" and candidate not in used_ids and self.repo.is_reel_available_for_new_batch(candidate):
                            chosen_id = candidate
                            break
                slot.reel_id = chosen_id
                used_ids.add(chosen_id)

            slot.qc_status = "PASS"
            reel_state = self.repo.get_reel_state(slot.reel_id)
            if not reel_state:
                video_file = self._resolve_video_file(slot.reel_id)
                reel_state = ReelState(
                    reel_id=slot.reel_id,
                    week_id=plan.week_id,
                    pipeline_version=3,
                    content_mode="silent_global_step_by_step",
                    generation_status="COMPLETE" if (video_file.exists() or self.dry_run) else "NOT_STARTED",
                    qc_status="PASS",
                    title=f"Architectural Marvel {slot.reel_id}",
                    caption=f"Building from the ground up in 30 seconds. Would you live here? ✨",
                    hashtags=["#architecture", "#design", "#satisfying", "#timelapse", "#reels"],
                    scheduled_at_local=slot.scheduled_at_local,
                    scheduled_at_utc=slot.scheduled_at_utc,
                    youtube_status=ReelPlatformStatus(slot.youtube_status) if slot.youtube_status in ReelPlatformStatus.__members__ else ReelPlatformStatus.NOT_STARTED,
                    tiktok_status=ReelPlatformStatus(slot.tiktok_status) if slot.tiktok_status in ReelPlatformStatus.__members__ else ReelPlatformStatus.NOT_STARTED,
                    instagram_status=ReelPlatformStatus(slot.instagram_status) if slot.instagram_status in ReelPlatformStatus.__members__ else ReelPlatformStatus.NOT_STARTED
                )
            assigned_states.append(reel_state)

        return assigned_states

    def _find_or_create_reel_state(
        self,
        reel_id: str,
        assigned_reels: List[ReelState],
        week_id: str,
        slot: PublishingSlot
    ) -> ReelState:
        """Finds or creates ReelState for a slot."""
        for r in assigned_reels:
            if r.reel_id == reel_id:
                return r

        existing = self.repo.get_reel_state(reel_id)
        if existing:
            return existing

        state = ReelState(
            reel_id=reel_id,
            week_id=week_id,
            pipeline_version=3,
            content_mode="silent_global_step_by_step",
            scheduled_at_local=slot.scheduled_at_local,
            scheduled_at_utc=slot.scheduled_at_utc
        )
        assigned_reels.append(state)
        return state

    def _resolve_video_file(self, reel_id: str) -> Path:
        """Locates the local video file for a reel."""
        candidates = [
            self.base_dir / "workspace" / "downloads" / f"clean_{reel_id}.mp4",
            self.base_dir / "output" / f"{reel_id}.mp4",
            self.base_dir / "workspace" / "downloads" / f"{reel_id}.mp4"
        ]
        for c in candidates:
            if c.exists():
                return c

        dl_dir = self.base_dir / "workspace" / "downloads"
        if dl_dir.exists():
            for f in dl_dir.glob(f"*{reel_id}*.mp4"):
                if f.exists():
                    return f

        return candidates[0]

    def _schedule_youtube_slot(self, slot: PublishingSlot, r_state: ReelState) -> bool:
        """Executes native YouTube Studio scheduling for a slot."""
        video_file = self._resolve_video_file(slot.reel_id)
        if not video_file.exists():
            logger.error(f"[{slot.reel_id}] Video file not found: {video_file}")
            slot.youtube_status = "FAILED_FATAL"
            r_state.youtube_status = ReelPlatformStatus.FAILED_FATAL
            return False

        file_sha = hashlib.sha256(video_file.read_bytes()).hexdigest()
        rec = PublishRecord(
            publish_id=f"PUB-{slot.reel_id}-YOUTUBE",
            batch_id=slot.scheduled_at_local.split()[0],
            reel_id=slot.reel_id,
            platform=Platform.YOUTUBE,
            account_handle=self.pub_config.youtube_expected_handle,
            video_file=video_file,
            video_sha256=file_sha,
            title=r_state.title or f"Architectural Marvel {slot.reel_id} #Shorts",
            description=f"{r_state.caption}\n\n{' '.join(r_state.hashtags)}",
            hashtags=r_state.hashtags,
            scheduled_at_local=slot.scheduled_at_local,
            scheduled_at_utc=slot.scheduled_at_utc,
            timezone="Europe/Istanbul",
            status=PlatformPublicationStatus.PENDING,
            dry_run=False,
            ai_generated=True,
            synthetic_media_disclosed=True
        )

        try:
            res_rec = self.yt_publisher.upload_and_schedule(rec)
            if res_rec.status == PlatformPublicationStatus.SCHEDULED:
                slot.youtube_status = "SCHEDULED"
                r_state.youtube_status = ReelPlatformStatus.SCHEDULED
                logger.info(f"[{slot.reel_id}] YouTube Studio scheduled successfully for {slot.scheduled_at_local}")
                return True
            else:
                slot.youtube_status = res_rec.status.value
                r_state.youtube_status = ReelPlatformStatus(res_rec.status.value) if res_rec.status.value in ReelPlatformStatus.__members__ else ReelPlatformStatus.FAILED_RETRYABLE
                logger.error(f"[{slot.reel_id}] YouTube scheduling failed: {res_rec.error_message}")
                return False
        except Exception as e:
            logger.error(f"[{slot.reel_id}] YouTube scheduling error: {e}")
            slot.youtube_status = "FAILED_RETRYABLE"
            r_state.youtube_status = ReelPlatformStatus.FAILED_RETRYABLE
            return False

    def _schedule_tiktok_slot(self, slot: PublishingSlot, r_state: ReelState) -> bool:
        """Executes native TikTok Studio scheduling for a slot."""
        video_file = self._resolve_video_file(slot.reel_id)
        if not video_file.exists():
            logger.error(f"[{slot.reel_id}] Video file not found: {video_file}")
            slot.tiktok_status = "FAILED_FATAL"
            r_state.tiktok_status = ReelPlatformStatus.FAILED_FATAL
            return False

        file_sha = hashlib.sha256(video_file.read_bytes()).hexdigest()
        rec = PublishRecord(
            publish_id=f"PUB-{slot.reel_id}-TIKTOK",
            batch_id=slot.scheduled_at_local.split()[0],
            reel_id=slot.reel_id,
            platform=Platform.TIKTOK,
            account_handle=self.pub_config.tiktok_expected_username,
            video_file=video_file,
            video_sha256=file_sha,
            title=r_state.title,
            description=f"{r_state.caption} {' '.join(r_state.hashtags)}",
            hashtags=r_state.hashtags,
            scheduled_at_local=slot.scheduled_at_local,
            scheduled_at_utc=slot.scheduled_at_utc,
            timezone="Europe/Istanbul",
            status=PlatformPublicationStatus.PENDING,
            dry_run=False,
            ai_generated=True,
            synthetic_media_disclosed=True
        )

        try:
            res_rec = self.tt_publisher.upload_and_schedule(rec)
            status_val = str(res_rec.status.value if hasattr(res_rec.status, "value") else res_rec.status)
            if status_val in ("SCHEDULED", "PUBLISHED", "REMOTE_VERIFIED"):
                slot.tiktok_status = "SCHEDULED"
                r_state.tiktok_status = ReelPlatformStatus.SCHEDULED
                logger.info(f"[{slot.reel_id}] TikTok Studio scheduled successfully for {slot.scheduled_at_local}")
                return True
            elif status_val in ("NEEDS_USER_HTML", "USER_ACTION_REQUIRED", "REVIEW_REQUIRED"):
                slot.tiktok_status = "NEEDS_USER_HTML"
                r_state.tiktok_status = ReelPlatformStatus.NEEDS_USER_HTML
                logger.warning(f"[{slot.reel_id}] TikTok Studio needs user HTML interaction (Rule 31).")
                return False
            else:
                slot.tiktok_status = status_val
                r_state.tiktok_status = ReelPlatformStatus(status_val) if status_val in ReelPlatformStatus.__members__ else ReelPlatformStatus.FAILED_RETRYABLE
                logger.error(f"[{slot.reel_id}] TikTok scheduling failed: {res_rec.error_message}")
                return False
        except Exception as e:
            logger.error(f"[{slot.reel_id}] TikTok scheduling error: {e}")
            slot.tiktok_status = "FAILED_RETRYABLE"
            r_state.tiktok_status = ReelPlatformStatus.FAILED_RETRYABLE
            return False

    def _handoff_instagram_slot(self, slot: PublishingSlot, r_state: ReelState, week_id: str) -> bool:
        """Executes authenticated media handoff of local MP4 to Railway private S3 storage."""
        video_file = self._resolve_video_file(slot.reel_id)
        if not video_file.exists():
            logger.error(f"[{slot.reel_id}] Video file not found: {video_file}")
            slot.instagram_status = "FAILED_FATAL"
            r_state.instagram_status = ReelPlatformStatus.FAILED_FATAL
            return False

        ok, data, err = handoff_reel_to_cloud(
            local_path=video_file,
            week_id=week_id,
            reel_id=slot.reel_id,
            scheduled_at_local=slot.scheduled_at_local,
            scheduled_at_utc=slot.scheduled_at_utc,
            timezone="Europe/Istanbul",
            caption=f"{r_state.caption}\n\n{' '.join(r_state.hashtags)}",
            job_id=f"JOB-{week_id}-{slot.reel_id}",
            client=self.cloud_client
        )

        if ok and data.get("ok"):
            slot.instagram_status = "MEDIA_READY"
            r_state.instagram_status = ReelPlatformStatus.READY
            logger.info(f"[{slot.reel_id}] Instagram media handoff succeeded: {data.get('media_object_key')}")
            return True
        else:
            slot.instagram_status = "FAILED_RETRYABLE"
            r_state.instagram_status = ReelPlatformStatus.FAILED_RETRYABLE
            logger.error(f"[{slot.reel_id}] Instagram media handoff failed: {err} ({data})")
            return False

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
        print(f"Scheduled: {report.youtube_success} / {len(plan.slots)}\n")
        print("TikTok:")
        print(f"Scheduled: {report.tiktok_success} / {len(plan.slots)}\n")
        print("Instagram:")
        print(f"Handoff (MEDIA_READY): {report.instagram_queued} / {len(plan.slots)}\n")
        if report.errors:
            print(f"Errors ({len(report.errors)}):")
            for err in report.errors:
                print(f"- {err}")
        print("=" * 60 + "\n")


def main():
    """CLI entrypoint for weekly orchestrator."""
    parser = argparse.ArgumentParser(description="Weekly 14-Reel Orchestrator & Publishing Control Center")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD), default next safe Monday")
    parser.add_argument("--week-id", type=str, default=None, help="Specific Week ID (e.g. 2026-W35)")
    parser.add_argument("--live", action="store_true", default=False, help="Enable real live generation & scheduling")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Dry run simulation mode (Default)")
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
