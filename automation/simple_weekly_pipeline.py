"""
Simple Weekly Pipeline -- deterministic, sequential, single-direction production entrypoint.

Replaces automation.weekly_orchestrator as the LIVE production entrypoint. Does not
reimplement Flow generation, YouTube/TikTok publishing, or Instagram media handoff --
it calls the existing, working modules one Reel at a time, in a fixed phase order, and
never lets a later phase start before the previous one is fully (14/14) done:

    PLAN -> GENERATE -> VALIDATE -> LOCK -> YOUTUBE -> TIKTOK -> INSTAGRAM_HANDOFF -> DONE

Content plan (workspace/batches/<week_id>/manifest.json) becomes immutable once LOCKED.
Platform publishing status (workspace/batches/<week_id>/progress.json) is tracked
separately and can never modify the manifest. See .claude/skills/weekly-resume-manager
and .claude/skills/production-media-guardian for the underlying safety contracts this
pipeline depends on -- it does not re-derive them.
"""
import argparse
import datetime
import hashlib
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ReelsAIFactory.SimpleWeeklyPipeline")

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
from automation.publishing.eligibility import is_live_production_eligible, HARD_EXCLUDED_REEL_IDS
from automation.publishing.preflight_gate import run_pre_publish_hard_gate, verify_reel_id_invariant, is_placeholder_metadata
from automation.publishing.metadata_builder import PublishingMetadataBuilder
from automation.flow.generator import GoogleFlowWebProvider, MockVideoProvider, VideoProvider
from automation.content.concepts import CATEGORIES
from automation.content.engine import ContentEngine
from automation.content.prompt_engine import PromptEngine, ReelConceptPlan
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
)
from automation.orchestration.obsidian_mirror import ObsidianControlCenter, DEFAULT_VAULT_PATH

PLATFORM_SUCCESS_STATUSES = ("SCHEDULED", "PUBLISHED", "REMOTE_VERIFIED")

# The submit went through but the confirmation read-back was inconclusive. The video is
# very likely correctly scheduled on the platform, so halting the whole week here does
# more harm than good -- record it, keep going, and let the end-of-run summary flag it
# for a human look. (2026-08-17: a Short WAS scheduled correctly but verification looked
# at the wrong Studio tab and stopped all 14 Reels on a false negative.)
SOFT_FAILURE_STATUSES = ("SCHEDULE_RESUME_REQUIRED", "UPLOADED_DRAFT", "REVIEW_REQUIRED")

# The browser/session itself is broken. Continuing would cascade the same failure into
# every remaining Reel, so this stops the current platform.
HARD_FAILURE_STATUSES = ("ACCOUNT_MISMATCH", "AUTH_REQUIRED", "NEEDS_USER_HTML")


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
    ):
        self.base_dir = (base_dir or Path(".").resolve())
        self.dry_run = dry_run
        self.week_id = week_id
        self.start_date = start_date

        self.batch_repo = BatchRepository(self.base_dir)
        self.state_repo = StateRepository(self.base_dir)
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
            self.pub_config = load_publishing_config(base_dir=self.base_dir)
        except Exception:
            self.pub_config = PublishingConfig()

        # Injected for tests / explicit wiring. Never eagerly constructed here -- each
        # phase lazily builds only the client(s) it needs, so GENERATE never imports a
        # publisher and YOUTUBE never touches the Flow provider (platform isolation).
        self.flow_provider = flow_provider
        self.yt_publisher = yt_publisher
        self.tt_publisher = tt_publisher
        self.cloud_client = cloud_client

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
        num = 11
        while len(allocated) < count:
            candidate = f"REEL-2026-{num:04d}"
            num += 1
            if candidate not in used:
                allocated.append(candidate)
                used.add(candidate)
        return allocated

    def _get_or_create_manifest(self) -> BatchManifest:
        """Loads the existing manifest for this week, or creates a fresh DRAFT one."""
        start_date = self.start_date or calculate_next_safe_week_start()
        week_id = self.week_id or generate_week_id(start_date)
        self.week_id = week_id

        existing = self.batch_repo.load_manifest(week_id)
        if existing is not None:
            logger.info(f"[PLAN] Existing manifest loaded for {week_id} (status={existing.status})")
            return existing

        logger.info(f"[PLAN] No manifest for {week_id} -- creating a fresh DRAFT (14 slots, 19:30 & 22:00 Europe/Istanbul).")
        slot_plan = generate_14_slot_week_plan(start_date=start_date, slot_times=["19:30", "22:00"], timezone_str="Europe/Istanbul")

        reel_ids = self._allocate_reel_ids(count=14)

        content_engine = ContentEngine()
        past_history = [{"id": r.reel_id, "title": r.title, "category": r.content_mode} for r in self.state_repo.list_all_reels()]
        concept_plans = content_engine.generate_next_reels(count=14, past_records=past_history, duration_seconds=10)

        reels: List[BatchReel] = []
        for i, (slot, reel_id, plan) in enumerate(zip(slot_plan.slots, reel_ids, concept_plans), start=1):
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
            reels=reels,
        )
        self.batch_repo.save_manifest(manifest)
        self.batch_repo.ensure_progress_entries(week_id, reel_ids)
        return manifest

    def _rebuild_concept_plan(self, reel: BatchReel) -> ReelConceptPlan:
        """Deterministically rebuilds the exact ReelConceptPlan (same prompt, same
        segments) used when this manifest entry was created -- see BatchReel's raw
        selector fields for why this is safe across separate process runs."""
        concept = next((c for c in CATEGORIES if c.id_slug == reel.concept_id_slug), None)
        if concept is None:
            raise ValueError(f"Unknown concept_id_slug '{reel.concept_id_slug}' for {reel.reel_id} -- manifest is corrupt.")
        return PromptEngine.build_concept_plan(
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

    def _run_generate_phase(self, manifest: BatchManifest) -> PhaseResult:
        self._init_flow_provider_if_needed()
        validator = VideoValidator(reject_wrong_ratio=True, audio_enabled=False)

        for reel in manifest.reels:
            if reel.generation_status == "COMPLETE":
                continue

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
                if status != "MEDIA_READY":
                    return False
            elif status not in PLATFORM_SUCCESS_STATUSES:
                return False
        return True

    def _build_publish_record(self, reel: BatchReel, platform: Platform, progress_entry: Dict[str, Any]) -> PublishRecord:
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
            status=PlatformPublicationStatus.PENDING,
            dry_run=self.dry_run,
            ai_generated=True,
            synthetic_media_disclosed=True,
            remote_id=progress_entry.get("remote_id"),
            remote_url=progress_entry.get("url"),
            upload_started=bool(progress_entry.get("remote_id")),
            remote_draft_exists=bool(progress_entry.get("remote_id")),
        )

    def _run_platform_phase(self, manifest: BatchManifest, platform: str) -> PhaseResult:
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
        soft_failures: List[str] = []

        for reel in manifest.reels:
            video_file = Path(reel.video_path)
            if not video_file.exists():
                self.batch_repo.update_platform_status(manifest.week_id, reel.reel_id, platform, "FAILED_FATAL", error="Video file missing on disk")
                return PhaseResult(False, platform.upper(), f"{reel.reel_id}: video dosyası bulunamadı", {"failed_reel": reel.reel_id, "hard_stop": True})

            progress = self.batch_repo.load_progress(manifest.week_id)
            entry = progress.get(reel.reel_id, {}).get(platform, {})
            if entry.get("status") in PLATFORM_SUCCESS_STATUSES:
                logger.info(f"[{platform.upper()}] {reel.reel_id} zaten {entry.get('status')}, atlanıyor.")
                continue

            reel_state = self.state_repo.get_reel_state(reel.reel_id)
            rec = self._build_publish_record(reel, plat_enum, entry)

            already_success = entry.get("status") in PLATFORM_SUCCESS_STATUSES
            gate_ok, gate_reason = run_pre_publish_hard_gate(
                reel_state=reel_state, slot=reel, publish_record=rec, video_path=video_file, already_platform_success=already_success
            )
            if not gate_ok:
                self.batch_repo.update_platform_status(manifest.week_id, reel.reel_id, platform, "FAILED_FATAL", error=gate_reason)
                logger.error(f"[{platform.upper()}] {reel.reel_id} ön-yayın kapısı tarafından ENGELLENDİ: {gate_reason}")
                return PhaseResult(False, platform.upper(), f"{reel.reel_id}: {gate_reason}", {"failed_reel": reel.reel_id, "reason": gate_reason, "hard_stop": True})

            logger.info(f"[{platform.upper()}] {reel.reel_id} sıraya alındı ({reel.index}/14)...")
            try:
                res_rec = publisher.upload_and_schedule(rec)
            except Exception as e:
                logger.error(f"[{platform.upper()}] {reel.reel_id} beklenmeyen hata: {e}")
                self.batch_repo.update_platform_status(manifest.week_id, reel.reel_id, platform, "FAILED_RETRYABLE", error=str(e))
                return PhaseResult(False, platform.upper(), f"{reel.reel_id}: {e}", {"failed_reel": reel.reel_id, "hard_stop": True})

            status_val = str(res_rec.status.value if hasattr(res_rec.status, "value") else res_rec.status)
            if status_val in PLATFORM_SUCCESS_STATUSES:
                self.batch_repo.update_platform_status(
                    manifest.week_id, reel.reel_id, platform, status_val,
                    remote_id=res_rec.remote_id, url=res_rec.remote_url, error=None,
                )
                logger.info(f"[{platform.upper()}] {reel.reel_id} basariyla planlandi ({reel.scheduled_at_local}).")
                continue

            self.batch_repo.update_platform_status(
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

    def _run_instagram_phase(self, manifest: BatchManifest) -> PhaseResult:
        if manifest.status != "LOCKED":
            return PhaseResult(False, "INSTAGRAM_HANDOFF", "Manifest LOCKED değil, handoff başlayamaz.", {})

        self._init_cloud_client_if_needed()
        reel_ids = manifest.reel_ids()
        self.batch_repo.ensure_progress_entries(manifest.week_id, reel_ids)

        for reel in manifest.reels:
            video_file = Path(reel.video_path)
            if not video_file.exists():
                self.batch_repo.update_platform_status(manifest.week_id, reel.reel_id, "instagram", "FAILED_FATAL", error="Video file missing on disk")
                return PhaseResult(False, "INSTAGRAM_HANDOFF", f"{reel.reel_id}: video dosyası bulunamadı", {"failed_reel": reel.reel_id})

            progress = self.batch_repo.load_progress(manifest.week_id)
            entry = progress.get(reel.reel_id, {}).get("instagram", {})
            if entry.get("status") == "MEDIA_READY":
                logger.info(f"[INSTAGRAM] {reel.reel_id} zaten MEDIA_READY, atlanıyor.")
                continue

            reel_state = self.state_repo.get_reel_state(reel.reel_id)
            elig_ok, elig_reason = is_live_production_eligible(reel_state, video_file)
            if not elig_ok:
                self.batch_repo.update_platform_status(manifest.week_id, reel.reel_id, "instagram", "FAILED_FATAL", error=elig_reason)
                return PhaseResult(False, "INSTAGRAM_HANDOFF", f"{reel.reel_id}: {elig_reason}", {"failed_reel": reel.reel_id})

            id_ok, id_reason = verify_reel_id_invariant(reel.reel_id, reel_state.reel_id, reel.reel_id, video_file)
            if not id_ok:
                self.batch_repo.update_platform_status(manifest.week_id, reel.reel_id, "instagram", "FAILED_FATAL", error=id_reason)
                return PhaseResult(False, "INSTAGRAM_HANDOFF", f"{reel.reel_id}: {id_reason}", {"failed_reel": reel.reel_id})

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
                self.batch_repo.update_platform_status(
                    manifest.week_id, reel.reel_id, "instagram", "MEDIA_READY",
                    remote_media_id=data.get("media_object_key"), error=None,
                )
                logger.info(f"[INSTAGRAM] {reel.reel_id} MEDIA_READY: {data.get('media_object_key')}")
                continue

            self.batch_repo.update_platform_status(manifest.week_id, reel.reel_id, "instagram", "FAILED_RETRYABLE", error=err)
            logger.error(f"[INSTAGRAM] {reel.reel_id} handoff basarisiz: {err}. Pipeline durduruluyor.")
            return PhaseResult(False, "INSTAGRAM_HANDOFF", f"{reel.reel_id}: {err}", {"failed_reel": reel.reel_id})

        return PhaseResult(True, "INSTAGRAM_HANDOFF", "14/14 Instagram handoff tamamlandı", {})

    # =========================================================================
    # TOP-LEVEL: single-command cascading run
    # =========================================================================

    def run(self, phase: Optional[str] = None) -> Tuple[bool, List[PhaseResult], BatchManifest]:
        results: List[PhaseResult] = []
        manifest = self._get_or_create_manifest()

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

        # PHASES 3-5: YOUTUBE / TIKTOK / INSTAGRAM.
        # Once the content is LOCKED the three platforms are independent of each other --
        # they publish the same 14 videos at the same slots, so a problem on one is no
        # reason to skip the other two. Only a hard failure (broken session/browser) stops
        # the platform it happened on; the remaining platforms still run.
        for platform, phase_fn in (
            ("youtube", self._run_youtube_phase),
            ("tiktok", self._run_tiktok_phase),
            ("instagram", self._run_instagram_phase),
        ):
            if self.all_platform_done(manifest.week_id, reel_ids, platform):
                continue
            result = phase_fn(manifest)
            results.append(result)

        all_ok = all(r.success for r in results)
        if all_ok:
            results.append(PhaseResult(True, "DONE", "Tüm fazlar tamamlandı.", {}))

        self._sync_obsidian(manifest)
        self._notify_telegram(manifest, results)
        self._print_status(manifest, results)
        return all_ok, results, manifest

    def _notify_telegram(self, manifest: BatchManifest, results: List[PhaseResult]) -> None:
        """
        Send the end-of-run summary to Telegram. Best-effort only: a notification problem
        must never change the pipeline's outcome, and the bot token is never logged.
        """
        try:
            from automation.cloud.config import CloudConfig
            from automation.cloud.telegram_bot import TelegramBotClient

            cfg = CloudConfig(self.base_dir)
            if not cfg.telegram_bot_token or not cfg.telegram_chat_id:
                logger.info("[TELEGRAM] Token/chat_id yok, bildirim atlandi.")
                return

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
                f"Instagram (MEDIA_READY): {_done('instagram')}/{total}",
                "",
            ]

            failed = [r for r in results if not r.success]
            if not failed:
                lines.append("Durum: TAMAMLANDI")
            else:
                lines.append("Durum: DIKKAT GEREKIYOR")
                for r in failed:
                    lines.append(f"- {r.phase}: {r.message}")

            ok, _msg_id, err = TelegramBotClient(cfg.telegram_bot_token).send_message(
                chat_id=cfg.telegram_chat_id, text="\n".join(lines)
            )
            logger.info("[TELEGRAM] Bildirim gonderildi." if ok else f"[TELEGRAM] Gonderilemedi: {err}")
        except Exception as e:
            logger.warning(f"[TELEGRAM] Bildirim hatasi (pipeline etkilenmedi): {e}")

    def _sync_obsidian(self, manifest: BatchManifest) -> None:
        """Obsidian is a mirror only -- a failure here must never break the pipeline."""
        try:
            for reel in manifest.reels:
                reel_state = self.state_repo.get_reel_state(reel.reel_id)
                if reel_state:
                    self.obsidian.sync_reel_note(reel_state)
        except Exception as e:
            logger.warning(f"[OBSIDIAN] Mirror sync failed (non-fatal): {e}")

    def _print_status(self, manifest: BatchManifest, results: List[PhaseResult]) -> None:
        print("=" * 60)
        print(f"REELS AI FACTORY -- {manifest.week_id}")
        print("=" * 60)
        gen_complete = sum(1 for r in manifest.reels if r.generation_status == "COMPLETE")
        print(f"PHASE 1 -- GENERATION")
        print(f"Videos: {gen_complete}/{len(manifest.reels)}" + (" [OK]" if gen_complete == len(manifest.reels) else ""))
        print(f"Manifest status: {manifest.status}")
        print()
        for r in results:
            marker = "[OK]" if r.success else "[STOPPED]"
            print(f"{r.phase}: {r.message} {marker}")
            if not r.success and r.detail.get("failed_reel"):
                print(f"Current: {r.detail['failed_reel']}")
        print()
        if any(not r.success for r in results):
            print("Pipeline stopped safely.")
            print("Resume command: HAFTALIK_14_REEL_URET_VE_PLANLA.bat")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Simple sequential weekly production pipeline")
    parser.add_argument("--start-date", type=str, default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--week-id", type=str, default=None, help="Specific Week ID (e.g. 2026-W35)")
    parser.add_argument("--live", action="store_true", default=False, help="Enable real live generation & publishing")
    parser.add_argument("--vault-path", type=str, default=None, help="Path to Obsidian vault")
    parser.add_argument("--phase", type=str, default=None, choices=["generate", "validate", "lock", "youtube", "tiktok", "instagram"], help="Debug only: run a single phase")

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
    )

    success, results, manifest = pipeline.run(phase=args.phase)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
