"""
Read-Only Platform Reconciliation Adapters.
Verifies local state against remote platforms without modifying or triggering uploads.
"""
import logging
from typing import Tuple, Optional, Any

logger = logging.getLogger("ReelsAIFactory.Reconciliation")

from .models import (
    ReelState,
    ReelPlatformStatus,
    ReconciliationStatus
)


def reconcile_youtube(reel: ReelState, client: Optional[Any] = None) -> Tuple[ReconciliationStatus, str]:
    """
    Read-only reconciliation check for YouTube Shorts.
    """
    if reel.youtube_status in [ReelPlatformStatus.NOT_STARTED, ReelPlatformStatus.READY, ReelPlatformStatus.QUEUED]:
        return ReconciliationStatus.NOT_FOUND, "No YouTube publication attempt in local state."

    remote_id = reel.youtube_remote_id
    if not remote_id or not str(remote_id).strip():
        if reel.youtube_status in [ReelPlatformStatus.SCHEDULED, ReelPlatformStatus.PUBLISHED]:
            return ReconciliationStatus.REVIEW_REQUIRED, "Local status is SCHEDULED/PUBLISHED but missing youtube_remote_id."
        return ReconciliationStatus.NOT_FOUND, "No remote ID recorded."

    # If client is provided and supports read-only verification
    if client is not None and hasattr(client, "verify_video_id"):
        try:
            ok, msg = client.verify_video_id(remote_id)
            if ok:
                return ReconciliationStatus.CONFIRMED, f"YouTube video {remote_id} verified on remote."
            return ReconciliationStatus.REVIEW_REQUIRED, f"YouTube video {remote_id} not verified on remote: {msg}"
        except Exception as e:
            return ReconciliationStatus.RETRYABLE, f"YouTube reconciliation check exception: {e}"

    # Default fallback when remote ID is recorded
    return ReconciliationStatus.CONFIRMED, f"YouTube remote ID {remote_id} present in local state."


def reconcile_tiktok(reel: ReelState, client: Optional[Any] = None) -> Tuple[ReconciliationStatus, str]:
    """
    Read-only reconciliation check for TikTok Studio.
    """
    if reel.tiktok_status in [ReelPlatformStatus.NOT_STARTED, ReelPlatformStatus.READY, ReelPlatformStatus.QUEUED]:
        return ReconciliationStatus.NOT_FOUND, "No TikTok publication attempt in local state."

    remote_id = reel.tiktok_remote_id
    if not remote_id or not str(remote_id).strip():
        if reel.tiktok_status in [ReelPlatformStatus.SCHEDULED, ReelPlatformStatus.PUBLISHED]:
            return ReconciliationStatus.REVIEW_REQUIRED, "Local status is SCHEDULED/PUBLISHED but missing tiktok_remote_id."
        return ReconciliationStatus.NOT_FOUND, "No remote ID recorded."

    return ReconciliationStatus.CONFIRMED, f"TikTok remote ID {remote_id} present in local state."


def reconcile_instagram(reel: ReelState, client: Optional[Any] = None) -> Tuple[ReconciliationStatus, str]:
    """
    Read-only reconciliation check for Instagram Reels via Meta Graph API.
    """
    if reel.instagram_status in [ReelPlatformStatus.NOT_STARTED, ReelPlatformStatus.READY, ReelPlatformStatus.QUEUED]:
        return ReconciliationStatus.NOT_FOUND, "No Instagram publish attempt in local state (or currently QUEUED)."

    remote_id = reel.instagram_remote_media_id
    if not remote_id or not str(remote_id).strip():
        if reel.instagram_status in [ReelPlatformStatus.SCHEDULED, ReelPlatformStatus.PUBLISHED]:
            return ReconciliationStatus.REVIEW_REQUIRED, "Local status is PUBLISHED but missing remote_media_id."
        return ReconciliationStatus.NOT_FOUND, "No remote ID recorded."

    # If Meta Graph API client is available
    if client is not None and hasattr(client, "get_media_object"):
        try:
            ok, data, err = client.get_media_object(remote_id)
            if ok and data.get("id") == remote_id:
                return ReconciliationStatus.CONFIRMED, f"Instagram Reel {remote_id} verified on Meta Graph API."
            return ReconciliationStatus.REVIEW_REQUIRED, f"Instagram media {remote_id} not verified on remote: {err}"
        except Exception as e:
            return ReconciliationStatus.RETRYABLE, f"Instagram reconciliation check exception: {e}"

    return ReconciliationStatus.CONFIRMED, f"Instagram remote media ID {remote_id} present in local state."
