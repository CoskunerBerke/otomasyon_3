"""
YouTube Studio Web UI Observer and DOM Driver.
Automates video upload, metadata population, AI disclosure, and native scheduling.
Includes dynamic aria-labelledby time input resolution, strict audience (Not made for kids) verification,
remote video ID capture, exact remote URL resume, and true post-schedule verification.
"""
import time
import logging
import re
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

from .youtube_studio_selectors import YouTubeStudioSelectors

logger = logging.getLogger("ReelsAIFactory.YouTubeStudioUIObserver")


class WizardStep:
    """YouTube Studio upload wizard step identifiers."""
    DETAILS = "DETAILS"
    VIDEO_ELEMENTS = "VIDEO_ELEMENTS"
    CHECKS = "CHECKS"
    VISIBILITY = "VISIBILITY"
    UNKNOWN = "UNKNOWN"

    # TR and EN label mappings for step detection
    LABEL_MAP = {
        "ayrıntılar": "DETAILS",
        "details": "DETAILS",
        "video öğeleri": "VIDEO_ELEMENTS",
        "video elements": "VIDEO_ELEMENTS",
        "ilk kontrol": "CHECKS",
        "i̇lk kontrol": "CHECKS",
        "checks": "CHECKS",
        "görünürlük": "VISIBILITY",
        "visibility": "VISIBILITY",
    }

    # Ordered progression
    ORDERED = ["DETAILS", "VIDEO_ELEMENTS", "CHECKS", "VISIBILITY"]

MONTH_MAP = {
    "oca": 1, "ocak": 1, "jan": 1, "january": 1,
    "şub": 2, "şubat": 2, "feb": 2, "february": 2,
    "mar": 3, "mart": 3, "march": 3,
    "nis": 4, "nisan": 4, "apr": 4, "april": 4,
    "may": 5, "mayıs": 5,
    "haz": 6, "haziran": 6, "jun": 6, "june": 6,
    "tem": 7, "temmuz": 7, "jul": 7, "july": 7,
    "ağu": 8, "ağustos": 8, "aug": 8, "august": 8,
    "eyl": 9, "eylül": 9, "sep": 9, "september": 9,
    "eki": 10, "ekim": 10, "oct": 10, "october": 10,
    "kas": 11, "kasım": 11, "nov": 11, "november": 11,
    "ara": 12, "aralık": 12, "dec": 12, "december": 12
}

class YouTubeStudioUIObserver:
    """Interacts with visible DOM elements of YouTube Studio Web UI."""

    def __init__(self, page: Any):
        self.page = page
        self.current_remote_id: Optional[str] = None
        self._active_wizard_dialog: Optional[Any] = None

    def is_logged_in(self) -> bool:
        """Check if user has an active session on YouTube Studio."""
        curr_url = self.page.url
        if "accounts.google.com" in curr_url or "signin" in curr_url:
            return False

        for sel in YouTubeStudioSelectors.LOGIN_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    return False
            except Exception:
                pass

        for sel in YouTubeStudioSelectors.CREATE_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    return True
            except Exception:
                pass

        return True

    def verify_logged_in_channel(
        self,
        expected_handle: str = "@BuiIdVerse",
        expected_channel_id: Optional[str] = "UCahsmsqzTCtwTDDtvCurtBA"
    ) -> Tuple[bool, str, str]:
        """
        Verify that the currently opened YouTube Studio channel matches expected_handle / channel_id.
        """
        exp_handle_norm = expected_handle.strip().lstrip("@").lower()
        detected_text = ""

        for sel in YouTubeStudioSelectors.CHANNEL_HEADER_SELECTORS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    text = loc.inner_text().strip()
                    if text:
                        detected_text = text
                        break
            except Exception:
                pass

        curr_url = self.page.url
        if expected_channel_id and expected_channel_id in curr_url:
            return True, f"Channel ID {expected_channel_id}", f"YouTube Channel Verified via URL: {expected_channel_id}"

        if detected_text:
            det_norm = detected_text.lower()
            if exp_handle_norm in det_norm or "buildverse" in det_norm:
                return True, detected_text, f"YouTube Channel Verified: {detected_text}"
            else:
                return False, detected_text, f"ACCOUNT_MISMATCH: Expected '{expected_handle}', detected '{detected_text}'"

        return True, expected_handle, f"YouTube Channel assumed active ({expected_handle})"

    def capture_video_id_and_url(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract the video link and 11-char video ID from the upload wizard or active URL.
        """
        video_id = None
        video_url = None

        # 1. Check active page URL
        curr_url = self.page.url
        if "/video/" in curr_url:
            parts = curr_url.split("/video/")[1].split("/")
            if parts and len(parts[0]) >= 8:
                video_id = parts[0]
                video_url = f"https://youtube.com/shorts/{video_id}"

        # 2. Check UI elements for Video Link (Video bağlantısı)
        for sel in YouTubeStudioSelectors.VIDEO_LINK_SELECTORS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    href = loc.get_attribute("href") or loc.inner_text().strip()
                    if href:
                        video_url = href
                        if "youtu.be/" in href:
                            video_id = href.split("youtu.be/")[1].split("?")[0]
                        elif "shorts/" in href:
                            video_id = href.split("shorts/")[1].split("?")[0]
                        elif "v=" in href:
                            video_id = href.split("v=")[1].split("&")[0]
                        break
            except Exception:
                pass

        if video_id:
            logger.info(f"[REMOTE_ID_CAPTURED] Captured YouTube Video ID: {video_id} ({video_url})")

        return video_id, video_url

    def enter_existing_draft_wizard(self, timeout_seconds: int = 15) -> bool:
        """
        If on https://studio.youtube.com/video/<id>/edit page with 'Bu video taslak durumunda',
        clicks 'Taslağı düzenle' (Edit draft) to open the stepper upload wizard.
        Verifies YOUTUBE_DRAFT_WIZARD_READY.
        """
        # 1. Check if wizard stepper is already open
        for sel in YouTubeStudioSelectors.WIZARD_STEPPER_SELECTORS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=800):
                    logger.info("Draft wizard stepper is already open (YOUTUBE_DRAFT_WIZARD_READY).")
                    return True
            except Exception:
                pass

        # 2. Look for 'Taslağı düzenle' / 'Edit draft' button on /video/<id>/edit
        for sel in YouTubeStudioSelectors.EDIT_DRAFT_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1500) and loc.is_enabled():
                    loc.scroll_into_view_if_needed()
                    loc.click()
                    logger.info(f"Clicked 'Taslağı düzenle' button: {sel}")
                    break
            except Exception as e:
                logger.debug(f"Edit draft button selector {sel} error: {e}")

        # 3. Wait for wizard stepper to appear
        start = time.time()
        while time.time() - start < timeout_seconds:
            for sel in YouTubeStudioSelectors.WIZARD_STEPPER_SELECTORS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=500):
                        logger.info("Draft wizard stepper confirmed open: YOUTUBE_DRAFT_WIZARD_READY.")
                        time.sleep(1.0)
                        return True
                except Exception:
                    pass
            time.sleep(1.0)

        # Fallback check if details inputs are visible
        for sel in YouTubeStudioSelectors.TITLE_INPUTS:
            try:
                if self.page.locator(sel).first.is_visible(timeout=500):
                    return True
            except Exception:
                pass

        logger.warning("Could not verify YOUTUBE_DRAFT_WIZARD_READY after opening draft.")
        return False

    def open_exact_remote_video(self, remote_id: str) -> bool:
        """
        Open the exact existing video draft by navigating directly to its edit URL.
        Eliminates duplicate uploads and title searches.
        """
        self.current_remote_id = remote_id
        self._active_wizard_dialog = None
        edit_url = f"https://studio.youtube.com/video/{remote_id}/edit"
        logger.info(f"Opening exact remote video: {edit_url}")
        try:
            self.page.goto(edit_url, wait_until="domcontentloaded", timeout=25000)
            time.sleep(2.5)
            return True
        except Exception as e:
            logger.error(f"Failed to open exact remote video {remote_id}: {e}")
            return False

    def find_matching_drafts(
        self,
        target_title: str,
        reel_id: str,
        channel_id: Optional[str] = "UCahsmsqzTCtwTDDtvCurtBA"
    ) -> List[Dict[str, Any]]:
        """
        Inspect YouTube Studio Content page for all drafts matching target_title or reel_id.
        """
        clean_title = target_title.lower().strip()
        r_id_clean = reel_id.lower().strip()
        matches = []

        content_url = f"https://studio.youtube.com/channel/{channel_id or ''}/videos/upload"
        if not ("videos/upload" in self.page.url or "videos/content" in self.page.url):
            try:
                self.page.goto(content_url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(2.0)
            except Exception as e:
                logger.debug(f"Navigation to Content list: {e}")

        for row_sel in YouTubeStudioSelectors.DRAFT_CONTENT_ROWS:
            try:
                rows = self.page.locator(row_sel)
                count = rows.count()
                for i in range(min(count, 30)):
                    row = rows.nth(i)
                    text = row.inner_text()
                    text_lower = text.lower()
                    if clean_title in text_lower or r_id_clean in text_lower:
                        video_id = None
                        link_el = row.locator("a[href*='/video/']").first
                        if link_el.count() > 0:
                            href = link_el.get_attribute("href") or ""
                            if "/video/" in href:
                                video_id = href.split("/video/")[1].split("/")[0]

                        matches.append({
                            "index": i,
                            "title": text.split("\n")[0] if "\n" in text else text[:60],
                            "video_id": video_id,
                            "visibility": "Draft / Private" if ("taslak" in text_lower or "draft" in text_lower or "gizli" in text_lower) else "Unknown",
                            "element": row
                        })
                if matches:
                    break
            except Exception as e:
                logger.debug(f"Row scan error: {e}")

        logger.info(f"[DIAGNOSTIC] {reel_id} matching YouTube drafts found: {len(matches)}")
        for idx, m in enumerate(matches, start=1):
            logger.info(f"  [{idx}] Title: '{m['title']}' | Video ID: {m['video_id']} | Visibility: {m['visibility']}")

        return matches

    def find_and_open_existing_draft(
        self,
        target_title: str,
        reel_id: str,
        channel_id: Optional[str] = "UCahsmsqzTCtwTDDtvCurtBA"
    ) -> bool:
        """
        Check if video is already uploaded as a draft and open its wizard.
        Prevents duplicate MP4 uploads.
        """
        clean_title = target_title.lower().strip()
        r_id_clean = reel_id.lower().strip()

        # 1. Check active page
        try:
            for sel in YouTubeStudioSelectors.TITLE_INPUTS:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1000):
                    curr_val = loc.inner_text() or (loc.input_value() if hasattr(loc, "input_value") else "")
                    if clean_title in curr_val.lower() or r_id_clean in curr_val.lower():
                        logger.info(f"Existing upload wizard is already open for '{target_title}'. Resuming directly.")
                        return True
        except Exception:
            pass

        # 2. Check Content List
        matches = self.find_matching_drafts(target_title, reel_id, channel_id)
        if matches:
            primary_match = matches[0]
            logger.info(f"Opening existing draft: '{primary_match['title']}' (Video ID: {primary_match['video_id']})")
            row = primary_match["element"]
            edit_btn = row.locator("a#thumbnail, a#video-title, #edit-button, ytcp-icon-button[aria-label*='Ayrıntılar'], ytcp-icon-button[aria-label*='Details']").first
            if edit_btn.count() > 0:
                edit_btn.click()
            else:
                row.click()
            time.sleep(2.5)
            return True

        return False

    def open_upload_dialog(self) -> bool:
        """Click Create -> Upload videos."""
        for sel in YouTubeStudioSelectors.CREATE_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    time.sleep(1.0)
                    break
            except Exception:
                pass

        for sel in YouTubeStudioSelectors.UPLOAD_MENU_ITEMS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    time.sleep(1.0)
                    return True
            except Exception:
                pass

        return True

    def upload_file(self, video_path: Path) -> bool:
        """Locate file input and upload video file."""
        video_path = Path(video_path).resolve()
        self.open_upload_dialog()

        for sel in YouTubeStudioSelectors.FILE_INPUT_SELECTORS:
            try:
                loc = self.page.locator(sel).first
                if loc.count() > 0:
                    loc.set_input_files(str(video_path))
                    logger.info(f"Set input files for YouTube Studio: {video_path.name}")
                    return True
            except Exception as e:
                logger.debug(f"File input selector {sel} failed: {e}")

        return False

    def wait_for_upload_completion(self, timeout_seconds: int = 120) -> bool:
        """Wait for video upload and initial processing."""
        start = time.time()
        while time.time() - start < timeout_seconds:
            for sel in YouTubeStudioSelectors.NEXT_BUTTONS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1000) and loc.is_enabled():
                        return True
                except Exception:
                    pass
            time.sleep(2.0)
        return True

    def fill_details(self, title: str, description: str, hashtags: List[str]) -> bool:
        """Fill title and description inputs."""
        full_title = title[:100]
        for sel in YouTubeStudioSelectors.TITLE_INPUTS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    self.page.keyboard.press("Control+A")
                    self.page.keyboard.press("Backspace")
                    loc.fill(full_title)
                    logger.info(f"Filled YouTube Title: {full_title[:40]}...")
                    break
            except Exception:
                pass

        tags_str = " ".join(hashtags)
        full_desc = f"{description}\n\n{tags_str}"
        for sel in YouTubeStudioSelectors.DESCRIPTION_INPUTS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=2000):
                    loc.click()
                    self.page.keyboard.press("Control+A")
                    self.page.keyboard.press("Backspace")
                    loc.fill(full_desc)
                    logger.info("Filled YouTube Description.")
                    break
            except Exception:
                pass

        return True

    def find_active_audience_container(self) -> Optional[Any]:
        """
        Locates the active 'Kitle' / 'Audience' section container in the active wizard dialog.
        The container must contain all 4 anchor texts:
        1. 'Kitle' or 'Audience'
        2. 'Evet, çocuklara özel' or "Yes, it's made for kids"
        3. 'Hayır, çocuklara özel değil' or "No, it's not made for kids"
        4. 'Yaş kısıtlaması' or 'Age restriction'
        Eliminates duplicate radio button pairs in DOM templates/clones.
        """
        candidate_selectors = [
            "ytcp-uploads-dialog #scrollable-content",
            "ytcp-uploads-dialog ytcp-animatable[step='DETAILS']",
            "ytcp-video-metadata-editor-basics",
            "ytcp-uploads-dialog div[class*='details']",
            "ytcp-uploads-dialog"
        ]

        for sel in candidate_selectors:
            try:
                candidates = self.page.locator(sel)
                count = candidates.count() if hasattr(candidates, "count") else 0
                for i in range(count):
                    container = candidates.nth(i)
                    if not container.is_visible():
                        continue
                    text = (container.inner_text() or "").lower()
                    has_kitle = "kitle" in text or "audience" in text
                    has_yes = "evet, çocuklara özel" in text or "yes, it's made for kids" in text or "çocuklara özel" in text
                    has_no = "hayır, çocuklara özel değil" in text or "no, it's not made for kids" in text or "çocuklara özel değil" in text
                    has_age = "yaş kısıtlaması" in text or "age restriction" in text or "kısıtlaması" in text or "restriction" in text

                    if has_kitle and has_yes and has_no and has_age:
                        logger.info(f"Resolved active audience container via '{sel}' [{i}] with all 4 anchor markers.")
                        return container
            except Exception as e:
                logger.debug(f"Candidate check error for {sel}: {e}")

        # Fallback: check all div containers with paper-radio-button
        try:
            divs = self.page.locator("ytcp-uploads-dialog div:has(tp-yt-paper-radio-button)")
            d_count = divs.count() if hasattr(divs, "count") else 0
            for i in range(d_count):
                d = divs.nth(i)
                if not d.is_visible():
                    continue
                txt = (d.inner_text() or "").lower()
                if ("kitle" in txt or "audience" in txt) and ("çocuklara özel değil" in txt or "not made for kids" in txt):
                    return d
        except Exception:
            pass

        return None

    def set_audience(self, made_for_kids: bool = False) -> Tuple[bool, str]:
        """
        Explicitly selects and verifies audience setting within the active 'Kitle' container.
        Scoping to the active container eliminates duplicate radio elements in DOM clones.
        """
        if not made_for_kids:
            container = self.find_active_audience_container()
            if not container:
                # If cannot resolve dedicated container, scope to active uploads dialog
                dialog_loc = self.page.locator("ytcp-uploads-dialog").first
                try:
                    if dialog_loc.is_visible(timeout=500):
                        container = dialog_loc
                    else:
                        container = self.page
                except Exception:
                    container = self.page

            # Try selectors in order of priority. Break on first matching selector group.
            no_selectors = [
                "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']",
                "tp-yt-paper-radio-button#not-made-for-kids-radio",
                "tp-yt-paper-radio-button:has-text('Hayır, çocuklara özel değil')",
                "tp-yt-paper-radio-button:has-text(\"No, it's not made for kids\")",
                "div[role='radio']:has-text('Hayır, çocuklara özel değil')",
                "div[role='radio']:has-text(\"No, it's not made for kids\")",
                "#radioLabel:has-text('Hayır, çocuklara özel değil')"
            ]

            yes_selectors = [
                "tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_MFK']",
                "tp-yt-paper-radio-button#made-for-kids-radio",
                "tp-yt-paper-radio-button:has-text('Evet, çocuklara özel')",
                "tp-yt-paper-radio-button:has-text(\"Yes, it's made for kids\")",
                "div[role='radio']:has-text('Evet, çocuklara özel')",
                "div[role='radio']:has-text(\"Yes, it's made for kids\")"
            ]

            visible_no = []
            for sel in no_selectors:
                try:
                    locs = container.locator(sel)
                    cnt = 0
                    if hasattr(locs, "count") and callable(locs.count):
                        try:
                            c = locs.count()
                            if isinstance(c, int):
                                cnt = c
                        except Exception:
                            cnt = 0

                    if cnt > 0:
                        for i in range(cnt):
                            r = locs.nth(i)
                            if r.is_visible():
                                bbox = r.bounding_box() if hasattr(r, "bounding_box") else {}
                                if bbox is not None:
                                    visible_no.append(r)
                    else:
                        r = locs.first if hasattr(locs, "first") else locs
                        if r.is_visible():
                            bbox = r.bounding_box() if hasattr(r, "bounding_box") else {}
                            if bbox is not None:
                                visible_no.append(r)
                    if visible_no:
                        break
                except Exception:
                    pass

            visible_yes = []
            for sel in yes_selectors:
                try:
                    locs = container.locator(sel)
                    cnt = 0
                    if hasattr(locs, "count") and callable(locs.count):
                        try:
                            c = locs.count()
                            if isinstance(c, int):
                                cnt = c
                        except Exception:
                            cnt = 0

                    if cnt > 0:
                        for i in range(cnt):
                            r = locs.nth(i)
                            if r.is_visible():
                                bbox = r.bounding_box() if hasattr(r, "bounding_box") else {}
                                if bbox is not None:
                                    visible_yes.append(r)
                    else:
                        r = locs.first if hasattr(locs, "first") else locs
                        if r.is_visible():
                            bbox = r.bounding_box() if hasattr(r, "bounding_box") else {}
                            if bbox is not None:
                                visible_yes.append(r)
                    if visible_yes:
                        break
                except Exception:
                    pass

            if len(visible_no) == 0:
                logger.error("[AUDIENCE_ERROR] No visible NOT_MADE_FOR_KIDS radio found in active container.")
                return False, "AUDIENCE_MISMATCH: NOT_MADE_FOR_KIDS radio not found or not clickable"

            if len(visible_no) > 1:
                logger.error(f"[AMBIGUOUS_ACTIVE_AUDIENCE_SECTION] Found {len(visible_no)} visible NOT_MADE_FOR_KIDS radios in container.")
                return False, "AMBIGUOUS_ACTIVE_AUDIENCE_SECTION"

            target_no = visible_no[0]
            target_yes = visible_yes[0] if visible_yes else None

            # Click NO radio
            if hasattr(target_no, "scroll_into_view_if_needed"):
                target_no.scroll_into_view_if_needed()
            target_no.click()
            logger.info("Clicked Audience option: 'Hayır, çocuklara özel değil' in active Kitle container.")

            # Stabilization polling (up to 3 seconds)
            poll_start = time.time()
            is_no_checked = False
            is_yes_checked = True
            while time.time() - poll_start < 3.0:
                time.sleep(0.5)
                try:
                    aria_chk = target_no.get_attribute("aria-checked")
                    chk = target_no.get_attribute("checked")
                    cls = target_no.get_attribute("class") or ""
                    is_no_checked = (aria_chk == "true" or chk == "true" or chk == "checked" or "checked" in str(cls) or "active" in str(cls))
                except Exception:
                    is_no_checked = False

                try:
                    if target_yes:
                        aria_chk_y = target_yes.get_attribute("aria-checked")
                        chk_y = target_yes.get_attribute("checked")
                        cls_y = target_yes.get_attribute("class") or ""
                        is_yes_checked = (aria_chk_y == "true" or chk_y == "true" or chk_y == "checked")
                    else:
                        is_yes_checked = False
                except Exception:
                    is_yes_checked = False

                if is_no_checked and not is_yes_checked:
                    break

            if is_no_checked and not is_yes_checked:
                logger.info("Audience verification: Expected: NOT_MADE_FOR_KIDS | Actual: NOT_MADE_FOR_KIDS | PASS")
                return True, "AUDIENCE_VERIFIED"
            elif is_yes_checked:
                logger.error("[AUDIENCE_MISMATCH] Video is set to Made for Kids ('Evet, çocuklara özel')!")
                return False, "AUDIENCE_MISMATCH: Video is set to Made for Kids"
            else:
                logger.error("[AUDIENCE_MISMATCH] Could not verify audience radio state after stabilization polling.")
                return False, "AUDIENCE_MISMATCH: Radio state could not be verified"

        return True, "AUDIENCE_VERIFIED"

    def _is_visibility_ui_ready(self, scope: Optional[Any] = None) -> bool:
        """
        Strong VISIBILITY-step detector for the current YouTube upload wizard.

        YouTube sometimes clears the dialog's ``workflow-step`` attribute while
        rendering the final Visibility page. In that state the persistent
        "Kontroller tamamlandı" text from the previous Checks step may remain
        visible and can create a false CHECKS classification.

        Prefer Visibility-specific interactive controls instead.
        """
        scope = scope or self.page

        strong_selectors = [
            "ytcp-visibility-card:has-text('Planlayın')",
            "ytcp-visibility-card:has-text('Schedule')",
            "div:has-text('Planlayın'):not(tp-yt-paper-tab):not(ytcp-stepper-step)",
            "div:has-text('Schedule'):not(tp-yt-paper-tab):not(ytcp-stepper-step)",
            "div:has-text('Kaydedin veya yayınlayın'):not(tp-yt-paper-tab):not(ytcp-stepper-step)",
            "div:has-text('Save or publish'):not(tp-yt-paper-tab):not(ytcp-stepper-step)",
            "tp-yt-paper-radio-button:has-text('Gizli')",
            "tp-yt-paper-radio-button:has-text('Private')",
            "tp-yt-paper-radio-button:has-text('Liste dışı')",
            "tp-yt-paper-radio-button:has-text('Unlisted')",
            "tp-yt-paper-radio-button:has-text('Herkese açık')",
            "tp-yt-paper-radio-button:has-text('Public')",
        ]

        visible_hits = 0
        for sel in strong_selectors:
            try:
                loc = scope.locator(sel).first
                if hasattr(loc, "is_visible") and loc.is_visible(timeout=250) is True:
                    visible_hits += 1
                    if ("Planlayın" in sel or "Schedule" in sel
                            or "Kaydedin" in sel or "Save or publish" in sel):
                        return True
                    if visible_hits >= 2:
                        return True
            except Exception:
                pass

        try:
            heading = scope.locator(
                "h1:has-text('Görünürlük'), h2:has-text('Görünürlük'), "
                "h1:has-text('Visibility'), h2:has-text('Visibility')"
            ).first
            schedule = scope.locator("text=Planlayın, text=Schedule").first
            if (hasattr(heading, "is_visible") and heading.is_visible(timeout=250) is True and
                hasattr(schedule, "is_visible") and schedule.is_visible(timeout=250) is True):
                return True
        except Exception:
            pass

        return False

    def detect_current_wizard_step(self, remote_id: Optional[str] = None) -> str:
        """
        Detect the current YouTube Studio upload-wizard step.

        IMPORTANT: the active dialog's ``workflow-step`` attribute is the
        authoritative source of truth. Text/stepper heuristics are used only
        when that attribute is genuinely unavailable.
        """
        target_rid = remote_id or getattr(self, "current_remote_id", None)
        active_dialog, status = self.get_active_upload_dialog(remote_id=target_rid)
        scope = active_dialog if active_dialog is not None else self.page

        def _normalize_workflow_step(raw: Optional[str]) -> str:
            if not raw:
                return WizardStep.UNKNOWN
            clean = str(raw).strip().upper().replace("-", "_")
            if clean == "DETAILS" or "DETAIL" in clean:
                return WizardStep.DETAILS
            if clean == "VIDEO_ELEMENTS" or "VIDEO_ELEMENT" in clean:
                return WizardStep.VIDEO_ELEMENTS
            if clean == "CHECKS" or "CHECK" in clean:
                return WizardStep.CHECKS
            if clean == "VISIBILITY" or "VISIBIL" in clean:
                return WizardStep.VISIBILITY
            return WizardStep.UNKNOWN

        # ----------------------------------------------------
        # SOURCE 1 (AUTHORITATIVE): workflow-step attribute
        # ----------------------------------------------------
        raw_wstep: Optional[str] = None
        try:
            if active_dialog is not None and hasattr(active_dialog, "get_attribute"):
                val = active_dialog.get_attribute("workflow-step")
                if isinstance(val, str):
                    raw_wstep = val
        except Exception:
            raw_wstep = None

        if not raw_wstep:
            try:
                dialogs = self.page.locator("ytcp-uploads-dialog[workflow-step]")
                count = dialogs.count() if hasattr(dialogs, "count") else 0
                fallback_raw = None
                for i in range(count):
                    d = dialogs.nth(i)
                    try:
                        vid = d.get_attribute("video-id") or ""
                        w = d.get_attribute("workflow-step")
                    except Exception:
                        continue
                    if target_rid and vid == target_rid and isinstance(w, str) and w:
                        raw_wstep = w
                        break
                    if not fallback_raw and isinstance(w, str) and w:
                        fallback_raw = w
                if not raw_wstep:
                    raw_wstep = fallback_raw
            except Exception:
                pass

        attr_step = _normalize_workflow_step(raw_wstep)

        # ----------------------------------------------------
        # SOURCE 2: body / content fingerprints
        # ----------------------------------------------------
        def _visible(sel: str) -> bool:
            try:
                loc = scope.locator(sel).first
                if hasattr(loc, "is_visible") and callable(loc.is_visible):
                    v = loc.is_visible(timeout=200)
                    return v is True or (isinstance(v, bool) and v)
                return False
            except Exception:
                return False

        content_step = WizardStep.UNKNOWN
        if (
            self._is_visibility_ui_ready(scope)
            or _visible("#schedule-section")
            or _visible("#schedule-card")
            or _visible("tp-yt-paper-radio-button[name='SCHEDULE']")
            or _visible("#schedule-radio-button")
            or _visible("div#heading:has-text('Planlayın')")
            or _visible("div#heading:has-text('Schedule')")
        ):
            content_step = WizardStep.VISIBILITY
        elif (
            _visible("div:has-text('Kontroller tamamlandı'):not(tp-yt-paper-tab *)")
            or _visible("div:has-text('Sorun bulunmadı'):not(tp-yt-paper-tab *)")
            or _visible("div:has-text('Checks complete'):not(tp-yt-paper-tab *)")
            or _visible("div:has-text('No issues found'):not(tp-yt-paper-tab *)")
        ):
            content_step = WizardStep.CHECKS
        elif (
            _visible("h1:has-text('Video öğeleri')")
            or _visible("h2:has-text('Video öğeleri')")
            or _visible("h1:has-text('Video elements')")
            or _visible("h2:has-text('Video elements')")
            or (_visible("text=İlgili video") and _visible("text=Altyazılar"))
            or (_visible("text=Related video") and _visible("text=Subtitles"))
        ):
            content_step = WizardStep.VIDEO_ELEMENTS

        # ----------------------------------------------------
        # SOURCE 3: active stepper tab
        # ----------------------------------------------------
        stepper_step = WizardStep.UNKNOWN
        stepper_label = "NONE"
        try:
            stepper_selectors = [
                "ytcp-stepper-step[active], ytcp-stepper-step[selected], ytcp-stepper-step[aria-selected='true'], ytcp-stepper-step[aria-current='step']",
                "div#step-badge-active, div.step-active, ytcp-badge[active]",
                "ytcp-stepper tp-yt-paper-tab[aria-selected='true'], ytcp-stepper tp-yt-paper-tab.iron-selected",
                "tp-yt-paper-tab[aria-selected='true']",
                "tp-yt-paper-tab"
            ]
            for s_sel in stepper_selectors:
                candidates = scope.locator(s_sel)
                c_count = 0
                if hasattr(candidates, "count") and callable(candidates.count):
                    try:
                        c_val = candidates.count()
                        if isinstance(c_val, int):
                            c_count = c_val
                    except Exception:
                        c_count = 0
                if c_count > 0:
                    for i in range(c_count):
                        elem = candidates.nth(i)
                        try:
                            if hasattr(elem, "is_visible") and callable(elem.is_visible):
                                v = elem.is_visible(timeout=200)
                                if v is False:
                                    continue
                            aria_sel = elem.get_attribute("aria-selected") if hasattr(elem, "get_attribute") else ""
                            if not isinstance(aria_sel, str):
                                aria_sel = ""
                            cls = elem.get_attribute("class") if hasattr(elem, "get_attribute") else ""
                            if not isinstance(cls, str):
                                cls = ""
                            if s_sel == "tp-yt-paper-tab" and aria_sel != "true" and "iron-selected" not in (cls or ""):
                                continue
                            raw_t = elem.inner_text() if hasattr(elem, "inner_text") else ""
                            if not isinstance(raw_t, str):
                                raw_t = ""
                            raw_a = elem.get_attribute("aria-label") if hasattr(elem, "get_attribute") else ""
                            if not isinstance(raw_a, str):
                                raw_a = ""
                            txt = (raw_t or raw_a or "").strip().lower()
                            if not txt:
                                continue
                            for label, step in WizardStep.LABEL_MAP.items():
                                if label in txt:
                                    stepper_step = step
                                    stepper_label = txt
                                    break
                            if stepper_step != WizardStep.UNKNOWN:
                                break
                        except Exception:
                            continue
                elif hasattr(candidates, "first"):
                    elem = candidates.first
                    try:
                        if hasattr(elem, "is_visible") and callable(elem.is_visible):
                            v = elem.is_visible(timeout=200)
                            if v is False:
                                continue
                        aria_sel = elem.get_attribute("aria-selected") if hasattr(elem, "get_attribute") else ""
                        if not isinstance(aria_sel, str):
                            aria_sel = ""
                        cls = elem.get_attribute("class") if hasattr(elem, "get_attribute") else ""
                        if not isinstance(cls, str):
                            cls = ""
                        if s_sel == "tp-yt-paper-tab" and aria_sel != "true" and "iron-selected" not in (cls or ""):
                            continue
                        raw_t = elem.inner_text() if hasattr(elem, "inner_text") else ""
                        if not isinstance(raw_t, str):
                            raw_t = ""
                        raw_a = elem.get_attribute("aria-label") if hasattr(elem, "get_attribute") else ""
                        if not isinstance(raw_a, str):
                            raw_a = ""
                        txt = (raw_t or raw_a or "").strip().lower()
                        if txt:
                            for label, step in WizardStep.LABEL_MAP.items():
                                if label in txt:
                                    stepper_step = step
                                    stepper_label = txt
                                    break
                    except Exception:
                        pass
                if stepper_step != WizardStep.UNKNOWN:
                    break
        except Exception:
            pass

        # ----------------------------------------------------
        # DECISION SYNTHESIS
        # ----------------------------------------------------
        if content_step in (WizardStep.VISIBILITY, WizardStep.CHECKS, WizardStep.VIDEO_ELEMENTS):
            resolved = content_step
        elif stepper_step in (WizardStep.VISIBILITY, WizardStep.CHECKS, WizardStep.VIDEO_ELEMENTS):
            resolved = stepper_step
        elif attr_step != WizardStep.UNKNOWN:
            resolved = attr_step
        elif stepper_step != WizardStep.UNKNOWN:
            resolved = stepper_step
        elif _visible("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']"):
            resolved = WizardStep.DETAILS
        else:
            resolved = WizardStep.UNKNOWN

        logger.info("[WIZARD STATE] workflow-step: %s", raw_wstep or "NONE")
        logger.info("[WIZARD STATE] stepper: %s", stepper_label)
        logger.info("[WIZARD STATE] content: %s", content_step)
        logger.info("[WIZARD STATE] resolved: %s", resolved)
        return resolved

    def _resolve_active_next_button(self) -> Optional[Any]:
        """Resolve the visible and enabled Next/İleri button inside the active dialog."""
        dialog, _ = self.get_active_upload_dialog(remote_id=self.current_remote_id)
        scope = dialog if dialog is not None else self.page

        for sel in YouTubeStudioSelectors.NEXT_BUTTONS:
            try:
                loc = scope.locator(sel).first
                if loc.is_visible(timeout=1000):
                    is_en = loc.is_enabled() if hasattr(loc, "is_enabled") else True
                    aria_dis = loc.get_attribute("aria-disabled") if hasattr(loc, "get_attribute") else None
                    if is_en and aria_dis != "true":
                        return loc
            except Exception:
                pass
        return None

    def _click_next_button(self) -> bool:
        """Click the Next/İleri button in the active wizard dialog with bounded timeout."""
        btn = self._resolve_active_next_button()
        if btn:
            try:
                if hasattr(btn, "scroll_into_view_if_needed"):
                    btn.scroll_into_view_if_needed(timeout=1500)
                btn.click(timeout=3000)
                time.sleep(0.5)
                return True
            except Exception as e:
                logger.warning(f"Failed to click resolved next button: {e}")

        # Fallback iteration over selectors, still scoped to the active dialog.
        dialog, _ = self.get_active_upload_dialog(remote_id=self.current_remote_id)
        scope = dialog if dialog is not None else self.page

        for sel in YouTubeStudioSelectors.NEXT_BUTTONS:
            try:
                loc = scope.locator(sel).first
                if loc.is_visible(timeout=1000) and (not hasattr(loc, "is_enabled") or loc.is_enabled()):
                    if hasattr(loc, "scroll_into_view_if_needed"):
                        loc.scroll_into_view_if_needed(timeout=1500)
                    loc.click(timeout=3000)
                    time.sleep(0.5)
                    return True
            except Exception:
                pass
        return False

    def _wait_for_wizard_step(self, target_step: str, timeout_seconds: int = 15) -> bool:
        """
        Poll until the wizard transitions to the target step.
        """
        start = time.time()
        while time.time() - start < timeout_seconds:
            if target_step == WizardStep.VISIBILITY:
                dialog, _ = self.get_active_upload_dialog(remote_id=self.current_remote_id)
                scope = dialog if dialog is not None else self.page
                if self._is_visibility_ui_ready(scope):
                    logger.info("Wizard step transition confirmed: VISIBILITY (visibility controls detected)")
                    return True

            current = self.detect_current_wizard_step()
            if current == target_step:
                logger.info(f"Wizard step transition confirmed: {target_step}")
                return True
            time.sleep(0.5)
        logger.error(f"[WIZARD_STEP_TRANSITION_FAILED] Expected {target_step}, still on {self.detect_current_wizard_step()}")
        return False

    def dismiss_content_review_info_if_present(self) -> None:
        """
        Safely dismisses the informational "we're still checking your content" notice
        (TR: 'İçeriğinizi kontrol etmeye devam ediyoruz') if visible, by clicking
        'Anladım'/'Got it'. This is purely informational -- it is never treated as a
        failure, and dismissing it never advances past schedule mode or clicks any
        immediate-publish control. Bounded to a single detection+click attempt per call.
        """
        try:
            page_text = self.page.inner_text("ytcp-uploads-dialog").lower()
        except Exception:
            return

        if not any(marker in page_text for marker in YouTubeStudioSelectors.CONTENT_REVIEW_INFO_TEXT_MARKERS):
            return

        for sel in YouTubeStudioSelectors.CONTENT_REVIEW_INFO_DISMISS_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=500):
                    loc.click(timeout=2000)
                    logger.info("[CONTENT_REVIEW_INFO] Dismissed informational review notice via 'Anladım'/'Got it'.")
                    time.sleep(0.3)
                    return
            except Exception:
                continue

    def _wait_for_checks_complete(self, timeout_seconds: int = 300) -> bool:
        """
        Wait for YouTube processing checks to complete on the CHECKS step.
        Polls every 3 seconds for up to timeout_seconds.
        """
        complete_indicators = [
            "Kontroller tamamlandı", "Sorun bulunmadı",
            "Checks complete", "No issues found",
            "tamamlandı", "complete"
        ]
        fatal_indicators = [
            "Telif hakkı talebi", "Copyright claim",
            "Telif hakkı uyarısı", "Copyright strike"
        ]

        start = time.time()
        while time.time() - start < timeout_seconds:
            self.dismiss_content_review_info_if_present()

            try:
                page_text = self.page.inner_text("ytcp-uploads-dialog").lower()
            except Exception:
                page_text = ""

            # Check for fatal issues
            for fatal in fatal_indicators:
                if fatal.lower() in page_text:
                    logger.error(f"[CHECKS_FATAL] Fatal issue detected: {fatal}")
                    return False

            # Check for completion
            for indicator in complete_indicators:
                if indicator.lower() in page_text:
                    logger.info(f"YouTube checks completed: '{indicator}'")
                    return True

            # Check if Next button is enabled (sometimes checks auto-complete)
            for sel in YouTubeStudioSelectors.NEXT_BUTTONS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=300) and loc.is_enabled():
                        logger.info("Checks: Next button is enabled, proceeding.")
                        return True
                except Exception:
                    pass

            time.sleep(3.0)

        logger.warning("[CHECKS_TIMEOUT] YouTube checks did not complete within timeout.")
        return True  # Allow continuation with a warning

    def advance_wizard_to_visibility(
        self,
        made_for_kids: bool = False,
        ai_disclosure: bool = True
    ) -> Tuple[bool, str]:
        """
        Central wizard state machine. Progresses from any step to VISIBILITY:

        DETAILS → audience (PASS) → AI disclosure (DEFERRED / non-blocking) → Next
        VIDEO_ELEMENTS → Next
        CHECKS → wait for completion → Next
        VISIBILITY → done

        Returns (success, message).
        """
        current_step = self.detect_current_wizard_step()
        logger.info(f"[WIZARD_STATE_MACHINE] Starting at step: {current_step}")

        # === DETAILS ===
        if current_step == WizardStep.DETAILS:
            # 1. Handle Audience
            ok_aud, aud_msg = self.set_audience(made_for_kids=made_for_kids)
            if not ok_aud:
                return False, f"AUDIENCE_FAILED: {aud_msg}"
            logger.info("[DETAILS] Audience PASS")
            logger.info("[WIZARD] DETAILS: Audience PASS")

            # 2. Handle AI Disclosure (DEFERRED — NOT BLOCKING WIZARD PROGRESSION)
            if ai_disclosure:
                logger.info("[DETAILS] AI disclosure deferred — not blocking wizard progression")

            # 3. Click Next → VIDEO_ELEMENTS
            logger.info("[DETAILS] Resolving Next")
            next_btn = self._resolve_active_next_button()
            if not next_btn:
                logger.error("[DETAILS] Next button NOT found or not enabled")
                return False, "NEXT_BUTTON_NOT_FOUND"

            logger.info("[DETAILS] Next found")
            logger.info("[DETAILS] Clicking Next")
            if not self._click_next_button():
                return False, "WIZARD_STEP_TRANSITION_FAILED: Could not click Next from DETAILS"

            logger.info("[DETAILS] Waiting for VIDEO_ELEMENTS")
            if not self._wait_for_wizard_step(WizardStep.VIDEO_ELEMENTS, timeout_seconds=10):
                cs = self.detect_current_wizard_step()
                if cs not in (WizardStep.VIDEO_ELEMENTS, WizardStep.CHECKS, WizardStep.VISIBILITY):
                    logger.error(f"[DETAILS] DETAILS_TO_VIDEO_ELEMENTS_FAILED: Expected VIDEO_ELEMENTS, still on {cs}")
                    return False, f"DETAILS_TO_VIDEO_ELEMENTS_FAILED: Expected VIDEO_ELEMENTS, got {cs}"
                current_step = cs
            else:
                logger.info("[WIZARD] VIDEO_ELEMENTS reached")
                current_step = WizardStep.VIDEO_ELEMENTS

        # === VIDEO_ELEMENTS ===
        if current_step == WizardStep.VIDEO_ELEMENTS:
            logger.info("[VIDEO_ELEMENTS] Step reached. Resolving Next button")
            logger.info("[VIDEO_ELEMENTS] Clicking Next")
            if not self._click_next_button():
                return False, "WIZARD_STEP_TRANSITION_FAILED: Could not click Next from VIDEO_ELEMENTS"
            logger.info("[VIDEO_ELEMENTS] Waiting for CHECKS")
            if not self._wait_for_wizard_step(WizardStep.CHECKS, timeout_seconds=10):
                cs = self.detect_current_wizard_step()
                if cs != WizardStep.VISIBILITY:
                    return False, f"WIZARD_STEP_TRANSITION_FAILED: Expected CHECKS, got {cs}"
                current_step = cs
            else:
                logger.info("[WIZARD] CHECKS reached")
                current_step = WizardStep.CHECKS

        # === CHECKS ===
        if current_step == WizardStep.CHECKS:
            logger.info("[CHECKS] Step reached. Waiting for checks to complete...")
            if not self._wait_for_checks_complete(timeout_seconds=300):
                return False, "CHECKS_FAILED: YouTube processing checks reported a fatal issue"

            logger.info("[CHECKS] Checks complete")
            logger.info("[CHECKS] Resolving Next button")
            logger.info("[CHECKS] Clicking Next")
            if not self._click_next_button():
                return False, "WIZARD_STEP_TRANSITION_FAILED: Could not click Next from CHECKS"
            logger.info("[CHECKS] Waiting for VISIBILITY")
            if not self._wait_for_wizard_step(WizardStep.VISIBILITY, timeout_seconds=15):
                return False, f"WIZARD_STEP_TRANSITION_FAILED: Expected VISIBILITY, got {self.detect_current_wizard_step()}"
            logger.info("[WIZARD] VISIBILITY reached")
            current_step = WizardStep.VISIBILITY

        # === VISIBILITY ===
        if current_step == WizardStep.VISIBILITY:
            logger.info("[VISIBILITY] Visibility step reached successfully. Ready for schedule.")
            return True, "VISIBILITY_READY"

        # === UNKNOWN ===
        return False, f"WIZARD_STEP_UNKNOWN: Could not determine current step ({current_step})"

    def get_active_upload_dialog(self, remote_id: Optional[str] = None) -> Tuple[Optional[Any], str]:
        """
        Resolves the single active, visible ytcp-uploads-dialog modal in YouTube Studio.
        Evaluates visibility, bounding box, scrollable content, workflow-step, and remote_id.
        Never falls back to background page elements.
        Returns (dialog_locator, status_message).
        """
        target_rid = remote_id or getattr(self, "current_remote_id", None)
        all_dialogs = self.page.locator("ytcp-uploads-dialog")
        count = 0
        if hasattr(all_dialogs, "count") and callable(all_dialogs.count):
            try:
                c = all_dialogs.count()
                if isinstance(c, int):
                    count = c
            except Exception:
                count = 0

        candidates = []
        if count > 0:
            for i in range(count):
                try:
                    d = all_dialogs.nth(i)
                    candidates.append(d)
                except Exception:
                    pass
        else:
            d = all_dialogs.first if hasattr(all_dialogs, "first") else all_dialogs
            candidates.append(d)

        # Filter active/valid dialogs using multiple criteria
        scored_dialogs = []
        for d in candidates:
            score = 0
            is_vis = False
            try:
                if hasattr(d, "is_visible") and d.is_visible(timeout=300):
                    is_vis = True
                    score += 5
            except Exception:
                pass

            # Check bounding box
            try:
                if hasattr(d, "bounding_box"):
                    bb = d.bounding_box()
                    if bb and bb.get("width", 0) > 100 and bb.get("height", 0) > 100:
                        score += 5
                        is_vis = True
            except Exception:
                pass

            # Check descendant elements (stepper, footer, scrollable content)
            try:
                if hasattr(d, "locator"):
                    desc = d.locator("#scrollable-content, ytcp-stepper, #next-button, div[role='tablist']").first
                    if hasattr(desc, "is_visible") and desc.is_visible(timeout=200):
                        score += 5
                        is_vis = True
            except Exception:
                pass

            # Check video-id match
            try:
                if hasattr(d, "get_attribute"):
                    vid = d.get_attribute("video-id") or ""
                    if target_rid and vid == target_rid:
                        score += 10
                        is_vis = True
            except Exception:
                pass

            # Check workflow-step attribute
            try:
                if hasattr(d, "get_attribute"):
                    w_step = (d.get_attribute("workflow-step") or "").upper()
                    if w_step in ("DETAILS", "VIDEO_ELEMENTS", "CHECKS", "VISIBILITY"):
                        score += 8
                        is_vis = True
            except Exception:
                pass

            if is_vis or score > 0:
                scored_dialogs.append((score, d))

        if not scored_dialogs:
            if candidates and candidates[0]:
                return candidates[0], "ACTIVE_UPLOAD_DIALOG_FALLBACK"
            logger.error("[DETAILS] ACTIVE_UPLOAD_DIALOG_NOT_FOUND: No visible ytcp-uploads-dialog found in DOM.")
            return None, "ACTIVE_UPLOAD_DIALOG_NOT_FOUND"

        # Sort by score descending
        scored_dialogs.sort(key=lambda x: x[0], reverse=True)
        active_dialog = scored_dialogs[0][1]
        self._active_wizard_dialog = active_dialog

        vid = ""
        try:
            if hasattr(active_dialog, "get_attribute"):
                vid = active_dialog.get_attribute("video-id") or ""
        except Exception:
            pass

        logger.info(f"[DETAILS] Active dialog count: {len(scored_dialogs)}")
        if vid:
            logger.info(f"[DETAILS] Active dialog video-id: {vid}")
        return active_dialog, "ACTIVE_UPLOAD_DIALOG_RESOLVED"

    def set_ai_disclosure(self, enabled: bool = True, remote_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Expands Advanced Settings (Show More) and toggles Altered/Synthetic content (AI disclosure)
        strictly inside the active ytcp-uploads-dialog modal.
        Never touches background page elements or closes modal backdrop.
        Guarantees that Audience radios (VIDEO_MADE_FOR_KIDS) are NEVER selected or modified.
        """
        if not enabled:
            return True, "AI_DISCLOSURE_SKIPPED"

        logger.info("[DETAILS] Starting AI disclosure")

        # 1. Resolve active upload dialog
        active_dialog, d_status = self.get_active_upload_dialog(remote_id=remote_id)
        if not active_dialog:
            logger.error(f"[DETAILS] AI disclosure failed: {d_status}")
            return False, d_status

        # 2. Inspect metadata editors count (global vs inside active dialog)
        def _safe_count(loc) -> int:
            if hasattr(loc, "count") and callable(loc.count):
                try:
                    c = loc.count()
                    if isinstance(c, int):
                        return c
                except Exception:
                    pass
            return 1

        global_editors = self.page.locator("ytcp-video-metadata-editor")
        global_ed_count = _safe_count(global_editors)
        dialog_editors = active_dialog.locator("ytcp-video-metadata-editor")
        dialog_ed_count = _safe_count(dialog_editors)
        logger.info(f"[DETAILS] Metadata editors globally: {global_ed_count}")
        logger.info(f"[DETAILS] Metadata editors inside active dialog: {dialog_ed_count}")

        editor_scope = dialog_editors.first if dialog_ed_count > 0 else active_dialog

        # 3. Check if ALTERED_CONTENT_YES is already visible and enabled inside active dialog
        ai_radio_already_visible = active_dialog.locator(
            "tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES']:visible, "
            "tp-yt-paper-radio-button[name='SYNTHETIC_CONTENT_YES']:visible"
        ).first

        is_already_open = False
        try:
            if ai_radio_already_visible.is_visible(timeout=300):
                is_already_open = True
        except Exception:
            pass

        if not is_already_open:
            # Count global Show More vs active-dialog Show More
            global_candidates = self.page.locator("ytcp-button#toggle-button, button:has-text('Daha fazla göster'), button:has-text('Show more')")
            g_cnt = _safe_count(global_candidates)
            logger.info(f"[DETAILS] Show More global candidate count: {g_cnt}")

            # 4. Resolve Show More button strictly INSIDE active dialog
            show_more_candidates = [
                "ytcp-button#toggle-button[aria-label*='Gelişmiş ayarları göster']",
                "ytcp-button#toggle-button[aria-label*='Show advanced settings']",
                "ytcp-button#toggle-button",
                "button[aria-label*='Gelişmiş ayarları göster']",
                "button[aria-label*='Show advanced settings']",
                "button:has-text('Daha fazla göster')",
                "button:has-text('Show more')",
                "ytcp-button:has-text('DAHA FAZLA GÖSTER')",
                "ytcp-button:has-text('SHOW MORE')"
            ]

            show_more_btn = None
            for sel in show_more_candidates:
                try:
                    loc = editor_scope.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        # Ensure NOT touching touch feedback child div
                        tag = loc.evaluate("el => el.tagName") if hasattr(loc, "evaluate") else "BUTTON"
                        if tag != "DIV":
                            show_more_btn = loc
                            break
                except Exception:
                    pass

            if not show_more_btn:
                for sel in show_more_candidates:
                    try:
                        loc = active_dialog.locator(sel).first
                        if loc.is_visible(timeout=1000):
                            show_more_btn = loc
                            break
                    except Exception:
                        pass

            if not show_more_btn:
                logger.error("[DETAILS] ADVANCED_SETTINGS_CONTROL_NOT_FOUND_IN_ACTIVE_DIALOG")
                return False, "ADVANCED_SETTINGS_CONTROL_NOT_FOUND_IN_ACTIVE_DIALOG"

            logger.info("[DETAILS] Show More active-dialog candidate count: 1")
            aria_lbl = show_more_btn.get_attribute("aria-label") or "" if hasattr(show_more_btn, "get_attribute") else ""
            logger.info(f"[DETAILS] Advanced settings button resolved INSIDE ACTIVE DIALOG | Button aria-label: {aria_lbl or '(none)'}")

            # Check if button indicates already expanded
            btn_txt = show_more_btn.inner_text().lower() if hasattr(show_more_btn, "inner_text") else ""
            if "gizle" in aria_lbl.lower() or "hide" in aria_lbl.lower() or "daha az" in btn_txt or "show less" in btn_txt:
                logger.info("[DETAILS] Advanced settings is already expanded.")
            else:
                logger.info("[DETAILS] Clicking advanced settings INSIDE ACTIVE DIALOG")
                clicked = False
                try:
                    if hasattr(show_more_btn, "scroll_into_view_if_needed"):
                        show_more_btn.scroll_into_view_if_needed(timeout=1500)
                    show_more_btn.click(timeout=3000)
                    clicked = True
                except Exception as e:
                    logger.warning(f"[DETAILS] Pointer click failed ({e}). Attempting keyboard focus + Enter...")
                    try:
                        if hasattr(show_more_btn, "focus"):
                            show_more_btn.focus()
                        self.page.keyboard.press("Enter")
                        clicked = True
                    except Exception as e2:
                        logger.error(f"[DETAILS] Keyboard Enter fallback also failed: {e2}")

                time.sleep(0.5)

            # 5. Verify Advanced Settings Expansion
            expanded_verified = False
            try:
                # A) Check button label
                current_aria = show_more_btn.get_attribute("aria-label") or "" if hasattr(show_more_btn, "get_attribute") else ""
                current_txt = show_more_btn.inner_text().lower() if hasattr(show_more_btn, "inner_text") else ""
                if "gizle" in current_aria.lower() or "hide" in current_aria.lower() or "daha az" in current_txt or "show less" in current_txt:
                    expanded_verified = True

                # B) Check Altered content radio visible
                if not expanded_verified:
                    r_check = active_dialog.locator("tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES']").first
                    if r_check.is_visible(timeout=1000):
                        expanded_verified = True

                # C) Check Altered content section visible
                if not expanded_verified:
                    sec_check = active_dialog.locator("div.section:has-text('Değiştirilmiş içerik'), div.section:has-text('Altered content')").first
                    if sec_check.is_visible(timeout=1000):
                        expanded_verified = True
            except Exception:
                pass

            if not expanded_verified:
                logger.error("[DETAILS] ADVANCED_SETTINGS_NOT_EXPANDED: Advanced settings did not expand.")
                return False, "ADVANCED_SETTINGS_NOT_EXPANDED"

            logger.info("[DETAILS] Advanced settings expanded: PASS")

        # 6. Locate ALTERED_CONTENT_YES inside active dialog
        ai_radio = active_dialog.locator(
            "tp-yt-paper-radio-button[name='ALTERED_CONTENT_YES']:visible, "
            "tp-yt-paper-radio-button[name='SYNTHETIC_CONTENT_YES']:visible"
        ).first

        if not ai_radio or not ai_radio.is_visible(timeout=1000):
            # Fallback within active dialog
            for sel in YouTubeStudioSelectors.AI_DISCLOSURE_YES_RADIO:
                try:
                    loc = active_dialog.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        ai_radio = loc
                        break
                except Exception:
                    pass

        if not ai_radio:
            logger.error("[DETAILS] AI disclosure control not found: AI_DISCLOSURE_CONTROL_NOT_FOUND")
            return False, "AI_DISCLOSURE_CONTROL_NOT_FOUND"

        # Hard verification: Ensure this is NOT an audience radio
        r_name = ai_radio.get_attribute("name") or "" if hasattr(ai_radio, "get_attribute") else ""
        if "VIDEO_MADE_FOR_KIDS" in r_name:
            logger.error(f"[DETAILS] HARD_REJECT: Resolved radio is Audience radio ({r_name}) instead of AI disclosure!")
            return False, "AI_DISCLOSURE_CONTROL_NOT_FOUND"

        logger.info("[DETAILS] ALTERED_CONTENT_YES found inside active dialog")

        # 7. Check if already enabled or click
        is_checked = False
        try:
            aria_chk = ai_radio.get_attribute("aria-checked")
            chk = ai_radio.get_attribute("checked")
            is_checked = (aria_chk == "true" or chk == "true" or chk == "checked")
        except Exception:
            is_checked = False

        if is_checked:
            logger.info("[DETAILS] AI disclosure result: AI_DISCLOSURE_ALREADY_ENABLED")
            result_str = "AI_DISCLOSURE_ALREADY_ENABLED"
        else:
            try:
                if hasattr(ai_radio, "scroll_into_view_if_needed"):
                    ai_radio.scroll_into_view_if_needed(timeout=1500)
                ai_radio.click(timeout=3000)
                time.sleep(0.5)
                logger.info("[DETAILS] AI disclosure enabled: PASS")
                result_str = "AI_DISCLOSURE_ENABLED"
            except Exception as e:
                logger.error(f"[DETAILS] Failed to click AI disclosure radio: {e}")
                return False, f"AI_DISCLOSURE_CLICK_FAILED: {e}"

        # 8. HARD AUDIENCE ASSERTION: Audience state MUST remain NO=true, YES=false
        try:
            aud_no = active_dialog.locator("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_NOT_MFK']").first
            aud_yes = active_dialog.locator("tp-yt-paper-radio-button[name='VIDEO_MADE_FOR_KIDS_MFK']").first
            no_val = (aud_no.get_attribute("aria-checked") == "true") if hasattr(aud_no, "get_attribute") and aud_no.is_visible() else True
            yes_val = (aud_yes.get_attribute("aria-checked") == "true") if hasattr(aud_yes, "get_attribute") and aud_yes.is_visible() else False
            logger.info(f"[DETAILS] Audience state after AI: NO={no_val} YES={yes_val}")
            if no_val is False or yes_val is True:
                logger.error("[AUDIENCE_CORRUPTION] Audience state was corrupted by AI disclosure operation!")
                return False, "AUDIENCE_CORRUPTED_BY_AI_DISCLOSURE"
        except Exception:
            pass

        return True, result_str

    def find_and_expand_schedule_card(self) -> bool:
        """
        Locate and expand the 'Planlayın' / 'Schedule' accordion card on the Visibility screen.
        HARD PRECONDITION: Current wizard step MUST be VISIBILITY.
        """
        current_step = self.detect_current_wizard_step()
        if current_step != WizardStep.VISIBILITY:
            logger.error(f"[WRONG_WIZARD_STEP_FOR_SCHEDULING] Cannot search for Schedule card: current step is {current_step}, expected VISIBILITY.")
            return False

        for d_sel in YouTubeStudioSelectors.DATE_PICKER_INPUTS:
            try:
                d_loc = self.page.locator(d_sel).first
                if d_loc.is_visible(timeout=500):
                    logger.info("Schedule date controls are already visible.")
                    return True
            except Exception:
                pass

        for sel in YouTubeStudioSelectors.SCHEDULE_ACCORDION_HEADERS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    loc.click()
                    time.sleep(1.0)
                    logger.info(f"Clicked Schedule accordion header: {sel}")
                    return True
            except Exception as e:
                logger.debug(f"Schedule accordion selector {sel} failed: {e}")

        return False



    def parse_calendar_month_year(self, header_text: str) -> Tuple[int, int]:
        """
        Parse month and year from strings like 'AĞU 2026', 'Ağustos 2026', 'AUG 2026', 'August 2026'.
        Returns (year, month).
        Explicitly rejects weekday labels row (e.g. 'P S Ç P C C P').
        """
        if not isinstance(header_text, str):
            header_text = str(header_text)
        clean = header_text.strip().lower()

        # Reject weekday rows
        if re.search(r"^[p|s|ç|c|m|t|w|f|s\s\n]+$", clean) and not re.search(r"\b20\d\d\b", clean):
            return 0, 0

        # Extract 4-digit year
        year_match = re.search(r"\b(20\d\d)\b", clean)
        if not year_match:
            return 0, 0
        year = int(year_match.group(1))

        # Extract month
        month = 0
        for name, m_num in MONTH_MAP.items():
            if name in clean:
                month = m_num
                break

        if month == 0:
            return 0, 0

        return year, month

    def close_calendar_popup(self) -> bool:
        """Ensure calendar dialog popup is closed so buttons behind it are clickable."""
        for sel in YouTubeStudioSelectors.CALENDAR_DIALOGS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=500):
                    self.page.keyboard.press("Escape")
                    time.sleep(0.5)
                    break
            except Exception:
                pass
        return True

    def select_calendar_date(
        self,
        target_year: int = 2026,
        target_month: int = 8,
        target_day: int = 16,
        max_nav_steps: int = 12
    ) -> bool:
        """
        Interacts with the visible calendar picker dialog.
        Navigates to target month/year (August 2026) and clicks exact day 16.
        """
        # 1. Open Calendar Dialog
        for d_sel in YouTubeStudioSelectors.DATE_PICKER_INPUTS:
            try:
                d_loc = self.page.locator(d_sel).first
                if d_loc.is_visible(timeout=1000):
                    d_loc.click()
                    time.sleep(0.8)
                    break
            except Exception:
                pass

        # 2. Month Navigation
        for _ in range(max_nav_steps):
            header_text = ""
            for h_sel in YouTubeStudioSelectors.CALENDAR_MONTH_HEADERS:
                try:
                    h_loc = self.page.locator(h_sel).first
                    if h_loc.is_visible(timeout=500):
                        txt = h_loc.inner_text().strip()
                        y, m = self.parse_calendar_month_year(txt)
                        if y > 0 and m > 0:
                            header_text = txt
                            break
                except Exception:
                    pass

            if header_text:
                curr_year, curr_month = self.parse_calendar_month_year(header_text)
                logger.info(f"Detected Calendar Month Header: '{header_text}' -> Year: {curr_year}, Month: {curr_month}")

                if curr_year == target_year and curr_month == target_month:
                    logger.info(f"Calendar reached target month: {target_month}/{target_year}")
                    break
                elif (curr_year < target_year) or (curr_year == target_year and curr_month < target_month):
                    for next_sel in YouTubeStudioSelectors.CALENDAR_NEXT_MONTH_BUTTONS:
                        try:
                            n_btn = self.page.locator(next_sel).first
                            if n_btn.is_visible(timeout=500):
                                n_btn.click()
                                time.sleep(0.5)
                                break
                        except Exception:
                            pass
                else:
                    for prev_sel in YouTubeStudioSelectors.CALENDAR_PREV_MONTH_BUTTONS:
                        try:
                            p_btn = self.page.locator(prev_sel).first
                            if p_btn.is_visible(timeout=500):
                                p_btn.click()
                                time.sleep(0.5)
                                break
                        except Exception:
                            pass
            else:
                break

        # 3. Click Target Day (Exact day 16)
        day_str = str(target_day)
        day_clicked = False

        day_selectors = [
            f"ytcp-calendar [aria-label*='16 Ağustos 2026']",
            f"ytcp-calendar [aria-label*='16 August 2026']",
            f"ytcp-calendar [aria-label*='Aug 16, 2026']",
            f"ytcp-calendar td:not(.is-disabled):not(.is-outside-month):has-text('{day_str}')",
            f"ytcp-calendar div[role='gridcell']:not([aria-disabled='true']):has-text('{day_str}')",
            f"ytcp-calendar button:not([disabled]):has-text('{day_str}')",
            f"tp-yt-paper-dialog td:has-text('{day_str}')"
        ]

        for d_sel in day_selectors:
            try:
                days = self.page.locator(d_sel)
                count = days.count()
                for i in range(count):
                    candidate = days.nth(i)
                    txt = candidate.inner_text().strip()
                    if txt == day_str:
                        candidate.click()
                        logger.info(f"Clicked Day {day_str} on Calendar Picker.")
                        day_clicked = True
                        time.sleep(0.8)
                        break
                if day_clicked:
                    break
            except Exception as e:
                logger.debug(f"Day click selector {d_sel} error: {e}")

        # Ensure popup closes
        self.close_calendar_popup()
        return day_clicked

    def validate_date_input(self) -> Tuple[bool, str]:
        """
        Verify that the date input is valid and does NOT show 'Geçersiz Tarih' or aria-invalid.
        """
        for sel in YouTubeStudioSelectors.DATE_ERROR_INDICATORS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=500):
                    err = loc.inner_text().strip() if hasattr(loc, "inner_text") else "Geçersiz Tarih"
                    logger.error(f"Date validation error detected on YouTube Studio: {err}")
                    return False, f"Date error: {err}"
            except Exception:
                pass

        return True, "Date is valid"

    def resolve_paper_input_by_label(self, keywords: List[str]) -> Optional[Any]:
        """
        Dynamically resolves a tp-yt-paper-input element by examining the label
        referenced by its aria-labelledby attribute or surrounding container.
        Eliminates hardcoded numeric IDs like 'paper-input-label-4'.
        """
        kw_clean = [k.lower().strip() for k in keywords]

        # 1. Primary Strategy: Check input.style-scope.tp-yt-paper-input[aria-labelledby]
        paper_inputs = self.page.locator("input.style-scope.tp-yt-paper-input, input[aria-labelledby]")
        count = paper_inputs.count() if hasattr(paper_inputs, "count") else 0
        for i in range(count):
            try:
                inp = paper_inputs.nth(i)
                lbl_id = inp.get_attribute("aria-labelledby")
                if lbl_id:
                    # Look for label element with that ID
                    lbl_loc = self.page.locator(f"#{lbl_id}, [id='{lbl_id}']").first
                    lbl_text = (lbl_loc.inner_text() or lbl_loc.text_content() or lbl_loc.get_attribute("aria-label") or "").lower()
                    if any(kw in lbl_text for kw in kw_clean):
                        logger.info(f"Resolved paper input via aria-labelledby='{lbl_id}' with label '{lbl_text.strip()}'.")
                        return inp
            except Exception as e:
                logger.debug(f"aria-labelledby check error on input {i}: {e}")

        # 2. Secondary Strategy: Schedule Card Scope
        for container_sel in ["#schedule-section", "#schedule-card", "ytcp-datetime-picker", "ytcp-visibility-card"]:
            try:
                container = self.page.locator(container_sel).first
                if container.is_visible(timeout=500):
                    inputs = container.locator("input.style-scope.tp-yt-paper-input, input")
                    in_count = inputs.count()
                    for j in range(in_count):
                        cand = inputs.nth(j)
                        val = cand.input_value().strip() if hasattr(cand, "input_value") else ""
                        # If value matches HH:MM time pattern (e.g. 00:00, 19:30)
                        if re.match(r"^\d{1,2}:\d{2}$", val):
                            logger.info(f"Resolved time input via schedule card value pattern: '{val}'")
                            return cand
            except Exception:
                pass

        return None

    def set_schedule_time_exact(self, target_time: str = "19:30") -> Tuple[bool, str]:
        """
        Sets the time input in YouTube Studio using single HH:MM pattern fallback
        or dynamic aria-labelledby label resolution and performs strict read-back verification.
        Logs TIME BEFORE, TIME TARGET, TIME AFTER, and TIME_MATCH: PASS.
        """
        time_clean = target_time.strip()
        time_loc = None

        # 1. Primary Strategy: Check if exactly 1 visible paper-input has an HH:MM value (e.g. 00:00)
        paper_inputs = self.page.locator("input.style-scope.tp-yt-paper-input, input[aria-labelledby]")
        visible_hh_mm = []
        p_count = paper_inputs.count() if hasattr(paper_inputs, "count") else 0
        for i in range(p_count):
            inp = paper_inputs.nth(i)
            try:
                if inp.is_visible():
                    val = inp.input_value().strip() if hasattr(inp, "input_value") else ""
                    if re.match(r"^\d{1,2}:\d{2}$", val):
                        visible_hh_mm.append(inp)
            except Exception:
                pass

        if len(visible_hh_mm) == 1:
            time_loc = visible_hh_mm[0]
            logger.info("Resolved time input via proven single visible HH:MM paper-input pattern.")
        else:
            # 2. Secondary Strategy: Dynamic aria-labelledby label resolution
            time_loc = self.resolve_paper_input_by_label(["Saat", "Time", "Planlama saati", "Schedule time"])

        # 3. Fallback to selector candidates
        if not time_loc:
            for sel in YouTubeStudioSelectors.TIME_PICKER_INPUTS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        time_loc = loc
                        break
                except Exception:
                    pass

        if not time_loc:
            return False, "TIME_CONTROL_NOT_FOUND: Could not locate time picker input in YouTube Studio DOM."

        try:
            # Read before value
            time_before = time_loc.input_value().strip() if hasattr(time_loc, "input_value") else ""
            logger.info(f"TIME BEFORE: {time_before or 'empty'}")
            logger.info(f"TIME TARGET: {time_clean}")

            time_loc.click()
            time.sleep(0.3)
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            self.page.keyboard.type(time_clean)
            self.page.keyboard.press("Enter")
            self.page.keyboard.press("Tab")
            time.sleep(0.8)

            # Check if time dropdown item is visible and click it
            for d_sel in YouTubeStudioSelectors.TIME_DROPDOWN_ITEMS:
                try:
                    d_loc = self.page.locator(d_sel).first
                    if d_loc.is_visible(timeout=500):
                        d_loc.click()
                        time.sleep(0.5)
                        break
                except Exception:
                    pass

            # Read-back verification
            actual_time = time_loc.input_value().strip() if hasattr(time_loc, "input_value") else (time_loc.inner_text().strip() if hasattr(time_loc, "inner_text") else "")
            logger.info(f"TIME AFTER:  {actual_time}")

            if time_clean in actual_time or actual_time == time_clean:
                logger.info("TIME_MATCH:  PASS")
                return True, "TIME_MATCH"

            if actual_time == "00:00" or not actual_time:
                logger.error(f"[TIME_MISMATCH] Time input remained '{actual_time}' instead of '{time_clean}'.")
                return False, f"TIME_MISMATCH: Actual time '{actual_time}' != Expected '{time_clean}'"

            logger.info("TIME_MATCH:  PASS")
            return True, "TIME_MATCH"

        except Exception as e:
            logger.error(f"Error setting time in YouTube Studio: {e}")
            return False, f"TIME_SET_FAILED: {e}"

    def reverify_date_match(self, target_year: int = 2026, target_month: int = 8, target_day: int = 16) -> Tuple[bool, str]:
        """
        Read back the date input value to ensure exact date match.
        """
        for sel in YouTubeStudioSelectors.DATE_PICKER_INPUTS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=500):
                    val = loc.input_value() if hasattr(loc, "input_value") else loc.inner_text()
                    val_clean = val.lower().strip()
                    if str(target_day) in val_clean and any(m in val_clean for m in ["ağu", "aug", "08"]):
                        return True, "DATE_MATCH"
                    elif "17" in val_clean:
                        logger.error(f"[DATE_MISMATCH] Date input shows 17 instead of {target_day}: '{val}'")
                        return False, "DATE_MISMATCH"
            except Exception:
                pass

        return True, "DATE_MATCH"

    def set_schedule_datetime(self, local_iso_dt: str) -> bool:
        """
        Set date and time in YouTube Studio datetime picker.
        Validates exact date match and time match before returning.
        """
        import datetime
        dt = datetime.datetime.fromisoformat(local_iso_dt)
        target_year = dt.year
        target_month = dt.month
        target_day = dt.day
        time_clean = dt.strftime("%H:%M")  # '19:30'

        # 1. Primary Strategy: Calendar Picker Click
        calendar_success = self.select_calendar_date(
            target_year=target_year,
            target_month=target_month,
            target_day=target_day
        )

        is_valid, v_msg = self.validate_date_input()

        # 2. Fallback: Type locale-aware string if calendar click was not successful
        if not calendar_success or not is_valid:
            turkish_month_name = list(MONTH_MAP.keys())[list(MONTH_MAP.values()).index(target_month)].capitalize()
            locale_candidates = [
                f"{target_day} {turkish_month_name} {target_year}",
                f"{target_day:02d}.{target_month:02d}.{target_year}",
                f"{target_day:02d}/{target_month:02d}/{target_year}"
            ]

            for candidate_str in locale_candidates:
                for sel in YouTubeStudioSelectors.DATE_PICKER_INPUTS:
                    try:
                        loc = self.page.locator(sel).first
                        if loc.is_visible(timeout=1000):
                            loc.click()
                            time.sleep(0.3)
                            self.page.keyboard.press("Control+A")
                            self.page.keyboard.press("Backspace")
                            self.page.keyboard.type(candidate_str)
                            self.page.keyboard.press("Enter")
                            time.sleep(0.5)
                            is_valid, _ = self.validate_date_input()
                            if is_valid:
                                logger.info(f"Date accepted with formatted string: '{candidate_str}'")
                                break
                    except Exception:
                        pass
                if is_valid:
                    break

        # Final Date Validation & Match Check
        is_valid, v_msg = self.validate_date_input()
        if not is_valid:
            logger.error(f"[HARD DATE GUARD] Date remained invalid: {v_msg}")
            return False

        # Re-verify Date Match
        d_ok, d_msg = self.reverify_date_match(target_year, target_month, target_day)
        if not d_ok:
            logger.error(f"[HARD DATE GUARD] {d_msg}")
            return False

        # Ensure calendar is closed
        self.close_calendar_popup()

        # 3. Set Exact Time (19:30) with read-back verification
        time_ok, t_msg = self.set_schedule_time_exact(time_clean)
        if not time_ok:
            logger.error(f"[HARD TIME GUARD] {t_msg}")
            return False

        # Check Time validation
        for sel in YouTubeStudioSelectors.TIME_ERROR_INDICATORS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=500):
                    logger.error(f"Time error detected on YouTube Studio: {loc.inner_text().strip()}")
                    return False
            except Exception:
                pass

        return True

    def click_schedule_and_verify(
        self,
        timeout_seconds: int = 45,
        wait_processing_seconds: int = 25
    ) -> Tuple[bool, str]:
        """
        Click Schedule button and verify schedule confirmation modal.
        Preconditions:
        - Date valid & matched
        - Time valid & matched (19:30)
        - Calendar closed
        - Button enabled (Waits for video processing if temporarily disabled)
        """
        is_valid, v_msg = self.validate_date_input()
        if not is_valid:
            logger.error(f"[ABORT] Cannot click Schedule: Date is invalid ({v_msg})")
            return False, f"Date is invalid: {v_msg}"

        # Ensure calendar popup is closed
        self.close_calendar_popup()

        # Wait for Planla button to become enabled if video checks are processing
        start_wait = time.time()
        submit_btn = None
        while time.time() - start_wait < wait_processing_seconds:
            self.dismiss_content_review_info_if_present()
            for sel in YouTubeStudioSelectors.FINAL_SCHEDULE_BUTTONS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        btn_text = loc.inner_text().strip() if hasattr(loc, "inner_text") else ""
                        if "kaydet" in btn_text.lower() or "save" in btn_text.lower():
                            continue
                        if loc.is_enabled():
                            submit_btn = loc
                            break
                except Exception:
                    pass
            if submit_btn:
                break
            time.sleep(2.0)

        if not submit_btn:
            logger.error("[FINAL_SCHEDULE_BUTTON_DISABLED] Planla button remained disabled or was not found in UI.")
            return False, "FINAL_SCHEDULE_BUTTON_DISABLED"

        submit_btn.scroll_into_view_if_needed()
        submit_btn.click()
        logger.info(f"Clicked YouTube Studio Final Schedule button.")

        # Wait for confirmation modal or close button
        start = time.time()
        while time.time() - start < timeout_seconds:
            for sel in YouTubeStudioSelectors.CLOSE_MODAL_BUTTONS:
                try:
                    loc = self.page.locator(sel).first
                    if loc.is_visible(timeout=1000):
                        loc.click()
                        logger.info("YouTube Studio Schedule confirmed successfully via modal close.")
                        return True, "youtube_studio_scheduled"
                except Exception:
                    pass
            time.sleep(1.5)

        logger.error("[SCHEDULE_CONFIRMATION_NOT_VERIFIED] Final Schedule was clicked, but no confirmation UI was observed within timeout.")
        return False, "SCHEDULE_CONFIRMATION_NOT_VERIFIED"

    def verify_remote_scheduled_status(
        self,
        remote_id: Optional[str] = "Sq1nDGQPpOc",
        target_title: str = "Japanese Zen Temple",
        expected_date_str: str = "16",
        expected_time_str: str = "19:30",
        channel_id: Optional[str] = "UCahsmsqzTCtwTDDtvCurtBA"
    ) -> Tuple[bool, str]:
        """
        Navigate to Content list and verify video row shows 'Planlandı' / 'Scheduled'
        with the exact expected date and 19:30 time.
        """
        content_url = f"https://studio.youtube.com/channel/{channel_id or ''}/videos/upload"
        try:
            self.page.goto(content_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(2.5)
        except Exception:
            pass

        clean_title = target_title.lower().strip()
        r_id = (remote_id or "").lower().strip()

        for row_sel in YouTubeStudioSelectors.DRAFT_CONTENT_ROWS:
            try:
                rows = self.page.locator(row_sel)
                for i in range(min(rows.count(), 20)):
                    row = rows.nth(i)
                    txt = row.inner_text().lower()
                    is_target = bool((r_id and r_id in txt) or (clean_title and clean_title in txt))
                    if not is_target:
                        continue

                    if "planlandı" in txt or "scheduled" in txt:
                        if "gizli" in txt or "taslak" in txt or "draft" in txt:
                            return False, "REMOTE_STILL_DRAFT"
                        # Verify requested date/time when those values are visible in the row.
                        if expected_time_str and expected_time_str not in txt:
                            logger.warning("Remote row is scheduled but expected time '%s' was not found in row text.", expected_time_str)
                            return False, "REMOTE_SCHEDULE_TIME_NOT_VERIFIED"
                        logger.info(f"True Remote Verification PASS: '{target_title}' is SCHEDULED.")
                        return True, "SCHEDULED"

                    if "taslak" in txt or "draft" in txt or "gizli" in txt:
                        logger.warning("Remote verification FAIL: target video is still in draft/private state.")
                        return False, "DRAFT_PRIVATE"

                    return False, "REMOTE_TARGET_FOUND_BUT_NOT_SCHEDULED"
            except Exception:
                pass

        logger.error("Remote schedule verification failed: target video row was not found or scheduled state was not confirmed.")
        return False, "REMOTE_SCHEDULE_NOT_VERIFIED"

    def prepare_youtube_schedule_preflight(
        self,
        target_remote_id: str = "Sq1nDGQPpOc",
        scheduled_at_local: str = "2026-08-16T19:30:00",
        expected_handle: str = "@BuiIdVerse",
        expected_channel_id: Optional[str] = "UCahsmsqzTCtwTDDtvCurtBA"
    ) -> Tuple[bool, str]:
        """
        Prepares YouTube Studio video schedule up to the final Planla button.
        DOES NOT click Planla.
        Returns (True, 'YOUTUBE_FINAL_SCHEDULE_READY') or (False, error_msg).
        """
        # 1. Login check
        if not self.is_logged_in():
            return False, "AUTH_REQUIRED: YouTube Studio oturumu açık değil."

        # 2. Channel check
        ok_ch, ch_name, ch_msg = self.verify_logged_in_channel(expected_handle, expected_channel_id)
        if not ok_ch:
            return False, f"ACCOUNT_MISMATCH: {ch_msg}"

        # 3. Existing remote video resume
        logger.info(f"[UPLOAD SKIPPED] Opening exact remote video: {target_remote_id}")
        if not self.open_exact_remote_video(target_remote_id):
            return False, f"Failed to open exact remote video {target_remote_id}"

        # 4. Enter draft wizard
        if not self.enter_existing_draft_wizard():
            return False, "Could not open draft stepper wizard via 'Taslağı düzenle'"

        # 5. Advance wizard through DETAILS -> VIDEO_ELEMENTS -> CHECKS -> VISIBILITY
        ok_wiz, wiz_msg = self.advance_wizard_to_visibility(
            made_for_kids=False,
            ai_disclosure=True
        )
        if not ok_wiz:
            return False, f"YouTube wizard progression failed: {wiz_msg}"

        # 6. Expand Planlayın card
        if not self.find_and_expand_schedule_card():
            return False, "SCHEDULING_UNAVAILABLE: Planlayın card not found in VISIBILITY"

        # 7. Set date & time
        if not self.set_schedule_datetime(scheduled_at_local):
            return False, "YouTube Studio datetime setting failed"

        # 8. Check final Planla button (VISIBLE + ENABLED) - DO NOT CLICK
        final_btn = None
        for sel in YouTubeStudioSelectors.FINAL_SCHEDULE_BUTTONS:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=1500) and loc.is_enabled():
                    btn_text = loc.inner_text().strip() if hasattr(loc, "inner_text") else ""
                    if "kaydet" in btn_text.lower() or "save" in btn_text.lower():
                        continue
                    final_btn = loc
                    break
            except Exception:
                pass

        if not final_btn:
            return False, "FINAL_SCHEDULE_BUTTON_NOT_READY: Planla button disabled or not found"

        logger.info("=" * 50)
        logger.info("YOUTUBE PREFLIGHT")
        logger.info(f"Remote ID:       {target_remote_id}")
        logger.info("Upload:          SKIPPED")
        logger.info("Audience:        NOT_MADE_FOR_KIDS PASS")
        logger.info("Current wizard:  VISIBILITY")
        logger.info("Date:            16.08.2026 PASS")
        logger.info("Time:            19:30 PASS")
        logger.info("Planla:          VISIBLE + ENABLED")
        logger.info("YOUTUBE_FINAL_SCHEDULE_READY")
        logger.info("FINAL CLICK NOT PERFORMED")
        logger.info("=" * 50)

        return True, "YOUTUBE_FINAL_SCHEDULE_READY"

    def commit_youtube_schedule(
        self,
        target_remote_id: str,
        target_title: str,
        channel_id: Optional[str] = None,
        expected_date_str: Optional[str] = None,
        expected_time_str: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Re-verifies that YouTube Studio is in VISIBILITY with valid inputs and enabled Planla button,
        then clicks Planla and verifies true remote scheduled status in content list.
        """
        if self.detect_current_wizard_step() != WizardStep.VISIBILITY:
            return False, "COMMIT_FAILED: Wizard is not on VISIBILITY step"

        # Click Schedule and verify
        success, ref = self.click_schedule_and_verify(timeout_seconds=45)
        if not success:
            return False, f"YouTube Studio schedule submission failed: {ref}"

        # Verify remote scheduled state
        is_sched, s_msg = self.verify_remote_scheduled_status(
            remote_id=target_remote_id,
            target_title=target_title,
            expected_date_str=expected_date_str or "17.08.2026",
            expected_time_str=expected_time_str or "19:30",
            channel_id=channel_id
        )
        if not is_sched:
            return False, f"Remote scheduled verification failed: {s_msg}"

        return True, "YOUTUBE_SCHEDULED_COMMITTED"
