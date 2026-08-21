"""
Regression tests for YouTube's post-upload verification race.

2026-08-19: a live run scheduled all 14 Reels correctly -- YouTube Studio showed every
one of them as "Planlandı" on the right date -- but the pipeline reported 5 of them as
SCHEDULE_RESUME_REQUIRED. The row was found and matched; its visibility cell was simply
still blank because YouTube was running its content check ("Kontrol ediliyor...") on the
freshly uploaded Short. Verification allowed about 7 seconds for that.

A false negative here is expensive: it holds the whole platform for 30 minutes and,
without the resume guard, invites a re-upload of a video that is already scheduled.

Covered:
  1. A cell that fills in late still verifies.
  2. A row that genuinely settles into draft is not waited out into a false pass.
  3. The publisher's retry gaps are long enough to outlast a content check.

No browser: the page is a fake whose row text changes between reads.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.publishing.youtube_studio_publisher import VERIFY_BACKOFF_SECONDS
from automation.publishing.youtube_studio_ui_observer import YouTubeStudioUIObserver


class FakeRow:
    """A content-list row whose text changes as YouTube finishes its content check."""

    def __init__(self, texts):
        self.texts = list(texts)
        self.reads = 0

    def inner_text(self):
        text = self.texts[min(self.reads, len(self.texts) - 1)]
        self.reads += 1
        return text


class FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def count(self):
        return len(self._rows)

    def nth(self, i):
        return self._rows[i]


class FakePage:
    def __init__(self, rows):
        self._rows = rows
        self.visited = []

    def goto(self, url, **kwargs):
        self.visited.append(url)

    def locator(self, selector):
        return FakeRows(self._rows)


def _observer(rows, tmp_path):
    obs = YouTubeStudioUIObserver.__new__(YouTubeStudioUIObserver)
    obs.page = FakePage(rows)
    obs.screenshots_dir = tmp_path
    return obs


def _verify(obs):
    return obs.verify_remote_scheduled_status(
        remote_id="abc123",
        target_title="Pompeii: Buried, Then Found Again",
        expected_date_str="24 Ağu 2026",
        expected_time_str="19:30",
        channel_id="UCtest",
    )


SCHEDULED_ROW = "pompeii: buried, then found again  abc123  planlandı  24 ağu 2026"
CHECKING_ROW = "pompeii: buried, then found again  abc123  kontrol ediliyor..."
DRAFT_ROW = "pompeii: buried, then found again  abc123  taslak"


def test_a_row_that_is_already_scheduled_passes_immediately(tmp_path):
    row = FakeRow([SCHEDULED_ROW])
    ok, msg = _verify(_observer([row], tmp_path))

    assert ok
    assert msg == "SCHEDULED"


def test_a_cell_that_fills_in_late_still_verifies(tmp_path, monkeypatch):
    """The exact 2026-08-19 failure: correct schedule, cell not painted yet."""
    monkeypatch.setattr("time.sleep", lambda s: None)

    # Blank while the content check runs, then "Planlandı" on the fourth read.
    row = FakeRow([CHECKING_ROW, CHECKING_ROW, CHECKING_ROW, SCHEDULED_ROW])
    ok, msg = _verify(_observer([row], tmp_path))

    assert ok, "a late visibility cell must not be reported as unscheduled"
    assert msg == "SCHEDULED"


def test_a_row_that_never_fills_in_stays_inconclusive(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    row = FakeRow([CHECKING_ROW])
    ok, msg = _verify(_observer([row], tmp_path))

    assert not ok
    assert msg == "REMOTE_TARGET_FOUND_BUT_NOT_SCHEDULED"


def test_a_genuine_draft_is_not_waited_out_into_a_pass(tmp_path, monkeypatch):
    """Waiting must not turn "this really is a draft" into a success."""
    monkeypatch.setattr("time.sleep", lambda s: None)

    row = FakeRow([CHECKING_ROW, DRAFT_ROW])
    ok, msg = _verify(_observer([row], tmp_path))

    assert not ok
    assert msg == "DRAFT_PRIVATE"


def test_an_unrelated_row_is_never_matched(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    other = FakeRow(["some other video  zzz999  planlandı  01 Eyl 2026"])
    ok, msg = _verify(_observer([other], tmp_path))

    assert not ok
    assert msg == "REMOTE_SCHEDULE_NOT_VERIFIED"


def test_publisher_retries_outlast_a_content_check(tmp_path):
    """
    Seconds are not enough. The gaps must add up to something on the order of a minute,
    which is how long the content check can take on a fresh Short.
    """
    assert sum(VERIFY_BACKOFF_SECONDS) >= 55, "verification gives up too early"
    assert VERIFY_BACKOFF_SECONDS[-1] == 0.0, "no point sleeping after the final attempt"
    assert len(VERIFY_BACKOFF_SECONDS) >= 3
    # Growing gaps: a quick check should not pay the full wait.
    non_zero = [s for s in VERIFY_BACKOFF_SECONDS if s]
    assert non_zero == sorted(non_zero), "backoff should grow, not shrink"


# ---------------------------------------------------------------- missing video id

def test_video_id_capture_polls_rather_than_reading_once():
    """
    2026-08-21: the first 7 Reels of a 14-Reel batch captured a video id and the last 7
    came back empty, then failed verification with "Remote YouTube video ID is missing".
    The link element is not in the wizard the instant an upload finishes.
    """
    from automation.publishing.youtube_studio_ui_observer import VIDEO_ID_WAIT_SECONDS

    assert VIDEO_ID_WAIT_SECONDS >= 10
    src = (Path(__file__).resolve().parents[1] / "automation" / "publishing"
           / "youtube_studio_ui_observer.py").read_text(encoding="utf-8")
    body = src[src.index("def capture_video_id_and_url"):src.index("def _read_video_id_once")]
    assert "while True" in body and "time.sleep" in body, "capture must poll"


def test_a_late_video_id_is_still_captured(tmp_path, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)

    obs = YouTubeStudioUIObserver.__new__(YouTubeStudioUIObserver)
    obs.screenshots_dir = tmp_path
    calls = {"n": 0}

    def late(_self):
        calls["n"] += 1
        if calls["n"] < 4:
            return None, None
        return "abc12345678", "https://youtu.be/abc12345678"

    monkeypatch.setattr(YouTubeStudioUIObserver, "_read_video_id_once", late)
    vid, url = obs.capture_video_id_and_url(wait_seconds=10)

    assert vid == "abc12345678"
    assert calls["n"] >= 4


def test_a_missing_id_is_verified_by_title_and_date_instead_of_failing():
    """Refusing outright recorded 7 correctly scheduled Reels as failures."""
    src = (Path(__file__).resolve().parents[1] / "automation" / "publishing"
           / "youtube_studio_publisher.py").read_text(encoding="utf-8")
    block = src[src.index("# 9. Verify scheduled status"):]
    block = block[:block.index("# Extract verified") if "# Extract verified" in block else 4000]

    assert "require_date_match=True" in block, "title-only matching would hit an earlier week"
    assert "mark_scheduled(" in block, "a verified schedule must be recorded as scheduled"


def test_title_only_matching_requires_the_date(tmp_path, monkeypatch):
    """The same concept carries the same title in a later week; the date separates them."""
    monkeypatch.setattr("time.sleep", lambda s: None)

    wrong_week = FakeRow(["pompeii: buried, then found again  planlandı  17 Ağu 2026"])
    obs = _observer([wrong_week], tmp_path)
    ok, msg = obs.verify_remote_scheduled_status(
        remote_id="", target_title="Pompeii: Buried, Then Found Again",
        expected_date_str="24 Ağu 2026", expected_time_str="19:30",
        channel_id="UCtest", require_date_match=True,
    )
    assert not ok, "a different week's row must not satisfy this Reel's verification"

    right_week = FakeRow(["pompeii: buried, then found again  planlandı  24 Ağu 2026"])
    obs2 = _observer([right_week], tmp_path)
    ok2, _ = obs2.verify_remote_scheduled_status(
        remote_id="", target_title="Pompeii: Buried, Then Found Again",
        expected_date_str="24 Ağu 2026", expected_time_str="19:30",
        channel_id="UCtest", require_date_match=True,
    )
    assert ok2
