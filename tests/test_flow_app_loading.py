"""
Regression tests for Flow's cold-start window.

2026-08-19: a live run failed all its Reels with "Google Flow 'Yeni proje' butonu
bulunamadı." The captured evidence showed the opposite of a UI change -- the account was
signed in (avatar and Flow TV in the header) and the page body just read "Loading...".
goto(wait_until="domcontentloaded") returns when the HTML shell is parsed, so the search
for the button ran ~4.5s later against an app that had not mounted yet.

Two things are covered:
  1. The caller waits for the workspace to actually mount before deciding it is missing.
  2. "Still loading" and "genuinely absent" are reported differently -- one means wait
     and retry, the other means the selectors need updating, and a run that conflates
     them sends whoever reads the log to fix the wrong thing.

No browser: the page is a fake whose visibility answers change over time.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.flow.page import FlowPage
from automation.flow.selectors import FlowSelectors, FlowUIChangedError


class FakeLocator:
    def __init__(self, visible_fn):
        self._visible_fn = visible_fn
        self.clicked = False

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return self._visible_fn()

    def click(self, timeout=None):
        self.clicked = True


class FakePage:
    """
    A page whose contents appear after `ready_after` visibility probes, imitating an SPA
    that paints a loading shell first.
    """

    def __init__(self, ready_after=0, never_ready=False, still_loading=False, url="https://labs.google/fx/tools/flow"):
        self.probes = 0
        self.ready_after = ready_after
        self.never_ready = never_ready
        self.still_loading = still_loading
        self.url = url

    def _mounted(self):
        return not self.never_ready and self.probes >= self.ready_after

    def locator(self, selector):
        def visible():
            self.probes += 1
            if selector in FlowSelectors.APP_LOADING_INDICATOR_SELECTORS:
                return self.still_loading and not self._mounted()
            if selector in FlowSelectors.NEW_PROJECT_BUTTON_SELECTORS:
                return self._mounted()
            return False

        return FakeLocator(visible)

    def screenshot(self, **kwargs):
        pass

    def content(self):
        return "<html></html>"

    def evaluate(self, *args, **kwargs):
        return 0

    def inner_text(self, selector):
        return ""


def _page_obj(fake, tmp_path):
    page = FlowPage.__new__(FlowPage)
    page.page = fake
    page.screenshots_dir = tmp_path
    return page


def test_loading_indicator_selectors_are_registered():
    assert FlowSelectors.APP_LOADING_INDICATOR_SELECTORS
    joined = " ".join(FlowSelectors.APP_LOADING_INDICATOR_SELECTORS)
    assert "Loading" in joined
    # The UI is used in Turkish; both spellings of the shell must be recognised.
    assert "Yükleniyor" in joined


def test_wait_returns_once_the_app_mounts(tmp_path):
    """The exact cold start that failed: the button appears a few seconds in."""
    fake = FakePage(ready_after=3, still_loading=True)
    page = _page_obj(fake, tmp_path)

    assert page.wait_for_app_ready(timeout_seconds=10) is True


def test_wait_gives_up_when_the_app_never_mounts(tmp_path):
    fake = FakePage(never_ready=True, still_loading=True)
    page = _page_obj(fake, tmp_path)

    assert page.wait_for_app_ready(timeout_seconds=2) is False


def test_still_loading_is_not_reported_as_a_ui_change(tmp_path):
    """Blaming the selectors for a slow page sends the reader to fix the wrong thing."""
    fake = FakePage(never_ready=True, still_loading=True)
    page = _page_obj(fake, tmp_path)

    with pytest.raises(FlowUIChangedError) as exc:
        page._raise_new_project_missing()

    message = str(exc.value)
    assert "Loading" in message
    assert "tekrar çalıştırın" in message
    assert "butonu bulunamadı" not in message


def test_a_genuinely_missing_button_still_reports_a_ui_change(tmp_path):
    fake = FakePage(never_ready=True, still_loading=False)
    page = _page_obj(fake, tmp_path)

    with pytest.raises(FlowUIChangedError) as exc:
        page._raise_new_project_missing()

    assert "butonu bulunamadı" in str(exc.value)


def test_is_app_still_loading_reflects_the_shell(tmp_path):
    loading = _page_obj(FakePage(never_ready=True, still_loading=True), tmp_path)
    mounted = _page_obj(FakePage(ready_after=0, still_loading=False), tmp_path)

    assert loading.is_app_still_loading() is True
    assert mounted.is_app_still_loading() is False
