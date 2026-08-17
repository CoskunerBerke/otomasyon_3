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


# ---------------------------------------------------------------------------
# Instagram's 20-minute minimum lead time
# (captured warning: "Şu andan en az 20 dakika sonra olan bir zaman seç")
# ---------------------------------------------------------------------------

def test_slot_less_than_20_minutes_away_is_rejected():
    now = datetime.datetime(2026, 8, 17, 19, 20)
    assert InstagramWebObserver.is_slot_too_soon(datetime.datetime(2026, 8, 17, 19, 30), now) is True
    assert InstagramWebObserver.is_slot_too_soon(datetime.datetime(2026, 8, 17, 19, 39), now) is True


def test_slot_at_least_20_minutes_away_is_accepted():
    now = datetime.datetime(2026, 8, 17, 19, 0)
    assert InstagramWebObserver.is_slot_too_soon(datetime.datetime(2026, 8, 17, 19, 30), now) is False
    assert InstagramWebObserver.is_slot_too_soon(datetime.datetime(2026, 8, 17, 22, 0), now) is False


def test_inline_too_soon_warning_blocks_submit():
    """The composer shows the warning inline; submitting anyway would silently fail."""
    page = _Page(schedule_on=True, body="Şu andan en az 20 dakika sonra olan bir zaman seç")
    obs = InstagramWebObserver(page)

    ok, reason = obs.click_schedule_and_verify(timeout_seconds=1)

    assert ok is False
    assert reason == "TIME_TOO_SOON"
    assert page.primary.clicks == 0


def test_no_warning_means_submit_proceeds():
    page = _Page(schedule_on=True, body="Gönderin planlandı")
    obs = InstagramWebObserver(page)

    ok, reason = obs.click_schedule_and_verify(timeout_seconds=3)

    assert ok is True
    assert page.primary.clicks == 1


# ---------------------------------------------------------------------------
# Date selection must work for ANY month/year -- this pipeline runs indefinitely,
# so nothing may assume the current month.
# ---------------------------------------------------------------------------

def test_date_format_covers_every_month_and_future_years():
    cases = {
        (2026, 1, 1): "1 Oca 2026",
        (2026, 8, 17): "17 Ağu 2026",
        (2026, 9, 3): "3 Eyl 2026",
        (2027, 2, 28): "28 Şub 2027",
        (2030, 12, 31): "31 Ara 2030",
    }
    for (y, m, d), expected in cases.items():
        assert InstagramWebObserver.format_tr_date(datetime.datetime(y, m, d)) == expected


def test_same_day_slot_needs_no_picker_interaction():
    """Instagram opens on today, so a same-day slot must not touch the calendar."""
    page = _Page()          # date button already reads 17 Ağu 2026
    obs = InstagramWebObserver(page)

    ok, reason = obs.select_date(datetime.datetime(2026, 8, 17, 19, 30))

    assert ok is True
    assert reason == "DATE_ALREADY_CORRECT"


def test_unresolvable_day_cell_reports_needs_user_html_and_clicks_nothing_wrong():
    """A day cell that cannot be resolved must never fall back to a guessed click --
    that would schedule the wrong date."""
    page = _Page()
    # Date button reports a different day than the target, and no day cell matches.
    obs = InstagramWebObserver(page)

    ok, reason = obs.select_date(datetime.datetime(2026, 8, 23, 19, 30), max_month_hops=0)

    assert ok is False
    assert reason in ("DATE_CELL_NOT_RESOLVED", "DATE_BUTTON_NOT_FOUND")


def test_day_cell_templates_are_parameterised_not_hardcoded():
    """Templates must be day-agnostic so any date works, now or years from now."""
    for tpl in InstagramWebSelectors.DAY_CELL_TEMPLATES:
        assert "{day}" in tpl
        rendered = tpl.format(day=23)
        assert "23" in rendered and "{day}" not in rendered


# ---------------------------------------------------------------------------
# Day cells are resolved by content, so correctness rests on verifying the date
# AFTER the click -- never on the selector having guessed right.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Real calendar DOM (captured 2026-08-17). The grid renders trailing days of the
# previous month and leading days of the next one, all aria-disabled -- so a
# text-only match for "1" would hit September 1st.
# ---------------------------------------------------------------------------

class _RealCalendarPage(_Page):
    def __init__(self, year=2026, month=8, today=17, **kw):
        super().__init__(**kw)
        self.year = year
        self.month = month
        self.today = today
        self.shown_date = self._fmt(year, month, today)
        self.clicked = []
        self.month_clicks = 0

    @staticmethod
    def _fmt(year, month, day):
        from automation.publishing.instagram_web_observer import TR_MONTHS
        return f"{day} {TR_MONTHS[month]} {year} Pzt"

    def _enabled_days(self):
        import calendar
        last = calendar.monthrange(self.year, self.month)[1]
        # Past days of the displayed month are disabled, like the real UI.
        start = self.today if (self.year, self.month) == (2026, 8) else 1
        return set(range(start, last + 1))

    def locator(self, selector):
        s = selector

        if "aria-label='Next month'" in s or "next month" in s.lower():
            btn = _Loc()

            def nxt():
                self.month_clicks += 1
                self.month = 1 if self.month == 12 else self.month + 1
                if self.month == 1:
                    self.year += 1
            btn.on_click = nxt
            return btn

        if "aria-label='Previous month'" in s or "previous month" in s.lower():
            btn = _Loc()

            def prv():
                self.month_clicks += 1
                self.month = 12 if self.month == 1 else self.month - 1
                if self.month == 12:
                    self.year -= 1
            btn.on_click = prv
            return btn

        if "role='grid'" in s or "right-of" in s:
            name = InstagramWebSelectors.TR_MONTHS_FULL[self.month]
            return _Loc(text=f"{name} {self.year}")

        if "gridcell" in s and "text-is('" in s:
            day = int(s.split("text-is('")[1].split("')")[0])
            # Only selectable cells exist for this selector -- exactly what
            # aria-disabled='false' buys us.
            if day not in self._enabled_days():
                return _Loc(visible=False, count=0)
            cell = _Loc(text=str(day))

            def pick(d=day):
                self.clicked.append((self.year, self.month, d))
                self.shown_date = self._fmt(self.year, self.month, d)
            cell.on_click = pick
            return cell

        if "aria-haspopup='dialog'" in s.lower():
            return _Loc(text=self.shown_date, attrs={"aria-expanded": "true"})

        return super().locator(s)


def test_reads_month_header():
    page = _RealCalendarPage(2026, 8)
    obs = InstagramWebObserver(page)
    assert obs.read_displayed_month() == (2026, 8)


def test_selects_a_later_day_in_the_displayed_month():
    page = _RealCalendarPage(2026, 8, today=17)
    obs = InstagramWebObserver(page)

    ok, reason = obs.select_date(datetime.datetime(2026, 8, 23, 19, 30))

    assert ok is True
    assert reason == "DATE_SELECTED"
    assert page.clicked == [(2026, 8, 23)]
    assert page.month_clicks == 0, "ayni ay icin ay degistirilmemeli"


def test_past_day_in_current_month_is_not_selectable():
    """Days before today are aria-disabled, so they must not resolve."""
    page = _RealCalendarPage(2026, 8, today=17)
    obs = InstagramWebObserver(page)

    ok, reason = obs.select_date(datetime.datetime(2026, 8, 5, 19, 30), max_month_hops=0)

    assert ok is False
    assert page.clicked == []


def test_adjacent_month_spillover_is_never_clicked():
    """Asking for the 1st must not hit the next month's greyed-out 1st sitting in the
    same grid -- the exact trap the aria-disabled filter exists to prevent."""
    page = _RealCalendarPage(2026, 8, today=17)
    obs = InstagramWebObserver(page)

    ok, _reason = obs.select_date(datetime.datetime(2026, 9, 1, 19, 30))

    # It must navigate into September, not click August's spillover cell.
    assert page.month_clicks >= 1
    assert all(m == 9 for (_y, m, _d) in page.clicked), f"yanlis ay tiklandi: {page.clicked}"


def test_navigates_forward_across_a_year_boundary():
    page = _RealCalendarPage(2026, 8, today=17)
    obs = InstagramWebObserver(page)

    ok, reason = obs.select_date(datetime.datetime(2027, 1, 15, 19, 30), max_month_hops=12)

    assert ok is True
    assert page.clicked == [(2027, 1, 15)]
