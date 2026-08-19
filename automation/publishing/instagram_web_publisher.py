"""
Instagram web publisher -- drives instagram.com's own native scheduling flow.

Instagram's Graph API has no scheduled-publish parameter, so the cloud path can only
publish a Reel when its moment arrives, and nothing shows up in the account's scheduled
queue in the meantime. The web composer does expose real scheduling ("İçeriği planla" ->
date + time -> "Planla"), which lands the post in instagram.com/scheduled_content/ just
like YouTube Studio and TikTok Studio do.

This wraps InstagramWebObserver -- which already knows the whole flow, including the
Kural 31 guards -- into the shape the weekly pipeline expects: one Reel in, a status and
a reason out, one composer session per Reel.

Safety, all inherited from the observer and re-stated here because this is the module
that actually runs in production:
  * The schedule toggle is verified ON immediately before the final click. With it OFF
    the same primary control reads "Paylaş" and posts instantly.
  * Any share-now wording on that control aborts the click (PUBLISH_NOW_BUTTON_REFUSED).
  * A slot under Instagram's 20-minute minimum is refused before submitting.
  * Nothing is ever deleted or modified remotely.
"""
import datetime
import logging
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .instagram_web_browser import InstagramWebBrowserManager
from .instagram_web_observer import InstagramWebObserver
from .instagram_web_selectors import InstagramWebSelectors

logger = logging.getLogger("ReelsAIFactory.InstagramWebPublisher")

SCHEDULED_CONTENT_URL = "https://www.instagram.com/scheduled_content/"

# How long to let instagram.com finish mounting before deciding the composer entry point
# is not there. The weekly run usually opens this Chrome cold -- the profile sits unused
# until the Instagram phase -- and instagram.com paints its shell well before the page is
# interactive. Flow failed exactly this way on 2026-08-19: a button that was merely late
# was reported as missing. 45s is generous on purpose; it costs nothing when the page is
# quick, and the alternative is failing all 14 Reels on a slow first load.
APP_READY_TIMEOUT_SECONDS = 45


class BaseInstagramWebPublisher:
    """Interface the weekly pipeline codes against."""

    def schedule_reel(
        self,
        video_path: Path,
        caption: str,
        hashtags: List[str],
        scheduled_at_local: str,
        reel_id: str,
    ) -> Tuple[str, Optional[str]]:
        """Returns (status, error). Status "SCHEDULED" means Instagram confirmed it."""
        raise NotImplementedError


class InstagramWebPublisher(BaseInstagramWebPublisher):
    """Real instagram.com composer driver."""

    def __init__(self, browser_manager: Optional[InstagramWebBrowserManager] = None):
        self.browser_manager = browser_manager or InstagramWebBrowserManager()

    def schedule_reel(
        self,
        video_path: Path,
        caption: str,
        hashtags: List[str],
        scheduled_at_local: str,
        reel_id: str,
    ) -> Tuple[str, Optional[str]]:
        video_path = Path(video_path)
        if not video_path.exists():
            return "FAILED_FATAL", f"Video file missing on disk: {video_path}"

        try:
            target = datetime.datetime.strptime(scheduled_at_local, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            return "FAILED_FATAL", f"Unparseable scheduled_at_local: {scheduled_at_local!r}"

        # Checked before opening a composer at all: Instagram rejects these inline and
        # the session would be wasted walking the whole flow to find that out.
        if InstagramWebObserver.is_slot_too_soon(target):
            return "FAILED_FATAL", "TIME_TOO_SOON: slot is under Instagram's 20-minute minimum"

        with self.browser_manager.connect() as (_browser, context):
            page = context.pages[0] if context.pages else context.new_page()
            obs = InstagramWebObserver(page)
            return self._run_composer(obs, page, video_path, caption, hashtags, target, reel_id)

    @staticmethod
    def _wait_for_page_ready(page: Any, timeout_seconds: int) -> bool:
        """
        Wait until the composer entry point is actually on screen.

        goto(wait_until="domcontentloaded") returns when the HTML is parsed, which on a
        cold Chrome is long before instagram.com is interactive. Looking for the button
        in that window finds nothing and is indistinguishable from a changed UI.
        """
        deadline = time.time() + timeout_seconds
        selector = InstagramWebSelectors.OPEN_COMPOSER_BUTTONS[0]
        while time.time() < deadline:
            try:
                if page.locator(selector).first.is_visible(timeout=1000):
                    return True
            except Exception:
                pass
            time.sleep(1.0)
        return False

    def _run_composer(
        self,
        obs: InstagramWebObserver,
        page: Any,
        video_path: Path,
        caption: str,
        hashtags: List[str],
        target: datetime.datetime,
        reel_id: str,
    ) -> Tuple[str, Optional[str]]:
        """
        Walks the composer once. Every step must succeed: a half-filled composer is
        abandoned rather than submitted, because submitting one is how a Reel gets
        scheduled with no caption, the wrong date, or the AI label missing.
        """
        try:
            page.goto(SCHEDULED_CONTENT_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            return "FAILED_RETRYABLE", f"Could not open {SCHEDULED_CONTENT_URL}: {e}"

        if not self._wait_for_page_ready(page, APP_READY_TIMEOUT_SECONDS):
            obs.capture_error_snapshot(f"{reel_id}_page_never_became_ready")
            return "FAILED_RETRYABLE", (
                "PAGE_NOT_READY: instagram.com/scheduled_content/ did not finish loading "
                f"within {APP_READY_TIMEOUT_SECONDS}s (the composer entry point never appeared)"
            )

        steps = [
            ("OPEN_COMPOSER", lambda: obs.open_composer()),
            ("UPLOAD_FILE", lambda: obs.upload_file(video_path)),
            ("ADVANCE_TO_CAPTION", lambda: obs.advance_to_caption_step()),
            ("FILL_CAPTION", lambda: obs.fill_caption(caption, hashtags)),
            # Required disclosure for AI-generated media -- see commit 51d2254.
            ("ENABLE_AI_LABEL", lambda: obs.enable_ai_label()),
            ("ENABLE_SCHEDULE", lambda: obs.enable_schedule()),
        ]

        for name, action in steps:
            try:
                ok = action()
            except Exception as e:
                obs.capture_error_snapshot(f"{reel_id}_{name.lower()}_exception")
                return "FAILED_RETRYABLE", f"{name}_EXCEPTION: {e}"
            if not ok:
                obs.capture_error_snapshot(f"{reel_id}_{name.lower()}_failed")
                return "FAILED_RETRYABLE", name

        ok, reason = obs.select_date(target)
        if not ok:
            obs.capture_error_snapshot(f"{reel_id}_select_date_failed")
            return "FAILED_RETRYABLE", f"SELECT_DATE_FAILED: {reason}"

        if not obs.set_time(target.hour, target.minute):
            obs.capture_error_snapshot(f"{reel_id}_set_time_failed")
            return "FAILED_RETRYABLE", "SET_TIME_FAILED"

        # Read the form back before submitting. The pickers can silently land on a
        # neighbouring value, and a wrong date here means a Reel published on the wrong day.
        if not obs.verify_date(target):
            obs.capture_error_snapshot(f"{reel_id}_date_verify_failed")
            return "FAILED_RETRYABLE", "DATE_VERIFICATION_FAILED"

        if not obs.verify_time(target.hour, target.minute):
            obs.capture_error_snapshot(f"{reel_id}_time_verify_failed")
            return "FAILED_RETRYABLE", "TIME_VERIFICATION_FAILED"

        ok, reason = obs.click_schedule_and_verify()
        if ok:
            logger.info(f"[IG WEB] {reel_id} planlandi: {target.strftime('%Y-%m-%d %H:%M')}")
            return "SCHEDULED", None

        # PUBLISH_NOW_BUTTON_REFUSED and SCHEDULE_MODE_NOT_ACTIVE are refusals to click a
        # share-now control, not transient errors -- retrying would re-run the same risk.
        if reason in ("PUBLISH_NOW_BUTTON_REFUSED", "SCHEDULE_MODE_NOT_ACTIVE", "SCHEDULE_BUTTON_NOT_FOUND"):
            return "FAILED_FATAL", reason
        return "FAILED_RETRYABLE", reason


class MockInstagramWebPublisher(BaseInstagramWebPublisher):
    """Dry-run stand-in. Opens no browser and touches no account."""

    def __init__(self):
        self.scheduled: List[Tuple[str, str]] = []

    def schedule_reel(
        self,
        video_path: Path,
        caption: str,
        hashtags: List[str],
        scheduled_at_local: str,
        reel_id: str,
    ) -> Tuple[str, Optional[str]]:
        if not Path(video_path).exists():
            return "FAILED_FATAL", f"Video file missing on disk: {video_path}"
        self.scheduled.append((reel_id, scheduled_at_local))
        logger.info(f"[IG WEB MOCK] {reel_id} planlandi (simulasyon): {scheduled_at_local}")
        return "SCHEDULED", None
