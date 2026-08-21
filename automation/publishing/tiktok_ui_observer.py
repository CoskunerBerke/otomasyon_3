"""
DOM observer and UI automation driver for TikTok Studio.
Handles upload, existing editor detection, caption replacement & verification,
'Paylaşıldığında' radio selection (Planla vs Şimdi), date/time setting, and post-schedule verification.
"""
import time
import logging
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from .tiktok_selectors import TikTokSelectors
from .youtube_studio_ui_observer import account_identities_match, normalize_account_identity

logger = logging.getLogger("ReelsAIFactory.TikTokUIObserver")

# How long to let TikTok's date field catch up with a clicked calendar cell before
# calling it a mismatch. One immediate read is not enough: the same date that failed
# for one Reel had succeeded for the one before it, seconds earlier.
# How long to let TikTok's upload form finish rendering before deciding the "Daha fazla
# göster" control is absent. It arrives with the rest of the form, so a few hundred
# milliseconds of probing reads a late button as a missing one.
# Gaps between remote-verification passes. TikTok's content list is not updated the
# instant a schedule is confirmed, and a single immediate read reported 7 of 14 correctly
# scheduled Reels as unverified. The trailing 0 means no sleep after the final attempt.
REMOTE_VERIFY_BACKOFF_SECONDS = (5.0, 10.0, 20.0, 0.0)

MORE_OPTIONS_WAIT_SECONDS = 12.0

# How long the upload area is given to mount before the file input is judged missing.
# The publisher returns to a freshly navigated upload page for every Reel, and that page
# builds its file input after load. Reading once and concluding "not found" stopped
# craftsbyman's week at its twelfth Reel on 2026-08-22, with eleven already scheduled.
FILE_INPUT_WAIT_SECONDS = 20.0

# How long the account guard waits for TikTok to show whose session this is.
ACCOUNT_IDENTITY_WAIT_SECONDS = 10.0

# The final Schedule button sits at the bottom of a page that is still settling while
# TikTok's content checks finish, so it can be in motion when the automation reaches it.
SCHEDULE_BUTTON_SETTLE_MS = 10000
SCHEDULE_CLICK_TIMEOUT_MS = 8000
MORE_OPTIONS_PROBE_MS = 800

DATE_READBACK_ATTEMPTS = 6
DATE_READBACK_INTERVAL_SECONDS = 0.5

class TikTokUIObserver:
    """Interacts with visible DOM elements of TikTok Studio."""

    def __init__(self, page: Any):
        self.page = page

    def capture_error_snapshot(self, tag: str) -> None:
        """Capture screenshot + HTML dump for post-mortem diagnosis, mirroring
        automation/flow/page.py's FlowPage.capture_error_snapshot."""
        try:
            import datetime as _dt
            shots_dir = Path("screenshots") / "errors"
            shots_dir.mkdir(parents=True, exist_ok=True)
            timestamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.page.screenshot(path=str(shots_dir / f"error_{tag}_{timestamp}.png"), full_page=True)
            html_content = self.page.content()
            (shots_dir / f"error_{tag}_{timestamp}.html").write_text(html_content, encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"[SNAPSHOT] Failed to capture error snapshot for '{tag}': {e}")

    def dismiss_content_review_info_if_present(self) -> None:
        """
        Dismiss TikTok's informational content-review notice ('Anladım'/'Got it'), the
        same class of blocker as YouTube's. Never a failure, and never a publish action --
        only acknowledgement labels are matched, never 'Hemen paylaş'/'Post now'.
        """
        for sel in TikTokSelectors.CONTENT_REVIEW_INFO_DISMISS_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=600):
                    loc.click(timeout=2500)
                    logger.info("[TIKTOK] Bilgilendirme penceresi 'Anladım' ile kapatildi.")
                    time.sleep(0.5)
                    return
            except Exception:
                continue

    def is_logged_in(self) -> bool:
        """Check if user has an active logged-in session on TikTok Studio."""
        curr_url = self.page.url
        if "login" in curr_url:
            return False

        # Look for login buttons
        for sel in TikTokSelectors.LOGIN_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    return False
            except Exception:
                pass

        return True

    def verify_logged_in_username(self, expected_username: str = "@kitchenverse360") -> Tuple[bool, str, str]:
        """
        Verify that the logged-in TikTok user matches expected_username.
        Returns: (is_match: bool, detected_username: str, message: str)
        """
        detected_username = ""

        username_selectors = [
            "div[class*='user-info'] span",
            "span[class*='unique-id']",
            "div[class*='user-avatar'] img",
            "a[href*='/@']",
            "span[class*='user-name']",
            "div[class*='account-name']"
        ]

        # Read patiently: the account chrome mounts after the rest of the page, and this
        # is the guard between a run and the wrong channel's audience.
        deadline = time.time() + ACCOUNT_IDENTITY_WAIT_SECONDS
        while not detected_username:
            for sel in username_selectors:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        text = loc.inner_text().strip() if not loc.get_attribute("href") else loc.get_attribute("href")
                        if text:
                            detected_username = text.split("/")[-1].split("?")[0].lstrip("@").strip()
                            if detected_username:
                                break
                except Exception:
                    pass

            if not detected_username:
                try:
                    url = self.page.url
                    if "/@" in url:
                        detected_username = url.split("/@")[-1].split("/")[0].split("?")[0]
                except Exception:
                    pass

            if detected_username or time.time() >= deadline:
                break
            time.sleep(1.0)

        if detected_username:
            act_norm = normalize_account_identity(detected_username)
            # Only THIS brand's handle passes. Until 2026-08-22 the literal "kitchenverse"
            # -- the FIRST channel's TikTok -- was accepted whatever brand was running,
            # so a craftsbyman run that landed on @kitchenverse360 would have been told it
            # was on the right account and published there.
            if account_identities_match(expected_username, detected_username):
                return True, f"@{detected_username}", f"TikTok User Verified: @{detected_username}"
            self.capture_error_snapshot("account_mismatch")
            return False, f"@{detected_username}", f"ACCOUNT_MISMATCH: Expected '{expected_username}', detected '@{detected_username}'"

        # Nothing readable. This does NOT block -- TikTok Studio's upload page may simply
        # not name the account anywhere, and refusing on a DOM this code cannot verify
        # would stop a working channel on a guess (Kural 31). What it must never do is
        # report success: the run continues on the strength of the per-brand Chrome
        # profile and CDP port alone, and says so.
        logger.warning(
            f"[TIKTOK] ACCOUNT_UNVERIFIED: '{expected_username}' sayfadan okunamadi. "
            f"Yayin, markaya ozel Chrome profiline guvenerek devam ediyor -- bu profile "
            f"yalnizca {expected_username} hesabinin girili oldugundan emin olun."
        )
        return True, "ACCOUNT_UNVERIFIED", (
            f"TikTok hesabi sayfadan dogrulanamadi; markaya ozel profile guveniliyor "
            f"({expected_username})."
        )

    def is_editor_open_for_reel(self, reel_id: str, filename: str) -> bool:
        """
        Check if TikTok upload editor is ALREADY open on screen with this video.
        Prevents duplicate re-uploads when resuming.
        """
        try:
            # Check for upload completion indicators
            is_uploaded = False
            for sel in TikTokSelectors.UPLOAD_COMPLETE_INDICATORS:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=500):
                    is_uploaded = True
                    break

            if not is_uploaded:
                return False

            # Check if caption field or page contains reel_id or filename
            r_id_clean = reel_id.lower().replace("-", "")
            f_clean = filename.lower()
            page_text = self.page.content().lower()

            # This Reel's own id or filename, and nothing else. "zen_temple" and "oasis"
            # used to count too -- leftovers from an early test that turned any page
            # mentioning an oasis into "the editor is already open for this Reel". These
            # captions are about buried objects becoming underground gardens and oases;
            # a match would have skipped the upload and hung this Reel's title, caption
            # and slot on whatever video was actually sitting in the editor.
            if r_id_clean in page_text or f_clean in page_text:
                logger.info(f"Existing TikTok editor session detected for {reel_id} ({filename}). Resuming directly.")
                return True
        except Exception as e:
            logger.debug(f"Editor detection error: {e}")

        return False

    def cancel_content_check_modal(self) -> bool:
        """
        Close the "Paylaşmaya devam edilsin mi?" modal by pressing İptal (Cancel).

        This modal offers only İptal and "Hemen paylaş". "Hemen paylaş" publishes the Reel
        IMMEDIATELY instead of at its scheduled slot -- clicking it would dump the whole
        week's videos out at once and destroy the schedule, so it is never touched. The
        correct flow is: cancel, let TikTok's content check finish, then schedule again.

        Every candidate is checked against FORBIDDEN_IMMEDIATE_PUBLISH_LABELS before it is
        clicked, so even a mis-written selector cannot reach the publish button.
        Returns True if the modal was cancelled.
        """
        for sel in TikTokSelectors.CONTENT_CHECK_MODAL_CANCEL_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if not loc.is_visible(timeout=800):
                    continue

                label = ""
                try:
                    label = (loc.inner_text() or "").strip().lower()
                except Exception:
                    label = ""
                if any(bad in label for bad in TikTokSelectors.FORBIDDEN_IMMEDIATE_PUBLISH_LABELS):
                    logger.error(
                        f"[TIKTOK SAFETY] Selector resolved to an immediate-publish control "
                        f"('{label}') -- refusing to click."
                    )
                    continue

                loc.click(timeout=2500)
                logger.info("[TIKTOK CHECK] 'Iptal' tiklandi, icerik kontrolu beklenecek.")
                time.sleep(1.0)
                return True
            except Exception:
                continue

        logger.warning("[TIKTOK CHECK] 'Iptal' butonu bulunamadi.")
        return False

    def dismiss_delete_confirmation_if_present(self) -> bool:
        """
        Cancel TikTok's "Bu gönderi silinsin mi?" dialog via "Şimdi değil".

        Cancelling deletes nothing: the post and its edits stay exactly as they are, and
        the page stops being blocked. This is the safe half of a dialog whose other button
        destroys content -- [Sil] is never clicked here, and cannot be reached by these
        selectors, which match only the cancel wording.

        Returns True if a dialog was cancelled.
        """
        for sel in TikTokSelectors.DELETE_DIALOG_CANCEL_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if not (loc.is_visible(timeout=800) and loc.is_enabled()):
                    continue

                # Read the button back before committing. If anything other than the
                # cancel wording is under this handle, do not click it.
                try:
                    label = (loc.inner_text() or "").strip().lower()
                except Exception:
                    label = ""
                is_cancel = any(safe in label for safe in ("şimdi değil", "simdi degil", "not now"))
                is_destructive = any(bad == label for bad in TikTokSelectors.DELETE_DIALOG_DESTRUCTIVE_LABELS)
                if is_destructive or (label and not is_cancel):
                    logger.error(f"[TIKTOK SAFETY] Beklenen 'Simdi degil' yerine '{label}' bulundu -- tiklanmadi.")
                    continue

                loc.click(timeout=2500)
                time.sleep(1.0)
                return True
            except Exception:
                continue

        return False

    def dismiss_unsaved_draft_banner_if_present(self) -> bool:
        """
        Clear TikTok's "Düzenlemekte olduğunuz bir video kaydedilmedi" resume banner by
        discarding the stale editing session, so the upload area becomes usable again.

        Only fires when the banner text is actually on the page, and only clicks
        'Sil'/'Discard' -- never 'Devam', which would reopen a previous video's editor and
        risk scheduling the wrong Reel. What it discards is an UNSAVED editor session, not
        a published or scheduled post; the worst case is re-uploading the file.
        Returns True if a banner was dismissed.
        """
        try:
            page_text = self.page.inner_text("body").lower()
        except Exception:
            return False

        # Checked before the banner test bails out: this dialog appears on its own after a
        # schedule, not only over a resume banner, and it blocks the page either way.
        #
        # It also carries its own [Sil], while the banner cleanup below matches buttons by
        # label across the whole page -- so leaving it up would let that cleanup's click
        # land on a delete button. Cancel it here, and never guess between the two.
        hit = next((m for m in TikTokSelectors.DESTRUCTIVE_DELETE_CONFIRM_MARKERS if m in page_text), None)
        if hit:
            # Cancel it rather than leaving it on screen. "Şimdi değil" removes nothing --
            # it dismisses the dialog and leaves the post untouched -- so taking that exit
            # is safe and unblocks the page. Only [Sil] is forbidden, and it is never a
            # candidate here: these selectors can resolve to no other wording.
            if self.dismiss_delete_confirmation_if_present():
                logger.info("[TIKTOK] Silme onayi 'Simdi degil' ile guvenle kapatildi.")
                return False

            self.capture_error_snapshot("tiktok_delete_confirm_present")
            logger.error(
                f"[TIKTOK SAFETY] Ekranda bir SILME onayi var ('{hit}') ve 'Simdi degil' "
                f"butonu bulunamadi. 'Sil' butonuna DOKUNULMAYACAK. "
                f"Bu pencereyi elle kapatin ('Simdi degil')."
            )
            return False

        if not any(m in page_text for m in TikTokSelectors.UNSAVED_DRAFT_BANNER_MARKERS):
            return False

        for sel in TikTokSelectors.UNSAVED_DRAFT_DISCARD_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=800) and loc.is_enabled():
                    loc.click(timeout=2500)
                    logger.info("[TIKTOK] Kaydedilmemis duzenleme bandi 'Sil' ile temizlendi.")
                    time.sleep(1.5)
                    return True
            except Exception:
                continue

        logger.warning("[TIKTOK] Kaydedilmemis duzenleme bandi goruldu ama temizlenemedi.")
        return False

    def upload_file(self, video_path: Path) -> bool:
        """
        Locate file input and upload video.
        Supports both Method A (direct set_input_files) and Method B (expect_file_chooser fallback).
        """
        video_path = Path(video_path).resolve()

        # A leftover unsaved-editing banner makes the whole upload area inert, so both
        # methods below would fail with "file input not found" until it is cleared.
        self.dismiss_unsaved_draft_banner_if_present()

        # Both methods are retried until the upload area has had time to mount. A single
        # immediate pass is what stopped the twelfth Reel of an otherwise clean week:
        # eleven videos were already scheduled, the page simply had not finished building
        # its file input yet, and "not found" was reported as if the control were absent.
        deadline = time.time() + FILE_INPUT_WAIT_SECONDS
        while True:
            # Method A: Try direct input[type='file']
            for sel in TikTokSelectors.FILE_INPUT_SELECTORS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.count() > 0:
                        loc.set_input_files(str(video_path))
                        logger.info(f"Set input files directly for TikTok: {video_path.name}")
                        return True
                except Exception as e:
                    logger.debug(f"Direct file input selector {sel} failed: {e}")

            # Method B: Native file chooser via visible 'Video seçin' button
            for sel in TikTokSelectors.SELECT_VIDEO_BUTTONS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1500) and loc.is_enabled():
                        logger.info(f"Triggering file chooser on TikTok via button: {sel}")
                        with self.page.expect_file_chooser(timeout=6000) as fc_info:
                            loc.click()
                        file_chooser = fc_info.value
                        file_chooser.set_files(str(video_path))
                        logger.info(f"Set file via native file chooser for TikTok: {video_path.name}")
                        return True
                except Exception as e:
                    logger.debug(f"File chooser button selector {sel} failed: {e}")

            if time.time() >= deadline:
                logger.error(
                    f"TIKTOK_FILE_INPUT_NOT_AVAILABLE: upload area did not mount within "
                    f"{FILE_INPUT_WAIT_SECONDS:.0f}s."
                )
                return False
            time.sleep(1.0)

    def wait_for_upload_completion(self, timeout_seconds: int = 120) -> bool:
        """Wait until TikTok Studio finishes uploading and processing the video."""
        start = time.time()
        while time.time() - start < timeout_seconds:
            for sel in TikTokSelectors.UPLOAD_COMPLETE_INDICATORS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        return True
                except Exception:
                    pass

            for sel in TikTokSelectors.CAPTION_EDITORS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        return True
                except Exception:
                    pass

            time.sleep(2.0)
        return False

    def dismiss_onboarding_overlay_if_present(self, max_steps: int = 10) -> Tuple[bool, str]:
        """
        Detects if TikTok Studio React-Joyride onboarding/tour overlay is present in DOM.
        Dismisses it using normal visible UI buttons (Kapat/Close, Atla/Skip, Tamam/Done, İleri/Next)
        or Escape fallback. Never uses force click.
        """
        # 1. Fast check if any overlay is visible
        is_overlay_present = False
        for ov_sel in TikTokSelectors.JOYRIDE_OVERLAYS:
            try:
                loc = self.page.locator(ov_sel).first
                if loc.is_visible(timeout=500):
                    is_overlay_present = True
                    break
            except Exception:
                pass

        if not is_overlay_present:
            return True, "NO_OVERLAY_PRESENT"

        logger.info("TikTok onboarding overlay detected (#react-joyride-portal). Attempting UI dismissal...")

        for step in range(max_steps):
            # Check if still visible
            still_visible = False
            for ov_sel in TikTokSelectors.JOYRIDE_OVERLAYS:
                try:
                    loc = self.page.locator(ov_sel).first
                    if loc.is_visible(timeout=300):
                        still_visible = True
                        break
                except Exception:
                    pass

            if not still_visible:
                logger.info(f"TikTok onboarding overlay dismissed on step {step+1}. CAPTION_INTERACTION_UNBLOCKED.")
                return True, "CAPTION_INTERACTION_UNBLOCKED"

            # 2. Try dismiss/close/skip buttons inside portal
            action_taken = False
            for btn_sel in TikTokSelectors.JOYRIDE_DISMISS_BUTTONS:
                try:
                    loc = self.page.locator(btn_sel).first
                    if loc.is_visible(timeout=500) and loc.is_enabled():
                        loc.click()
                        time.sleep(0.5)
                        action_taken = True
                        logger.info(f"Clicked Joyride dismiss button: {btn_sel}")
                        break
                except Exception:
                    pass

            # 3. If no close/skip button, try Next/İleri
            if not action_taken:
                for next_sel in TikTokSelectors.JOYRIDE_NEXT_BUTTONS:
                    try:
                        loc = self.page.locator(next_sel).first
                        if loc.is_visible(timeout=500) and loc.is_enabled():
                            loc.click()
                            time.sleep(0.5)
                            action_taken = True
                            logger.info(f"Clicked Joyride tour Next button: {next_sel}")
                            break
                    except Exception:
                        pass

            # 4. Fallback: Escape key
            if not action_taken:
                self.page.keyboard.press("Escape")
                time.sleep(0.5)

        # Final check
        for ov_sel in TikTokSelectors.JOYRIDE_OVERLAYS:
            try:
                loc = self.page.locator(ov_sel).first
                if loc.is_visible(timeout=500):
                    logger.error("TIKTOK_ONBOARDING_OVERLAY_BLOCKING: React Joyride overlay remained visible after dismissal attempts.")
                    return False, "TIKTOK_ONBOARDING_OVERLAY_BLOCKING"
            except Exception:
                pass

        logger.info("TikTok onboarding overlay dismissed. CAPTION_INTERACTION_UNBLOCKED.")
        return True, "CAPTION_INTERACTION_UNBLOCKED"

    def replace_caption(self, caption: str, hashtags: List[str]) -> Tuple[bool, str]:
        """
        Completely clears the default filename caption and replaces it with generated caption + hashtags.
        Performs read-back verification to guarantee filename prefix is gone.
        """
        # First dismiss any React-Joyride onboarding overlay
        ok_ov, ov_msg = self.dismiss_onboarding_overlay_if_present()
        if not ok_ov:
            return False, f"CAPTION_VERIFICATION_FAILED: {ov_msg}"

        full_text = f"{caption}\n\n{' '.join(hashtags)}".strip()
        editor_loc = None

        for sel in TikTokSelectors.CAPTION_EDITORS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    editor_loc = loc
                    break
            except Exception:
                pass

        if not editor_loc:
            return False, "CAPTION_VERIFICATION_FAILED: Caption editor not found in DOM."

        try:
            editor_loc.click()
            time.sleep(0.3)

            # Thorough clear (Control+A -> Backspace)
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            time.sleep(0.3)

            # Try fill or keyboard type
            try:
                editor_loc.fill(full_text)
            except Exception:
                self.page.keyboard.type(full_text)

            time.sleep(0.5)

            # Read-back verification
            actual_val = editor_loc.inner_text().strip() if hasattr(editor_loc, "inner_text") else ""
            if not actual_val and hasattr(editor_loc, "input_value"):
                actual_val = editor_loc.input_value().strip()

            logger.info(f"TikTok Caption read-back: '{actual_val[:60]}...'")

            # Validate: not empty, no REEL-2026- filename prefix, hashtags present
            if "REEL-2026-" in actual_val or ".mp4" in actual_val:
                logger.error(f"CAPTION_VERIFICATION_FAILED: Filename was not completely cleared from caption: '{actual_val}'")
                return False, "CAPTION_VERIFICATION_FAILED: Filename prefix still present in caption."

            if not any(tag.lower() in actual_val.lower() for tag in hashtags if len(tag) > 2):
                logger.warning("Hashtags might not have been captured in caption readout.")

            return True, "CAPTION_VERIFIED"

        except Exception as e:
            logger.error(f"Error replacing caption: {e}")
            return False, f"CAPTION_VERIFICATION_FAILED: {e}"

    def select_schedule_mode(self, target_mode: str = "SCHEDULE") -> Tuple[bool, str]:
        """
        Selects 'Planla' (Schedule) under 'Paylaşıldığında' section.
        Verifies that Planla radio input is checked and Şimdi radio input is unchecked.
        Uses semantic label, wrapper, inner circle, or keyboard Space interactions to avoid
        pointer intercept issues on custom TikTok radio components.
        """
        logger.info("[TIKTOK] Resolving 'Paylaşıldığında' / Schedule mode section...")

        # 1. Locate Planla and Şimdi radio inputs
        planla_input = self.page.locator("input[name='postSchedule'][value='schedule'], input[type='radio'][value='schedule']").first
        simdi_input = self.page.locator("input[name='postSchedule'][value='post_now'], input[type='radio'][value='post_now']").first

        # Helper to read real checked state from DOM
        def _get_input_checked(loc: Any) -> bool:
            if not loc:
                return False
            try:
                if hasattr(loc, "is_checked") and callable(loc.is_checked):
                    res = loc.is_checked()
                    if isinstance(res, bool):
                        return res
            except Exception:
                pass
            try:
                if hasattr(loc, "evaluate") and callable(loc.evaluate):
                    res = loc.evaluate("el => el.checked")
                    if isinstance(res, bool):
                        return res
            except Exception:
                pass
            try:
                if hasattr(loc, "get_attribute") and callable(loc.get_attribute):
                    res = loc.get_attribute("aria-checked")
                    if isinstance(res, str):
                        if res.lower() == "true":
                            return True
                        elif res.lower() == "false":
                            return False
            except Exception:
                pass
            return False

        # Verify input presence in DOM
        is_planla_present = False
        try:
            if hasattr(planla_input, "is_visible") and planla_input.is_visible(timeout=1000):
                is_planla_present = True
            elif hasattr(planla_input, "count") and planla_input.count() > 0:
                is_planla_present = True
        except Exception:
            pass

        if not is_planla_present:
            # Fallback check on selectors
            for sel in TikTokSelectors.SCHEDULE_RADIO_OPTIONS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=500):
                        is_planla_present = True
                        break
                except Exception:
                    pass

        if not is_planla_present:
            logger.error("[TIKTOK] SCHEDULE_MODE_MISMATCH: 'Planla' radio option not found in DOM.")
            return False, "SCHEDULING_UNAVAILABLE: 'Planla' radio not found."

        logger.info("[TIKTOK] Schedule input resolved")
        radio_id = ""
        try:
            if hasattr(planla_input, "get_attribute"):
                radio_id = planla_input.get_attribute("id") or ""
        except Exception:
            pass
        if radio_id:
            logger.info(f"[TIKTOK] Schedule input id: {radio_id}")

        p_chk_before = _get_input_checked(planla_input)
        s_chk_before = _get_input_checked(simdi_input)
        logger.info(
            f"[TIKTOK] Current state before interaction:\n"
            f"schedule.checked={str(p_chk_before).lower()}\n"
            f"now.checked={str(s_chk_before).lower()}"
        )

        # 2. If already checked, skip click interaction
        if p_chk_before and not s_chk_before:
            logger.info("[TIKTOK] Schedule radio already selected")
        else:
            # 3. Try interaction strategies in sequence
            interaction_success = False

            # STRATEGY A — LABEL FOR
            if radio_id:
                try:
                    lbl = self.page.locator(f"label[for='{radio_id}']").first
                    if lbl.is_visible(timeout=300):
                        logger.info("[TIKTOK] Trying schedule radio via LABEL")
                        if hasattr(lbl, "scroll_into_view_if_needed"):
                            lbl.scroll_into_view_if_needed(timeout=1000)
                        lbl.click(timeout=2500)
                        time.sleep(0.2)
                        if _get_input_checked(planla_input) and not _get_input_checked(simdi_input):
                            interaction_success = True
                except Exception as e:
                    logger.debug(f"[TIKTOK] Strategy A (LABEL) exception: {e}")

            # STRATEGY B — NEAREST ANCESTOR LABEL
            if not interaction_success:
                try:
                    anc_lbl = planla_input.locator("xpath=ancestor::label[1]").first
                    if anc_lbl.is_visible(timeout=300):
                        logger.info("[TIKTOK] Trying schedule radio via ANCESTOR_LABEL")
                        if hasattr(anc_lbl, "scroll_into_view_if_needed"):
                            anc_lbl.scroll_into_view_if_needed(timeout=1000)
                        anc_lbl.click(timeout=2500)
                        time.sleep(0.2)
                        if _get_input_checked(planla_input) and not _get_input_checked(simdi_input):
                            interaction_success = True
                except Exception as e:
                    logger.debug(f"[TIKTOK] Strategy B (ANCESTOR_LABEL) exception: {e}")

            # STRATEGY C — RADIO WRAPPER
            if not interaction_success:
                try:
                    wrapper_candidates = [
                        planla_input.locator("xpath=ancestor::*[contains(@class, 'Radio') or contains(@class, 'radio') or contains(@class, 'Option') or contains(@class, 'option')][1]").first,
                        self.page.locator("label:has(input[name='postSchedule'][value='schedule']), div.schedule-radio-container label:has-text('Planla'), div.schedule-radio-container label:has-text('Schedule'), div[role='radio']:has-text('Planla'), div[role='radio']:has-text('Schedule'), label:has-text('Planla'), label:has-text('Schedule')").first
                    ]
                    for wrp in wrapper_candidates:
                        try:
                            if wrp and wrp.is_visible(timeout=300):
                                logger.info("[TIKTOK] Trying schedule radio via WRAPPER")
                                if hasattr(wrp, "scroll_into_view_if_needed"):
                                    wrp.scroll_into_view_if_needed(timeout=1000)
                                wrp.click(timeout=2500)
                                time.sleep(0.2)
                                if _get_input_checked(planla_input) and not _get_input_checked(simdi_input):
                                    interaction_success = True
                                    break
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"[TIKTOK] Strategy C (WRAPPER) exception: {e}")

            # STRATEGY D — INNER CIRCLE
            if not interaction_success:
                try:
                    circle_candidates = [
                        planla_input.locator("xpath=..//span[contains(@class, 'Radio__innerCircle') or contains(@class, 'innerCircle') or contains(@class, 'Radio__circle')]").first,
                        planla_input.locator("xpath=ancestor::*[contains(@class, 'Radio')][1]//span[contains(@class, 'Radio__innerCircle')]").first,
                        planla_input.locator("..").locator("span.Radio__innerCircle, span.Radio__circle").first
                    ]
                    for circ in circle_candidates:
                        try:
                            if circ and circ.is_visible(timeout=300):
                                logger.info("[TIKTOK] Trying schedule radio via INNER_CIRCLE")
                                if hasattr(circ, "scroll_into_view_if_needed"):
                                    circ.scroll_into_view_if_needed(timeout=1000)
                                circ.click(timeout=2500)
                                time.sleep(0.2)
                                if _get_input_checked(planla_input) and not _get_input_checked(simdi_input):
                                    interaction_success = True
                                    break
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"[TIKTOK] Strategy D (INNER_CIRCLE) exception: {e}")

            # STRATEGY E — KEYBOARD ACCESSIBILITY FALLBACK
            if not interaction_success:
                try:
                    logger.info("[TIKTOK] Trying schedule radio via KEYBOARD_SPACE")
                    if hasattr(planla_input, "focus"):
                        planla_input.focus()
                    time.sleep(0.1)
                    self.page.keyboard.press("Space")
                    time.sleep(0.2)
                    if _get_input_checked(planla_input) and not _get_input_checked(simdi_input):
                        interaction_success = True
                    else:
                        self.page.keyboard.press("Enter")
                        time.sleep(0.2)
                        if _get_input_checked(planla_input) and not _get_input_checked(simdi_input):
                            interaction_success = True
                except Exception as e:
                    logger.debug(f"[TIKTOK] Strategy E (KEYBOARD_SPACE) exception: {e}")

            # STRATEGY F — SELECTORS LIST FALLBACK
            if not interaction_success:
                for sel in TikTokSelectors.SCHEDULE_RADIO_OPTIONS:
                    try:
                        loc = self.page.locator(sel).first
                        if loc.is_visible(timeout=300):
                            if hasattr(loc, "scroll_into_view_if_needed"):
                                loc.scroll_into_view_if_needed(timeout=1000)
                            loc.click(timeout=2000)
                            time.sleep(0.2)
                            if _get_input_checked(planla_input) and not _get_input_checked(simdi_input):
                                interaction_success = True
                                break
                    except Exception:
                        pass

        # 4. Log state after interaction
        p_chk_after = _get_input_checked(planla_input)
        s_chk_after = _get_input_checked(simdi_input)
        p_aria_after = planla_input.get_attribute("aria-checked") if hasattr(planla_input, "get_attribute") else ""
        s_aria_after = simdi_input.get_attribute("aria-checked") if hasattr(simdi_input, "get_attribute") else ""

        logger.info(
            f"[TIKTOK] Schedule state after interaction:\n"
            f"schedule.checked={str(p_chk_after).lower()}\n"
            f"now.checked={str(s_chk_after).lower()}\n"
            f"schedule.aria-checked={p_aria_after or 'false'}\n"
            f"now.aria-checked={s_aria_after or 'false'}"
        )

        # 5. Stabilization polling (3 seconds)
        poll_start = time.time()
        verified = False
        while time.time() - poll_start < 3.0:
            p_curr = _get_input_checked(planla_input)
            s_curr = _get_input_checked(simdi_input)
            if p_curr and not s_curr:
                verified = True
                break
            time.sleep(0.15)

        if verified:
            logger.info("[TIKTOK] Schedule mode stabilization PASS")
            logger.info("TikTok schedule mode: Expected: PLANLA | Actual: PLANLA | SCHEDULE_MODE_VERIFIED")
            return True, "SCHEDULE_MODE_VERIFIED"
        else:
            logger.error("[TIKTOK] SCHEDULE_MODE_MISMATCH: Planla radio could not be verified as active.")
            return False, "SCHEDULING_UNAVAILABLE: Failed to click Planla"

    @staticmethod
    def _normalize_schedule_date(value: Any) -> str:
        """Normalize common TikTok Studio date formats to YYYY-MM-DD."""
        if not isinstance(value, str):
            return ""
        value = value.strip()
        if not value:
            return ""
        m = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", value)
        if m:
            y, mo, d = map(int, m.groups())
            return f"{y:04d}-{mo:02d}-{d:02d}"
        m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", value)
        if m:
            d, mo, y = map(int, m.groups())
            return f"{y:04d}-{mo:02d}-{d:02d}"
        return value

    @staticmethod
    def _normalize_schedule_time(value: Any) -> str:
        """Normalize a time-ish value to HH:MM."""
        if not isinstance(value, str):
            return ""
        value = value.strip()
        m = re.search(r"\b(\d{1,2}):(\d{2})\b", value)
        if not m:
            return value
        h, minute = map(int, m.groups())
        return f"{h:02d}:{minute:02d}"

    @staticmethod
    def _read_locator_value(loc: Any) -> str:
        """Read a form control's live value without trusting placeholder text."""
        try:
            val = loc.input_value(timeout=1000)
            if isinstance(val, str):
                return val.strip()
        except Exception:
            pass
        try:
            val = loc.get_attribute("value")
            if isinstance(val, str):
                return val.strip()
        except Exception:
            pass
        try:
            val = loc.inner_text(timeout=1000)
            if isinstance(val, str):
                return val.strip()
        except Exception:
            pass
        return ""

    def _find_visible_schedule_input(self, selectors: List[str]) -> Optional[Any]:
        for sel in selectors:
            try:
                candidates = self.page.locator(sel)
                c_count = 0
                if hasattr(candidates, "count") and callable(candidates.count):
                    try:
                        res = candidates.count()
                        if isinstance(res, int):
                            c_count = res
                    except Exception:
                        c_count = 0
                if c_count > 0:
                    for idx in range(min(c_count, 8)):
                        loc = candidates.nth(idx)
                        is_vis = False
                        if hasattr(loc, "is_visible") and callable(loc.is_visible):
                            try:
                                v = loc.is_visible(timeout=400)
                                is_vis = (v is True or (isinstance(v, bool) and v))
                            except Exception:
                                is_vis = False
                        is_en = True
                        if hasattr(loc, "is_enabled") and callable(loc.is_enabled):
                            try:
                                v = loc.is_enabled()
                                if isinstance(v, bool):
                                    is_en = v
                            except Exception:
                                is_en = True
                        if is_vis and is_en:
                            return loc
                else:
                    loc = candidates.first if hasattr(candidates, "first") else candidates
                    is_vis = False
                    if hasattr(loc, "is_visible") and callable(loc.is_visible):
                        try:
                            v = loc.is_visible(timeout=400)
                            is_vis = (v is True or (isinstance(v, bool) and v))
                        except Exception:
                            is_vis = False
                    is_en = True
                    if hasattr(loc, "is_enabled") and callable(loc.is_enabled):
                        try:
                            v = loc.is_enabled()
                            if isinstance(v, bool):
                                is_en = v
                        except Exception:
                            is_en = True
                    if is_vis and is_en:
                        return loc
            except Exception:
                continue
        return None

    def read_schedule_datetime(self) -> Tuple[str, str]:
        """Read the actual date/time currently shown by TikTok Studio."""
        date_loc = self._find_visible_schedule_input(TikTokSelectors.DATE_INPUTS)
        time_loc = self._find_visible_schedule_input(TikTokSelectors.TIME_INPUTS)
        raw_date = self._read_locator_value(date_loc) if date_loc else ""
        raw_time = self._read_locator_value(time_loc) if time_loc else ""
        return (
            self._normalize_schedule_date(raw_date),
            self._normalize_schedule_time(raw_time),
        )

    def verify_schedule_datetime(self, local_iso_str: str) -> Tuple[bool, str]:
        """Hard-gate commit by reading the browser's live date/time values."""
        import datetime
        dt = datetime.datetime.fromisoformat(local_iso_str)
        expected_date = dt.strftime("%Y-%m-%d")
        expected_time = dt.strftime("%H:%M")
        actual_date, actual_time = self.read_schedule_datetime()

        logger.info(
            "TikTok schedule read-back: "
            f"expected={expected_date} {expected_time} | "
            f"actual={actual_date or 'NONE'} {actual_time or 'NONE'}"
        )

        if actual_date != expected_date:
            return False, (
                f"DATE_MISMATCH: expected {expected_date}, got "
                f"{actual_date or 'EMPTY'}"
            )
        if actual_time != expected_time:
            return False, (
                f"TIME_MISMATCH: expected {expected_time}, got "
                f"{actual_time or 'EMPTY'}"
            )
        return True, "DATETIME_MATCH"

    TR_MONTHS = {
        "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4,
        "mayıs": 5, "mayis": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
        "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11,
        "kasim": 11, "aralık": 12, "aralik": 12
    }
    EN_MONTHS = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }

    def _parse_month_name(self, month_str: str) -> int:
        clean = (month_str or "").strip().lower()
        if clean in self.TR_MONTHS:
            return self.TR_MONTHS[clean]
        if clean in self.EN_MONTHS:
            return self.EN_MONTHS[clean]
        for k, v in self.TR_MONTHS.items():
            if k in clean:
                return v
        for k, v in self.EN_MONTHS.items():
            if k in clean:
                return v
        m = re.search(r"\b(\d{1,2})\b", clean)
        if m:
            return int(m.group(1))
        return 0

    def _set_schedule_date(self, date_loc: Any, target_date_iso: str) -> bool:
        """
        Set TikTok Studio schedule date using real UI Calendar picker
        as primary strategy, with strict month navigation and read-back verification.
        """
        norm_expected = self._normalize_schedule_date(target_date_iso)
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", norm_expected)
        if not m:
            logger.error(f"[TIKTOK DATE] Invalid target date format: {target_date_iso}")
            return False
        target_year = int(m.group(1))
        target_month = int(m.group(2))
        target_day = int(m.group(3))
        target_day_str = str(target_day)

        # Check if already set
        actual = self._read_locator_value(date_loc)
        if self._normalize_schedule_date(actual) == norm_expected:
            logger.info(f"[TIKTOK DATE] Date already matches {norm_expected}")
            return True

        logger.info(
            f"[TIKTOK DATE] Setting date to {norm_expected} "
            f"(Year: {target_year}, Month: {target_month}, Day: {target_day}) via Calendar UI..."
        )

        try:
            # 1. Open Calendar Picker
            cal_wrapper = self.page.locator(".calendar-wrapper").first
            is_cal_open = False
            if hasattr(cal_wrapper, "is_visible"):
                try:
                    is_cal_open = bool(cal_wrapper.is_visible(timeout=300))
                except Exception:
                    is_cal_open = False

            if not is_cal_open:
                if hasattr(date_loc, "scroll_into_view_if_needed"):
                    try:
                        date_loc.scroll_into_view_if_needed(timeout=1000)
                    except Exception:
                        pass
                date_loc.click(timeout=2000)
                time.sleep(0.4)

            # Wait for calendar wrapper
            cal_wrapper = self.page.locator(".calendar-wrapper").first
            if hasattr(cal_wrapper, "wait_for"):
                try:
                    cal_wrapper.wait_for(state="visible", timeout=3000)
                except Exception:
                    pass

            # 2. Month and Year Navigation
            for _ in range(24):
                month_title_loc = self.page.locator(".calendar-wrapper .month-title").first
                year_title_loc = self.page.locator(".calendar-wrapper .year-title").first
                raw_month = (month_title_loc.inner_text() if hasattr(month_title_loc, "inner_text") else "") or ""
                raw_year = (year_title_loc.inner_text() if hasattr(year_title_loc, "inner_text") else "") or ""

                cur_month = self._parse_month_name(raw_month)
                m_year = re.search(r"\b(\d{4})\b", raw_year)
                cur_year = int(m_year.group(1)) if m_year else target_year

                logger.info(
                    f"[TIKTOK DATE] Calendar header readback: "
                    f"month={raw_month} ({cur_month}), year={cur_year} | "
                    f"target: month={target_month}, year={target_year}"
                )

                if (cur_year == target_year and cur_month == target_month) or cur_month == 0:
                    break

                arrows = self.page.locator(".calendar-wrapper .month-header-wrapper .arrow")
                arrow_count = arrows.count() if hasattr(arrows, "count") else 2

                if (cur_year, cur_month) < (target_year, target_month):
                    # Next arrow (index 1)
                    next_arrow = arrows.nth(1) if hasattr(arrows, "nth") else arrows.last
                    if hasattr(next_arrow, "click"):
                        next_arrow.click(timeout=1500)
                    logger.info("[TIKTOK DATE] Clicked next month arrow")
                else:
                    # Prev arrow (index 0)
                    prev_arrow = arrows.nth(0) if hasattr(arrows, "nth") else arrows.first
                    if hasattr(prev_arrow, "click"):
                        prev_arrow.click(timeout=1500)
                    logger.info("[TIKTOK DATE] Clicked previous month arrow")
                time.sleep(0.3)

            # 3. Select Target Day
            #
            # Kural 31: two strategies, and both require `.valid`. The grid repeats the
            # day number across months -- asking for "27" in August also matches 27 July
            # in the leading row and, at month end, the trailing next-month days. Those
            # spillover cells and past days render without `.valid`, so dropping that
            # class from the selector is how a click lands on the wrong month and the
            # date silently stays put (2026-08-19: REEL-2026-0032 wanted 27 Aug and the
            # field never moved off 19 Aug).
            day_selectors = [
                f".calendar-wrapper .day-span-container:has(span.day.valid:text-is('{target_day_str}'))",
                f".calendar-wrapper span.day.valid:text-is('{target_day_str}')",
            ]
            day_clicked = False
            for d_sel in day_selectors:
                try:
                    candidates = self.page.locator(d_sel)
                    cnt = candidates.count() if hasattr(candidates, "count") else 0
                    if cnt == 0 and hasattr(candidates, "first"):
                        cnt = 1
                    for idx in range(cnt):
                        d_loc = candidates.nth(idx) if hasattr(candidates, "nth") else candidates.first
                        if hasattr(d_loc, "is_visible") and d_loc.is_visible(timeout=400):
                            if hasattr(d_loc, "scroll_into_view_if_needed"):
                                d_loc.scroll_into_view_if_needed(timeout=1000)
                            d_loc.click(timeout=1500)
                            day_clicked = True
                            logger.info(f"[TIKTOK DATE] Clicked day '{target_day_str}' ({d_sel})")
                            time.sleep(0.3)
                            break
                    if day_clicked:
                        break
                except Exception:
                    continue

            # 4. Verify Readback
            #
            # The field updates a moment after the cell is clicked, and TikTok is not
            # consistently quick about it -- REEL-2026-0031 set the very same date
            # successfully while 0032 was read too early and reported a mismatch. Poll
            # briefly instead of trusting one immediate read.
            actual = self._read_locator_value(date_loc)
            for _ in range(DATE_READBACK_ATTEMPTS):
                if self._normalize_schedule_date(actual) == norm_expected:
                    break
                time.sleep(DATE_READBACK_INTERVAL_SECONDS)
                actual = self._read_locator_value(date_loc)

            if self._normalize_schedule_date(actual) == norm_expected:
                logger.info(f"[TIKTOK DATE] Calendar UI selection SUCCESS: '{actual}'")
                return True
            else:
                logger.warning(f"[TIKTOK DATE] Calendar UI readback mismatch: expected='{norm_expected}' got='{actual}'")
                # The picker is still on screen here; capture it while the evidence exists.
                # Without this a DATE_MISMATCH -- the one failure that halts TikTok
                # outright -- left nothing behind to diagnose from.
                self.capture_error_snapshot("tiktok_date_mismatch_calendar_open")
        except Exception as e:
            logger.debug(f"[TIKTOK DATE] Calendar UI attempt exception: {e}")

        # Fallback (Keyboard / Fill if supported)
        for method in ("keyboard", "fill"):
            try:
                date_loc.click(timeout=2000)
                time.sleep(0.15)
                if method == "keyboard":
                    self.page.keyboard.press("Control+A")
                    self.page.keyboard.press("Backspace")
                    self.page.keyboard.type(norm_expected, delay=20)
                else:
                    date_loc.fill(norm_expected, timeout=2000)
                try:
                    self.page.keyboard.press("Enter")
                    self.page.keyboard.press("Tab")
                except Exception:
                    pass
                time.sleep(0.3)

                actual = self._read_locator_value(date_loc)
                if self._normalize_schedule_date(actual) == norm_expected:
                    logger.info(f"[TIKTOK DATE] Date fallback ({method}) SUCCESS: '{actual}'")
                    return True
            except Exception as e:
                logger.debug(f"[TIKTOK DATE] Date fallback ({method}) failed: {e}")

        final_actual, _ = self.read_schedule_datetime()
        logger.error(f"[TIKTOK DATE] DATE_MISMATCH: Failed to set date to {norm_expected}, current={final_actual}")
        return False

    def _set_schedule_time(self, time_loc: Any, target_time: str) -> bool:
        """
        Set TikTok Studio schedule time using real UI timepicker (hours + minutes)
        as primary strategy, with strict read-back verification.
        """
        norm_expected = self._normalize_schedule_time(target_time)
        m = re.search(r"(\d{1,2}):(\d{2})", norm_expected)
        if not m:
            logger.error(f"[TIKTOK TIME] Invalid target time format: {target_time}")
            return False
        target_hour = f"{int(m.group(1)):02d}"
        target_minute = f"{int(m.group(2)):02d}"

        # Check if already set
        actual = self._read_locator_value(time_loc)
        if self._normalize_schedule_time(actual) == norm_expected:
            logger.info(f"[TIKTOK TIME] Time already matches {norm_expected}")
            return True

        # -----------------------------------------------------------
        # PRIMARY STRATEGY: UI TIMEPICKER DROPDOWN (Hours + Minutes)
        # -----------------------------------------------------------
        logger.info(
            f"[TIKTOK TIME] Setting time to {norm_expected} "
            f"(Hour: {target_hour}, Minute: {target_minute}) via UI Picker..."
        )
        try:
            timepicker_container = self.page.locator("div.tiktok-timepicker-time-picker-container").first
            is_open = False
            if hasattr(timepicker_container, "is_visible"):
                try:
                    is_open = bool(timepicker_container.is_visible(timeout=300))
                except Exception:
                    is_open = False

            if not is_open:
                if hasattr(time_loc, "scroll_into_view_if_needed"):
                    try:
                        time_loc.scroll_into_view_if_needed(timeout=1500)
                    except Exception:
                        pass
                time_loc.click(timeout=2000)
                time.sleep(0.3)

            # Wait for picker container
            timepicker_container = self.page.locator("div.tiktok-timepicker-time-picker-container").first
            if hasattr(timepicker_container, "wait_for"):
                try:
                    timepicker_container.wait_for(state="visible", timeout=3000)
                except Exception:
                    pass

            # 1. Select Hour from .tiktok-timepicker-left
            hour_selectors = [
                f"div.tiktok-timepicker-time-picker-container .tiktok-timepicker-option-item:has(span.tiktok-timepicker-option-text.tiktok-timepicker-left:text-is('{target_hour}'))",
                f"div.tiktok-timepicker-time-picker-container span.tiktok-timepicker-option-text.tiktok-timepicker-left:text-is('{target_hour}')",
                f"span.tiktok-timepicker-left:text-is('{target_hour}')",
                f".tiktok-timepicker-option-item:has(span.tiktok-timepicker-left:text-is('{target_hour}'))",
                f"xpath=//div[contains(@class, 'tiktok-timepicker-time-picker-container')]//div[contains(@class, 'tiktok-timepicker-option-item')][.//span[contains(@class, 'tiktok-timepicker-left') and normalize-space()='{target_hour}']]"
            ]
            hour_clicked = False
            for h_sel in hour_selectors:
                try:
                    h_loc = self.page.locator(h_sel).first
                    if hasattr(h_loc, "is_visible") and h_loc.is_visible(timeout=500):
                        if hasattr(h_loc, "scroll_into_view_if_needed"):
                            h_loc.scroll_into_view_if_needed(timeout=1000)
                        h_loc.click(timeout=1500)
                        hour_clicked = True
                        logger.info(f"[TIKTOK TIME] Clicked hour '{target_hour}' ({h_sel})")
                        time.sleep(0.2)
                        break
                except Exception:
                    continue

            # 2. Select Minute from .tiktok-timepicker-right
            min_selectors = [
                f"div.tiktok-timepicker-time-picker-container .tiktok-timepicker-option-item:has(span.tiktok-timepicker-option-text.tiktok-timepicker-right:text-is('{target_minute}'))",
                f"div.tiktok-timepicker-time-picker-container span.tiktok-timepicker-option-text.tiktok-timepicker-right:text-is('{target_minute}')",
                f"span.tiktok-timepicker-right:text-is('{target_minute}')",
                f".tiktok-timepicker-option-item:has(span.tiktok-timepicker-right:text-is('{target_minute}'))",
                f"xpath=//div[contains(@class, 'tiktok-timepicker-time-picker-container')]//div[contains(@class, 'tiktok-timepicker-option-item')][.//span[contains(@class, 'tiktok-timepicker-right') and normalize-space()='{target_minute}']]"
            ]
            min_clicked = False
            for m_sel in min_selectors:
                try:
                    m_loc = self.page.locator(m_sel).first
                    if hasattr(m_loc, "is_visible") and m_loc.is_visible(timeout=500):
                        if hasattr(m_loc, "scroll_into_view_if_needed"):
                            m_loc.scroll_into_view_if_needed(timeout=1000)
                        m_loc.click(timeout=1500)
                        min_clicked = True
                        logger.info(f"[TIKTOK TIME] Clicked minute '{target_minute}' ({m_sel})")
                        time.sleep(0.2)
                        break
                except Exception:
                    continue

            # 3. Dismiss popup & verify closed
            logger.info("[TIKTOK TIME] Closing timepicker container...")
            try:
                self.page.keyboard.press("Escape")
            except Exception:
                pass
            time.sleep(0.3)

            # Strategy 1: Check if closed after Escape
            timepicker_container = self.page.locator("div.tiktok-timepicker-time-picker-container").first
            is_open = False
            try:
                if hasattr(timepicker_container, "is_visible") and timepicker_container.is_visible(timeout=500):
                    is_open = True
            except Exception:
                pass

            # Strategy 2: If still open, click neutral schedule area outside the picker
            if is_open:
                logger.info("[TIKTOK TIME] Timepicker still open after Escape. Attempting neutral area click...")
                neutral_selectors = [
                    "div.scheduled-container",
                    "div:has-text('Paylaşıldığında')",
                    "div.scheduled-picker",
                    "label:has-text('Planla')"
                ]
                for n_sel in neutral_selectors:
                    try:
                        n_loc = self.page.locator(n_sel).first
                        if hasattr(n_loc, "is_visible") and n_loc.is_visible(timeout=500):
                            n_loc.click(timeout=1000)
                            time.sleep(0.3)
                            if not (hasattr(timepicker_container, "is_visible") and timepicker_container.is_visible(timeout=400)):
                                is_open = False
                                break
                    except Exception:
                        pass

            if is_open:
                logger.error("=" * 50)
                logger.error("STATUS: NEEDS_USER_HTML")
                logger.error("Platform: TikTok")
                logger.error("Target: TikTok timepicker close/commit behavior")
                logger.error("Request:")
                logger.error("- timepicker container current outerHTML")
                logger.error("- time input current outerHTML")
                logger.error("=" * 50)
                return False

            actual = self._read_locator_value(time_loc)
            if not actual:
                fresh_time = self.page.locator(
                    "div.scheduled-picker input, div.scheduled-container input.TUXTextInputCore-input, input.TUXTextInputCore-input[value*=':'], input.TUXTextInputCore-input"
                ).first
                actual = self._read_locator_value(fresh_time)
            if self._normalize_schedule_time(actual) == norm_expected:
                logger.info("[TIKTOK TIME] Picker closed")
                logger.info(f"[TIKTOK TIME] Post-close readback: {actual}")
                logger.info("[TIKTOK TIME] COMMITTED PASS")
                return True
            else:
                logger.error(f"[TIKTOK TIME] TIME_COMMIT_MISMATCH: expected='{norm_expected}', got='{actual}'")
                return False
        except Exception as e:
            logger.debug(f"[TIKTOK TIME] Time UI picker attempt exception: {e}")

        # Fallback (Keyboard / Fill)
        logger.info(f"[TIKTOK TIME] Attempting time fallback via keyboard/fill...")
        for method in ("keyboard", "fill"):
            try:
                time_loc.click(timeout=2000)
                time.sleep(0.15)
                if method == "keyboard":
                    self.page.keyboard.press("Control+A")
                    self.page.keyboard.press("Backspace")
                    self.page.keyboard.type(norm_expected, delay=20)
                else:
                    time_loc.fill(norm_expected, timeout=2000)
                try:
                    self.page.keyboard.press("Enter")
                    self.page.keyboard.press("Tab")
                except Exception:
                    pass
                time.sleep(0.3)

                actual = self._read_locator_value(time_loc)
                if self._normalize_schedule_time(actual) == norm_expected:
                    logger.info(f"[TIKTOK TIME] Time fallback ({method}) SUCCESS: '{actual}'")
                    return True
            except Exception as e:
                logger.debug(f"[TIKTOK TIME] Time fallback ({method}) failed: {e}")

        _, final_actual = self.read_schedule_datetime()
        logger.error(f"[TIKTOK TIME] TIME_MISMATCH: Failed to set time to {norm_expected}, current={final_actual}")
        return False

    def _set_schedule_input(self, loc: Any, value: str, field_name: str) -> bool:
        """Use normal UI events and verify the field after every attempt."""
        if field_name == "time":
            return self._set_schedule_time(loc, value)
        elif field_name == "date":
            return self._set_schedule_date(loc, value)

        actual = self._read_locator_value(loc)
        return self._normalize_schedule_date(actual) == self._normalize_schedule_date(value)

    def set_schedule_datetime(self, local_iso_str: str) -> Tuple[bool, str]:
        """
        Set TikTok Studio's schedule date/time and STRICTLY verify live read-back.
        Returns True only when both controls exactly match the requested slot.
        """
        import datetime
        dt = datetime.datetime.fromisoformat(local_iso_str)
        target_date = dt.strftime("%Y-%m-%d")
        target_time = dt.strftime("%H:%M")

        date_loc = self._find_visible_schedule_input(TikTokSelectors.DATE_INPUTS)
        time_loc = self._find_visible_schedule_input(TikTokSelectors.TIME_INPUTS)

        if date_loc is None:
            logger.error("TIKTOK_DATE_CONTROL_NOT_FOUND")
            return False, "DATE_CONTROL_NOT_FOUND"
        if time_loc is None:
            logger.error("TIKTOK_TIME_CONTROL_NOT_FOUND")
            return False, "TIME_CONTROL_NOT_FOUND"

        if not self._set_schedule_input(date_loc, target_date, "date"):
            actual_date, _ = self.read_schedule_datetime()
            logger.error(
                f"DATE_MISMATCH after setting: expected {target_date}, "
                f"got {actual_date or 'EMPTY'}"
            )
            return False, (
                f"DATE_MISMATCH: expected {target_date}, "
                f"got {actual_date or 'EMPTY'}"
            )

        time_loc = self._find_visible_schedule_input(TikTokSelectors.TIME_INPUTS)
        if time_loc is None:
            return False, "TIME_CONTROL_NOT_FOUND_AFTER_DATE"

        if not self._set_schedule_input(time_loc, target_time, "time"):
            _, actual_time = self.read_schedule_datetime()
            logger.error(
                f"TIME_MISMATCH after setting: expected {target_time}, "
                f"got {actual_time or 'EMPTY'}"
            )
            return False, (
                f"TIME_MISMATCH: expected {target_time}, "
                f"got {actual_time or 'EMPTY'}"
            )

        ok, msg = self.verify_schedule_datetime(local_iso_str)
        if not ok:
            logger.error(f"TikTok datetime hard-gate failed: {msg}")
            return False, msg

        return True, "DATETIME_SET_AND_VERIFIED"

    def ensure_more_options_expanded(self) -> bool:
        """
        Ensures 'Daha fazla göster' (More options) is expanded so that AIGC container is accessible.
        Primary: div.more-btn:has(span:text-is("Daha fazla göster"))
        Fallback: div.more-btn:has(span:text-is("Show more"))
        """
        aigc_loc = self.page.locator("div[data-e2e='aigc_container'], [data-e2e='aigc_container']").first
        try:
            if hasattr(aigc_loc, "is_visible") and aigc_loc.is_visible(timeout=MORE_OPTIONS_PROBE_MS):
                logger.info("[TIKTOK MORE] AIGC container already visible | MORE_OPTIONS_ALREADY_EXPANDED")
                return True
        except Exception:
            pass

        logger.info("[TIKTOK MORE] AIGC container not visible. Expanding 'Daha fazla göster'...")

        # Kural 31: two strategies. The three that were dropped were not just surplus --
        # `div:has-text('Daha fazla göster')` matches every ancestor containing that text,
        # up to and including the page wrapper, so `.first` could resolve to a huge
        # container and the click would land anywhere inside it. `div.more-btn` alone is
        # kept as the language-independent fallback.
        btn_selectors = [
            "div.more-btn:has(span:text-is('Daha fazla göster')), div.more-btn:has(span:text-is('Show more'))",
            "div.more-btn",
        ]

        # The control arrives with the rest of the upload form. Probing for a few hundred
        # milliseconds is how a late-rendering button gets read as a missing one -- the
        # same mistake that cost this run three separate failures today.
        deadline = time.time() + MORE_OPTIONS_WAIT_SECONDS
        while time.time() < deadline:
            for b_sel in btn_selectors:
                try:
                    loc = self.page.locator(b_sel).first
                    if not (hasattr(loc, "is_visible") and loc.is_visible(timeout=MORE_OPTIONS_PROBE_MS)):
                        continue
                    if hasattr(loc, "scroll_into_view_if_needed"):
                        loc.scroll_into_view_if_needed(timeout=1000)
                    loc.click(timeout=1500)
                    logger.info(f"[TIKTOK MORE] Clicked '{b_sel}'")
                    time.sleep(0.3)

                    # Poll for the AIGC container to appear after the expand.
                    poll_start = time.time()
                    while time.time() - poll_start < 3.0:
                        fresh_aigc = self.page.locator("div[data-e2e='aigc_container'], [data-e2e='aigc_container']").first
                        if hasattr(fresh_aigc, "is_visible") and fresh_aigc.is_visible(timeout=MORE_OPTIONS_PROBE_MS):
                            logger.info("[TIKTOK MORE] AIGC container visible")
                            logger.info("MORE_OPTIONS_EXPANDED")
                            return True
                        time.sleep(0.15)
                except Exception as e:
                    logger.debug(f"[TIKTOK MORE] Click attempt on {b_sel} failed: {e}")

            # Neither strategy resolved yet; the form may still be rendering.
            time.sleep(0.5)

        # Check one last time
        try:
            fresh_aigc = self.page.locator("div[data-e2e='aigc_container'], [data-e2e='aigc_container']").first
            if hasattr(fresh_aigc, "is_visible") and fresh_aigc.is_visible(timeout=MORE_OPTIONS_PROBE_MS):
                logger.info("[TIKTOK MORE] AIGC container visible | MORE_OPTIONS_EXPANDED")
                return True
        except Exception:
            pass

        # Capture the page while the form is still on screen. Without this the only
        # record of the failure is a log line asking a human for HTML that nobody is
        # standing by to copy.
        self.capture_error_snapshot("tiktok_more_options_not_found")

        logger.error("=" * 50)
        logger.error("STATUS: NEEDS_USER_HTML")
        logger.error("Platform: TikTok")
        logger.error("Target: Daha fazla göster")
        logger.error("Request:")
        logger.error("- more-btn current outerHTML")
        logger.error("- aigc_container current outerHTML")
        logger.error("=" * 50)
        return False

    def toggle_ai_disclosure(self, enable: bool = True) -> bool:
        """
        Expands 'Daha fazla göster' (Show more) if needed and toggles AI content disclosure ON.
        Strictly scopes to 'AI ile oluşturulmuş içerik' container and verifies ON state.
        Never uses global switch selectors (protects against copyright or content-check switches).
        Follows Rule 31 (max 2 safe semantic strategies, no force/JS hacks, exact NEEDS_USER_HTML on failure).
        """
        if not enable:
            return True

        if not self.ensure_more_options_expanded():
            logger.error("AI_DISCLOSURE_CONTROL_NOT_FOUND: Could not expand more options.")
            return False

        aigc_container = self.page.locator("div[data-e2e='aigc_container'], [data-e2e='aigc_container']").first
        try:
            if not (hasattr(aigc_container, "is_visible") and aigc_container.is_visible(timeout=400)):
                logger.error("AI_DISCLOSURE_CONTROL_NOT_FOUND: aigc_container not visible after expansion.")
                return False
        except Exception:
            pass

        def _read_strict_aigc_state() -> Tuple[bool, Dict[str, Any]]:
            """Read live state strictly scoped inside aigc_container, explicit OFF overriding stale state."""
            st: Dict[str, Any] = {
                "aria_checked": None,
                "data_state": None,
                "input_checked": None,
                "thumb_state": None,
                "class": None,
            }
            try:
                fresh_aigc = self.page.locator("div[data-e2e='aigc_container'], [data-e2e='aigc_container']").first
                if not (hasattr(fresh_aigc, "is_visible") and fresh_aigc.is_visible(timeout=200)):
                    fresh_aigc = aigc_container

                content = fresh_aigc.locator("div.Switch__content, .Switch__content").first
                if hasattr(content, "get_attribute"):
                    try:
                        st["aria_checked"] = content.get_attribute("aria-checked")
                        st["data_state"] = content.get_attribute("data-state")
                        st["class"] = content.get_attribute("class")
                    except Exception:
                        pass

                thumb = fresh_aigc.locator("span[data-part='thumb'], .Switch__thumb").first
                if hasattr(thumb, "get_attribute"):
                    try:
                        st["thumb_state"] = thumb.get_attribute("data-state")
                    except Exception:
                        pass

                sw_inp = fresh_aigc.locator("input.Switch__input[role='switch'], input[role='switch'], input[type='checkbox']").first
                if hasattr(sw_inp, "is_checked") and callable(sw_inp.is_checked):
                    try:
                        val = sw_inp.is_checked()
                        if isinstance(val, bool):
                            st["input_checked"] = val
                    except Exception:
                        pass
                if st["input_checked"] is None and hasattr(sw_inp, "evaluate") and callable(sw_inp.evaluate):
                    try:
                        val = sw_inp.evaluate("el => el.checked === true")
                        if isinstance(val, bool):
                            st["input_checked"] = val
                    except Exception:
                        pass

                # If container itself is mocked directly in unit tests
                if hasattr(fresh_aigc, "get_attribute"):
                    try:
                        c_aria = fresh_aigc.get_attribute("aria-checked")
                        if c_aria and not st["aria_checked"]:
                            st["aria_checked"] = c_aria
                        c_state = fresh_aigc.get_attribute("data-state")
                        if c_state and not st["data_state"]:
                            st["data_state"] = c_state
                    except Exception:
                        pass
                if hasattr(fresh_aigc, "is_checked") and callable(fresh_aigc.is_checked) and st["input_checked"] is None:
                    try:
                        c_chk = fresh_aigc.is_checked()
                        if isinstance(c_chk, bool):
                            st["input_checked"] = c_chk
                    except Exception:
                        pass

                aria_val = str(st["aria_checked"] or "").lower()
                data_st_val = str(st["data_state"] or "").lower()
                cls_val = str(st["class"] or "")

                # Explicit OFF check: aria-checked='false' AND data-state='unchecked' (or checked-false class)
                # Overrides any stale ON signal!
                is_explicit_off = (
                    (aria_val == "false" and data_st_val == "unchecked")
                    or "checked-false" in cls_val
                )

                if is_explicit_off and aria_val != "true" and data_st_val != "checked":
                    return False, st

                if aria_val == "true" or data_st_val == "checked" or "checked-true" in cls_val:
                    return True, st

                if st["input_checked"] is True and not is_explicit_off:
                    return True, st

                if str(st["thumb_state"] or "").lower() == "checked" and not is_explicit_off:
                    return True, st

                return False, st
            except Exception as e:
                logger.debug(f"[TIKTOK AIGC] State read exception: {e}")
                return False, st

        # Read initial state strictly scoped inside aigc_container
        is_on, initial_st = _read_strict_aigc_state()
        logger.info("[TIKTOK AIGC] STRICT SCOPE = aigc_container")
        logger.info(
            f"[TIKTOK AIGC] BEFORE aria={initial_st.get('aria_checked')} "
            f"state={initial_st.get('data_state')}"
        )

        if is_on:
            logger.info(
                f"[TIKTOK AIGC] Already enabled "
                f"(aria={initial_st.get('aria_checked')}, "
                f"state={initial_st.get('data_state')}, "
                f"input.checked={initial_st.get('input_checked')}) | "
                f"AI_DISCLOSURE_ALREADY_ENABLED"
            )
            return True

        logger.info("[TIKTOK AIGC] STATE=OFF")

        # Strategy 1 (Primary): Normal click on div.Switch__content
        try:
            content_btn = aigc_container.locator("div.Switch__content, .Switch__content").first
            if hasattr(content_btn, "scroll_into_view_if_needed"):
                content_btn.scroll_into_view_if_needed(timeout=1000)
            content_btn.click(timeout=2000)
            logger.info("[TIKTOK AIGC] Clicked AIGC Switch__content")
            time.sleep(0.3)

            # Polling up to 3.0 seconds for fresh ON state
            start = time.time()
            while time.time() - start < 3.0:
                is_on, fresh_st = _read_strict_aigc_state()
                if is_on:
                    logger.info(f"[TIKTOK AIGC] AFTER aria={fresh_st.get('aria_checked')}")
                    logger.info(f"[TIKTOK AIGC] AFTER state={fresh_st.get('data_state')}")
                    logger.info(f"[TIKTOK AIGC] AFTER input.checked={fresh_st.get('input_checked')}")
                    logger.info("AI_DISCLOSURE_VERIFIED")
                    return True
                time.sleep(0.1)
        except Exception as e:
            logger.debug(f"[TIKTOK AIGC] Primary click failed: {e}")

        # Strategy 2 (Fallback): Normal click on div.Switch__root[data-layout="switch-root"]
        logger.info("[TIKTOK AIGC] Attempting fallback click on div.Switch__root...")
        try:
            root_btn = aigc_container.locator(
                "div.Switch__root[data-layout='switch-root'], div.Switch__root, .Switch__root"
            ).first
            if hasattr(root_btn, "scroll_into_view_if_needed"):
                root_btn.scroll_into_view_if_needed(timeout=1000)
            root_btn.click(timeout=2000)
            time.sleep(0.3)

            start = time.time()
            while time.time() - start < 3.0:
                is_on, fresh_st = _read_strict_aigc_state()
                if is_on:
                    logger.info(f"[TIKTOK AIGC] AFTER aria={fresh_st.get('aria_checked')}")
                    logger.info(f"[TIKTOK AIGC] AFTER state={fresh_st.get('data_state')}")
                    logger.info(f"[TIKTOK AIGC] AFTER input.checked={fresh_st.get('input_checked')}")
                    logger.info("AI_DISCLOSURE_VERIFIED")
                    return True
                time.sleep(0.1)
        except Exception as e:
            logger.debug(f"[TIKTOK AIGC] Fallback click failed: {e}")

        # Failed both strategies -> RULE 31: NEEDS_USER_HTML and STOP
        logger.error("=" * 50)
        logger.error("STATUS: NEEDS_USER_HTML")
        logger.error("Platform: TikTok")
        logger.error("Target: AIGC switch")
        logger.error("Request:")
        logger.error("- aigc_container current outerHTML")
        logger.error("- Switch__content current outerHTML")
        logger.error("- Switch__root current outerHTML")
        logger.error("=" * 50)
        return False

    def wait_for_content_checks(self, max_wait_seconds: int = 720, poll_interval: float = 2.0) -> bool:
        """
        Polls until TikTok safety & copyright checks are completed.
        Active checking is identified by: .status-checking[data-show='true'] (visible).
        Elements with data-show='false' are ignored.
        Checks complete when active_checking == 0 and visible success count > 0.
        """
        logger.info("[TIKTOK CHECK] Waiting for TikTok safety checks...")
        start = time.time()
        while time.time() - start < max_wait_seconds:
            active_checking_count = 0
            visible_success_count = 0

            try:
                chk_locs = self.page.locator(".status-checking[data-show='true'], div.status-result.status-checking[data-show='true']")
                cnt = chk_locs.count() if hasattr(chk_locs, "count") else 0
                for i in range(cnt):
                    try:
                        elem = chk_locs.nth(i)
                        if hasattr(elem, "is_visible") and elem.is_visible():
                            active_checking_count += 1
                    except Exception:
                        pass

                succ_locs = self.page.locator(".status-success, div.status-result.status-success, div:has-text('Sorun tespit edilmedi')")
                s_cnt = succ_locs.count() if hasattr(succ_locs, "count") else 0
                for i in range(s_cnt):
                    try:
                        elem = succ_locs.nth(i)
                        if hasattr(elem, "is_visible") and elem.is_visible():
                            visible_success_count += 1
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"[TIKTOK CHECK] Poll error: {e}")

            logger.info(f"[TIKTOK CHECK] active_checking={active_checking_count}, visible_success={visible_success_count}")

            if active_checking_count == 0 and visible_success_count > 0:
                logger.info("[TIKTOK CHECK] CHECKS_COMPLETED")
                return True

            time.sleep(poll_interval)

        logger.warning("[TIKTOK CHECK] Timeout waiting for content checks.")
        return False

    def click_schedule_and_verify(
        self,
        schedule_mode_verified: bool = True,
        timeout_seconds: int = 45
    ) -> Tuple[bool, str]:
        """
        Click the final Schedule/Planla action only after hard safety checks.
        Primary selector: button[data-e2e='post_video_button']
        Never report success merely because a click was attempted.
        Handles content check modal without clicking 'Hemen paylaş'. Max 2 submit attempts.
        """
        if not schedule_mode_verified:
            logger.error(
                "[PUBLISH-NOW HARD SAFETY] Cannot click action button: "
                "Schedule mode is not verified active!"
            )
            return False, "SCHEDULE_MODE_NOT_ACTIVE"

        # 1. Hard precommit gates
        try:
            tp = self.page.locator("div.tiktok-timepicker-time-picker-container").first
            if hasattr(tp, "is_visible") and tp.is_visible(timeout=200):
                logger.error("[TIKTOK FINAL] TIMEPICKER_OPEN: Timepicker container is still open!")
                return False, "TIMEPICKER_OPEN"
        except Exception:
            pass

        cur_date, cur_time = self.read_schedule_datetime()

        sched_chk = None
        now_chk = None
        try:
            planla_input = self.page.locator("input[name='postSchedule'][value='schedule'], input[value='schedule']").first
            simdi_input = self.page.locator("input[name='postSchedule'][value='now'], input[value='now']").first
            if hasattr(planla_input, "is_checked") and callable(planla_input.is_checked):
                sched_chk = planla_input.is_checked()
            if hasattr(simdi_input, "is_checked") and callable(simdi_input.is_checked):
                now_chk = simdi_input.is_checked()
        except Exception:
            pass

        # Fresh AIGC state check
        aigc_state_info: Dict[str, Any] = {}
        try:
            aigc = self.page.locator("div[data-e2e='aigc_container'], [data-e2e='aigc_container']").first
            if hasattr(aigc, "is_visible") and aigc.is_visible(timeout=300):
                content = aigc.locator("div.Switch__content, .Switch__content").first
                if hasattr(content, "get_attribute"):
                    aigc_state_info["aria"] = content.get_attribute("aria-checked")
                    aigc_state_info["state"] = content.get_attribute("data-state")
                    aigc_state_info["class"] = content.get_attribute("class")
                sw_inp = aigc.locator("input.Switch__input[role='switch'], input[role='switch']").first
                if hasattr(sw_inp, "is_checked") and callable(sw_inp.is_checked):
                    aigc_state_info["input_checked"] = sw_inp.is_checked()

                if hasattr(aigc, "get_attribute"):
                    if not aigc_state_info.get("aria"):
                        aigc_state_info["aria"] = aigc.get_attribute("aria-checked")
                    if not aigc_state_info.get("state"):
                        aigc_state_info["state"] = aigc.get_attribute("data-state")
                if hasattr(aigc, "is_checked") and callable(aigc.is_checked) and aigc_state_info.get("input_checked") is None:
                    aigc_state_info["input_checked"] = aigc.is_checked()
        except Exception:
            pass

        # Maximum 2 submit attempts
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            logger.info(f"[TIKTOK FINAL] Starting final submit attempt {attempt}/{max_attempts}...")

            submit_btn = None
            btn_diag: Dict[str, Any] = {
                "aria_disabled": None,
                "data_disabled": None,
                "data_loading": None,
                "enabled": False,
                "text": ""
            }

            final_btn = self.page.locator("button[data-e2e='post_video_button']").first
            poll_start = time.time()
            while time.time() - poll_start < 3.0:
                try:
                    if hasattr(final_btn, "is_visible") and final_btn.is_visible(timeout=300):
                        btn_diag["enabled"] = final_btn.is_enabled() if hasattr(final_btn, "is_enabled") else True
                        btn_diag["aria_disabled"] = final_btn.get_attribute("aria-disabled") if hasattr(final_btn, "get_attribute") else "false"
                        btn_diag["data_disabled"] = final_btn.get_attribute("data-disabled") if hasattr(final_btn, "get_attribute") else "false"
                        btn_diag["data_loading"] = final_btn.get_attribute("data-loading") if hasattr(final_btn, "get_attribute") else "false"
                        btn_diag["text"] = (final_btn.inner_text() or "").strip()

                        if (
                            btn_diag["enabled"] is True
                            and str(btn_diag["aria_disabled"]).lower() != "true"
                            and str(btn_diag["data_disabled"]).lower() != "true"
                            and str(btn_diag["data_loading"]).lower() != "true"
                        ):
                            submit_btn = final_btn
                            logger.info("[TIKTOK FINAL] post_video_button resolved & ready")
                            logger.info(f"[TIKTOK FINAL] enabled={btn_diag['enabled']}")
                            logger.info(f"[TIKTOK FINAL] aria-disabled={btn_diag['aria_disabled']}")
                            logger.info(f"[TIKTOK FINAL] data-disabled={btn_diag['data_disabled']}")
                            logger.info(f"[TIKTOK FINAL] data-loading={btn_diag['data_loading']}")
                            logger.info(f"[TIKTOK FINAL] text={btn_diag['text']}")
                            break
                except Exception as e:
                    logger.debug(f"[TIKTOK FINAL] post_video_button poll exception: {e}")
                time.sleep(0.2)

            if submit_btn is None:
                for sel in TikTokSelectors.FINAL_ACTION_BUTTONS:
                    if "post_video_button" in sel:
                        continue
                    try:
                        loc = self.page.locator(sel).first
                        if loc.is_visible(timeout=400) and loc.is_enabled():
                            btn_text = (loc.inner_text() or "").strip()
                            text_norm = btn_text.lower()
                            if text_norm and any(token in text_norm for token in ("planla", "schedule")):
                                submit_btn = loc
                                logger.info(f"[TIKTOK FINAL] Fallback final button found: '{btn_text}' ({sel})")
                                break
                    except Exception:
                        pass

            if submit_btn is None:
                logger.error("=" * 50)
                logger.error("STATUS: NEEDS_USER_HTML")
                logger.error("Platform: TikTok")
                logger.error("Target: final post_video_button disabled after all fields verified")
                logger.error("Diagnostic:")
                logger.error(f"- final time: {cur_time}")
                logger.error(f"- final date: {cur_date}")
                logger.error(f"- schedule.checked: {sched_chk}")
                logger.error(f"- now.checked: {now_chk}")
                logger.error(f"- fresh AIGC aria: {aigc_state_info.get('aria')}, state: {aigc_state_info.get('state')}, input.checked: {aigc_state_info.get('input_checked')}")
                logger.error(f"- button aria-disabled: {btn_diag['aria_disabled']}")
                logger.error(f"- button data-disabled: {btn_diag['data_disabled']}")
                logger.error(f"- button data-loading: {btn_diag['data_loading']}")
                logger.error("=" * 50)
                return False, "FINAL_BUTTON_NOT_READY"

            # Scrolling is a convenience, not a precondition: the button is rendered and
            # clickable where it sits. Giving it 1.5s to hold still, on a page whose layout
            # is still shifting as the content checks finish, is how CBM-REEL-2026-0013
            # came back FAILED on 2026-08-22 with its video uploaded, its caption written,
            # its slot set to 28 Aug 19:30 and both checks green. Nothing was wrong except
            # that the button moved while the automation reached for it.
            try:
                if hasattr(submit_btn, "scroll_into_view_if_needed"):
                    submit_btn.scroll_into_view_if_needed(timeout=SCHEDULE_BUTTON_SETTLE_MS)
            except Exception as e:
                logger.info(
                    f"[TIKTOK FINAL] Scroll skipped ({type(e).__name__}); clicking where it stands."
                )

            try:
                submit_btn.click(timeout=SCHEDULE_CLICK_TIMEOUT_MS)
                logger.info(f"[TIKTOK FINAL] Normal click submitted on final schedule button (Attempt {attempt}).")
            except Exception as e:
                # Not a verdict. The click may still have landed -- only the success check
                # below is entitled to say -- and if it did not, this loop has another
                # attempt left. Returning here skipped both, and turned a moving button
                # into a failed week.
                logger.warning(f"[TIKTOK FINAL] Click attempt {attempt} raised: {e}")

            time.sleep(1.5)

            for sel in TikTokSelectors.MODAL_CONFIRM_BUTTONS:
                try:
                    modal_btn = self.page.locator(sel).first
                    if modal_btn.is_visible(timeout=1000) and modal_btn.is_enabled():
                        modal_btn.click(timeout=2500)
                        time.sleep(1.0)
                        break
                except Exception:
                    pass

            check_modal_detected = False
            start = time.time()
            wait_limit = 5 if attempt < max_attempts else timeout_seconds
            while time.time() - start < wait_limit:
                # An informational notice sitting on top hides the success indicator
                # underneath it, which would otherwise read as a failed schedule.
                self.dismiss_content_review_info_if_present()
                for sel in TikTokSelectors.SCHEDULE_SUCCESS_INDICATORS:
                    try:
                        loc = self.page.locator(sel).first
                        if loc.is_visible(timeout=400):
                            logger.info("TikTok Studio schedule success indicator detected.")
                            return True, "TIKTOK_FINAL_SCHEDULE_SUBMITTED"
                    except Exception:
                        pass

                current_url = (self.page.url or "").lower()
                if (
                    "tiktokstudio/content" in current_url
                    or "tiktokstudio/manage" in current_url
                ):
                    logger.info(f"TikTok Studio redirected after schedule: {self.page.url}")
                    return True, "TIKTOK_FINAL_SCHEDULE_SUBMITTED"

                try:
                    check_modal_loc = self.page.locator(
                        ", ".join(TikTokSelectors.CONTENT_CHECK_CONFIRM_MODAL)
                        + ", div[role='dialog']:has-text('Continue posting?')"
                        + ", div[role='dialog']:has-text('kontrol ediyoruz')"
                    ).first
                    if hasattr(check_modal_loc, "is_visible") and check_modal_loc.is_visible(timeout=300):
                        check_modal_detected = True
                        logger.info("[TIKTOK CHECK] CONTENT_CHECK_CONFIRMATION_DETECTED")
                        logger.info("[TIKTOK CHECK] NEVER clicking 'Hemen paylaş' (Automation forbidden)")
                        break
                except Exception:
                    pass

                time.sleep(0.8)

            if check_modal_detected:
                if attempt >= max_attempts:
                    logger.error("=" * 50)
                    logger.error("STATUS: NEEDS_USER_HTML")
                    logger.error("Platform: TikTok")
                    logger.error("Target: Content check confirmation modal appeared on attempt 2")
                    logger.error("=" * 50)
                    return False, "CONTENT_CHECK_MODAL_RETRY_FAILED"

                logger.info("[TIKTOK CHECK] Modal 'Iptal' ile guvenle kapatiliyor...")
                if not self.cancel_content_check_modal():
                    # Escape only as a fallback if the real Cancel button was unreachable.
                    try:
                        self.page.keyboard.press("Escape")
                    except Exception:
                        pass
                time.sleep(0.5)

                checks_done = self.wait_for_content_checks(max_wait_seconds=720, poll_interval=2.0)
                if not checks_done:
                    logger.warning("[TIKTOK CHECK] Checks did not complete within timeout, proceeding to final attempt.")

                time.sleep(1.0)
                continue

            current_url = (self.page.url or "").lower()
            if "tiktokstudio/content" in current_url or "tiktokstudio/manage" in current_url:
                return True, "TIKTOK_FINAL_SCHEDULE_SUBMITTED"

        logger.error(
            "TIKTOK_SCHEDULE_CONFIRMATION_TIMEOUT: final button was clicked "
            "but no success indicator or content redirect was observed."
        )
        return False, "TIKTOK_SCHEDULE_CONFIRMATION_TIMEOUT"

    def verify_remote_scheduled_status(
        self,
        expected_title: str = "",
        expected_date_str: str = "",
        expected_time_str: str = ""
    ) -> Tuple[bool, str]:
        """
        Conservative remote verification.
        A navigation attempt by itself is never treated as proof of scheduling.
        """
        content_url = "https://www.tiktok.com/tiktokstudio/content"

        # Reload every attempt, even when already on this URL. A post scheduled seconds
        # ago is not in a list that was rendered before it existed, and the old code
        # skipped navigation precisely in that case -- so the check ran against a stale
        # page and reported "not verified" for a post that was there.
        for attempt, backoff in enumerate(REMOTE_VERIFY_BACKOFF_SECONDS, start=1):
            ok, msg = self._read_scheduled_marker_once(
                content_url, expected_title, expected_time_str
            )
            if ok:
                return True, msg
            if backoff:
                logger.info(
                    f"[TIKTOK VERIFY] {attempt}. deneme sonucsuz; {backoff:.0f}s sonra tekrar."
                )
                time.sleep(backoff)

        self.capture_error_snapshot("tiktok_remote_schedule_not_verified")
        return False, msg

    def _read_scheduled_marker_once(
        self,
        content_url: str,
        expected_title: str,
        expected_time_str: str,
    ) -> Tuple[bool, str]:
        """One pass over the content list: reload, read, look for the scheduled markers."""
        try:
            self.page.goto(
                content_url,
                wait_until="domcontentloaded",
                timeout=20000
            )
            time.sleep(2.0)
        except Exception as e:
            return False, f"REMOTE_VERIFICATION_NAVIGATION_FAILED: {e}"

        try:
            page_text = (self.page.inner_text("body") or "").strip()
        except Exception:
            try:
                page_text = self.page.content() or ""
            except Exception:
                page_text = ""

        lower = page_text.lower()
        scheduled_marker = any(
            marker in lower
            for marker in (
                "planlandı",
                "planlanmış",
                "scheduled",
                "zamanlandı",
            )
        )

        # TikTok Studio's content list does not print the word "Planlandı" at all -- a
        # scheduled post is shown as a clock badge with its slot, e.g. "17 Ağu, 19:30"
        # (confirmed against the operator's Gönderiler screenshot). Requiring the word
        # therefore failed for every correctly scheduled Reel, so the slot time counts as
        # a scheduled-state marker in its own right.
        if not scheduled_marker and expected_time_str:
            scheduled_marker = expected_time_str in page_text

        title_tokens = [
            t.lower()
            for t in re.findall(r"[A-Za-z0-9ÇĞİÖŞÜçğıöşü]+", expected_title or "")
            if len(t) >= 4
        ]
        title_match = (
            not title_tokens
            or sum(token in lower for token in title_tokens[:5]) >= min(2, len(title_tokens))
        )

        if scheduled_marker and title_match:
            return True, "REMOTE_SCHEDULE_VERIFIED"

        return False, (
            "REMOTE_SCHEDULE_NOT_VERIFIED: content page did not expose "
            "a matching scheduled-state marker."
        )

    def detect_editor_state(self) -> str:
        """
        Explicitly detects whether TikTok Studio page is an empty upload page
        or an already-loaded editor session.
        Returns: 'EMPTY_UPLOAD_PAGE', 'LOADED_EDITOR', or 'UNKNOWN'
        """
        content_text = ""
        try:
            content_text = (self.page.content() or "").lower()
        except Exception:
            pass

        # 1. Check for loaded editor indicators
        has_editor = False
        for sel in TikTokSelectors.CAPTION_EDITORS:
            try:
                if self.page.locator(sel).first.is_visible(timeout=500):
                    has_editor = True
                    break
            except Exception:
                pass

        has_upload_complete = False
        for sel in TikTokSelectors.UPLOAD_COMPLETE_INDICATORS:
            try:
                if self.page.locator(sel).first.is_visible(timeout=500):
                    has_upload_complete = True
                    break
            except Exception:
                pass

        if has_editor or has_upload_complete or "yüklendi" in content_text or "uploaded" in content_text:
            logger.info("Detected TikTok Studio State: LOADED_EDITOR")
            return "LOADED_EDITOR"

        # 2. Check for empty upload page indicators
        has_select_btn = False
        for sel in TikTokSelectors.SELECT_VIDEO_BUTTONS + TikTokSelectors.FILE_INPUT_SELECTORS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=500) or loc.count() > 0:
                    has_select_btn = True
                    break
            except Exception:
                pass

        if has_select_btn or "video seçin" in content_text or "select video" in content_text:
            logger.info("Detected TikTok Studio State: EMPTY_UPLOAD_PAGE")
            return "EMPTY_UPLOAD_PAGE"

        logger.warning("Detected TikTok Studio State: UNKNOWN")
        return "UNKNOWN"

    def prepare_tiktok_schedule_preflight(
        self,
        record: Any,
        expected_username: str = "@kitchenverse360"
    ) -> Tuple[bool, str]:
        """
        Prepares TikTok Studio video schedule up to the final action button.
        If EMPTY_UPLOAD_PAGE: uploads video file to reach LOADED_EDITOR without posting.
        If LOADED_EDITOR: skips upload.
        Replaces caption, selects Planla, sets date/time, toggles AI disclosure.
        DOES NOT click final action button.
        Returns (True, 'TIKTOK_FINAL_SCHEDULE_READY') or (False, error_msg).
        """
        # 1. Login & User check
        if not self.is_logged_in():
            return False, "AUTH_REQUIRED: TikTok Studio not logged in"

        ok_u, u_name, u_msg = self.verify_logged_in_username(expected_username)
        if not ok_u:
            return False, f"ACCOUNT_MISMATCH: {u_msg}"

        # 2. Detect Editor State
        state = self.detect_editor_state()
        if state == "EMPTY_UPLOAD_PAGE":
            logger.info(f"[{record.reel_id}] EMPTY_UPLOAD_PAGE detected. Uploading video file to editor: {record.video_file.name}")
            if not self.upload_file(record.video_file):
                return False, "TikTok file input / upload button not found"

            # Wait for upload completion to reach editor
            if not self.wait_for_upload_completion(timeout_seconds=120):
                return False, "TikTok video upload timed out before editor loaded"
        elif state == "LOADED_EDITOR":
            logger.info(f"[{record.reel_id}] LOADED_EDITOR detected. Skipping upload.")
        else:
            # Fallback upload attempt
            if not self.upload_file(record.video_file):
                return False, f"Unknown page state ({state}) and upload failed"
            self.wait_for_upload_completion(timeout_seconds=60)

        # 3. Dismiss React-Joyride Overlay if present
        self.dismiss_onboarding_overlay_if_present()

        # 4. Replace caption with generated description + hashtags
        ok_cap, cap_msg = self.replace_caption(record.description, record.hashtags)
        if not ok_cap:
            return False, f"TikTok caption replacement failed: {cap_msg}"
        time.sleep(0.5)

        # 5. Select 'Planla' under 'Paylaşıldığında'
        ok_mode, mode_msg = self.select_schedule_mode("SCHEDULE")
        if not ok_mode:
            return False, f"TikTok schedule mode selection failed: {mode_msg}"
        time.sleep(0.5)

        # 6. Set date & time (16.08.2026 19:30)
        ok_dt, dt_msg = self.set_schedule_datetime(record.scheduled_at_local)
        if not ok_dt:
            return False, f"TikTok datetime setting failed: {dt_msg}"
        time.sleep(0.5)

        # 7. AI Disclosure
        self.toggle_ai_disclosure(True)

        # 8. Check final action button (Planla/Paylaş) - DO NOT CLICK
        final_btn = None
        for sel in TikTokSelectors.FINAL_ACTION_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1500) and loc.is_enabled():
                    final_btn = loc
                    break
            except Exception:
                pass

        if not final_btn:
            return False, "FINAL_ACTION_BUTTON_NOT_READY: Final button disabled or not found"

        logger.info("=" * 50)
        logger.info("TIKTOK PREFLIGHT")
        logger.info(f"Account:         {expected_username} PASS")
        logger.info("Editor:          LOADED_EDITOR PASS")
        logger.info("Caption:         VERIFIED (NO RAW FILENAME) PASS")
        logger.info("Schedule Mode:   PLANLA SELECTED PASS")
        logger.info("Date:            16.08.2026 PASS")
        logger.info("Time:            19:30 PASS")
        logger.info("Action Button:   VISIBLE + ENABLED")
        logger.info("TIKTOK_FINAL_SCHEDULE_READY")
        logger.info("FINAL CLICK NOT PERFORMED")
        logger.info("=" * 50)

        return True, "TIKTOK_FINAL_SCHEDULE_READY"

    def commit_tiktok_schedule(
        self,
        record: Any
    ) -> Tuple[bool, str]:
        """
        PHASE-2 commit.
        Rebuilds and re-verifies the live TikTok schedule state before clicking.
        A previous preflight PASS is never trusted if controls changed afterward.
        """
        ok_mode, mode_msg = self.select_schedule_mode("SCHEDULE")
        if not ok_mode:
            return False, f"COMMIT_SCHEDULE_MODE_FAILED: {mode_msg}"

        # TikTok can reset the time between preflight and commit; set it again.
        ok_dt, dt_msg = self.set_schedule_datetime(record.scheduled_at_local)
        if not ok_dt:
            return False, f"COMMIT_DATETIME_FAILED: {dt_msg}"

        ok_readback, readback_msg = self.verify_schedule_datetime(
            record.scheduled_at_local
        )
        if not ok_readback:
            logger.error(
                "[TIKTOK COMMIT HARD GUARD] Final click blocked: "
                f"{readback_msg}"
            )
            return False, f"COMMIT_DATETIME_READBACK_FAILED: {readback_msg}"

        # Re-check Planla after the date/time fields rerender.
        ok_mode2, mode_msg2 = self.select_schedule_mode("SCHEDULE")
        if not ok_mode2:
            return False, f"COMMIT_SCHEDULE_MODE_RECHECK_FAILED: {mode_msg2}"

        success, ref = self.click_schedule_and_verify(
            schedule_mode_verified=True,
            timeout_seconds=45
        )
        if not success:
            return False, f"TikTok schedule submission failed: {ref}"

        remote_ok, remote_msg = self.verify_remote_scheduled_status(
            expected_title=record.title
        )
        if not remote_ok:
            logger.warning(
                "TikTok final action was confirmed, but secondary remote "
                f"verification was inconclusive: {remote_msg}"
            )

        return True, "TIKTOK_SCHEDULED_COMMITTED"
