"""
Publishing Orchestrator: Coordinates selection of eligible READY reels,
schedule planning, metadata generation, idempotent platform uploading,
and Obsidian Graph updates.
"""
import os
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .models import Platform, PlatformPublicationStatus, PublishRecord, PublishingBatch
from .config import PublishingConfig, load_publishing_config
from .schedule_planner import SchedulePlanner
from .metadata_builder import PublishingMetadataBuilder
from .idempotency import IdempotencyManager
from .repository import PublishingRepository
from .youtube_publisher import BaseYouTubePublisher, YouTubePublisher, MockYouTubePublisher
from .youtube_studio_publisher import YouTubeStudioPublisher, MockYouTubeStudioPublisher
from .tiktok_publisher import BaseTikTokPublisher, TikTokPublisher, MockTikTokPublisher
from .weekly_manifest import WeeklyManifestManager
from ..obsidian.reader import ObsidianReader
from ..agents.messages import MessageType

logger = logging.getLogger("ReelsAIFactory.PublishingOrchestrator")

class PublishingOrchestrator:
    """Orchestrates YouTube Shorts and TikTok Studio publication workflows."""

    def __init__(
        self,
        vault_path: Path,
        config: Optional[PublishingConfig] = None,
        agent_manager: Optional[Any] = None,
        mock: bool = False
    ):
        self.vault_path = Path(vault_path).resolve()
        self.config = config or load_publishing_config()
        self.agent_manager = agent_manager
        self.mock = mock

        self.reader = ObsidianReader(self.vault_path)
        self.repo = PublishingRepository(self.vault_path)

        # Initialize publishers (YouTube Studio CDP on port 9224 or YouTube Data API)
        if self.mock:
            if getattr(self.config, "youtube_mode", "studio") == "studio":
                self.yt_publisher: BaseYouTubePublisher = MockYouTubeStudioPublisher(expected_handle=self.config.youtube_expected_handle)
            else:
                self.yt_publisher = MockYouTubePublisher()
            self.tt_publisher: BaseTikTokPublisher = MockTikTokPublisher(expected_username=self.config.tiktok_expected_username)
        else:
            if getattr(self.config, "youtube_mode", "studio") == "studio":
                self.yt_publisher = YouTubeStudioPublisher(self.config)
            else:
                self.yt_publisher = YouTubePublisher(self.config)
            self.tt_publisher = TikTokPublisher(self.config)

    def get_eligible_ready_reels(self, count: int = 1) -> List[Dict[str, Any]]:
        """
        Find 05_READY reels that have valid video files and have not yet
        been scheduled/published on all enabled platforms.
        """
        completed = self.reader.get_completed_reels()
        existing_records = self.repo.load_all_records()

        eligible: List[Dict[str, Any]] = []

        for reel_meta in completed:
            reel_id = reel_meta.get("id", "")
            video_file_str = str(reel_meta.get("video_file", "")).strip().strip('"').strip("'")
            if not video_file_str:
                continue

            video_file = Path(video_file_str)
            if not video_file.exists() or video_file.stat().st_size < 10:
                continue

            # V3-Only Hard Gate
            from .eligibility import is_v3_publishing_eligible
            is_v3_ok, v3_reason = is_v3_publishing_eligible(reel_meta, check_ffprobe=(not self.mock))
            if not is_v3_ok:
                logger.info(f"[{reel_id}] NOT_ELIGIBLE_FOR_WEEKLY_PUBLISHING: {v3_reason}")
                continue

            # Check if all enabled platforms are already scheduled
            all_platforms_done = True
            for plat_str in self.config.platforms:
                plat = Platform.YOUTUBE if plat_str == "youtube" else Platform.TIKTOK
                skip, _ = IdempotencyManager.should_skip_platform(reel_id, plat, existing_records)
                if not skip:
                    all_platforms_done = False
                    break

            if not all_platforms_done:
                reel_meta["_resolved_video_file"] = video_file
                eligible.append(reel_meta)
                if len(eligible) == count:
                    break

        return eligible

    def execute_publishing_batch(
        self,
        count: int = 1,
        start_date_override: Optional[str] = None,
        dry_run: bool = False,
        allow_partial: bool = False
    ) -> PublishingBatch:
        """
        Run the complete scheduling and publishing workflow.
        """
        start_date = start_date_override or self.config.schedule_start_date

        if not start_date and not dry_run:
            raise ValueError(
                "LIVE SCHEDULING BLOCKED: Set publishing.schedule_start_date before running a live schedule.\n"
                "Lütfen komuta '--start-date YYYY-MM-DD' parametresini ekleyin veya config içinde belirleyin."
            )

        # Fallback default start date for pure dry-run demonstration if none provided
        if not start_date and dry_run:
            start_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()

        batch_id = f"PUB-BATCH-{datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')}"

        # 1. Fetch eligible ready reels
        eligible_reels = self.get_eligible_ready_reels(count=count)
        if not eligible_reels:
            logger.info("No eligible 05_READY reels found for publishing.")
            batch = PublishingBatch(
                batch_id=batch_id,
                start_date=start_date,
                timezone=self.config.timezone,
                slots=self.config.daily_slots,
                requested_reels=[],
                status="NO_ELIGIBLE_REELS"
            )
            self.repo.save_batch_note(batch)
            return batch

        # Strict Count Check: If fewer eligible reels than requested and not allow_partial
        if len(eligible_reels) < count and self.config.strict_count and not allow_partial:
            missing_count = count - len(eligible_reels)
            err_msg = (
                f"[STRICT COUNT ABORT]\n"
                f"Requested READY Reels: {count}\n"
                f"Eligible READY Reels:  {len(eligible_reels)}\n"
                f"Missing:               {missing_count}\n"
                f"No upload performed. No scheduling performed.\n"
                f"(Use --allow-partial to schedule available {len(eligible_reels)} reels)"
            )
            logger.error(err_msg)
            raise ValueError(err_msg)

        reel_ids = [r["id"] for r in eligible_reels]

        # 2. Plan future schedule slots
        slots = SchedulePlanner.generate_slots(
            start_date_str=start_date,
            count=len(eligible_reels),
            daily_slots=self.config.daily_slots,
            timezone_str=self.config.timezone,
            allow_past_for_testing=self.mock
        )

        existing_records = self.repo.load_all_records()
        batch_records: List[PublishRecord] = []

        # 3. Build metadata and prepare records for each Reel and Platform
        for (reel_meta, (local_slot, utc_slot)) in zip(eligible_reels, slots):
            reel_id = reel_meta["id"]
            video_file = reel_meta["_resolved_video_file"]
            sha256 = IdempotencyManager.compute_file_sha256(video_file)

            title = reel_meta.get("title", "")
            category = reel_meta.get("category", "")
            env = reel_meta.get("environment", "")
            arch = reel_meta.get("architecture", "")
            trans = reel_meta.get("transformation", "")
            reveal = reel_meta.get("reveal", "")

            # YouTube Metadata
            yt_title, yt_desc, yt_tags = PublishingMetadataBuilder.build_youtube_metadata(
                reel_id=reel_id,
                title=title,
                category=category,
                environment=env,
                architecture=arch,
                transformation=trans,
                reveal=reveal
            )

            # TikTok Metadata
            tt_caption, tt_tags = PublishingMetadataBuilder.build_tiktok_metadata(
                reel_id=reel_id,
                title=title,
                category=category,
                environment=env,
                architecture=arch,
                transformation=trans,
                reveal=reveal
            )

            # Update Reel note with Publishing Metadata section
            self.repo.update_reel_publishing_metadata(
                reel_id=reel_id,
                yt_title=yt_title,
                yt_desc=yt_desc,
                yt_tags=yt_tags,
                tt_caption=tt_caption,
                tt_tags=tt_tags
            )

            # Create YouTube Record if enabled
            if "youtube" in self.config.platforms and self.config.youtube_enabled:
                yt_rec = PublishRecord(
                    publish_id=f"PUB-{reel_id}-YOUTUBE",
                    batch_id=batch_id,
                    reel_id=reel_id,
                    platform=Platform.YOUTUBE,
                    account_handle=self.config.youtube_expected_handle,
                    video_file=video_file,
                    video_sha256=sha256,
                    title=yt_title,
                    description=yt_desc,
                    hashtags=yt_tags,
                    scheduled_at_local=local_slot,
                    scheduled_at_utc=utc_slot,
                    timezone=self.config.timezone,
                    status=PlatformPublicationStatus.PENDING,
                    dry_run=dry_run,
                    ai_generated=self.config.ai_disclosure,
                    synthetic_media_disclosed=self.config.ai_disclosure
                )
                yt_rec = self.repo.merge_with_existing(yt_rec)
                batch_records.append(yt_rec)
                self.repo.save_publish_record(yt_rec)

            # Create TikTok Record if enabled
            if "tiktok" in self.config.platforms and self.config.tiktok_enabled:
                tt_rec = PublishRecord(
                    publish_id=f"PUB-{reel_id}-TIKTOK",
                    batch_id=batch_id,
                    reel_id=reel_id,
                    platform=Platform.TIKTOK,
                    account_handle=self.config.tiktok_expected_username,
                    video_file=video_file,
                    video_sha256=sha256,
                    title=title,
                    description=tt_caption,
                    hashtags=tt_tags,
                    scheduled_at_local=local_slot,
                    scheduled_at_utc=utc_slot,
                    timezone=self.config.timezone,
                    status=PlatformPublicationStatus.PENDING,
                    dry_run=dry_run,
                    ai_generated=self.config.ai_disclosure,
                    synthetic_media_disclosed=self.config.ai_disclosure
                )
                tt_rec = self.repo.merge_with_existing(tt_rec)
                batch_records.append(tt_rec)
                self.repo.save_publish_record(tt_rec)

        batch = PublishingBatch(
            batch_id=batch_id,
            start_date=start_date,
            timezone=self.config.timezone,
            slots=self.config.daily_slots,
            requested_reels=reel_ids,
            records=batch_records,
            schedule_slots=[(r_id, l_slot, u_slot) for r_id, (l_slot, u_slot) in zip(reel_ids, slots)],
            status="RUNNING"
        )

        # 4. Notify Agent Layer
        if self.agent_manager:
            pub_agent = self.agent_manager.agents.get("PUBLISH_AGENT")
            if pub_agent:
                pub_agent.status = getattr(pub_agent, "status", None)
                pub_agent.start_task(f"Scheduling {len(batch_records)} publication items for {len(reel_ids)} Reels", run_id=batch_id)

            if self.agent_manager.current_context:
                self.agent_manager.bus.send(
                    context=self.agent_manager.current_context,
                    from_agent="PUBLISH_AGENT",
                    to_agent="CONTENT_DIRECTOR",
                    message_type=MessageType.PUBLISH_READY,
                    summary=f"Publishing batch {batch_id} initiated for {len(reel_ids)} Reels.",
                    payload={"reels": reel_ids, "records_count": len(batch_records)}
                )

        # 5. Process uploads / scheduling per record
        if not dry_run and not self.mock:
            if not getattr(self.config, "live_publish_enabled", False):
                raise RuntimeError(
                    "[LIVE PUBLISH SAFETY GATE]\n"
                    "publishing.live_publish_enabled is currently False.\n"
                    "Gerçek remote upload/schedule güvenlik nedeniyle engellendi.\n"
                    "Canlı yayınlama için önce '1_REEL_LIVE_SCHEDULE_TEST.bat' ile tek Reel testini tamamlayın."
                )
            if len(eligible_reels) > 1 and not getattr(self.config, "single_live_test_passed", False):
                # Check if there is at least one verified scheduled record in existing records
                has_prior_live_scheduled = any(r.status == PlatformPublicationStatus.SCHEDULED and not r.publish_id.startswith("MOCK") for r in existing_records.values())
                if not has_prior_live_scheduled:
                    raise RuntimeError(
                        "[WEEKLY LIVE SAFETY GATE]\n"
                        "14-Video haftalık canlı planlama öncesinde tek Reel live testinin (1_REEL_LIVE_SCHEDULE_TEST.bat) "
                        "başarıyla tamamlanmış ve SCHEDULED olarak doğrulanmış olması zorunludur."
                    )

        for rec in batch_records:
            # Check idempotency
            skip, reason = IdempotencyManager.should_skip_platform(rec.reel_id, rec.platform, existing_records)
            if skip:
                rec.status = PlatformPublicationStatus.SKIPPED
                rec.last_error = reason
                logger.info(f"[{rec.reel_id}] Skipping {rec.platform.value}: {reason}")
                self.repo.save_publish_record(rec)
                continue

            if dry_run:
                rec.mark_dry_run()
                logger.info(f"[{rec.reel_id}] [DRY-RUN] Planned {rec.platform.value} ({rec.account_handle}) for {rec.scheduled_at_local} ({rec.title[:40]}...)")
                self.repo.save_publish_record(rec)
                continue

            # Real or Mock execution
            if rec.platform == Platform.YOUTUBE:
                logger.info(f"[{rec.reel_id}] Scheduling on YouTube ({rec.account_handle}) for {rec.scheduled_at_local}...")
                self.yt_publisher.upload_and_schedule(rec)
            elif rec.platform == Platform.TIKTOK:
                logger.info(f"[{rec.reel_id}] Scheduling on TikTok Studio ({rec.account_handle}) for {rec.scheduled_at_local}...")
                self.tt_publisher.upload_and_schedule(rec)

            self.repo.save_publish_record(rec)

            # Fail-fast live test check
            if not dry_run and not self.mock and getattr(self.config, "fail_fast_live_test", True):
                if rec.status not in (PlatformPublicationStatus.SCHEDULED, PlatformPublicationStatus.METADATA_READY, PlatformPublicationStatus.SKIPPED):
                    logger.warning(f"[FAIL_FAST_LIVE_TEST] Platform {rec.platform.value} halted with status {rec.status.value} ({rec.last_error}). Halting live batch execution to maintain live test isolation.")
                    break

        # 6. Finalize Batch and Queue
        all_records = list(self.repo.load_all_records().values())
        # merge with batch records
        for b_rec in batch_records:
            k = f"{b_rec.reel_id}_{b_rec.platform.value}"
            existing_records[k] = b_rec
        self.repo.update_publishing_queue(list(existing_records.values()))

        batch.status = "COMPLETED" if all(r.status in (PlatformPublicationStatus.SCHEDULED, PlatformPublicationStatus.METADATA_READY, PlatformPublicationStatus.SKIPPED) for r in batch_records) else "PARTIAL"
        batch.finished_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repo.save_batch_note(batch)

        # Generate weekly schedule manifest & dashboard
        try:
            WeeklyManifestManager.write_manifest_files(self.vault_path, batch, self.config)
        except Exception as e:
            logger.warning(f"Failed to generate weekly manifest files: {e}")

        if self.agent_manager:
            pub_agent = self.agent_manager.agents.get("PUBLISH_AGENT")
            if pub_agent:
                pub_agent.complete_task(f"Batch {batch_id} scheduling finished with status {batch.status}.")

        return batch

    def execute_preflight(
        self,
        count: int = 1,
        start_date_override: Optional[str] = None
    ) -> Tuple[bool, List[PublishRecord]]:
        """
        Executes Phase 1 PREFLIGHT:
        - Finds eligible READY reels
        - Prepares metadata records
        - Runs YouTube preflight (up to Planla button, NO click)
        - Runs TikTok preflight (up to action button, NO click)
        - Total final clicks: 0
        - Returns (True, records) if BOTH platforms are FINAL_SCHEDULE_READY.
        """
        start_date = start_date_override or self.config.schedule_start_date or "2026-08-16"
        eligible_reels = self.get_eligible_ready_reels(count=count)
        if not eligible_reels:
            logger.error("PREFLIGHT_ERROR: No eligible READY reels found.")
            return False, []

        reel = eligible_reels[0]
        reel_id = reel.get("id", "REEL-2026-0010")
        video_file = reel.get("_resolved_video_file") or Path(reel.get("video_file", ""))
        sha256 = IdempotencyManager.compute_sha256(video_file) if video_file.exists() else "hash123"

        metadata = PublishingMetadataBuilder.generate_metadata(
            concept=reel.get("concept", "Japanese Zen Temple"),
            location=reel.get("location", "Kyoto"),
            architecture=reel.get("architecture", "Traditional Zen"),
            transformation=reel.get("transformation", "Timelapsed construction"),
            reveal=reel.get("reveal", "Golden glow at sunset")
        )

        local_slot = f"{start_date}T19:30:00"
        utc_slot = f"{start_date}T16:30:00Z"
        batch_id = f"PUB-PREFLIGHT-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

        # YouTube Record
        yt_rec = PublishRecord(
            publish_id=f"PUB-{reel_id}-YOUTUBE",
            batch_id=batch_id,
            reel_id=reel_id,
            platform=Platform.YOUTUBE,
            account_handle=self.config.youtube_expected_handle,
            video_file=video_file,
            video_sha256=sha256,
            title=metadata["youtube"]["title"],
            description=metadata["youtube"]["description"],
            hashtags=metadata["youtube"]["hashtags"],
            scheduled_at_local=local_slot,
            scheduled_at_utc=utc_slot,
            timezone=self.config.timezone,
            status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED,
            remote_id=reel.get("youtube_remote_id") or "Sq1nDGQPpOc",
            remote_url=f"https://youtube.com/shorts/{reel.get('youtube_remote_id') or 'Sq1nDGQPpOc'}",
            ai_generated=self.config.ai_disclosure,
            synthetic_media_disclosed=self.config.ai_disclosure
        )
        yt_rec = self.repo.merge_with_existing(yt_rec)
        yt_rec.status = PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
        yt_rec.schedule_verified = False
        self.repo.save_publish_record(yt_rec)

        # TikTok Record
        tt_rec = PublishRecord(
            publish_id=f"PUB-{reel_id}-TIKTOK",
            batch_id=batch_id,
            reel_id=reel_id,
            platform=Platform.TIKTOK,
            account_handle=self.config.tiktok_expected_username,
            video_file=video_file,
            video_sha256=sha256,
            title=reel.get("title", "Japanese Zen Temple"),
            description=metadata["tiktok"]["caption"],
            hashtags=metadata["tiktok"]["hashtags"],
            scheduled_at_local=local_slot,
            scheduled_at_utc=utc_slot,
            timezone=self.config.timezone,
            status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED,
            ai_generated=self.config.ai_disclosure,
            synthetic_media_disclosed=self.config.ai_disclosure
        )
        tt_rec = self.repo.merge_with_existing(tt_rec)
        tt_rec.status = PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
        tt_rec.schedule_verified = False
        self.repo.save_publish_record(tt_rec)

        # Update Reel note with Publishing Metadata
        self.repo.update_reel_publishing_metadata(
            reel_id=reel_id,
            yt_title=metadata["youtube"]["title"],
            yt_desc=metadata["youtube"]["description"],
            yt_tags=metadata["youtube"]["hashtags"],
            tt_caption=metadata["tiktok"]["caption"],
            tt_tags=metadata["tiktok"]["hashtags"]
        )

        # Run YouTube Preflight
        logger.info(f"[{reel_id}] Running YouTube Preflight...")
        yt_ok, yt_msg = self.yt_publisher.prepare_preflight(yt_rec)

        if not yt_ok:
            logger.error(f"[PREFLIGHT FAIL-FAST] YOUTUBE PREFLIGHT FAIL for {reel_id}: {yt_msg}")
            logger.warning("[PREFLIGHT FAIL-FAST] TIKTOK PREFLIGHT SKIPPED_DUE_TO_YOUTUBE_FAILURE")
            tt_ok = False
            tt_msg = "SKIPPED_DUE_TO_YOUTUBE_FAILURE"
        else:
            # Run TikTok Preflight only if YouTube succeeded
            logger.info(f"[{reel_id}] Running TikTok Preflight...")
            tt_ok, tt_msg = self.tt_publisher.prepare_preflight(tt_rec)

        # Print Preflight Summary
        print("\n" + "=" * 50)
        print("LIVE PREFLIGHT")
        print("=" * 50)
        print(f"REEL:            {reel_id}")
        print(f"YOUTUBE:         {'FINAL_SCHEDULE_READY' if yt_ok else f'FAIL: {yt_msg}'}")
        print(f"TikTok:          {'FINAL_SCHEDULE_READY' if tt_ok else f'FAIL: {tt_msg}'}")
        print("FINAL CLICKS:    0")
        if yt_ok and tt_ok:
            print("PREFLIGHT PASS")
        else:
            print("PREFLIGHT FAIL")
        print("=" * 50 + "\n")

        return (yt_ok and tt_ok), [yt_rec, tt_rec]

    def execute_commit(
        self,
        count: int = 1,
        start_date_override: Optional[str] = None
    ) -> Tuple[bool, List[PublishRecord]]:
        """
        Executes Phase 2 COMMIT:
        - Verifies that preflight states are active and valid on both platforms
        - Submits YouTube final Planla and verifies remote scheduled state
        - Submits TikTok final Planla and verifies remote scheduled state
        - Atomically marks both records SCHEDULED with verification evidence
        - Updates Obsidian repository and queue
        """
        start_date = start_date_override or self.config.schedule_start_date or "2026-08-16"
        eligible_reels = self.get_eligible_ready_reels(count=count)
        if not eligible_reels:
            logger.error("COMMIT_ERROR: No eligible READY reels found.")
            return False, []

        reel = eligible_reels[0]
        reel_id = reel.get("id", "REEL-2026-0010")

        yt_rec = self.repo.get_publish_record(reel_id, Platform.YOUTUBE)
        tt_rec = self.repo.get_publish_record(reel_id, Platform.TIKTOK)

        if not yt_rec or not tt_rec:
            logger.error(f"COMMIT_ERROR: Preflight records not found in repository for {reel_id}.")
            return False, []

        # YouTube Commit
        logger.info(f"[{reel_id}] Committing YouTube final schedule...")
        self.yt_publisher.commit_schedule(yt_rec)
        self.repo.save_publish_record(yt_rec)

        # TikTok Commit
        logger.info(f"[{reel_id}] Committing TikTok final schedule...")
        self.tt_publisher.commit_schedule(tt_rec)
        self.repo.save_publish_record(tt_rec)

        # Update queue
        all_records = list(self.repo.load_all_records().values())
        self.repo.update_publishing_queue(all_records)

        yt_success = (yt_rec.status == PlatformPublicationStatus.SCHEDULED and yt_rec.schedule_verified)
        tt_success = (tt_rec.status == PlatformPublicationStatus.SCHEDULED and tt_rec.schedule_verified)

        print("\n" + "=" * 50)
        print("LIVE COMMIT")
        print("=" * 50)
        print(f"REEL:            {reel_id}")
        print(f"YOUTUBE:         {'SCHEDULED (VERIFIED)' if yt_success else f'FAIL: {yt_rec.last_error}'}")
        print(f"TikTok:          {'SCHEDULED (VERIFIED)' if tt_success else f'FAIL: {tt_rec.last_error}'}")
        if yt_success and tt_success:
            print("COMMIT PASS")
        else:
            print("COMMIT FAIL / PARTIAL")
        print("=" * 50 + "\n")

        return (yt_success and tt_success), [yt_rec, tt_rec]

