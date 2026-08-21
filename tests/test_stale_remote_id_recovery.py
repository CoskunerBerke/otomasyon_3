"""
Regression tests for a recorded remote video that no longer exists.

2026-08-21: seven Reels were uploaded three times over and the operator deleted the
fourteen duplicates by hand. The cleanup cleared progress.json but not the publisher's
own record store, whose merge_with_existing states outright that existing remote
evidence ALWAYS WINS. So on 2026-08-22 all seven Reels resumed onto the deleted id
VTMhhYTl9Co:

  * open_exact_remote_video() returned True because page.goto() had not raised -- but
    Studio was rendering "Maalesef bir hata olustu" where the editor should have been;
  * the publisher then hunted for 'Taslagi duzenle' on that error placeholder and
    reported NEEDS_USER_HTML about a button that was correctly absent;
  * nothing was uploaded, and the pipeline recorded the same deleted id onto all seven
    Reels a second time, because the collision guard only covered success statuses.

Four days of slots stayed empty while every state file claimed the work had been sent.

Covered here is the decision, not the Studio DOM: page and observer are fakes.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.publishing.youtube_studio_selectors import YouTubeStudioSelectors
from automation.publishing.youtube_studio_ui_observer import (
    VIDEO_EDIT_PAGE_WAIT_SECONDS,
    YouTubeStudioUIObserver,
)


# --------------------------------------------------------------------------
# open_exact_remote_video: navigation is not proof
# --------------------------------------------------------------------------

class FakeLocator:
    def __init__(self, visible):
        self._visible = visible

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return self._visible


class FakePage:
    """A Studio page that either mounts the editor or renders the error placeholder."""

    def __init__(self, editor_mounts):
        self.editor_mounts = editor_mounts
        self.goto_urls = []

    def goto(self, url, **kwargs):
        self.goto_urls.append(url)

    def locator(self, selector):
        return FakeLocator(self.editor_mounts)


def _observer(page):
    obs = YouTubeStudioUIObserver.__new__(YouTubeStudioUIObserver)
    obs.page = page
    obs.current_remote_id = None
    obs._active_wizard_dialog = None
    return obs


def test_a_deleted_video_is_not_reported_as_opened(monkeypatch):
    """The exact 2026-08-22 failure: an error placeholder read as a live editor."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    page = FakePage(editor_mounts=False)

    assert _observer(page).open_exact_remote_video("VTMhhYTl9Co") is False
    assert page.goto_urls == ["https://studio.youtube.com/video/VTMhhYTl9Co/edit"]


def test_a_live_video_still_opens(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    assert _observer(FakePage(editor_mounts=True)).open_exact_remote_video("A_-ciGRmRQc") is True


def test_the_editor_is_given_time_to_mount():
    """
    Concluding "deleted" too early would send a live Reel back to a fresh upload and put
    a second copy on the channel -- the failure this whole file exists to prevent.
    """
    assert VIDEO_EDIT_PAGE_WAIT_SECONDS >= 20, "the editor mounts well after domcontentloaded"


def test_edit_page_proof_keeps_two_safe_strategies():
    """Kural 31: at most two semantic strategies for one UI question."""
    strategies = YouTubeStudioSelectors.VIDEO_EDIT_PAGE_READY
    assert len(strategies) <= 2
    joined = " ".join(strategies)
    for banned in ("force", "dispatchEvent", "pointer-events"):
        assert banned not in joined


# --------------------------------------------------------------------------
# The publisher: a vanished video demotes to a clean upload
# --------------------------------------------------------------------------

class FakeObserver:
    """Studio with the recorded video deleted and nothing scheduled under this title."""

    def __init__(self, editor_mounts=False):
        self.editor_mounts = editor_mounts
        self.calls = []

    def is_logged_in(self):
        return True

    def verify_logged_in_channel(self, **kwargs):
        return True, "@craftsbyman", "OK"

    def verify_remote_scheduled_status(self, **kwargs):
        self.calls.append("verify")
        return False, "REMOTE_SCHEDULE_NOT_VERIFIED"

    def open_exact_remote_video(self, remote_id):
        self.calls.append("open_video")
        return self.editor_mounts

    def enter_existing_draft_wizard(self):
        self.calls.append("enter_draft_wizard")
        return False

    def find_and_open_existing_draft(self, *a, **k):
        self.calls.append("find_draft_by_title")
        return False

    def upload_file(self, video_file):
        self.calls.append("upload_file")
        return False  # stop the run here; reaching this point is the assertion

    def capture_video_id_and_url(self):
        return None, None


def _publisher_with(monkeypatch, tmp_path, observer):
    from automation.publishing import youtube_studio_publisher as mod
    from automation.publishing.config import PublishingConfig
    from automation.publishing.repository import PublishingRepository

    monkeypatch.setattr(mod, "YouTubeStudioUIObserver", lambda page: observer)
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    class FakePageStub:
        url = "https://studio.youtube.com"

        def goto(self, *a, **k):
            pass

    class FakeCtx:
        pages = []

        def new_page(self):
            return FakePageStub()

    class FakeConnect:
        def __enter__(self):
            return (None, FakeCtx())

        def __exit__(self, *exc):
            return False

    pub = mod.YouTubeStudioPublisher.__new__(mod.YouTubeStudioPublisher)
    pub.config = PublishingConfig()
    pub.repo = PublishingRepository(tmp_path)
    pub.browser_mgr = type("BM", (), {"connect": lambda self: FakeConnect()})()
    return pub


def _stale_record(tmp_path):
    from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord

    video = tmp_path / "clean_clean_CBM-REEL-2026-0001_aircraft-garden-hidden.mp4"
    video.write_bytes(b"0" * 64)
    return PublishRecord(
        publish_id="PUB-CBM-REEL-2026-0001-YOUTUBE",
        batch_id="CBM-2026-W34",
        reel_id="CBM-REEL-2026-0001",
        platform=Platform.YOUTUBE,
        video_sha256="0" * 64,
        account_handle="@craftsbyman",
        title="Constructing A Plane Went Into the Ground",
        description="An aircraft fuselage buried behind a farmhouse",
        hashtags=["#Shorts"],
        video_file=video,
        scheduled_at_local="2026-08-22 19:30:00",
        scheduled_at_utc="2026-08-22 16:30:00",
        status=PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED,
        remote_id="VTMhhYTl9Co",
        remote_url="https://www.youtube.com/watch?v=VTMhhYTl9Co",
        upload_started=True,
        remote_draft_exists=True,
        dry_run=False,
    )


def test_a_deleted_recorded_video_falls_back_to_uploading(monkeypatch, tmp_path):
    """
    Before: resume onto the deleted id, fail to find 'Taslagi duzenle', report
    NEEDS_USER_HTML, upload nothing -- forever, on every rerun.
    """
    obs = FakeObserver(editor_mounts=False)
    pub = _publisher_with(monkeypatch, tmp_path, obs)

    result = pub.upload_and_schedule(_stale_record(tmp_path))

    assert "upload_file" in obs.calls, "a video that no longer exists must be uploaded again"
    assert "enter_draft_wizard" not in obs.calls, "no draft wizard hunt on an error placeholder"
    assert result.remote_id in (None, ""), "the deleted id must not survive in the record"


def test_a_live_recorded_video_is_never_re_uploaded(monkeypatch, tmp_path):
    """The other half of the guard: resume must still forbid uploading."""
    obs = FakeObserver(editor_mounts=True)
    pub = _publisher_with(monkeypatch, tmp_path, obs)

    pub.upload_and_schedule(_stale_record(tmp_path))

    assert "upload_file" not in obs.calls, "STRICT RESUME: an existing video is never re-uploaded"
    assert "enter_draft_wizard" in obs.calls


# --------------------------------------------------------------------------
# The pipeline: one id may never be recorded onto two Reels
# --------------------------------------------------------------------------

def test_a_shared_remote_id_is_refused_on_the_soft_failure_path():
    """
    The guard used to run only for SCHEDULED/PUBLISHED, so SCHEDULE_RESUME_REQUIRED --
    which is what a failed resume returns -- wrote the deleted id onto all seven Reels.
    """
    import inspect
    from automation import simple_weekly_pipeline as swp

    src = inspect.getsource(swp.SimpleWeeklyPipeline._run_platform_phase)
    before_guard = src.split("_reel_already_using_remote_id")[0]
    condition = "\n".join(before_guard.rstrip().splitlines()[-6:])

    assert "if res_rec.remote_id:" in condition, (
        "the collision guard must cover every returned id, not just successful ones"
    )
    assert "PLATFORM_SUCCESS_STATUSES" not in condition, (
        "gating the guard on success is what let the stale id through"
    )
