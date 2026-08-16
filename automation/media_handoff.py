"""
Local Media Handoff Service for Reels AI Factory.
Transports finalized local MP4 files to Railway private S3 storage and registers
InstagramScheduledJob (status=MEDIA_READY) in PostgreSQL.
Does NOT generate videos, does NOT publish to platforms, and does NOT claim worker commands.
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, Union

logger = logging.getLogger("ReelsAIFactory.MediaHandoff")

from automation.cloud.config import CloudConfig
from automation.cloud.media_storage import compute_file_sha256
from automation.local_worker_cloud_client import LocalWorkerCloudClient


def handoff_reel_to_cloud(
    local_path: Union[str, Path],
    week_id: str,
    reel_id: str,
    scheduled_at_local: str,
    scheduled_at_utc: str,
    timezone: str = "Europe/Istanbul",
    caption: str = "",
    job_id: Optional[str] = None,
    client: Optional[LocalWorkerCloudClient] = None,
    config: Optional[CloudConfig] = None
) -> Tuple[bool, Dict[str, Any], Optional[str]]:
    """
    Transports a single finalized local MP4 video file to Railway cloud storage and
    registers the InstagramScheduledJob as MEDIA_READY in PostgreSQL.
    Returns (success, response_dict, error_code).
    """
    cfg = config or CloudConfig()
    p = Path(local_path).resolve()

    if not p.exists() or not p.is_file():
        logger.error(f"[MEDIA HANDOFF] Local file not found: {p}")
        return False, {}, "FILE_NOT_FOUND"

    if not p.name.lower().endswith(".mp4"):
        logger.error(f"[MEDIA HANDOFF] File is not an MP4: {p.name}")
        return False, {}, "INVALID_MEDIA_FORMAT"

    cl = client or LocalWorkerCloudClient(
        public_base_url=cfg.public_base_url,
        api_key=cfg.local_worker_api_key,
        timeout_seconds=60.0
    )

    file_size = p.stat().st_size
    file_sha256 = compute_file_sha256(p).lower()
    logger.info(f"[MEDIA HANDOFF] Initiating handoff for {reel_id} ({file_size} bytes, SHA: {file_sha256[:8]}...)")

    ok, data, err = cl.upload_media_for_instagram(
        local_path=p,
        week_id=week_id,
        reel_id=reel_id,
        scheduled_at_local=scheduled_at_local,
        scheduled_at_utc=scheduled_at_utc,
        timezone=timezone,
        caption=caption,
        job_id=job_id
    )

    if ok:
        logger.info(f"[MEDIA HANDOFF] Successfully handed off {reel_id} -> {data.get('media_object_key')}")
        return True, data, None
    else:
        logger.warning(f"[MEDIA HANDOFF] Handoff failed for {reel_id}: {err}")
        return False, data, err
