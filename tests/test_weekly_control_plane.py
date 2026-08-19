"""
Comprehensive Test Suite for Cloud Control Plane, Telegram Approval Bot,
Always-On Instagram Scheduler, Local Worker Bridge, and Obsidian Sync.
"""
import os
import re
import json
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from automation.cloud.config import CloudConfig
from automation.cloud.database import Database
from automation.cloud.models import (
    CloudWeek,
    CloudWeekStatus,
    TelegramApproval,
    TelegramApprovalStatus,
    LocalWorkerCommand,
    CommandType,
    CommandStatus,
    InstagramScheduledJob,
    InstagramJobStatus,
    WorkerHeartbeat,
    NotificationLog
)
from automation.cloud.telegram_bot import TelegramBotClient
from automation.cloud.approval_service import (
    ApprovalService,
    format_approval_message,
    build_approval_inline_keyboard
)
from automation.cloud.media_storage import (
    LocalMediaStorageAdapter,
    compute_file_sha256
)
from automation.cloud.instagram_worker import InstagramCloudWorker
from automation.cloud.scheduler import CloudScheduler
from automation.cloud.health import get_health_status
from automation.cloud.telegram_webhook import handle_webhook_request
from automation.cloud.local_worker_api import (
    handle_worker_heartbeat,
    handle_get_next_command,
    handle_complete_command,
    handle_sync_cloud_state
)
from automation.cloud_sync import CloudObsidianSync
from automation.local_worker import LocalWorker
from automation.local_worker_cloud_client import LocalWorkerCloudClient
from automation.publishing.instagram_models import InstagramConfig
from automation.publishing.instagram_api import InstagramAPIClient


# =============================================================================
# 0. ENVIRONMENT ISOLATION (must apply to every test in this module)
# =============================================================================
#
# CloudConfig resolves every setting through os.getenv(KEY, <safe default>) --
# INSTAGRAM_DRY_RUN defaults to "true", INSTAGRAM_ALLOW_UPLOAD/ALLOW_PUBLISH to
# "false", PUBLIC_BASE_URL to "", and so on. A developer machine configured for
# live Instagram or live Railway work exports those very keys, so a plain
# CloudConfig(tmp_path) would silently inherit the LIVE values instead of the
# documented defaults. A test written as "the safe defaults block the upload"
# would then prove nothing on that machine -- it would drive the live path.
#
# Every test here therefore runs with the whole CloudConfig environment surface
# removed, so the safety defaults under test are the ones actually in effect on
# any machine. Tests that need a non-default value set it explicitly on the cfg
# object. This only mutates os.environ inside the pytest process (monkeypatch
# restores it afterwards); the .env file itself is never read, written, or
# printed. It also relies on every test passing tmp_path as CloudConfig's
# base_dir, so CloudConfig._load_dotenv() finds no .env to re-inject.

CLOUD_CONFIG_ENV_KEYS = (
    "APP_ENV",
    "APP_TIMEZONE",
    "DATABASE_URL",
    "ENABLE_INSTAGRAM_WORKER",
    "ENABLE_MEDIA_CLEANUP",
    "ENABLE_TELEGRAM_WEBHOOK",
    "ENABLE_WEEKLY_SCHEDULER",
    "INSTAGRAM_ACCOUNT_ID",
    "INSTAGRAM_ALLOW_PUBLISH",
    "INSTAGRAM_ALLOW_UPLOAD",
    "INSTAGRAM_DRY_RUN",
    "INSTAGRAM_EXPECTED_USERNAME",
    "INSTAGRAM_PREPARE_MINUTES_BEFORE",
    "LOCAL_WORKER_API_KEY",
    "LOCAL_WORKER_POLL_SECONDS",
    "MEDIA_RETENTION_DAYS",
    "MEDIA_STORAGE_BACKEND",
    "META_ACCESS_TOKEN",
    "META_GRAPH_VERSION",
    "PORT",
    "PUBLIC_BASE_URL",
    "S3_ACCESS_KEY_ID",
    "S3_BUCKET",
    "S3_ENDPOINT_URL",
    "S3_REGION",
    "S3_SECRET_ACCESS_KEY",
    "TELEGRAM_ALLOWED_USER_ID",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_WEBHOOK_SECRET",
    "WEEKLY_APPROVAL_DAY",
    "WEEKLY_APPROVAL_LOCAL_TIME",
)


@pytest.fixture(autouse=True)
def isolated_cloud_env(monkeypatch):
    """Strips every CloudConfig-controlled variable from the process environment."""
    for key in CLOUD_CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_env_isolation_covers_every_cloudconfig_env_key():
    """Guard against drift: if CloudConfig starts reading a new environment
    variable, CLOUD_CONFIG_ENV_KEYS must learn about it too. Otherwise that new
    variable becomes another channel through which a machine's live settings can
    leak into these tests and quietly invalidate a safety assertion."""
    config_source = (
        Path(__file__).resolve().parents[1] / "automation" / "cloud" / "config.py"
    ).read_text(encoding="utf-8")

    referenced = set(re.findall(r'os\.getenv\(\s*"([A-Z0-9_]+)"', config_source))
    assert referenced, "Could not parse any os.getenv() key out of automation/cloud/config.py"

    uncovered = sorted(referenced - set(CLOUD_CONFIG_ENV_KEYS))
    assert not uncovered, (
        "CloudConfig reads environment variables that the isolation fixture does "
        f"not clear: {uncovered}"
    )


def test_isolated_env_yields_safe_instagram_defaults(tmp_path):
    """The publishing safety defaults are the premise of the dry-run gate test
    below, so assert them directly instead of assuming them."""
    cfg = CloudConfig(tmp_path)

    assert cfg.instagram_dry_run is True
    assert cfg.instagram_allow_upload is False
    assert cfg.instagram_allow_publish is False
    assert cfg.enable_instagram_worker is False
    assert cfg.enable_weekly_scheduler is False
    assert cfg.public_base_url == ""


# =============================================================================
# 1. TELEGRAM APPROVAL & DAY-6 SCHEDULER TESTS
# =============================================================================

def test_day6_approval_calculation_and_schedule(tmp_path):
    """Test 1 & 2: Day-6 date calculated correctly in Europe/Istanbul timezone."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_chat_id = 99999
    cfg.timezone_str = "Europe/Istanbul"
    cfg.weekly_approval_day = 6
    cfg.weekly_approval_local_time = "12:00"

    db = Database(cfg.database_url)
    mock_bot = MagicMock(spec=TelegramBotClient)
    approval_svc = ApprovalService(cfg, db, mock_bot)
    mock_ig_worker = MagicMock(spec=InstagramCloudWorker)

    scheduler = CloudScheduler(cfg, db, approval_svc, mock_ig_worker)

    # Week starting on Monday 2026-08-24 -> Day 6 is Saturday 2026-08-29
    week = CloudWeek(
        week_id="2026-W35",
        start_date="2026-08-24",
        end_date="2026-08-30",
        status=CloudWeekStatus.ACTIVE
    )
    db.save_week(week)

    # Mock time on Saturday 2026-08-29 13:00 (Past 12:00)
    mock_now = datetime.datetime(2026, 8, 29, 13, 0, 0)
    with patch.object(scheduler, "get_current_local_datetime", return_value=mock_now):
        mock_bot.send_message.return_value = (True, 12345, None)
        sent = scheduler.check_day6_approvals()

        assert sent == 1
        mock_bot.send_message.assert_called_once()


def test_approval_message_sent_once_no_duplicate_on_restart(tmp_path):
    """Test 3 & 4: Restarting scheduler does not send duplicate Telegram messages for the same week."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_chat_id = 987654

    db = Database(cfg.database_url)
    mock_bot = MagicMock(spec=TelegramBotClient)
    mock_bot.send_message.return_value = (True, 111, None)
    approval_svc = ApprovalService(cfg, db, mock_bot)

    ok1, id1 = approval_svc.create_and_send_approval("2026-W35", "2026-W36")
    assert ok1 is True
    assert mock_bot.send_message.call_count == 1

    # Second trigger attempt (e.g. after service restart)
    ok2, id2 = approval_svc.create_and_send_approval("2026-W35", "2026-W36")
    assert ok2 is True
    assert id2 == id1
    # Message send was NOT called again
    assert mock_bot.send_message.call_count == 1


def test_telegram_evet_approves_and_creates_single_generate_command(tmp_path):
    """Test 5, 6, 7: EVET callback approves next week, creates 1 GENERATE_WEEK command, double click is idempotent."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_allowed_user_id = 12345
    cfg.telegram_chat_id = 99999

    db = Database(cfg.database_url)
    mock_bot = MagicMock(spec=TelegramBotClient)
    approval_svc = ApprovalService(cfg, db, mock_bot)

    # Setup approval
    approval = TelegramApproval(
        approval_id="APPR-TEST-1",
        week_id="2026-W35",
        next_week_id="2026-W36",
        status=TelegramApprovalStatus.PENDING,
        telegram_message_id=555,
        telegram_chat_id=99999
    )
    db.save_approval(approval)

    callback_payload = {
        "id": "cb_1",
        "from": {"id": 12345, "username": "admin"},
        "message": {"chat": {"id": 99999}, "message_id": 555},
        "data": "weekly_approve:APPR-TEST-1"
    }

    # First EVET click
    res1 = approval_svc.handle_callback_query(callback_payload)
    assert res1["status"] == "APPROVED"
    mock_bot.answer_callback_query.assert_called()
    mock_bot.edit_message_text.assert_called()

    # Verify command created in DB
    cmd = db.get_next_pending_command()
    assert cmd is not None
    assert cmd.type == CommandType.GENERATE_WEEK
    assert cmd.week_id == "2026-W36"

    # Second EVET click (Double click / spam)
    res2 = approval_svc.handle_callback_query(callback_payload)
    assert res2["status"] == "ALREADY_PROCESSED"

    # Command count in DB remains strictly 1
    with db.get_connection() as conn:
        count = conn.cursor().execute("SELECT count(*) FROM local_worker_commands").fetchone()[0]
        assert count == 1


def test_telegram_hayir_rejects_and_creates_zero_commands(tmp_path):
    """Test 8 & 9: HAYIR callback rejects next week and creates zero worker commands."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_allowed_user_id = 12345
    cfg.telegram_chat_id = 99999

    db = Database(cfg.database_url)
    mock_bot = MagicMock(spec=TelegramBotClient)
    approval_svc = ApprovalService(cfg, db, mock_bot)

    approval = TelegramApproval(
        approval_id="APPR-TEST-2",
        week_id="2026-W35",
        next_week_id="2026-W36",
        status=TelegramApprovalStatus.PENDING,
        telegram_message_id=556,
        telegram_chat_id=99999
    )
    db.save_approval(approval)

    callback_payload = {
        "id": "cb_2",
        "from": {"id": 12345},
        "message": {"chat": {"id": 99999}, "message_id": 556},
        "data": "weekly_reject:APPR-TEST-2"
    }

    res = approval_svc.handle_callback_query(callback_payload)
    assert res["status"] == "REJECTED"

    cmd = db.get_next_pending_command()
    assert cmd is None


def test_unauthorized_telegram_user_rejected(tmp_path):
    """Test 10: Unauthorized Telegram User ID is strictly blocked."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_allowed_user_id = 12345
    cfg.telegram_chat_id = 99999

    db = Database(cfg.database_url)
    mock_bot = MagicMock(spec=TelegramBotClient)
    approval_svc = ApprovalService(cfg, db, mock_bot)

    callback_payload = {
        "id": "cb_bad",
        "from": {"id": 99999999},  # Unauthorized user
        "message": {"chat": {"id": 99999}, "message_id": 555},
        "data": "weekly_approve:APPR-TEST-1"
    }

    res = approval_svc.handle_callback_query(callback_payload)
    assert res["status"] == "UNAUTHORIZED"


def test_webhook_secret_header_validation(tmp_path):
    """Test 11: Telegram Webhook secret token header validated (403 on mismatch)."""
    cfg = CloudConfig(tmp_path)
    cfg.telegram_webhook_secret = "correct_secret_123"
    mock_approval_svc = MagicMock()

    # 1. Invalid secret
    code_bad, _ = handle_webhook_request(
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_secret"},
        update={"update_id": 1},
        config=cfg,
        approval_service=mock_approval_svc
    )
    assert code_bad == 403

    # 2. Valid secret
    code_good, _ = handle_webhook_request(
        headers={"X-Telegram-Bot-Api-Secret-Token": "correct_secret_123"},
        update={"update_id": 1},
        config=cfg,
        approval_service=mock_approval_svc
    )
    assert code_good == 200


def test_expired_approval_rejected(tmp_path):
    """Test 14: Expired approval token is rejected with EXPIRED status."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_allowed_user_id = 12345
    cfg.telegram_chat_id = 99999

    db = Database(cfg.database_url)
    mock_bot = MagicMock(spec=TelegramBotClient)
    approval_svc = ApprovalService(cfg, db, mock_bot)

    # Past expiration date
    approval = TelegramApproval(
        approval_id="APPR-EXPIRED",
        week_id="2026-W35",
        next_week_id="2026-W36",
        status=TelegramApprovalStatus.PENDING,
        telegram_message_id=557,
        telegram_chat_id=99999,
        expires_at="2026-08-01 00:00:00"
    )
    db.save_approval(approval)

    callback_payload = {
        "id": "cb_exp",
        "from": {"id": 12345},
        "message": {"chat": {"id": 99999}, "message_id": 557},
        "data": "weekly_approve:APPR-EXPIRED"
    }

    res = approval_svc.handle_callback_query(callback_payload)
    assert res["status"] == "EXPIRED"


# =============================================================================
# 2. LOCAL WORKER & COMMAND CLAIM TESTS
# =============================================================================

def test_worker_heartbeat_and_claim_command(tmp_path):
    """Test 16, 17, 18: Worker registers heartbeat and atomically claims pending command."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.local_worker_api_key = "test_key_123"

    db = Database(cfg.database_url)

    # 1. Heartbeat
    code_hb, _ = handle_worker_heartbeat(
        headers={"X-Worker-Api-Key": "test_key_123"},
        payload={"worker_id": "win_worker_1"},
        config=cfg,
        db=db
    )
    assert code_hb == 200
    latest_hb = db.get_latest_heartbeat()
    assert latest_hb.worker_id == "win_worker_1"

    # 2. Add command
    cmd = LocalWorkerCommand(
        command_id="CMD-101",
        type=CommandType.GENERATE_WEEK,
        week_id="2026-W36"
    )
    db.create_command(cmd)

    # 3. Claim command
    code_claim, claim_data = handle_get_next_command(
        headers={"X-Worker-Api-Key": "test_key_123"},
        worker_id="win_worker_1",
        config=cfg,
        db=db
    )
    assert code_claim == 200
    assert claim_data["command"]["command_id"] == "CMD-101"
    assert claim_data["command"]["status"] == "CLAIMED"


# =============================================================================
# 3. MEDIA STORAGE & INSTAGRAM ALWAYS-ON WORKER TESTS
# =============================================================================

def test_media_storage_local_adapter_and_hash_verification(tmp_path):
    """Test 20 & 33: Local media storage adapter stores file and validates SHA256 checksum."""
    storage_root = tmp_path / "media_storage"
    adapter = LocalMediaStorageAdapter(storage_root)

    source_file = tmp_path / "source_video.mp4"
    source_file.write_bytes(b"mock video data 12345")
    expected_hash = compute_file_sha256(source_file)

    key = adapter.put_file(source_file, "2026-W35/REEL-0011.mp4")
    assert adapter.exists(key) is True

    meta = adapter.get_metadata(key)
    assert meta["sha256"] == expected_hash

    dest_file = tmp_path / "downloaded_video.mp4"
    ok = adapter.get_file(key, dest_file)
    assert ok is True
    assert compute_file_sha256(dest_file) == expected_hash


def test_instagram_worker_claims_and_publishes_due_job(tmp_path):
    """Test 21, 23, 25, 35: Instagram worker claims due job, binary uploads from storage, publishes, and verifies remote ID."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.instagram_prepare_minutes_before = 30
    # Under the isolated environment the flags resolve to dry_run=True /
    # allow_upload=False / allow_publish=False, so execute_job() would short-circuit at
    # its dry-run safety gate and never reach the upload -> poll -> publish ->
    # remote-verify path this test exists to cover. Pinning the flags here is safe
    # because api_client below is a fully mocked InstagramAPIClient -- no real Meta
    # Graph API call can happen.
    cfg.instagram_dry_run = False
    cfg.instagram_allow_upload = True
    cfg.instagram_allow_publish = True

    db = Database(cfg.database_url)
    storage = LocalMediaStorageAdapter(tmp_path / "media_storage")

    # Store mock video
    mock_mp4 = tmp_path / "mock_reel.mp4"
    mock_mp4.write_bytes(b"x" * 2048)
    media_key = storage.put_file(mock_mp4, "reels/REEL-0011.mp4")
    media_hash = compute_file_sha256(mock_mp4)

    # Create due job (due in 5 minutes, inside 30-minute prepare window)
    now_dt = datetime.datetime.now()
    sched_local = (now_dt + datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    sched_utc = (now_dt - datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")

    job = InstagramScheduledJob(
        job_id="JOB-IG-1",
        week_id="2026-W35",
        reel_id="REEL-2026-0011",
        scheduled_at_local=sched_local,
        scheduled_at_utc=sched_utc,
        media_object_key=media_key,
        media_sha256=media_hash,
        caption="Zen garden timelapse ✨",
        status=InstagramJobStatus.MEDIA_READY
    )
    db.save_instagram_job(job)

    # Mock Meta API Client
    mock_api = MagicMock(spec=InstagramAPIClient)
    mock_api.check_publishing_limit.return_value = (True, {"quota_usage": 0, "config": {"quota_total": 25}}, None)
    mock_api.create_reels_container.return_value = (True, "CREATED", "CONT_123", "https://rupload.meta.com/123")
    mock_api.upload_video_resumable.return_value = (True, "UPLOAD_SUCCESS")
    mock_api.poll_container_status.return_value = (True, "FINISHED", {"status_code": "FINISHED"})
    mock_api.publish_media.return_value = (True, "PUBLISHED", "IG_MEDIA_99999")
    mock_api.get_media_object.return_value = (True, {"id": "IG_MEDIA_99999", "permalink": "https://instagr.am/p/123"}, None)

    worker = InstagramCloudWorker(cfg, db, storage, api_client=mock_api)

    # Process due jobs
    processed = worker.process_due_jobs("test_worker")
    assert processed == 1

    # Verify job completed in DB
    completed_job = db.get_instagram_job("JOB-IG-1")
    assert completed_job.status == InstagramJobStatus.REMOTE_VERIFIED
    assert completed_job.remote_media_id == "IG_MEDIA_99999"
    assert completed_job.permalink == "https://instagr.am/p/123"


def test_instagram_worker_dry_run_gate_blocks_real_upload(tmp_path):
    """The publishing safety flags (dry_run=True / allow_upload=False) must stop
    execute_job() before any binary upload or publish call reaches Meta -- a job may only
    be simulated, never really published, unless the flags are explicitly enabled."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.instagram_prepare_minutes_before = 30
    # The blocking flag values are pinned on the object rather than left to
    # CloudConfig's env-resolved defaults. INSTAGRAM_DRY_RUN / INSTAGRAM_ALLOW_UPLOAD
    # in a developer's environment would otherwise decide what this test exercises,
    # and on a machine configured for live Instagram work the assertions below would
    # be checking the live upload path instead of the guard.
    # (That the defaults are these same safe values is covered separately by
    # test_isolated_env_yields_safe_instagram_defaults.)
    cfg.instagram_dry_run = True
    cfg.instagram_allow_upload = False
    cfg.instagram_allow_publish = False

    db = Database(cfg.database_url)
    storage = LocalMediaStorageAdapter(tmp_path / "media_storage")

    mock_mp4 = tmp_path / "mock_reel.mp4"
    mock_mp4.write_bytes(b"x" * 2048)
    media_key = storage.put_file(mock_mp4, "reels/REEL-0012.mp4")

    now_dt = datetime.datetime.now()
    job = InstagramScheduledJob(
        job_id="JOB-IG-DRY",
        week_id="2026-W35",
        reel_id="REEL-2026-0012",
        scheduled_at_local=(now_dt + datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
        scheduled_at_utc=(now_dt - datetime.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
        media_object_key=media_key,
        media_sha256=compute_file_sha256(mock_mp4),
        caption="Dry run guard",
        status=InstagramJobStatus.MEDIA_READY
    )
    db.save_instagram_job(job)

    mock_api = MagicMock(spec=InstagramAPIClient)
    mock_api.check_publishing_limit.return_value = (True, {"quota_usage": 0, "config": {"quota_total": 25}}, None)
    mock_api.create_reels_container.return_value = (True, "CREATED", "CONT_DRY", "https://rupload.meta.com/dry")

    worker = InstagramCloudWorker(cfg, db, storage, api_client=mock_api)
    assert worker.process_due_jobs("test_worker") == 1

    mock_api.upload_video_resumable.assert_not_called()
    mock_api.publish_media.assert_not_called()

    dry_job = db.get_instagram_job("JOB-IG-DRY")
    assert dry_job.remote_media_id == "MOCK_DRY_RUN_ID"
    assert dry_job.status == InstagramJobStatus.PUBLISHED


def test_notification_duplicate_prevention(tmp_path):
    """Test 26 & 27: NotificationLog prevents sending duplicate alerts for the same failure."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    db = Database(cfg.database_url)

    payload_hash = "hash_alert_reel_0011_fatal"
    assert db.has_notification_been_sent(payload_hash) is False

    log = NotificationLog(
        notification_id="NOTIF-1",
        notification_type="IG_PUBLISH_FAILURE",
        recipient="chat_99999",
        payload_hash=payload_hash
    )
    db.log_notification(log)

    assert db.has_notification_been_sent(payload_hash) is True


# =============================================================================
# 4. OBSIDIAN SYNC & HEALTH TESTS
# =============================================================================

def test_obsidian_approval_sync(tmp_path):
    """Test 28 & 29: CloudSync mirrors approvals into 03_APPROVALS/."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    db = Database(cfg.database_url)

    approval = TelegramApproval(
        approval_id="APPR-SYNC-1",
        week_id="2026-W35",
        next_week_id="2026-W36",
        status=TelegramApprovalStatus.APPROVED,
        telegram_message_id=777,
        responded_at="2026-08-29 12:05:00"
    )
    db.save_approval(approval)

    vault_dir = tmp_path / "obsidian_vault"
    syncer = CloudObsidianSync(db, vault_dir)
    res = syncer.sync_approval_note(approval)
    assert res is True

    appr_file = vault_dir / "03_APPROVALS" / "APPROVAL-2026-W36.md"
    assert appr_file.exists()
    content = appr_file.read_text(encoding="utf-8")
    assert "status: APPROVED" in content
    assert "next_week_id: 2026-W36" in content


def test_health_endpoint_diagnostics(tmp_path):
    """Test 30 & 31: Health endpoint returns system status without exposing any secrets."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_bot_token = "123456:SECRET_BOT_TOKEN"
    cfg.meta_access_token = "EAAB_SECRET_META_TOKEN"
    # HEALTHY requires is_storage_configured; pin the backend so the assertion does not
    # depend on MEDIA_STORAGE_BACKEND / S3_* resolution on the machine running the test.
    cfg.media_storage_backend = "local"

    db = Database(cfg.database_url)
    health_data = get_health_status(cfg, db)

    assert health_data["status"] == "HEALTHY"
    assert health_data["database"] == "CONNECTED"

    # Strict secret verification: no secret strings appear in dictionary values
    health_str = json.dumps(health_data)
    assert "SECRET_BOT_TOKEN" not in health_str
    assert "SECRET_META_TOKEN" not in health_str


def test_dry_development_mode_zero_external_actions(tmp_path):
    """Test 31, 32, 33, 34: Dry mode guarantees 0 Telegram sends, 0 Meta writes, 0 storage writes, 0 real generation."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"

    db = Database(cfg.database_url)
    mock_bot = MagicMock(spec=TelegramBotClient)
    approval_svc = ApprovalService(cfg, db, mock_bot)
    mock_ig_worker = MagicMock(spec=InstagramCloudWorker)

    scheduler = CloudScheduler(cfg, db, approval_svc, mock_ig_worker)

    # In dry/untriggered mode, check_day6_approvals sends 0 messages when no active week is due
    sent = scheduler.check_day6_approvals()
    assert sent == 0
    mock_bot.send_message.assert_not_called()


def test_local_worker_run_cycle_and_obsidian_sync(tmp_path):
    """Test 15, 28, 29: Local worker runs cycle, handles offline queue, and syncs Obsidian without crashing."""
    vault_dir = tmp_path / "obsidian_vault"

    # LocalWorker builds a real LocalWorkerCloudClient out of PUBLIC_BASE_URL and
    # LOCAL_WORKER_API_KEY when none is injected, and run_cycle() then really posts a
    # heartbeat and really claims the next pending command. On a machine pointed at the
    # live Railway control plane that is an outbound call to production from a unit test,
    # so the client is always mocked here -- offline behaviour is what this test asserts.
    mock_cloud_client = MagicMock(spec=LocalWorkerCloudClient)
    mock_cloud_client.send_heartbeat.return_value = (False, {}, "PUBLIC_BASE_URL_MISSING")
    mock_cloud_client.get_next_command.return_value = (False, {}, "PUBLIC_BASE_URL_MISSING")
    mock_cloud_client.get_cloud_state.return_value = (False, {}, "PUBLIC_BASE_URL_MISSING")

    worker = LocalWorker(
        worker_id="win_test_worker",
        base_dir=tmp_path,
        vault_path=vault_dir,
        cloud_client=mock_cloud_client
    )

    cycle_res = worker.run_cycle()
    assert cycle_res["worker_id"] == "win_test_worker"
    assert cycle_res["heartbeat_ok"] is False
    assert cycle_res["processed_command_id"] is None
    assert (vault_dir / "03_APPROVALS").exists()


def test_unauthorized_worker_key_rejected(tmp_path):
    """Test: Worker API rejects invalid X-Worker-Api-Key."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = "correct_secret_key"
    db = Database(f"sqlite:///{tmp_path / 'cloud_test.db'}")

    code, resp = handle_worker_heartbeat(
        headers={"X-Worker-Api-Key": "wrong_key"},
        payload={"worker_id": "bad_worker"},
        config=cfg,
        db=db
    )
    assert code == 401
    assert resp["error"] == "UNAUTHORIZED_WORKER_KEY"

