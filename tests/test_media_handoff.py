"""
Comprehensive Unit Test Suite for Local MP4 -> Railway S3 -> Instagram MEDIA_READY Handoff.
Tests endpoint authentication, multipart parsing, SHA256 integrity checks,
deterministic object keys, storage verification, PostgreSQL InstagramScheduledJob registration,
idempotency, conflict protection, error rollbacks, temp cleanup, and local handoff service.
Uses strict mocks only: 0 real S3 writes, 0 real video publishing, 0 real generation.
"""
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
from automation.cloud.local_worker_api import handle_media_upload
from automation.cloud.app import CloudApp
from automation.local_worker_cloud_client import LocalWorkerCloudClient
from automation.media_handoff import handoff_reel_to_cloud


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


def test_media_upload_rejects_path_traversal(tmp_path):
    """Test 7 & 8: Reject path traversal in week_id or reel_id."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    sample_bytes = b"safe video bytes"
    sha = hashlib.sha256(sample_bytes).hexdigest()

    # Traversal in week_id
    payload = {
        "file": sample_bytes,
        "filename": "test.mp4",
        "week_id": "../etc",
        "reel_id": "REEL-2026-0011",
        "media_sha256": sha
    }
    headers = {"X-Worker-Api-Key": "valid_secret_key_123"}
    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 400
    assert resp["error"] == "INVALID_WEEK_ID"

    # Traversal in reel_id
    payload["week_id"] = "2026-W34"
    payload["reel_id"] = "../../root"
    code, resp = handle_media_upload(headers, payload, cfg, db)
    assert code == 400
    assert resp["error"] == "INVALID_REEL_ID"


# =============================================================================
# 2. S3 STORAGE & INSTAGRAM JOB REGISTRATION TESTS
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

    # Pre-populate DB job with MEDIA_READY
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
    mock_storage.exists.return_value = True  # Already exists in S3
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
    # Should NOT upload duplicate bytes
    mock_storage.put_file.assert_not_called()


def test_media_upload_rejects_conflicting_sha(tmp_path):
    """Test 17: Existing job with DIFFERENT SHA returns 409 MEDIA_CONFLICT."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "valid_secret_key_123"
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    # Pre-populate DB with different SHA
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
            reel_id=f"REEL-2026-{adv_status.value}",
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
            "reel_id": f"REEL-2026-{adv_status.value}",
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
# 3. LOCAL CLIENT & MEDIA HANDOFF SERVICE TESTS
# =============================================================================

def test_local_worker_cloud_client_upload_media(tmp_path):
    """Test 22, 23, 24: LocalWorkerCloudClient computes SHA256 and sends multipart request with auth headers."""
    video_file = tmp_path / "REEL-2026-0011.mp4"
    video_file.write_bytes(b"local client test bytes 12345")
    expected_sha = hashlib.sha256(b"local client test bytes 12345").hexdigest()

    client = LocalWorkerCloudClient(
        public_base_url="https://reels.up.railway.app",
        api_key="worker_key_abc",
        worker_id="win_local_1"
    )

    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "status": "MEDIA_READY",
            "media_object_key": f"media/2026-W34/REEL-2026-0011/{expected_sha}.mp4",
            "media_sha256": expected_sha,
            "idempotent": False
        }
        mock_post.return_value = mock_resp

        ok, data, err = client.upload_media_for_instagram(
            local_path=video_file,
            week_id="2026-W34",
            reel_id="REEL-2026-0011",
            scheduled_at_local="2026-08-17 19:30:00",
            scheduled_at_utc="2026-08-17 16:30:00",
            caption="Automated Reel"
        )
        assert ok is True
        assert err is None
        assert data["media_sha256"] == expected_sha

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://reels.up.railway.app/worker/media/upload"
        assert kwargs["data"]["media_sha256"] == expected_sha
        assert kwargs["data"]["week_id"] == "2026-W34"


def test_media_handoff_service_end_to_end(tmp_path):
    """Test 25, 26, 27, 28, 29: handoff_reel_to_cloud delegates to client without platform actions."""
    video_file = tmp_path / "REEL-2026-0012.mp4"
    video_file.write_bytes(b"test reel payload 999")
    expected_sha = hashlib.sha256(b"test reel payload 999").hexdigest()

    mock_client = MagicMock()
    mock_client.upload_media_for_instagram.return_value = (
        True,
        {
            "ok": True,
            "status": "MEDIA_READY",
            "job_id": "JOB-2026-W34-REEL-2026-0012",
            "media_object_key": f"media/2026-W34/REEL-2026-0012/{expected_sha}.mp4",
            "media_sha256": expected_sha,
            "idempotent": False
        },
        None
    )

    ok, data, err = handoff_reel_to_cloud(
        local_path=video_file,
        week_id="2026-W34",
        reel_id="REEL-2026-0012",
        scheduled_at_local="2026-08-17 22:00:00",
        scheduled_at_utc="2026-08-17 19:00:00",
        caption="Second daily slot reel",
        client=mock_client
    )

    assert ok is True
    assert err is None
    assert data["job_id"] == "JOB-2026-W34-REEL-2026-0012"
    mock_client.upload_media_for_instagram.assert_called_once()
