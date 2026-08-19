"""
YouTube Studio Web Publisher & Scheduler using dedicated Playwright Chrome CDP on port 9224.
Includes absolute pre-upload repository guard, existing remote video resume,
exact 19:30 time setting & readback, strict audience verification, and true post-schedule verification.
"""
from abc import ABC, abstractmethod
import os
import hashlib
import time
import logging
from pathlib import Path
from typing import Optional, Any, Tuple, List, Dict

from .models import Platform, PlatformPublicationStatus, PublishRecord
from .config import PublishingConfig, get_default_youtube_studio_profile_path
from .repository import PublishingRepository
from .youtube_studio_browser import YouTubeStudioBrowserManager
from .youtube_studio_ui_observer import YouTubeStudioUIObserver

logger = logging.getLogger("ReelsAIFactory.YouTubeStudioPublisher")

# Gaps between remote-verification attempts. A Short that was just scheduled can take
# well over a minute to show "Planlandı" in the content list, because YouTube runs its
# content check first. The last entry is 0: no sleep after the final attempt.
VERIFY_BACKOFF_SECONDS = (10.0, 20.0, 30.0, 0.0)

def parse_schedule_datetime(scheduled_at_local: str) -> Tuple[str, str]:
    """
    Parses a local schedule datetime string (ISO or space separated)
    and returns (expected_date_str, expected_time_str) in Turkish YouTube Studio format:
    e.g. '2026-08-17 22:00:00' -> ('17.08.2026', '22:00').
    """
    import datetime
    if not scheduled_at_local:
        return "", ""

    s = scheduled_at_local.strip()
    dt_obj = None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d"
    ]
    try:
        dt_obj = datetime.datetime.fromisoformat(s)
    except Exception:
        for fmt in formats:
            try:
                dt_obj = datetime.datetime.strptime(s, fmt)
                break
            except Exception:
                pass

    if dt_obj is None:
        return "", ""

    return dt_obj.strftime("%d.%m.%Y"), dt_obj.strftime("%H:%M")


class BaseYouTubePublisher(ABC):
    @abstractmethod
    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        pass

class YouTubeStudioPublisher(BaseYouTubePublisher):
    """Production YouTube Studio web publisher via Playwright CDP (port 9224)."""

    def __init__(self, config: PublishingConfig, repo: Optional[PublishingRepository] = None):
        self.config = config
        self.repo = repo or PublishingRepository(Path("."))
        self.browser_mgr = YouTubeStudioBrowserManager(
            debug_port=getattr(self.config, "youtube_studio_debug_port", 9224),
            profile_dir=getattr(self.config, "youtube_studio_profile_dir", get_default_youtube_studio_profile_path())
        )

    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        """Upload video and schedule publication on YouTube Studio web."""
        if not record.video_file.exists():
            record.mark_failed(f"Video file not found on disk: {record.video_file}")
            return record

        try:
            with self.browser_mgr.connect() as (browser, context):
                page = None
                for p in context.pages:
                    if "studio.youtube.com" in p.url:
                        page = p
                        break
                if not page:
                    page = context.new_page()

                # Always return to a known-clean canonical page before touching this
                # page's state. Without this, a page left open from a PREVIOUS reel's
                # failed/partial attempt (e.g. stuck mid-editor after a wizard-step or
                # schedule-confirmation failure) gets reused as-is: verify_logged_in_channel()
                # then reads whatever text happens to be on that leftover page (e.g. the
                # previous video's title) instead of the actual channel name, misreporting
                # ACCOUNT_MISMATCH for every subsequent Reel in the same run (2026-08-17
                # incident: 10 consecutive Reels falsely blocked after Reel #1 left the page
                # in a bad state).
                channel_url = f"https://studio.youtube.com/channel/{self.config.youtube_expected_channel_id or ''}"
                try:
                    page.goto(channel_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"[{record.reel_id}] Failed to navigate to canonical channel page: {e}")

                observer = YouTubeStudioUIObserver(page)
                time.sleep(2.0)

                # 1. Check Login
                if not observer.is_logged_in():
                    record.mark_failed(
                        "YouTube Studio oturumu açık değil. Lütfen önce 'YOUTUBE_LOGIN.bat' ile giriş yapın.",
                        status=PlatformPublicationStatus.AUTH_REQUIRED
                    )
                    return record

                # 2. Verify Target Channel (@BuiIdVerse)
                is_match, detected_channel, v_msg = observer.verify_logged_in_channel(
                    expected_handle=self.config.youtube_expected_handle,
                    expected_channel_id=self.config.youtube_expected_channel_id
                )
                if not is_match:
                    record.mark_failed(v_msg, status=PlatformPublicationStatus.ACCOUNT_MISMATCH)
                    logger.error(f"[{record.reel_id}] YouTube upload blocked due to account mismatch: {v_msg}")
                    return record

                logger.info(f"[{record.reel_id}] YouTube Target Channel Verified: {detected_channel}")

                # 3. ABSOLUTE PRE-UPLOAD REPOSITORY RELOAD & GUARD
                existing_disk_rec = self.repo.get_publish_record(record.reel_id, Platform.YOUTUBE)
                if existing_disk_rec:
                    record = self.repo.merge_with_existing(record)

                has_remote_evidence = bool(
                    record.remote_id or (existing_disk_rec and existing_disk_rec.remote_id)
                    or record.remote_url or (existing_disk_rec and existing_disk_rec.remote_url)
                    or record.upload_started or (existing_disk_rec and existing_disk_rec.upload_started)
                    or record.remote_draft_exists or (existing_disk_rec and existing_disk_rec.remote_draft_exists)
                    or record.status in [
                        PlatformPublicationStatus.UPLOADED_DRAFT,
                        PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED,
                        PlatformPublicationStatus.SCHEDULED,
                        PlatformPublicationStatus.PUBLISHED
                    ]
                )

                target_remote_id = record.remote_id or (existing_disk_rec.remote_id if existing_disk_rec else None)

                if has_remote_evidence and target_remote_id:
                    # STRICT RESUME: Upload is FORBIDDEN!
                    logger.info(f"[{record.reel_id}] [UPLOAD SKIPPED] Existing YouTube remote video detected (remote_id: {target_remote_id}). Resume mode enabled.")
                    if not observer.open_exact_remote_video(target_remote_id):
                        record.mark_failed(f"Failed to open existing remote video {target_remote_id}", status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED)
                        return record

                    # Open Draft Wizard stepper via 'Taslağı düzenle' (YOUTUBE_DRAFT_WIZARD_READY)
                    if not observer.enter_existing_draft_wizard():
                        record.mark_failed("Could not open draft stepper wizard via 'Taslağı düzenle'.", status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED)
                        return record

                elif has_remote_evidence:
                    # Fallback title search if remote_id wasn't populated but draft exists
                    logger.info(f"[{record.reel_id}] [RESUME_EXISTING_YOUTUBE_DRAFT] Found existing draft record for '{record.title}'. Resuming without upload.")
                    if not observer.find_and_open_existing_draft(record.title, record.reel_id, channel_id=self.config.youtube_expected_channel_id):
                        record.mark_failed("[HARD UPLOAD GUARD] Record in resume state but draft wizard could not be opened.", status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED)
                        return record

                    # Capture video ID if visible
                    v_id, v_url = observer.capture_video_id_and_url()
                    if v_id and not record.remote_id:
                        record.remote_id = v_id
                        record.remote_url = v_url or f"https://youtube.com/shorts/{v_id}"
                        record.remote_draft_exists = True
                        self.repo.save_publish_record(record)
                else:
                    # 4. Upload Video File (Only when NO remote evidence exists anywhere)
                    logger.info(f"[{record.reel_id}] Uploading to YouTube Studio: {record.video_file.name}")
                    record.upload_started = True
                    if not observer.upload_file(record.video_file):
                        record.mark_failed("YouTube Studio file input not found.")
                        return record

                    # Wait for Upload Completion
                    if not observer.wait_for_upload_completion(timeout_seconds=120):
                        record.mark_failed("YouTube video upload timed out or failed to process.")
                        return record

                    # Capture video ID immediately from link element and atomic persist
                    try:
                        v_id, v_url = observer.capture_video_id_and_url()
                        if v_id:
                            record.remote_id = v_id
                            record.remote_url = v_url or f"https://youtube.com/shorts/{v_id}"
                            record.remote_draft_exists = True
                            record.status = PlatformPublicationStatus.UPLOADED_DRAFT
                            logger.info(f"[{record.reel_id}] Captured remote_id: {v_id} at upload time. Saving to repository.")
                            self.repo.save_publish_record(record)
                    except Exception as e:
                        logger.debug(f"Video ID capture error: {e}")

                    # Fill Details (Title, Description, Hashtags)
                    observer.fill_details(record.title, record.description, record.hashtags)
                    time.sleep(1.0)

                # 5. WIZARD STATE MACHINE: Advance through all steps to VISIBILITY
                #    This handles Audience, AI Disclosure, and all step transitions centrally
                wizard_ok, wizard_msg = observer.advance_wizard_to_visibility(
                    made_for_kids=self.config.youtube_made_for_kids,
                    ai_disclosure=self.config.ai_disclosure
                )
                if not wizard_ok:
                    record.mark_failed(
                        f"YouTube wizard state machine failed: {wizard_msg}",
                        status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
                    )
                    return record

                # 6. Expand Schedule Card (VISIBILITY step verified by precondition)
                if not observer.find_and_expand_schedule_card():
                    record.mark_failed(
                        "YouTube Studio schedule seçeneği ('Planlayın') bulunamadı veya açılamadı. Video doğrudan yayınlanmadı (Güvenli İptal).",
                        status=PlatformPublicationStatus.SCHEDULING_UNAVAILABLE
                    )
                    return record

                # 7. Set Date & Time (with dynamic aria-labelledby time resolver & strict 19:30 readback)
                if not observer.set_schedule_datetime(record.scheduled_at_local):
                    record.mark_failed(
                        "YouTube Studio tarih/saat seçimi geçersiz ('Geçersiz Tarih' veya Tarih/Saat Uyuşmazlığı).",
                        status=PlatformPublicationStatus.SCHEDULING_UNAVAILABLE
                    )
                    return record
                time.sleep(1.0)

                # 8. Submit Schedule (Waits for processing if button is disabled, NEVER logs false positive)
                success, ref = observer.click_schedule_and_verify(timeout_seconds=45)
                if not success:
                    record.mark_failed(f"YouTube Studio schedule submission failed: {ref}")
                    return record

                # 9. Verify scheduled status in content list
                target_vid_id = record.remote_id or target_remote_id
                if not target_vid_id:
                    record.mark_failed(
                        "Remote YouTube video ID is missing; refusing to guess or verify the wrong draft.",
                        status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
                    )
                    return record
                expected_date_str, expected_time_str = parse_schedule_datetime(record.scheduled_at_local)

                # Bounded remote verification: eventual consistency on YouTube's side means
                # a schedule that just succeeded may not be reflected in the content list
                # instantly -- the content check has to finish first. Retry with growing
                # gaps before treating it as inconclusive; two attempts seconds apart were
                # not enough (2026-08-19: 5 of 14 Reels flagged while all 14 were scheduled).
                # Never re-uploads or re-submits the schedule while verifying.
                is_sched, s_msg = False, "NOT_ATTEMPTED"
                for attempt, backoff in enumerate(VERIFY_BACKOFF_SECONDS, start=1):
                    is_sched, s_msg = observer.verify_remote_scheduled_status(
                        remote_id=target_vid_id,
                        target_title=record.title,
                        expected_date_str=expected_date_str,
                        expected_time_str=expected_time_str,
                        channel_id=self.config.youtube_expected_channel_id
                    )
                    if is_sched:
                        break
                    if backoff:
                        logger.info(
                            f"[{record.reel_id}] Uzak dogrulama {attempt}. denemede sonuçsuz ({s_msg}); "
                            f"{backoff:.0f}s sonra tekrar denenecek."
                        )
                        time.sleep(backoff)
                if not is_sched:
                    # Still inconclusive after 2 attempts: preserve remote evidence
                    # (remote_id/remote_url already captured above) and never falsely
                    # mark SCHEDULED.
                    record.mark_failed(f"Remote scheduled verification failed ({s_msg})", status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED)
                    self.repo.save_publish_record(record)
                    return record

                # Extract verified date/time for mark_scheduled
                import datetime as _dt
                try:
                    _sched_dt = _dt.datetime.fromisoformat(record.scheduled_at_local)
                    _v_date = _sched_dt.strftime("%Y-%m-%d")
                    _v_time = _sched_dt.strftime("%H:%M")
                except Exception:
                    _v_date = None
                    _v_time = None

                record.mark_scheduled(
                    remote_id=target_vid_id,
                    remote_url=record.remote_url or f"https://youtube.com/shorts/{target_vid_id}",
                    verified_date=_v_date,
                    verified_time=_v_time
                )
                self.repo.save_publish_record(record)
                logger.info(f"[{record.reel_id}] YouTube Studio scheduled successfully for {record.scheduled_at_local} (Remote ID: {target_vid_id})")
                return record

        except ConnectionError as ce:
            record.mark_failed(str(ce), status=PlatformPublicationStatus.AUTH_REQUIRED)
            return record
        except Exception as e:
            logger.exception(f"YouTube Studio upload error for {record.reel_id}: {e}")
            record.mark_failed(f"YouTube Studio upload failed: {e}")
            return record

    def prepare_preflight(self, record: PublishRecord) -> Tuple[bool, str]:
        """Runs preflight on YouTube Studio: prepares wizard up to Planla button without clicking."""
        try:
            with self.browser_mgr.connect() as (browser, context):
                page = None
                for p in context.pages:
                    if "studio.youtube.com" in p.url:
                        page = p
                        break
                if not page:
                    page = context.new_page()

                observer = YouTubeStudioUIObserver(page)
                time.sleep(1.0)

                target_remote_id = record.remote_id
                if not target_remote_id:
                    return False, "PREFLIGHT_BLOCKED: record.remote_id is missing; refusing to target a hardcoded draft."
                ok, msg = observer.prepare_youtube_schedule_preflight(
                    target_remote_id=target_remote_id,
                    scheduled_at_local=record.scheduled_at_local,
                    expected_handle=self.config.youtube_expected_handle,
                    expected_channel_id=self.config.youtube_expected_channel_id
                )
                return ok, msg
        except Exception as e:
            logger.exception(f"YouTube Studio preflight error: {e}")
            return False, f"PREFLIGHT_ERROR: {e}"

    def commit_schedule(self, record: PublishRecord) -> PublishRecord:
        """Commits schedule on YouTube Studio: clicks Planla and verifies remote scheduled state."""
        try:
            with self.browser_mgr.connect() as (browser, context):
                page = None
                for p in context.pages:
                    if "studio.youtube.com" in p.url:
                        page = p
                        break
                if not page:
                    record.mark_failed("No active YouTube Studio page found for commit.")
                    return record

                observer = YouTubeStudioUIObserver(page)
                target_remote_id = record.remote_id
                if not target_remote_id:
                    record.mark_failed("Commit blocked: record.remote_id is missing; refusing to target a hardcoded draft.")
                    return record

                exp_date, exp_time = parse_schedule_datetime(record.scheduled_at_local)
                ok, msg = observer.commit_youtube_schedule(
                    target_remote_id=target_remote_id,
                    target_title=record.title,
                    channel_id=self.config.youtube_expected_channel_id,
                    expected_date_str=exp_date,
                    expected_time_str=exp_time
                )
                if not ok:
                    record.mark_failed(f"YouTube Studio commit failed: {msg}")
                    return record

                import datetime as _dt
                try:
                    _sched_dt = _dt.datetime.fromisoformat(record.scheduled_at_local)
                    _v_date = _sched_dt.strftime("%Y-%m-%d")
                    _v_time = _sched_dt.strftime("%H:%M")
                except Exception:
                    _v_date = None
                    _v_time = None

                record.mark_scheduled(
                    remote_id=target_remote_id,
                    remote_url=record.remote_url or f"https://youtube.com/shorts/{target_remote_id}",
                    verified_date=_v_date,
                    verified_time=_v_time
                )
                self.repo.save_publish_record(record)
                return record
        except Exception as e:
            logger.exception(f"YouTube Studio commit error: {e}")
            record.mark_failed(f"YouTube Studio commit error: {e}")
            return record


class MockYouTubeStudioPublisher(BaseYouTubePublisher):
    """Mock publisher for safe tests and dry-runs (Zero web interaction / Zero uploads)."""

    def __init__(self, simulate_mismatch: bool = False, expected_handle: str = "@BuiIdVerse"):
        self.simulate_mismatch = simulate_mismatch
        self.expected_handle = expected_handle

    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        if not record.video_file.exists():
            record.mark_failed(f"Video file not found: {record.video_file}")
            return record

        if self.simulate_mismatch:
            record.mark_failed(
                f"ACCOUNT_MISMATCH: Expected '{self.expected_handle}', detected '@other_channel'",
                status=PlatformPublicationStatus.ACCOUNT_MISMATCH
            )
            return record

        mock_ref = f"mock_yt_{hashlib.md5((record.reel_id + '_yt_studio').encode('utf-8')).hexdigest()[:11]}"
        record.mark_scheduled(
            remote_id=mock_ref,
            remote_url=f"https://studio.youtube.com/video/{mock_ref}/edit"
        )
        return record

    def prepare_preflight(self, record: PublishRecord) -> Tuple[bool, str]:
        if self.simulate_mismatch:
            return False, f"ACCOUNT_MISMATCH: Expected '{self.expected_handle}'"
        return True, "YOUTUBE_FINAL_SCHEDULE_READY"

    def commit_schedule(self, record: PublishRecord) -> PublishRecord:
        mock_ref = record.remote_id or f"mock_yt_{hashlib.md5((record.reel_id + '_yt_studio').encode('utf-8')).hexdigest()[:11]}"
        record.mark_scheduled(
            remote_id=mock_ref,
            remote_url=f"https://studio.youtube.com/video/{mock_ref}/edit",
            verified_date="2026-08-16",
            verified_time="19:30"
        )
        return record

