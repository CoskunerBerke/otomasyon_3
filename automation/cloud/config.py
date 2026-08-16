"""
Configuration and Environment Settings for Cloud Control Plane & Telegram Bot.
Handles database URLs, Telegram tokens, security secrets, timezone, and media storage.
Includes Railway production environment gates, safety flags, and variable normalization.
"""
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


def mask_secret(secret: Optional[str], show_first: int = 4, show_last: int = 4) -> str:
    """Masks sensitive strings like tokens and passwords for safe logging."""
    if not secret:
        return "<EMPTY>"
    s = str(secret).strip()
    if len(s) <= (show_first + show_last):
        return "***"
    return f"{s[:show_first]}...{s[-show_last:]}"


class CloudConfig:
    """Central configuration for Cloud Control Plane, Telegram, and Workers."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = (base_dir or Path(".").resolve())
        self._load_dotenv()

        # Environment Mode
        self.app_env = os.getenv("APP_ENV", "development").strip().lower()
        self.port = int(os.getenv("PORT", "8000"))

        # Database
        self.database_url = os.getenv(
            "DATABASE_URL",
            f"sqlite:///{self.base_dir / 'workspace' / 'cloud_control_plane.db'}"
        ).strip()

        # Feature Flags / Subsystem Enablement (Safe First-Deploy Defaults)
        self.enable_telegram_webhook = os.getenv("ENABLE_TELEGRAM_WEBHOOK", "true").strip().lower() in ("true", "1", "yes")
        self.enable_weekly_scheduler = os.getenv("ENABLE_WEEKLY_SCHEDULER", "false").strip().lower() in ("true", "1", "yes")
        self.enable_instagram_worker = os.getenv("ENABLE_INSTAGRAM_WORKER", "false").strip().lower() in ("true", "1", "yes")
        self.enable_media_cleanup = os.getenv("ENABLE_MEDIA_CLEANUP", "false").strip().lower() in ("true", "1", "yes")
        self.media_retention_days = int(os.getenv("MEDIA_RETENTION_DAYS", "7"))

        # Telegram Settings
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        
        allowed_user = os.getenv("TELEGRAM_ALLOWED_USER_ID", "1835798213").strip()
        self.telegram_allowed_user_id: Optional[int] = int(allowed_user) if allowed_user.isdigit() else None

        chat_id = os.getenv("TELEGRAM_CHAT_ID", "1835798213").strip()
        self.telegram_chat_id: Optional[int] = int(chat_id) if chat_id.lstrip("-").isdigit() else None

        self.telegram_webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        
        raw_public_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
        self.public_base_url = raw_public_url

        # Approval Schedule
        self.weekly_approval_day = int(os.getenv("WEEKLY_APPROVAL_DAY", "6"))
        self.weekly_approval_local_time = os.getenv("WEEKLY_APPROVAL_LOCAL_TIME", "18:00").strip()
        self.timezone_str = os.getenv("APP_TIMEZONE", "Europe/Istanbul")

        # Local Worker API Key
        self.local_worker_api_key = os.getenv("LOCAL_WORKER_API_KEY", "").strip()
        self.local_worker_poll_seconds = int(os.getenv("LOCAL_WORKER_POLL_SECONDS", "60"))

        # Media Storage (S3 / Railway Storage Bucket)
        self.media_storage_backend = os.getenv("MEDIA_STORAGE_BACKEND", "local").strip().lower()
        self.s3_endpoint_url = os.getenv("S3_ENDPOINT_URL", "").strip()
        self.s3_bucket = os.getenv("S3_BUCKET", "").strip()
        self.s3_access_key_id = os.getenv("S3_ACCESS_KEY_ID", "").strip()
        self.s3_secret_access_key = os.getenv("S3_SECRET_ACCESS_KEY", "").strip()
        self.s3_region = os.getenv("S3_REGION", "auto").strip()

        # Instagram Cloud Worker & Publishing Safety Flags
        self.instagram_prepare_minutes_before = int(os.getenv("INSTAGRAM_PREPARE_MINUTES_BEFORE", "15"))
        self.meta_access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
        self.instagram_account_id = os.getenv("INSTAGRAM_ACCOUNT_ID", "17841411536006797").strip()
        self.instagram_expected_username = os.getenv("INSTAGRAM_EXPECTED_USERNAME", "builddverse").strip()
        self.meta_graph_version = os.getenv("META_GRAPH_VERSION", "v26.0").strip()

        self.instagram_dry_run = os.getenv("INSTAGRAM_DRY_RUN", "true").strip().lower() in ("true", "1", "yes")
        self.instagram_allow_upload = os.getenv("INSTAGRAM_ALLOW_UPLOAD", "false").strip().lower() in ("true", "1", "yes")
        self.instagram_allow_publish = os.getenv("INSTAGRAM_ALLOW_PUBLISH", "false").strip().lower() in ("true", "1", "yes")

    def _load_dotenv(self) -> None:
        """Loads environment variables from local .env file if present."""
        env_file = self.base_dir / ".env"
        if not env_file.exists():
            return
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql://") or self.database_url.startswith("postgres://")

    def validate_production_database(self) -> Tuple[bool, Optional[str]]:
        """Hard gate: Production environment must use PostgreSQL."""
        if self.is_production:
            if not self.is_postgres:
                return False, "PRODUCTION_DATABASE_INVALID"
        return True, None

    def validate_production_storage(self) -> Tuple[bool, Optional[str]]:
        """Hard gate: Production with S3 backend must have all S3 credentials."""
        if self.is_production and self.media_storage_backend == "s3":
            if not (self.s3_endpoint_url and self.s3_bucket and self.s3_access_key_id and self.s3_secret_access_key):
                return False, "PRODUCTION_S3_STORAGE_INVALID"
        return True, None

    def validate_public_url(self) -> Tuple[bool, Optional[str]]:
        """Ensures public URL starts with https:// in production."""
        if not self.public_base_url:
            return True, None
        if self.is_production and not self.public_base_url.startswith("https://"):
            return False, "NON_HTTPS_PRODUCTION_URL"
        return True, None

    @property
    def masked_bot_token(self) -> str:
        return mask_secret(self.telegram_bot_token, 4, 4)

    @property
    def masked_meta_token(self) -> str:
        return mask_secret(self.meta_access_token, 4, 4)

    @property
    def masked_worker_key(self) -> str:
        return mask_secret(self.local_worker_api_key, 3, 3)

    @property
    def is_telegram_configured(self) -> bool:
        return bool(
            self.telegram_bot_token
            and self.telegram_allowed_user_id
            and self.telegram_chat_id
        )

    @property
    def is_storage_configured(self) -> bool:
        if self.media_storage_backend == "s3":
            return bool(self.s3_bucket and self.s3_endpoint_url and self.s3_access_key_id and self.s3_secret_access_key)
        return True  # Local backend is always configured

    @property
    def is_worker_api_enabled(self) -> bool:
        return bool(self.local_worker_api_key)

    def to_sanitized_dict(self) -> Dict[str, Any]:
        """Returns safe configuration summary without leaking secrets."""
        return {
            "app_env": self.app_env,
            "port": self.port,
            "database_url": self.database_url.split("@")[-1] if "@" in self.database_url else self.database_url,
            "is_postgres": self.is_postgres,
            "telegram_bot_token": self.masked_bot_token,
            "telegram_allowed_user_id": self.telegram_allowed_user_id,
            "telegram_chat_id": self.telegram_chat_id,
            "telegram_webhook_secret_set": bool(self.telegram_webhook_secret),
            "public_base_url": self.public_base_url or "<NOT_SET>",
            "weekly_approval_day": self.weekly_approval_day,
            "weekly_approval_local_time": self.weekly_approval_local_time,
            "timezone": self.timezone_str,
            "local_worker_api_key": self.masked_worker_key,
            "worker_api_enabled": self.is_worker_api_enabled,
            "media_storage_backend": self.media_storage_backend,
            "storage_configured": self.is_storage_configured,
            "s3_bucket": self.s3_bucket or "<NOT_SET>",
            "s3_endpoint_url": self.s3_endpoint_url or "<NOT_SET>",
            "s3_region": self.s3_region,
            "instagram_account_id": self.instagram_account_id,
            "instagram_expected_username": self.instagram_expected_username,
            "meta_token_set": bool(self.meta_access_token),
            "instagram_dry_run": self.instagram_dry_run,
            "instagram_allow_upload": self.instagram_allow_upload,
            "instagram_allow_publish": self.instagram_allow_publish,
            "enable_weekly_scheduler": self.enable_weekly_scheduler,
            "enable_instagram_worker": self.enable_instagram_worker,
            "enable_media_cleanup": self.enable_media_cleanup,
            "media_retention_days": self.media_retention_days
        }
