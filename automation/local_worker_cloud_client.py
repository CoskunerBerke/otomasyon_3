"""
Lightweight Cloud API Client for Local Windows Worker.
Communicates with Railway Cloud Control Plane via authenticated HTTP REST endpoints.
Handles heartbeats, command polling, completion reporting, state synchronization,
private storage self-test, and multipart media upload for Instagram scheduling.
Strictly avoids exposing API keys in logs and provides clear error diagnostics.
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List, Union
import requests

logger = logging.getLogger("ReelsAIFactory.LocalWorkerCloudClient")

from automation.cloud.config import mask_secret
from automation.cloud.media_storage import compute_file_sha256


class LocalWorkerCloudClient:
    """HTTP Client for Local Windows Worker communication with Railway Cloud Control Plane."""

    def __init__(
        self,
        public_base_url: str,
        api_key: str,
        worker_id: str = "win_local_worker_1",
        timeout_seconds: float = 15.0
    ):
        self.public_base_url = (public_base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.worker_id = worker_id.strip() if worker_id else "win_local_worker_1"
        self.timeout = timeout_seconds

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ReelsAIFactory-LocalWorker/1.0",
            "X-Worker-Api-Key": self.api_key,
            "X-Worker-Id": self.worker_id
        })

    def _url(self, path: str) -> str:
        clean_path = path.lstrip("/")
        return f"{self.public_base_url}/{clean_path}"

    def send_heartbeat(
        self,
        status: str = "IDLE",
        capabilities: Optional[List[str]] = None
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Sends worker heartbeat to POST /worker/heartbeat.
        Returns (success, response_dict, error_code).
        """
        if not self.public_base_url:
            return False, {}, "PUBLIC_BASE_URL_MISSING"
        if not self.api_key:
            return False, {}, "WORKER_API_DISABLED"

        url = self._url("/worker/heartbeat")
        payload = {
            "worker_id": self.worker_id,
            "hostname_hash": "win_local_host",
            "version": "1.0.0",
            "capabilities": capabilities or ["FLOW", "YOUTUBE", "TIKTOK", "MEDIA_UPLOAD", "OBSIDIAN_SYNC"],
            "status": status
        }

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"[CLOUD CLIENT] Heartbeat acknowledged for worker '{self.worker_id}'")
                return True, data, None
            elif resp.status_code in (401, 403):
                logger.warning(f"[CLOUD CLIENT] Heartbeat rejected: 401 Unauthorized")
                return False, {}, "UNAUTHORIZED_WORKER_KEY"
            else:
                logger.warning(f"[CLOUD CLIENT] Heartbeat failed with status {resp.status_code}: {resp.text}")
                return False, {}, f"HTTP_{resp.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"[CLOUD CLIENT] Connection error during heartbeat: {e}")
            return False, {}, "CLOUD_UNREACHABLE"

    def get_next_command(self) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Polls next claimed command from GET /worker/commands/next.
        Returns (success, command_data_or_None, error_code).
        """
        if not self.public_base_url:
            return False, None, "PUBLIC_BASE_URL_MISSING"
        if not self.api_key:
            return False, None, "WORKER_API_DISABLED"

        url = self._url("/worker/commands/next")
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                cmd = data.get("command")
                return True, cmd, None
            elif resp.status_code in (401, 403):
                return False, None, "UNAUTHORIZED_WORKER_KEY"
            else:
                return False, None, f"HTTP_{resp.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"[CLOUD CLIENT] Connection error getting next command: {e}")
            return False, None, "CLOUD_UNREACHABLE"

    def complete_command(
        self,
        command_id: str,
        status: str = "COMPLETE",
        error_message: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Reports command completion to POST /worker/commands/{command_id}/complete.
        Returns (success, response_dict, error_code).
        """
        if not self.public_base_url or not self.api_key:
            return False, {}, "WORKER_CONFIG_MISSING"

        url = self._url(f"/worker/commands/{command_id}/complete")
        payload = {
            "worker_id": self.worker_id,
            "status": status,
            "error_message": error_message
        }

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                return True, resp.json(), None
            elif resp.status_code in (401, 403):
                return False, {}, "UNAUTHORIZED_WORKER_KEY"
            else:
                return False, {}, f"HTTP_{resp.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"[CLOUD CLIENT] Connection error completing command {command_id}: {e}")
            return False, {}, "CLOUD_UNREACHABLE"

    def get_cloud_state(self) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Retrieves active weeks, approvals, and jobs from GET /worker/state/sync for Obsidian.
        Returns (success, state_dict, error_code).
        """
        if not self.public_base_url:
            return False, {}, "PUBLIC_BASE_URL_MISSING"
        if not self.api_key:
            return False, {}, "WORKER_API_DISABLED"

        url = self._url("/worker/state/sync")
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                return True, resp.json(), None
            elif resp.status_code in (401, 403):
                return False, {}, "UNAUTHORIZED_WORKER_KEY"
            else:
                return False, {}, f"HTTP_{resp.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"[CLOUD CLIENT] Connection error syncing cloud state: {e}")
            return False, {}, "CLOUD_UNREACHABLE"

    def run_storage_self_test(self) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Triggers cloud private S3 storage round-trip diagnostic via POST /worker/storage/self-test.
        Sends X-Worker-Api-Key and X-Storage-Smoke-Test: true.
        Returns (success, response_dict, error_code).
        """
        if not self.public_base_url:
            return False, {}, "PUBLIC_BASE_URL_MISSING"
        if not self.api_key:
            return False, {}, "WORKER_API_DISABLED"

        url = self._url("/worker/storage/self-test")
        custom_headers = {
            "X-Storage-Smoke-Test": "true"
        }

        try:
            resp = self.session.post(url, headers=custom_headers, timeout=self.timeout)
            if resp.status_code == 200:
                return True, resp.json(), None
            elif resp.status_code in (401, 403):
                return False, {}, "UNAUTHORIZED_WORKER_KEY"
            elif resp.status_code == 400:
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                return False, data, "CONFIRMATION_REQUIRED"
            else:
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                return False, data, f"HTTP_{resp.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"[CLOUD CLIENT] Connection error running storage self-test: {e}")
            return False, {}, "CLOUD_UNREACHABLE"

    def upload_media_for_instagram(
        self,
        local_path: Union[str, Path],
        week_id: str,
        reel_id: str,
        scheduled_at_local: str,
        scheduled_at_utc: str,
        timezone: str = "Europe/Istanbul",
        caption: str = "",
        job_id: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """
        Uploads a finalized local MP4 file to Railway private S3 storage and registers MEDIA_READY Instagram job.
        Computes SHA256 locally, sends authenticated multipart POST to /worker/media/upload.
        Returns (success, response_dict, error_code).
        """
        if not self.public_base_url:
            return False, {}, "PUBLIC_BASE_URL_MISSING"
        if not self.api_key:
            return False, {}, "WORKER_API_DISABLED"

        p = Path(local_path).resolve()
        if not p.exists() or not p.is_file():
            return False, {}, "FILE_NOT_FOUND"

        if not p.name.lower().endswith(".mp4"):
            return False, {}, "INVALID_MEDIA_FORMAT"

        file_size = p.stat().st_size
        if file_size == 0:
            return False, {}, "MEDIA_EMPTY"

        if file_size > 100 * 1024 * 1024:
            return False, {}, "MEDIA_TOO_LARGE"

        local_sha256 = compute_file_sha256(p).lower()

        url = self._url("/worker/media/upload")
        form_data = {
            "week_id": week_id,
            "reel_id": reel_id,
            "scheduled_at_local": scheduled_at_local,
            "scheduled_at_utc": scheduled_at_utc,
            "timezone": timezone,
            "caption": caption,
            "media_sha256": local_sha256
        }
        if job_id:
            form_data["job_id"] = job_id

        try:
            with open(p, "rb") as f:
                files = {
                    "file": (p.name, f, "video/mp4")
                }
                resp = self.session.post(
                    url,
                    data=form_data,
                    files=files,
                    timeout=max(self.timeout, 60.0)
                )

            try:
                data = resp.json()
            except Exception:
                data = {}

            if resp.status_code == 200:
                logger.info(f"[CLOUD CLIENT] Media upload succeeded: {data.get('media_object_key')}")
                return True, data, None
            elif resp.status_code in (401, 403):
                return False, data, "UNAUTHORIZED_WORKER_KEY"
            elif resp.status_code == 409:
                err_code = data.get("error", "CONFLICT")
                return False, data, err_code
            elif resp.status_code == 413:
                return False, data, "MEDIA_TOO_LARGE"
            elif resp.status_code == 400:
                err_code = data.get("error", "BAD_REQUEST")
                return False, data, err_code
            else:
                return False, data, f"HTTP_{resp.status_code}"

        except requests.exceptions.RequestException as e:
            logger.error(f"[CLOUD CLIENT] Connection error during media upload: {e}")
            return False, {}, "CLOUD_UNREACHABLE"
