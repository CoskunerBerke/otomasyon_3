"""
Regression tests for the guards that decide WHERE a Reel goes and WHAT it is called.

Found by auditing the whole publishing path on 2026-08-22, after three days in which
every incident turned out to be the same mistake: reading a browser once and treating
"not ready yet" as "not there".

The two worst findings were not timing at all, though:

  * Both account guards accepted the FIRST channel's name whatever brand was running --
    `or "buildverse" in det_norm` on YouTube, `or "kitchenverse" in act_norm` on TikTok.
    A craftsbyman run that landed on the first channel would have been told it was on the
    right account and published there. brands.py exists to make exactly that impossible.
  * Both then FAILED OPEN: when nothing could be read they returned "assumed active".
    A slow page was enough to skip the last check standing between a run and the wrong
    audience -- and publishing to the wrong channel cannot be undone.

Plus: YouTube's fill_details returned True unconditionally, so a title field that never
mounted meant the Reel published under YouTube's default -- the source filename.

Covered here is the decision, not the Studio DOM: pages are fakes.
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.publishing.tiktok_ui_observer import TikTokUIObserver
from automation.publishing.youtube_studio_ui_observer import (
    CHANNEL_IDENTITY_WAIT_SECONDS,
    FILE_INPUT_WAIT_SECONDS,
    TITLE_INPUT_WAIT_SECONDS,
    YouTubeStudioUIObserver,
)

REPO = Path(__file__).resolve().parents[1]


class FakeLoc:
    def __init__(self, text=None, visible=False, count=0, href=None):
        self._text, self._visible, self._count, self._href = text, visible, count, href
        self.filled = None

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return self._visible

    def is_enabled(self):
        return True

    def count(self):
        return self._count

    def inner_text(self):
        return self._text or ""

    def get_attribute(self, name):
        return self._href if name == "href" else None

    def click(self):
        pass

    def fill(self, value):
        self.filled = value
        self._text = value

    def set_input_files(self, path):
        self.filled = path


class FakePage:
    """Answers every selector with the same configured element."""

    def __init__(self, url="https://studio.youtube.com/", element=None):
        self.url = url
        self.element = element or FakeLoc()
        self.keyboard = type("K", (), {"press": lambda *a, **k: None, "type": lambda *a, **k: None})()

    def locator(self, selector):
        return self.element

    def content(self):
        return ""


def _yt(page):
    obs = YouTubeStudioUIObserver.__new__(YouTubeStudioUIObserver)
    obs.page = page
    obs.capture_error_snapshot = lambda *a, **k: None
    return obs


def _tt(page):
    obs = TikTokUIObserver.__new__(TikTokUIObserver)
    obs.page = page
    obs.capture_error_snapshot = lambda *a, **k: None
    return obs


# ---------------------------------------------------------------- YouTube channel

def test_youtube_verifies_through_the_channel_id_in_the_url():
    """The strong signal: the publisher navigated to this id and it survived."""
    page = FakePage(url="https://studio.youtube.com/channel/UCcZow6RbRyK3xH-KymR_9KQ/videos")
    ok, detected, _ = _yt(page).verify_logged_in_channel("@craftsbyman", "UCcZow6RbRyK3xH-KymR_9KQ")
    assert ok is True


def test_youtube_no_longer_accepts_the_first_channel_as_a_skeleton_key(monkeypatch):
    """A craftsbyman run sitting on @BuiIdVerse must be refused, not welcomed."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    page = FakePage(
        url="https://studio.youtube.com/channel/UCahsmsqzTCtwTDDtvCurtBA/videos",
        element=FakeLoc(text="BuildVerse", visible=True),
    )
    ok, detected, msg = _yt(page).verify_logged_in_channel("@craftsbyman", "UCcZow6RbRyK3xH-KymR_9KQ")
    assert ok is False
    assert "ACCOUNT_MISMATCH" in msg
    assert "BuildVerse" in detected


def test_youtube_still_accepts_its_own_handle(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    page = FakePage(url="https://studio.youtube.com/", element=FakeLoc(text="craftsbyman", visible=True))
    ok, _, _ = _yt(page).verify_logged_in_channel("@craftsbyman", "UCcZow6RbRyK3xH-KymR_9KQ")
    assert ok is True


def test_youtube_refuses_when_the_channel_cannot_be_read(monkeypatch):
    """The old code returned 'assumed active' here and published anyway."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        "automation.publishing.youtube_studio_ui_observer.CHANNEL_IDENTITY_WAIT_SECONDS", 0.0
    )
    page = FakePage(url="https://studio.youtube.com/", element=FakeLoc(visible=False))
    ok, _, msg = _yt(page).verify_logged_in_channel("@craftsbyman", "UCcZow6RbRyK3xH-KymR_9KQ")
    assert ok is False
    assert "ACCOUNT_MISMATCH" in msg


def test_no_brand_name_is_hardcoded_in_either_account_guard():
    """The skeleton keys, gone from the source and not to come back."""
    yt = (REPO / "automation" / "publishing" / "youtube_studio_ui_observer.py").read_text(encoding="utf-8")
    tt = (REPO / "automation" / "publishing" / "tiktok_ui_observer.py").read_text(encoding="utf-8")

    assert 'or "buildverse" in det_norm' not in yt
    assert 'or "kitchenverse" in act_norm' not in tt
    for source, name in ((yt, "youtube"), (tt, "tiktok")):
        assert "assumed active" not in source, f"{name} guard still assumes an account"


# ---------------------------------------------------------------- TikTok account

def test_tiktok_no_longer_accepts_the_first_channel_as_a_skeleton_key(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    page = FakePage(url="https://www.tiktok.com/tiktokstudio/upload",
                    element=FakeLoc(text="kitchenverse360", visible=True))
    ok, detected, msg = _tt(page).verify_logged_in_username("@craftsbyman")
    assert ok is False
    assert "ACCOUNT_MISMATCH" in msg


def test_tiktok_accepts_its_own_handle(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    page = FakePage(url="https://www.tiktok.com/tiktokstudio/upload",
                    element=FakeLoc(text="craftsbyman", visible=True))
    ok, _, _ = _tt(page).verify_logged_in_username("@craftsbyman")
    assert ok is True


# ---------------------------------------------------------------- identity matching

@pytest.mark.parametrize(
    "expected,detected,should_match,why",
    [
        # The first channel's handle is "@BuiIdVerse" -- a capital i where the display
        # name has a lowercase L. This pair is the whole reason the old skeleton key
        # existed, and folding confusable characters is what replaces it.
        ("@BuiIdVerse", "BuildVerse Official", True, "handle vs display name"),
        ("@craftsbyman", "Crafts By Man", True, "spacing and case"),
        ("@kitchenverse360", "kitchenverse360", True, "exact"),
        ("@kitchenverse360", "kitchenverse", True, "display drops the suffix"),
        # The whole point: one brand must never satisfy another's guard.
        ("@craftsbyman", "BuildVerse", False, "second brand on the first channel"),
        ("@craftsbyman", "kitchenverse360", False, "second brand on the first TikTok"),
        ("@craftsbyman", "Random Gaming Hub", False, "someone else entirely"),
        # Two characters sit inside almost any handle; accepting them would hand back
        # the fail-open this guard exists to remove.
        ("@craftsbyman", "c", False, "too short to mean anything"),
        ("@craftsbyman", "", False, "nothing read"),
    ],
)
def test_identity_matching(expected, detected, should_match, why):
    from automation.publishing.youtube_studio_ui_observer import account_identities_match

    assert account_identities_match(expected, detected) is should_match, why


def test_tiktok_never_claims_verification_it_did_not_do(monkeypatch):
    """
    This one does not block -- TikTok's upload page may simply not name the account, and
    refusing on a DOM this code cannot verify would stop a working channel on a guess
    (Kural 31). What it must never do is report success.
    """
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        "automation.publishing.tiktok_ui_observer.ACCOUNT_IDENTITY_WAIT_SECONDS", 0.0
    )
    page = FakePage(url="https://www.tiktok.com/tiktokstudio/upload", element=FakeLoc(visible=False))
    ok, detected, msg = _tt(page).verify_logged_in_username("@craftsbyman")
    assert detected == "ACCOUNT_UNVERIFIED"
    assert "Verified" not in msg


# ---------------------------------------------------------------- YouTube upload + title

def test_youtube_waits_for_the_upload_dialog_to_build_its_input(monkeypatch, tmp_path):
    """The defect that stopped TikTok's twelfth Reel, carried by YouTube too."""
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 16)

    class LatePage(FakePage):
        def __init__(self):
            super().__init__()
            self.looks = 0

        def locator(self, selector):
            self.looks += 1
            return FakeLoc(count=1 if self.looks > 6 else 0)

    obs = _yt(LatePage())
    obs.open_upload_dialog = lambda *a, **k: True
    assert obs.upload_file(video) is True


def test_youtube_upload_wait_is_generous_but_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        "automation.publishing.youtube_studio_ui_observer.FILE_INPUT_WAIT_SECONDS", 0.0
    )
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 16)

    obs = _yt(FakePage(element=FakeLoc(count=0)))
    obs.open_upload_dialog = lambda *a, **k: True
    assert obs.upload_file(video) is False
    assert FILE_INPUT_WAIT_SECONDS >= 15
    assert TITLE_INPUT_WAIT_SECONDS >= 10
    assert CHANNEL_IDENTITY_WAIT_SECONDS >= 10


def test_a_missing_title_field_is_a_failure_not_a_shrug(monkeypatch):
    """
    It used to return True regardless, and the Reel published under YouTube's default
    title -- the source filename.
    """
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        "automation.publishing.youtube_studio_ui_observer.TITLE_INPUT_WAIT_SECONDS", 0.0
    )
    obs = _yt(FakePage(element=FakeLoc(visible=False)))
    assert obs.fill_details("A real title", "A real caption", ["#Shorts"]) is False


def test_a_title_still_showing_the_filename_is_refused(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    class StubbornLoc(FakeLoc):
        def fill(self, value):
            pass  # the field refuses the write and keeps the upload's filename

    loc = StubbornLoc(text="clean_clean_CBM-REEL-2026-0001_aircraft-garden-hidden.mp4", visible=True)
    assert _yt(FakePage(element=loc)).fill_details("A real title", "A caption", ["#Shorts"]) is False


def test_the_publisher_acts_on_that_answer():
    src = (REPO / "automation" / "publishing" / "youtube_studio_publisher.py").read_text(encoding="utf-8")
    assert "if not observer.fill_details(" in src, (
        "an unwritten title must stop the Reel, not be ignored"
    )


# ---------------------------------------------------------------- TikTok editor reuse

def test_a_caption_about_an_oasis_is_not_mistaken_for_an_open_editor():
    """
    "zen_temple" and "oasis" were leftovers from an early test. These Reels are about
    buried objects becoming underground gardens and oases, so a match would have skipped
    the upload and hung this Reel's title, caption and slot on another Reel's video.
    """
    src = (REPO / "automation" / "publishing" / "tiktok_ui_observer.py").read_text(encoding="utf-8")
    detector = src.split("def is_editor_open_for_reel")[1].split("def ")[0]
    assert '"zen_temple" in page_text' not in detector
    assert '"oasis" in page_text' not in detector
    assert "r_id_clean in page_text" in detector
