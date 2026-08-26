"""
Simple Weekly Pipeline -- deterministic, sequential, single-direction production entrypoint.

Replaces automation.weekly_orchestrator as the LIVE production entrypoint. Does not
reimplement Flow generation, YouTube/TikTok publishing, or Instagram media handoff --
it calls the existing, working modules one Reel at a time, in a fixed phase order, and
never lets a later phase start before the previous one is fully (14/14) done:

    PLAN -> GENERATE -> VALIDATE -> LOCK -> YOUTUBE -> TIKTOK -> INSTAGRAM -> DONE

Content plan (workspace/batches/<week_id>/manifest.json) becomes immutable once LOCKED.
Platform publishing status (workspace/batches/<week_id>/progress.json) is tracked
separately and can never modify the manifest. See .claude/skills/weekly-resume-manager
and .claude/skills/production-media-guardian for the underlying safety contracts this
pipeline depends on -- it does not re-derive them.
"""
import argparse
import datetime
import hashlib
import os
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ReelsAIFactory.SimpleWeeklyPipeline")

from automation.brands import Brand, get_brand
from automation.config import load_config, AppConfig
from automation.publishing.config import PublishingConfig, load_publishing_config
from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord
from automation.publishing.youtube_studio_publisher import (
    BaseYouTubePublisher,
    YouTubeStudioPublisher,
    MockYouTubeStudioPublisher,
)
from automation.publishing.tiktok_publisher import (
    BaseTikTokPublisher,
    TikTokPublisher,
    MockTikTokPublisher,
)
from automation.publishing.instagram_web_publisher import (
    BaseInstagramWebPublisher,
    InstagramWebPublisher,
    MockInstagramWebPublisher,
)
from automation.publishing.eligibility import is_live_production_eligible, HARD_EXCLUDED_REEL_IDS
from automation.publishing.preflight_gate import run_pre_publish_hard_gate, verify_reel_id_invariant, is_placeholder_metadata
from automation.publishing.repository import PublishingRepository
from automation.publishing.metadata_builder import PublishingMetadataBuilder
from automation.flow.generator import GoogleFlowWebProvider, MockVideoProvider, VideoProvider
from automation.content.concepts import CATEGORIES
from automation.content.content_modes import (
    CUTAWAY_REVEAL_STORY,
    NARRATIVE_AMBIENT_STORY,
    SILENT_STEP_BY_STEP,
    is_live_eligible_mode,
    requires_audio,
    HIDDEN_BUILD_STORY,
    LIVE_ELIGIBLE_CONTENT_MODES,
)
from automation.content.engine import ContentEngine
from automation.content.prompt_engine import PromptEngine, ReelConceptPlan
from automation.content.story_concepts import STORY_CONCEPTS
from automation.content.hidden_build_concepts import HIDDEN_BUILD_CONCEPTS
from automation.content.cutaway_concepts import CUTAWAY_CONCEPTS
from automation.quality.validator import VideoValidator
from automation.media_handoff import handoff_reel_to_cloud
from automation.local_worker_cloud_client import LocalWorkerCloudClient
from automation.orchestration.batch_manifest import (
    BatchReel,
    BatchManifest,
    BatchRepository,
)
from automation.orchestration.state_repository import StateRepository
from automation.orchestration.models import ReelState, ReelProvenance
from automation.orchestration.slot_generator import (
    generate_14_slot_week_plan,
    calculate_next_safe_week_start,
    generate_week_id,
    get_timezone,
)
from automation.orchestration.obsidian_mirror import ObsidianControlCenter, DEFAULT_VAULT_PATH

# The two daily slots, in order. Defined once so the planner and the start-date rule
# below can never drift apart about when a day's first slot is.
DAILY_SLOT_TIMES = ("19:30", "22:00")

# How much room a same-day start must leave before that first slot. Generating a full
# week of 14 Reels took 49 minutes on 2026-08-21, so six hours is generous; a day whose
# first slot is nearer than this starts tomorrow instead, rather than risk scheduling
# into a moment that has already passed by the time publishing begins.
SAME_DAY_START_LEAD_HOURS = 6

PLATFORM_SUCCESS_STATUSES = ("SCHEDULED", "PUBLISHED", "REMOTE_VERIFIED")

# Remote ids that identify a platform's state rather than one particular video.
# TikTok's scheduler hands back no per-post id, so the publisher records a fixed marker
# instead; every Reel of the week carries the same one BY DESIGN. Reading that as a
# collision would stop TikTok on its second Reel every single week, with a
# REEL_ID_MEDIA_MISMATCH naming two Reels that are both perfectly scheduled.
NON_IDENTIFYING_REMOTE_IDS = frozenset({"tiktok_scheduled_post"})

# How Instagram gets its Reels. Exactly one of these runs per Reel -- running both would
# schedule the post through the composer AND hand the same media to the cloud worker,
# which publishes it again when its moment arrives. Two copies of every Reel.
#
#   "web"   -- drive instagram.com's native scheduler; the post appears in the account's
#              scheduled queue immediately, like YouTube and TikTok. Ends at SCHEDULED.
#   "cloud" -- upload to S3 and hand off to the Railway worker, which publishes at the
#              scheduled moment via the Graph API. Ends at MEDIA_READY.
INSTAGRAM_DELIVERY_WEB = "web"
INSTAGRAM_DELIVERY_CLOUD = "cloud"
INSTAGRAM_DELIVERY_MODES = (INSTAGRAM_DELIVERY_WEB, INSTAGRAM_DELIVERY_CLOUD)

# "This Reel already reached Instagram", whichever route delivered it. Both routes' end
# states count, always -- the delivery mode chooses what to do with NEW work, never how
# to read work that is already done.
#
# Reading this per-mode was a real bug: with the web route selected, a week delivered via
# the cloud (ending at MEDIA_READY) read as unfinished, so the pipeline resumed it and
# scheduled all 14 already-delivered Reels a second time through the composer.
# SUBMITTED_UNVERIFIED: 'Planla' was pressed, the post is almost certainly on the account,
# only the confirmation dialog was not read in time. It is terminal on purpose -- a retry
# would schedule the same video twice, and this system may not delete the extra copy.
# The end-of-run summary flags it for a human look instead.
INSTAGRAM_TERMINAL_STATUSES = ("MEDIA_READY", "SUBMITTED_UNVERIFIED") + PLATFORM_SUCCESS_STATUSES

# The submit went through but the confirmation read-back was inconclusive. The video is
# very likely correctly scheduled on the platform, so halting the whole week here does
# more harm than good -- record it, keep going, and let the end-of-run summary flag it
# for a human look. (2026-08-17: a Short WAS scheduled correctly but verification looked
# at the wrong Studio tab and stopped all 14 Reels on a false negative.)
SOFT_FAILURE_STATUSES = ("SCHEDULE_RESUME_REQUIRED", "UPLOADED_DRAFT", "REVIEW_REQUIRED")

# The browser/session itself is broken. Continuing would cascade the same failure into
# every remaining Reel, so this stops the current platform.
HARD_FAILURE_STATUSES = ("ACCOUNT_MISMATCH", "AUTH_REQUIRED", "NEEDS_USER_HTML")

# Statuses that prove a file already went up, whether or not its remote id was ever read.
# A rebuilt PublishRecord must carry this, because the publisher decides between "resume
# the existing draft" and "upload from scratch" on exactly that evidence.
#
# 2026-08-21: it did not. _build_publish_record hardcoded PENDING and derived
# upload_started from remote_id alone, so seven Reels whose id capture failed looked
# untouched on retry and were uploaded again -- twice, once per pass of the 30-minute
# hold. Fourteen planned Reels became twenty-eight videos on a live channel.
UPLOAD_ALREADY_ATTEMPTED_STATUSES = (
    "UPLOAD_ATTEMPTED",
    "UPLOADED_DRAFT",
    "SCHEDULE_RESUME_REQUIRED",
    "SCHEDULING_UNAVAILABLE",
    "REVIEW_REQUIRED",
    "SUBMITTED_UNVERIFIED",
) + PLATFORM_SUCCESS_STATUSES


class PhaseResult:
    """Outcome of running one phase. `success=True` means the phase is fully (14/14) done."""

    def __init__(self, success: bool, phase: str, message: str, detail: Optional[Dict[str, Any]] = None):
        self.success = success
        self.phase = phase
        self.message = message
        self.detail = detail or {}


class SimpleWeeklyPipeline:
    """
    Deterministic sequential weekly production pipeline. One video at a time, one
    platform phase at a time, fail-fast within a phase, never runs backwards.
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        vault_path: Optional[Path] = None,
        dry_run: bool = True,
        week_id: Optional[str] = None,
        start_date: Optional[datetime.date] = None,
        flow_provider: Optional[VideoProvider] = None,
        yt_publisher: Optional[BaseYouTubePublisher] = None,
        tt_publisher: Optional[BaseTikTokPublisher] = None,
        cloud_client: Optional[LocalWorkerCloudClient] = None,
        stuck_wait_minutes: int = 30,
        stuck_retry_seconds: int = 300,
        content_mode: Optional[str] = None,
        instagram_delivery: Optional[str] = None,
        ig_web_publisher: Optional[BaseInstagramWebPublisher] = None,
        brand: Optional[Brand] = None,
    ):
        self.base_dir = (base_dir or Path(".").resolve())
        self.dry_run = dry_run
        self.week_id = week_id
        self.start_date = start_date
        # Which channel this run belongs to. Everything brand-specific -- ids, accounts,
        # browsers, content mode -- comes from here, and the default brand reproduces the
        # pre-brand behaviour exactly.
        self.brand = brand or get_brand()

        # Only used when PLAN creates a fresh manifest. A resumed manifest keeps the mode
        # it was locked with, so a rerun can never silently re-mode a week mid-flight.
        # Falling back to the brand's own mode means a brand cannot be run in another
        # brand's format by forgetting a flag. Resolved before validation so the fallback
        # is what gets validated.
        self.content_mode = content_mode or self.brand.content_mode
        if not is_live_eligible_mode(self.content_mode):
            raise ValueError(f"Unknown content_mode '{self.content_mode}' -- register it in automation.content.content_modes first.")

        instagram_delivery = instagram_delivery or self.brand.instagram_delivery
        if instagram_delivery not in INSTAGRAM_DELIVERY_MODES:
            raise ValueError(
                f"Unknown instagram_delivery '{instagram_delivery}' -- expected one of {INSTAGRAM_DELIVERY_MODES}."
            )
        self.instagram_delivery = instagram_delivery
        # How long to hold a stuck platform for a manual fix before moving on, and how
        # often to retry inside that window. Tests set these to 0 to skip the wait.
        self.stuck_wait_minutes = stuck_wait_minutes
        self.stuck_retry_seconds = stuck_retry_seconds

        self.batch_repo = BatchRepository(self.base_dir)
        self.state_repo = StateRepository(self.base_dir)
        # Read-only here: the publishers own this store. The pipeline consults it only to
        # notice when it disagrees with progress.json -- see _report_state_divergence.
        self.pub_repo = PublishingRepository(self.base_dir)
        self.obsidian = ObsidianControlCenter(vault_path or DEFAULT_VAULT_PATH)

        try:
            self.app_config = load_config(base_dir=self.base_dir)
        except Exception:
            self.app_config = AppConfig(
                vault_path=vault_path or DEFAULT_VAULT_PATH,
                output_path=self.base_dir / "output",
                chrome_profile_dir=self.base_dir / "workspace" / "chrome-profile",
                workspace_downloads_dir=self.base_dir / "workspace" / "downloads",
            )

        try:
            self.pub_config = self.brand.apply_to_publishing_config(
                load_publishing_config(base_dir=self.base_dir)
            )
        except Exception:
            self.pub_config = self.brand.apply_to_publishing_config(PublishingConfig())

        # Injected for tests / explicit wiring. Never eagerly constructed here -- each
        # phase lazily builds only the client(s) it needs, so GENERATE never imports a
        # publisher and YOUTUBE never touches the Flow provider (platform isolation).
        self.flow_provider = flow_provider
        self.yt_publisher = yt_publisher
        self.tt_publisher = tt_publisher
        self.cloud_client = cloud_client
        self.ig_web_publisher = ig_web_publisher

    # =========================================================================
    # PHASE 0: PLAN (manifest creation, Reel ID allocation)
    # =========================================================================

    def _allocate_reel_ids(self, count: int) -> List[str]:
        """
        Monotonic, deterministic, never-reused Reel ID allocation. Checks every place a
        Reel ID could already exist: other batch manifests, persisted ReelState records,
        and real files on disk. HARD_EXCLUDED_REEL_IDS (mock/diagnostic) are permanent.
        """
        used = set(HARD_EXCLUDED_REEL_IDS)

        if self.batch_repo.batches_dir.exists():
            for d in self.batch_repo.batches_dir.iterdir():
                if not d.is_dir():
                    continue
                m = self.batch_repo.load_manifest(d.name)
                if m:
                    used.update(m.reel_ids())

        for r in self.state_repo.list_all_reels():
            used.add(r.reel_id)

        dl_dir = self.base_dir / "workspace" / "downloads"
        if dl_dir.exists():
            for f in dl_dir.glob("*REEL-*.mp4"):
                m = re.search(r"(REEL-\d{4}-\d{4})", f.name)
                if m:
                    used.add(m.group(1))

        allocated: List[str] = []
        # The second brand starts its numbering at 1: its ids carry a prefix, so they can
        # never collide with the original series regardless of where that has reached.
        num = 11 if not self.brand.id_prefix else 1
        while len(allocated) < count:
            candidate = self.brand.reel_id(num)
            num += 1
            if candidate not in used:
                allocated.append(candidate)
                used.add(candidate)
        return allocated

    def _is_batch_finished(self, manifest: BatchManifest) -> bool:
        """
        A batch is done when it is LOCKED and every platform this brand publishes to is
        complete.

        Only this brand's platforms count. A platform that is switched off is not a gap to
        be filled later by this check -- but switching it back on makes past weeks read as
        unfinished again, so the next run completes them on that platform alone.
        """
        if manifest.status != "LOCKED" or not self.all_generated(manifest):
            return False
        reel_ids = manifest.reel_ids()
        return all(
            self.all_platform_done(manifest.week_id, reel_ids, p)
            for p in self.brand.platforms
        )

    def _find_unfinished_week_id(self) -> Optional[str]:
        """
        Most recent batch that still has work left, or None if everything is finished.

        Without this, running the BAT with no --week-id would compute *next* week and
        open a brand new DRAFT, abandoning an in-flight batch and re-spending real Flow
        credits generating 14 fresh videos. Resuming where the work actually stopped is
        the whole point of the single-command design.
        """
        if not self.batch_repo.batches_dir.exists():
            return None
        for week_dir in sorted(self.batch_repo.batches_dir.iterdir(), reverse=True):
            if not week_dir.is_dir():
                continue
            # Only this brand's weeks. Resuming another channel's batch would generate
            # and publish its Reels into the wrong account.
            if not self.brand.owns_week_id(week_dir.name):
                continue
            manifest = self.batch_repo.load_manifest(week_dir.name)
            if manifest and not self._is_batch_finished(manifest):
                return manifest.week_id
        return None

    def find_last_scheduled_date(self) -> Optional[datetime.date]:
        """
        The date of the latest slot that actually reached a platform, across every batch.

        "Latest video on YouTube/TikTok/Instagram" is read from progress.json rather than
        from the three Studio UIs: progress.json is written by the publishing phases
        themselves and records the remote id and URL each one came back with, so it
        already *is* the platform outcome -- without three more DOM scrapes that can
        break on any layout change.

        Slots that were planned but never published (PENDING/NOT_STARTED/FAILED) do not
        count. Their dates are not occupied, so a new week may legitimately reuse them.
        """
        latest: Optional[datetime.date] = None

        if not self.batch_repo.batches_dir.exists():
            return None

        for week_dir in sorted(self.batch_repo.batches_dir.iterdir()):
            if not week_dir.is_dir():
                continue
            # A brand's calendar is its own: the other channel's schedule must not push
            # this one's start date, and vice versa.
            if not self.brand.owns_week_id(week_dir.name):
                continue
            manifest = self.batch_repo.load_manifest(week_dir.name)
            if manifest is None:
                continue
            progress = self.batch_repo.load_progress(week_dir.name)

            for reel in manifest.reels:
                entry = progress.get(reel.reel_id, {})
                reached_a_platform = any(
                    entry.get(platform, {}).get("status")
                    in (INSTAGRAM_TERMINAL_STATUSES if platform == "instagram" else PLATFORM_SUCCESS_STATUSES)
                    for platform in ("youtube", "tiktok", "instagram")
                )
                if not reached_a_platform:
                    continue

                try:
                    slot_date = datetime.datetime.strptime(
                        reel.scheduled_at_local, "%Y-%m-%d %H:%M:%S"
                    ).date()
                except (ValueError, TypeError):
                    logger.warning(
                        f"[PLAN] {reel.reel_id} has an unparseable scheduled_at_local "
                        f"({reel.scheduled_at_local!r}) -- skipped when finding the last scheduled date."
                    )
                    continue

                if latest is None or slot_date > latest:
                    latest = slot_date

        return latest

    def _earliest_usable_start(self, now: datetime.datetime) -> datetime.date:
        """
        The soonest day a new week may begin.

        Today counts when its first slot is still SAME_DAY_START_LEAD_HOURS away.
        Always skipping to tomorrow threw away both of today's slots even at breakfast
        time -- a whole day of the week lost for nothing, and the reason a run started in
        the morning published nothing until the following evening.
        """
        hour, minute = (int(part) for part in DAILY_SLOT_TIMES[0].split(":"))
        first_slot_today = now.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if now + datetime.timedelta(hours=SAME_DAY_START_LEAD_HOURS) <= first_slot_today:
            return now.date()
        return now.date() + datetime.timedelta(days=1)

    def _resolve_start_date(self) -> datetime.date:
        """
        Where the next week begins: the day after the last slot already on a platform.

        Falls back to starting as soon as possible when nothing has ever been published,
        and never returns a date whose slots have gone by -- see _earliest_usable_start,
        which lets a week begin today while today's slots are still ahead.
        """
        if self.start_date:
            return self.start_date

        tz = get_timezone("Europe/Istanbul")
        now = datetime.datetime.now(tz)
        earliest = self._earliest_usable_start(now)

        last_scheduled = self.find_last_scheduled_date()
        if last_scheduled is None:
            # A brand that has never published starts as soon as it can rather than
            # waiting for the next calendar Monday: a new channel has no rhythm to align
            # to yet, and the slot generator handles any start day. Established brands
            # never reach this branch -- they continue from their own last slot below.
            logger.info(f"[PLAN] '{self.brand.brand_id}' henuz hic yayin yapmamis -- {earliest} tarihinde basliyor.")
            return earliest

        day_after = last_scheduled + datetime.timedelta(days=1)
        chosen = max(day_after, earliest)
        if chosen != day_after:
            logger.warning(
                f"[PLAN] Son planli video {last_scheduled} -- ertesi gun ({day_after}) gecmiste kaldigi icin "
                f"baslangic {chosen} olarak alindi."
            )
        else:
            logger.info(f"[PLAN] Son planli video {last_scheduled}; yeni hafta {chosen} tarihinde basliyor.")
        return chosen

    def _get_or_create_manifest(self) -> BatchManifest:
        """Loads the existing manifest for this week, or creates a fresh DRAFT one."""
        if not self.week_id:
            resumable = self._find_unfinished_week_id()
            if resumable:
                logger.info(f"[PLAN] Yarim kalmis batch bulundu, devam ediliyor: {resumable}")
                self.week_id = resumable

        start_date = self._resolve_start_date()
        week_id = self.week_id or self.brand.week_id(generate_week_id(start_date))
        self.week_id = week_id

        existing = self.batch_repo.load_manifest(week_id)
        if existing is not None and existing.start_date != start_date.isoformat() and self.week_id is None:
            # The ISO week we computed is already occupied by a batch that starts on a
            # different day. Resuming it would silently publish into the wrong week, so
            # stop and let a human pick the date with --start-date / --week-id.
            raise RuntimeError(
                f"WEEK_ID_COLLISION: computed start {start_date} maps to {week_id}, but that week "
                f"already exists starting {existing.start_date}. Re-run with an explicit "
                f"--start-date or --week-id."
            )
        if existing is not None:
            logger.info(f"[PLAN] Existing manifest loaded for {week_id} (status={existing.status}, mode={existing.content_mode})")
            # The manifest wins. A resumed week keeps the mode it was planned in even if
            # this invocation passed a different --content-mode, so half a week can never
            # come out silent and the other half narrated.
            if existing.content_mode != self.content_mode:
                logger.warning(
                    f"[PLAN] --content-mode '{self.content_mode}' ignored: {week_id} was planned as "
                    f"'{existing.content_mode}' and is being resumed in that mode."
                )
                self.content_mode = existing.content_mode
            return existing

        logger.info(f"[PLAN] No manifest for {week_id} -- creating a fresh DRAFT (14 slots, 19:30 & 22:00 Europe/Istanbul).")
        slot_plan = generate_14_slot_week_plan(start_date=start_date, slot_times=list(DAILY_SLOT_TIMES), timezone_str="Europe/Istanbul")

        reel_ids = self._allocate_reel_ids(count=14)

        past_history = [{"id": r.reel_id, "title": r.title, "category": r.content_mode} for r in self.state_repo.list_all_reels()]
        concept_plans = self._plan_concepts(past_history)

        reels: List[BatchReel] = []
        for i, (slot, reel_id, plan) in enumerate(zip(slot_plan.slots, reel_ids, concept_plans), start=1):
            if plan.content_mode in (NARRATIVE_AMBIENT_STORY, CUTAWAY_REVEAL_STORY):
                concept = plan.concept_def
                yt_title, _yt_desc, yt_tags = PublishingMetadataBuilder.build_story_youtube_metadata(
                    reel_id=reel_id,
                    name=concept.name,
                    category_group=concept.category_group,
                    real_basis=concept.real_basis,
                    topic_description=concept.topic_description,
                    narrative_frame=concept.narrative_frame,
                )
            else:
                yt_title, _yt_desc, yt_tags = PublishingMetadataBuilder.build_youtube_metadata(
                    reel_id=reel_id,
                    title=plan.title,
                    category=plan.category,
                    environment=plan.environment,
                    architecture=plan.architecture,
                    transformation=plan.transformation,
                    reveal=plan.reveal,
                )
            reels.append(BatchReel(
                index=i,
                reel_id=reel_id,
                scheduled_at_local=slot.scheduled_at_local,
                scheduled_at_utc=slot.scheduled_at_utc,
                topic_key=plan.topic_key,
                title=yt_title,
                caption=plan.topic_description,
                hashtags=yt_tags,
                content_mode=plan.content_mode,
                concept_id_slug=plan.concept_def.id_slug,
                environment=plan.environment,
                architecture=plan.architecture,
                transformation=plan.transformation,
                camera_style=plan.camera_style,
                lighting=plan.lighting,
                materials=plan.materials,
                reveal=plan.reveal,
                diversity_score=plan.diversity_score,
            ))

        manifest = BatchManifest(
            week_id=week_id,
            start_date=start_date.isoformat(),
            timezone="Europe/Istanbul",
            target_reels=14,
            status="DRAFT",
            content_mode=self.content_mode,
            reels=reels,
        )
        self.batch_repo.save_manifest(manifest)
        self.batch_repo.ensure_progress_entries(week_id, reel_ids)
        return manifest

    def _plan_concepts(self, past_history: List[Dict[str, Any]]) -> List[Any]:
        """
        The week's fourteen concept plans, in slot order.

        With no alternate format this is one engine over one library, exactly as before.
        With one, the day's two slots carry different subjects: 19:30 draws from the
        brand's own mode and 22:00 from its alternate, so a viewer who sees both posts in
        a day does not get the same idea twice.

        Each mode is ranked within its own library, because diversity is a property of a
        format's own pool: a cistern under a street and a ruined city are not near
        duplicates, and scoring them against each other would suppress neither.
        """
        primary = ContentEngine(content_mode=self.content_mode)
        alternate_mode = self.brand.alternate_content_mode
        if not alternate_mode or alternate_mode == self.content_mode:
            return primary.generate_next_reels(
                count=14, past_records=past_history, duration_seconds=10
            )

        evening_engine = ContentEngine(content_mode=alternate_mode)
        morning_plans = primary.generate_next_reels(
            count=7, past_records=past_history, duration_seconds=10
        )
        evening_plans = evening_engine.generate_next_reels(
            count=7, past_records=past_history, duration_seconds=10
        )
        logger.info(
            f"[PLAN] Iki formatli hafta: 19:30 '{self.content_mode}', "
            f"22:00 '{alternate_mode}'."
        )

        # Slots arrive as day1-19:30, day1-22:00, day2-19:30, ... so the morning plan
        # always goes first and the evening one second.
        interleaved: List[Any] = []
        for morning, evening in zip(morning_plans, evening_plans):
            interleaved.append(morning)
            interleaved.append(evening)
        return interleaved

    def _rebuild_concept_plan(self, reel: BatchReel) -> ReelConceptPlan:
        """Deterministically rebuilds the exact ReelConceptPlan (same prompt, same
        segments) used when this manifest entry was created -- see BatchReel's raw
        selector fields for why this is safe across separate process runs.

        The concept is looked up in the library its own content_mode belongs to: a story
        slug does not exist in CATEGORIES and would otherwise read as a corrupt manifest.
        """
        if reel.content_mode == NARRATIVE_AMBIENT_STORY:
            library, builder = STORY_CONCEPTS, PromptEngine.build_story_concept_plan
        elif reel.content_mode == HIDDEN_BUILD_STORY:
            library, builder = HIDDEN_BUILD_CONCEPTS, PromptEngine.build_hidden_build_plan
        elif reel.content_mode == CUTAWAY_REVEAL_STORY:
            library, builder = CUTAWAY_CONCEPTS, PromptEngine.build_cutaway_plan
        else:
            library, builder = CATEGORIES, PromptEngine.build_concept_plan

        concept = next((c for c in library if c.id_slug == reel.concept_id_slug), None)
        if concept is None:
            raise ValueError(
                f"Unknown concept_id_slug '{reel.concept_id_slug}' for {reel.reel_id} "
                f"in content_mode '{reel.content_mode}' -- manifest is corrupt."
            )
        return builder(
            concept=concept,
            env=reel.environment,
            arch=reel.architecture,
            transformation=reel.transformation,
            camera=reel.camera_style,
            lighting=reel.lighting,
            materials=reel.materials,
            reveal=reel.reveal,
            diversity_score=reel.diversity_score,
            duration_seconds=10,
        )

    # =========================================================================
    # PHASE 1: GENERATE (Flow only -- no publisher code is imported or called here)
    # =========================================================================

    def _init_flow_provider_if_needed(self) -> None:
        if self.flow_provider is not None:
            return
        if self.dry_run:
            self.flow_provider = MockVideoProvider(self.app_config.workspace_downloads_dir)
        else:
            self.flow_provider = GoogleFlowWebProvider(self.app_config)

    def all_generated(self, manifest: BatchManifest) -> bool:
        return all(r.generation_status == "COMPLETE" for r in manifest.reels)

    # Two Reels failing the same way in a row is a broken setup, not bad luck -- e.g.
    # Flow returning silent renders for an audio mode. Stopping there leaves the
    # remaining Flow credits unspent and the batch resumable once the cause is fixed.
    MAX_CONSECUTIVE_SAME_FAILURES = 2

    @staticmethod
    def _failure_signature(error: Exception) -> str:
        """The error's kind, ignoring the Reel-specific tail: 'QC_FAILED: AUDIO_MISSING'."""
        text = str(error)
        parts = [p.strip() for p in text.split(":")]
        return ": ".join(parts[:2]) if len(parts) > 1 else text[:60]

    def _run_generate_phase(self, manifest: BatchManifest) -> PhaseResult:
        self._init_flow_provider_if_needed()

        repeated_failure: Optional[str] = None
        consecutive_same = 0

        for reel in manifest.reels:
            if reel.generation_status == "COMPLETE":
                continue

            # Per Reel, not per run: the manifest is the authority on what this Reel's
            # audio should be, so a mixed-mode batch still validates each one correctly.
            validator = VideoValidator(
                reject_wrong_ratio=True,
                audio_enabled=requires_audio(reel.content_mode),
            )

            logger.info(f"[GENERATE] {reel.reel_id} ({reel.title}) -- Flow uretimi baslatiliyor...")
            try:
                plan = self._rebuild_concept_plan(reel)
                target_filename = f"clean_{reel.reel_id}_{reel.topic_key}.mp4"

                if self.dry_run:
                    downloaded_file = self.flow_provider.generate_single_video(plan=plan, reel_id=reel.reel_id, target_filename=target_filename)
                else:
                    downloaded_file = self.flow_provider.generate_single_video(plan=plan, reel_id=reel.reel_id, target_filename=target_filename)

                qc_res = validator.process_and_validate(input_video=downloaded_file, output_dir=self.app_config.workspace_downloads_dir)
                if not qc_res.is_passed:
                    raise RuntimeError(f"QC_FAILED: {qc_res.error_message}")

                final_mp4 = Path(qc_res.processed_video_path)
                file_sha = hashlib.sha256(final_mp4.read_bytes()).hexdigest()

                reel.video_path = str(final_mp4.resolve())
                reel.video_sha256 = file_sha
                reel.generation_status = "COMPLETE"
                reel.generation_error = None

                provenance = ReelProvenance.MOCK_TEST_PROVIDER.value if isinstance(self.flow_provider, MockVideoProvider) else ReelProvenance.FLOW_LIVE_GENERATION.value
                reel_state = ReelState(
                    reel_id=reel.reel_id,
                    week_id=manifest.week_id,
                    pipeline_version=reel.pipeline_version,
                    content_mode=reel.content_mode,
                    generation_status="COMPLETE",
                    qc_status="PASS",
                    video_path=reel.video_path,
                    video_sha256=reel.video_sha256,
                    source=provenance,
                    title=reel.title,
                    caption=reel.caption,
                    hashtags=reel.hashtags,
                    scheduled_at_local=reel.scheduled_at_local,
                    scheduled_at_utc=reel.scheduled_at_utc,
                )
                self.state_repo.save_reel_state(reel_state)

                logger.info(f"[GENERATE] {reel.reel_id} tamamlandi ve dogrulandi: {final_mp4}")
            except Exception as e:
                reel.generation_status = "FAILED"
                reel.generation_error = str(e)
                logger.error(f"[GENERATE] {reel.reel_id} basarisiz: {e}")

                signature = self._failure_signature(e)
                consecutive_same = consecutive_same + 1 if signature == repeated_failure else 1
                repeated_failure = signature

                if consecutive_same >= self.MAX_CONSECUTIVE_SAME_FAILURES:
                    self.batch_repo.save_manifest(manifest)
                    complete_count = sum(1 for r in manifest.reels if r.generation_status == "COMPLETE")
                    logger.error(
                        f"[GENERATE] Ayni hata ust uste {consecutive_same} kez tekrarladi ({signature}) -- "
                        f"kalan Reel'ler denenmeden duruluyor. Sebep giderilince ayni komut kaldigi yerden devam eder."
                    )
                    return PhaseResult(
                        success=False,
                        phase="GENERATE",
                        message=f"{complete_count}/{len(manifest.reels)} video hazir -- tekrarlayan hata: {signature}",
                        detail={
                            "complete": complete_count,
                            "total": len(manifest.reels),
                            "stopped_early": True,
                            "repeated_failure": signature,
                        },
                    )
            else:
                consecutive_same = 0
                repeated_failure = None

            self.batch_repo.save_manifest(manifest)

        complete_count = sum(1 for r in manifest.reels if r.generation_status == "COMPLETE")
        ok = complete_count == len(manifest.reels)
        return PhaseResult(
            success=ok,
            phase="GENERATE",
            message=f"{complete_count}/{len(manifest.reels)} video hazir",
            detail={"complete": complete_count, "total": len(manifest.reels)},
        )

    # =========================================================================
    # PHASE 2: VALIDATE + LOCK
    # =========================================================================

    def _run_validate_and_lock_phase(self, manifest: BatchManifest) -> PhaseResult:
        if manifest.status == "LOCKED":
            return PhaseResult(True, "LOCK", "Manifest zaten LOCKED", {})

        problems: List[str] = []
        expected_count = manifest.target_reels

        ids = [r.reel_id for r in manifest.reels]
        if len(ids) != expected_count or len(set(ids)) != expected_count:
            problems.append(f"{expected_count} benzersiz Reel ID bekleniyordu, bulunan: {len(ids)} toplam / {len(set(ids))} benzersiz")

        slots = [(r.scheduled_at_local) for r in manifest.reels]
        if len(set(slots)) != len(slots):
            problems.append("Aynı schedule slotuna birden fazla Reel atanmış")

        for reel in manifest.reels:
            if not reel.video_path or not reel.video_sha256:
                problems.append(f"{reel.reel_id}: video_path/sha256 eksik")
                continue

            video_path = Path(reel.video_path)
            if not video_path.exists():
                problems.append(f"{reel.reel_id}: video dosyası bulunamadı ({video_path})")
                continue

            if self.dry_run:
                # Simulation mode intentionally uses MockVideoProvider output, which is
                # correctly rejected by the strict production-provenance gate below --
                # that gate must stay strict for real (non-dry-run) content. Dry-run
                # still enforces metadata sanity so a simulated run exercises the same
                # placeholder-rejection contract as a real one.
                if is_placeholder_metadata(reel.title, reel.caption):
                    problems.append(f"{reel.reel_id}: placeholder/generic metadata reddedildi")
                continue

            reel_state = self.state_repo.get_reel_state(reel.reel_id)
            ok, reason = is_live_production_eligible(reel_state, video_path)
            if not ok:
                problems.append(f"{reel.reel_id}: eligibility FAIL ({reason})")
                continue

            id_ok, id_reason = verify_reel_id_invariant(reel.reel_id, reel_state.reel_id, reel.reel_id, video_path)
            if not id_ok:
                problems.append(f"{reel.reel_id}: {id_reason}")

            if is_placeholder_metadata(reel.title, reel.caption):
                problems.append(f"{reel.reel_id}: placeholder/generic metadata reddedildi")

        if problems:
            for p in problems:
                logger.error(f"[VALIDATE] {p}")
            return PhaseResult(False, "LOCK", f"{len(problems)} sorun bulundu, manifest LOCKED olamadı", {"problems": problems})

        manifest.status = "LOCKED"
        manifest.locked_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.batch_repo.save_manifest(manifest)
        logger.info(f"[LOCK] Manifest {manifest.week_id} LOCKED ({expected_count}/{expected_count} real, eligible reels).")
        return PhaseResult(True, "LOCK", "Manifest LOCKED", {})

    # =========================================================================
    # PHASE 3 / 4: YOUTUBE / TIKTOK (sequential, fail-fast, canonical page per Reel
    # already enforced inside YouTubeStudioPublisher/TikTokPublisher themselves)
    # =========================================================================

    def _init_youtube_publisher_if_needed(self) -> None:
        if self.yt_publisher is not None:
            return
        if self.dry_run:
            self.yt_publisher = MockYouTubeStudioPublisher(expected_handle=self.pub_config.youtube_expected_handle)
        else:
            self.yt_publisher = YouTubeStudioPublisher(self.pub_config)

    def _init_tiktok_publisher_if_needed(self) -> None:
        if self.tt_publisher is not None:
            return
        if self.dry_run:
            self.tt_publisher = MockTikTokPublisher(expected_username=self.pub_config.tiktok_expected_username)
        else:
            self.tt_publisher = TikTokPublisher(self.pub_config)

    def all_platform_done(self, week_id: str, reel_ids: List[str], platform: str) -> bool:
        progress = self.batch_repo.load_progress(week_id)
        for reel_id in reel_ids:
            status = progress.get(reel_id, {}).get(platform, {}).get("status")
            if platform == "instagram":
                if status not in INSTAGRAM_TERMINAL_STATUSES:
                    return False
            elif status not in PLATFORM_SUCCESS_STATUSES:
                return False
        return True

    def _counts_as_done(self, entry: Dict[str, Any]) -> bool:
        """
        Whether a recorded status may be trusted to skip the work again.

        A rehearsal's record counts inside that rehearsal -- the hold re-runs phases, and
        without this a dry run would schedule every Reel twice. It never counts once the
        run is live: the mock publishers invent a remote id and report SCHEDULED, and
        taking that as done leaves a real slot empty while the state file says otherwise.
        """
        return self.dry_run or not entry.get("dry_run")

    def _record_platform_status(
        self, week_id: str, reel_id: str, platform: str, status: str, **fields: Any
    ) -> bool:
        """
        Write one platform status, stamped with whether a rehearsal produced it.

        The mock publishers return SCHEDULED with an invented remote id, and these phases
        record whatever a publisher hands back. Without this stamp a --dry-run leaves
        records indistinguishable from real ones, and the next live run skips every Reel
        in the week as "already done" -- slots left empty while the state file says the
        week is finished. The .bat advertises --dry-run as the safe option, so the safe
        option has to actually be safe.
        """
        return self.batch_repo.update_platform_status(
            week_id, reel_id, platform, status, dry_run=self.dry_run, **fields
        )

    def _report_state_divergence(
        self, manifest: BatchManifest, platform: str, plat_enum: Platform
    ) -> None:
        """
        Say out loud when the two state stores disagree about a Reel.

        Platform state lives in two places: progress.json, which this pipeline writes and
        reports from, and 13_PUBLISHING/PUB-*.md, which the publishers write and then
        consult through merge_with_existing -- where, in its own words, existing remote
        evidence ALWAYS WINS.

        On 2026-08-21 fourteen duplicate uploads were deleted by hand and progress.json
        was cleared. The publish records were not, so a deleted video's id came straight
        back and held seven Reels in a resume loop against a video that no longer existed.
        Every state file looked plausible on its own; nothing anywhere said the two
        disagreed. This does not pick a winner -- the publisher now proves for itself
        whether a recorded video still exists -- it just makes the disagreement visible
        in the run output instead of leaving it to be discovered days later.
        """
        progress = self.batch_repo.load_progress(manifest.week_id)
        for reel in manifest.reels:
            entry = (progress.get(reel.reel_id) or {}).get(platform) or {}
            try:
                record = self.pub_repo.get_publish_record(reel.reel_id, plat_enum)
            except Exception:
                continue
            if record is None:
                continue

            tracked = entry.get("remote_id") or None
            recorded = getattr(record, "remote_id", None) or None
            if tracked == recorded:
                continue

            logger.warning(
                f"[STATE_DIVERGENCE] {reel.reel_id}/{platform}: progress.json "
                f"'{tracked or '-'}' derken yayin kaydi '{recorded or '-'}' diyor. "
                f"Yayinci hangisinin gercek oldugunu kendisi dogrulayacak."
            )

    def _reel_already_using_remote_id(
        self, manifest: BatchManifest, platform: str, remote_id: str, this_reel_id: str
    ) -> Optional[str]:
        """The other Reel of this week already recorded against `remote_id`, if any."""
        progress = self.batch_repo.load_progress(manifest.week_id)
        for reel in manifest.reels:
            if reel.reel_id == this_reel_id:
                continue
            if progress.get(reel.reel_id, {}).get(platform, {}).get("remote_id") == remote_id:
                return reel.reel_id
        return None

    def _build_publish_record(self, reel: BatchReel, platform: Platform, progress_entry: Dict[str, Any]) -> PublishRecord:
        recorded = str(progress_entry.get("status") or "")
        # A rehearsal's record is not evidence that anything was uploaded for real.
        trusted = self._counts_as_done(progress_entry)
        if not trusted:
            recorded = ""
        upload_attempted = trusted and (
            bool(progress_entry.get("remote_id")) or recorded in UPLOAD_ALREADY_ATTEMPTED_STATUSES
        )
        try:
            recorded_status = PlatformPublicationStatus(recorded) if recorded else PlatformPublicationStatus.PENDING
        except ValueError:
            # An unrecognised status is still evidence of an attempt if it says so above;
            # what it must never do is read as PENDING and invite a fresh upload silently.
            recorded_status = (
                PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED if upload_attempted
                else PlatformPublicationStatus.PENDING
            )

        video_file = Path(reel.video_path)
        file_sha = reel.video_sha256 or hashlib.sha256(video_file.read_bytes()).hexdigest()
        account_handle = self.pub_config.youtube_expected_handle if platform == Platform.YOUTUBE else self.pub_config.tiktok_expected_username

        return PublishRecord(
            publish_id=f"PUB-{reel.reel_id}-{platform.value.upper()}",
            batch_id=reel.scheduled_at_local.split()[0],
            reel_id=reel.reel_id,
            platform=platform,
            account_handle=account_handle,
            video_file=video_file,
            video_sha256=file_sha,
            title=reel.title or reel.reel_id,
            # Caption only -- hashtags are appended exactly once, by the UI observer
            # layer (fill_details / replace_caption). See reel-metadata-director skill.
            description=reel.caption,
            hashtags=reel.hashtags,
            scheduled_at_local=reel.scheduled_at_local,
            scheduled_at_utc=reel.scheduled_at_utc,
            timezone="Europe/Istanbul",
            status=recorded_status,
            dry_run=self.dry_run,
            ai_generated=True,
            synthetic_media_disclosed=True,
            remote_id=progress_entry.get("remote_id"),
            remote_url=progress_entry.get("url"),
            # An upload that happened is evidence even when its id was never read.
            # Deriving this from remote_id alone is what re-uploaded seven Reels.
            upload_started=upload_attempted,
            remote_draft_exists=upload_attempted,
        )

    def _run_platform_phase(self, manifest: BatchManifest, platform: str) -> PhaseResult:
        # A brand whose accounts are still placeholders must never reach a publisher: the
        # ACCOUNT_MISMATCH guard would be comparing against a placeholder expectation.
        if not self.dry_run:
            self.brand.ensure_publishable()
        """Shared sequential/fail-fast loop for YouTube and TikTok."""
        if manifest.status != "LOCKED":
            return PhaseResult(False, platform.upper(), "Manifest LOCKED değil, platform yayını başlayamaz.", {})

        if platform == "youtube":
            self._init_youtube_publisher_if_needed()
            publisher = self.yt_publisher
            plat_enum = Platform.YOUTUBE
        else:
            self._init_tiktok_publisher_if_needed()
            publisher = self.tt_publisher
            plat_enum = Platform.TIKTOK

        reel_ids = manifest.reel_ids()
        self.batch_repo.ensure_progress_entries(manifest.week_id, reel_ids)
        self._report_state_divergence(manifest, platform, plat_enum)
        soft_failures: List[str] = []

        for reel in manifest.reels:
            video_file = Path(reel.video_path)
            if not video_file.exists():
                self._record_platform_status(manifest.week_id, reel.reel_id, platform, "FAILED_FATAL", error="Video file missing on disk")
                return PhaseResult(False, platform.upper(), f"{reel.reel_id}: video dosyası bulunamadı", {"failed_reel": reel.reel_id, "hard_stop": True})

            progress = self.batch_repo.load_progress(manifest.week_id)
            entry = progress.get(reel.reel_id, {}).get(platform, {})
            if entry.get("status") in PLATFORM_SUCCESS_STATUSES and self._counts_as_done(entry):
                logger.info(f"[{platform.upper()}] {reel.reel_id} zaten {entry.get('status')}, atlanıyor.")
                continue

            reel_state = self.state_repo.get_reel_state(reel.reel_id)
            rec = self._build_publish_record(reel, plat_enum, entry)

            already_success = entry.get("status") in PLATFORM_SUCCESS_STATUSES
            gate_ok, gate_reason = run_pre_publish_hard_gate(
                reel_state=reel_state, slot=reel, publish_record=rec, video_path=video_file, already_platform_success=already_success
            )
            if not gate_ok:
                self._record_platform_status(manifest.week_id, reel.reel_id, platform, "FAILED_FATAL", error=gate_reason)
                logger.error(f"[{platform.upper()}] {reel.reel_id} ön-yayın kapısı tarafından ENGELLENDİ: {gate_reason}")
                return PhaseResult(False, platform.upper(), f"{reel.reel_id}: {gate_reason}", {"failed_reel": reel.reel_id, "reason": gate_reason, "hard_stop": True})

            logger.info(f"[{platform.upper()}] {reel.reel_id} sıraya alındı ({reel.index}/14)...")

            # Record the attempt BEFORE making it. If the process dies mid-upload, or the
            # id is never read, the next run must still know this file already went up --
            # otherwise it uploads it again.
            if not already_success and not self.dry_run:
                self._record_platform_status(
                    manifest.week_id, reel.reel_id, platform, "UPLOAD_ATTEMPTED",
                    error="Gonderim baslatildi; sonuc henuz yazilmadi.",
                )

            try:
                res_rec = publisher.upload_and_schedule(rec)
            except Exception as e:
                logger.error(f"[{platform.upper()}] {reel.reel_id} beklenmeyen hata: {e}")
                self._record_platform_status(manifest.week_id, reel.reel_id, platform, "FAILED_RETRYABLE", error=str(e))
                return PhaseResult(False, platform.upper(), f"{reel.reel_id}: {e}", {"failed_reel": reel.reel_id, "hard_stop": True})

            status_val = str(res_rec.status.value if hasattr(res_rec.status, "value") else res_rec.status)

            # A remote id already claimed by a different Reel of this week means the
            # publisher read a stale page: on 2026-08-21 seven Reels all came back with
            # one id, because capture fell through to a browser URL still showing the
            # previous video. Recording it would tie this Reel's state to another Reel's
            # video, which CLAUDE.md's Reel ID invariant exists to prevent.
            # Checked for EVERY returned id, not just successful ones. Guarding only the
            # success path left the soft-failure write below unprotected, and on
            # 2026-08-22 that path recorded one deleted video's id onto all seven Reels
            # a second time -- the very collision this guard exists to stop.
            if res_rec.remote_id and res_rec.remote_id not in NON_IDENTIFYING_REMOTE_IDS:
                clash = self._reel_already_using_remote_id(
                    manifest, platform, res_rec.remote_id, reel.reel_id
                )
                if clash:
                    self._record_platform_status(
                        manifest.week_id, reel.reel_id, platform, "FAILED_FATAL",
                        error=(
                            f"REEL_ID_MEDIA_MISMATCH: {res_rec.remote_id} zaten {clash} "
                            f"Reel'ine ait. Bayat sayfadan okunmus olabilir; kaydedilmedi."
                        ),
                    )
                    logger.error(
                        f"[{platform.upper()}] {reel.reel_id}: {res_rec.remote_id} zaten "
                        f"{clash} tarafindan kullaniliyor -- REEL_ID_MEDIA_MISMATCH."
                    )
                    return PhaseResult(
                        False, platform.upper(),
                        f"{reel.reel_id}: REEL_ID_MEDIA_MISMATCH ({res_rec.remote_id} = {clash})",
                        {"failed_reel": reel.reel_id, "hard_stop": True},
                    )

            if status_val in PLATFORM_SUCCESS_STATUSES:
                self._record_platform_status(
                    manifest.week_id, reel.reel_id, platform, status_val,
                    remote_id=res_rec.remote_id, url=res_rec.remote_url, error=None,
                )
                logger.info(f"[{platform.upper()}] {reel.reel_id} basariyla planlandi ({reel.scheduled_at_local}).")
                continue

            self._record_platform_status(
                manifest.week_id, reel.reel_id, platform, status_val,
                remote_id=res_rec.remote_id, url=res_rec.remote_url, error=res_rec.last_error,
            )

            if status_val in SOFT_FAILURE_STATUSES:
                soft_failures.append(reel.reel_id)
                logger.warning(
                    f"[{platform.upper()}] {reel.reel_id} dogrulanamadi ({status_val}): {res_rec.last_error}. "
                    f"Gonderim yapildi, sonraki Reel'e devam ediliyor."
                )
                continue

            logger.error(f"[{platform.upper()}] {reel.reel_id} basarisiz ({status_val}): {res_rec.last_error}. {platform} durduruluyor.")
            return PhaseResult(
                False, platform.upper(), f"{reel.reel_id}: {status_val} ({res_rec.last_error})",
                {"failed_reel": reel.reel_id, "status": status_val, "hard_stop": True, "soft_failures": soft_failures},
            )

        if soft_failures:
            return PhaseResult(
                False, platform.upper(),
                f"{len(soft_failures)} Reel gonderildi ama uzaktan dogrulanamadi (manuel kontrol onerilir)",
                {"hard_stop": False, "soft_failures": soft_failures},
            )
        return PhaseResult(True, platform.upper(), f"14/14 {platform} tamamlandı", {"soft_failures": []})

    def _run_youtube_phase(self, manifest: BatchManifest) -> PhaseResult:
        return self._run_platform_phase(manifest, "youtube")

    def _run_tiktok_phase(self, manifest: BatchManifest) -> PhaseResult:
        return self._run_platform_phase(manifest, "tiktok")

    # =========================================================================
    # PHASE 5: INSTAGRAM MEDIA HANDOFF
    # =========================================================================

    def _init_cloud_client_if_needed(self) -> None:
        if self.cloud_client is not None or self.dry_run:
            return
        from automation.cloud.config import CloudConfig
        cfg = CloudConfig(self.base_dir)
        self.cloud_client = LocalWorkerCloudClient(public_base_url=cfg.public_base_url, api_key=cfg.local_worker_api_key)

    def _init_ig_web_publisher_if_needed(self) -> None:
        if self.ig_web_publisher is not None:
            return
        self.ig_web_publisher = (
            MockInstagramWebPublisher() if self.dry_run else InstagramWebPublisher()
        )

    def _run_instagram_phase(self, manifest: BatchManifest) -> PhaseResult:
        """Delivers the week to Instagram by exactly one route -- see INSTAGRAM_DELIVERY_MODES."""
        if self.instagram_delivery == INSTAGRAM_DELIVERY_WEB:
            return self._run_instagram_web_phase(manifest)
        return self._run_instagram_cloud_phase(manifest)

    def _run_instagram_web_phase(self, manifest: BatchManifest) -> PhaseResult:
        """
        Schedules each Reel through instagram.com's own composer, so the post shows up in
        the account's scheduled queue right away rather than waiting for a worker.

        One composer session per Reel, and a Reel already marked done is skipped -- a
        rerun after a partial week must never schedule the same video twice.
        """
        phase = "INSTAGRAM_WEB"
        if manifest.status != "LOCKED":
            return PhaseResult(False, phase, "Manifest LOCKED değil, planlama başlayamaz.", {})

        if not self.dry_run:
            self.brand.ensure_publishable()

        self._init_ig_web_publisher_if_needed()
        self.batch_repo.ensure_progress_entries(manifest.week_id, manifest.reel_ids())

        for reel in manifest.reels:
            progress = self.batch_repo.load_progress(manifest.week_id)
            entry = progress.get(reel.reel_id, {}).get("instagram", {})
            if entry.get("status") in INSTAGRAM_TERMINAL_STATUSES and self._counts_as_done(entry):
                # Covers a Reel already handed to the cloud worker too: scheduling it here
                # as well would put two copies of the same video on the account.
                logger.info(f"[INSTAGRAM] {reel.reel_id} zaten {entry.get('status')}, atlanıyor.")
                continue

            video_file = Path(reel.video_path) if reel.video_path else None
            ok, reason = self._instagram_preflight(manifest, reel, video_file, phase)
            if not ok:
                return PhaseResult(False, phase, f"{reel.reel_id}: {reason}", {"failed_reel": reel.reel_id})

            logger.info(f"[INSTAGRAM] {reel.reel_id} planlanıyor ({reel.index}/14): {reel.scheduled_at_local}")
            status, error = self.ig_web_publisher.schedule_reel(
                video_path=video_file,
                caption=reel.caption,
                hashtags=reel.hashtags,
                scheduled_at_local=reel.scheduled_at_local,
                reel_id=reel.reel_id,
            )

            self._record_platform_status(
                manifest.week_id, reel.reel_id, "instagram", status, error=error
            )

            if status in PLATFORM_SUCCESS_STATUSES:
                logger.info(f"[INSTAGRAM] {reel.reel_id} planlandı.")
                continue

            if status == "SUBMITTED_UNVERIFIED":
                logger.warning(
                    f"[INSTAGRAM] {reel.reel_id} gonderildi ama onay okunamadi -- "
                    f"tekrar denenmeyecek, sonda ozetlenecek. {error}"
                )
                continue

            logger.error(f"[INSTAGRAM] {reel.reel_id} planlanamadı ({status}): {error}")
            return PhaseResult(
                False, phase, f"{reel.reel_id}: {status} -- {error}",
                {"failed_reel": reel.reel_id, "status": status, "error": error},
            )

        return PhaseResult(True, phase, f"{len(manifest.reels)}/{len(manifest.reels)} Instagram planlaması tamamlandı", {})

    def _instagram_preflight(self, manifest: BatchManifest, reel: BatchReel, video_file: Optional[Path], phase: str):
        """The media checks both Instagram routes share. Returns (ok, reason)."""
        if video_file is None or not video_file.exists():
            self._record_platform_status(
                manifest.week_id, reel.reel_id, "instagram", "FAILED_FATAL",
                error="Video file missing on disk",
            )
            return False, "video dosyası bulunamadı"

        reel_state = self.state_repo.get_reel_state(reel.reel_id)
        elig_ok, elig_reason = is_live_production_eligible(reel_state, video_file)
        if not elig_ok:
            self._record_platform_status(
                manifest.week_id, reel.reel_id, "instagram", "FAILED_FATAL", error=elig_reason
            )
            return False, elig_reason

        id_ok, id_reason = verify_reel_id_invariant(reel.reel_id, reel_state.reel_id, reel.reel_id, video_file)
        if not id_ok:
            self._record_platform_status(
                manifest.week_id, reel.reel_id, "instagram", "FAILED_FATAL", error=id_reason
            )
            return False, id_reason

        return True, ""

    def _run_instagram_cloud_phase(self, manifest: BatchManifest) -> PhaseResult:
        if manifest.status != "LOCKED":
            return PhaseResult(False, "INSTAGRAM_HANDOFF", "Manifest LOCKED değil, handoff başlayamaz.", {})

        self._init_cloud_client_if_needed()
        reel_ids = manifest.reel_ids()
        self.batch_repo.ensure_progress_entries(manifest.week_id, reel_ids)

        for reel in manifest.reels:
            progress = self.batch_repo.load_progress(manifest.week_id)
            entry = progress.get(reel.reel_id, {}).get("instagram", {})
            if entry.get("status") in INSTAGRAM_TERMINAL_STATUSES:
                logger.info(f"[INSTAGRAM] {reel.reel_id} zaten {entry.get('status')}, atlanıyor.")
                continue

            # Same media checks as the web route, from the same place -- provenance,
            # eligibility and the Reel ID invariant do not depend on how it is delivered.
            video_file = Path(reel.video_path) if reel.video_path else None
            ok, reason = self._instagram_preflight(manifest, reel, video_file, "INSTAGRAM_HANDOFF")
            if not ok:
                return PhaseResult(False, "INSTAGRAM_HANDOFF", f"{reel.reel_id}: {reason}", {"failed_reel": reel.reel_id})

            logger.info(f"[INSTAGRAM] {reel.reel_id} Railway/S3'e gönderiliyor ({reel.index}/14)...")
            ok, data, err = handoff_reel_to_cloud(
                local_path=video_file,
                week_id=manifest.week_id,
                reel_id=reel.reel_id,
                scheduled_at_local=reel.scheduled_at_local,
                scheduled_at_utc=reel.scheduled_at_utc,
                timezone="Europe/Istanbul",
                caption=f"{reel.caption}\n\n{' '.join(reel.hashtags)}",
                job_id=f"JOB-{manifest.week_id}-{reel.reel_id}",
                client=self.cloud_client,
            )

            if ok and data.get("ok"):
                self._record_platform_status(
                    manifest.week_id, reel.reel_id, "instagram", "MEDIA_READY",
                    remote_media_id=data.get("media_object_key"), error=None,
                )
                logger.info(f"[INSTAGRAM] {reel.reel_id} MEDIA_READY: {data.get('media_object_key')}")
                continue

            self._record_platform_status(manifest.week_id, reel.reel_id, "instagram", "FAILED_RETRYABLE", error=err)
            logger.error(f"[INSTAGRAM] {reel.reel_id} handoff basarisiz: {err}. Pipeline durduruluyor.")
            return PhaseResult(False, "INSTAGRAM_HANDOFF", f"{reel.reel_id}: {err}", {"failed_reel": reel.reel_id})

        return PhaseResult(True, "INSTAGRAM_HANDOFF", "14/14 Instagram handoff tamamlandı", {})

    # =========================================================================
    # TOP-LEVEL: single-command cascading run
    # =========================================================================

    def _refuse_dry_run_over_live_week(self, manifest: BatchManifest) -> None:
        """
        A rehearsal must never write into a week that has already published for real.

        The mock publishers return SCHEDULED with an invented remote id, and the
        publishing phases record whatever the publisher hands back -- that write is not
        conditioned on dry_run anywhere. Pointed at a live week, --dry-run therefore
        overwrites real publication records with mock ones, and SCHEDULED is exactly what
        the "already done, skip" test looks for. Every overwritten Reel is then skipped
        forever by the next live run: the slots stay empty while the state file insists
        the week is finished.

        Rehearsing a week that has published nothing stays allowed -- that is what the
        flag is for, and it is how the test suite uses it.
        """
        if not self.dry_run:
            return

        live: List[str] = []
        progress = self.batch_repo.load_progress(manifest.week_id)
        for reel_id in sorted(progress):
            entry = progress.get(reel_id) or {}
            for platform in ("youtube", "tiktok", "instagram"):
                record = entry.get(platform) or {}
                remote = record.get("remote_id") or record.get("remote_media_id")
                if remote and not str(remote).startswith("mock_"):
                    live.append(f"{reel_id}/{platform}")

        if live:
            raise RuntimeError(
                f"DRY_RUN_OVER_LIVE_WEEK: {manifest.week_id} gercek yayin kaydi tasiyor "
                f"({len(live)} kayit, ornek: {live[0]}). Prova calistirmasi bu kayitlarin "
                f"uzerine sahte 'SCHEDULED' yazar ve sonraki canli calistirma o Reel'leri "
                f"'zaten yapilmis' sanip atlar -- slotlar bos kalir. Bu haftayi calistirmak "
                f"icin --live kullanin; prova icin bos bir --week-id verin."
            )

    def run(self, phase: Optional[str] = None) -> Tuple[bool, List[PhaseResult], BatchManifest]:
        results: List[PhaseResult] = []
        manifest = self._get_or_create_manifest()
        self._refuse_dry_run_over_live_week(manifest)

        if phase:
            handler = {
                "generate": self._run_generate_phase,
                "validate": self._run_validate_and_lock_phase,
                "lock": self._run_validate_and_lock_phase,
                "youtube": self._run_youtube_phase,
                "tiktok": self._run_tiktok_phase,
                "instagram": self._run_instagram_phase,
            }.get(phase)
            if handler is None:
                raise ValueError(f"Unknown --phase '{phase}'")
            if phase in ("youtube", "tiktok", "instagram") and not self.brand.publishes_to(phase):
                # Refused rather than run: opening a browser for an account this brand
                # deliberately does not use is how a video reaches the wrong channel.
                raise ValueError(
                    f"PLATFORM_DISABLED_FOR_BRAND: '{self.brand.brand_id}' markasi "
                    f"'{phase}' platformuna yayin yapmiyor. Acmak icin automation/brands.py "
                    f"icinde bu markanin 'platforms' listesine ekleyin."
                )
            result = handler(manifest)
            results.append(result)
            self._sync_obsidian(manifest)
            self._print_status(manifest, results)
            return result.success, results, manifest

        # PHASE 1: GENERATE
        if not self.all_generated(manifest):
            result = self._run_generate_phase(manifest)
            results.append(result)
            if not result.success:
                self._sync_obsidian(manifest)
                self._print_status(manifest, results)
                return False, results, manifest

        # PHASE 2: VALIDATE + LOCK
        if manifest.status != "LOCKED":
            result = self._run_validate_and_lock_phase(manifest)
            results.append(result)
            if not result.success:
                self._sync_obsidian(manifest)
                self._print_status(manifest, results)
                return False, results, manifest

        reel_ids = manifest.reel_ids()

        # PHASES 3-5: one platform fully finished before the next one starts.
        # If a platform cannot reach 14/14, alert on Telegram and hold for
        # self.stuck_wait_minutes so the operator can fix it by hand; retry periodically
        # to pick that fix up, and only move on to the next platform once the window
        # expires. This is deliberately sequential -- the operator wants to deal with one
        # platform at a time rather than chase three broken ones at once.
        for platform, phase_fn in (
            ("youtube", self._run_youtube_phase),
            ("tiktok", self._run_tiktok_phase),
            ("instagram", self._run_instagram_phase),
        ):
            if not self.brand.publishes_to(platform):
                # Switched off for this brand. Skipped outright rather than run and
                # failed, so it costs no time, records no failure and holds nothing.
                logger.info(f"[{platform.upper()}] '{self.brand.brand_id}' bu platforma yayin yapmiyor -- atlaniyor.")
                continue

            if self.all_platform_done(manifest.week_id, reel_ids, platform):
                continue

            result = phase_fn(manifest)
            if not self.all_platform_done(manifest.week_id, reel_ids, platform):
                result = self._hold_for_manual_fix(manifest, platform, phase_fn, result)
            results.append(result)

        all_ok = all(r.success for r in results)
        if all_ok:
            results.append(PhaseResult(True, "DONE", "Tüm fazlar tamamlandı.", {}))

        self._sync_obsidian(manifest)
        self._notify_telegram(manifest, results)
        self._print_status(manifest, results)
        return all_ok, results, manifest

    def _hold_for_manual_fix(
        self,
        manifest: BatchManifest,
        platform: str,
        phase_fn: Any,
        last_result: PhaseResult,
    ) -> PhaseResult:
        """
        A platform did not reach 14/14. Alert on Telegram, then hold for
        stuck_wait_minutes, retrying periodically so a manual fix is picked up as soon as
        it lands. After the window expires, give up on this platform and let the caller
        continue to the next one -- a stuck platform must not cost the whole week.
        """
        reel_ids = manifest.reel_ids()
        done = self._platform_done_count(manifest, platform)
        self._send_telegram(
            f"Reels AI Factory — {manifest.week_id}\n\n"
            f"{platform.upper()} TAKILDI: {done}/{len(reel_ids)}\n"
            f"Sebep: {last_result.message}\n\n"
            f"{self.stuck_wait_minutes} dk icinde duzeltirsen kaldigi yerden devam eder.\n"
            f"Duzeltilmezse otomatik olarak diger platforma gecilir."
        )

        if self.stuck_wait_minutes <= 0:
            return last_result

        deadline = time.time() + (self.stuck_wait_minutes * 60)
        logger.warning(
            f"[{platform.upper()}] {done}/{len(reel_ids)} -- manuel duzeltme icin "
            f"{self.stuck_wait_minutes} dk bekleniyor. Duzeltilirse otomatik devam eder."
        )

        while time.time() < deadline:
            time.sleep(min(self.stuck_retry_seconds, max(1, deadline - time.time())))
            if self.all_platform_done(manifest.week_id, reel_ids, platform):
                break
            logger.info(f"[{platform.upper()}] Yeniden deneniyor...")
            last_result = phase_fn(manifest)
            if self.all_platform_done(manifest.week_id, reel_ids, platform):
                break

        if self.all_platform_done(manifest.week_id, reel_ids, platform):
            logger.info(f"[{platform.upper()}] Duzeldi, 14/14 tamamlandi.")
            self._send_telegram(f"Reels AI Factory — {manifest.week_id}\n\n{platform.upper()} duzeldi: 14/14 tamam.")
            return PhaseResult(True, platform.upper(), f"14/14 {platform} tamamlandı", {"soft_failures": []})

        done = self._platform_done_count(manifest, platform)
        logger.warning(f"[{platform.upper()}] {done}/{len(reel_ids)} -- sure doldu, sonraki platforma geciliyor.")
        self._send_telegram(
            f"Reels AI Factory — {manifest.week_id}\n\n"
            f"{platform.upper()} {done}/{len(reel_ids)} kaldi, sure doldu.\n"
            f"Sonraki platforma geciliyor."
        )
        return last_result

    def _platform_done_count(self, manifest: BatchManifest, platform: str) -> int:
        progress = self.batch_repo.load_progress(manifest.week_id)
        ok = PLATFORM_SUCCESS_STATUSES + (("MEDIA_READY",) if platform == "instagram" else ())
        return sum(
            1 for r in manifest.reels
            if progress.get(r.reel_id, {}).get(platform, {}).get("status") in ok
        )

    def _send_telegram(self, text: str) -> None:
        """Best-effort Telegram send. Never raises, never logs the bot token."""
        # Under pytest, refuse outright. Tests run the full pipeline against tmp_path but
        # CloudConfig still reads the real environment, so a test run happily sent live
        # messages to the operator's actual Telegram chat (a "2026-W99 TAMAMLANDI" notice
        # from a test batch landed there on 2026-08-17). Test doubles are the only way a
        # test should ever reach this method.
        if "PYTEST_CURRENT_TEST" in os.environ:
            logger.debug("[TELEGRAM] pytest ortami -- gercek bildirim gonderilmiyor.")
            return

        try:
            from automation.cloud.config import CloudConfig
            from automation.cloud.telegram_bot import TelegramBotClient

            cfg = CloudConfig(self.base_dir)
            if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
                logger.info("[TELEGRAM] Token/chat_id yok, bildirim atlandi.")
                return
            ok, _mid, err = TelegramBotClient(cfg.telegram_bot_token).send_message(
                chat_id=cfg.telegram_chat_id, text=text
            )
            logger.info("[TELEGRAM] Bildirim gonderildi." if ok else f"[TELEGRAM] Gonderilemedi: {err}")
        except Exception as e:
            logger.warning(f"[TELEGRAM] Bildirim hatasi (pipeline etkilenmedi): {e}")

    def _notify_telegram(self, manifest: BatchManifest, results: List[PhaseResult]) -> None:
        """
        Send the end-of-run summary to Telegram. Best-effort only: a notification problem
        must never change the pipeline's outcome, and the bot token is never logged.
        """
        self._send_telegram(self.build_summary_text(manifest, results))

    def build_summary_text(self, manifest: BatchManifest, results: List[PhaseResult]) -> str:
        """
        Compose the end-of-run summary. Pure string building, no I/O, so the wording can
        be tested without any risk of reaching the real Telegram API.
        """
        progress = self.batch_repo.load_progress(manifest.week_id)
        total = len(manifest.reels)

        def _done(platform: str) -> int:
            ok = PLATFORM_SUCCESS_STATUSES + (("MEDIA_READY",) if platform == "instagram" else ())
            return sum(
                1 for r in manifest.reels
                if progress.get(r.reel_id, {}).get(platform, {}).get("status") in ok
            )

        lines = [
            f"Reels AI Factory — {manifest.week_id}",
            "",
            f"Uretim : {sum(1 for r in manifest.reels if r.generation_status == 'COMPLETE')}/{total}",
            f"YouTube : {_done('youtube')}/{total}",
            f"TikTok  : {_done('tiktok')}/{total}",
            # MEDIA_READY means the file reached Railway/S3 and is queued for the cloud
            # Instagram worker -- it is NOT "published on Instagram". Spelled out so the
            # summary cannot be misread as the Reels already being live.
            f"Instagram (MEDIA_READY, henuz yayinlanmadi): {_done('instagram')}/{total}",
            "",
        ]

        failed = [r for r in results if not r.success]
        if not failed:
            lines.append("Durum: TAMAMLANDI")
        else:
            lines.append("Durum: DIKKAT GEREKIYOR")
            for r in failed:
                lines.append(f"- {r.phase}: {r.message}")

        return "\n".join(lines)

    def _sync_obsidian(self, manifest: BatchManifest) -> None:
        """Obsidian is a mirror only -- a failure here must never break the pipeline."""
        try:
            for reel in manifest.reels:
                reel_state = self.state_repo.get_reel_state(reel.reel_id)
                if reel_state:
                    self.obsidian.sync_reel_note(reel_state)
        except Exception as e:
            logger.warning(f"[OBSIDIAN] Mirror sync failed (non-fatal): {e}")

    @staticmethod
    def _ascii_safe(text: str) -> str:
        """
        Transliterate Turkish characters for the terminal summary. The Windows console
        runs cp1254 here, so 'tamamlandı' printed as 'tamamland?' -- unreadable in the one
        place the operator actually looks. Log files keep the original Turkish.
        """
        table = str.maketrans({
            "ı": "i", "İ": "I", "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G",
            "ü": "u", "Ü": "U", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
        })
        return str(text).translate(table)

    def _print_status(self, manifest: BatchManifest, results: List[PhaseResult]) -> None:
        p = lambda s="": print(self._ascii_safe(s))
        total = len(manifest.reels)
        gen_complete = sum(1 for r in manifest.reels if r.generation_status == "COMPLETE")
        progress = self.batch_repo.load_progress(manifest.week_id)

        def _done(platform: str) -> int:
            ok = PLATFORM_SUCCESS_STATUSES + (("MEDIA_READY",) if platform == "instagram" else ())
            return sum(
                1 for r in manifest.reels
                if progress.get(r.reel_id, {}).get(platform, {}).get("status") in ok
            )

        p("=" * 60)
        p(f"REELS AI FACTORY -- {self.brand.display_name} -- {manifest.week_id}")
        p("=" * 60)
        p(f"Uretim    : {gen_complete}/{total}" + ("  [OK]" if gen_complete == total else ""))
        p(f"Manifest  : {manifest.status}")
        p()
        platform_counts = {}
        for label, key in (("YouTube  ", "youtube"), ("TikTok   ", "tiktok"), ("Instagram", "instagram")):
            n = _done(key)
            platform_counts[key] = n
            if not self.brand.publishes_to(key):
                # Named rather than hidden: "0/14" beside the others reads as a failure,
                # and silence would leave nobody aware the platform is waiting to be
                # switched back on.
                p(f"{label} : KAPALI (bu marka su an bu platforma yayin yapmiyor)")
                continue
            p(f"{label} : {n}/{total}" + ("  [OK]" if n == total else ""))
        p()

        failed = [r for r in results if not r.success]
        for r in failed:
            p(f"{r.phase}: {r.message}")
            if r.detail.get("failed_reel"):
                p(f"   -> {r.detail['failed_reel']}")
            for soft in r.detail.get("soft_failures", []):
                p(f"   -> {soft} (gonderildi, uzaktan dogrulanamadi)")

        # The closing line is driven by the real per-platform counts, not just by whether
        # the phases that happened to run reported success -- otherwise a run that skipped
        # work, or a status preview, would claim TAMAMLANDI while platforms sit at 1/14.
        everything_done = (
            gen_complete == total
            and manifest.status == "LOCKED"
            and all(c == total for c in platform_counts.values())
        )
        p()
        if everything_done:
            p("TAMAMLANDI - tum platformlar hazir.")
        else:
            p("Devam etmek icin ayni komutu tekrar calistir:")
            p(f"  {self.brand.weekly_bat}")
        p("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Simple sequential weekly production pipeline")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--week-id", type=str, default=None, help="Specific Week ID (e.g. 2026-W35)")
    parser.add_argument("--live", action="store_true", default=False, help="Enable real live generation & publishing")
    parser.add_argument("--vault-path", type=str, default=None, help="Path to Obsidian vault")
    parser.add_argument("--phase", type=str, default=None, choices=["generate", "validate", "lock", "youtube", "tiktok", "instagram"], help="Debug only: run a single phase")
    parser.add_argument(
        "--brand",
        type=str,
        default=None,
        help=(
            "Which channel to run. Defaults to the original series. Each brand keeps its "
            "own week ids, Reel ids, accounts, Chrome profiles and content mode."
        ),
    )
    parser.add_argument(
        "--instagram-delivery",
        type=str,
        default=INSTAGRAM_DELIVERY_WEB,
        choices=list(INSTAGRAM_DELIVERY_MODES),
        help=(
            "How Instagram is delivered. 'web' schedules through instagram.com's own "
            "composer (post appears in the scheduled queue immediately). 'cloud' hands "
            "the media to the Railway worker, which publishes it at the scheduled moment. "
            "Never both -- that would post every Reel twice."
        ),
    )
    parser.add_argument(
        "--content-mode",
        type=str,
        default=None,
        choices=sorted(LIVE_ELIGIBLE_CONTENT_MODES),
        help="Content mode for a NEW week. Ignored when resuming an existing manifest.",
    )

    args = parser.parse_args()

    start_date = None
    if args.start_date:
        try:
            start_date = datetime.date.fromisoformat(args.start_date)
        except ValueError:
            print(f"ERROR: Invalid date format for --start-date: '{args.start_date}'. Must be YYYY-MM-DD.")
            sys.exit(1)

    pipeline = SimpleWeeklyPipeline(
        vault_path=Path(args.vault_path) if args.vault_path else None,
        dry_run=not args.live,
        week_id=args.week_id,
        start_date=start_date,
        content_mode=args.content_mode,
        instagram_delivery=args.instagram_delivery,
        brand=get_brand(args.brand),
    )

    success, results, manifest = pipeline.run(phase=args.phase)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
