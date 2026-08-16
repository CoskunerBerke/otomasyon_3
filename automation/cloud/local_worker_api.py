"""
REST Handlers for Local Windows Worker Communication with Cloud Control Plane.
Protects endpoints with Worker API Key authentication.
Includes worker heartbeat, command dispatching, state sync, private storage self-test,
and authenticated MP4 media upload with S3 storage and Instagram job registration.
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
    CommandStatus,
    InstagramScheduledJob,
    InstagramJobStatus
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


def _parse_multipart_form(raw_body: bytes, content_type: str) -> Tuple[Dict[str, str], Optional[Tuple[str, str, bytes]]]:
    """
    Parses multipart/form-data into form fields and a file tuple (filename, content_type, file_bytes).
    Returns (form_fields_dict, file_info_or_None).
    """
    from email.parser import BytesParser
    from email.policy import default

    header_bytes = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
    msg = BytesParser(policy=default).parsebytes(header_bytes + raw_body)

    fields = {}
    file_info = None

    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        if filename:
            file_bytes = part.get_payload(decode=True) or b""
            part_content_type = part.get_content_type()
            file_info = (filename, part_content_type, file_bytes)
        elif name:
            val_bytes = part.get_payload(decode=True) or b""
            try:
                fields[name] = val_bytes.decode("utf-8")
            except Exception:
                fields[name] = val_bytes.decode("latin-1", errors="replace")

    return fields, file_info


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


def handle_media_upload(
    headers: Dict[str, str],
    payload: Dict[str, Any],
    config: CloudConfig,
    db: Database,
    storage: Optional[MediaStorageInterface] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Handles POST /worker/media/upload.
    Receives finalized MP4 file via multipart/form-data or dict payload,
    validates size, extension, SHA256 integrity, uploads to private S3 deterministically,
    and registers InstagramScheduledJob with status MEDIA_READY in PostgreSQL.
    """
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    # Extract multipart fields and file
    file_bytes = b""
    filename = ""
    fields = {}

    if "__raw_multipart__" in payload:
        raw_mp = payload["__raw_multipart__"]
        ct = payload.get("__content_type__", "")
        fields, file_info = _parse_multipart_form(raw_mp, ct)
        if file_info:
            filename, _, file_bytes = file_info
    else:
        fields = payload
        file_bytes = payload.get("file", b"")
        filename = payload.get("filename", "video.mp4")

    # If file_bytes is str (e.g. mock or json), encode to bytes
    if isinstance(file_bytes, str):
        file_bytes = file_bytes.encode("utf-8")

    week_id = str(fields.get("week_id", "")).strip()
    reel_id = str(fields.get("reel_id", "")).strip()
    scheduled_at_local = str(fields.get("scheduled_at_local", "")).strip()
    scheduled_at_utc = str(fields.get("scheduled_at_utc", "")).strip()
    timezone_str = str(fields.get("timezone", config.timezone_str or "Europe/Istanbul")).strip()
    caption = str(fields.get("caption", "")).strip()
    client_sha256 = str(fields.get("media_sha256", "")).strip().lower()
    job_id = str(fields.get("job_id", "")).strip() or f"JOB-{week_id}-{reel_id}"

    # Validation: week_id and reel_id (no traversal, no slashes)
    if not week_id or "/" in week_id or "\\" in week_id or ".." in week_id:
        return 400, {"ok": False, "error": "INVALID_WEEK_ID", "message": "Invalid or unsafe week_id"}
    if not reel_id or "/" in reel_id or "\\" in reel_id or ".." in reel_id:
        return 400, {"ok": False, "error": "INVALID_REEL_ID", "message": "Invalid or unsafe reel_id"}

    # Validation: filename must end in .mp4
    if not filename.lower().endswith(".mp4"):
        return 400, {"ok": False, "error": "INVALID_MEDIA_FORMAT", "message": "File must end in .mp4"}

    # Validation: file size
    if not file_bytes or len(file_bytes) == 0:
        return 400, {"ok": False, "error": "MEDIA_EMPTY", "message": "Uploaded media file is empty"}

    max_size = 100 * 1024 * 1024  # 100 MB
    if len(file_bytes) > max_size:
        return 413, {"ok": False, "error": "MEDIA_TOO_LARGE", "message": "File exceeds maximum 100 MB limit"}

    # Write to local temp file to compute server SHA256
    temp_dir = Path(tempfile.gettempdir()) / "cloud_media_uploads"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"upload_{uuid.uuid4().hex[:12]}.mp4"

    temp_file.write_bytes(file_bytes)
    server_sha256 = compute_file_sha256(temp_file).lower()

    if not client_sha256 or client_sha256 != server_sha256:
        if temp_file.exists():
            temp_file.unlink()
        return 400, {
            "ok": False,
            "error": "MEDIA_SHA256_MISMATCH",
            "message": f"Calculated SHA256 ({server_sha256}) did not match provided SHA256 ({client_sha256})"
        }

    # Deterministic object key (strictly without traversal)
    object_key = f"media/{week_id}/{reel_id}/{server_sha256}.mp4"

    # Pre-check existing PostgreSQL job for conflicts or advanced state
    existing_job = db.get_instagram_job(job_id)
    if existing_job:
        adv_statuses = {
            InstagramJobStatus.PUBLISHED,
            InstagramJobStatus.REMOTE_VERIFIED,
            InstagramJobStatus.PUBLISHING,
            InstagramJobStatus.UPLOADING_TO_META,
            InstagramJobStatus.PROCESSING,
            InstagramJobStatus.READY_TO_PUBLISH,
            InstagramJobStatus.PREPARING
        }
        if existing_job.status in adv_statuses:
            if temp_file.exists():
                temp_file.unlink()
            return 409, {
                "ok": False,
                "error": "JOB_ALREADY_ADVANCED",
                "message": f"Job {job_id} is already in state {existing_job.status.value} and cannot be reset to MEDIA_READY."
            }

        if existing_job.media_sha256 and existing_job.media_sha256.lower() != server_sha256:
            if temp_file.exists():
                temp_file.unlink()
            return 409, {
                "ok": False,
                "error": "MEDIA_CONFLICT",
                "message": f"Job {job_id} already exists with different media SHA ({existing_job.media_sha256})."
            }

    adapter = storage or get_media_storage(config)
    if not adapter.is_ready():
        if temp_file.exists():
            temp_file.unlink()
        return 500, {"ok": False, "error": "STORAGE_NOT_READY", "message": "Media storage backend is not ready"}

    newly_created_s3_object = False
    try:
        # Check if exact S3 object exists (Idempotency)
        if adapter.exists(object_key):
            is_idempotent = True
        else:
            adapter.put_file(temp_file, object_key, content_type="video/mp4")
            newly_created_s3_object = True
            is_idempotent = False

        # Verify storage
        exists_verified = adapter.exists(object_key)
        if not exists_verified:
            return 500, {"ok": False, "error": "STORAGE_VERIFICATION_FAILED", "message": "Object not found in storage after upload"}

        meta = adapter.get_metadata(object_key)
        if meta and meta.get("size_bytes") and meta.get("size_bytes") != len(file_bytes):
            return 500, {"ok": False, "error": "STORAGE_VERIFICATION_FAILED", "message": "Storage object size mismatch"}

        # If existing job is already MEDIA_READY with same sha, return idempotent success
        if existing_job and existing_job.status == InstagramJobStatus.MEDIA_READY and existing_job.media_sha256 == server_sha256:
            return 200, {
                "ok": True,
                "status": "MEDIA_READY",
                "job_id": existing_job.job_id,
                "week_id": existing_job.week_id,
                "reel_id": existing_job.reel_id,
                "media_object_key": existing_job.media_object_key,
                "media_sha256": existing_job.media_sha256,
                "size_bytes": len(file_bytes),
                "storage_verified": True,
                "idempotent": True
            }

        # Create or update InstagramScheduledJob
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        job = InstagramScheduledJob(
            job_id=job_id,
            week_id=week_id,
            reel_id=reel_id,
            scheduled_at_local=scheduled_at_local,
            scheduled_at_utc=scheduled_at_utc,
            timezone=timezone_str,
            media_object_key=object_key,
            media_sha256=server_sha256,
            caption=caption,
            status=InstagramJobStatus.MEDIA_READY,
            created_at=existing_job.created_at if existing_job else now_str,
            updated_at=now_str
        )

        try:
            db.save_instagram_job(job)
        except Exception as db_err:
            logger.error(f"[MEDIA UPLOAD] Failed to save Instagram job to database: {db_err}")
            # Rollback: if we created a new S3 object in this request, delete it
            if newly_created_s3_object:
                try:
                    adapter.delete_file(object_key)
                except Exception:
                    pass
            return 500, {
                "ok": False,
                "error": "DATABASE_SAVE_FAILED",
                "message": f"Failed to persist job to database: {db_err}"
            }

        return 200, {
            "ok": True,
            "status": "MEDIA_READY",
            "job_id": job.job_id,
            "week_id": job.week_id,
            "reel_id": job.reel_id,
            "media_object_key": job.media_object_key,
            "media_sha256": job.media_sha256,
            "size_bytes": len(file_bytes),
            "storage_verified": True,
            "idempotent": is_idempotent
        }

    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
