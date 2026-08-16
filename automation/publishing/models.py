"""
Data models and Enums for Publishing Agent V1 (YouTube Shorts + TikTok Studio).
"""
from dataclasses import dataclass, field
from enum import Enum
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

class Platform(str, Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    INSTAGRAM = "instagram"

class PlatformPublicationStatus(str, Enum):
    PENDING = "PENDING"
    METADATA_READY = "METADATA_READY"
    DRY_RUN = "DRY_RUN"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    ACCOUNT_VERIFICATION_REQUIRED = "ACCOUNT_VERIFICATION_REQUIRED"
    ACCOUNT_VERIFIED = "ACCOUNT_VERIFIED"
    ACCOUNT_MISMATCH = "ACCOUNT_MISMATCH"
    READY_TO_UPLOAD = "READY_TO_UPLOAD"
    UPLOADING = "UPLOADING"
    UPLOAD_COMPLETE = "UPLOAD_COMPLETE"
    SCHEDULING = "SCHEDULING"
    SCHEDULED = "SCHEDULED"
    PROCESSING = "PROCESSING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    SCHEDULING_UNAVAILABLE = "SCHEDULING_UNAVAILABLE"
    UPLOADED_DRAFT = "UPLOADED_DRAFT"
    SCHEDULE_RESUME_REQUIRED = "SCHEDULE_RESUME_REQUIRED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"

@dataclass
class PublishRecord:
    """Represents a publication record for a single platform."""
    publish_id: str
    batch_id: str
    reel_id: str
    platform: Platform
    video_file: Path
    video_sha256: str
    title: str
    description: str
    hashtags: List[str]
    scheduled_at_local: str
    scheduled_at_utc: str
    account_handle: str = ""
    timezone: str = "Europe/Istanbul"
    status: PlatformPublicationStatus = PlatformPublicationStatus.PENDING
    remote_id: Optional[str] = None
    remote_url: Optional[str] = None
    upload_started: bool = False
    remote_draft_exists: bool = False
    dry_run: bool = False
    attempt_count: int = 0
    last_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    ai_generated: bool = True
    synthetic_media_disclosed: bool = True
    # Schedule verification evidence
    schedule_verified: bool = False
    verified_schedule_date: Optional[str] = None
    verified_schedule_time: Optional[str] = None
    verified_remote_status: Optional[str] = None
    verified_at: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.platform, str):
            self.platform = Platform(self.platform)
        if isinstance(self.status, str):
            self.status = PlatformPublicationStatus(self.status)
        if isinstance(self.video_file, str):
            self.video_file = Path(self.video_file)

    def mark_scheduled(self, remote_id: Optional[str] = None, remote_url: Optional[str] = None,
                       verified_date: Optional[str] = None, verified_time: Optional[str] = None) -> None:
        self.status = PlatformPublicationStatus.SCHEDULED
        if remote_id:
            self.remote_id = remote_id
        if remote_url:
            self.remote_url = remote_url
        self.dry_run = False
        self.schedule_verified = True
        self.verified_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if verified_date:
            self.verified_schedule_date = verified_date
        if verified_time:
            self.verified_schedule_time = verified_time
        self.verified_remote_status = "SCHEDULED"
        self.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def mark_dry_run(self) -> None:
        self.status = PlatformPublicationStatus.METADATA_READY
        self.remote_id = None
        self.remote_url = None
        self.dry_run = True
        self.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def mark_failed(self, error_message: str, status: PlatformPublicationStatus = PlatformPublicationStatus.FAILED) -> None:
        self.status = status
        self.last_error = error_message
        self.attempt_count += 1
        self.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "publish_id": self.publish_id,
            "batch_id": self.batch_id,
            "reel_id": self.reel_id,
            "platform": self.platform.value,
            "account_handle": self.account_handle,
            "video_file": str(self.video_file),
            "video_sha256": self.video_sha256,
            "title": self.title,
            "description": self.description,
            "hashtags": self.hashtags,
            "scheduled_at_local": self.scheduled_at_local,
            "scheduled_at_utc": self.scheduled_at_utc,
            "timezone": self.timezone,
            "status": self.status.value,
            "remote_id": self.remote_id,
            "remote_url": self.remote_url,
            "upload_started": self.upload_started,
            "remote_draft_exists": self.remote_draft_exists,
            "dry_run": self.dry_run,
            "attempt_count": self.attempt_count,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ai_generated": self.ai_generated,
            "synthetic_media_disclosed": self.synthetic_media_disclosed,
            "schedule_verified": self.schedule_verified,
            "verified_schedule_date": self.verified_schedule_date,
            "verified_schedule_time": self.verified_schedule_time,
            "verified_remote_status": self.verified_remote_status,
            "verified_at": self.verified_at
        }

@dataclass
class PublishingBatch:
    """Represents a scheduled publishing batch run."""
    batch_id: str
    start_date: str
    timezone: str
    slots: List[str]
    requested_reels: List[str] = field(default_factory=list)
    records: List[PublishRecord] = field(default_factory=list)
    schedule_slots: List[tuple] = field(default_factory=list)
    status: str = "PENDING"
    started_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    finished_at: Optional[str] = None

# Backward compatibility alias
PublishBatch = PublishingBatch
