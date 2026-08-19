"""
Regression tests for TikTok's schedule date picker.

2026-08-19: REEL-2026-0032 needed 27 August and the field never left 19 August, which
stopped the whole TikTok phase. REEL-2026-0031 had set that same 27 August seconds
earlier without trouble -- so the selector was not simply wrong.

Two defects behind it:

1. Three of the five day selectors did not require `.valid`. TikTok's grid repeats day
   numbers across months -- asking for "27" in August also matches 27 July in the leading
   row -- and those spillover cells, like past days, render without `.valid`. Clicking one
   does nothing and leaves the date where it was. (Kural 31 also caps this at two
   strategies; there were five.)
2. The field was read once, 0.3s after the click. TikTok does not always update that fast.

No browser: the calendar is a fake grid built to mirror the captured screenshot.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import automation.publishing.tiktok_ui_observer as tiktok_mod
from automation.publishing.tiktok_ui_observer import (
    DATE_READBACK_ATTEMPTS,
    DATE_READBACK_INTERVAL_SECONDS,
    TikTokUIObserver,
)


SOURCE = (Path(__file__).resolve().parents[1]
          / "automation" / "publishing" / "tiktok_ui_observer.py").read_text(encoding="utf-8")


def _day_selector_block():
    start = SOURCE.index("day_selectors = [")
    end = SOURCE.index("]", start)
    return SOURCE[start:end]


def test_every_day_selector_requires_the_valid_class():
    """
    Without `.valid` a selector can match the previous month's 27 in the leading row --
    a cell that is visible, clickable, and does nothing.
    """
    block = _day_selector_block()
    lines = [l.strip() for l in block.splitlines() if ".calendar-wrapper" in l]

    assert lines, "no day selectors found"
    for line in lines:
        assert "span.day.valid" in line, f"selector may hit an adjacent-month cell: {line}"


def test_kural_31_two_strategies_at_most():
    block = _day_selector_block()
    lines = [l for l in block.splitlines() if ".calendar-wrapper" in l]
    assert len(lines) <= 2, f"Kural 31 allows 2 strategies per UI action, found {len(lines)}"


def test_readback_waits_long_enough_to_be_useful():
    assert DATE_READBACK_ATTEMPTS >= 2, "one read is what caused the false mismatch"
    total = DATE_READBACK_ATTEMPTS * DATE_READBACK_INTERVAL_SECONDS
    assert total >= 2.0, f"only {total}s of patience; the field can take longer"


def test_a_date_mismatch_captures_evidence():
    """DATE_MISMATCH halts TikTok outright and used to leave nothing to diagnose from."""
    idx = SOURCE.index("Calendar UI readback mismatch")
    following = SOURCE[idx:idx + 800]
    assert "capture_error_snapshot" in following, "a halting failure must leave evidence"


# ---------------------------------------------------------------- behaviour

class FakeCell:
    def __init__(self, day, valid, recorder):
        self.day = day
        self.valid = valid
        self.recorder = recorder

    def is_visible(self, timeout=None):
        return True

    def scroll_into_view_if_needed(self, timeout=None):
        pass

    def click(self, timeout=None):
        self.recorder.append((self.day, self.valid))


class FakeCells:
    def __init__(self, cells):
        self.cells = cells

    def count(self):
        return len(self.cells)

    def nth(self, i):
        return self.cells[i]

    @property
    def first(self):
        return self.cells[0]


class FakeCalendarPage:
    """
    Mirrors the captured August 2026 grid: a leading 27 from July (not `.valid`) and the
    real 27 August (`.valid`).
    """

    def __init__(self):
        self.clicks = []

    def locator(self, selector):
        july_27 = FakeCell(27, valid=False, recorder=self.clicks)
        august_27 = FakeCell(27, valid=True, recorder=self.clicks)

        if "span.day.valid" in selector:
            return FakeCells([august_27])
        return FakeCells([july_27, august_27])


def test_a_valid_scoped_selector_picks_august_not_july():
    page = FakeCalendarPage()

    cells = page.locator(".calendar-wrapper span.day.valid:text-is('27')")
    cells.nth(0).click()

    assert page.clicks == [(27, True)], "the click must land on the in-month day"


def test_an_unscoped_selector_would_hit_july_first():
    """Shows what the removed selectors did -- the leading cell comes first in the grid."""
    page = FakeCalendarPage()

    cells = page.locator(".calendar-wrapper span.day:text-is('27')")
    cells.nth(0).click()

    assert page.clicks == [(27, False)], "unscoped selection hits the adjacent month"
