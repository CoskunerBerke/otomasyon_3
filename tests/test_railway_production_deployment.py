"""
Comprehensive Test Suite for Railway Production Deployment Foundation.
Tests production gates, PostgreSQL driver requirements, real S3 boto3 adapter,
health diagnostics, safety flags, secret scanning, Railway configuration,
cloud publishing import isolation, and LocalWorker ↔ Railway HTTP API integration.
"""
import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.cloud.config import CloudConfig
from automation.cloud.database import Database
from automation.cloud.health import get_health_status
from automation.cloud.media_storage import (
    LocalMediaStorageAdapter,
    S3MediaStorageAdapter,
    get_media_storage
)
from automation.cloud.instagram_worker import InstagramCloudWorker
from automation.cloud.scheduler import CloudScheduler
from automation.cloud.telegram_webhook import handle_webhook_request
from automation.cloud.local_worker_api import (
    handle_worker_heartbeat,
    handle_get_next_command,
    handle_complete_command,
    handle_sync_cloud_state
)
from automation.cloud.app import CloudApp
from automation.cloud.secret_scan import scan_repository, scan_file_for_secrets
from automation.cloud.telegram_live_smoke_test import run_smoke_test
from automation.cloud.setup_telegram_webhook import setup_webhook
from automation.local_worker_cloud_client import LocalWorkerCloudClient
from automation.local_worker import LocalWorker, run_heartbeat_only
from automation.cloud_sync import CloudObsidianSync
from automation.local_worker_preflight import run_local_worker_preflight


# =============================================================================
# 1. POSTGRESQL & PRODUCTION ENVIRONMENT HARD GATES
# =============================================================================

def test_production_rejects_sqlite_database_url(tmp_path):
    """Test 1: In APP_ENV=production, SQLite DATABASE_URL raises PRODUCTION_DATABASE_INVALID."""
    cfg = CloudConfig(tmp_path)
    cfg.app_env = "production"
    cfg.database_url = "sqlite:///workspace/prod.db"

    valid, err = cfg.validate_production_database()
    assert valid is False
    assert err == "PRODUCTION_DATABASE_INVALID"

    with pytest.raises(ValueError, match="PRODUCTION_DATABASE_INVALID"):
        Database(cfg.database_url, is_production=True)


def test_production_accepts_postgresql_database_url(tmp_path):
    """Test 2: In APP_ENV=production, PostgreSQL DATABASE_URL format is accepted."""
    cfg = CloudConfig(tmp_path)
    cfg.app_env = "production"
    cfg.database_url = "postgresql://user:secretpass@postgres.railway.internal:5432/railway"

    valid, err = cfg.validate_production_database()
    assert valid is True
    assert err is None
    assert cfg.is_postgres is True


def test_postgres_driver_present_in_dockerfile():
    """Test: Dockerfile includes psycopg driver installation for PostgreSQL support."""
    dockerfile = Path("Dockerfile")
    assert dockerfile.exists()
    content = dockerfile.read_text(encoding="utf-8")
    assert "psycopg" in content


# =============================================================================
# 2. SERVER PORT & HEALTH DIAGNOSTICS
# =============================================================================

def test_app_binds_railway_port_config(tmp_path):
    """Test 3: CloudConfig correctly parses dynamic Railway PORT environment variable."""
    with patch.dict(os.environ, {"PORT": "9050"}):
        cfg = CloudConfig(tmp_path)
        assert cfg.port == 9050


def test_health_endpoint_exposes_no_secrets_and_shows_safety_flags(tmp_path):
    """Test 4 & 19: /health returns complete status and safety flags without leaking secrets."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_bot_token = "123456789:SUPER_SECRET_BOT_TOKEN_XYZ"
    cfg.meta_access_token = "EAAB_SUPER_SECRET_META_TOKEN_123"
    cfg.s3_secret_access_key = "SECRET_S3_KEY_ABC"
    cfg.instagram_dry_run = True
    cfg.instagram_allow_upload = False
    cfg.instagram_allow_publish = False

    db = Database(cfg.database_url)
    health = get_health_status(cfg, db)

    assert health["status"] in ("HEALTHY", "DEGRADED")
    assert health["telegram_configured"] is True
    assert health["weekly_scheduler"] == "DISABLED"
    assert health["instagram_worker"] == "DISABLED"
    assert health["instagram_dry_run"] is True
    assert health["instagram_allow_upload"] is False
    assert health["instagram_allow_publish"] is False

    dumped = json.dumps(health)
    assert "SUPER_SECRET_BOT_TOKEN" not in dumped
    assert "SUPER_SECRET_META_TOKEN" not in dumped
    assert "SECRET_S3_KEY" not in dumped


def test_railway_healthcheck_path_remains_health():
    """Test: railway.toml healthcheck path remains exactly /health."""
    railway_toml = Path("railway.toml")
    assert railway_toml.exists()
    content = railway_toml.read_text(encoding="utf-8")
    assert 'healthcheckPath = "/health"' in content


# =============================================================================
# 3. REAL S3 ADAPTER OPERATIONS (MOCKED BOTO3 CLIENT)
# =============================================================================

def test_s3_storage_put_get_delete_exists_and_metadata(tmp_path):
    """Test: Real S3MediaStorageAdapter calls real client upload/download/head/delete."""
    mock_s3_client = MagicMock()

    adapter = S3MediaStorageAdapter(
        endpoint_url="https://s3.railway.app",
        bucket="reels-bucket",
        access_key="key_123",
        secret_key="secret_456",
        region="auto",
        s3_client=mock_s3_client
    )
    assert adapter.is_ready() is True

    # 1. put_file
    sample_file = tmp_path / "test_video.mp4"
    sample_file.write_bytes(b"test video payload")
    key = adapter.put_file(sample_file, "2026-W35/REEL-0001.mp4")
    assert key == "2026-W35/REEL-0001.mp4"
    mock_s3_client.upload_file.assert_called_once_with(
        Filename=str(sample_file),
        Bucket="reels-bucket",
        Key="2026-W35/REEL-0001.mp4",
        ExtraArgs={"ContentType": "video/mp4"}
    )

    # 2. get_file
    target_path = tmp_path / "downloaded.mp4"
    def fake_download(Bucket, Key, Filename):
        Path(Filename).write_bytes(b"downloaded content")
    mock_s3_client.download_file.side_effect = fake_download

    ok_get = adapter.get_file(key, target_path)
    assert ok_get is True
    assert target_path.exists()
    mock_s3_client.download_file.assert_called_once_with(
        Bucket="reels-bucket",
        Key="2026-W35/REEL-0001.mp4",
        Filename=str(target_path)
    )

    # 3. exists (head_object)
    mock_s3_client.head_object.return_value = {
        "ContentLength": 1024,
        "ContentType": "video/mp4",
        "ETag": '"etag123"',
        "LastModified": "2026-08-16T12:00:00Z"
    }
    assert adapter.exists(key) is True
    mock_s3_client.head_object.assert_called_with(Bucket="reels-bucket", Key="2026-W35/REEL-0001.mp4")

    # 4. get_metadata
    meta = adapter.get_metadata(key)
    assert meta["size_bytes"] == 1024
    assert meta["etag"] == "etag123"

    # 5. delete_file
    ok_del = adapter.delete_file(key)
    assert ok_del is True
    mock_s3_client.delete_object.assert_called_once_with(Bucket="reels-bucket", Key="2026-W35/REEL-0001.mp4")


def test_s3_missing_credentials_fails_validation(tmp_path):
    """Test: Incomplete S3 settings return is_ready() False."""
    adapter = S3MediaStorageAdapter(
        endpoint_url="",
        bucket="reels-bucket",
        access_key="key",
        secret_key=""
    )
    assert adapter.is_ready() is False


# =============================================================================
# 4. INSTAGRAM SAFETY FLAGS & SCHEDULER ISOLATION
# =============================================================================

def test_instagram_worker_respects_config_safety_flags(tmp_path):
    """Test: InstagramCloudWorker respects dry_run and upload/publish flags from CloudConfig."""
    cfg = CloudConfig(tmp_path)
    cfg.instagram_dry_run = True
    cfg.instagram_allow_upload = False
    cfg.instagram_allow_publish = False

    db = Database(f"sqlite:///{tmp_path / 'cloud_test.db'}")
    mock_storage = MagicMock()
    mock_api = MagicMock()

    worker = InstagramCloudWorker(cfg, db, mock_storage, api_client=mock_api)
    assert worker.config.instagram_dry_run is True
    assert worker.config.instagram_allow_upload is False
    assert worker.config.instagram_allow_publish is False


def test_scheduler_subsystem_flags_isolation(tmp_path):
    """Test: weekly_scheduler and instagram_worker flags operate independently with no cross-trigger."""
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    cfg.enable_weekly_scheduler = False
    cfg.enable_instagram_worker = True

    db = Database(cfg.database_url)
    mock_approval_svc = MagicMock()
    mock_ig_worker = MagicMock()
    mock_ig_worker.process_due_jobs.return_value = 2

    scheduler = CloudScheduler(cfg, db, mock_approval_svc, mock_ig_worker)

    res = scheduler.run_iteration()
    assert res["approvals_sent"] == 0
    assert res["instagram_jobs_processed"] == 2
    mock_ig_worker.process_due_jobs.assert_called_once()


# =============================================================================
# 5. FIRST DEPLOY SAFE DEFAULTS & SCHEDULE
# =============================================================================

def test_first_deploy_safe_defaults(tmp_path):
    """Test: Default production configuration has scheduler and live publishing disabled."""
    cfg = CloudConfig(tmp_path)
    assert cfg.weekly_approval_local_time == "18:00"
    assert cfg.weekly_approval_day == 6
    assert cfg.timezone_str == "Europe/Istanbul"
    assert cfg.instagram_dry_run is True
    assert cfg.instagram_allow_upload is False
    assert cfg.instagram_allow_publish is False
    assert cfg.enable_weekly_scheduler is False
    assert cfg.enable_instagram_worker is False


# =============================================================================
# 6. CLOUD IMPORT ISOLATION & DOCKER NO-BROWSER GUARANTEE
# =============================================================================

def test_cloud_import_isolation_and_publishing_package():
    """Test: Importing cloud control plane app does not load Playwright, publisher, or browser modules."""
    for mod in list(sys.modules.keys()):
        if (
            mod.startswith("automation.publishing")
            or mod.startswith("automation.cloud")
            or "obsidian" in mod
            or mod == "playwright"
        ):
            del sys.modules[mod]

    import automation.cloud.app
    assert "automation.cloud.app" in sys.modules
    assert "automation.publishing.publisher" not in sys.modules
    assert "automation.publishing.tiktok_browser" not in sys.modules
    assert "automation.publishing.tiktok_publisher" not in sys.modules
    assert "automation.publishing.youtube_publisher" not in sys.modules
    assert "playwright" not in sys.modules
    assert not any("obsidian" in m for m in sys.modules)


def test_instagram_models_and_api_independent_imports():
    """Test: Instagram models and API client can be imported independently without heavy dependencies."""
    from automation.publishing.instagram_models import InstagramConfig, InstagramPublishState
    from automation.publishing.instagram_api import InstagramAPIClient

    cfg = InstagramConfig(access_token="test_tok")
    client = InstagramAPIClient(cfg)
    assert client.config.access_token == "test_tok"
    assert InstagramPublishState.READY_TO_PUBLISH == "READY_TO_PUBLISH"


def test_lazy_export_compatibility():
    """Test: Lazy package-level exports still load on-demand when requested."""
    from automation.publishing import PublishingOrchestrator
    assert PublishingOrchestrator is not None
    assert PublishingOrchestrator.__name__ == "PublishingOrchestrator"


def test_windows_variables_not_required_in_cloud(tmp_path):
    """Test: CloudConfig does not require Windows variables (APPDATA, USERPROFILE)."""
    with patch.dict(os.environ, {}, clear=True):
        cfg = CloudConfig(tmp_path)
        assert cfg.app_env == "development"
        assert cfg.port == 8000
        assert cfg.timezone_str == "Europe/Istanbul"


# =============================================================================
# 7. REPO SECRET SCANNER & TEMPLATES
# =============================================================================

def test_dockerignore_excludes_sensitive_files():
    """Test: .dockerignore excludes .env, browser profiles, and video folders."""
    ignore_file = Path(".dockerignore")
    assert ignore_file.exists()
    content = ignore_file.read_text(encoding="utf-8")

    assert ".env" in content
    assert "browser-profile" in content
    assert "*.mp4" in content
    assert "AI_Reels" in content


def test_env_railway_example_contains_no_secrets():
    """Test: .env.railway.example is a safe template with no real secrets."""
    example_path = Path(".env.railway.example")
    assert example_path.exists()
    content = example_path.read_text(encoding="utf-8")

    assert "TELEGRAM_BOT_TOKEN=" in content
    assert "META_ACCESS_TOKEN=" in content
    assert "LOCAL_WORKER_API_KEY=" in content
    assert "WEEKLY_APPROVAL_LOCAL_TIME=18:00" in content
    assert "INSTAGRAM_DRY_RUN=true" in content


def test_local_worker_preflight_and_smoke_test_defaults(tmp_path):
    """Test: Preflights and smoke tests default to 0 writes and dry plan."""
    mock_cfg = CloudConfig(tmp_path)
    mock_cfg.telegram_bot_token = "mock_token_12345"
    mock_cfg.telegram_chat_id = 12345
    mock_cfg.local_worker_api_key = "worker_secret_123"
    mock_cfg.public_base_url = "https://reels.up.railway.app"

    # 1. Local worker preflight executes 0 writes
    with patch("automation.local_worker_preflight.CloudConfig", return_value=mock_cfg):
        ok, _ = run_local_worker_preflight(tmp_path)
        assert ok is True

    # 2. Smoke test default is dry plan (0 sends)
    res_smoke = run_smoke_test(send=False, config=mock_cfg)
    assert res_smoke is True

    # 3. Webhook setup default is dry plan (0 API writes)
    res_hook = setup_webhook(apply_changes=False, config=mock_cfg)
    assert res_hook is True


def test_telegram_smoke_test_send_with_none_config(tmp_path):
    """Test: run_smoke_test(send=True, config=None) does not raise AttributeError and uses instantiated cfg."""
    import automation.cloud.telegram_live_smoke_test as smoke_mod
    mock_cfg = CloudConfig(tmp_path)
    mock_cfg.telegram_bot_token = "mock_bot_token_123"
    mock_cfg.telegram_chat_id = 1835798213

    with patch.object(smoke_mod, "CloudConfig", return_value=mock_cfg):
        with patch.object(smoke_mod.TelegramBotClient, "send_message", return_value=(True, 999, None)) as mock_send:
            success = smoke_mod.run_smoke_test(send=True, config=None)
            assert success is True

            mock_send.assert_called_once()
            called_kwargs = mock_send.call_args[1]
            assert called_kwargs["chat_id"] == 1835798213


def test_telegram_smoke_test_send_with_explicit_config(tmp_path):
    """Test: run_smoke_test(send=True, config=cfg) uses the passed config object."""
    import automation.cloud.telegram_live_smoke_test as smoke_mod
    mock_cfg = CloudConfig(tmp_path)
    mock_cfg.telegram_bot_token = "explicit_bot_token_456"
    mock_cfg.telegram_chat_id = 99887766

    with patch.object(smoke_mod.TelegramBotClient, "send_message", return_value=(True, 1001, None)) as mock_send:
        success = smoke_mod.run_smoke_test(send=True, config=mock_cfg)
        assert success is True

        mock_send.assert_called_once()
        called_kwargs = mock_send.call_args[1]
        assert called_kwargs["chat_id"] == 99887766


# =============================================================================
# 8. LOCAL WORKER ↔ RAILWAY HTTP API INTEGRATION
# =============================================================================

def test_local_worker_cloud_client_endpoints_and_headers():
    """Test: LocalWorkerCloudClient sends correct headers and targets expected endpoints."""
    client = LocalWorkerCloudClient(
        public_base_url="https://reels.up.railway.app",
        api_key="secret_worker_key_xyz",
        worker_id="win_test_worker"
    )
    assert client.session.headers["X-Worker-Api-Key"] == "secret_worker_key_xyz"
    assert client.session.headers["X-Worker-Id"] == "win_test_worker"

    # 1. Heartbeat
    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "status": "HEARTBEAT_ACKNOWLEDGED"}
        mock_post.return_value = mock_resp

        ok, data, err = client.send_heartbeat(status="IDLE")
        assert ok is True
        assert err is None
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://reels.up.railway.app/worker/heartbeat"
        assert kwargs["json"]["worker_id"] == "win_test_worker"

    # 2. Get next command
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "command": {"command_id": "cmd_123", "type": "GENERATE_WEEK"}}
        mock_get.return_value = mock_resp

        ok, cmd, err = client.get_next_command()
        assert ok is True
        assert cmd["command_id"] == "cmd_123"
        args, kwargs = mock_get.call_args
        assert args[0] == "https://reels.up.railway.app/worker/commands/next"

    # 3. Complete command
    with patch.object(client.session, "post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True}
        mock_post.return_value = mock_resp

        ok, resp_data, err = client.complete_command("cmd_123", status="COMPLETE")
        assert ok is True
        args, kwargs = mock_post.call_args
        assert args[0] == "https://reels.up.railway.app/worker/commands/cmd_123/complete"

    # 4. State sync
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"ok": True, "weeks": [], "approvals": []}
        mock_get.return_value = mock_resp

        ok, state_payload, err = client.get_cloud_state()
        assert ok is True
        args, kwargs = mock_get.call_args
        assert args[0] == "https://reels.up.railway.app/worker/state/sync"


def test_local_worker_cloud_client_error_translations():
    """Test: LocalWorkerCloudClient translates 401 to UNAUTHORIZED_WORKER_KEY and connection err to CLOUD_UNREACHABLE."""
    import requests

    client = LocalWorkerCloudClient(
        public_base_url="https://reels.up.railway.app",
        api_key="wrong_key"
    )

    # 401 Unauthorized
    with patch.object(client.session, "get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        ok, data, err = client.get_cloud_state()
        assert ok is False
        assert err == "UNAUTHORIZED_WORKER_KEY"

    # Connection error
    with patch.object(client.session, "get", side_effect=requests.exceptions.ConnectionError("Failed")):
        ok, data, err = client.get_cloud_state()
        assert ok is False
        assert err == "CLOUD_UNREACHABLE"


def test_local_worker_heartbeat_only_mode_safety(tmp_path):
    """Test: --heartbeat-only invokes client.send_heartbeat and does NOT claim commands or run orchestrator."""
    mock_client = MagicMock()
    mock_client.send_heartbeat.return_value = (True, {"ok": True}, None)

    worker = LocalWorker(
        worker_id="win_test_worker",
        base_dir=tmp_path,
        cloud_client=mock_client
    )

    success = run_heartbeat_only(worker)
    assert success is True
    mock_client.send_heartbeat.assert_called_once_with(status="IDLE")
    mock_client.get_next_command.assert_not_called()
    mock_client.complete_command.assert_not_called()


def test_cloud_obsidian_sync_from_payload(tmp_path):
    """Test: CloudObsidianSync writes approval markdown notes from cloud JSON payload without direct DB."""
    vault_dir = tmp_path / "ObsidianVault"
    sync_engine = CloudObsidianSync(db=None, vault_path=vault_dir)

    payload = {
        "ok": True,
        "weeks": [{"week_id": "2026-W34", "status": "ACTIVE"}],
        "approvals": [
            {
                "approval_id": "appr_99",
                "week_id": "2026-W34",
                "next_week_id": "2026-W35",
                "status": "PENDING",
                "telegram_message_id": 555,
                "telegram_chat_id": 1835798213,
                "created_at": "2026-08-16 18:00:00"
            }
        ],
        "instagram_jobs": []
    }

    res = sync_engine.sync_from_cloud_payload(payload)
    assert res["active_weeks"] == 1
    assert res["synced_approvals"] == 1

    expected_note = vault_dir / "03_APPROVALS" / "APPROVAL-2026-W35.md"
    assert expected_note.exists()
    content = expected_note.read_text(encoding="utf-8")
    assert "approval_id: appr_99" in content
    assert "2026-W35" in content
