"""
YouTube Shorts Publisher & Resumable Uploader using official YouTube Data API v3.
"""
from abc import ABC, abstractmethod
import os
import hashlib
import logging
from pathlib import Path
from typing import Optional, Any

from .models import Platform, PlatformPublicationStatus, PublishRecord
from .config import PublishingConfig
from .youtube_auth import YouTubeAuthManager, AuthRequiredError, YouTubeAuthError

logger = logging.getLogger("ReelsAIFactory.YouTubePublisher")

class BaseYouTubePublisher(ABC):
    @abstractmethod
    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        pass

    def prepare_preflight(self, record: PublishRecord) -> Any:
        return True, "YOUTUBE_FINAL_SCHEDULE_READY"

    def commit_schedule(self, record: PublishRecord) -> PublishRecord:
        return record

class YouTubePublisher(BaseYouTubePublisher):
    """Production YouTube Data API v3 publisher."""

    def __init__(self, config: PublishingConfig):
        self.config = config

    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        """Upload video and schedule publication via YouTube Data API v3."""
        if not record.video_file.exists():
            record.mark_failed(f"Video file not found on disk: {record.video_file}")
            return record

        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError:
            record.mark_failed("googleapiclient is not installed.")
            return record

        try:
            youtube = YouTubeAuthManager.get_authenticated_service(
                client_secret_path=self.config.youtube_client_secret_path,
                token_path=self.config.youtube_token_path,
                interactive=False
            )
        except AuthRequiredError as are:
            record.mark_failed(str(are), status=PlatformPublicationStatus.AUTH_REQUIRED)
            return record
        except Exception as e:
            record.mark_failed(f"YouTube authentication failed: {e}", status=PlatformPublicationStatus.AUTH_REQUIRED)
            return record

        # 1. Verify authenticated channel matches expected handle (@BuiIdVerse)
        is_verified, v_msg, ch_info = YouTubeAuthManager.verify_authenticated_channel(
            youtube,
            expected_handle=self.config.youtube_expected_handle,
            expected_channel_id=self.config.youtube_expected_channel_id
        )
        if not is_verified:
            err_type = ch_info.get("error_type", "")
            if err_type == "REAUTH_REQUIRED" or "reauth" in v_msg.lower() or "insufficient" in v_msg.lower():
                record.mark_failed(v_msg, status=PlatformPublicationStatus.AUTH_REQUIRED)
                logger.error(f"[{record.reel_id}] YouTube upload blocked due to missing permissions: {v_msg}")
            else:
                record.mark_failed(v_msg, status=PlatformPublicationStatus.ACCOUNT_MISMATCH)
                logger.error(f"[{record.reel_id}] YouTube upload blocked due to account mismatch: {v_msg}")
            return record

        logger.info(f"[{record.reel_id}] YouTube Target Account Verified: {ch_info.get('title')} ({ch_info.get('custom_url')})")

        # Prepare request body
        clean_tags = [t.lstrip("#") for t in record.hashtags]
        body = {
            "snippet": {
                "title": record.title[:100],
                "description": f"{record.description}\n\n{' '.join(record.hashtags)}",
                "tags": clean_tags,
                "categoryId": "28"
            },
            "status": {
                "privacyStatus": self.config.youtube_privacy_status,
                "publishAt": record.scheduled_at_utc,
                "selfDeclaredMadeForKids": self.config.youtube_made_for_kids,
                "containsSyntheticMedia": self.config.ai_disclosure
            }
        }

        try:
            media = MediaFileUpload(
                str(record.video_file),
                mimetype="video/mp4",
                chunksize=1024 * 1024 * 5,  # 5MB chunks
                resumable=True
            )

            request = youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status_obj, response = request.next_chunk()
                if status_obj:
                    progress = int(status_obj.progress() * 100)
                    logger.debug(f"YouTube upload progress for {record.reel_id}: {progress}%")

            video_id = response.get("id")
            if not video_id:
                record.mark_failed("YouTube upload completed but no video ID returned.")
                return record

            # Verify remote resource
            verify_res = youtube.videos().list(part="status", id=video_id).execute()
            items = verify_res.get("items", [])
            if not items:
                record.mark_failed(f"Video {video_id} uploaded but not verified on remote channel.")
                return record

            remote_status = items[0].get("status", {})
            remote_privacy = remote_status.get("privacyStatus")
            remote_publish_at = remote_status.get("publishAt")

            # Check if project restriction forced private lock
            if remote_status.get("rejectionReason"):
                record.mark_failed(
                    f"Video rejected by YouTube: {remote_status.get('rejectionReason')}",
                    status=PlatformPublicationStatus.REVIEW_REQUIRED
                )
                return record

            remote_url = f"https://youtu.be/{video_id}"
            record.mark_scheduled(remote_id=video_id, remote_url=remote_url)
            logger.info(f"[{record.reel_id}] YouTube Shorts scheduled successfully: {remote_url} (PublishAt: {record.scheduled_at_utc})")
            return record

        except Exception as e:
            err_str = str(e)
            logger.exception(f"YouTube upload error for {record.reel_id}: {err_str}")
            if "unverified" in err_str.lower() or "quota" in err_str.lower():
                record.mark_failed(f"YouTube API restriction: {err_str}", status=PlatformPublicationStatus.REVIEW_REQUIRED)
            else:
                record.mark_failed(f"YouTube upload failed: {err_str}")
            return record

class MockYouTubePublisher(BaseYouTubePublisher):
    """Mock publisher for safe tests and dry-runs (Zero real API calls / Zero uploads)."""

    def __init__(self, simulate_mismatch: bool = False, expected_handle: str = "@BuiIdVerse"):
        self.simulate_mismatch = simulate_mismatch
        self.expected_handle = expected_handle

    def upload_and_schedule(self, record: PublishRecord) -> PublishRecord:
        if not record.video_file.exists():
            record.mark_failed(f"Video file not found: {record.video_file}")
            return record

        if self.simulate_mismatch:
            record.mark_failed(
                f"ACCOUNT_MISMATCH: Expected '{self.expected_handle}', authenticated as '@OtherChannel'",
                status=PlatformPublicationStatus.ACCOUNT_MISMATCH
            )
            return record

        # Generate deterministic mock video ID
        mock_id = f"mock_yt_{hashlib.md5(record.reel_id.encode('utf-8')).hexdigest()[:11]}"
        record.mark_scheduled(
            remote_id=mock_id,
            remote_url=f"https://youtu.be/{mock_id}",
            verified_date="2026-08-16",
            verified_time="19:30"
        )
        return record

    def prepare_preflight(self, record: PublishRecord) -> Any:
        if self.simulate_mismatch:
            return False, f"ACCOUNT_MISMATCH: Expected '{self.expected_handle}'"
        return True, "YOUTUBE_FINAL_SCHEDULE_READY"

    def commit_schedule(self, record: PublishRecord) -> PublishRecord:
        mock_id = record.remote_id or f"mock_yt_{hashlib.md5(record.reel_id.encode('utf-8')).hexdigest()[:11]}"
        record.mark_scheduled(
            remote_id=mock_id,
            remote_url=f"https://youtu.be/{mock_id}",
            verified_date="2026-08-16",
            verified_time="19:30"
        )
        return record
