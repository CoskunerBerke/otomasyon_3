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

from unittest.mock import MagicMock

import automation.publishing.tiktok_ui_observer as tiktok_mod
from automation.publishing.tiktok_ui_observer import (
    CALENDAR_PICK_ATTEMPTS,
    DATE_READBACK_ATTEMPTS,
    DATE_READBACK_INTERVAL_SECONDS,
    DAY_CELL_VISIBLE_TIMEOUT_MS,
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


# ---------------------------------------------------------------- 2026-09-17
#
# CBM-REEL-2026-0063 wanted 21 September and the field stayed on the 17th, which stopped
# the TikTok phase at 6/14. The snapshot taken at that moment shows the calendar still
# open with the 17th selected and 21 rendered as `day valid` right there in the grid --
# so the cell was there and no click had landed on it. Nothing in the run log said
# whether the click was made, missed, or skipped, because those lines were logger.info
# and the run log only shows warnings.


def test_a_missed_pick_is_tried_again_before_failing():
    assert CALENDAR_PICK_ATTEMPTS >= 2, (
        "one flaky click fails the Reel, and the pipeline's answer is to re-upload the "
        "whole video to TikTok"
    )


def test_the_day_cell_is_given_time_to_appear():
    """400ms in an animated popup: a slow frame looked like a missing cell."""
    assert DAY_CELL_VISIBLE_TIMEOUT_MS >= 1500


def test_the_mismatch_says_whether_a_day_was_clicked_at_all():
    idx = SOURCE.index("Calendar UI readback mismatch")
    warning = SOURCE[idx:idx + 400]
    assert "tiklandi=" in warning and "aday sayisi=" in warning, (
        "a halting failure must say whether the cell was found and clicked"
    )


def _flaky_calendar(date_val, clicks, works_on_click):
    """September 2026 open on the right month; the day cell only takes on Nth click."""
    page = MagicMock()

    day = MagicMock()
    day.is_visible.return_value = True

    def on_click(*_a, **_k):
        clicks.append(1)
        if len(clicks) >= works_on_click:
            date_val[0] = "2026-09-21"

    day.click.side_effect = on_click

    cal = MagicMock()
    cal.is_visible.return_value = True

    def locator(sel):
        res = MagicMock()
        if "month-title" in sel:
            res.first = MagicMock(inner_text=MagicMock(return_value="Eylül"))
        elif "year-title" in sel:
            res.first = MagicMock(inner_text=MagicMock(return_value="2026"))
        elif "calendar-wrapper" in sel and "day" in sel:
            res.first = day
            res.count.return_value = 1
            res.nth.return_value = day
        elif "calendar-wrapper" in sel:
            res.first = cal
        else:
            res.first = MagicMock(
                is_visible=MagicMock(return_value=False),
                wait_for=MagicMock(side_effect=TimeoutError("not visible")),
            )
        return res

    page.locator.side_effect = locator
    return page


def test_a_click_that_does_not_take_is_retried_and_succeeds(monkeypatch):
    monkeypatch.setattr(tiktok_mod.time, "sleep", lambda *_: None)
    date_val = ["2026-09-17"]
    clicks = []

    date_input = MagicMock()
    date_input.is_visible.return_value = True
    date_input.get_attribute.side_effect = lambda a: date_val[0] if a == "value" else None
    date_input.input_value.side_effect = lambda: date_val[0]

    page = _flaky_calendar(date_val, clicks, works_on_click=2)
    observer = TikTokUIObserver(page)

    assert observer._set_schedule_date(date_input, "2026-09-21") is True
    assert len(clicks) == 2, "the second attempt is the one that lands"
    assert date_val[0] == "2026-09-21"


def test_a_cell_that_never_takes_still_fails_and_leaves_evidence(monkeypatch):
    """Retrying must not turn a real mismatch into a false success."""
    monkeypatch.setattr(tiktok_mod.time, "sleep", lambda *_: None)
    date_val = ["2026-09-17"]
    clicks = []
    captured = []

    date_input = MagicMock()
    date_input.is_visible.return_value = True
    date_input.get_attribute.side_effect = lambda a: date_val[0] if a == "value" else None
    date_input.input_value.side_effect = lambda: date_val[0]

    page = _flaky_calendar(date_val, clicks, works_on_click=99)
    observer = TikTokUIObserver(page)
    monkeypatch.setattr(observer, "capture_error_snapshot", lambda tag: captured.append(tag))

    assert observer._set_schedule_date(date_input, "2026-09-21") is False
    assert len(clicks) == CALENDAR_PICK_ATTEMPTS
    assert captured == ["tiktok_date_mismatch_calendar_open"], "evidence exactly once"
