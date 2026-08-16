"""
Data models and Enums for the Cloud Control Plane, Database, and Telegram Bot.
"""
from dataclasses import dataclass, field
from enum import Enum
import datetime
from typing import Optional, Dict, Any, List


class CloudWeekStatus(str, Enum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    WAITING_FOR_LOCAL_WORKER = "WAITING_FOR_LOCAL_WORKER"
    GENERATING = "GENERATING"
    READY = "READY"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class TelegramApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class CommandType(str, Enum):
    GENERATE_WEEK = "GENERATE_WEEK"
    SYNC_STATE = "SYNC_STATE"
    RECONCILE = "RECONCILE"
    UPLOAD_MEDIA = "UPLOAD_MEDIA"


class CommandStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FATAL = "FAILED_FATAL"


class InstagramJobStatus(str, Enum):
    QUEUED = "QUEUED"
    WAITING_FOR_MEDIA = "WAITING_FOR_MEDIA"
    MEDIA_UPLOADING = "MEDIA_UPLOADING"
    MEDIA_READY = "MEDIA_READY"
    PREPARING = "PREPARING"
    UPLOADING_TO_META = "UPLOADING_TO_META"
    PROCESSING = "PROCESSING"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    REMOTE_VERIFIED = "REMOTE_VERIFIED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FATAL = "FAILED_FATAL"


@dataclass
class CloudWeek:
    """Represents a 7-day publishing cycle in the cloud control plane."""
    week_id: str
    start_date: str
    end_date: str
    timezone: str = "Europe/Istanbul"
    status: CloudWeekStatus = CloudWeekStatus.PLANNED
    target_reels: int = 14
    approval_status: str = "PENDING"
    approval_sent_at: Optional[str] = None
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "week_id": self.week_id,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "timezone": self.timezone,
            "status": self.status.value if isinstance(self.status, CloudWeekStatus) else str(self.status),
            "target_reels": self.target_reels,
            "approval_status": self.approval_status,
            "approval_sent_at": self.approval_sent_at,
            "approved_at": self.approved_at,
            "rejected_at": self.rejected_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class TelegramApproval:
    """Tracks a Telegram approval message and interactive inline keyboard response."""
    approval_id: str
    week_id: str
    next_week_id: str
    status: TelegramApprovalStatus = TelegramApprovalStatus.PENDING
    telegram_message_id: Optional[int] = None
    telegram_chat_id: Optional[int] = None
    token: Optional[str] = None
    expires_at: Optional[str] = None
    responded_at: Optional[str] = None
    response: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "week_id": self.week_id,
            "next_week_id": self.next_week_id,
            "status": self.status.value if isinstance(self.status, TelegramApprovalStatus) else str(self.status),
            "telegram_message_id": self.telegram_message_id,
            "telegram_chat_id": self.telegram_chat_id,
            "token": self.token,
            "expires_at": self.expires_at,
            "responded_at": self.responded_at,
            "response": self.response,
            "created_at": self.created_at
        }


@dataclass
class LocalWorkerCommand:
    """Command queue item dispatched from Cloud to Local Windows Worker."""
    command_id: str
    type: CommandType
    week_id: str
    status: CommandStatus = CommandStatus.PENDING
    payload: Dict[str, Any] = field(default_factory=dict)
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    completed_at: Optional[str] = None
    attempt_count: int = 0
    last_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "type": self.type.value if isinstance(self.type, CommandType) else str(self.type),
            "week_id": self.week_id,
            "status": self.status.value if isinstance(self.status, CommandStatus) else str(self.status),
            "payload": self.payload,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at,
            "completed_at": self.completed_at,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "created_at": self.created_at
        }


@dataclass
class InstagramScheduledJob:
    """Always-on cloud publishing job for an individual Instagram Reel."""
    job_id: str
    week_id: str
    reel_id: str
    scheduled_at_local: str
    scheduled_at_utc: str
    timezone: str = "Europe/Istanbul"
    media_object_key: Optional[str] = None
    media_sha256: Optional[str] = None
    caption: str = ""
    status: InstagramJobStatus = InstagramJobStatus.QUEUED
    attempt_count: int = 0
    claimed_by: Optional[str] = None
    claimed_at: Optional[str] = None
    lease_expires_at: Optional[str] = None
    container_id: Optional[str] = None
    remote_media_id: Optional[str] = None
    permalink: Optional[str] = None
    published_at: Optional[str] = None
    last_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "week_id": self.week_id,
            "reel_id": self.reel_id,
            "scheduled_at_local": self.scheduled_at_local,
            "scheduled_at_utc": self.scheduled_at_utc,
            "timezone": self.timezone,
            "media_object_key": self.media_object_key,
            "media_sha256": self.media_sha256,
            "caption": self.caption,
            "status": self.status.value if isinstance(self.status, InstagramJobStatus) else str(self.status),
            "attempt_count": self.attempt_count,
            "claimed_by": self.claimed_by,
            "claimed_at": self.claimed_at,
            "lease_expires_at": self.lease_expires_at,
            "container_id": self.container_id,
            "remote_media_id": self.remote_media_id,
            "permalink": self.permalink,
            "published_at": self.published_at,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class WorkerHeartbeat:
    """Records health and online presence of the local worker."""
    worker_id: str
    hostname_hash: str
    version: str
    capabilities: List[str] = field(default_factory=list)
    last_seen_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "hostname_hash": self.hostname_hash,
            "version": self.version,
            "capabilities": self.capabilities,
            "last_seen_at": self.last_seen_at
        }


@dataclass
class NotificationLog:
    """Prevents duplicate Telegram notifications."""
    notification_id: str
    notification_type: str
    recipient: str
    payload_hash: str
    sent_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "notification_type": self.notification_type,
            "recipient": self.recipient,
            "payload_hash": self.payload_hash,
            "sent_at": self.sent_at
        }
