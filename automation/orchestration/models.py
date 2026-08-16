"""
Data models and Enums for Weekly 14 Reel Orchestrator and Multi-Platform Control Center.
"""
from dataclasses import dataclass, field
from enum import Enum
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class ReelPlatformStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    READY = "READY"
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    REMOTE_VERIFIED = "REMOTE_VERIFIED"
    SKIPPED_ALREADY_DONE = "SKIPPED_ALREADY_DONE"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FATAL = "FAILED_FATAL"
    NEEDS_USER_HTML = "NEEDS_USER_HTML"
    NEEDS_USER_META_SETUP = "NEEDS_USER_META_SETUP"
    TEST_COMPLETED = "TEST_COMPLETED"


class ReconciliationStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    RETRYABLE = "RETRYABLE"
    RECONCILED_FROM_REMOTE = "RECONCILED_FROM_REMOTE"
    NOT_FOUND = "NOT_FOUND"


@dataclass
class InstagramScheduledJob:
    """Represents a scheduled Instagram Reel job in the future publishing queue."""
    job_id: str
    week_id: str
    reel_id: str
    video_path: str
    caption: str
    scheduled_at_local: str
    timezone: str = "Europe/Istanbul"
    status: str = "QUEUED"
    attempt_count: int = 0
    container_id: Optional[str] = None
    remote_media_id: Optional[str] = None
    last_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "week_id": self.week_id,
            "reel_id": self.reel_id,
            "video_path": self.video_path,
            "caption": self.caption,
            "scheduled_at_local": self.scheduled_at_local,
            "timezone": self.timezone,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "container_id": self.container_id,
            "remote_media_id": self.remote_media_id,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InstagramScheduledJob":
        return cls(
            job_id=data.get("job_id", ""),
            week_id=data.get("week_id", ""),
            reel_id=data.get("reel_id", ""),
            video_path=data.get("video_path", ""),
            caption=data.get("caption", ""),
            scheduled_at_local=data.get("scheduled_at_local", ""),
            timezone=data.get("timezone", "Europe/Istanbul"),
            status=data.get("status", "QUEUED"),
            attempt_count=data.get("attempt_count", 0),
            container_id=data.get("container_id"),
            remote_media_id=data.get("remote_media_id"),
            last_error=data.get("last_error"),
            created_at=data.get("created_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            updated_at=data.get("updated_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )


@dataclass
class ReelState:
    """Tracks state and publishing lifecycle for a single Reel across 3 platforms."""
    reel_id: str
    week_id: Optional[str] = None
    pipeline_version: int = 3
    content_mode: str = "silent_global_step_by_step"
    generation_status: str = "NOT_STARTED"
    qc_status: str = "PENDING"
    video_path: Optional[str] = None
    video_sha256: Optional[str] = None
    title: str = ""
    caption: str = ""
    hashtags: List[str] = field(default_factory=list)
    scheduled_at_local: Optional[str] = None
    scheduled_at_utc: Optional[str] = None
    timezone: str = "Europe/Istanbul"
    
    # Platform-independent states
    youtube_status: ReelPlatformStatus = ReelPlatformStatus.NOT_STARTED
    youtube_remote_id: Optional[str] = None
    youtube_url: Optional[str] = None
    youtube_error: Optional[str] = None
    
    tiktok_status: ReelPlatformStatus = ReelPlatformStatus.NOT_STARTED
    tiktok_remote_id: Optional[str] = None
    tiktok_url: Optional[str] = None
    tiktok_error: Optional[str] = None
    
    instagram_status: ReelPlatformStatus = ReelPlatformStatus.NOT_STARTED
    instagram_remote_media_id: Optional[str] = None
    instagram_permalink: Optional[str] = None
    instagram_error: Optional[str] = None
    
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reel_id": self.reel_id,
            "week_id": self.week_id,
            "pipeline_version": self.pipeline_version,
            "content_mode": self.content_mode,
            "generation_status": self.generation_status,
            "qc_status": self.qc_status,
            "video_path": self.video_path,
            "video_sha256": self.video_sha256,
            "title": self.title,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "scheduled_at_local": self.scheduled_at_local,
            "scheduled_at_utc": self.scheduled_at_utc,
            "timezone": self.timezone,
            "youtube": {
                "status": self.youtube_status.value if isinstance(self.youtube_status, ReelPlatformStatus) else str(self.youtube_status),
                "remote_id": self.youtube_remote_id,
                "url": self.youtube_url,
                "error": self.youtube_error
            },
            "tiktok": {
                "status": self.tiktok_status.value if isinstance(self.tiktok_status, ReelPlatformStatus) else str(self.tiktok_status),
                "remote_id": self.tiktok_remote_id,
                "url": self.tiktok_url,
                "error": self.tiktok_error
            },
            "instagram": {
                "status": self.instagram_status.value if isinstance(self.instagram_status, ReelPlatformStatus) else str(self.instagram_status),
                "remote_media_id": self.instagram_remote_media_id,
                "permalink": self.instagram_permalink,
                "error": self.instagram_error
            },
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReelState":
        yt = data.get("youtube", {})
        tt = data.get("tiktok", {})
        ig = data.get("instagram", {})

        def parse_status(val: Any) -> ReelPlatformStatus:
            if isinstance(val, ReelPlatformStatus):
                return val
            try:
                return ReelPlatformStatus(str(val))
            except Exception:
                return ReelPlatformStatus.NOT_STARTED

        return cls(
            reel_id=data.get("reel_id", ""),
            week_id=data.get("week_id"),
            pipeline_version=data.get("pipeline_version", 3),
            content_mode=data.get("content_mode", "silent_global_step_by_step"),
            generation_status=data.get("generation_status", "NOT_STARTED"),
            qc_status=data.get("qc_status", "PENDING"),
            video_path=data.get("video_path"),
            video_sha256=data.get("video_sha256"),
            title=data.get("title", ""),
            caption=data.get("caption", ""),
            hashtags=data.get("hashtags", []),
            scheduled_at_local=data.get("scheduled_at_local"),
            scheduled_at_utc=data.get("scheduled_at_utc"),
            timezone=data.get("timezone", "Europe/Istanbul"),
            youtube_status=parse_status(yt.get("status")),
            youtube_remote_id=yt.get("remote_id"),
            youtube_url=yt.get("url"),
            youtube_error=yt.get("error"),
            tiktok_status=parse_status(tt.get("status")),
            tiktok_remote_id=tt.get("remote_id"),
            tiktok_url=tt.get("url"),
            tiktok_error=tt.get("error"),
            instagram_status=parse_status(ig.get("status")),
            instagram_remote_media_id=ig.get("remote_media_id"),
            instagram_permalink=ig.get("permalink"),
            instagram_error=ig.get("error"),
            created_at=data.get("created_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            updated_at=data.get("updated_at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )


@dataclass
class PublishingSlot:
    """A specific publishing slot in a weekly plan."""
    slot_index: int
    day_number: int
    date_str: str
    time_str: str
    scheduled_at_local: str
    scheduled_at_utc: str
    reel_id: Optional[str] = None
    youtube_status: str = "NOT_STARTED"
    tiktok_status: str = "NOT_STARTED"
    instagram_status: str = "NOT_STARTED"
    qc_status: str = "PENDING"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slot_index": self.slot_index,
            "day_number": self.day_number,
            "date": self.date_str,
            "time": self.time_str,
            "scheduled_at_local": self.scheduled_at_local,
            "scheduled_at_utc": self.scheduled_at_utc,
            "reel_id": self.reel_id,
            "youtube_status": self.youtube_status,
            "tiktok_status": self.tiktok_status,
            "instagram_status": self.instagram_status,
            "qc_status": self.qc_status
        }


@dataclass
class WeekPlan:
    """Represents a 7-day 14-Reel publishing schedule."""
    week_id: str
    start_date: str
    timezone: str = "Europe/Istanbul"
    target_reels: int = 14
    slots_per_day: int = 2
    slot_times: List[str] = field(default_factory=lambda: ["19:30", "22:00"])
    platforms: List[str] = field(default_factory=lambda: ["youtube", "tiktok", "instagram"])
    status: str = "PLANNED"
    approved: bool = False
    slots: List[PublishingSlot] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "week_id": self.week_id,
            "start_date": self.start_date,
            "timezone": self.timezone,
            "target_reels": self.target_reels,
            "slots_per_day": self.slots_per_day,
            "slot_times": self.slot_times,
            "platforms": self.platforms,
            "status": self.status,
            "approved": self.approved,
            "slots": [s.to_dict() for s in self.slots],
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class RunReport:
    """Summary of a weekly orchestrator execution run."""
    run_id: str
    start_time: str
    finish_time: Optional[str] = None
    duration_seconds: float = 0.0
    mode: str = "DRY_RUN"  # DRY_RUN or LIVE
    week_id: str = ""
    inventory_found: int = 0
    generation_needed: int = 0
    qc_passed: int = 0
    youtube_success: int = 0
    tiktok_success: int = 0
    instagram_queued: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "start_time": self.start_time,
            "finish_time": self.finish_time,
            "duration_seconds": round(self.duration_seconds, 2),
            "mode": self.mode,
            "week_id": self.week_id,
            "inventory_found": self.inventory_found,
            "generation_needed": self.generation_needed,
            "qc_passed": self.qc_passed,
            "youtube_success": self.youtube_success,
            "tiktok_success": self.tiktok_success,
            "instagram_queued": self.instagram_queued,
            "errors": self.errors
        }
