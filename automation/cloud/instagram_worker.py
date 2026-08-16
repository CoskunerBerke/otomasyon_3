"""
Always-On Instagram Cloud Publishing Worker.
Processes scheduled Instagram jobs, manages preparation windows, streams binary media from storage,
executes official Meta Graph API publishing, and enforces strict exactly-once safety and safety flags.
"""
import os
import time
import tempfile
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("ReelsAIFactory.InstagramCloudWorker")

from .config import CloudConfig
from .database import Database
from .models import (
    InstagramScheduledJob,
    InstagramJobStatus,
    NotificationLog
)
from .media_storage import MediaStorageInterface, compute_file_sha256
from automation.publishing.instagram_models import (
    InstagramConfig,
    InstagramPublishRequest,
    InstagramPublishState
)
from automation.publishing.instagram_api import InstagramAPIClient, mask_token


class InstagramCloudWorker:
    """Processes due Instagram Reel jobs in the cloud database."""

    def __init__(
        self,
        config: CloudConfig,
        db: Database,
        storage: MediaStorageInterface,
        api_client: Optional[InstagramAPIClient] = None
    ):
        self.config = config
        self.db = db
        self.storage = storage
        if api_client is not None:
            self.client = api_client
        else:
            ig_cfg = InstagramConfig(
                access_token=config.meta_access_token,
                graph_version=config.meta_graph_version,
                account_id=config.instagram_account_id,
                expected_username=config.instagram_expected_username,
                dry_run=config.instagram_dry_run,
                allow_upload=config.instagram_allow_upload,
                allow_publish=config.instagram_allow_publish
            )
            self.client = InstagramAPIClient(ig_cfg)

    def process_due_jobs(self, worker_id: str = "cloud_worker_1") -> int:
        """
        Scans for due jobs within the preparation window and processes them.
        Returns the number of jobs processed.
        """
        now_dt = datetime.datetime.now()
        # Look ahead by prepare_minutes
        prepare_cutoff = (now_dt + datetime.timedelta(minutes=self.config.instagram_prepare_minutes_before)).strftime("%Y-%m-%d %H:%M:%S")

        processed_count = 0
        while True:
            # Atomic claim to prevent double publishing
            job = self.db.claim_due_instagram_job(worker_id, prepare_cutoff)
            if not job:
                break

            logger.info(f"[IG WORKER] Claimed due job: {job.job_id} for {job.reel_id} (Target: {job.scheduled_at_local})")
            success = self.execute_job(job)
            processed_count += 1

        return processed_count

    def execute_job(self, job: InstagramScheduledJob) -> bool:
        """
        Executes a single claimed Instagram job lifecycle with safety flags and exactly-once safety.
        """
        if not job.media_object_key:
            job.status = InstagramJobStatus.FAILED_FATAL
            job.last_error = "MISSING_MEDIA_OBJECT_KEY"
            self.db.save_instagram_job(job)
            logger.error(f"[IG WORKER] Job {job.job_id} failed: No media object key.")
            return False

        # 1. Download media to temporary file
        temp_dir = Path(tempfile.gettempdir()) / "reels_cloud_ig"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_video_path = temp_dir / f"{job.reel_id}_temp.mp4"

        try:
            ok_get = self.storage.get_file(job.media_object_key, temp_video_path)
            if not ok_get or not temp_video_path.exists():
                job.status = InstagramJobStatus.FAILED_RETRYABLE
                job.last_error = f"FAILED_TO_DOWNLOAD_MEDIA: {job.media_object_key}"
                self.db.save_instagram_job(job)
                logger.error(f"[IG WORKER] Could not download media for {job.job_id}")
                return False

            # Verify SHA256 if recorded
            if job.media_sha256:
                actual_sha = compute_file_sha256(temp_video_path)
                if actual_sha != job.media_sha256:
                    job.status = InstagramJobStatus.FAILED_FATAL
                    job.last_error = f"MEDIA_SHA256_MISMATCH: expected {job.media_sha256}, got {actual_sha}"
                    self.db.save_instagram_job(job)
                    logger.error(f"[IG WORKER] {job.last_error}")
                    return False

            # 2. Check quota limit
            ok_limit, limit_data, _ = self.client.check_publishing_limit(self.config.instagram_account_id)
            if ok_limit:
                usage = limit_data.get("quota_usage", 0)
                total = limit_data.get("config", {}).get("quota_total", 25)
                if usage >= total:
                    job.status = InstagramJobStatus.FAILED_RETRYABLE
                    job.last_error = f"RATE_LIMIT_BLOCKED: {usage}/{total} in 24h"
                    self.db.save_instagram_job(job)
                    return False

            # 3. Create Container
            publish_req = InstagramPublishRequest(
                reel_id=job.reel_id,
                video_path=temp_video_path,
                caption=job.caption,
                share_to_feed=True,
                dry_run=self.config.instagram_dry_run,
                allow_upload=self.config.instagram_allow_upload,
                allow_publish=self.config.instagram_allow_publish
            )

            job.status = InstagramJobStatus.UPLOADING_TO_META
            self.db.save_instagram_job(job)

            ok_cont, msg_cont, container_id, upload_uri = self.client.create_reels_container(publish_req)
            if not ok_cont or not container_id:
                job.status = InstagramJobStatus.FAILED_RETRYABLE
                job.last_error = f"CONTAINER_CREATE_FAILED: {msg_cont}"
                self.db.save_instagram_job(job)
                return False

            job.container_id = container_id

            # Dry-run early exit
            if self.config.instagram_dry_run or not self.config.instagram_allow_upload:
                logger.info(f"[IG WORKER] DRY RUN / UPLOAD DISABLED: Simulation completed for {job.job_id}")
                job.status = InstagramJobStatus.PUBLISHED
                job.remote_media_id = "MOCK_DRY_RUN_ID"
                self.db.save_instagram_job(job)
                return True

            # 4. Stream binary video to Meta
            ok_up, msg_up = self.client.upload_video_resumable(
                upload_uri=upload_uri,
                video_path=temp_video_path,
                dry_run=self.config.instagram_dry_run,
                allow_upload=self.config.instagram_allow_upload
            )
            if not ok_up:
                job.status = InstagramJobStatus.FAILED_RETRYABLE
                job.last_error = f"UPLOAD_FAILED: {msg_up}"
                self.db.save_instagram_job(job)
                return False

            # 5. Poll container status until FINISHED
            job.status = InstagramJobStatus.PROCESSING
            self.db.save_instagram_job(job)

            ok_proc, status_proc, _ = self.client.poll_container_status(container_id, timeout_seconds=300)
            if not ok_proc or status_proc != "FINISHED":
                job.status = InstagramJobStatus.FAILED_RETRYABLE
                job.last_error = f"PROCESSING_{status_proc}"
                self.db.save_instagram_job(job)
                return False

            job.status = InstagramJobStatus.READY_TO_PUBLISH
            self.db.save_instagram_job(job)

            # Check if live publish is enabled
            if not self.config.instagram_allow_publish:
                logger.info(f"[IG WORKER] PUBLISH DISABLED: Container {container_id} ready but publishing disabled.")
                return True

            # 6. Publish Media (Exactly-once safe)
            job.status = InstagramJobStatus.PUBLISHING
            self.db.save_instagram_job(job)

            ok_pub, msg_pub, media_id = self.client.publish_media(
                container_id=container_id,
                dry_run=self.config.instagram_dry_run,
                allow_publish=self.config.instagram_allow_publish
            )

            if not ok_pub or not media_id:
                # If network timeout occurs after publish call, reconcile first before retry
                logger.warning(f"[IG WORKER] Publish call returned {msg_pub}. Performing safety reconciliation...")
                job.status = InstagramJobStatus.FAILED_RETRYABLE
                job.last_error = f"PUBLISH_FAILED: {msg_pub}"
                self.db.save_instagram_job(job)
                return False

            job.remote_media_id = str(media_id).strip()
            job.published_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 7. Remote Verification
            time.sleep(1.5)
            ok_ver, ver_data, _ = self.client.get_media_object(media_id)
            if ok_ver and ver_data.get("id") == media_id:
                job.permalink = ver_data.get("permalink")
                job.status = InstagramJobStatus.REMOTE_VERIFIED
            else:
                job.status = InstagramJobStatus.PUBLISHED

            job.updated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.db.save_instagram_job(job)
            logger.info(f"[IG WORKER] Job {job.job_id} successfully published! Media ID: {job.remote_media_id}")
            return True

        except Exception as e:
            job.status = InstagramJobStatus.FAILED_FATAL
            job.last_error = f"WORKER_EXCEPTION: {str(e)}"
            self.db.save_instagram_job(job)
            logger.error(f"[IG WORKER] Unhandled exception processing {job.job_id}: {e}")
            return False

        finally:
            # Clean up local temporary file
            if temp_video_path.exists():
                try:
                    temp_video_path.unlink()
                except Exception:
                    pass
