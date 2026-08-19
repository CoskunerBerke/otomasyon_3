"""
Regression tests for the Instagram web delivery route -- scheduling through
instagram.com's own composer instead of handing the media to the cloud worker.

The property that matters most is that the two routes are mutually exclusive. Instagram
is the one platform with two working paths, and running both against the same Reel
schedules the post in the composer AND lets the worker publish it again at the same
moment -- two copies of every video, on a real account, not undoable by this system
(CLAUDE.md forbids deleting remote content automatically).

The rest guards the composer flow itself: a half-filled form is abandoned rather than
submitted, and a share-now control is never clicked.

No real browser and no real account -- the publisher is faked at the observer boundary.
"""
import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.content.content_modes import NARRATIVE_AMBIENT_STORY
from automation.orchestration.batch_manifest import BatchManifest, BatchReel, BatchRepository
from automation.publishing.instagram_web_publisher import (
    InstagramWebPublisher,
    MockInstagramWebPublisher,
)
from automation.simple_weekly_pipeline import (
    INSTAGRAM_DELIVERY_CLOUD,
    INSTAGRAM_DELIVERY_WEB,
    INSTAGRAM_TERMINAL_STATUSES,
    SimpleWeeklyPipeline,
)


class RecordingPublisher(MockInstagramWebPublisher):
    """Mock that can be told to fail, and remembers every call."""

    def __init__(self, result=("SCHEDULED", None), fail_on=None):
        super().__init__()
        self.result = result
        self.fail_on = fail_on or {}
        self.calls = []

    def schedule_reel(self, video_path, caption, hashtags, scheduled_at_local, reel_id):
        self.calls.append(reel_id)
        if reel_id in self.fail_on:
            return self.fail_on[reel_id]
        return self.result


class FakeObserver:
    """Stands in for InstagramWebObserver, recording which steps ran."""

    def __init__(self, fail_step=None, schedule_result=(True, "INSTAGRAM_SCHEDULED"),
                 date_ok=True, time_ok=True):
        self.fail_step = fail_step
        self.schedule_result = schedule_result
        self.date_ok = date_ok
        self.time_ok = time_ok
        self.steps = []
        self.snapshots = []

    def _run(self, name):
        self.steps.append(name)
        return self.fail_step != name

    def open_composer(self):
        return self._run("open_composer")

    def upload_file(self, path):
        return self._run("upload_file")

    def advance_to_caption_step(self):
        return self._run("advance_to_caption_step")

    def fill_caption(self, caption, hashtags=None):
        return self._run("fill_caption")

    def enable_ai_label(self):
        return self._run("enable_ai_label")

    def enable_schedule(self):
        return self._run("enable_schedule")

    def select_date(self, target):
        self.steps.append("select_date")
        return (self.fail_step != "select_date"), "reason"

    def set_time(self, hour, minute):
        return self._run("set_time")

    def verify_date(self, target):
        self.steps.append("verify_date")
        return self.date_ok

    def verify_time(self, hour, minute):
        self.steps.append("verify_time")
        return self.time_ok

    def click_schedule_and_verify(self, timeout_seconds=30):
        self.steps.append("click_schedule_and_verify")
        return self.schedule_result

    def capture_error_snapshot(self, tag):
        self.snapshots.append(tag)


class FakePage:
    def __init__(self, goto_fails=False):
        self.goto_fails = goto_fails
        self.url = None

    def goto(self, url, **kwargs):
        if self.goto_fails:
            raise RuntimeError("navigation blocked")
        self.url = url


@pytest.fixture
def video(tmp_path):
    f = tmp_path / "clean_REEL-2026-0025_pompeii-story.mp4"
    f.write_bytes(b"video" * 512)
    return f


def _future_slot(days=3):
    return (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- composer flow

def _publish(video, observer, slot=None):
    pub = InstagramWebPublisher(browser_manager=object())
    return pub._run_composer(
        obs=observer,
        page=FakePage(),
        video_path=video,
        caption="caption",
        hashtags=["#history"],
        target=datetime.datetime.strptime(slot or _future_slot(), "%Y-%m-%d %H:%M:%S"),
        reel_id="REEL-2026-0025",
    )


def test_full_composer_walk_reports_scheduled(video):
    obs = FakeObserver()
    status, error = _publish(video, obs)

    assert status == "SCHEDULED"
    assert error is None
    # The AI disclosure is not optional -- see commit 51d2254.
    assert "enable_ai_label" in obs.steps
    assert obs.steps.index("enable_schedule") < obs.steps.index("click_schedule_and_verify")


@pytest.mark.parametrize(
    "failing",
    ["open_composer", "upload_file", "advance_to_caption_step", "fill_caption",
     "enable_ai_label", "enable_schedule", "select_date", "set_time"],
)
def test_a_half_filled_composer_is_never_submitted(video, failing):
    """Submitting a partly-filled form is how a Reel gets scheduled with no caption."""
    obs = FakeObserver(fail_step=failing)
    status, error = _publish(video, obs)

    assert status.startswith("FAILED")
    assert "click_schedule_and_verify" not in obs.steps
    assert obs.snapshots, "a failure must leave DOM evidence behind"


def test_wrong_date_on_the_form_aborts_before_submit(video):
    obs = FakeObserver(date_ok=False)
    status, error = _publish(video, obs)

    assert status == "FAILED_RETRYABLE"
    assert error == "DATE_VERIFICATION_FAILED"
    assert "click_schedule_and_verify" not in obs.steps


def test_wrong_time_on_the_form_aborts_before_submit(video):
    obs = FakeObserver(time_ok=False)
    status, error = _publish(video, obs)

    assert status == "FAILED_RETRYABLE"
    assert error == "TIME_VERIFICATION_FAILED"
    assert "click_schedule_and_verify" not in obs.steps


@pytest.mark.parametrize(
    "refusal", ["PUBLISH_NOW_BUTTON_REFUSED", "SCHEDULE_MODE_NOT_ACTIVE", "SCHEDULE_BUTTON_NOT_FOUND"]
)
def test_share_now_refusals_are_fatal_not_retryable(video, refusal):
    """Retrying a refusal to click a share-now control just re-runs the same risk."""
    obs = FakeObserver(schedule_result=(False, refusal))
    status, error = _publish(video, obs)

    assert status == "FAILED_FATAL"
    assert error == refusal


def test_unconfirmed_submit_is_retryable(video):
    obs = FakeObserver(schedule_result=(False, "SCHEDULE_CONFIRMATION_NOT_VERIFIED"))
    status, error = _publish(video, obs)

    assert status == "FAILED_RETRYABLE"
    assert error == "SCHEDULE_CONFIRMATION_NOT_VERIFIED"


def test_slot_under_twenty_minutes_never_opens_a_composer(tmp_path, video):
    """Instagram refuses these inline; walking the whole flow to find out wastes a session."""
    class ExplodingBrowser:
        def connect(self):
            raise AssertionError("browser must not be opened for a too-soon slot")

    pub = InstagramWebPublisher(browser_manager=ExplodingBrowser())
    soon = (datetime.datetime.now() + datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    status, error = pub.schedule_reel(video, "c", [], soon, "REEL-2026-0025")

    assert status == "FAILED_FATAL"
    assert "TIME_TOO_SOON" in error


def test_missing_video_is_fatal(tmp_path):
    pub = InstagramWebPublisher(browser_manager=object())
    status, error = pub.schedule_reel(tmp_path / "gone.mp4", "c", [], _future_slot(), "REEL-2026-0025")
    assert status == "FAILED_FATAL"
    assert "missing" in error.lower()


def test_navigation_failure_is_retryable(video):
    pub = InstagramWebPublisher(browser_manager=object())
    status, error = pub._run_composer(
        obs=FakeObserver(), page=FakePage(goto_fails=True), video_path=video,
        caption="c", hashtags=[], target=datetime.datetime.now() + datetime.timedelta(days=2),
        reel_id="REEL-2026-0025",
    )
    assert status == "FAILED_RETRYABLE"


# ---------------------------------------------------------------- delivery routing

def _locked_week(tmp_path, reel_count=3):
    repo = BatchRepository(tmp_path)
    base = datetime.date.today() + datetime.timedelta(days=7)
    reels = []
    for i in range(reel_count):
        video = tmp_path / f"clean_REEL-2026-{25 + i}_story.mp4"
        video.write_bytes(b"v" * 256)
        reels.append(BatchReel(
            index=i + 1,
            reel_id=f"REEL-2026-{25 + i}",
            scheduled_at_local=f"{base.isoformat()} 19:30:00",
            scheduled_at_utc=f"{base.isoformat()} 16:30:00",
            content_mode=NARRATIVE_AMBIENT_STORY,
            video_path=str(video),
            generation_status="COMPLETE",
        ))
    manifest = BatchManifest(
        week_id="2026-W40", start_date=base.isoformat(), status="LOCKED",
        content_mode=NARRATIVE_AMBIENT_STORY, reels=reels,
    )
    repo.save_manifest(manifest)
    repo.ensure_progress_entries(manifest.week_id, [r.reel_id for r in reels])
    return manifest


def _pipeline(tmp_path, publisher, delivery=INSTAGRAM_DELIVERY_WEB):
    pipe = SimpleWeeklyPipeline(
        base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=True,
        content_mode=NARRATIVE_AMBIENT_STORY, instagram_delivery=delivery,
        ig_web_publisher=publisher,
    )
    # Let the media checks through; they have their own tests in test_narrative_ambient_story.
    pipe._instagram_preflight = lambda manifest, reel, video_file, phase: (True, "")
    return pipe


def test_web_delivery_schedules_every_reel(tmp_path):
    manifest = _locked_week(tmp_path)
    publisher = RecordingPublisher()
    pipe = _pipeline(tmp_path, publisher)

    result = pipe._run_instagram_phase(manifest)

    assert result.success, result.message
    assert publisher.calls == [r.reel_id for r in manifest.reels]

    progress = pipe.batch_repo.load_progress(manifest.week_id)
    assert all(progress[r.reel_id]["instagram"]["status"] == "SCHEDULED" for r in manifest.reels)


def test_web_delivery_never_hands_media_to_the_cloud(tmp_path, monkeypatch):
    """Both routes running means every Reel is posted twice on a real account."""
    import automation.simple_weekly_pipeline as pipeline_mod

    def explode(*args, **kwargs):
        raise AssertionError("cloud handoff must not run in web delivery mode")

    monkeypatch.setattr(pipeline_mod, "handoff_reel_to_cloud", explode)

    manifest = _locked_week(tmp_path)
    pipe = _pipeline(tmp_path, RecordingPublisher())
    assert pipe._run_instagram_phase(manifest).success


def test_cloud_delivery_never_opens_the_composer(tmp_path, monkeypatch):
    import automation.simple_weekly_pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod, "handoff_reel_to_cloud",
        lambda **kwargs: (True, {"ok": True, "media_object_key": "media/x.mp4"}, None),
    )

    manifest = _locked_week(tmp_path)
    publisher = RecordingPublisher()
    pipe = _pipeline(tmp_path, publisher, delivery=INSTAGRAM_DELIVERY_CLOUD)
    pipe.cloud_client = object()

    result = pipe._run_instagram_phase(manifest)

    assert result.success, result.message
    assert publisher.calls == [], "the composer must stay closed in cloud delivery mode"

    progress = pipe.batch_repo.load_progress(manifest.week_id)
    assert all(progress[r.reel_id]["instagram"]["status"] == "MEDIA_READY" for r in manifest.reels)


def test_already_scheduled_reels_are_not_scheduled_again(tmp_path):
    """A rerun after a partial week must not double-post what already landed."""
    manifest = _locked_week(tmp_path)
    publisher = RecordingPublisher()
    pipe = _pipeline(tmp_path, publisher)

    progress = pipe.batch_repo.load_progress(manifest.week_id)
    progress[manifest.reels[0].reel_id]["instagram"]["status"] = "SCHEDULED"
    pipe.batch_repo.save_progress(manifest.week_id, progress)

    assert pipe._run_instagram_phase(manifest).success
    assert manifest.reels[0].reel_id not in publisher.calls
    assert publisher.calls == [r.reel_id for r in manifest.reels[1:]]


def test_phase_stops_on_the_first_failure(tmp_path):
    manifest = _locked_week(tmp_path)
    failing_id = manifest.reels[1].reel_id
    publisher = RecordingPublisher(fail_on={failing_id: ("FAILED_FATAL", "PUBLISH_NOW_BUTTON_REFUSED")})
    pipe = _pipeline(tmp_path, publisher)

    result = pipe._run_instagram_phase(manifest)

    assert not result.success
    assert result.detail["failed_reel"] == failing_id
    # The third Reel is never attempted.
    assert manifest.reels[2].reel_id not in publisher.calls


def test_unlocked_manifest_is_refused(tmp_path):
    manifest = _locked_week(tmp_path)
    manifest.status = "DRAFT"
    publisher = RecordingPublisher()
    pipe = _pipeline(tmp_path, publisher)

    assert not pipe._run_instagram_phase(manifest).success
    assert publisher.calls == []


def test_unknown_delivery_mode_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Unknown instagram_delivery"):
        SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v",
                             dry_run=True, instagram_delivery="both")


def test_both_routes_end_states_count_as_delivered():
    """
    Whichever route delivered a Reel, it is delivered. Reading this per-mode meant a
    cloud-delivered week looked unfinished under the web route, so the pipeline resumed
    it and scheduled all 14 already-delivered Reels again.
    """
    assert "MEDIA_READY" in INSTAGRAM_TERMINAL_STATUSES
    assert "SCHEDULED" in INSTAGRAM_TERMINAL_STATUSES


def test_cloud_delivered_reels_are_not_rescheduled_by_the_web_route(tmp_path):
    """The exact double-post this guards: W34 sat at MEDIA_READY when web became default."""
    manifest = _locked_week(tmp_path)
    publisher = RecordingPublisher()
    pipe = _pipeline(tmp_path, publisher, delivery=INSTAGRAM_DELIVERY_WEB)

    progress = pipe.batch_repo.load_progress(manifest.week_id)
    for reel in manifest.reels:
        progress[reel.reel_id]["instagram"]["status"] = "MEDIA_READY"
    pipe.batch_repo.save_progress(manifest.week_id, progress)

    assert pipe._run_instagram_phase(manifest).success
    assert publisher.calls == [], "media already handed to the cloud must not be scheduled again"


def test_a_cloud_delivered_week_reads_as_finished_under_the_web_route(tmp_path):
    """Otherwise the next run resumes the finished week instead of opening the next one."""
    manifest = _locked_week(tmp_path)
    pipe = _pipeline(tmp_path, RecordingPublisher(), delivery=INSTAGRAM_DELIVERY_WEB)

    progress = pipe.batch_repo.load_progress(manifest.week_id)
    for reel in manifest.reels:
        progress[reel.reel_id] = {
            "youtube": {"status": "SCHEDULED", "remote_id": "y", "url": "u", "error": None},
            "tiktok": {"status": "SCHEDULED", "remote_id": "t", "url": "u", "error": None},
            "instagram": {"status": "MEDIA_READY", "remote_media_id": "m", "error": None},
        }
    pipe.batch_repo.save_progress(manifest.week_id, progress)

    assert pipe.all_platform_done(manifest.week_id, manifest.reel_ids(), "instagram")
    assert pipe._is_batch_finished(manifest)
    assert pipe._find_unfinished_week_id() is None
