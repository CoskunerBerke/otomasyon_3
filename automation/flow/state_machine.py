"""
Deterministic Flow Generation State Machine and Decision Engine.
Guarantees at most ONE duration follow-up response, prevents infinite chat spam,
strictly excludes stale baseline video artifacts, and associates generations with active sessions.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Set

from .chat_classifier import AgentMessageType
from .ui_observer import FlowUISnapshot

class GenerationLifecycleState(Enum):
    PROMPT_READY = "prompt_ready"
    PROMPT_SUBMITTED = "prompt_submitted"
    AGENT_PROCESSING = "agent_processing"
    OPTIONAL_DURATION_FOLLOWUP = "optional_duration_followup"
    MEDIA_GENERATION_STARTED = "media_generation_started"
    MEDIA_GENERATING = "media_generating"
    MEDIA_READY = "media_ready"
    DOWNLOADING = "downloading"
    VALIDATING = "validating"
    READY = "ready"
    FAILED = "failed"

class FlowDecisionAction(Enum):
    WAIT = "wait"
    ANSWER_DURATION_ONCE = "answer_duration_once"
    START_MEDIA_GENERATION = "start_media_generation"
    MARK_MEDIA_READY = "mark_media_ready"
    DOWNLOAD_MEDIA = "download_media"
    RECOVER_DOWNLOAD_UI = "recover_download_ui"
    USER_ACTION_REQUIRED = "user_action_required"
    FAIL_SAFE = "fail_safe"

@dataclass
class GenerationSession:
    """Tracks active generation context per Reel."""
    reel_id: str
    flow_project_url: str = ""
    prompt_hash: str = ""
    baseline_artifact_fingerprints: Set[str] = field(default_factory=set)
    submit_attempted: bool = False
    new_artifact_fingerprint: Optional[str] = None

class FlowDecisionEngine:
    """Evaluates Flow UI snapshots against current lifecycle state and active session."""

    MAX_AUTOMATIC_CHAT_REPLIES_PER_REEL = 2

    def __init__(self, initial_state: GenerationLifecycleState = GenerationLifecycleState.PROMPT_SUBMITTED):
        self.state = initial_state
        self.duration_followup_answered: bool = False
        self.automatic_chat_replies_count: int = 1

    def decide_next_action(
        self,
        snapshot: FlowUISnapshot,
        session: Optional[GenerationSession] = None
    ) -> FlowDecisionAction:
        """
        Evaluate snapshot and active session to return the single deterministic action to take.
        Prevents stale/baseline artifacts from being downloaded for new reels.
        """
        # If prompt was not yet submitted for this session, NEVER download existing stale artifacts!
        if session and not session.submit_attempted:
            return FlowDecisionAction.START_MEDIA_GENERATION

        # CASE 1: Video download button is directly visible (only for newly detected artifact or confirmed ready)
        if snapshot.download_button_visible and (snapshot.new_video_artifact_detected or self.state == GenerationLifecycleState.MEDIA_GENERATING):
            self.state = GenerationLifecycleState.MEDIA_READY
            return FlowDecisionAction.DOWNLOAD_MEDIA

        # CASE 2: Newly appeared video artifact detected on canvas / list
        if snapshot.new_video_artifact_detected:
            if not snapshot.stop_button_visible:
                self.state = GenerationLifecycleState.MEDIA_READY
                if session:
                    session.new_artifact_fingerprint = snapshot.new_artifact_fingerprint
                return FlowDecisionAction.RECOVER_DOWNLOAD_UI

        # CASE 3: Agent explicitly signaled media ready
        if snapshot.latest_agent_message_type == AgentMessageType.MEDIA_READY_MESSAGE:
            if not snapshot.stop_button_visible:
                self.state = GenerationLifecycleState.MEDIA_READY
                return FlowDecisionAction.RECOVER_DOWNLOAD_UI

        # CASE 4: Active generation in progress (stop button visible)
        if snapshot.stop_button_visible:
            self.state = GenerationLifecycleState.MEDIA_GENERATING
            return FlowDecisionAction.WAIT

        # CASE 5: Agent progress message
        if snapshot.latest_agent_message_type == AgentMessageType.GENERATION_PROGRESS:
            self.state = GenerationLifecycleState.MEDIA_GENERATING
            return FlowDecisionAction.WAIT

        # CASE 6: Real duration follow-up question (Allowed ONLY ONCE before generation starts)
        if snapshot.latest_agent_message_type == AgentMessageType.DURATION_QUESTION:
            if self.duration_followup_answered:
                return FlowDecisionAction.WAIT

            if self.state in [
                GenerationLifecycleState.MEDIA_GENERATION_STARTED,
                GenerationLifecycleState.MEDIA_GENERATING,
                GenerationLifecycleState.MEDIA_READY,
                GenerationLifecycleState.DOWNLOADING
            ]:
                return FlowDecisionAction.WAIT

            if self.automatic_chat_replies_count >= self.MAX_AUTOMATIC_CHAT_REPLIES_PER_REEL:
                return FlowDecisionAction.USER_ACTION_REQUIRED

            self.duration_followup_answered = True
            self.automatic_chat_replies_count += 1
            self.state = GenerationLifecycleState.MEDIA_GENERATION_STARTED
            return FlowDecisionAction.ANSWER_DURATION_ONCE

        # CASE 7: Agent Error
        if snapshot.latest_agent_message_type == AgentMessageType.ERROR:
            self.state = GenerationLifecycleState.FAILED
            return FlowDecisionAction.USER_ACTION_REQUIRED

        # Default fallback: wait
        return FlowDecisionAction.WAIT
