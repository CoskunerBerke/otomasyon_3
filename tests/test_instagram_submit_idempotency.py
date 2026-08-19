"""
Regression tests for what happens after Instagram's 'Planla' has been pressed.

2026-08-19, first live Instagram run: REEL-2026-0025 WAS scheduled -- the success dialog
("Reels videon planlandı.") was on screen -- but Instagram took about a minute to show
it and the code waited 30 seconds. It recorded FAILED_RETRYABLE, and the 30-minute hold
then re-ran the Reel, which would have scheduled the same video a second time. This
system may not delete remote content, so a duplicate is a manual cleanup on a real
account.

Two properties, both non-negotiable:
  1. Once 'Planla' is clicked, that Reel is never submitted again by any retry.
  2. The confirmation is given long enough to actually appear, and the success dialog
     is dismissed so the next Reel starts clean.

Also pinned: the slow-'İleri' fix (the caption probe is short; the patience is on the
button Instagram holds back), and the misleading "Tarih uyusmuyor" pre-check log.
"""
import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.content.content_modes import NARRATIVE_AMBIENT_STORY
from automation.orchestration.batch_manifest import BatchManifest, BatchReel, BatchRepository
from automation.publishing.instagram_web_observer import (
    CAPTION_PROBE_MS,
    SCHEDULE_CONFIRM_TIMEOUT_SECONDS,
    STEP_WAIT_MS,
    InstagramWebObserver,
)
from automation.publishing.instagram_web_publisher import InstagramWebPublisher
from automation.publishing.instagram_web_selectors import InstagramWebSelectors
from automation.simple_weekly_pipeline import (
    INSTAGRAM_TERMINAL_STATUSES,
    SimpleWeeklyPipeline,
)

SRC = (Path(__file__).resolve().parents[1] / "automation" / "publishing"
       / "instagram_web_observer.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- publisher mapping

class FakeObserver:
    def __init__(self, schedule_result):
        self.schedule_result = schedule_result
        self.steps = []

    def __getattr__(self, name):
        # Every composer step succeeds; only the final submit result is controlled.
        def ok(*a, **k):
            self.steps.append(name)
            if name == "select_date":
                return True, "ok"
            return True
        return ok

    def click_schedule_and_verify(self, timeout_seconds=None):
        self.steps.append("click_schedule_and_verify")
        return self.schedule_result

    def capture_error_snapshot(self, tag):
        pass


class FakePage:
    def goto(self, *a, **k):
        pass

    def locator(self, selector):
        class L:
            first = property(lambda self: self)
            def is_visible(self, timeout=None):
                return True
        return L()


def _run(video, result):
    pub = InstagramWebPublisher(browser_manager=object())
    return pub._run_composer(
        obs=FakeObserver(result), page=FakePage(), video_path=video, caption="c",
        hashtags=["#x"], target=datetime.datetime.now() + datetime.timedelta(days=3),
        reel_id="REEL-2026-0025",
    )


@pytest.fixture
def video(tmp_path):
    f = tmp_path / "clean_REEL-2026-0025_story.mp4"
    f.write_bytes(b"v" * 256)
    return f


def test_a_submit_whose_confirmation_timed_out_is_not_retryable(video):
    status, error = _run(video, (False, "SUBMITTED_CONFIRMATION_TIMEOUT"))

    assert status == "SUBMITTED_UNVERIFIED"
    assert status != "FAILED_RETRYABLE"
    assert "tekrar" in error.lower()


def test_a_confirmed_submit_is_scheduled(video):
    status, error = _run(video, (True, "INSTAGRAM_SCHEDULED"))
    assert status == "SCHEDULED"
    assert error is None


def test_a_refused_click_is_still_fatal(video):
    status, _ = _run(video, (False, "PUBLISH_NOW_BUTTON_REFUSED"))
    assert status == "FAILED_FATAL"


# ---------------------------------------------------------------- pipeline never re-submits

def test_submitted_unverified_is_terminal():
    """Terminal means: skipped by every retry and every resume."""
    assert "SUBMITTED_UNVERIFIED" in INSTAGRAM_TERMINAL_STATUSES


class CountingPublisher:
    def __init__(self):
        self.calls = []

    def schedule_reel(self, video_path, caption, hashtags, scheduled_at_local, reel_id):
        self.calls.append(reel_id)
        return "SCHEDULED", None


def _locked_week(tmp_path, n=3):
    repo = BatchRepository(tmp_path)
    base = datetime.date.today() + datetime.timedelta(days=7)
    reels = []
    for i in range(n):
        v = tmp_path / f"clean_REEL-2026-{25 + i}_s.mp4"
        v.write_bytes(b"v" * 64)
        reels.append(BatchReel(
            index=i + 1, reel_id=f"REEL-2026-{25 + i}",
            scheduled_at_local=f"{base.isoformat()} 19:30:00",
            scheduled_at_utc=f"{base.isoformat()} 16:30:00",
            content_mode=NARRATIVE_AMBIENT_STORY, video_path=str(v), generation_status="COMPLETE",
        ))
    m = BatchManifest(week_id="2026-W40", start_date=base.isoformat(), status="LOCKED",
                      content_mode=NARRATIVE_AMBIENT_STORY, reels=reels)
    repo.save_manifest(m)
    repo.ensure_progress_entries(m.week_id, [r.reel_id for r in reels])
    return m


def test_a_submitted_reel_is_never_scheduled_again_on_retry(tmp_path):
    """The exact double-post the hold would have produced for REEL-2026-0025."""
    manifest = _locked_week(tmp_path)
    publisher = CountingPublisher()
    pipe = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v", dry_run=True,
                                content_mode=NARRATIVE_AMBIENT_STORY, instagram_delivery="web",
                                ig_web_publisher=publisher)
    pipe._instagram_preflight = lambda *a, **k: (True, "")

    progress = pipe.batch_repo.load_progress(manifest.week_id)
    progress[manifest.reels[0].reel_id]["instagram"]["status"] = "SUBMITTED_UNVERIFIED"
    pipe.batch_repo.save_progress(manifest.week_id, progress)

    # Run the phase twice, as the hold would.
    pipe._run_instagram_phase(manifest)
    pipe._run_instagram_phase(manifest)

    assert manifest.reels[0].reel_id not in publisher.calls, "a submitted Reel must never be re-sent"
    assert publisher.calls.count(manifest.reels[1].reel_id) == 1
    assert pipe.all_platform_done(manifest.week_id, manifest.reel_ids(), "instagram")


def test_a_submitted_week_reads_as_finished():
    """Otherwise the next run resumes it and opens the composer for it again."""
    assert "SUBMITTED_UNVERIFIED" in INSTAGRAM_TERMINAL_STATUSES


# ---------------------------------------------------------------- confirmation patience & cleanup

def test_confirmation_window_outlasts_instagram_processing():
    assert SCHEDULE_CONFIRM_TIMEOUT_SECONDS >= 120, "a minute was observed live; 30s read success as failure"


def test_click_schedule_default_uses_the_long_window():
    sig = SRC[SRC.index("def click_schedule_and_verify"):SRC.index("def click_schedule_and_verify") + 200]
    assert "SCHEDULE_CONFIRM_TIMEOUT_SECONDS" in sig


def test_confirmation_timeout_is_reported_as_submitted_not_as_failure():
    body = SRC[SRC.index("def click_schedule_and_verify"):SRC.index("def _close_success_dialog")]
    assert "SUBMITTED_CONFIRMATION_TIMEOUT" in body
    assert "SCHEDULE_CONFIRMATION_NOT_VERIFIED" not in body.split("btn.click(timeout=4000)")[1], \
        "after the click, the outcome must not be reported as a plain failure"


def test_success_dialog_is_dismissed_via_bitti():
    assert InstagramWebSelectors.SUCCESS_DIALOG_DONE_BUTTONS
    joined = " ".join(InstagramWebSelectors.SUCCESS_DIALOG_DONE_BUTTONS)
    assert "Bitti" in joined and "role='button'" in joined
    assert not any(cls in joined for cls in ("x1i10hfl", "xjqpnuy")), "hashed classes must not be used"
    body = SRC[SRC.index("def click_schedule_and_verify"):SRC.index("def _close_success_dialog")]
    assert "_close_success_dialog()" in body


# ---------------------------------------------------------------- 'İleri' speed

def test_caption_probe_is_short_and_ileri_wait_is_long():
    """
    The caption box is absent on the crop and filter screens, so waiting for it there
    only delays 'İleri'. The patience belongs on 'İleri', which Instagram holds back
    while the video is processed.
    """
    assert CAPTION_PROBE_MS <= 3000
    assert STEP_WAIT_MS >= 10000
    body = SRC[SRC.index("def advance_to_caption_step"):SRC.index("def fill_caption")]
    assert "CAPTION_PROBE_MS" in body.split("for step in range")[1].split("_click(")[0]


# ---------------------------------------------------------------- date pre-check log

def test_date_precheck_does_not_warn():
    """select_date asks 'already right?' before opening the picker; that is not a mismatch."""
    pre = SRC[SRC.index("def select_date"):].split("DATE_ALREADY_CORRECT")[0]
    assert "strict=False" in pre
