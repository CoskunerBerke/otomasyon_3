"""
REST Handlers for Local Windows Worker Communication with Cloud Control Plane.
Protects endpoints with Worker API Key authentication.
Includes worker heartbeat, command dispatching, state sync, private storage self-test,
bounded multipart streaming MP4 upload, and safe diagnostic cleanup.
"""
import os
import re
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

WEEK_REGEX = re.compile(r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
REEL_REGEX = re.compile(r"^REEL-\d{4}-\d{4}$")
JOB_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]+$")


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


def stream_multipart_request(
    rfile: Any,
    content_length: int,
    content_type: str,
    max_file_size: int = 100 * 1024 * 1024,
    chunk_size: int = 65536
) -> Tuple[Dict[str, str], Optional[Path], Optional[str], int, str, Optional[str]]:
    """
    Streams multipart/form-data from rfile directly to disk in bounded chunks.
    Calculates SHA256 incrementally and enforces 100 MB max size during streaming.
    Returns (fields, temp_file_path, filename, file_size, calculated_sha256, error_code).
    """
    import hashlib

    match = re.search(r'boundary=([^;]+)', content_type, re.IGNORECASE)
    if not match:
        return {}, None, None, 0, "", "INVALID_MULTIPART_BOUNDARY"

    boundary = match.group(1).strip().strip('"').encode("utf-8")
    delimiter = b"--" + boundary

    temp_dir = Path(tempfile.gettempdir()) / "cloud_media_stream"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"stream_{uuid.uuid4().hex[:12]}.mp4"

    fields: Dict[str, str] = {}
    filename: Optional[str] = None
    file_size: int = 0
    hasher = hashlib.sha256()

    bytes_remaining = content_length
    buffer = b""

    def read_more():
        nonlocal buffer, bytes_remaining
        if bytes_remaining <= 0:
            return False
        read_sz = min(chunk_size, bytes_remaining)
        chunk = rfile.read(read_sz)
        if not chunk:
            return False
        bytes_remaining -= len(chunk)
        buffer += chunk
        return True

    while delimiter not in buffer:
        if not read_more():
            break

    idx = buffer.find(delimiter)
    if idx == -1:
        return {}, None, None, 0, "", "MULTIPART_DELIMITER_NOT_FOUND"

    buffer = buffer[idx + len(delimiter):]
    out_file = None

    try:
        while True:
            if buffer.startswith(b"\r\n"):
                buffer = buffer[2:]
            elif buffer.startswith(b"--"):
                break

            while b"\r\n\r\n" not in buffer:
                if not read_more():
                    break

            if b"\r\n\r\n" not in buffer:
                break

            hdr_end = buffer.find(b"\r\n\r\n")
            header_bytes = buffer[:hdr_end]
            buffer = buffer[hdr_end + 4:]

            header_str = header_bytes.decode("latin-1", errors="replace")
            is_file = False
            part_name = ""
            part_filename = None

            for line in header_str.split("\r\n"):
                if line.lower().startswith("content-disposition:"):
                    name_match = re.search(r'name="([^"]+)"', line, re.IGNORECASE)
                    if name_match:
                        part_name = name_match.group(1)
                    fname_match = re.search(r'filename="([^"]+)"', line, re.IGNORECASE)
                    if fname_match:
                        part_filename = fname_match.group(1)
                        is_file = True

            if is_file:
                filename = part_filename
                out_file = open(temp_path, "wb")
                search_boundary = b"\r\n" + delimiter

                while True:
                    b_idx = buffer.find(search_boundary)
                    if b_idx != -1:
                        data_chunk = buffer[:b_idx]
                        file_size += len(data_chunk)
                        if file_size > max_file_size:
                            out_file.close()
                            if temp_path.exists():
                                temp_path.unlink()
                            return {}, None, None, 0, "", "MEDIA_TOO_LARGE"
                        hasher.update(data_chunk)
                        out_file.write(data_chunk)
                        buffer = buffer[b_idx + len(search_boundary):]
                        break
                    else:
                        safe_len = len(buffer) - len(search_boundary)
                        if safe_len > 0:
                            data_chunk = buffer[:safe_len]
                            file_size += len(data_chunk)
                            if file_size > max_file_size:
                                out_file.close()
                                if temp_path.exists():
                                    temp_path.unlink()
                                return {}, None, None, 0, "", "MEDIA_TOO_LARGE"
                            hasher.update(data_chunk)
                            out_file.write(data_chunk)
                            buffer = buffer[safe_len:]
                        if not read_more():
                            break
                out_file.close()
                out_file = None
            else:
                search_boundary = b"\r\n" + delimiter
                field_val_bytes = b""
                while True:
                    b_idx = buffer.find(search_boundary)
                    if b_idx != -1:
                        field_val_bytes += buffer[:b_idx]
                        buffer = buffer[b_idx + len(search_boundary):]
                        break
                    else:
                        safe_len = len(buffer) - len(search_boundary)
                        if safe_len > 0:
                            field_val_bytes += buffer[:safe_len]
                            buffer = buffer[safe_len:]
                        if not read_more():
                            field_val_bytes += buffer
                            buffer = b""
                            break
                fields[part_name] = field_val_bytes.decode("utf-8", errors="replace")

        while bytes_remaining > 0:
            chunk = rfile.read(min(chunk_size, bytes_remaining))
            if not chunk:
                break
            bytes_remaining -= len(chunk)

        calculated_sha = hasher.hexdigest().lower() if filename else ""
        return fields, temp_path, filename, file_size, calculated_sha, None

    except Exception as e:
        if out_file:
            try:
                out_file.close()
            except Exception:
                pass
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        return {}, None, None, 0, "", f"STREAM_ERROR: {e}"


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
        put_res = adapter.put_file(src_file, object_key, content_type="application/octet-stream")
        upload_ok = bool(put_res)
        exists_after_upload = adapter.exists(object_key)
        metadata = adapter.get_metadata(object_key)
        meta_size = metadata.get("size_bytes", 0)
        download_ok = adapter.get_file(object_key, dst_file)

        if download_ok and dst_file.exists():
            downloaded_sha = compute_file_sha256(dst_file)
            sha_match = (downloaded_sha == initial_sha256)

        delete_ok = adapter.delete_file(object_key)
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
            "upload": upload_ok,
            "exists_after_upload": exists_after_upload,
            "download": download_ok,
            "sha256_match": sha_match,
            "delete": delete_ok,
            "exists_after_delete": exists_after_delete
        }

    finally:
        try:
            if exists_after_upload and exists_after_delete:
                adapter.delete_file(object_key)
        except Exception:
            pass

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
    Supports bounded streaming temp-files, validates strict identifiers and file size,
    verifies SHA256 integrity, uploads to private S3 deterministically,
    and registers InstagramScheduledJob with status MEDIA_READY in PostgreSQL.
    """
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    fields = {}
    temp_file: Optional[Path] = None
    filename = ""
    file_size = 0
    server_sha256 = ""
    is_streamed = False

    if "__stream_file_path__" in payload:
        # Received via bounded streaming
        fields = payload.get("__fields__", {})
        temp_file = Path(payload["__stream_file_path__"])
        filename = payload.get("__filename__", "video.mp4")
        file_size = payload.get("__file_size__", 0)
        server_sha256 = payload.get("__calculated_sha256__", "")
        is_streamed = True
    else:
        # Direct dictionary payload / unit test mock
        fields = payload
        filename = payload.get("filename", "video.mp4")
        raw_file = payload.get("file", b"")
        if isinstance(raw_file, str):
            raw_file = raw_file.encode("utf-8")

        file_size = len(raw_file)
        if file_size > 100 * 1024 * 1024:
            return 413, {"ok": False, "error": "MEDIA_TOO_LARGE"}

        if file_size > 0:
            temp_dir = Path(tempfile.gettempdir()) / "cloud_media_uploads"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file = temp_dir / f"upload_{uuid.uuid4().hex[:12]}.mp4"
            temp_file.write_bytes(raw_file)
            server_sha256 = compute_file_sha256(temp_file).lower()

    week_id = str(fields.get("week_id", "")).strip()
    reel_id = str(fields.get("reel_id", "")).strip()
    scheduled_at_local = str(fields.get("scheduled_at_local", "")).strip()
    scheduled_at_utc = str(fields.get("scheduled_at_utc", "")).strip()
    timezone_str = str(fields.get("timezone", config.timezone_str or "Europe/Istanbul")).strip()
    caption = str(fields.get("caption", "")).strip()
    client_sha256 = str(fields.get("media_sha256", "")).strip().lower()
    job_id = str(fields.get("job_id", "")).strip() or f"JOB-{week_id}-{reel_id}"

    # Strict week_id validation: ^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$
    if not WEEK_REGEX.match(week_id):
        if temp_file and temp_file.exists():
            temp_file.unlink()
        return 400, {"ok": False, "error": "INVALID_WEEK_ID"}

    # Strict reel_id validation: ^REEL-\d{4}-\d{4}$
    if not REEL_REGEX.match(reel_id):
        if temp_file and temp_file.exists():
            temp_file.unlink()
        return 400, {"ok": False, "error": "INVALID_REEL_ID"}

    # Strict job_id validation
    if not JOB_ID_REGEX.match(job_id) or len(job_id) > 64:
        if temp_file and temp_file.exists():
            temp_file.unlink()
        return 400, {"ok": False, "error": "INVALID_JOB_ID"}

    # Filename validation
    if not filename.lower().endswith(".mp4"):
        if temp_file and temp_file.exists():
            temp_file.unlink()
        return 400, {"ok": False, "error": "INVALID_MEDIA_FORMAT"}

    # File size validation
    if file_size == 0 or not temp_file or not temp_file.exists():
        if temp_file and temp_file.exists():
            temp_file.unlink()
        return 400, {"ok": False, "error": "MEDIA_EMPTY"}

    if file_size > 100 * 1024 * 1024:
        if temp_file.exists():
            temp_file.unlink()
        return 413, {"ok": False, "error": "MEDIA_TOO_LARGE"}

    # SHA256 verification
    if not client_sha256 or client_sha256 != server_sha256:
        if temp_file.exists():
            temp_file.unlink()
        return 400, {"ok": False, "error": "MEDIA_SHA256_MISMATCH"}

    # Deterministic object key
    object_key = f"media/{week_id}/{reel_id}/{server_sha256}.mp4"

    # Pre-check existing PostgreSQL job
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
            return 409, {"ok": False, "error": "JOB_ALREADY_ADVANCED"}

        if existing_job.media_sha256 and existing_job.media_sha256.lower() != server_sha256:
            if temp_file.exists():
                temp_file.unlink()
            return 409, {"ok": False, "error": "MEDIA_CONFLICT"}

    adapter = storage or get_media_storage(config)
    if not adapter.is_ready():
        if temp_file.exists():
            temp_file.unlink()
        return 500, {"ok": False, "error": "STORAGE_NOT_READY"}

    newly_created_s3_object = False
    try:
        if adapter.exists(object_key):
            is_idempotent = True
        else:
            adapter.put_file(temp_file, object_key, content_type="video/mp4")
            newly_created_s3_object = True
            is_idempotent = False

        exists_verified = adapter.exists(object_key)
        if not exists_verified:
            return 500, {"ok": False, "error": "STORAGE_VERIFICATION_FAILED"}

        meta = adapter.get_metadata(object_key)
        if meta and meta.get("size_bytes") and meta.get("size_bytes") != file_size:
            return 500, {"ok": False, "error": "STORAGE_VERIFICATION_FAILED"}

        if existing_job and existing_job.status == InstagramJobStatus.MEDIA_READY and existing_job.media_sha256 == server_sha256:
            return 200, {
                "ok": True,
                "status": "MEDIA_READY",
                "job_id": existing_job.job_id,
                "week_id": existing_job.week_id,
                "reel_id": existing_job.reel_id,
                "media_object_key": existing_job.media_object_key,
                "media_sha256": existing_job.media_sha256,
                "size_bytes": file_size,
                "storage_verified": True,
                "idempotent": True
            }

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
            if newly_created_s3_object:
                try:
                    adapter.delete_file(object_key)
                except Exception:
                    pass
            return 500, {"ok": False, "error": "DATABASE_SAVE_FAILED"}

        return 200, {
            "ok": True,
            "status": "MEDIA_READY",
            "job_id": job.job_id,
            "week_id": job.week_id,
            "reel_id": job.reel_id,
            "media_object_key": job.media_object_key,
            "media_sha256": job.media_sha256,
            "size_bytes": file_size,
            "storage_verified": True,
            "idempotent": is_idempotent
        }

    finally:
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass


def handle_diagnostic_cleanup(
    headers: Dict[str, str],
    payload: Dict[str, Any],
    config: CloudConfig,
    db: Database,
    storage: Optional[MediaStorageInterface] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Handles POST /worker/media/diagnostic-cleanup.
    Narrowly restricted to deleting ONLY test jobs where:
    - job_id begins with 'DIAG-HANDOFF-'
    - status == MEDIA_READY
    - remote_media_id is empty/null
    - container_id is empty/null
    - published_at is empty/null
    Deletes the exact S3 object and DB row.
    """
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    job_id = str(payload.get("job_id", "")).strip()
    if not job_id.startswith("DIAG-HANDOFF-"):
        return 403, {
            "ok": False,
            "error": "DIAGNOSTIC_CLEANUP_NOT_ALLOWED",
            "message": "Only diagnostic jobs starting with 'DIAG-HANDOFF-' may be cleaned up."
        }

    job = db.get_instagram_job(job_id)
    if not job:
        return 404, {
            "ok": False,
            "error": "JOB_NOT_FOUND",
            "message": f"Job {job_id} not found."
        }

    if (
        job.status != InstagramJobStatus.MEDIA_READY
        or bool(job.remote_media_id)
        or bool(job.container_id)
        or bool(job.published_at)
    ):
        return 403, {
            "ok": False,
            "error": "DIAGNOSTIC_CLEANUP_NOT_ALLOWED",
            "message": f"Job {job_id} is in status {job.status.value} and cannot be cleaned via diagnostic API."
        }

    adapter = storage or get_media_storage(config)
    s3_deleted = False

    if job.media_object_key:
        try:
            adapter.delete_file(job.media_object_key)
            s3_deleted = not adapter.exists(job.media_object_key)
        except Exception as e:
            logger.error(f"[DIAG CLEANUP] Error deleting S3 object {job.media_object_key}: {e}")
            s3_deleted = False
    else:
        s3_deleted = True

    db_deleted = db.delete_instagram_job(job_id)

    return 200, {
        "ok": True,
        "status": "DIAGNOSTIC_CLEANED",
        "job_id": job_id,
        "s3_deleted": s3_deleted,
        "db_deleted": db_deleted
    }
