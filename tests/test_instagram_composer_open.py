"""
Regression: a composer that opened, reported as a composer that did not.

2026-09-21, REEL-2026-0082 on BuildVerse's Instagram. The step failed as OPEN_COMPOSER
with Playwright "waiting for element to be visible, enabled and stable" on the
"İçeriği planla" button -- and the snapshot taken at that failure shows the "Yeni
gönderi oluştur" dialog open, "Bilgisayardan seç" waiting for a file. The click had
worked; the dialog it opened then sat on top of the button, so every retry of the same
click timed out, and the Reel was marked FAILED_RETRYABLE with the composer ready.

No browser: the observer is driven through a fake page.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.publishing.instagram_web_observer import InstagramWebObserver


class FakeLocator:
    def __init__(self, is_visible):
        self._visible = is_visible

    @property
    def first(self):
        return self

    def wait_for(self, state="visible", timeout=None):
        if not self._visible():
            raise TimeoutError("not visible")

    def is_visible(self):
        return self._visible()


class ComposerPage:
    """A scheduled_content page whose composer is open or closed on demand."""

    def __init__(self, composer_open):
        self.composer_open = composer_open

    def locator(self, selector):
        if "Bilgisayardan" in selector or "Select from computer" in selector:
            return FakeLocator(lambda: self.composer_open)
        return FakeLocator(lambda: True)


def _observer(page, click_result, opens_composer=False):
    obs = InstagramWebObserver(page)
    clicks = []

    def click(selectors, what):
        clicks.append(what)
        if opens_composer:
            page.composer_open = True
        return click_result

    obs._click = click
    obs.capture_error_snapshot = lambda tag: clicks.append(f"snapshot:{tag}")
    return obs, clicks


def test_a_click_that_opened_the_composer_is_not_a_failure():
    """The 0082 case: the click reports failure, the dialog is open anyway."""
    page = ComposerPage(composer_open=False)
    obs, clicks = _observer(page, click_result=False, opens_composer=True)

    assert obs.open_composer() is True
    assert not any(c.startswith("snapshot:") for c in clicks)


def test_an_already_open_composer_is_not_clicked_again():
    """Clicking the entry button under an open dialog is what timed out in the first place."""
    page = ComposerPage(composer_open=True)
    obs, clicks = _observer(page, click_result=False)

    assert obs.open_composer() is True
    assert clicks == [], "open composer must not be clicked through"


def test_a_click_that_really_failed_still_fails_loudly():
    """Accepting an open composer must not turn a genuinely missing button into success."""
    page = ComposerPage(composer_open=False)
    obs, clicks = _observer(page, click_result=False, opens_composer=False)

    assert obs.open_composer() is False
    assert "snapshot:composer_button_not_found" in clicks


def test_a_normal_click_still_works():
    page = ComposerPage(composer_open=False)
    obs, clicks = _observer(page, click_result=True, opens_composer=True)

    assert obs.open_composer() is True
    assert clicks == ["İçeriği planla"]
