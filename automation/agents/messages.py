"""
Message model and MessageType definitions for inter-agent communication.
"""
from dataclasses import dataclass, field
from enum import Enum
import datetime
from typing import Dict, Any, Optional

class MessageType(str, Enum):
    TASK_REQUEST = "TASK_REQUEST"
    TASK_RESULT = "TASK_RESULT"
    STATUS_UPDATE = "STATUS_UPDATE"
    HISTORY_RESULT = "HISTORY_RESULT"
    CONCEPT_SELECTED = "CONCEPT_SELECTED"
    SEGMENT_PLAN_READY = "SEGMENT_PLAN_READY"
    FLOW_GENERATION_STARTED = "FLOW_GENERATION_STARTED"
    FLOW_GENERATION_PROGRESS = "FLOW_GENERATION_PROGRESS"
    SEGMENT_READY = "SEGMENT_READY"
    QC_STARTED = "QC_STARTED"
    QC_PASS = "QC_PASS"
    QC_FAIL = "QC_FAIL"
    FINAL_CONCAT_STARTED = "FINAL_CONCAT_STARTED"
    FINAL_QC_PASS = "FINAL_QC_PASS"
    FINAL_QC_FAIL = "FINAL_QC_FAIL"
    PUBLISH_READY = "PUBLISH_READY"
    PUBLISH_BATCH_STARTED = "PUBLISH_BATCH_STARTED"
    METADATA_READY = "METADATA_READY"
    YOUTUBE_UPLOAD_STARTED = "YOUTUBE_UPLOAD_STARTED"
    YOUTUBE_UPLOAD_COMPLETE = "YOUTUBE_UPLOAD_COMPLETE"
    YOUTUBE_SCHEDULED = "YOUTUBE_SCHEDULED"
    TIKTOK_UPLOAD_STARTED = "TIKTOK_UPLOAD_STARTED"
    TIKTOK_UPLOAD_COMPLETE = "TIKTOK_UPLOAD_COMPLETE"
    TIKTOK_SCHEDULED = "TIKTOK_SCHEDULED"
    PUBLISH_PLATFORM_FAILED = "PUBLISH_PLATFORM_FAILED"
    PUBLISH_BATCH_COMPLETE = "PUBLISH_BATCH_COMPLETE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    ANALYTICS_RESULT = "ANALYTICS_RESULT"
    RESUME = "RESUME"
    ERROR = "ERROR"

# Set of message types considered "meaningful" milestones that warrant dedicated graph nodes
MEANINGFUL_MESSAGE_TYPES = {
    MessageType.TASK_REQUEST,
    MessageType.HISTORY_RESULT,
    MessageType.CONCEPT_SELECTED,
    MessageType.SEGMENT_PLAN_READY,
    MessageType.FLOW_GENERATION_STARTED,
    MessageType.SEGMENT_READY,
    MessageType.QC_PASS,
    MessageType.QC_FAIL,
    MessageType.FINAL_CONCAT_STARTED,
    MessageType.FINAL_QC_PASS,
    MessageType.FINAL_QC_FAIL,
    MessageType.PUBLISH_READY,
    MessageType.PUBLISH_BATCH_STARTED,
    MessageType.METADATA_READY,
    MessageType.YOUTUBE_SCHEDULED,
    MessageType.TIKTOK_SCHEDULED,
    MessageType.PUBLISH_PLATFORM_FAILED,
    MessageType.PUBLISH_BATCH_COMPLETE,
    MessageType.AUTH_REQUIRED,
    MessageType.RESUME,
    MessageType.ERROR
}

@dataclass
class AgentMessage:
    """Structured message passed between agents and logged to Obsidian."""
    message_id: str
    run_id: str
    from_agent: str
    to_agent: str
    message_type: MessageType
    summary: str
    payload: Dict[str, Any] = field(default_factory=dict)
    reel_id: Optional[str] = None
    segment_index: Optional[int] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    is_meaningful: bool = True

    def __post_init__(self):
        if isinstance(self.message_type, str):
            try:
                self.message_type = MessageType(self.message_type)
            except Exception:
                pass
        self.is_meaningful = self.message_type in MEANINGFUL_MESSAGE_TYPES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "run_id": self.run_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "message_type": self.message_type.value if isinstance(self.message_type, MessageType) else str(self.message_type),
            "summary": self.summary,
            "payload": self.payload,
            "reel_id": self.reel_id,
            "segment_index": self.segment_index,
            "created_at": self.created_at,
            "is_meaningful": self.is_meaningful
        }
