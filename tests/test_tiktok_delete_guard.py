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
    def __init__(self, recorder, label, text=""):
        self.recorder = recorder
        self.label = label
        self.text = text

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return True

    def wait_for(self, state=None, timeout=None):
        """Model Playwright: wait_for polls and RAISES on timeout, unlike
        is_visible, which is a snapshot that returns a bool. A fake that offers
        only is_visible makes every "not visible" path pass for the wrong
        reason -- and, since 2026-08-22, makes every visible one fail.
        """
        if not self.is_visible():
            raise TimeoutError(f"not visible within {timeout}ms")

    def is_enabled(self):
        return True

    def inner_text(self):
        return self.text

    def click(self, timeout=None):
        self.recorder.append(self.label)


class FakePage:
    """
    Resolves selectors the way the real modal footer would: the cancel selectors reach
    the secondary button, and a bare "Sil" match reaches the destructive primary one.
    """

    def __init__(self, body_text, has_cancel=True):
        self.body_text = body_text
        self.has_cancel = has_cancel
        self.clicks = []

    def inner_text(self, selector):
        return self.body_text

    def locator(self, selector):
        if "Şimdi değil" in selector or "Not now" in selector:
            if not self.has_cancel:
                return FakeLocator(self.clicks, "MISSING", text="")
            return FakeLocator(self.clicks, "CANCEL", text="Şimdi değil")
        # Anything else in this dialog is the primary [Sil].
        return FakeLocator(self.clicks, "DELETE", text="Sil")

    def screenshot(self, **kwargs):
        pass

    def content(self):
        return f"<html>{self.body_text}</html>"

    def evaluate(self, *a, **k):
        return 0


def _observer(body_text, tmp_path, has_cancel=True):
    obs = TikTokUIObserver.__new__(TikTokUIObserver)
    obs.page = FakePage(body_text, has_cancel=has_cancel)
    obs.screenshots_dir = tmp_path
    return obs


def test_the_delete_button_is_never_clicked(tmp_path):
    """The dangerous case: both texts on screen at once."""
    obs = _observer(RESUME_BANNER + " " + DELETE_DIALOG, tmp_path)

    obs.dismiss_unsaved_draft_banner_if_present()

    assert "DELETE" not in obs.page.clicks, "the destructive button must never be clicked"


def test_the_dialog_is_cancelled_rather_than_left_on_screen(tmp_path):
    """Cancelling removes nothing and unblocks the page, so it needs no human."""
    obs = _observer(DELETE_DIALOG, tmp_path)

    obs.dismiss_unsaved_draft_banner_if_present()

    assert obs.page.clicks == ["CANCEL"]


def test_a_dialog_appearing_without_a_resume_banner_is_still_handled(tmp_path):
    """It shows up on its own after a schedule; the banner test must not skip past it."""
    obs = _observer(DELETE_DIALOG, tmp_path)

    obs.dismiss_unsaved_draft_banner_if_present()

    assert obs.page.clicks == ["CANCEL"]


def test_without_a_cancel_button_nothing_is_clicked(tmp_path):
    """No safe exit means stop and ask -- never fall back to the other button."""
    obs = _observer(DELETE_DIALOG, tmp_path, has_cancel=False)

    assert obs.dismiss_unsaved_draft_banner_if_present() is False
    assert "DELETE" not in obs.page.clicks


def test_a_plain_resume_banner_is_still_cleared(tmp_path):
    """The guard must not disable the behaviour it is protecting."""
    obs = _observer(RESUME_BANNER, tmp_path)

    assert obs.dismiss_unsaved_draft_banner_if_present() is True
    assert obs.page.clicks, "an ordinary resume banner should still be discarded"


def test_an_unrelated_page_does_nothing(tmp_path):
    obs = _observer("TikTok Studio içerik listesi", tmp_path)

    assert obs.dismiss_unsaved_draft_banner_if_present() is False
    assert obs.page.clicks == []


def test_cancel_selectors_pin_the_exact_label():
    """
    The two buttons are siblings and the destructive one is the primary, so a substring
    match on the cancel selectors would be a real hazard.
    """
    for selector in TikTokSelectors.DELETE_DIALOG_CANCEL_BUTTONS:
        assert ":text-is(" in selector, f"cancel selector must pin exact text: {selector}"
        assert "Sil" not in selector.replace("Şimdi değil", ""), selector
    # A build hash would break on the next TikTok deploy (Kural 31).
    assert not any("jsx-" in s for s in TikTokSelectors.DELETE_DIALOG_CANCEL_BUTTONS)


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
