"""
REST Handlers for Local Windows Worker Communication with Cloud Control Plane.
Protects endpoints with Worker API Key authentication.
Includes worker heartbeat, command dispatching, state sync, and private storage diagnostic round-trip.
"""
import os
import uuid
import json
import logging
import tempfile
import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("ReelsAIFactory.LocalWorkerAPI")

from .config import CloudConfig
from .database import Database
from .models import (
    WorkerHeartbeat,
    LocalWorkerCommand,
    CommandStatus
)
from .security import verify_worker_api_key
from .media_storage import MediaStorageInterface, compute_file_sha256, get_media_storage


def _authenticate_worker(headers: Dict[str, str], config: CloudConfig) -> Tuple[bool, Optional[str]]:
    """Verifies X-Worker-Api-Key header."""
    if not config.is_worker_api_enabled:
        return False, "WORKER_API_DISABLED"
    received_key = (
        headers.get("X-Worker-Api-Key") or
        headers.get("x-worker-api-key") or
        headers.get("HTTP_X_WORKER_API_KEY")
    )
    if verify_worker_api_key(received_key, config.local_worker_api_key):
        return True, None
    return False, "UNAUTHORIZED_WORKER_KEY"


def handle_worker_heartbeat(
    headers: Dict[str, str],
    payload: Dict[str, Any],
    config: CloudConfig,
    db: Database
) -> Tuple[int, Dict[str, Any]]:
    """Handles POST /worker/heartbeat."""
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    worker_id = payload.get("worker_id", "local_win_worker")
    hostname_hash = payload.get("hostname_hash", "win_hash")
    version = payload.get("version", "1.0.0")
    capabilities = payload.get("capabilities", ["FLOW", "YOUTUBE", "TIKTOK", "MEDIA_UPLOAD", "OBSIDIAN_SYNC"])

    hb = WorkerHeartbeat(
        worker_id=worker_id,
        hostname_hash=hostname_hash,
        version=version,
        capabilities=capabilities,
        last_seen_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.record_heartbeat(hb)
    return 200, {"ok": True, "status": "HEARTBEAT_ACKNOWLEDGED"}


def handle_get_next_command(
    headers: Dict[str, str],
    worker_id: str,
    config: CloudConfig,
    db: Database
) -> Tuple[int, Dict[str, Any]]:
    """Handles GET /worker/commands/next (Atomically claims next pending command)."""
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    cmd = db.get_next_pending_command()
    if not cmd:
        return 200, {"ok": True, "command": None}

    # Atomically claim
    claimed = db.claim_command(cmd.command_id, worker_id)
    if claimed:
        cmd.status = CommandStatus.CLAIMED
        cmd.claimed_by = worker_id
        logger.info(f"[WORKER API] Command {cmd.command_id} ({cmd.type.value}) claimed by {worker_id}")
        return 200, {"ok": True, "command": cmd.to_dict()}

    return 200, {"ok": True, "command": None}


def handle_complete_command(
    headers: Dict[str, str],
    command_id: str,
    payload: Dict[str, Any],
    config: CloudConfig,
    db: Database
) -> Tuple[int, Dict[str, Any]]:
    """Handles POST /worker/commands/{command_id}/complete."""
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    status_str = payload.get("status", "COMPLETE")
    error_msg = payload.get("error_message")

    try:
        status_enum = CommandStatus(status_str)
    except ValueError:
        status_enum = CommandStatus.COMPLETE

    ok = db.complete_command(command_id, status_enum, error_msg)
    if ok:
        logger.info(f"[WORKER API] Command {command_id} marked as {status_str}")
        return 200, {"ok": True, "command_id": command_id, "status": status_str}

    return 404, {"ok": False, "error": "COMMAND_NOT_FOUND"}


def handle_sync_cloud_state(
    headers: Dict[str, str],
    config: CloudConfig,
    db: Database
) -> Tuple[int, Dict[str, Any]]:
    """Handles GET /worker/state/sync to mirror cloud data into local Obsidian vault."""
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    active_weeks = db.list_active_weeks()
    all_weeks_data = [w.to_dict() for w in active_weeks]

    # Collect approvals and Instagram jobs for active weeks
    approvals_data = []
    ig_jobs_data = []
    for w in active_weeks:
        appr = db.get_pending_approval_for_week(w.week_id)
        if appr:
            approvals_data.append(appr.to_dict())
        jobs = db.list_instagram_jobs_for_week(w.week_id)
        ig_jobs_data.extend([j.to_dict() for j in jobs])

    return 200, {
        "ok": True,
        "weeks": all_weeks_data,
        "approvals": approvals_data,
        "instagram_jobs": ig_jobs_data
    }


def handle_storage_self_test(
    headers: Dict[str, str],
    config: CloudConfig,
    storage: Optional[MediaStorageInterface] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Handles POST /worker/storage/self-test.
    Executes an end-to-end S3 round-trip test in private storage:
    PUT -> HEAD/exists -> metadata -> GET/download -> SHA256 match -> DELETE -> exists False.
    Guarantees cleanup of test object and temporary files.
    """
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    # Require explicit confirmation header
    confirm_hdr = (
        headers.get("X-Storage-Smoke-Test") or
        headers.get("x-storage-smoke-test") or
        headers.get("HTTP_X_STORAGE_SMOKE_TEST")
    )
    if str(confirm_hdr).strip().lower() not in ("true", "1", "yes"):
        return 400, {
            "ok": False,
            "error": "CONFIRMATION_REQUIRED",
            "message": "Header X-Storage-Smoke-Test: true is required"
        }

    adapter = storage or get_media_storage(config)
    if not adapter.is_ready():
        return 500, {
            "ok": False,
            "error": "STORAGE_NOT_READY",
            "message": "Storage adapter credentials or directory not ready"
        }

    test_id = uuid.uuid4().hex[:12]
    object_key = f"diagnostics/storage-smoke/{test_id}.bin"

    temp_dir = Path(tempfile.gettempdir()) / "storage_smoke_test"
    temp_dir.mkdir(parents=True, exist_ok=True)
    src_file = temp_dir / f"src_{test_id}.bin"
    dst_file = temp_dir / f"dst_{test_id}.bin"

    test_bytes = os.urandom(2048)
    src_file.write_bytes(test_bytes)
    initial_sha256 = compute_file_sha256(src_file)

    upload_ok = False
    exists_after_upload = False
    download_ok = False
    sha_match = False
    delete_ok = False
    exists_after_delete = True
    meta_size = 0

    try:
        # 1. PUT
        put_res = adapter.put_file(src_file, object_key, content_type="application/octet-stream")
        upload_ok = bool(put_res)

        # 2. HEAD / exists
        exists_after_upload = adapter.exists(object_key)

        # 3. Metadata
        metadata = adapter.get_metadata(object_key)
        meta_size = metadata.get("size_bytes", 0)

        # 4. GET / download
        download_ok = adapter.get_file(object_key, dst_file)

        # 5. SHA256 verify
        if download_ok and dst_file.exists():
            downloaded_sha = compute_file_sha256(dst_file)
            sha_match = (downloaded_sha == initial_sha256)

        # 6. DELETE
        delete_ok = adapter.delete_file(object_key)

        # 7. Final exists
        exists_after_delete = adapter.exists(object_key)

        overall_ok = (
            upload_ok
            and exists_after_upload
            and download_ok
            and sha_match
            and delete_ok
            and not exists_after_delete
        )

        return (200 if overall_ok else 500), {
            "ok": overall_ok,
            "status": "S3_ROUND_TRIP_PASS" if overall_ok else "S3_ROUND_TRIP_FAILED",
            "upload": upload_ok,
            "exists_after_upload": exists_after_upload,
            "download": download_ok,
            "sha256_match": sha_match,
            "delete": delete_ok,
            "exists_after_delete": exists_after_delete,
            "size_bytes": len(test_bytes),
            "storage_backend": config.media_storage_backend
        }

    except Exception as e:
        logger.error(f"[STORAGE SMOKE] Exception during round-trip test: {e}")
        return 500, {
            "ok": False,
            "error": "STORAGE_SELF_TEST_EXCEPTION",
            "message": str(e),
            "upload": upload_ok,
            "exists_after_upload": exists_after_upload,
            "download": download_ok,
            "sha256_match": sha_match,
            "delete": delete_ok,
            "exists_after_delete": exists_after_delete
        }

    finally:
        # Guarantee remote deletion
        try:
            if exists_after_upload and exists_after_delete:
                adapter.delete_file(object_key)
        except Exception:
            pass

        # Guarantee local temporary files deletion
        for f in (src_file, dst_file):
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
