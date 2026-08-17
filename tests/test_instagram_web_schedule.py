"""
Instagram web scheduling flow (instagram.com composer).

The safety property that matters most: a post may only ever be SCHEDULED. With the
"İçeriği planla" toggle OFF the composer's primary button reads "Paylaş" and posts
immediately, so the toggle must be verified ON before that button is ever clicked.

Fakes only -- no browser, no network, no Instagram calls.
"""
import datetime

import pytest

from automation.publishing.instagram_web_observer import InstagramWebObserver
from automation.publishing.instagram_web_selectors import InstagramWebSelectors


class _Loc:
    def __init__(self, text="", visible=True, attrs=None, count=1):
        self._text = text
        self._visible = visible
        self._attrs = attrs or {}
        self._count = count
        self.clicks = 0

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def count(self):
        return self._count

    def is_visible(self, timeout=None):
        return self._visible

    def inner_text(self):
        return self._text

    def get_attribute(self, name):
        return self._attrs.get(name)

    def scroll_into_view_if_needed(self, timeout=None):
        return None

    def click(self, timeout=None):
        self.clicks += 1
        if callable(getattr(self, "on_click", None)):
            self.on_click()

    def locator(self, selector):
        return getattr(self, "child", _Loc(visible=False, count=0))


class _Page:
    """Composer page whose primary button label follows the schedule toggle, exactly
    like the real UI (toggle off => 'Paylaş', toggle on => 'Planla')."""

    def __init__(self, schedule_on=True, ai_on=False, hour=19, minute=30, body=""):
        self.schedule_on = schedule_on
        self.ai_on = ai_on
        self.hour = hour
        self.minute = minute
        self.body = body

        self.schedule_switch = _Loc(attrs={"aria-checked": "true" if schedule_on else "false"})
        self.ai_switch = _Loc(attrs={"aria-checked": "true" if ai_on else "false"})

        def flip_schedule():
            self.schedule_on = not self.schedule_on
            self.schedule_switch._attrs["aria-checked"] = "true" if self.schedule_on else "false"

        def flip_ai():
            self.ai_on = not self.ai_on
            self.ai_switch._attrs["aria-checked"] = "true" if self.ai_on else "false"

        self.schedule_switch.on_click = flip_schedule
        self.ai_switch.on_click = flip_ai
        self.primary = _Loc(text="Planla" if schedule_on else "Paylaş")

    def locator(self, selector):
        s = selector.lower()

        if "içeriği planla" in selector or "Schedule content" in selector:
            row = _Loc()
            row.child = self.schedule_switch
            return row
        if "yapay zeka" in s or "Add AI label" in selector:
            row = _Loc()
            row.child = self.ai_switch
            return row

        if "text-is('planla')" in s or "text-is('schedule')" in s or "has-text('planla')" in s:
            # Primary action reflects the live toggle state.
            self.primary._text = "Planla" if self.schedule_on else "Paylaş"
            return self.primary

        if "aria-label='hours'" in s:
            return _Loc(attrs={"aria-valuenow": str(self.hour)})
        if "aria-label='minutes'" in s:
            return _Loc(attrs={"aria-valuenow": str(self.minute)})
        if "aria-haspopup='dialog'" in s:
            return _Loc(text="17 Ağu 2026 Pzt")

        return _Loc(visible=False, count=0)

    def inner_text(self, selector):
        return self.body

    def screenshot(self, path=None, full_page=None):
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"")

    def content(self):
        return "<html></html>"


# ---------------------------------------------------------------------------
# The core safety property
# ---------------------------------------------------------------------------

def test_never_clicks_share_when_schedule_toggle_is_off():
    """Toggle OFF => primary button is 'Paylaş' (posts immediately) => must NOT be clicked."""
    page = _Page(schedule_on=False)
    obs = InstagramWebObserver(page)

    ok, reason = obs.click_schedule_and_verify(timeout_seconds=1)

    assert ok is False
    assert reason == "SCHEDULE_MODE_NOT_ACTIVE"
    assert page.primary.clicks == 0, "ASLA 'Paylas' tiklanmamali"


def test_refuses_primary_button_labelled_share_even_if_toggle_reads_on():
    """Defense in depth: toggle claims ON but the button still says 'Paylaş' -- refuse."""
    page = _Page(schedule_on=True)
    page.primary._text = "Paylaş"

    class _StickyPage(_Page):
        pass

    # Freeze the label so the observer sees the mismatch.
    orig_locator = page.locator

    def locator(selector):
        loc = orig_locator(selector)
        if loc is page.primary:
            loc._text = "Paylaş"
        return loc
    page.locator = locator

    obs = InstagramWebObserver(page)
    ok, reason = obs.click_schedule_and_verify(timeout_seconds=1)

    assert ok is False
    assert reason == "PUBLISH_NOW_BUTTON_REFUSED"
    assert page.primary.clicks == 0


def test_schedules_when_toggle_on_and_confirmation_appears():
    page = _Page(schedule_on=True, body="Gönderin planlandı")
    obs = InstagramWebObserver(page)

    ok, reason = obs.click_schedule_and_verify(timeout_seconds=3)

    assert ok is True
    assert reason == "INSTAGRAM_SCHEDULED"
    assert page.primary.clicks == 1


# ---------------------------------------------------------------------------
# Toggles
# ---------------------------------------------------------------------------

def test_ai_label_toggle_is_turned_on():
    """Instagram requires realistic AI content to be labelled; these Reels always are."""
    page = _Page(ai_on=False)
    obs = InstagramWebObserver(page)

    assert obs.enable_ai_label() is True
    assert page.ai_switch.get_attribute("aria-checked") == "true"
    assert page.ai_switch.clicks == 1


def test_ai_label_toggle_not_clicked_twice_when_already_on():
    page = _Page(ai_on=True)
    obs = InstagramWebObserver(page)

    assert obs.enable_ai_label() is True
    assert page.ai_switch.clicks == 0


def test_schedule_toggle_turned_on_and_verified():
    page = _Page(schedule_on=False)
    obs = InstagramWebObserver(page)

    assert obs.enable_schedule() is True
    assert obs.is_schedule_enabled() is True


# ---------------------------------------------------------------------------
# Time / date
# ---------------------------------------------------------------------------

def test_time_verified_by_reading_back_aria_valuenow():
    page = _Page(hour=19, minute=30)
    obs = InstagramWebObserver(page)

    assert obs.verify_time(19, 30) is True
    assert obs.verify_time(22, 0) is False


def test_date_verified_against_button_text():
    page = _Page()
    obs = InstagramWebObserver(page)

    assert obs.verify_date(datetime.datetime(2026, 8, 17, 19, 30)) is True
    assert obs.verify_date(datetime.datetime(2026, 8, 23, 19, 30)) is False


def test_turkish_date_format_matches_instagram_rendering():
    assert InstagramWebObserver.format_tr_date(datetime.datetime(2026, 8, 17)) == "17 Ağu 2026"
    assert InstagramWebObserver.format_tr_date(datetime.datetime(2026, 12, 1)) == "1 Ara 2026"


# ---------------------------------------------------------------------------
# Kural 31
# ---------------------------------------------------------------------------

def test_selectors_are_semantic_not_hashed_classes():
    """Instagram's class names are hashed atomic CSS that changes between builds, so no
    selector may anchor on them."""
    groups = [
        InstagramWebSelectors.OPEN_COMPOSER_BUTTONS,
        InstagramWebSelectors.SELECT_FROM_COMPUTER_BUTTONS,
        InstagramWebSelectors.NEXT_BUTTONS,
        InstagramWebSelectors.CAPTION_INPUTS,
        InstagramWebSelectors.SCHEDULE_SUBMIT_BUTTONS,
        InstagramWebSelectors.HOUR_INPUTS,
        InstagramWebSelectors.MINUTE_INPUTS,
    ]
    for group in groups:
        assert len(group) <= 2, "Kural 31: en fazla 2 strateji"
        for sel in group:
            # Hashed atomic classes look like .x1i10hfl / .xjqpnuy
            assert ".x1" not in sel and ".xjq" not in sel, f"hash'li class kullanilmis: {sel}"


def test_forbidden_share_labels_cover_both_languages():
    labels = InstagramWebSelectors.FORBIDDEN_IMMEDIATE_SHARE_LABELS
    assert "paylaş" in labels
    assert "share" in labels
