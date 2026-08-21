"""
One test file for the failure mode that broke this project four times in a single day.

2026-08-19, in order: Flow reported "Yeni proje butonu bulunamadı" against a page still
showing "Loading..."; YouTube reported 5 of 14 Reels unscheduled while its content check
was still running; TikTok reported 7 of 14 unverified by reading a content list that had
not been reloaded since before the posts existed; TikTok then failed a date it had set
correctly seconds earlier for the previous Reel.

Every one was the same mistake: reading a UI once, immediately, and treating "not ready
yet" as "not there". Every one halted or degraded a live run that was otherwise fine.

These tests pin the waits themselves. They are deliberately about constants rather than
behaviour -- behaviour is covered in the per-platform files -- because the regression to
guard against is someone trimming a timeout back to milliseconds to make a test faster.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- Flow

def test_flow_waits_for_its_workspace_to_mount():
    from automation.flow.page import FlowPage
    from automation.flow.selectors import FlowSelectors

    assert hasattr(FlowPage, "wait_for_app_ready")
    assert hasattr(FlowPage, "is_app_still_loading")
    assert FlowSelectors.APP_LOADING_INDICATOR_SELECTORS


def test_flow_distinguishes_loading_from_missing():
    """The two need opposite responses: wait and re-run, versus fix the selectors."""
    src = (REPO / "automation" / "flow" / "page.py").read_text(encoding="utf-8")
    assert "_raise_new_project_missing" in src
    assert "yüklenmesini tamamlamadı" in src


# ---------------------------------------------------------------- YouTube

def test_youtube_verification_outlasts_a_content_check():
    from automation.publishing.youtube_studio_publisher import VERIFY_BACKOFF_SECONDS

    assert sum(VERIFY_BACKOFF_SECONDS) >= 55, "a fresh Short can take a minute to settle"
    assert VERIFY_BACKOFF_SECONDS[-1] == 0.0, "no sleep after the last attempt"


def test_youtube_row_settle_is_not_instantaneous():
    src = (REPO / "automation" / "publishing" / "youtube_studio_ui_observer.py").read_text(encoding="utf-8")
    attempts = int(re.search(r"ROW_SETTLE_ATTEMPTS = (\d+)", src).group(1))
    seconds = float(re.search(r"ROW_SETTLE_SECONDS = ([\d.]+)", src).group(1))

    assert attempts * seconds >= 10, "a matched row needs real time to fill its cell"


def test_youtube_checks_before_resuming_a_draft():
    """An already-scheduled video has no draft to reopen; hunting for one loops forever."""
    src = (REPO / "automation" / "publishing" / "youtube_studio_publisher.py").read_text(encoding="utf-8")
    check = src.find("already_scheduled, why = observer.verify_remote_scheduled_status")
    assert check != -1
    assert check < src.find("if has_remote_evidence and target_remote_id:")
    # The title-fallback branch became a second `if` on 2026-08-22, so that a recorded
    # video found to be deleted can clear its id and fall through to a clean upload
    # instead of dead-ending in the resume chain.
    assert check < src.find("if has_remote_evidence and not target_remote_id:")


# ---------------------------------------------------------------- TikTok

def test_tiktok_verification_retries_on_a_fresh_page():
    from automation.publishing.tiktok_ui_observer import REMOTE_VERIFY_BACKOFF_SECONDS

    assert len(REMOTE_VERIFY_BACKOFF_SECONDS) >= 3
    assert sum(REMOTE_VERIFY_BACKOFF_SECONDS) >= 30


def test_tiktok_verification_reloads_every_attempt():
    """
    The old code skipped navigation when already on the content URL -- exactly the case
    where the list predates the post being verified.
    """
    src = (REPO / "automation" / "publishing" / "tiktok_ui_observer.py").read_text(encoding="utf-8")
    assert "_read_scheduled_marker_once" in src
    body = src[src.index("def _read_scheduled_marker_once"):]
    body = body[:body.index("def ", 10)]
    assert "self.page.goto(" in body, "each pass must reload the list"
    assert "not in (self.page.url" not in body, "the stale-page shortcut must be gone"


def test_tiktok_date_readback_polls():
    from automation.publishing.tiktok_ui_observer import (
        DATE_READBACK_ATTEMPTS,
        DATE_READBACK_INTERVAL_SECONDS,
    )

    assert DATE_READBACK_ATTEMPTS >= 2
    assert DATE_READBACK_ATTEMPTS * DATE_READBACK_INTERVAL_SECONDS >= 2.0


def test_tiktok_more_options_waits_for_the_form():
    from automation.publishing.tiktok_ui_observer import (
        MORE_OPTIONS_PROBE_MS,
        MORE_OPTIONS_WAIT_SECONDS,
    )

    assert MORE_OPTIONS_WAIT_SECONDS >= 8, "the control arrives with the rest of the form"
    assert MORE_OPTIONS_PROBE_MS >= 500


def test_tiktok_more_options_keeps_two_safe_strategies():
    """
    Kural 31, and a real hazard: `div:has-text(...)` matches every ancestor containing
    the text, so `.first` could resolve to a page-sized container.
    """
    src = (REPO / "automation" / "publishing" / "tiktok_ui_observer.py").read_text(encoding="utf-8")
    block = src[src.index("btn_selectors = ["):]
    block = block[:block.index("]")]
    lines = [l.strip() for l in block.splitlines() if l.strip().startswith('"')]

    assert len(lines) <= 2, f"Kural 31 allows 2 strategies, found {len(lines)}"
    for line in lines:
        assert "more-btn" in line, f"selector is not scoped to the control: {line}"


# ---------------------------------------------------------------- Instagram

def test_instagram_composer_waits_for_video_processing():
    from automation.publishing.instagram_web_observer import (
        STEP_WAIT_MS,
        UPLOAD_SETTLE_SECONDS,
    )

    assert STEP_WAIT_MS >= 10000, "'İleri' is unusable until the video is processed"
    assert UPLOAD_SETTLE_SECONDS >= 3


def test_instagram_publisher_waits_for_a_cold_page():
    from automation.publishing.instagram_web_publisher import APP_READY_TIMEOUT_SECONDS

    assert APP_READY_TIMEOUT_SECONDS >= 30, "this Chrome is opened cold by the weekly run"


def test_instagram_helper_actually_waits_rather_than_snapshotting():
    """
    Locator.is_visible() ignores its timeout -- it is a snapshot. Only wait_for() polls.
    Using the wrong one is how a rendering SPA reads as an empty page.
    """
    src = (REPO / "automation" / "publishing" / "instagram_web_observer.py").read_text(encoding="utf-8")
    helper = src[src.index("def _first_visible"):]
    helper = helper[:helper.index("def _click")]

    # Strip the docstring: it explains the is_visible trap by name, and matching that
    # explanation would fail the test for describing the bug it prevents.
    body = helper.split('"""')[-1]

    assert "wait_for(" in body
    assert "is_visible(" not in body


# ---------------------------------------------------------------- failures leave evidence

@pytest.mark.parametrize(
    "path,marker",
    [
        ("automation/publishing/tiktok_ui_observer.py", "tiktok_date_mismatch_calendar_open"),
        ("automation/publishing/tiktok_ui_observer.py", "tiktok_more_options_not_found"),
        ("automation/publishing/tiktok_ui_observer.py", "tiktok_remote_schedule_not_verified"),
        ("automation/publishing/instagram_web_publisher.py", "page_never_became_ready"),
    ],
)
def test_halting_failures_capture_evidence(path, marker):
    """
    A failure nobody can diagnose costs another live run to reproduce. Each of these
    stopped or degraded a platform while leaving nothing behind.
    """
    src = (REPO / path).read_text(encoding="utf-8")
    assert marker in src
