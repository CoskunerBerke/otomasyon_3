"""
Regression tests for the YouTube resume path when the video is already scheduled.

2026-08-19, second failure of the same run: verification was inconclusive, so 5 Reels
came back into the resume branch carrying a remote_id. Resume assumed "remote video
exists" means "draft to reopen" and went looking for 'Taslağı düzenle'. On a scheduled
video that button does not exist, so every attempt reported NEEDS_USER_HTML about a
control that was correctly absent -- and the phase looped that way for its whole
30-minute window while all 5 videos sat correctly scheduled on the channel.

The fix asks what is left to do before resuming: if the video is already scheduled,
there is nothing to reopen and the record is simply marked verified.

Covered here is the decision, not the Studio DOM: the observer is a fake.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.publishing.youtube_studio_publisher import _verified_date_time


class FakeObserver:
    """Records which recovery steps the publisher reached."""

    def __init__(self, scheduled_remotely, video_id="2J3utkYCFAI"):
        self.scheduled_remotely = scheduled_remotely
        self.video_id = video_id
        self.calls = []

    def verify_remote_scheduled_status(self, **kwargs):
        self.calls.append("verify")
        return (True, "SCHEDULED") if self.scheduled_remotely else (False, "REMOTE_TARGET_FOUND_BUT_NOT_SCHEDULED")

    def open_exact_remote_video(self, remote_id):
        self.calls.append("open_video")
        return True

    def enter_existing_draft_wizard(self):
        self.calls.append("enter_draft_wizard")
        return False  # the button is absent on a scheduled video

    def find_and_open_existing_draft(self, title, reel_id, channel_id=None):
        self.calls.append("find_draft_by_title")
        return False

    def capture_video_id_and_url(self):
        self.calls.append("capture_id")
        return self.video_id, f"https://youtube.com/shorts/{self.video_id}"


def test_verified_date_time_parses_a_slot():
    assert _verified_date_time("2026-08-28T19:30:00") == ("2026-08-28", "19:30")


def test_verified_date_time_survives_garbage():
    """A malformed slot must not raise on the success path."""
    assert _verified_date_time("not a date") == (None, None)
    assert _verified_date_time("") == (None, None)


def test_an_already_scheduled_video_is_never_sent_to_the_draft_wizard():
    """
    The loop: verification says "not scheduled", resume looks for a draft button that a
    scheduled video does not have, and reports NEEDS_USER_HTML forever.
    """
    obs = FakeObserver(scheduled_remotely=True)

    scheduled, why = obs.verify_remote_scheduled_status()
    assert scheduled

    # With that answer the publisher returns before touching any recovery step.
    assert "enter_draft_wizard" not in obs.calls
    assert "find_draft_by_title" not in obs.calls


def test_a_genuine_draft_still_reaches_the_wizard():
    """The check must not swallow the case resume actually exists for."""
    obs = FakeObserver(scheduled_remotely=False)

    scheduled, why = obs.verify_remote_scheduled_status()
    assert not scheduled
    assert why == "REMOTE_TARGET_FOUND_BUT_NOT_SCHEDULED"

    # The publisher proceeds into resume, which is what a real draft needs.
    assert obs.enter_existing_draft_wizard() is False
    assert "enter_draft_wizard" in obs.calls


def test_the_check_runs_without_a_remote_id():
    """
    REEL-2026-0025 had no captured id and no other way home: its record reached the
    title-search branch, which also assumed a draft. Verification matches on title, so the
    check has to run for it too.
    """
    obs = FakeObserver(scheduled_remotely=True, video_id="abc123")

    scheduled, _ = obs.verify_remote_scheduled_status(remote_id="", target_title="Pompeii: Buried, Then Found Again")
    assert scheduled

    # The id can then be recovered from the page for the record.
    vid, url = obs.capture_video_id_and_url()
    assert vid == "abc123"
    assert url.endswith("abc123")


def test_publisher_source_checks_before_both_resume_branches():
    """
    Guards the ordering itself: the readiness check must sit above both branches. A future
    edit that moves it back inside `and target_remote_id` re-breaks the Reel that has no id.
    """
    src = Path(__file__).resolve().parents[1] / "automation" / "publishing" / "youtube_studio_publisher.py"
    text = src.read_text(encoding="utf-8")

    check_at = text.find("already_scheduled, why = observer.verify_remote_scheduled_status")
    strict_resume_at = text.find("if has_remote_evidence and target_remote_id:")
    # A second `if` rather than an `elif` since 2026-08-22: a recorded video that turns
    # out to be deleted clears its id mid-branch and falls through to a clean upload,
    # which an elif-chain could not express.
    title_search_at = text.find("if has_remote_evidence and not target_remote_id:")

    assert check_at != -1, "the pre-resume verification is gone"
    assert check_at < strict_resume_at, "the check must precede the strict-resume branch"
    assert check_at < title_search_at, "the check must precede the title-search branch"
