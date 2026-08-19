"""
DOM driver for Instagram's web scheduling flow.

Mirrors the YouTube Studio / TikTok Studio observers: semantic selectors only, at most 2
strategies per action, no force clicks, no JS click/dispatchEvent, no overlay removal, no
hashed-class anchors, and DOM evidence captured whenever something cannot be resolved.

The one non-negotiable here: a post may only ever be SCHEDULED. If the schedule toggle
cannot be verified ON, the composer's primary action is still "Paylaş" (share now) and
clicking it would publish immediately -- so the flow stops instead.
"""
import datetime
import logging
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from .instagram_web_selectors import InstagramWebSelectors

logger = logging.getLogger("ReelsAIFactory.InstagramWebObserver")

# Instagram keeps rendering long after "domcontentloaded", and processes an attached
# video before the composer will advance. These are the two places that were tuned in
# milliseconds and would read a slow step as a broken one -- the failure mode that cost
# this project three separate outages in one day (Flow, YouTube Studio, TikTok).
STEP_WAIT_MS = 15000
SWITCH_WAIT_MS = 4000
CAPTION_PROBE_MS = 1500
# After 'Planla', Instagram uploads + processes before confirming; ~1 min observed live.
SCHEDULE_CONFIRM_TIMEOUT_SECONDS = 240
UPLOAD_SETTLE_SECONDS = 5.0

TR_MONTHS = {
    1: "Oca", 2: "Şub", 3: "Mar", 4: "Nis", 5: "May", 6: "Haz",
    7: "Tem", 8: "Ağu", 9: "Eyl", 10: "Eki", 11: "Kas", 12: "Ara",
}


class InstagramWebObserver:
    """Drives instagram.com's create-post dialog to schedule a Reel."""

    def __init__(self, page: Any):
        self.page = page

    # ------------------------------------------------------------------
    # diagnostics
    # ------------------------------------------------------------------

    def capture_error_snapshot(self, tag: str) -> None:
        """Persist screenshot + HTML so an unresolved control can be fixed from evidence."""
        try:
            shots = Path("screenshots") / "errors"
            shots.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.page.screenshot(path=str(shots / f"error_ig_{tag}_{ts}.png"), full_page=True)
            (shots / f"error_ig_{tag}_{ts}.html").write_text(
                self.page.content(), encoding="utf-8", errors="ignore"
            )
        except Exception as e:
            logger.debug(f"[IG WEB] snapshot '{tag}' alinamadi: {e}")

    def _first_visible(self, selectors: List[str], timeout_ms: int = 2500) -> Optional[Any]:
        """Try each selector in turn, actually waiting up to `timeout_ms` for it to render.

        Locator.is_visible(timeout=...) ignores its timeout and returns instantly -- it is
        a snapshot check, not a wait. Instagram's composer is a React SPA that keeps
        rendering after "domcontentloaded", so an instant check catches it mid-render and
        reports every control as missing even when it appears a moment later. wait_for()
        is the call that actually polls for the timeout.
        """
        for sel in selectors:
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=timeout_ms)
                return loc
            except Exception:
                continue
        return None

    def _click(self, selectors: List[str], what: str, timeout_ms: int = 2500) -> bool:
        loc = self._first_visible(selectors, timeout_ms=timeout_ms)
        if loc is None:
            logger.warning(f"[IG WEB] '{what}' bulunamadi.")
            return False
        try:
            loc.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        try:
            loc.click(timeout=3000)
            time.sleep(0.8)
            return True
        except Exception as e:
            logger.warning(f"[IG WEB] '{what}' tiklanamadi: {e}")
            return False

    # ------------------------------------------------------------------
    # composer
    # ------------------------------------------------------------------

    def open_composer(self) -> bool:
        """Click the /scheduled_content/ page's own 'İçeriği planla' button.

        This must be called after navigating to /scheduled_content/ -- that page's button
        is the only entry point used, since it is the one guaranteed to open a composer
        with the schedule toggle. There is no fallback to the generic 'Oluştur' composer:
        that opens a different dialog with no scheduling at all, so a missing button is
        reported rather than silently swapped for the wrong flow.
        """
        if self._click(InstagramWebSelectors.OPEN_COMPOSER_BUTTONS, "İçeriği planla"):
            return True

        self.capture_error_snapshot("composer_button_not_found")
        logger.error("=" * 50)
        logger.error("STATUS: NEEDS_USER_HTML")
        logger.error("Platform: Instagram Web")
        logger.error("Target: /scheduled_content/ page's 'İçeriği planla' button")
        logger.error("Needed: outerHTML of that button and its parent/wrapper.")
        logger.error("=" * 50)
        return False

    def upload_file(self, video_path: Path) -> bool:
        """Attach the video. Prefers the hidden file input; falls back to the visible
        'Bilgisayardan seç' button driving a native file chooser."""
        video_path = Path(video_path).resolve()

        for sel in InstagramWebSelectors.FILE_INPUTS:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    loc.set_input_files(str(video_path))
                    logger.info(f"[IG WEB] Dosya dogrudan input'a verildi: {video_path.name}")
                    time.sleep(UPLOAD_SETTLE_SECONDS)
                    return True
            except Exception as e:
                logger.debug(f"[IG WEB] file input {sel}: {e}")

        btn = self._first_visible(InstagramWebSelectors.SELECT_FROM_COMPUTER_BUTTONS)
        if btn is not None:
            try:
                with self.page.expect_file_chooser(timeout=8000) as fc:
                    btn.click(timeout=3000)
                fc.value.set_files(str(video_path))
                logger.info(f"[IG WEB] Dosya file chooser ile verildi: {video_path.name}")
                time.sleep(UPLOAD_SETTLE_SECONDS)
                return True
            except Exception as e:
                logger.warning(f"[IG WEB] file chooser basarisiz: {e}")

        self.capture_error_snapshot("file_input_not_found")
        return False

    def advance_to_caption_step(self, max_steps: int = 3) -> bool:
        """Click 'İleri' through crop and filter screens until the caption step appears.

        Instagram processes the video after it is attached, and the crop screen's 'İleri'
        does not become usable until that finishes -- for a 30s Reel that is seconds, not
        milliseconds. Each wait here is therefore generous: a step that is merely slow
        must not be read as a composer that failed to advance.
        """
        for step in range(max_steps):
            # Quick look for the caption box -- on the crop and filter screens it is not
            # there, and waiting STEP_WAIT_MS for it on each of them cost ~30s per Reel
            # before the first 'İleri' was even pressed (2026-08-19). The patience belongs
            # on 'İleri' itself, which is the control Instagram holds back while the
            # video is processed.
            if self._first_visible(InstagramWebSelectors.CAPTION_INPUTS, timeout_ms=CAPTION_PROBE_MS) is not None:
                logger.info(f"[IG WEB] Caption adimina ulasildi ({step} 'İleri').")
                return True
            if not self._click(InstagramWebSelectors.NEXT_BUTTONS, "İleri", timeout_ms=STEP_WAIT_MS):
                break
            time.sleep(1.0)

        if self._first_visible(InstagramWebSelectors.CAPTION_INPUTS, timeout_ms=STEP_WAIT_MS) is not None:
            return True
        self.capture_error_snapshot("caption_step_not_reached")
        return False

    def fill_caption(self, caption: str, hashtags: Optional[List[str]] = None) -> bool:
        """Write caption + hashtags. This is the single place hashtags are appended for
        Instagram, mirroring the YouTube/TikTok contract."""
        loc = self._first_visible(InstagramWebSelectors.CAPTION_INPUTS)
        if loc is None:
            self.capture_error_snapshot("caption_input_not_found")
            return False

        text = caption.strip()
        if hashtags:
            tags = " ".join(t if t.startswith("#") else f"#{t}" for t in hashtags)
            text = f"{text}\n\n{tags}".strip()
        text = text[:2199]   # Instagram caption limit, minus the trailing space below

        # Instagram opens a hashtag autocomplete for the token under the cursor, and the
        # caption ends in a hashtag -- so after typing, a suggestion list ("#airpods",
        # "#aikido", ...) stays open over the form. It covered the AI-label switch on
        # 2026-08-19 and every click on it was intercepted, which read as the toggle
        # failing. A trailing space ends the token so no suggestion is active, and moving
        # focus off the field closes anything that is still showing. Tab only moves focus;
        # Escape is deliberately avoided because in this dialog it asks to discard the post.
        text = text + " "

        try:
            loc.click(timeout=3000)
            time.sleep(0.3)
            try:
                loc.fill(text)
            except Exception:
                self.page.keyboard.type(text)
            time.sleep(0.4)
            self.page.keyboard.press("Tab")
            time.sleep(0.6)
            return True
        except Exception as e:
            logger.warning(f"[IG WEB] Caption yazilamadi: {e}")
            self.capture_error_snapshot("caption_fill_failed")
            return False

    # ------------------------------------------------------------------
    # toggles
    # ------------------------------------------------------------------

    def _switch_near_text(self, label_texts: List[str]) -> Optional[Any]:
        """Resolve the role='switch' input belonging to a labelled row.

        Instagram renders label and switch as siblings inside one container with only
        hashed class names, so the row is located by its visible text and the switch is
        then taken from within that row -- text and role, never the hashed classes.
        """
        # Both strategies require the row to actually contain a switch. Without that,
        # `.last` resolves to the innermost div around the label text -- which holds no
        # switch -- and "İçeriği planla" also matches the composer entry button sitting
        # behind the dialog on /scheduled_content/. Confirmed against the real row markup
        # (2026-08-19): <div><div><span>LABEL</span></div><div>...<input role="switch"></div></div>.
        switch_sel = InstagramWebSelectors.SWITCH_INPUTS[0]
        for text in label_texts:
            for row_sel in (
                f"div:has(> div > div > span:text-is('{text}')):has({switch_sel})",
                f"div:has(span:text-is('{text}')):has({switch_sel})",
            ):
                try:
                    row = self.page.locator(row_sel).last
                    row.wait_for(state="visible", timeout=SWITCH_WAIT_MS)
                    sw = row.locator(switch_sel).last
                    if sw.count() > 0:
                        return sw
                except Exception:
                    continue
        return None

    def _is_switch_on(self, sw: Any) -> Optional[bool]:
        try:
            val = sw.get_attribute("aria-checked")
            if val is None:
                return None
            return str(val).strip().lower() == "true"
        except Exception:
            return None

    def set_toggle(self, label_texts: List[str], desired: bool, what: str) -> bool:
        """Bring a labelled switch to `desired`, verifying via aria-checked.

        Only a real click is used -- the aria-checked attribute is read for verification
        and never written, which would fake the state without changing Instagram's.
        """
        sw = self._switch_near_text(label_texts)
        if sw is None:
            logger.warning(f"[IG WEB] '{what}' anahtari bulunamadi.")
            self.capture_error_snapshot(f"toggle_not_found_{what}")
            return False

        state = self._is_switch_on(sw)
        if state is desired:
            logger.info(f"[IG WEB] '{what}' zaten {'ACIK' if desired else 'KAPALI'}.")
            return True

        try:
            sw.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass

        clicked = False
        for attempt in (1, 2):
            try:
                sw.click(timeout=3000)
                clicked = True
                break
            except Exception as e:
                if attempt == 1:
                    # Usually a popover (hashtag suggestions) intercepting the click. Move
                    # focus off whatever owns it and try once more.
                    logger.info(f"[IG WEB] '{what}' ilk tiklama engellendi ({type(e).__name__}); ustteki katman kapatilip tekrar denenecek.")
                    try:
                        self.page.keyboard.press("Tab")
                    except Exception:
                        pass
                    time.sleep(0.6)
                    sw = self._switch_near_text(label_texts) or sw
                else:
                    logger.warning(f"[IG WEB] '{what}' tiklanamadi: {e}")
                    self.capture_error_snapshot(f"toggle_click_failed_{what}")
        if not clicked:
            return False
        time.sleep(0.8)

        state = self._is_switch_on(self._switch_near_text(label_texts) or sw)
        if state is desired:
            logger.info(f"[IG WEB] '{what}' -> {'ACIK' if desired else 'KAPALI'} dogrulandi.")
            return True

        logger.warning(f"[IG WEB] '{what}' istenen duruma getirilemedi (aria-checked={state}).")
        self.capture_error_snapshot(f"toggle_verify_failed_{what}")
        return False

    def enable_ai_label(self) -> bool:
        """Instagram requires realistic AI-generated content to be labelled; every Reel
        this factory produces is Google Flow output, so this is always turned on."""
        return self.set_toggle(InstagramWebSelectors.AI_LABEL_TOGGLE_TEXTS, True, "Yapay zeka etiketi")

    def enable_schedule(self) -> bool:
        return self.set_toggle(InstagramWebSelectors.SCHEDULE_TOGGLE_TEXTS, True, "İçeriği planla")

    def is_schedule_enabled(self) -> bool:
        sw = self._switch_near_text(InstagramWebSelectors.SCHEDULE_TOGGLE_TEXTS)
        return bool(sw is not None and self._is_switch_on(sw))

    # ------------------------------------------------------------------
    # date / time
    # ------------------------------------------------------------------

    @staticmethod
    def format_tr_date(dt: datetime.datetime) -> str:
        """'17 Ağu 2026' -- the form Instagram shows on the date button."""
        return f"{dt.day} {TR_MONTHS.get(dt.month, '')} {dt.year}"

    @staticmethod
    def is_slot_too_soon(target: datetime.datetime, now: Optional[datetime.datetime] = None) -> bool:
        """Instagram rejects any slot less than MIN_LEAD_MINUTES from now."""
        now = now or datetime.datetime.now()
        lead = (target - now).total_seconds() / 60.0
        return lead < InstagramWebSelectors.MIN_LEAD_MINUTES

    def has_time_too_soon_warning(self) -> bool:
        """True when the composer is showing the 'at least 20 minutes from now' notice."""
        try:
            body = (self.page.inner_text("body") or "").lower()
        except Exception:
            return False
        return any(m in body for m in InstagramWebSelectors.TIME_TOO_SOON_MARKERS)

    def set_time(self, hour: int, minute: int) -> bool:
        """Fill the Hours/Minutes spinbuttons and read them back.

        These are Meta spinbuttons: <input role="spinbutton" aria-valuenow="14" value="">
        with an aria-hidden <label> painting the digits. The typed value lands in
        aria-valuenow, not value, so that is what is read back (captured 2026-08-19).
        """
        for selectors, value, what in (
            (InstagramWebSelectors.HOUR_INPUTS, hour, "Saat"),
            (InstagramWebSelectors.MINUTE_INPUTS, minute, "Dakika"),
        ):
            loc = self._first_visible(selectors)
            if loc is None:
                logger.warning(f"[IG WEB] '{what}' alani bulunamadi.")
                self.capture_error_snapshot("time_input_not_found")
                return False

            if not self._write_spinbutton(loc, value, what):
                self.capture_error_snapshot(f"time_set_failed_{what}")
                return False

        return self.verify_time(hour, minute)

    def _write_spinbutton(self, loc: Any, value: int, what: str) -> bool:
        """Two ways in, each read back before it is believed: typed digits, then fill()."""
        wanted = f"{value:02d}"

        def current() -> Optional[int]:
            try:
                now = loc.get_attribute("aria-valuenow")
                return int(str(now)) if now is not None and str(now).strip() != "" else None
            except Exception:
                return None

        if current() == value:
            return True

        # 1. Focus and type the digits, as a person would.
        try:
            try:
                loc.click(timeout=2500)
            except Exception:
                loc.focus()
            self.page.keyboard.press("Control+A")
            self.page.keyboard.type(wanted)
            time.sleep(0.5)
            if current() == value:
                return True
        except Exception as e:
            logger.debug(f"[IG WEB] {what}: yazarak ayarlanamadi: {e}")

        # 2. Set the value through the input itself.
        try:
            loc.fill(wanted)
            time.sleep(0.5)
            if current() == value:
                return True
        except Exception as e:
            logger.debug(f"[IG WEB] {what}: fill ile ayarlanamadi: {e}")

        logger.warning(f"[IG WEB] '{what}' {wanted} yapilamadi (aria-valuenow={current()}).")
        return False

    def verify_time(self, hour: int, minute: int) -> bool:
        """Read back aria-valuenow rather than trusting the typing."""
        for selectors, expected, what in (
            (InstagramWebSelectors.HOUR_INPUTS, hour, "Saat"),
            (InstagramWebSelectors.MINUTE_INPUTS, minute, "Dakika"),
        ):
            loc = self._first_visible(selectors, timeout_ms=1500)
            if loc is None:
                return False
            try:
                now = loc.get_attribute("aria-valuenow")
                if now is None or int(str(now)) != int(expected):
                    logger.warning(f"[IG WEB] {what} dogrulanamadi: beklenen {expected}, okunan {now}")
                    return False
            except Exception:
                return False
        logger.info(f"[IG WEB] Saat dogrulandi: {hour:02d}:{minute:02d}")
        return True

    def select_date(self, target: datetime.datetime, max_month_hops: int = 14) -> Tuple[bool, str]:
        """
        Pick `target`'s day from the date picker, for ANY month/year.

        Instagram opens on the current month, so reaching a later slot may need one or
        more "next month" hops. Written generically because this pipeline runs
        indefinitely -- nothing here assumes a particular month or year.

        If the date already reads correctly (same-day slots), nothing is clicked. If the
        day cell cannot be resolved, DOM evidence is captured and NEEDS_USER_HTML is
        reported rather than clicking a guessed cell and scheduling the wrong day.
        """
        if self.verify_date(target, strict=False):
            return True, "DATE_ALREADY_CORRECT"

        btn = self._first_visible(InstagramWebSelectors.DATE_PICKER_BUTTONS, timeout_ms=2000)
        if btn is None:
            self.capture_error_snapshot("date_button_not_found")
            return False, "DATE_BUTTON_NOT_FOUND"

        try:
            if str(btn.get_attribute("aria-expanded") or "").lower() != "true":
                btn.click(timeout=3000)
                time.sleep(1.0)
        except Exception as e:
            return False, f"DATE_PICKER_OPEN_FAILED: {e}"

        # Navigate by reading the month header rather than clicking hopefully: the header
        # states exactly which month is displayed, so the number of hops is known instead
        # of guessed, and a stuck header is detected immediately.
        for _hop in range(max_month_hops + 1):
            shown = self.read_displayed_month()
            if shown is None:
                logger.warning("[IG WEB] Ay basligi okunamadi.")
                break

            if shown == (target.year, target.month):
                if self._click_day_cell(target.day):
                    time.sleep(0.8)
                    if self.verify_date(target):
                        logger.info(f"[IG WEB] Tarih secildi: {self.format_tr_date(target)}")
                        return True, "DATE_SELECTED"
                logger.warning(f"[IG WEB] {target.day} gunu secilemedi (dolu/gecmis olabilir).")
                break

            if (target.year, target.month) < shown:
                if not self._click(InstagramWebSelectors.PREV_MONTH_BUTTONS, "onceki ay", timeout_ms=1200):
                    break
            else:
                if not self._click(InstagramWebSelectors.NEXT_MONTH_BUTTONS, "sonraki ay", timeout_ms=1200):
                    break
            time.sleep(0.8)

            if self.read_displayed_month() == shown:
                logger.warning("[IG WEB] Ay degismedi, navigasyon durdu.")
                break

        self.capture_error_snapshot("date_cell_not_resolved")
        logger.error("=" * 50)
        logger.error("STATUS: NEEDS_USER_HTML")
        logger.error("Platform: Instagram Web")
        logger.error(f"Target: date picker day cell for {self.format_tr_date(target)}")
        logger.error("Needed: outerHTML of the OPEN calendar dialog (one day cell + the")
        logger.error("        month header + the next-month arrow).")
        logger.error("=" * 50)
        return False, "DATE_CELL_NOT_RESOLVED"

    def read_displayed_month(self) -> Optional[Tuple[int, int]]:
        """Parse the calendar header ("Ağustos 2026") into (year, month)."""
        for sel in InstagramWebSelectors.MONTH_HEADER:
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=1200)
                text = (loc.inner_text() or "").strip()
            except Exception:
                continue

            for num, name in InstagramWebSelectors.TR_MONTHS_FULL.items():
                if name.lower() in text.lower():
                    for token in text.replace(name, " ").split():
                        if token.isdigit() and len(token) == 4:
                            return int(token), num
        return None

    def _click_day_cell(self, day: int) -> bool:
        """Click the selectable grid cell for `day` in the displayed month.

        aria-disabled='false' is essential, not cosmetic: the grid also renders trailing
        days of the previous month and leading days of the next one (all disabled), so a
        text-only match for "1" would land on the following month's 1st. Past days of the
        current month are disabled the same way, so an unbookable day simply won't match.
        """
        for template in InstagramWebSelectors.DAY_CELL_TEMPLATES:
            sel = template.format(day=day)
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=1000)
                loc.click(timeout=2500)
                return True
            except Exception:
                continue
        return False

    def verify_date(self, target: datetime.datetime, strict: bool = True) -> bool:
        """Confirm the date button already shows the target day.

        Instagram defaults to today, so same-day slots need no interaction. A different
        day requires the picker dialog, whose day cells are not in the captured DOM --
        rather than guess at them the flow reports NEEDS_USER_HTML.
        """
        btn = self._first_visible(InstagramWebSelectors.DATE_PICKER_BUTTONS, timeout_ms=2000)
        if btn is None:
            return False
        try:
            shown = (btn.inner_text() or "").strip()
        except Exception:
            return False
        wanted = self.format_tr_date(target)
        if wanted in shown:
            logger.info(f"[IG WEB] Tarih dogrulandi: {shown}")
            return True
        # Only a warning when the caller says so. select_date() calls this first to see
        # whether the picker is needed at all, and at that moment the field still shows
        # today -- logging that as a mismatch made a normal run read like a failure.
        log = logger.warning if strict else logger.info
        log(f"[IG WEB] Tarih henuz '{shown}', hedef '{wanted}'" + ("" if strict else " -- secici aciliyor."))
        return False

    # ------------------------------------------------------------------
    # submit
    # ------------------------------------------------------------------

    def click_schedule_and_verify(self, timeout_seconds: int = SCHEDULE_CONFIRM_TIMEOUT_SECONDS) -> Tuple[bool, str]:
        """Press 'Planla', but only after the schedule toggle is verified ON.

        With the toggle OFF the same primary control reads 'Paylaş' and posts
        immediately, so the label is re-checked right before clicking and any
        share-now wording aborts the click.
        """
        if not self.is_schedule_enabled():
            logger.error("[IG WEB] SCHEDULE_MODE_NOT_ACTIVE -- 'Planla' tiklanmayacak.")
            self.capture_error_snapshot("schedule_toggle_off")
            return False, "SCHEDULE_MODE_NOT_ACTIVE"

        # Instagram will not accept a slot under 20 minutes away and says so inline.
        # Submitting anyway just fails to schedule, so stop while the reason is still clear.
        if self.has_time_too_soon_warning():
            logger.error("[IG WEB] TIME_TOO_SOON -- Instagram en az 20 dk sonrasini istiyor.")
            self.capture_error_snapshot("time_too_soon")
            return False, "TIME_TOO_SOON"

        btn = self._first_visible(InstagramWebSelectors.SCHEDULE_SUBMIT_BUTTONS)
        if btn is None:
            self.capture_error_snapshot("schedule_button_not_found")
            logger.error("=" * 50)
            logger.error("STATUS: NEEDS_USER_HTML")
            logger.error("Platform: Instagram Web")
            logger.error("Target: composer 'Planla' button")
            logger.error("Needed: outerHTML of the Planla button and its parent/wrapper.")
            logger.error("=" * 50)
            return False, "SCHEDULE_BUTTON_NOT_FOUND"

        try:
            label = (btn.inner_text() or "").strip().lower()
        except Exception:
            label = ""
        if label and label not in ("planla", "schedule"):
            if any(bad in label for bad in InstagramWebSelectors.FORBIDDEN_IMMEDIATE_SHARE_LABELS):
                logger.error(f"[IG SAFETY] Birincil buton '{label}' -- aninda paylasim, tiklanmayacak.")
                self.capture_error_snapshot("primary_button_is_share_now")
                return False, "PUBLISH_NOW_BUTTON_REFUSED"

        # Stale-state guard: if the success wording is ALREADY on the page before the
        # click, a later sighting of it proves nothing about this Reel. Refuse rather than
        # submit into a state that cannot be verified.
        try:
            pre = (self.page.inner_text("body") or "").lower()
        except Exception:
            pre = ""
        if self._has_success_marker(pre):
            self.capture_error_snapshot("success_marker_present_before_submit")
            logger.error("[IG WEB] Gonderimden ONCE sayfada basari metni var -- onay guvenilir olamaz, tiklanmayacak.")
            return False, "STALE_SUCCESS_STATE_BEFORE_SUBMIT"

        try:
            btn.click(timeout=4000)
        except Exception as e:
            return False, f"SCHEDULE_CLICK_FAILED: {e}"

        # From here on the submit HAS happened. Whatever the read-back says, this Reel
        # must never be submitted again by a retry -- that is how a post ends up twice on
        # the account, and this system may not delete the extra one.
        #
        # Instagram uploads and processes the video after 'Planla', then shows a dialog
        # titled "Reels videosu planlandı" (first with a spinner, then a checkmark) and a
        # "Bitti" button. On 2026-08-19 that took about a minute; the old 30s window read
        # a successful schedule as a failure.
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                body = (self.page.inner_text("body") or "").lower()
                # Both halves are required: the success phrase AND the dialog's own
                # "Bitti" button on screen. The phrase alone was fooled once.
                if self._has_success_marker(body) and self._success_dialog_visible():
                    logger.info("[IG WEB] Planlama onaylandi (basari penceresi + Bitti gorundu).")
                    self.capture_success_evidence()
                    self._close_success_dialog()
                    return True, "INSTAGRAM_SCHEDULED"
            except Exception:
                pass
            time.sleep(2.0)

        self.capture_error_snapshot("schedule_confirmation_not_verified")
        return False, "SUBMITTED_CONFIRMATION_TIMEOUT"

    @staticmethod
    def _has_success_marker(lower_body: str) -> bool:
        return any(m in lower_body for m in InstagramWebSelectors.SCHEDULE_SUCCESS_MARKERS)

    def _success_dialog_visible(self) -> bool:
        for sel in InstagramWebSelectors.SUCCESS_DIALOG_DONE_BUTTONS:
            try:
                if self.page.locator(sel).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        return False

    def capture_success_evidence(self) -> None:
        """
        One screenshot per confirmed schedule. Failures already leave evidence; a false
        success leaves none, which is exactly what made the missing 14th post on
        2026-08-19 undiagnosable. Cheap insurance: a PNG per Reel.
        """
        try:
            self.screenshots_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.page.screenshot(path=str(self.screenshots_dir / f"ok_ig_scheduled_{ts}.png"))
        except Exception:
            pass

    def _close_success_dialog(self) -> None:
        """
        Press "Bitti" on the success dialog so the next Reel starts from a clean page.
        Captured 2026-08-19: <div role="button" tabindex="0">Bitti</div>, hashed classes
        only -- matched by role and exact text. Missing it is harmless (the next Reel
        reloads the page anyway), so this never fails the schedule.
        """
        # Let the spinner turn into the checkmark before dismissing.
        time.sleep(3.0)
        for sel in InstagramWebSelectors.SUCCESS_DIALOG_DONE_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                loc.wait_for(state="visible", timeout=5000)
                loc.click(timeout=3000)
                logger.info("[IG WEB] Basari penceresi 'Bitti' ile kapatildi.")
                time.sleep(1.0)
                return
            except Exception:
                continue
        logger.info("[IG WEB] 'Bitti' bulunamadi; sonraki Reel sayfayi zaten yeniden yukleyecek.")
