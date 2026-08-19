"""
Regression test: TikTok's discard path must never click a delete confirmation.

TikTok labels two very different buttons "Sil". One discards an unsaved editing session
-- harmless, the file is simply re-uploaded. The other sits in "Bu gönderi silinsin mi?
Videonuz ... ve tüm düzenlemeler kalıcı olarak silinecek." and destroys a post.

dismiss_unsaved_draft_banner_if_present tests for the resume banner by reading the whole
page, then clicks the first button labelled "Sil" it can find. Those are two different
elements: a stale "kaydedilmedi" bar anywhere on the page would authorise a click that
lands on the delete dialog instead. CLAUDE.md forbids this system from removing platform
content automatically under any circumstance, so the two must never be confused.

Observed live on 2026-08-19 while the operator was clearing these dialogs by hand.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.publishing.tiktok_selectors import TikTokSelectors
from automation.publishing.tiktok_ui_observer import TikTokUIObserver


RESUME_BANNER = "Düzenlemekte olduğunuz bir video kaydedilmedi. Düzenlemeye devam edilsin mi?"
DELETE_DIALOG = (
    "Bu gönderi silinsin mi? Videonuz \"Dramatic sheer ocean...\" ve tüm düzenlemeler "
    "kalıcı olarak silinecek. Şimdi değil Sil"
)


class FakeLocator:
    def __init__(self, recorder, label):
        self.recorder = recorder
        self.label = label

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return True

    def is_enabled(self):
        return True

    def click(self, timeout=None):
        self.recorder.append(self.label)


class FakePage:
    def __init__(self, body_text):
        self.body_text = body_text
        self.clicks = []

    def inner_text(self, selector):
        return self.body_text

    def locator(self, selector):
        return FakeLocator(self.clicks, selector)

    def screenshot(self, **kwargs):
        pass

    def content(self):
        return f"<html>{self.body_text}</html>"

    def evaluate(self, *a, **k):
        return 0


def _observer(body_text, tmp_path):
    obs = TikTokUIObserver.__new__(TikTokUIObserver)
    obs.page = FakePage(body_text)
    obs.screenshots_dir = tmp_path
    return obs


def test_a_delete_confirmation_is_never_clicked(tmp_path):
    """The dangerous case: both texts on screen at once."""
    obs = _observer(RESUME_BANNER + " " + DELETE_DIALOG, tmp_path)

    result = obs.dismiss_unsaved_draft_banner_if_present()

    assert result is False
    assert obs.page.clicks == [], "no button may be clicked while a delete dialog is up"


def test_a_delete_confirmation_alone_is_left_alone(tmp_path):
    obs = _observer(DELETE_DIALOG, tmp_path)

    assert obs.dismiss_unsaved_draft_banner_if_present() is False
    assert obs.page.clicks == []


def test_a_plain_resume_banner_is_still_cleared(tmp_path):
    """The guard must not disable the behaviour it is protecting."""
    obs = _observer(RESUME_BANNER, tmp_path)

    assert obs.dismiss_unsaved_draft_banner_if_present() is True
    assert obs.page.clicks, "an ordinary resume banner should still be discarded"


def test_an_unrelated_page_does_nothing(tmp_path):
    obs = _observer("TikTok Studio içerik listesi", tmp_path)

    assert obs.dismiss_unsaved_draft_banner_if_present() is False
    assert obs.page.clicks == []


def test_delete_markers_cover_the_observed_dialog():
    text = DELETE_DIALOG.lower()
    assert any(m in text for m in TikTokSelectors.DESTRUCTIVE_DELETE_CONFIRM_MARKERS)


def test_delete_markers_do_not_match_the_resume_banner():
    """Over-matching would silently disable draft cleanup and stall the TikTok phase."""
    text = RESUME_BANNER.lower()
    assert not any(m in text for m in TikTokSelectors.DESTRUCTIVE_DELETE_CONFIRM_MARKERS)


def test_immediate_publish_labels_remain_forbidden():
    """Unrelated to this fix, but the other never-click list must stay intact."""
    assert "hemen paylaş" in TikTokSelectors.FORBIDDEN_IMMEDIATE_PUBLISH_LABELS
    assert "post now" in TikTokSelectors.FORBIDDEN_IMMEDIATE_PUBLISH_LABELS
