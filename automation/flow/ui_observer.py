"""
Google Flow UI Observer and DOM snapshot generator.
Captures unified, deterministic UI state including new agent messages (ignoring user bubbles),
active generation indicators (stop button), newly appeared video artifacts (fingerprint-based),
and strictly enabled download buttons.
"""
from dataclasses import dataclass, field
import hashlib
from typing import List, Set, Optional
from playwright.sync_api import Page

from .chat_classifier import classify_agent_message, AgentMessageType

@dataclass
class FlowUISnapshot:
    page_url: str
    latest_new_agent_messages: List[str] = field(default_factory=list)
    latest_agent_message_type: AgentMessageType = AgentMessageType.UNKNOWN
    stop_button_visible: bool = False
    prompt_editable: bool = True
    generate_button_visible: bool = False
    generate_button_enabled: bool = False
    video_artifact_count: int = 0
    new_video_artifact_detected: bool = False
    new_artifact_fingerprint: Optional[str] = None
    download_button_visible: bool = False
    settings_panel_open: bool = False

class FlowUIObserver:
    """Observes Flow Project Editor DOM and generates discrete, immutable UI snapshots."""

    def __init__(self, page: Page):
        self.page = page
        self.baseline_artifact_fingerprints: Set[str] = set()
        self.seen_agent_message_hashes: Set[str] = set()

    def set_baseline_artifacts(self, fingerprints: Optional[Set[str]] = None) -> None:
        """Record current artifacts on screen as baseline to avoid confusing old videos with new ones."""
        if fingerprints is not None:
            self.baseline_artifact_fingerprints = set(fingerprints)
        else:
            self.baseline_artifact_fingerprints = self.get_visible_artifact_fingerprints()

    def get_visible_artifact_fingerprints(self) -> Set[str]:
        """Extract unique fingerprints of all video elements and edit links currently in the DOM."""
        fps: Set[str] = set()
        try:
            for v in self.page.locator("video").all():
                if v.is_visible():
                    src = v.get_attribute("src") or ""
                    if src:
                        fps.add(f"video:{src}")

            for l in self.page.locator("a[href*='/edit/']").all():
                if l.is_visible():
                    href = l.get_attribute("href") or ""
                    if href:
                        fps.add(f"link:{href}")
        except Exception:
            pass
        return fps

    def count_video_artifacts(self) -> int:
        return len(self.get_visible_artifact_fingerprints())

    def extract_new_agent_messages(self) -> List[str]:
        """
        Extract only new, unseen Agent messages from chat panel.
        Explicitly excludes user bubble turns.
        """
        new_messages = []
        try:
            agent_paragraphs = self.page.locator("div[class*='sc-'] > p:not([class*='sc-e7b1103b'])").all()

            for idx, p_el in enumerate(agent_paragraphs):
                if not p_el.is_visible():
                    continue

                txt = (p_el.text_content() or "").strip()
                if not txt or len(txt) < 3:
                    continue

                if txt.lower() == "8 saniye" or txt.lower() == "8 seconds":
                    continue
                if txt.startswith("Create a mesmerizing") and "Duration:" in txt:
                    continue

                msg_hash = hashlib.md5(f"{idx}:{txt}".encode("utf-8")).hexdigest()
                if msg_hash not in self.seen_agent_message_hashes:
                    self.seen_agent_message_hashes.add(msg_hash)
                    new_messages.append(txt)
        except Exception:
            pass

        return new_messages

    def take_snapshot(self) -> FlowUISnapshot:
        """Capture a complete snapshot of current UI state."""
        url = self.page.url

        # 1. Stop button check (indicating generation is active)
        stop_btn = self.page.locator("button:has(i.google-symbols:text-is('stop')), button:has(i:text-is('stop')), button[aria-label*='Stop' i], button[aria-label*='Durdur' i]").first
        stop_visible = bool(stop_btn.count() > 0 and stop_btn.is_visible())

        # 2. Extract new agent messages
        new_msgs = self.extract_new_agent_messages()
        msg_type = AgentMessageType.UNKNOWN
        if new_msgs:
            msg_type = classify_agent_message(new_msgs[-1])

        # 3. Video artifacts with strict baseline comparison
        current_fps = self.get_visible_artifact_fingerprints()
        new_fps = current_fps - self.baseline_artifact_fingerprints
        new_video_detected = len(new_fps) > 0
        new_fp = next(iter(new_fps), None) if new_video_detected else None

        # 4. Download button visibility & enabled check (skips disabled buttons instantly)
        dl_visible = False
        try:
            dl_candidates = self.page.locator("button:has(i.google-symbols:text-is('download')), button:has(i:text-is('download')), button:has-text('İndir'), button:has-text('Download')").all()
            for btn in dl_candidates:
                if btn.is_visible() and btn.get_attribute("aria-disabled") != "true" and btn.is_enabled():
                    dl_visible = True
                    break
        except Exception:
            pass

        # 5. Generate button
        gen_btn = self.page.locator("button:has(i.google-symbols:text-is('arrow_forward')), button:has(i:text-is('arrow_forward'))").first
        gen_visible = bool(gen_btn.count() > 0 and gen_btn.is_visible())
        gen_enabled = bool(gen_visible and gen_btn.get_attribute("aria-disabled") != "true")

        # 6. Prompt editable
        prompt_input = self.page.locator("div[data-slate-editor='true'], div[role='textbox'][contenteditable='true']").first
        prompt_editable = bool(prompt_input.count() > 0 and prompt_input.is_visible())

        # 7. Settings panel open
        settings_panel = self.page.locator("[role='radiogroup'], div:has(button[role='radio'][value='AUTO_APPROVE'])").first
        settings_open = bool(settings_panel.count() > 0 and settings_panel.is_visible())

        return FlowUISnapshot(
            page_url=url,
            latest_new_agent_messages=new_msgs,
            latest_agent_message_type=msg_type,
            stop_button_visible=stop_visible,
            prompt_editable=prompt_editable,
            generate_button_visible=gen_visible,
            generate_button_enabled=gen_enabled,
            video_artifact_count=len(current_fps),
            new_video_artifact_detected=new_video_detected,
            new_artifact_fingerprint=new_fp,
            download_button_visible=dl_visible,
            settings_panel_open=settings_open
        )
