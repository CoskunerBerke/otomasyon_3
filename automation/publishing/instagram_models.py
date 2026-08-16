"""
Data models and Enums for Instagram Reels Content Publishing API (Meta Graph API).
"""
from dataclasses import dataclass, field
from enum import Enum
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class InstagramPublishState(str, Enum):
    """Lifecycle states for Instagram Reels publishing."""
    NOT_STARTED = "NOT_STARTED"
    PREFLIGHT_OK = "PREFLIGHT_OK"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    NEEDS_USER_META_SETUP = "NEEDS_USER_META_SETUP"
    MEDIA_VALID = "MEDIA_VALID"
    MEDIA_INVALID = "MEDIA_INVALID"
    UPLOAD_PENDING = "UPLOAD_PENDING"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    PUBLISH_PENDING = "PUBLISH_PENDING"
    PUBLISHED = "PUBLISHED"
    REMOTE_VERIFIED = "REMOTE_VERIFIED"
    RATE_LIMIT_BLOCKED = "RATE_LIMIT_BLOCKED"
    SKIP_ALREADY_PUBLISHED = "SKIP_ALREADY_PUBLISHED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FATAL = "FAILED_FATAL"


@dataclass
class InstagramConfig:
    """Configuration for Meta Graph API / Instagram Reels Publishing."""
    app_id: str = ""
    app_secret: str = ""
    access_token: str = ""
    graph_version: str = "v22.0"
    account_id: str = ""
    expected_username: str = "builddverse"
    dry_run: bool = True
    allow_upload: bool = False
    allow_publish: bool = False
    timeout_seconds: int = 30
    max_retries: int = 3
    poll_interval_seconds: float = 3.0
    max_poll_wait_seconds: int = 300

    @property
    def masked_token(self) -> str:
        """Returns a safely masked representation of the access token."""
        if not self.access_token:
            return "<EMPTY_TOKEN>"
        tok = self.access_token.strip()
        if len(tok) <= 8:
            return "***"
        return f"{tok[:4]}...{tok[-4:]}"

    @property
    def normalized_username(self) -> str:
        """Returns expected username without '@' prefix and lowercased."""
        return self.expected_username.strip().lstrip("@").lower()


@dataclass
class InstagramMediaValidationResult:
    """Result of local video format validation against Instagram Reels requirements."""
    is_valid: bool = False
    duration_seconds: float = 0.0
    width: int = 0
    height: int = 0
    aspect_ratio: str = ""
    video_codec: str = ""
    audio_codec: Optional[str] = None
    fps: float = 0.0
    file_size_bytes: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def status_code(self) -> str:
        return "INSTAGRAM_MEDIA_VALID" if self.is_valid else "INSTAGRAM_MEDIA_INVALID"


@dataclass
class InstagramPublishRequest:
    """Request payload for an Instagram Reel publication."""
    reel_id: str
    video_path: Path
    caption: str
    scheduled_at_local: Optional[str] = None
    hashtags: List[str] = field(default_factory=list)
    share_to_feed: bool = True
    thumb_offset: Optional[int] = None
    dry_run: bool = True
    allow_upload: bool = False
    allow_publish: bool = False

    def __post_init__(self):
        if isinstance(self.video_path, str):
            self.video_path = Path(self.video_path)

    def full_caption(self) -> str:
        """Builds full caption string including hashtags within 2200 char limit."""
        parts = [self.caption.strip()] if self.caption else []
        if self.hashtags:
            tag_str = " ".join(t if t.startswith("#") else f"#{t}" for t in self.hashtags)
            parts.append(tag_str)
        text = "\n\n".join(p for p in parts if p)
        # Instagram caption limit is 2200 characters
        if len(text) > 2200:
            text = text[:2197] + "..."
        return text


@dataclass
class InstagramPublishResult:
    """Result and serialized state of an Instagram Reel publication."""
    platform: str = "instagram"
    reel_id: str = ""
    status: InstagramPublishState = InstagramPublishState.NOT_STARTED
    remote_media_id: Optional[str] = None
    container_id: Optional[str] = None
    permalink: Optional[str] = None
    scheduled_at_local: Optional[str] = None
    published_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    quota_usage: Optional[int] = None
    quota_total: Optional[int] = None
    retry_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    updated_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "reel_id": self.reel_id,
            "status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "remote_media_id": self.remote_media_id,
            "container_id": self.container_id,
            "permalink": self.permalink,
            "scheduled_at_local": self.scheduled_at_local,
            "published_at": self.published_at,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "quota_usage": self.quota_usage,
            "quota_total": self.quota_total,
            "retry_at": self.retry_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_frontmatter_dict(self) -> Dict[str, Any]:
        """Provides YAML frontmatter dictionary suitable for Obsidian note updates."""
        return {
            "instagram_status": self.status.value if isinstance(self.status, Enum) else str(self.status),
            "instagram_media_id": self.remote_media_id,
            "instagram_container_id": self.container_id,
            "instagram_permalink": self.permalink,
            "instagram_published_at": self.published_at,
            "instagram_error": self.error_message if self.error_message else None,
        }
