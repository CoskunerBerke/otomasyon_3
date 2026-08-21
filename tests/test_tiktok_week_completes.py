"""
Regression tests for finishing a whole week on TikTok.

Two defects sat between craftsbyman and its first complete TikTok week, and neither
would have shown up until the run was already live on a real account.

1. TikTok's scheduler hands back no per-post id, so the publisher records the fixed
   marker "tiktok_scheduled_post" on every Reel. The week-level collision guard added on
   2026-08-21 compares recorded ids literally, so Reel 2 would have been refused as
   REEL_ID_MEDIA_MISMATCH against Reel 1 -- both of them correctly scheduled -- and the
   platform would have stopped there. Every week, on its second Reel.

2. The login helper opened TikTok's other upload URL, so the one-time new-account tour
   that blocks the caption editor was never met on the page the publisher actually
   drives. That tour is what stopped CBM-REEL-2026-0001 on 2026-08-21, and it appears
   once per account and never again -- there is no second chance to capture it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]


def test_tiktoks_fixed_marker_is_not_treated_as_a_collision():
    """Reel 2 must not be refused for carrying the same marker as Reel 1."""
    from automation.simple_weekly_pipeline import NON_IDENTIFYING_REMOTE_IDS

    assert "tiktok_scheduled_post" in NON_IDENTIFYING_REMOTE_IDS


def test_the_marker_the_publisher_records_is_the_one_exempted():
    """
    The exemption is a literal string, so it silently stops matching if the publisher
    ever renames its marker -- and the week would break on Reel 2 again.
    """
    from automation.simple_weekly_pipeline import NON_IDENTIFYING_REMOTE_IDS

    src = (REPO / "automation" / "publishing" / "tiktok_publisher.py").read_text(encoding="utf-8")
    # Literal ids only. The mock publisher derives its id per Reel, so it is genuinely
    # identifying and must NOT be exempt.
    recorded = {
        line.split('remote_id="', 1)[1].split('"', 1)[0]
        for line in src.splitlines()
        if 'remote_id="' in line
    }
    assert recorded, "the publisher no longer records a remote_id at all"
    assert recorded <= set(NON_IDENTIFYING_REMOTE_IDS), (
        f"TikTok records {recorded - set(NON_IDENTIFYING_REMOTE_IDS)}, which the week-level "
        f"collision guard would read as one Reel stealing another's video"
    )


def test_a_real_youtube_id_is_still_guarded():
    """The exemption must not become a hole: real per-video ids still collide."""
    from automation.simple_weekly_pipeline import NON_IDENTIFYING_REMOTE_IDS

    assert "VTMhhYTl9Co" not in NON_IDENTIFYING_REMOTE_IDS
    assert "A_-ciGRmRQc" not in NON_IDENTIFYING_REMOTE_IDS


def test_the_collision_guard_consults_the_exemption():
    """Guards the wiring, not just the constant."""
    import inspect
    from automation import simple_weekly_pipeline as swp

    src = inspect.getsource(swp.SimpleWeeklyPipeline._run_platform_phase)
    before_guard = src.split("_reel_already_using_remote_id")[0]
    condition = "\n".join(before_guard.rstrip().splitlines()[-6:])

    assert "NON_IDENTIFYING_REMOTE_IDS" in condition
    assert "if res_rec.remote_id" in condition


def test_login_lands_on_the_page_the_publisher_drives():
    """
    The new-account tour appears once, on the upload page the automation uses. Opening a
    different URL for the human means they dismiss nothing the automation will meet.
    """
    from automation.publishing.config import PublishingConfig

    src = (REPO / "automation" / "publishing" / "brand_login.py").read_text(encoding="utf-8")
    assert "launch_chrome_for_tiktok(start_url=PublishingConfig().tiktok_url)" in src, (
        "the login helper must open the publisher's own TikTok upload URL"
    )
    assert PublishingConfig().tiktok_url.startswith("https://www.tiktok.com/")


# --------------------------------------------------------------------------
# The upload area is built after the page loads
# --------------------------------------------------------------------------

class _Loc:
    def __init__(self, present):
        self.present = present
        self.files = None

    @property
    def first(self):
        return self

    def count(self):
        return 1 if self.present else 0

    def set_input_files(self, path):
        self.files = path

    def is_visible(self, timeout=None):
        return False

    def is_enabled(self):
        return False


class SlowUploadPage:
    """The file input mounts only after `mounts_after` passes over the selectors."""

    def __init__(self, mounts_after):
        self.mounts_after = mounts_after
        self.looks = 0

    def locator(self, selector):
        if "input[type='file']" in selector:
            self.looks += 1
            return _Loc(self.looks > self.mounts_after)
        return _Loc(False)


def _tiktok_observer(page):
    from automation.publishing.tiktok_ui_observer import TikTokUIObserver

    obs = TikTokUIObserver.__new__(TikTokUIObserver)
    obs.page = page
    obs.dismiss_unsaved_draft_banner_if_present = lambda *a, **k: (True, "NO_BANNER")
    return obs


def test_the_upload_area_is_waited_for_not_read_once(monkeypatch, tmp_path):
    """
    Eleven Reels were already scheduled when the twelfth reported "file input not found"
    and stopped the week. The control was not absent -- the page had not built it yet.
    """
    import time as _time
    from automation.publishing import tiktok_ui_observer as mod

    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 16)

    page = SlowUploadPage(mounts_after=8)
    assert _tiktok_observer(page).upload_file(video) is True


def test_a_genuinely_missing_upload_area_still_fails(monkeypatch, tmp_path):
    """Patience must not become an infinite wait that hides a real breakage."""
    from automation.publishing import tiktok_ui_observer as mod

    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)
    monkeypatch.setattr(mod, "FILE_INPUT_WAIT_SECONDS", 0.0)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 16)

    assert _tiktok_observer(SlowUploadPage(mounts_after=10**9)).upload_file(video) is False


def test_the_upload_wait_is_generous_enough():
    from automation.publishing.tiktok_ui_observer import FILE_INPUT_WAIT_SECONDS

    assert FILE_INPUT_WAIT_SECONDS >= 15


# --------------------------------------------------------------------------
# Verification reads what TikTok actually displays
# --------------------------------------------------------------------------

def test_schedule_verification_matches_the_caption_not_the_title():
    """
    TikTok's content list prints the caption that was written into the post. The title is
    the YouTube headline and shares almost no words with it, so verifying against it
    reported "not verified" for three correctly scheduled Reels on 2026-08-22 -- and
    passed for the other eleven only because their two texts happened to share a word.
    """
    src = (REPO / "automation" / "publishing" / "tiktok_publisher.py").read_text(encoding="utf-8")
    assert "expected_title=record.description or record.title" in src, (
        "verification must match the text TikTok shows, which is the caption"
    )


def test_the_caption_verified_against_is_the_caption_written():
    """The written text and the verified text must come from the same field."""
    src = (REPO / "automation" / "publishing" / "tiktok_publisher.py").read_text(encoding="utf-8")
    assert "observer.replace_caption(record.description, record.hashtags)" in src


# --------------------------------------------------------------------------
# The final Schedule click, on a page that is still settling
# --------------------------------------------------------------------------

def test_the_schedule_button_is_given_time_to_stop_moving():
    """
    CBM-REEL-2026-0013 came back FAILED on 2026-08-22 with its video uploaded, its caption
    written, its slot set to 28 Aug 19:30 and both of TikTok's checks green. The only
    thing wrong was that the button was still moving -- the content checks finishing
    reflows the page under it -- and it was given 1.5s to hold still.
    """
    from automation.publishing.tiktok_ui_observer import (
        SCHEDULE_BUTTON_SETTLE_MS,
        SCHEDULE_CLICK_TIMEOUT_MS,
    )

    assert SCHEDULE_BUTTON_SETTLE_MS >= 8000, "a reflowing page needs more than a moment"
    assert SCHEDULE_CLICK_TIMEOUT_MS >= 5000


def test_a_failed_scroll_does_not_cancel_the_click():
    """Scrolling is a convenience; the button is clickable where it sits."""
    src = (REPO / "automation" / "publishing" / "tiktok_ui_observer.py").read_text(encoding="utf-8")
    body = src.split("def click_schedule_and_verify")[1].split("\n    def ")[0]

    scroll_at = body.find("scroll_into_view_if_needed(timeout=")
    click_at = body.find("submit_btn.click(")
    assert scroll_at != -1 and click_at != -1

    between = body[scroll_at:click_at]
    assert "except Exception" in between, "the scroll must be caught on its own"
    assert "return False" not in between, "a scroll that fails must not end the submit"


def test_a_raised_click_still_gets_its_second_attempt():
    """
    The submit loop runs twice by design. Returning on the first exception skipped both
    the success check -- which is the only thing entitled to say whether the click landed
    -- and the retry.
    """
    src = (REPO / "automation" / "publishing" / "tiktok_ui_observer.py").read_text(encoding="utf-8")
    body = src.split("def click_schedule_and_verify")[1].split("\n    def ")[0]

    assert "SCHEDULE_CLICK_FAILED" not in body, (
        "a raised click is no longer a verdict on its own"
    )
    assert "max_attempts = 2" in body, "the retry this depends on must still exist"


def test_the_submit_still_fails_when_nothing_confirms_it():
    """Patience must not become a false success: an unconfirmed submit still fails."""
    src = (REPO / "automation" / "publishing" / "tiktok_ui_observer.py").read_text(encoding="utf-8")
    body = src.split("def click_schedule_and_verify")[1].split("\n    def ")[0]

    assert 'return False, "TIKTOK_SCHEDULE_CONFIRMATION_TIMEOUT"' in body
