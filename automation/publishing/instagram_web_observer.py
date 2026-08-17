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
        for sel in selectors:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=timeout_ms):
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
        return self._click(InstagramWebSelectors.OPEN_COMPOSER_BUTTONS, "İçeriği planla / Oluştur")

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
                    time.sleep(2.0)
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
                time.sleep(2.0)
                return True
            except Exception as e:
                logger.warning(f"[IG WEB] file chooser basarisiz: {e}")

        self.capture_error_snapshot("file_input_not_found")
        return False

    def advance_to_caption_step(self, max_steps: int = 3) -> bool:
        """Click 'İleri' through crop and filter screens until the caption step appears."""
        for step in range(max_steps):
            if self._first_visible(InstagramWebSelectors.CAPTION_INPUTS, timeout_ms=1500) is not None:
                logger.info(f"[IG WEB] Caption adimina ulasildi ({step} 'İleri').")
                return True
            if not self._click(InstagramWebSelectors.NEXT_BUTTONS, "İleri"):
                break
            time.sleep(1.2)

        if self._first_visible(InstagramWebSelectors.CAPTION_INPUTS, timeout_ms=2000) is not None:
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
        text = text[:2200]   # Instagram caption limit

        try:
            loc.click(timeout=3000)
            time.sleep(0.3)
            try:
                loc.fill(text)
            except Exception:
                self.page.keyboard.type(text)
            time.sleep(0.5)
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
        for text in label_texts:
            for row_sel in (
                f"div:has(> div > div > span:text-is('{text}'))",
                f"div:has(span:text-is('{text}'))",
            ):
                try:
                    row = self.page.locator(row_sel).last
                    if not row.is_visible(timeout=1200):
                        continue
                    sw = row.locator(InstagramWebSelectors.SWITCH_INPUTS[0]).last
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
            sw.click(timeout=3000)
            time.sleep(0.8)
        except Exception as e:
            logger.warning(f"[IG WEB] '{what}' tiklanamadi: {e}")
            return False

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

    def set_time(self, hour: int, minute: int) -> bool:
        """Fill the Hours/Minutes spinbuttons and read them back."""
        ok = True
        for selectors, value, what in (
            (InstagramWebSelectors.HOUR_INPUTS, hour, "Saat"),
            (InstagramWebSelectors.MINUTE_INPUTS, minute, "Dakika"),
        ):
            loc = self._first_visible(selectors)
            if loc is None:
                logger.warning(f"[IG WEB] '{what}' alani bulunamadi.")
                self.capture_error_snapshot("time_input_not_found")
                return False
            try:
                loc.click(timeout=2500)
                self.page.keyboard.press("Control+A")
                self.page.keyboard.type(f"{value:02d}")
                time.sleep(0.4)
            except Exception as e:
                logger.warning(f"[IG WEB] '{what}' yazilamadi: {e}")
                ok = False

        return ok and self.verify_time(hour, minute)

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

    def verify_date(self, target: datetime.datetime) -> bool:
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
        logger.warning(f"[IG WEB] Tarih uyusmuyor: beklenen '{wanted}', ekranda '{shown}'")
        return False

    # ------------------------------------------------------------------
    # submit
    # ------------------------------------------------------------------

    def click_schedule_and_verify(self, timeout_seconds: int = 30) -> Tuple[bool, str]:
        """Press 'Planla', but only after the schedule toggle is verified ON.

        With the toggle OFF the same primary control reads 'Paylaş' and posts
        immediately, so the label is re-checked right before clicking and any
        share-now wording aborts the click.
        """
        if not self.is_schedule_enabled():
            logger.error("[IG WEB] SCHEDULE_MODE_NOT_ACTIVE -- 'Planla' tiklanmayacak.")
            self.capture_error_snapshot("schedule_toggle_off")
            return False, "SCHEDULE_MODE_NOT_ACTIVE"

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

        try:
            btn.click(timeout=4000)
        except Exception as e:
            return False, f"SCHEDULE_CLICK_FAILED: {e}"

        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                body = (self.page.inner_text("body") or "").lower()
                if any(m in body for m in InstagramWebSelectors.SCHEDULE_SUCCESS_MARKERS):
                    logger.info("[IG WEB] Planlama onaylandi.")
                    return True, "INSTAGRAM_SCHEDULED"
            except Exception:
                pass
            time.sleep(1.5)

        self.capture_error_snapshot("schedule_confirmation_not_verified")
        return False, "SCHEDULE_CONFIRMATION_NOT_VERIFIED"
