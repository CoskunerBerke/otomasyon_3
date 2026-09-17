"""
Regression: Flow's agent failing, and a download that never reached the automation client.

2026-09-17, CBM-REEL-2026-0057. Segments 1 and 2 downloaded; on segment 3 Flow answered
"Ajan başarısız oldu. Lütfen tekrar deneyin." and offered a "Tekrar dene" button. Nothing
generates until that button is pressed, and nothing in the pipeline knew the button
existed, so the run sat in WAIT for its full twenty-minute timeout.

The second failure came from the recovery itself: pressing the button from a separate CDP
client reset Chrome's download behaviour, so the retried video went to the user's own
Downloads folder. Playwright still reported a download, save_as() wrote 0 bytes, nothing
raised, and the segment failed with a 5 MB video sitting on disk one directory away.
"""
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from automation.flow.chat_classifier import classify_agent_message, AgentMessageType
from automation.flow.downloader import FlowDownloader
from automation.flow.page import FlowPage
from automation.flow.selectors import is_single_shot_approval_label
from automation.flow.state_machine import (
    FlowDecisionAction,
    FlowDecisionEngine,
    GenerationLifecycleState,
    GenerationSession,
)
from automation.flow.ui_observer import FlowUIObserver, FlowUISnapshot


def _page(retry_label=None, approval_labels=(), clicked=None):
    """A Flow page showing only what a test puts on it: a retry button, an approval row."""
    page = MagicMock()
    page.url = "https://flow.google.com/project/x"

    def button(label):
        b = MagicMock()
        b.is_visible.return_value = True
        b.inner_text.return_value = label
        b.click.side_effect = lambda timeout=None: (clicked if clicked is not None else []).append(label)
        return b

    def locator(sel):
        loc = MagicMock()
        loc.all.return_value = []
        loc.count.return_value = 0
        loc.first.count.return_value = 0
        loc.first.is_visible.return_value = False
        loc.first.get_attribute.return_value = None
        if retry_label is not None and "Tekrar dene" in sel:
            loc.first.count.return_value = 1
            loc.first.is_visible.return_value = True
            loc.first.inner_text.return_value = retry_label
        elif approval_labels and "Onayla" in sel:
            # has-text() is a substring match, so Flow's three buttons all come back here.
            loc.all.return_value = [button(l) for l in approval_labels]
        else:
            loc.first.wait_for.side_effect = Exception("not visible")
        return loc

    page.locator.side_effect = locator
    return page


APPROVAL_ROW = ("Onayla", "Her zaman onayla", "Reddet")


def _session():
    s = GenerationSession(reel_id="CBM-REEL-2026-0057-S3")
    s.submit_attempted = True
    return s


def test_the_observer_sees_flows_retry_button():
    assert _observe("Tekrar dene").agent_retry_available is True


def test_no_retry_button_means_nothing_to_retry():
    assert _observe(None).agent_retry_available is False


def test_a_container_that_merely_contains_the_words_is_not_the_button():
    """A long label means the selector matched a panel, and pressing that is a guess."""
    long_label = "Ajan başarısız oldu. Lütfen tekrar deneyin. Tekrar dene " + "x" * 40
    assert _observe(long_label).agent_retry_available is False


def _observe(retry_label):
    return FlowUIObserver(_page(retry_label)).take_snapshot()


def _snapshot(**kw):
    base = dict(page_url="u", agent_retry_available=True)
    base.update(kw)
    return FlowUISnapshot(**base)


def test_a_failed_agent_is_retried_instead_of_waited_out():
    engine = FlowDecisionEngine()
    assert engine.decide_next_action(_snapshot(), session=_session()) == \
        FlowDecisionAction.RETRY_AGENT_GENERATION
    assert engine.agent_retries_used == 1


def test_retrying_forever_is_not_an_option():
    """Each retry is a real generation attempt, so the budget is what protects credits."""
    engine = FlowDecisionEngine()
    session = _session()
    for _ in range(engine.MAX_AGENT_RETRIES_PER_SEGMENT):
        assert engine.decide_next_action(_snapshot(), session=session) == \
            FlowDecisionAction.RETRY_AGENT_GENERATION
    assert engine.decide_next_action(_snapshot(), session=session) == \
        FlowDecisionAction.USER_ACTION_REQUIRED
    assert engine.state == GenerationLifecycleState.FAILED


def test_a_finished_video_beats_a_stale_retry_banner():
    """The banner from a previous attempt must never discard media already on screen."""
    engine = FlowDecisionEngine()
    snap = _snapshot(download_button_visible=True, new_video_artifact_detected=True,
                     new_artifact_fingerprint="media:abc")
    assert engine.decide_next_action(snap, session=_session()) == FlowDecisionAction.DOWNLOAD_MEDIA
    assert engine.agent_retries_used == 0


def test_a_generation_in_flight_is_not_interrupted():
    engine = FlowDecisionEngine()
    snap = _snapshot(stop_button_visible=True)
    assert engine.decide_next_action(snap, session=_session()) == FlowDecisionAction.WAIT
    assert engine.agent_retries_used == 0


def test_the_page_presses_the_button():
    fp = FlowPage.__new__(FlowPage)
    fp.page = _page("Tekrar dene")
    assert fp.click_agent_retry() is True


def test_pressing_a_button_that_is_not_there_reports_failure():
    fp = FlowPage.__new__(FlowPage)
    fp.page = _page(None)
    assert fp.click_agent_retry() is False


def test_the_failure_message_classifies_as_an_error():
    """For the case where the banner is up but the button is not reachable."""
    assert classify_agent_message("Ajan başarısız oldu. Lütfen tekrar deneyin.") == \
        AgentMessageType.ERROR


def _download_page():
    """A download that reports success while writing nothing."""
    page = MagicMock()
    page.wait_for_selector.side_effect = Exception("no quality menu")
    download = MagicMock()
    download.save_as.side_effect = lambda p: Path(p).write_bytes(b"")
    info = MagicMock()
    info.value = download
    cm = MagicMock()
    cm.__enter__.return_value = info
    cm.__exit__.return_value = False
    page.expect_download.return_value = cm
    return page


def _download_button():
    btn = MagicMock()
    btn.get_attribute.return_value = None
    btn.is_enabled.return_value = True
    return btn


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    return tmp_path


def test_a_video_chrome_saved_to_the_users_downloads_is_recovered(home):
    downloads = home / "Downloads"
    downloads.mkdir()
    (downloads / "Man_exploring_underground_wine_c.mp4").write_bytes(b"v" * 5_000_000)

    dl = FlowDownloader(home / "workspace_downloads")
    out = dl.trigger_and_save_download(
        page=_download_page(),
        download_button_locator=_download_button(),
        target_filename="segment_03.mp4",
    )
    assert out.stat().st_size == 5_000_000


def test_an_empty_download_with_nothing_to_recover_still_fails(home):
    (home / "Downloads").mkdir()
    dl = FlowDownloader(home / "workspace_downloads")
    with pytest.raises(RuntimeError, match="missing or invalid size"):
        dl.trigger_and_save_download(
            page=_download_page(),
            download_button_locator=_download_button(),
            target_filename="segment_03.mp4",
        )


def test_an_older_file_in_downloads_is_not_mistaken_for_this_segment(home):
    """The window is the click, not the folder -- an old download is not this video."""
    downloads = home / "Downloads"
    downloads.mkdir()
    stale = downloads / "yesterday.mp4"
    stale.write_bytes(b"v" * 5_000_000)
    import os
    old = time.time() - 3600
    os.utime(stale, (old, old))

    dl = FlowDownloader(home / "workspace_downloads")
    with pytest.raises(RuntimeError, match="missing or invalid size"):
        dl.trigger_and_save_download(
            page=_download_page(),
            download_button_locator=_download_button(),
            target_filename="segment_03.mp4",
        )


# --- Flow's credit question -------------------------------------------------------
#
# CBM-REEL-2026-0062, 2026-09-17: "15 kredi karşılığında bu 1 video üretimi işlemini
# başlatmamı ister misiniz?" with Onayla / Her zaman onayla / Reddet. Nothing generates
# until it is answered and nothing times out either, so the Reel burned its whole
# twenty-minute budget on a question and finished with no segments at all.


@pytest.mark.parametrize("label", ["Onayla", "onayla", "Approve", "Approve "])
def test_the_single_shot_approval_is_recognised(label):
    assert is_single_shot_approval_label(label) is True


@pytest.mark.parametrize("label", [
    "Her zaman onayla", "Always approve", "Reddet", "Decline", "İptal",
    "15 kredi karşılığında bu 1 video üretimi işlemini başlatmamı ister misiniz? Onayla",
    "", None,
])
def test_the_other_buttons_are_never_ours_to_press(label):
    """Her zaman onayla writes a stored setting; Reddet throws the segment away."""
    assert is_single_shot_approval_label(label) is False


def test_the_observer_sees_the_pending_credit_question():
    assert _page_snapshot(approval_labels=APPROVAL_ROW).generation_approval_pending is True


def test_a_page_without_the_question_reports_nothing_pending():
    assert _page_snapshot().generation_approval_pending is False


def test_always_approve_alone_is_not_a_pending_question():
    """If the only match is the setting-changing button, there is nothing to press."""
    assert _page_snapshot(approval_labels=("Her zaman onayla",)).generation_approval_pending is False


def _page_snapshot(**kw):
    return FlowUIObserver(_page(**kw)).take_snapshot()


def test_the_question_is_answered_instead_of_waited_out():
    engine = FlowDecisionEngine()
    snap = _snapshot(agent_retry_available=False, generation_approval_pending=True)
    assert engine.decide_next_action(snap, session=_session()) ==         FlowDecisionAction.APPROVE_GENERATION_ONCE


def test_one_segment_gets_one_approval():
    """A second question is not this segment's, so it goes to the operator."""
    engine = FlowDecisionEngine()
    session = _session()
    snap = _snapshot(agent_retry_available=False, generation_approval_pending=True)
    assert engine.decide_next_action(snap, session=session) ==         FlowDecisionAction.APPROVE_GENERATION_ONCE
    assert engine.decide_next_action(snap, session=session) ==         FlowDecisionAction.USER_ACTION_REQUIRED


def test_media_on_screen_still_wins_over_a_pending_question():
    engine = FlowDecisionEngine()
    snap = _snapshot(agent_retry_available=False, generation_approval_pending=True,
                     download_button_visible=True, new_video_artifact_detected=True,
                     new_artifact_fingerprint="media:abc")
    assert engine.decide_next_action(snap, session=_session()) == FlowDecisionAction.DOWNLOAD_MEDIA
    assert engine.generation_approvals_used == 0


def test_only_onayla_is_pressed_never_her_zaman_onayla():
    """The whole point: has-text('Onayla') matches all three, and two of them are not ours."""
    clicked = []
    fp = FlowPage.__new__(FlowPage)
    fp.page = _page(approval_labels=APPROVAL_ROW, clicked=clicked)
    assert fp.approve_generation_once() is True
    assert clicked == ["Onayla"]


def test_no_approval_button_reports_failure():
    fp = FlowPage.__new__(FlowPage)
    fp.page = _page()
    assert fp.approve_generation_once() is False
