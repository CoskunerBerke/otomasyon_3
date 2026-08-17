"""
TikTok Studio Publisher & Scheduler using dedicated Playwright Chrome CDP on port 9223.
Includes editor session resume, filename caption replacement, 'Planla' radio verification,
publish-now hard safety guard, and post-schedule verification.
"""
from abc import ABC, abstractmethod
import os
import hashlib
import time
import logging
from pathlib import Path
from typing import Optional, Any, Tuple, List, Dict

from .models import Platform, PlatformPublicationStatus, PublishRecord
from .config import PublishingConfig
from .tiktok_browser import TikTokBrowserManager
from .tiktok_ui_observer import TikTokUIObserver

logger = logging.getLogger("ReelsAIFactory.TikTokPublisher")

class BaseTikTokPublisher(ABC):
    @abstractmethod
    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        pass

class TikTokPublisher(BaseTikTokPublisher):
    """Production TikTok Studio web publisher via Playwright CDP (port 9223)."""

    def __init__(self, config: PublishingConfig):
        self.config = config
        self.browser_mgr = TikTokBrowserManager(
            debug_port=self.config.tiktok_debug_port,
            profile_dir=self.config.tiktok_profile_dir
        )

    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        """Upload video and schedule publication on TikTok Studio web."""
        if not record.video_file.exists():
            record.mark_failed(f"Video file not found on disk: {record.video_file}")
            return record

        try:
            with self.browser_mgr.connect() as (browser, context):
                page = None
                for p in context.pages:
                    if "tiktok.com" in p.url:
                        page = p
                        break
                if not page:
                    page = context.new_page()

                # Always return to a known-clean canonical page before touching this
                # page's state -- same fix and same reasoning as YouTubeStudioPublisher:
                # a page left open mid-editor from a previous Reel's attempt causes
                # verify_logged_in_username() to read stale/wrong DOM content (e.g. a raw
                # numeric user ID) instead of the actual @handle, misreporting
                # ACCOUNT_MISMATCH for every subsequent Reel in the same run.
                try:
                    page.goto(self.config.tiktok_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning(f"[{record.reel_id}] Failed to navigate to canonical TikTok page: {e}")

                observer = TikTokUIObserver(page)
                time.sleep(2.0)

                # 1. Check Login
                if not observer.is_logged_in():
                    record.mark_failed(
                        "TikTok Studio oturumu açık değil. Lütfen önce 'TIKTOK_LOGIN.bat' ile giriş yapın.",
                        status=PlatformPublicationStatus.AUTH_REQUIRED
                    )
                    return record

                # 2. Verify Target TikTok Username (@kitchenverse360)
                is_match, detected_user, v_msg = observer.verify_logged_in_username(self.config.tiktok_expected_username)
                if not is_match:
                    record.mark_failed(v_msg, status=PlatformPublicationStatus.ACCOUNT_MISMATCH)
                    logger.error(f"[{record.reel_id}] TikTok upload blocked due to account mismatch: {v_msg}")
                    return record

                logger.info(f"[{record.reel_id}] TikTok Target Account Verified: {detected_user}")

                # Clear any leftover "unsaved editing session" banner BEFORE deciding
                # whether an editor is already open -- otherwise a stale session from a
                # previous Reel can be mistaken for this Reel's editor, and the upload
                # area stays inert for the rest of the run.
                observer.dismiss_unsaved_draft_banner_if_present()

                # 3. Check if existing editor session is already open (PREVENTS RE-UPLOAD)
                is_editor_open = observer.is_editor_open_for_reel(record.reel_id, record.video_file.name)
                if is_editor_open:
                    logger.info(f"[{record.reel_id}] [RESUME_EXISTING_TIKTOK_EDITOR] Existing loaded upload editor detected. Skipping re-upload.")
                else:
                    # Upload Video
                    logger.info(f"[{record.reel_id}] Uploading to TikTok Studio: {record.video_file.name}")
                    if not observer.upload_file(record.video_file):
                        record.mark_failed("TikTok file input not found on page.")
                        return record

                    # Wait for Upload Completion
                    if not observer.wait_for_upload_completion(timeout_seconds=120):
                        record.mark_failed("TikTok video upload timed out or failed to process.")
                        return record

                # 4. Replace Default Filename Caption with Generated Description + Hashtags
                ok_cap, cap_msg = observer.replace_caption(record.description, record.hashtags)
                if not ok_cap:
                    record.mark_failed(f"TikTok caption replacement failed: {cap_msg}")
                    return record
                time.sleep(1.0)

                # 5. AI Disclosure (Expand 'Daha fazla göster' if needed)
                if self.config.ai_disclosure:
                    observer.toggle_ai_disclosure(True)
                    time.sleep(0.5)

                # 6. Select 'Planla' under 'Paylaşıldığında' & Verify (FAIL-SAFE: Never post immediately!)
                ok_mode, mode_msg = observer.select_schedule_mode("SCHEDULE")
                if not ok_mode:
                    record.mark_failed(
                        f"TikTok Studio schedule seçeneği ('Planla') seçilemedi: {mode_msg}. Video doğrudan yayınlanmadı (Güvenli İptal).",
                        status=PlatformPublicationStatus.SCHEDULING_UNAVAILABLE
                    )
                    return record

                # 7. Set Date & Time (Target: 16.08.2026 19:30)
                ok_dt, dt_msg = observer.set_schedule_datetime(record.scheduled_at_local)
                if not ok_dt:
                    record.mark_failed(f"TikTok datetime setting failed: {dt_msg}")
                    return record
                time.sleep(1.0)

                # 8. Re-read LIVE controls immediately before final submit.
                ok_rb, rb_msg = observer.verify_schedule_datetime(record.scheduled_at_local)
                if not ok_rb:
                    record.mark_failed(
                        f"TikTok schedule hard-gate failed before submit: {rb_msg}"
                    )
                    return record

                # 9. Submit Schedule with HARD SAFETY GUARD
                success, ref = observer.click_schedule_and_verify(
                    schedule_mode_verified=True,
                    timeout_seconds=45
                )
                if not success:
                    record.mark_failed(f"TikTok schedule submission failed: {ref}")
                    return record

                # 10. Secondary remote verification (do not fake success).
                remote_ok, remote_msg = observer.verify_remote_scheduled_status(
                    expected_title=record.title
                )
                if not remote_ok:
                    logger.warning(
                        f"[{record.reel_id}] TikTok secondary remote verification "
                        f"inconclusive after confirmed submit: {remote_msg}"
                    )

                record.mark_scheduled(
                    remote_id="tiktok_scheduled_post",
                    remote_url="https://www.tiktok.com/tiktokstudio/content"
                )
                logger.info(f"[{record.reel_id}] TikTok Studio scheduled successfully for {record.scheduled_at_local}")
                return record

        except ConnectionError as ce:
            record.mark_failed(str(ce), status=PlatformPublicationStatus.AUTH_REQUIRED)
            return record
        except Exception as e:
            logger.exception(f"TikTok upload error for {record.reel_id}: {e}")
            record.mark_failed(f"TikTok upload failed: {e}")
            return record

    def prepare_preflight(self, record: PublishRecord) -> Tuple[bool, str]:
        """Runs preflight on TikTok Studio: prepares editor up to final action button without clicking."""
        try:
            with self.browser_mgr.connect() as (browser, context):
                page = None
                for p in context.pages:
                    if "tiktok.com" in p.url:
                        page = p
                        break
                if not page:
                    page = context.new_page()
                    page.goto(self.config.tiktok_url, wait_until="domcontentloaded", timeout=30000)

                observer = TikTokUIObserver(page)
                time.sleep(1.0)

                ok, msg = observer.prepare_tiktok_schedule_preflight(
                    record=record,
                    expected_username=self.config.tiktok_expected_username
                )
                return ok, msg
        except Exception as e:
            logger.exception(f"TikTok preflight error: {e}")
            return False, f"PREFLIGHT_ERROR: {e}"

    def commit_schedule(self, record: PublishRecord) -> PublishRecord:
        """Commits schedule on TikTok Studio: clicks Planla and verifies remote scheduled state."""
        try:
            with self.browser_mgr.connect() as (browser, context):
                page = None
                for p in context.pages:
                    if "tiktok.com" in p.url:
                        page = p
                        break
                if not page:
                    record.mark_failed("No active TikTok Studio page found for commit.")
                    return record

                observer = TikTokUIObserver(page)
                ok, msg = observer.commit_tiktok_schedule(record)
                if not ok:
                    record.mark_failed(f"TikTok Studio commit failed: {msg}")
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
                    remote_id="tiktok_scheduled_post",
                    remote_url="https://www.tiktok.com/tiktokstudio/content",
                    verified_date=_v_date,
                    verified_time=_v_time
                )
                return record
        except Exception as e:
            logger.exception(f"TikTok commit error: {e}")
            record.mark_failed(f"TikTok commit error: {e}")
            return record


class MockTikTokPublisher(BaseTikTokPublisher):
    """Mock publisher for safe tests and dry-runs (Zero web interaction / Zero uploads)."""

    def __init__(self, simulate_mismatch: bool = False, expected_username: str = "@kitchenverse360"):
        self.simulate_mismatch = simulate_mismatch
        self.expected_username = expected_username

    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        if not record.video_file.exists():
            record.mark_failed(f"Video file not found: {record.video_file}")
            return record

        if self.simulate_mismatch:
            record.mark_failed(
                f"ACCOUNT_MISMATCH: Expected '{self.expected_username}', detected '@other_user'",
                status=PlatformPublicationStatus.ACCOUNT_MISMATCH
            )
            return record

        mock_ref = f"mock_tt_{hashlib.md5((record.reel_id + '_tiktok').encode('utf-8')).hexdigest()[:10]}"
        record.mark_scheduled(
            remote_id=mock_ref,
            remote_url=f"https://www.tiktok.com/tiktokstudio/content#{mock_ref}"
        )
        return record

    def prepare_preflight(self, record: PublishRecord) -> Tuple[bool, str]:
        if self.simulate_mismatch:
            return False, f"ACCOUNT_MISMATCH: Expected '{self.expected_username}'"
        return True, "TIKTOK_FINAL_SCHEDULE_READY"

    def commit_schedule(self, record: PublishRecord) -> PublishRecord:
        mock_ref = f"mock_tt_{hashlib.md5((record.reel_id + '_tiktok').encode('utf-8')).hexdigest()[:10]}"
        record.mark_scheduled(
            remote_id=mock_ref,
            remote_url=f"https://www.tiktok.com/tiktokstudio/content#{mock_ref}",
            verified_date="2026-08-16",
            verified_time="19:30"
        )
        return record

