"""
Page Object Model for Google Flow interface.
Implements one-project-per-reel navigation, baseline artifact fingerprinting,
Agent settings configuration (Never approve, 9:16, Omni Flash, Nano Banana 2),
Slate.js prompt filling with duration sanitization, Generate button resolution,
fast-skip for disabled download buttons, and self-recovery UI observer-driven state machine.
"""
import time
import re
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
from playwright.sync_api import Page, Locator, TimeoutError as PlaywrightTimeoutError

from .selectors import (
    FlowSelectors,
    FlowPageState,
    FlowError,
    FlowUIChangedError,
    UserActionRequiredError,
    InsufficientCreditsError,
    GenerationTimeoutError,
    RealGenerationDisabled,
    GenerationStateUncertain
)
from .downloader import FlowDownloader
from .ui_observer import FlowUIObserver, FlowUISnapshot
from .state_machine import FlowDecisionEngine, FlowDecisionAction, GenerationLifecycleState, GenerationSession
from ..content.duration_rules import sanitize_video_duration, DEFAULT_VIDEO_DURATION

class FlowPage:
    """Page Object for navigating and interacting with Google Flow."""

    def __init__(self, page: Page, screenshots_dir: Path, downloads_dir: Path):
        self.page = page
        self.screenshots_dir = Path(screenshots_dir).resolve()
        self.downloader = FlowDownloader(downloads_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._submit_attempted = False
        self.observer = FlowUIObserver(self.page)
        self.decision_engine = FlowDecisionEngine()

    def capture_error_snapshot(self, tag: str) -> Path:
        """Capture screenshot, HTML dump, and DOM diagnostics for debugging UI issues."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_file = self.screenshots_dir / f"error_{tag}_{timestamp}.png"
        html_file = self.screenshots_dir / f"error_{tag}_{timestamp}.html"
        diag_file = self.screenshots_dir / f"error_{tag}_{timestamp}_diag.txt"

        try:
            self.page.screenshot(path=str(screenshot_file), full_page=True)
            html_content = self.page.content()
            html_file.write_text(html_content, encoding="utf-8", errors="ignore")

            btn_count = len(self.page.locator("button").all())
            ta_count = len(self.page.locator("textarea").all())
            ce_count = len(self.page.locator("[contenteditable='true']").all())
            tb_count = len(self.page.locator("[role='textbox']").all())

            diag_text = (
                f"URL: {self.page.url}\n"
                f"Title: {self.page.title()}\n"
                f"Buttons: {btn_count}\n"
                f"Textareas: {ta_count}\n"
                f"ContentEditables: {ce_count}\n"
                f"Role Textboxes: {tb_count}\n"
            )
            diag_file.write_text(diag_text, encoding="utf-8")
        except Exception:
            pass
        return screenshot_file

    def find_first_visible(self, selectors: list, timeout_ms: int = 1500) -> Optional[Locator]:
        """Iterate through selector list and return first visible element."""
        for sel in selectors:
            try:
                loc = self.page.locator(sel).first
                if loc.is_visible(timeout=timeout_ms):
                    return loc
            except Exception:
                continue
        return None

    def check_auth_and_security(self) -> None:
        """
        Check if Google Login, CAPTCHA, or verification is currently blocking the view.
        """
        current_url = self.page.url.lower()
        if "accounts.google.com" in current_url or "signin" in current_url:
            self.capture_error_snapshot("auth_required")
            raise UserActionRequiredError("Google hesabı girişi gerekiyor. Lütfen açık Chrome penceresinde Google hesabınıza giriş yapın.")

        for auth_sel in FlowSelectors.AUTH_CHALLENGE_PATTERNS:
            try:
                loc = self.page.locator(auth_sel).first
                if loc.is_visible(timeout=800):
                    self.capture_error_snapshot("security_challenge")
                    raise UserActionRequiredError(f"Güvenlik doğrulaması / CAPTCHA tespit edildi ({auth_sel}).")
            except UserActionRequiredError:
                raise
            except Exception:
                continue

    def check_credit_warnings(self) -> None:
        """Check for credit depletion or quota limit messages."""
        for cred_sel in FlowSelectors.CREDIT_WARNING_SELECTORS:
            try:
                loc = self.page.locator(cred_sel).first
                if loc.is_visible(timeout=800):
                    self.capture_error_snapshot("out_of_credits")
                    raise InsufficientCreditsError("Google Flow kredileriniz tükendi veya kota aşıldı.")
            except InsufficientCreditsError:
                raise
            except Exception:
                continue

    def open(self, flow_url: str) -> None:
        """Open or navigate to Google Flow web application."""
        current_url = self.page.url
        if "flow" not in current_url.lower():
            try:
                self.page.goto(flow_url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass

        self.check_auth_and_security()

    def detect_page_state(self) -> FlowPageState:
        """Detect whether Flow is on the Home page or inside the Project Editor."""
        self.check_auth_and_security()

        current_url = self.page.url.lower()
        if "/project/" in current_url:
            return FlowPageState.PROJECT_EDITOR

        prompt_input = self.find_first_visible(FlowSelectors.PROMPT_INPUT_SELECTORS, timeout_ms=1000)
        if prompt_input:
            return FlowPageState.PROJECT_EDITOR

        new_project_btn = self.find_first_visible(FlowSelectors.NEW_PROJECT_BUTTON_SELECTORS, timeout_ms=1000)
        if new_project_btn:
            return FlowPageState.HOME

        return FlowPageState.UNKNOWN

    def ensure_project_for_reel(self, reel_id: str, flow_project_url: Optional[str] = None, timeout_seconds: int = 20) -> str:
        """
        Enforces one-project-per-reel policy.
        If flow_project_url is provided, navigates directly to it.
        Otherwise, navigates to Home, creates a brand new project, and captures the project URL.
        """
        self.check_auth_and_security()

        # CASE 1: Existing dedicated project URL provided
        if flow_project_url and "/project/" in flow_project_url.lower():
            if self.page.url != flow_project_url:
                try:
                    self.page.goto(flow_project_url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(1.5)
                except Exception:
                    pass
            self.ensure_project_editor(timeout_seconds=timeout_seconds)
            return self.page.url

        # CASE 2: Create a new dedicated project for this Reel
        current_url = self.page.url.lower()
        if "/tools/flow" not in current_url or "/project/" in current_url:
            try:
                self.page.goto("https://labs.google/fx/tools/flow", wait_until="domcontentloaded", timeout=30000)
                time.sleep(1.5)
            except Exception:
                pass

        new_btn = self.find_first_visible(FlowSelectors.NEW_PROJECT_BUTTON_SELECTORS, timeout_ms=3000)
        if not new_btn:
            if "/project/" in self.page.url:
                return self.page.url
            self.capture_error_snapshot("new_project_btn_missing")
            raise FlowUIChangedError("Google Flow 'Yeni proje' butonu bulunamadı.")

        new_btn.click()

        # Wait for new project workspace to mount
        start_wait = time.time()
        while time.time() - start_wait < timeout_seconds:
            if "/project/" in self.page.url.lower():
                prompt_input = self.find_first_visible(FlowSelectors.PROMPT_INPUT_SELECTORS, timeout_ms=1000)
                if prompt_input:
                    return self.page.url
            time.sleep(0.5)

        return self.page.url

    def ensure_project_editor(self, timeout_seconds: int = 20) -> None:
        """
        Ensure the page is inside the Flow Project Editor workspace and prompt input is visible.
        """
        current_url = self.page.url.lower()
        if "/edit/" in current_url:
            back_btn = self.page.locator("button:has(i:text-is('arrow_back')), button:has-text('Bitti')").first
            if back_btn.count() > 0 and back_btn.is_visible():
                back_btn.click()
                time.sleep(1.0)

        state = self.detect_page_state()

        if state == FlowPageState.HOME:
            new_btn = self.find_first_visible(FlowSelectors.NEW_PROJECT_BUTTON_SELECTORS)
            if not new_btn:
                self.capture_error_snapshot("new_project_btn_missing")
                raise FlowUIChangedError("Google Flow 'Yeni proje' butonu bulunamadı.")

            new_btn.click()

        start_wait = time.time()
        while time.time() - start_wait < timeout_seconds:
            prompt_input = self.find_first_visible(FlowSelectors.PROMPT_INPUT_SELECTORS, timeout_ms=1000)
            if prompt_input:
                try:
                    if prompt_input.is_visible():
                        return
                except Exception:
                    pass
            time.sleep(0.5)

        self.capture_error_snapshot("project_editor_timeout")
        raise FlowUIChangedError("Yeni proje çalışma alanı ve prompt kutusu yüklenirken zaman aşımı oluştu.")

    def resolve_settings_button(self) -> Optional[Locator]:
        """Resolve the tune/Settings button next to the prompt composer."""
        candidates = []
        for btn in self.page.locator("button").all():
            try:
                if not btn.is_visible():
                    continue
                txt = (btn.text_content() or "").strip()
                icon_loc = btn.locator("i.google-symbols, i, svg").first
                icon_txt = (icon_loc.text_content() or "").strip() if icon_loc.count() > 0 else ""
                if icon_txt == "tune" or "ayar" in txt.lower() or "setting" in txt.lower():
                    candidates.append(btn)
            except Exception:
                continue

        if candidates:
            return candidates[-1]

        fallback = self.find_first_visible(FlowSelectors.SETTINGS_BUTTON_SELECTORS, timeout_ms=1000)
        return fallback

    def configure_agent_settings(
        self,
        approval_mode: str = "never",
        video_ratio: str = "9:16",
        video_outputs: int = 1,
        video_model: str = "Omni Flash",
        image_ratio: str = "9:16",
        image_outputs: int = 2,
        image_model: str = "Nano Banana 2",
        target_duration: int = DEFAULT_VIDEO_DURATION
    ) -> None:
        """
        Open Agent settings dialog, configure approval=Never, ratios, output counts, models,
        and click Save to persist.
        """
        self.ensure_project_editor()
        settings_btn = self.resolve_settings_button()
        if not settings_btn:
            self.capture_error_snapshot("settings_btn_missing")
            raise FlowUIChangedError("Google Flow 'Ayarlar / Settings' butonu bulunamadı.")

        settings_btn.click()
        time.sleep(1.0)

        # 1. Configure Approval: Never (AUTO_APPROVE)
        if approval_mode.lower() == "never":
            never_radio = self.find_first_visible(FlowSelectors.APPROVAL_NEVER_SELECTORS, timeout_ms=2000)
            if never_radio:
                try:
                    never_radio.click()
                    time.sleep(0.3)
                except Exception:
                    pass

        # 2. Select 9:16 aspect ratios for both Image & Video
        for r_btn in self.page.locator("button:has-text('9:16')").all():
            try:
                if r_btn.is_visible():
                    r_btn.click()
                    time.sleep(0.2)
            except Exception:
                pass

        # 3. Output counts: Image x2, Video x1
        x1_buttons = self.page.locator("button:has-text('x1')").all()
        x2_buttons = self.page.locator("button:has-text('x2')").all()
        if x2_buttons and x2_buttons[0].is_visible():
            try:
                x2_buttons[0].click()
                time.sleep(0.2)
            except Exception:
                pass
        if len(x1_buttons) >= 2 and x1_buttons[1].is_visible():
            try:
                x1_buttons[1].click()
                time.sleep(0.2)
            except Exception:
                pass

        # 4. Save Settings
        save_btn = self.find_first_visible(FlowSelectors.SAVE_SETTINGS_BUTTON_SELECTORS, timeout_ms=2000)
        if not save_btn:
            self.capture_error_snapshot("save_settings_btn_missing")
            raise FlowUIChangedError("FLOW_SETTINGS_SAVE_FAILED: Ayarlar 'Kaydet / Save' butonu bulunamadı.")

        save_btn.click()
        time.sleep(1.0)

        print("Flow Agent Settings:")
        print(f"Approval before generation: {approval_mode.upper()}")
        print(f"Image ratio: {image_ratio}")
        print(f"Image outputs: x{image_outputs}")
        print(f"Image model: {image_model}")
        print(f"Video ratio: {video_ratio}")
        print(f"Video outputs: x{video_outputs}")
        print(f"Video model: {video_model}")
        print(f"Video duration target: {target_duration}s")
        print("SETTINGS VERIFIED\n")

    def enter_prompt(self, prompt_text: str, target_duration: int = DEFAULT_VIDEO_DURATION) -> None:
        """
        Write sanitized prompt text into the Slate.js generation input field
        and verify that the text was successfully written into the DOM.
        """
        self.ensure_project_editor()

        sanitized_prompt = sanitize_video_duration(prompt_text, target_duration=target_duration)

        prompt_input = self.find_first_visible(FlowSelectors.PROMPT_INPUT_SELECTORS, timeout_ms=3000)
        if not prompt_input:
            self.capture_error_snapshot("prompt_input_missing")
            raise FlowUIChangedError("Google Flow prompt giriş alanı bulunamadı. Lütfen selectors.py dosyasını kontrol edin.")

        prompt_input.click()
        time.sleep(0.3)

        prompt_input.fill("")
        time.sleep(0.2)

        prompt_input.fill(sanitized_prompt)
        time.sleep(0.5)

        read_back = (prompt_input.text_content() or "").strip()
        first_few_words = sanitized_prompt.split()[:3]
        expected_substring = " ".join(first_few_words)

        if expected_substring not in read_back and len(read_back) < 10:
            self.capture_error_snapshot("prompt_fill_verification_failed")
            raise FlowUIChangedError(
                f"FLOW_PROMPT_FILL_FAILED: Prompt yazıldı fakat DOM üzerinde doğrulanamadı. "
                f"(Okunan: '{read_back[:40]}...')"
            )

    def resolve_generate_button(self) -> Locator:
        """Robust resolver for Google Flow 'Generate / Oluştur' button."""
        candidates = []
        for btn in self.page.locator("button").all():
            try:
                if not btn.is_visible():
                    continue

                if btn.get_attribute("aria-haspopup") == "dialog":
                    continue

                icons = btn.locator("i.google-symbols, i, svg").all()
                has_arrow_forward = False
                for ic in icons:
                    ic_text = (ic.text_content() or "").strip()
                    if ic_text == "arrow_forward":
                        has_arrow_forward = True
                        break

                btn_text = (btn.text_content() or "").lower()
                has_action_text = any(w in btn_text for w in ["oluştur", "generate", "create", "submit", "üret"])

                if has_arrow_forward or (has_action_text and btn.get_attribute("aria-disabled") is not None):
                    candidates.append(btn)
            except Exception:
                continue

        if candidates:
            for c in candidates:
                if c.get_attribute("aria-disabled") == "false":
                    return c
            return candidates[0]

        loc2 = self.page.locator("button:has(i:text-is('arrow_forward'))").first
        if loc2.count() > 0 and loc2.is_visible():
            return loc2

        fallback = self.find_first_visible(FlowSelectors.GENERATE_BUTTON_SELECTORS, timeout_ms=1000)
        if fallback:
            return fallback

        self.capture_error_snapshot("generate_button_missing")
        raise FlowUIChangedError("FLOW_GENERATE_BUTTON_NOT_FOUND: Google Flow 'Oluştur / Generate' butonu bulunamadı.")

    def resolve_enabled_download_button(self, timeout_ms: int = 1500) -> Optional[Locator]:
        """
        Find and return an enabled download button locator.
        Instantly skips disabled buttons without waiting for Playwright's 30s click timeout.
        """
        selectors = [
            "button:has(i.google-symbols:text-is('download'))",
            "button:has(i:text-is('download'))",
            "button:has-text('İndir')",
            "button:has-text('Download')"
        ]
        for sel in selectors:
            try:
                locs = self.page.locator(sel).all()
                for loc in locs:
                    if loc.is_visible(timeout=timeout_ms):
                        aria_dis = loc.get_attribute("aria-disabled")
                        if aria_dis != "true" and loc.is_enabled():
                            return loc
            except Exception:
                continue
        return None

    def trigger_generation(self, allow_real_generation: bool = True, session: Optional[GenerationSession] = None) -> None:
        """
        Click Generate with strict double-click & credit protection.
        Captures baseline artifact fingerprints BEFORE clicking.
        """
        self.check_credit_warnings()
        self.check_auth_and_security()

        state = self.detect_page_state()
        if state != FlowPageState.PROJECT_EDITOR:
            raise FlowUIChangedError(f"Generation başlatılamaz: sayfa Project Editor durumunda değil ({state.value}).")

        if self._submit_attempted:
            raise GenerationStateUncertain("ÇİFT CLICK KORUMASI: Generate butonuna zaten basılmıştı. İkinci kez tıklanmayacak.")

        # Capture baseline before clicking
        baseline_fps = self.observer.get_visible_artifact_fingerprints()
        self.observer.set_baseline_artifacts(baseline_fps)
        if session:
            session.baseline_artifact_fingerprints = baseline_fps
            session.submit_attempted = True

        if not allow_real_generation:
            raise RealGenerationDisabled("REAL_GENERATION_DISABLED: allow_real_generation=False olduğu için Generate butonuna basılmadı.")

        gen_btn = self.resolve_generate_button()
        aria_disabled = gen_btn.get_attribute("aria-disabled")
        if aria_disabled == "true":
            self.capture_error_snapshot("generate_button_disabled")
            raise FlowUIChangedError("FLOW_GENERATE_BUTTON_DISABLED: Generate butonu pasif (aria-disabled=true). Promptun dolu olduğundan emin olun.")

        self._submit_attempted = True
        self.decision_engine.state = GenerationLifecycleState.PROMPT_SUBMITTED
        gen_btn.click()
        time.sleep(2.0)

        self.check_credit_warnings()
        self.check_auth_and_security()

    def recover_and_open_video_detail(self) -> bool:
        """Self-recovery helper to open the generated video player / detail view."""
        try:
            video_link = self.page.locator("a[href*='/edit/']").first
            if video_link.count() > 0 and video_link.is_visible():
                video_link.click()
                time.sleep(1.0)
                return True

            video_elem = self.page.locator("video").first
            if video_elem.count() > 0 and video_elem.is_visible():
                video_elem.click()
                time.sleep(1.0)
                return True

            play_btn = self.page.locator("button:has(i.google-symbols:text-is('play_circle')), button:has-text('play_circle')").first
            if play_btn.count() > 0 and play_btn.is_visible():
                play_btn.click()
                time.sleep(1.0)
                return True
        except Exception:
            pass
        return False

    def wait_for_completion_and_download(
        self,
        target_filename: str,
        timeout_minutes: int = 20,
        target_duration: int = DEFAULT_VIDEO_DURATION,
        session: Optional[GenerationSession] = None
    ) -> Path:
        """
        Observer-driven deterministic polling loop.
        Guarantees at most ONE duration answer, avoids chat loops, and strictly verifies new artifacts.
        Fast-skips disabled download buttons and recovers detail view instantly.
        """
        timeout_seconds = timeout_minutes * 60
        start_time = time.time()
        last_logged_state = None

        print("[FLOW] State Machine başlatıldı (Video üretimi izleniyor)...")

        while time.time() - start_time < timeout_seconds:
            self.check_auth_and_security()
            self.check_credit_warnings()

            snapshot = self.observer.take_snapshot()
            action = self.decision_engine.decide_next_action(snapshot, session=session)

            current_state_str = self.decision_engine.state.value
            if current_state_str != last_logged_state:
                print(f"[FLOW] State: {current_state_str.upper()} | Action: {action.value.upper()}")
                last_logged_state = current_state_str

            # ACTION 1 & 2: Download or Recover Download UI
            if action in [FlowDecisionAction.DOWNLOAD_MEDIA, FlowDecisionAction.RECOVER_DOWNLOAD_UI]:
                dl_btn = self.resolve_enabled_download_button(timeout_ms=1000)
                if not dl_btn:
                    # Instantly recover detail view without waiting 30s
                    print("[FLOW] Enabled indirme butonu aranıyor -> Video detay görünümü açılıyor...")
                    self.recover_and_open_video_detail()
                    time.sleep(1.0)
                    dl_btn = self.resolve_enabled_download_button(timeout_ms=1500)

                if dl_btn:
                    print(f"[FLOW] Reel: {session.reel_id if session else target_filename}")
                    print(f"[FLOW] Project: {session.flow_project_url if session else self.page.url}")
                    print(f"[FLOW] Baseline artifacts: {len(session.baseline_artifact_fingerprints) if session else 0}")
                    print(f"[FLOW] New artifact detected: {snapshot.new_artifact_fingerprint}")
                    print(f"[FLOW] Artifact belongs to active session: YES")
                    print("[FLOW] Downloading...")
                    return self.downloader.trigger_and_save_download(
                        page=self.page,
                        download_button_locator=dl_btn,
                        target_filename=target_filename,
                        timeout_seconds=60
                    )

            # ACTION 3: Answer duration question strictly once
            elif action == FlowDecisionAction.ANSWER_DURATION_ONCE:
                print(f"[FLOW] [DURATION QUESTION DETECTED] Soru algılandı -> Tek seferlik '{target_duration} saniye' yanıtı gönderiliyor...")
                prompt_input = self.find_first_visible(FlowSelectors.PROMPT_INPUT_SELECTORS, timeout_ms=2000)
                if prompt_input:
                    prompt_input.click()
                    prompt_input.fill(f"{target_duration} saniye")
                    time.sleep(0.5)
                    gen_btn = self.resolve_generate_button()
                    gen_btn.click()
                    time.sleep(2.0)

            # ACTION 4: User Action Required
            elif action == FlowDecisionAction.USER_ACTION_REQUIRED:
                self.capture_error_snapshot("user_action_required")
                raise UserActionRequiredError("FLOW_USER_ACTION_REQUIRED: Flow arayüzünde kullanıcı müdahalesi gerekiyor.")

            time.sleep(3.0)

        self.capture_error_snapshot("generation_timeout")
        raise GenerationTimeoutError(f"Video üretimi {timeout_minutes} dakika içinde tamamlanamadı.")
