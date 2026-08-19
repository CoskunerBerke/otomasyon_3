"""
Regression tests for Instagram's composer getting in its own way.

2026-08-19, first live Instagram run: the caption ends in "#AI", so after typing it
Instagram opened a hashtag autocomplete ("#airpods", "#aikido", ...) and left it open
over the form. The AI-label switch sat under that popover, every click on it was
intercepted, and the run read that as the toggle failing -- so the date and time were
never set and the Reel was abandoned.

Three things are pinned here, against the real markup the operator captured:

  1. The caption leaves no active hashtag token behind and moves focus off the field,
     so no suggestion list stays open.
  2. A labelled switch is found only in a row that actually contains a switch -- the
     innermost div around the label text holds none, and "İçeriği planla" also matches
     the composer entry button behind the dialog.
  3. The time spinbuttons are read from aria-valuenow, because their value attribute is
     always empty.

No browser: the page is a fake that records what was typed and clicked.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.publishing.instagram_web_observer import InstagramWebObserver
from automation.publishing.instagram_web_selectors import InstagramWebSelectors


class FakeKeyboard:
    def __init__(self):
        self.pressed = []
        self.typed = []

    def press(self, key):
        self.pressed.append(key)

    def type(self, text):
        self.typed.append(text)


class FakeLocator:
    def __init__(self, page, name, attrs=None, count=1, click_fails_first=False):
        self.page = page
        self.name = name
        self.attrs = dict(attrs or {})
        self._count = count
        self.click_fails_first = click_fails_first
        self.clicks = 0
        self.filled = None

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def count(self):
        return self._count

    def wait_for(self, state=None, timeout=None):
        if self._count == 0:
            raise TimeoutError(f"{self.name} never visible")

    def click(self, timeout=None):
        self.clicks += 1
        if self.click_fails_first and self.clicks == 1:
            raise RuntimeError("<div> intercepts pointer events")
        self.page.clicks.append(self.name)
        if self.name == "switch":
            self.attrs["aria-checked"] = "true"

    def fill(self, text):
        self.filled = text
        self.page.filled[self.name] = text
        if self.name in ("hours", "minutes"):
            self.attrs["aria-valuenow"] = str(int(text))

    def focus(self):
        pass

    def scroll_into_view_if_needed(self, timeout=None):
        pass

    def get_attribute(self, name):
        return self.attrs.get(name)

    def locator(self, selector):
        return self.page.locator(selector)


class FakePage:
    """A composer whose rows and inputs mirror the captured Instagram markup."""

    def __init__(self, switch_click_fails_first=False):
        self.keyboard = FakeKeyboard()
        self.clicks = []
        self.filled = {}
        self.switch = FakeLocator(self, "switch", {"aria-checked": "false"},
                                  click_fails_first=switch_click_fails_first)
        self.hours = FakeLocator(self, "hours", {"aria-valuenow": "14", "value": ""})
        self.minutes = FakeLocator(self, "minutes", {"aria-valuenow": "46", "value": ""})
        self.caption = FakeLocator(self, "caption")

    def locator(self, selector):
        if "input[role='switch']" in selector and ":has(" in selector:
            # A row selector: only the ones that require a switch resolve to the real row.
            return FakeLocator(self, "row", count=1)
        if selector == InstagramWebSelectors.SWITCH_INPUTS[0]:
            return self.switch
        if "Hours" in selector or "Saat" in selector:
            return self.hours
        if "Minutes" in selector or "Dakika" in selector:
            return self.minutes
        if "textarea" in selector or "contenteditable" in selector:
            return self.caption
        return FakeLocator(self, "nothing", count=0)

    def screenshot(self, **kwargs):
        pass

    def content(self):
        return "<html></html>"

    def evaluate(self, *a, **k):
        return 0


def _observer(page, tmp_path):
    obs = InstagramWebObserver.__new__(InstagramWebObserver)
    obs.page = page
    obs.screenshots_dir = tmp_path
    return obs


# ---------------------------------------------------------------- caption

def test_caption_leaves_no_active_hashtag_and_moves_focus_away(tmp_path):
    page = FakePage()
    obs = _observer(page, tmp_path)

    assert obs.fill_caption("A Roman street buried by Vesuvius", ["#Shorts", "#Pompeii", "#AI"])

    written = page.filled["caption"]
    assert written.endswith("#AI "), "a trailing space ends the hashtag token Instagram autocompletes"
    assert "Tab" in page.keyboard.pressed, "focus must leave the field so the popover closes"
    assert "Escape" not in page.keyboard.pressed, "Escape asks to discard the whole post"


def test_caption_stays_within_instagram_limit_including_the_space(tmp_path):
    page = FakePage()
    obs = _observer(page, tmp_path)

    obs.fill_caption("x" * 5000, [])

    assert len(page.filled["caption"]) <= 2200


# ---------------------------------------------------------------- switches

def test_switch_row_lookup_requires_a_switch_in_the_row():
    """Guards the selector shape itself against the real markup's nesting."""
    src = (Path(__file__).resolve().parents[1] / "automation" / "publishing"
           / "instagram_web_observer.py").read_text(encoding="utf-8")
    body = src[src.index("def _switch_near_text"):src.index("def _is_switch_on")]
    row_selectors = [l.strip() for l in body.splitlines() if l.strip().startswith('f"div:has(')]

    assert len(row_selectors) == 2, "Kural 31: two strategies"
    for sel in row_selectors:
        assert ":has({switch_sel})" in sel, f"row selector does not require a switch: {sel}"


def test_ai_label_is_switched_on_and_verified(tmp_path):
    page = FakePage()
    obs = _observer(page, tmp_path)

    assert obs.enable_ai_label() is True
    assert page.switch.attrs["aria-checked"] == "true"
    assert page.clicks.count("switch") == 1


def test_an_intercepted_first_click_is_retried_after_clearing_the_overlay(tmp_path):
    """The live failure: a popover over the switch swallowed the click."""
    page = FakePage(switch_click_fails_first=True)
    obs = _observer(page, tmp_path)

    assert obs.enable_ai_label() is True
    assert page.switch.clicks == 2
    assert "Tab" in page.keyboard.pressed
    assert page.switch.attrs["aria-checked"] == "true"


def test_a_switch_that_is_already_on_is_not_clicked(tmp_path):
    """Entering via /scheduled_content/ pre-enables 'İçeriği planla'; toggling it again would turn it OFF."""
    page = FakePage()
    page.switch.attrs["aria-checked"] = "true"
    obs = _observer(page, tmp_path)

    assert obs.enable_schedule() is True
    assert page.switch.clicks == 0


# ---------------------------------------------------------------- time

def test_time_is_read_from_aria_valuenow_not_value(tmp_path):
    page = FakePage()
    obs = _observer(page, tmp_path)

    assert obs.set_time(19, 30) is True
    assert page.hours.attrs["aria-valuenow"] == "19"
    assert page.minutes.attrs["aria-valuenow"] == "30"
    assert page.hours.attrs["value"] == "", "value stays empty on these spinbuttons; only aria-valuenow moves"


def test_time_falls_back_to_fill_when_typing_does_not_land(tmp_path):
    """Typing is the first path; if aria-valuenow does not move, fill() is the second."""
    page = FakePage()
    obs = _observer(page, tmp_path)

    # Typing in the fake goes to the keyboard recorder, not the input -- so only fill() moves the value.
    assert obs.set_time(22, 0) is True
    assert page.hours.filled == "22"
    assert page.minutes.filled == "00"


def test_verify_time_rejects_a_wrong_readback(tmp_path):
    page = FakePage()
    obs = _observer(page, tmp_path)

    assert obs.verify_time(19, 30) is False   # still 14:46
