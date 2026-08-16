"""
Comprehensive Unit Test Suite for Local MP4 -> Railway S3 -> Instagram MEDIA_READY Handoff.
Tests bounded multipart streaming, strict regex validation, SHA256 integrity checks,
deterministic object keys, storage verification, PostgreSQL InstagramScheduledJob registration,
idempotency, conflict protection, error rollbacks, temp cleanup, diagnostic cleanup, and live smoke test helper.
Uses strict mocks only: 0 real S3 writes, 0 real video publishing, 0 real generation.
"""
import io
import os
import json
import hashlib
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.cloud.config import CloudConfig
from automation.cloud.database import Database
from automation.cloud.models import InstagramScheduledJob, InstagramJobStatus
from automation.cloud.local_worker_api import (
    handle_media_upload,
    handle_diagnostic_cleanup,
    stream_multipart_request
)
from automation.cloud.app import CloudApp
from automation.local_worker_cloud_client import LocalWorkerCloudClient
from automation.media_handoff import handoff_reel_to_cloud
from automation.media_handoff_live_smoke_test import run_media_handoff_smoke_test


# =============================================================================
# 1. AUTHENTICATION & INPUT VALIDATION TESTS
# =============================================================================

def test_media_upload_requires_worker_api_auth(tmp_path):
    """Test 1 & 2: /worker/media/upload requires valid X-Worker-Api-Key header."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    # Missing header -> 401
    code, resp = handle_media_upload({}, {}, cfg, db)
    assert code == 401
    assert resp["error"] == "UNAUTHORIZED_WORKER_KEY"

    # Wrong key -> 401
    code, resp = handle_media_upload({"X-Worker-Api-Key": "wrong_key"}, {}, cfg, db)
    assert code == 401
    assert resp["error"] == "UNAUTHORIZED_WORKER_KEY"


def test_media_upload_rejects_non_mp4_extension(tmp_path):
    """Test 3: Reject non-mp4 files."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    payload = {
        "file": b"dummy data",
        "filename": "video.mov",
        "week_id": "2026-W34",
        "reel_id": "REEL-2026-0011",
        "media_sha256": hashlib.sha256(b"dummy data").hexdigest()
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 400
    assert resp["error"] == "INVALID_MEDIA_FORMAT"


def test_media_upload_rejects_empty_file(tmp_path):
    """Test 4: Reject empty (0 byte) file."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    payload = {
        "file": b"",
        "filename": "empty.mp4",
        "week_id": "2026-W34",
        "reel_id": "REEL-2026-0011",
        "media_sha256": hashlib.sha256(b"").hexdigest()
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 400
    assert resp["error"] == "MEDIA_EMPTY"


def test_media_upload_rejects_oversized_file(tmp_path):
    """Test 5: Reject files > 100 MB."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    large_payload = b"x" * (100 * 1024 * 1024 + 10)
    payload = {
        "file": large_payload,
        "filename": "large.mp4",
        "week_id": "2026-W34",
        "reel_id": "REEL-2026-0011",
        "media_sha256": "fake_sha"
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 413
    assert resp["error"] == "MEDIA_TOO_LARGE"


def test_media_upload_rejects_sha256_mismatch(tmp_path):
    """Test 6: Reject when client-provided SHA256 does not match server-calculated SHA256."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    mock_storage = MagicMock()

    payload = {
        "file": b"actual video content 123",
        "filename": "test.mp4",
        "week_id": "2026-W34",
        "reel_id": "REEL-2026-0011",
        "media_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    code, resp = handle_media_upload(headers, payload, cfg, db, storage=mock_storage)
    assert code == 400
    assert resp["error"] == "MEDIA_SHA256_MISMATCH"
    mock_storage.put_file.assert_not_called()


def test_media_upload_strict_regex_validation(tmp_path):
    """Test 7 & 8: Strict regex validation for week_id, reel_id, and job_id."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    sample_bytes = b"safe video bytes"
    sha = hashlib.sha256(sample_bytes).hexdigest()

    # Invalid week_id (fails ^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$)
    payload = {
        "file": sample_bytes,
        "filename": "test.mp4",
        "week_id": "invalid-week",
        "reel_id": "REEL-2026-0011",
        "media_sha256": sha
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}
    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 400
    assert resp["error"] == "INVALID_WEEK_ID"

    # Invalid reel_id (fails ^REEL-\d{4}-\d{4}$)
    payload["week_id"] = "2026-W34"
    payload["reel_id"] = "BAD_REEL_NAME"
    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 400
    assert resp["error"] == "INVALID_REEL_ID"

    # Invalid job_id
    payload["reel_id"] = "REEL-2026-0011"
    payload["job_id"] = "bad/job/path"
    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 400
    assert resp["error"] == "INVALID_JOB_ID"


# =============================================================================
# 2. BOUNDED MULTIPART STREAMING TESTS
# =============================================================================

def test_stream_multipart_request_bounded_chunks():
    """Test: stream_multipart_request reads in chunks and writes directly to disk with SHA."""
    boundary = "----WebKitFormBoundaryXYZ"
    video_content = b"streaming mp4 video content test bytes"
    expected_sha = hashlib.sha256(video_content).hexdigest()

    raw_multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="week_id"\r\n\r\n'
        f"2026-W34\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="reel_id"\r\n\r\n'
        f"REEL-2026-0011\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="video.mp4"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8") + video_content + f"\r\n--{boundary}--\r\n".encode("utf-8")

    stream = io.BytesIO(raw_multipart)
    content_type = f"multipart/form-data; boundary={boundary}"

    fields, temp_path, filename, file_size, calculated_sha, err = stream_multipart_request(
        stream, len(raw_multipart), content_type, chunk_size=16
    )

    assert err is None
    assert fields["week_id"] == "2026-W34"
    assert fields["reel_id"] == "REEL-2026-0011"
    assert filename == "video.mp4"
    assert file_size == len(video_content)
    assert calculated_sha == expected_sha
    assert temp_path.exists()

    # Cleanup temp
    temp_path.unlink()


def test_stream_multipart_request_exceeds_max_size_cleans_up():
    """Test: stream_multipart_request aborts and deletes partial file if limit exceeded."""
    boundary = "----WebKitBoundaryLimit"
    large_chunk = b"A" * 1024

    raw_multipart = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="video.mp4"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode("utf-8") + large_chunk + f"\r\n--{boundary}--\r\n".encode("utf-8")

    stream = io.BytesIO(raw_multipart)
    content_type = f"multipart/form-data; boundary={boundary}"

    # Set max_file_size to 500 bytes (< 1024 bytes)
    fields, temp_path, filename, file_size, calculated_sha, err = stream_multipart_request(
        stream, len(raw_multipart), content_type, max_file_size=500, chunk_size=64
    )

    assert err == "MEDIA_TOO_LARGE"
    assert temp_path is None or not temp_path.exists()


# =============================================================================
# 3. S3 STORAGE & INSTAGRAM JOB REGISTRATION TESTS
# =============================================================================

def test_media_upload_successful_first_upload(tmp_path):
    """Test 9, 11, 12, 13, 14, 15: Successful upload puts file in S3, verifies, and saves job as MEDIA_READY."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    video_data = b"real mp4 video frame bytes"
    sha = hashlib.sha256(video_data).hexdigest()

    mock_storage = MagicMock()
    mock_storage.is_ready.return_value = True
    mock_storage.exists.side_effect = [False, True]  # exists before upload: False, exists after upload: True
    mock_storage.put_file.return_value = f"media/2026-W34/REEL-2026-0011/{sha}.mp4"
    mock_storage.get_metadata.return_value = {"size_bytes": len(video_data), "etag": "etag_123"}

    payload = {
        "file": video_data,
        "filename": "REEL-2026-0011.mp4",
        "week_id": "2026-W34",
        "reel_id": "REEL-2026-0011",
        "scheduled_at_local": "2026-08-17 19:30:00",
        "scheduled_at_utc": "2026-08-17 16:30:00",
        "timezone": "Europe/Istanbul",
        "caption": "Test AI Reel Caption",
        "media_sha256": sha
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    code, resp = handle_media_upload(headers, payload, cfg, db, storage=mock_storage)
    assert code == 200
    assert resp["ok"] is True
    assert resp["status"] == "MEDIA_READY"
    assert resp["media_object_key"] == f"media/2026-W34/REEL-2026-0011/{sha}.mp4"
    assert resp["media_sha256"] == sha
    assert resp["idempotent"] is False
    assert resp["storage_verified"] is True

    # Verify S3 put was called with deterministic key
    mock_storage.put_file.assert_called_once()
    args, kwargs = mock_storage.put_file.call_args
    assert args[1] == f"media/2026-W34/REEL-2026-0011/{sha}.mp4"

    # Verify PostgreSQL job was persisted
    job = db.get_instagram_job("JOB-2026-W34-REEL-2026-0011")
    assert job is not None
    assert job.status == InstagramJobStatus.MEDIA_READY
    assert job.media_object_key == f"media/2026-W34/REEL-2026-0011/{sha}.mp4"
    assert job.media_sha256 == sha
    assert job.caption == "Test AI Reel Caption"


def test_media_upload_idempotent_when_s3_and_job_exist(tmp_path):
    """Test 10 & 16: When exact object and MEDIA_READY job already exist, return idempotent success."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    video_data = b"idempotent video bytes"
    sha = hashlib.sha256(video_data).hexdigest()
    object_key = f"media/2026-W34/REEL-2026-0011/{sha}.mp4"

    pre_job = InstagramScheduledJob(
        job_id="JOB-2026-W34-REEL-2026-0011",
        week_id="2026-W34",
        reel_id="REEL-2026-0011",
        scheduled_at_local="2026-08-17 19:30:00",
        scheduled_at_utc="2026-08-17 16:30:00",
        timezone="Europe/Istanbul",
        media_object_key=object_key,
        media_sha256=sha,
        caption="Existing caption",
        status=InstagramJobStatus.MEDIA_READY
    )
    db.save_instagram_job(pre_job)

    mock_storage = MagicMock()
    mock_storage.is_ready.return_value = True
    mock_storage.exists.return_value = True
    mock_storage.get_metadata.return_value = {"size_bytes": len(video_data)}

    payload = {
        "file": video_data,
        "filename": "REEL-2026-0011.mp4",
        "week_id": "2026-W34",
        "reel_id": "REEL-2026-0011",
        "scheduled_at_local": "2026-08-17 19:30:00",
        "scheduled_at_utc": "2026-08-17 16:30:00",
        "media_sha256": sha
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    code, resp = handle_media_upload(headers, payload, cfg, db, storage=mock_storage)
    assert code == 200
    assert resp["ok"] is True
    assert resp["idempotent"] is True
    mock_storage.put_file.assert_not_called()


def test_media_upload_rejects_conflicting_sha(tmp_path):
    """Test 17: Existing job with DIFFERENT SHA returns 409 MEDIA_CONFLICT."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    pre_job = InstagramScheduledJob(
        job_id="JOB-2026-W34-REEL-2026-0011",
        week_id="2026-W34",
        reel_id="REEL-2026-0011",
        scheduled_at_local="2026-08-17 19:30:00",
        scheduled_at_utc="2026-08-17 16:30:00",
        timezone="Europe/Istanbul",
        media_object_key="media/2026-W34/REEL-2026-0011/old_sha.mp4",
        media_sha256="old_sha_1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        caption="Old caption",
        status=InstagramJobStatus.WAITING_FOR_MEDIA
    )
    db.save_instagram_job(pre_job)

    new_video = b"brand new different video"
    new_sha = hashlib.sha256(new_video).hexdigest()

    payload = {
        "file": new_video,
        "filename": "REEL-2026-0011.mp4",
        "week_id": "2026-W34",
        "reel_id": "REEL-2026-0011",
        "scheduled_at_local": "2026-08-17 19:30:00",
        "scheduled_at_utc": "2026-08-17 16:30:00",
        "media_sha256": new_sha
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 409
    assert resp["error"] == "MEDIA_CONFLICT"


def test_media_upload_protects_advanced_jobs(tmp_path):
    """Test 18: Existing job in PUBLISHED / REMOTE_VERIFIED / PUBLISHING state returns 409 JOB_ALREADY_ADVANCED."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    video = b"sample video bytes"
    sha = hashlib.sha256(video).hexdigest()

    for adv_status in (InstagramJobStatus.PUBLISHED, InstagramJobStatus.REMOTE_VERIFIED, InstagramJobStatus.PUBLISHING):
        pre_job = InstagramScheduledJob(
            job_id=f"JOB-2026-W34-REEL-2026-{adv_status.value}",
            week_id="2026-W34",
            reel_id="REEL-2026-0011",
            scheduled_at_local="2026-08-17 19:30:00",
            scheduled_at_utc="2026-08-17 16:30:00",
            timezone="Europe/Istanbul",
            media_object_key="media/test.mp4",
            media_sha256=sha,
            caption="Advanced caption",
            status=adv_status
        )
        db.save_instagram_job(pre_job)

        payload = {
            "file": video,
            "filename": "video.mp4",
            "week_id": "2026-W34",
            "reel_id": "REEL-2026-0011",
            "job_id": f"JOB-2026-W34-REEL-2026-{adv_status.value}",
            "scheduled_at_local": "2026-08-17 19:30:00",
            "scheduled_at_utc": "2026-08-17 16:30:00",
            "media_sha256": sha
        }
        headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

        code, resp = handle_media_upload(headers, payload, cfg, db)
        assert code == 409
        assert resp["error"] == "JOB_ALREADY_ADVANCED"


def test_media_upload_db_failure_rolls_back_new_s3_object(tmp_path):
    """Test 19 & 20: DB failure after a NEW S3 upload triggers S3 delete rollback."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"

    mock_db = MagicMock()
    mock_db.get_instagram_job.return_value = None
    mock_db.save_instagram_job.side_effect = Exception("DB Connection Lost")

    video = b"rollback test video"
    sha = hashlib.sha256(video).hexdigest()

    mock_storage = MagicMock()
    mock_storage.is_ready.return_value = True
    mock_storage.exists.side_effect = [False, True]
    mock_storage.get_metadata.return_value = {"size_bytes": len(video)}
    mock_storage.delete_file.return_value = True

    payload = {
        "file": video,
        "filename": "test.mp4",
        "week_id": "2026-W34",
        "reel_id": "REEL-2026-0011",
        "scheduled_at_local": "2026-08-17 19:30:00",
        "scheduled_at_utc": "2026-08-17 16:30:00",
        "media_sha256": sha
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    code, resp = handle_media_upload(headers, payload, cfg, mock_db, storage=mock_storage)
    assert code == 500
    assert resp["error"] == "DATABASE_SAVE_FAILED"
    # S3 cleanup called on rollback
    mock_storage.delete_file.assert_called_once_with(f"media/2026-W34/REEL-2026-0011/{sha}.mp4")


# =============================================================================
# 4. DIAGNOSTIC CLEANUP ENDPOINT TESTS
# =============================================================================

def test_diagnostic_cleanup_auth_and_restrictions(tmp_path):
    """Test: /worker/media/diagnostic-cleanup strictly enforces auth, prefix, and non-advanced state."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    # 1. Invalid auth -> 401
    code, resp = handle_diagnostic_cleanup({"X-Worker-Api-Key": "wrong"}, {}, cfg, db)
    assert code == 401

    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    # 2. Non-diagnostic job ID -> 403
    code, resp = handle_diagnostic_cleanup(headers, {"job_id": "JOB-2026-W34-REEL-2026-0011"}, cfg, db)
    assert code == 403
    assert resp["error"] == "DIAGNOSTIC_CLEANUP_NOT_ALLOWED"

    # 3. Non-existent job -> 404
    code, resp = handle_diagnostic_cleanup(headers, {"job_id": "DIAG-HANDOFF-notfound123"}, cfg, db)
    assert code == 404
    assert resp["error"] == "JOB_NOT_FOUND"

    # 4. Diagnostic job with advanced status -> 403
    adv_job = InstagramScheduledJob(
        job_id="DIAG-HANDOFF-adv123",
        week_id="2099-W52",
        reel_id="REEL-2099-9999",
        scheduled_at_local="2099-12-28 19:30:00",
        scheduled_at_utc="2099-12-28 16:30:00",
        status=InstagramJobStatus.PUBLISHED
    )
    db.save_instagram_job(adv_job)
    code, resp = handle_diagnostic_cleanup(headers, {"job_id": "DIAG-HANDOFF-adv123"}, cfg, db)
    assert code == 403
    assert resp["error"] == "DIAGNOSTIC_CLEANUP_NOT_ALLOWED"


def test_diagnostic_cleanup_fails_if_s3_still_exists_and_preserves_db(tmp_path):
    """Test: If S3 object cannot be deleted and still exists, DB row is PRESERVED and 500 is returned."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    diag_job = InstagramScheduledJob(
        job_id="DIAG-HANDOFF-s3fail",
        week_id="2099-W52",
        reel_id="REEL-2099-9999",
        scheduled_at_local="2099-12-28 19:30:00",
        scheduled_at_utc="2099-12-28 16:30:00",
        media_object_key="media/2099-W52/REEL-2099-9999/test.mp4",
        status=InstagramJobStatus.MEDIA_READY
    )
    db.save_instagram_job(diag_job)

    mock_storage = MagicMock()
    mock_storage.exists.return_value = True  # S3 still exists!

    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}
    code, resp = handle_diagnostic_cleanup(headers, {"job_id": "DIAG-HANDOFF-s3fail"}, cfg, db, storage=mock_storage)

    assert code == 500
    assert resp["error"] == "DIAGNOSTIC_S3_CLEANUP_FAILED"

    # CRITICAL: DB row MUST NOT be deleted when S3 delete fails
    job_in_db = db.get_instagram_job("DIAG-HANDOFF-s3fail")
    assert job_in_db is not None


def test_diagnostic_cleanup_rejects_wrong_week_or_reel_or_prefix(tmp_path):
    """Test: Diagnostic cleanup strictly rejects jobs not matching 2099-W52 / REEL-2099-9999 / media/2099-W52/..."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}

    # 1. Wrong week_id
    job1 = InstagramScheduledJob(
        job_id="DIAG-HANDOFF-wrongweek",
        week_id="2026-W34",
        reel_id="REEL-2099-9999",
        scheduled_at_local="2099-12-28 19:30:00",
        scheduled_at_utc="2099-12-28 16:30:00",
        media_object_key="media/2099-W52/REEL-2099-9999/test.mp4",
        status=InstagramJobStatus.MEDIA_READY
    )
    db.save_instagram_job(job1)
    code, resp = handle_diagnostic_cleanup(headers, {"job_id": "DIAG-HANDOFF-wrongweek"}, cfg, db)
    assert code == 403
    assert resp["error"] == "DIAGNOSTIC_CLEANUP_NOT_ALLOWED"

    # 2. Wrong reel_id
    job2 = InstagramScheduledJob(
        job_id="DIAG-HANDOFF-wrongreel",
        week_id="2099-W52",
        reel_id="REEL-2026-0011",
        scheduled_at_local="2099-12-28 19:30:00",
        scheduled_at_utc="2099-12-28 16:30:00",
        media_object_key="media/2099-W52/REEL-2099-9999/test.mp4",
        status=InstagramJobStatus.MEDIA_READY
    )
    db.save_instagram_job(job2)
    code, resp = handle_diagnostic_cleanup(headers, {"job_id": "DIAG-HANDOFF-wrongreel"}, cfg, db)
    assert code == 403
    assert resp["error"] == "DIAGNOSTIC_CLEANUP_NOT_ALLOWED"

    # 3. Wrong media_object_key prefix
    job3 = InstagramScheduledJob(
        job_id="DIAG-HANDOFF-wrongkey",
        week_id="2099-W52",
        reel_id="REEL-2099-9999",
        scheduled_at_local="2099-12-28 19:30:00",
        scheduled_at_utc="2099-12-28 16:30:00",
        media_object_key="media/2026-W34/REEL-2026-0011/test.mp4",
        status=InstagramJobStatus.MEDIA_READY
    )
    db.save_instagram_job(job3)
    code, resp = handle_diagnostic_cleanup(headers, {"job_id": "DIAG-HANDOFF-wrongkey"}, cfg, db)
    assert code == 403
    assert resp["error"] == "DIAGNOSTIC_CLEANUP_NOT_ALLOWED"


def test_diagnostic_cleanup_success(tmp_path):
    """Test: Diagnostic cleanup deletes exact S3 object and DB row for valid DIAG-HANDOFF job."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    diag_job = InstagramScheduledJob(
        job_id="DIAG-HANDOFF-clean123",
        week_id="2099-W52",
        reel_id="REEL-2099-9999",
        scheduled_at_local="2099-12-28 19:30:00",
        scheduled_at_utc="2099-12-28 16:30:00",
        media_object_key="media/2099-W52/REEL-2099-9999/test.mp4",
        status=InstagramJobStatus.MEDIA_READY
    )
    db.save_instagram_job(diag_job)

    mock_storage = MagicMock()
    mock_storage.exists.return_value = False  # after deletion exists -> False
    mock_storage.delete_file.return_value = True

    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}
    code, resp = handle_diagnostic_cleanup(headers, {"job_id": "DIAG-HANDOFF-clean123"}, cfg, db, storage=mock_storage)

    assert code == 200
    assert resp["ok"] is True
    assert resp["status"] == "DIAGNOSTIC_CLEANED"
    assert resp["s3_deleted"] is True
    assert resp["db_deleted"] is True

    mock_storage.delete_file.assert_called_once_with("media/2099-W52/REEL-2099-9999/test.mp4")
    assert db.get_instagram_job("DIAG-HANDOFF-clean123") is None


# =============================================================================
# 5. LOCAL CLIENT & LIVE SMOKE TEST HELPER TESTS
# =============================================================================

def test_local_worker_cloud_client_upload_and_cleanup(tmp_path):
    """Test: LocalWorkerCloudClient handles upload and cleanup API calls."""
    video_file = tmp_path / "REEL-2026-0011.mp4"
    video_file.write_bytes(b"local client test bytes 12345")
    expected_sha = hashlib.sha256(b"local client test bytes 12345").hexdigest()

    client = LocalWorkerCloudClient(
        public_base_url="https://reels.up.railway.app",
        api_key="worker_key_abc",
        worker_id="win_local_1"
    )

    with patch.object(client.session, "post") as mock_post:
        # Upload
        mock_resp_up = MagicMock()
        mock_resp_up.status_code = 200
        mock_resp_up.json.return_value = {
            "ok": True,
            "status": "MEDIA_READY",
            "media_object_key": f"media/2026-W34/REEL-2026-0011/{expected_sha}.mp4",
            "media_sha256": expected_sha,
            "idempotent": False
        }
        mock_post.return_value = mock_resp_up

        ok, data, err = client.upload_media_for_instagram(
            local_path=video_file,
            week_id="2026-W34",
            reel_id="REEL-2026-0011",
            scheduled_at_local="2026-08-17 19:30:00",
            scheduled_at_utc="2026-08-17 16:30:00",
            caption="Automated Reel"
        )
        assert ok is True

        # Cleanup
        mock_resp_clean = MagicMock()
        mock_resp_clean.status_code = 200
        mock_resp_clean.json.return_value = {
            "ok": True,
            "status": "DIAGNOSTIC_CLEANED",
            "s3_deleted": True,
            "db_deleted": True
        }
        mock_post.return_value = mock_resp_clean

        ok_c, data_c, err_c = client.cleanup_diagnostic_media("DIAG-HANDOFF-12345")
        assert ok_c is True
        assert data_c["status"] == "DIAGNOSTIC_CLEANED"


def test_media_handoff_smoke_test_cli_flow(tmp_path):
    """Test: run_media_handoff_smoke_test defaults to dry plan and executes full cycle with --apply."""
    video_file = tmp_path / "smoke_test_reel.mp4"
    video_file.write_bytes(b"smoke test video frame bytes 777")

    mock_cfg = CloudConfig(tmp_path)
    mock_cfg.public_base_url = "https://reels.up.railway.app"
    mock_cfg.local_worker_api_key = "worker_key_123"

    # 1. Dry run
    res_dry = run_media_handoff_smoke_test(str(video_file), apply_changes=False, config=mock_cfg)
    assert res_dry is True

    # 2. Live apply
    mock_client = MagicMock()
    mock_client.upload_media_for_instagram.return_value = (
        True,
        {
            "ok": True,
            "status": "MEDIA_READY",
            "job_id": "DIAG-HANDOFF-test1234",
            "media_object_key": "media/2099-W52/REEL-2099-9999/sha.mp4"
        },
        None
    )
    mock_client.get_cloud_state.return_value = (
        True,
        {"instagram_jobs": [{"job_id": "DIAG-HANDOFF-test1234", "status": "MEDIA_READY"}]},
        None
    )
    mock_client.cleanup_diagnostic_media.return_value = (
        True,
        {"ok": True, "status": "DIAGNOSTIC_CLEANED", "s3_deleted": True, "db_deleted": True},
        None
    )

    res_live = run_media_handoff_smoke_test(str(video_file), apply_changes=True, client=mock_client, config=mock_cfg)
    assert res_live is True
    mock_client.upload_media_for_instagram.assert_called_once()
    mock_client.cleanup_diagnostic_media.assert_called_once()
