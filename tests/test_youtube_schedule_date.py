"""
Regression: a wrong schedule date must never be reported as success.

2026-09-10, CBM-2026-W37. Seven Reels reached YouTube; two of them carried the wrong
date. CBM-REEL-2026-0046 was due on 12 September at 22:00 and CBM-REEL-2026-0049 on the
14th at 19:30, and both landed on the 11th -- the day Studio offers by default. Both were
recorded as SCHEDULED.

Two defects, one after the other:

  * the calendar day selectors were pinned to '16 Ağustos 2026' (f-strings with no
    placeholder, left over from the August incident), so the click fell through to a
    generic day-number match and, when that missed, the field kept Studio's default.
  * reverify_date_match compared the day against a hardcoded list of August spellings,
    had a special case for the number 17, and returned True when nothing matched at all.
    From September the month test could not pass, so every call reached that fallthrough.

The second is the one that matters. A date that fails loudly costs a retry; a wrong date
that reports success loses the slot and nobody finds out.
"""
from unittest.mock import MagicMock

import pytest

from automation.publishing.youtube_studio_ui_observer import YouTubeStudioUIObserver


def _observer(field_value, selector_count=1):
    """An observer whose date field reads back `field_value`."""
    page = MagicMock()

    def locator(_sel):
        loc = MagicMock()
        loc.first.wait_for.return_value = None
        loc.first.input_value.return_value = field_value
        return loc

    page.locator.side_effect = locator
    obs = YouTubeStudioUIObserver.__new__(YouTubeStudioUIObserver)
    obs.page = page
    return obs


# --------------------------------------------------------------- parsing

@pytest.mark.parametrize("raw,expected", [
    ("11 Eyl 2026", (2026, 9, 11)),
    ("11 Eylül 2026", (2026, 9, 11)),
    ("12.09.2026", (2026, 9, 12)),
    ("12/09/2026", (2026, 9, 12)),
    ("Sep 14, 2026", (2026, 9, 14)),
    ("14 September 2026", (2026, 9, 14)),
    ("16 Ağustos 2026", (2026, 8, 16)),
])
def test_date_field_parses_every_locale_form(raw, expected):
    assert _observer("").parse_date_input_value(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "Geçersiz Tarih", "next tuesday"])
def test_unparseable_values_report_zeros(raw):
    assert _observer("").parse_date_input_value(raw)[1] == 0


# ------------------------------------------------------------ verification

def test_september_date_now_verifies():
    """The exact case the old month list could never satisfy."""
    ok, msg = _observer("12 Eyl 2026").reverify_date_match(2026, 9, 12)
    assert ok is True
    assert msg == "DATE_MATCH"


def test_the_bug_that_shipped_is_caught():
    """
    Field says the 11th, the slot wanted the 12th.

    This is CBM-REEL-2026-0046 exactly. It previously returned DATE_MATCH.
    """
    ok, msg = _observer("11 Eyl 2026").reverify_date_match(2026, 9, 12)
    assert ok is False
    assert "DATE_MISMATCH" in msg
    assert "11 Eyl 2026" in msg, "mesaj alanda ne yazdigini soylemeli"


def test_three_day_drift_is_caught():
    """CBM-REEL-2026-0049: due the 14th, landed on the 11th."""
    ok, _ = _observer("11 Eyl 2026").reverify_date_match(2026, 9, 14)
    assert ok is False


def test_wrong_month_same_day_is_caught():
    """Same day number in the wrong month used to satisfy the day-substring test."""
    ok, _ = _observer("12 Ağu 2026").reverify_date_match(2026, 9, 12)
    assert ok is False


def test_unreadable_field_fails_rather_than_assuming_success():
    """
    The old code returned True when it could not read anything.

    Not being able to confirm the date is not evidence that the date is right.
    """
    ok, msg = _observer("").reverify_date_match(2026, 9, 12)
    assert ok is False
    assert "DATE_UNREADABLE" in msg


def test_august_still_verifies():
    """The month it used to hardcode must keep working."""
    ok, _ = _observer("16 Ağustos 2026").reverify_date_match(2026, 8, 16)
    assert ok is True
