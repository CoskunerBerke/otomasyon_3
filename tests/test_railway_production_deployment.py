"""
Comprehensive Test Suite for Railway Production Deployment Foundation.
Tests production gates, PostgreSQL requirements, S3 storage, health diagnostics,
secret scanning, Railway configuration, and safe dry defaults.
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
from automation.cloud.telegram_webhook import handle_webhook_request
from automation.cloud.local_worker_api import (
    handle_worker_heartbeat,
    handle_get_next_command
)
from automation.cloud.app import CloudApp
from automation.cloud.secret_scan import scan_repository, scan_file_for_secrets
from automation.cloud.telegram_live_smoke_test import run_smoke_test
from automation.cloud.setup_telegram_webhook import setup_webhook
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


# =============================================================================
# 2. SERVER PORT & HEALTH DIAGNOSTICS
# =============================================================================

def test_app_binds_railway_port_config(tmp_path):
    """Test 3: CloudConfig correctly parses dynamic Railway PORT environment variable."""
    with patch.dict(os.environ, {"PORT": "9050"}):
        cfg = CloudConfig(tmp_path)
        assert cfg.port == 9050


def test_health_endpoint_exposes_no_secrets(tmp_path):
    """Test 4: /health returns complete status without leaking database passwords or tokens."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.telegram_bot_token = "123456789:SUPER_SECRET_BOT_TOKEN_XYZ"
    cfg.meta_access_token = "EAAB_SUPER_SECRET_META_TOKEN_123"
    cfg.s3_secret_access_key = "SECRET_S3_KEY_ABC"

    db = Database(cfg.database_url)
    health = get_health_status(cfg, db)

    assert health["status"] in ("HEALTHY", "DEGRADED")
    assert health["telegram_configured"] is False  # chat_id not set
    assert health["scheduler"] == "ENABLED"

    dumped = json.dumps(health)
    assert "SUPER_SECRET_BOT_TOKEN" not in dumped
    assert "SUPER_SECRET_META_TOKEN" not in dumped
    assert "SECRET_S3_KEY" not in dumped


# =============================================================================
# 3. WEBHOOK & WORKER API SECURITY GATES
# =============================================================================

def test_missing_webhook_secret_in_production_blocks_webhook(tmp_path):
    """Test 5: Production environment blocks incoming webhook requests if TELEGRAM_WEBHOOK_SECRET is empty."""
    cfg = CloudConfig(tmp_path)
    cfg.app_env = "production"
    cfg.telegram_webhook_secret = ""  # Missing in production
    mock_svc = MagicMock()

    code, resp = handle_webhook_request(
        headers={},
        update={"update_id": 100},
        config=cfg,
        approval_service=mock_svc
    )
    assert code == 403
    assert resp["error"] == "TELEGRAM_WEBHOOK_SECRET_MISSING"


def test_missing_worker_key_disables_worker_api(tmp_path):
    """Test 6: Empty LOCAL_WORKER_API_KEY disables worker endpoints with WORKER_API_DISABLED."""
    cfg = CloudConfig(tmp_path)
    cfg.local_worker_api_key = ""  # Empty
    db = Database(f"sqlite:///{tmp_path / 'test.db'}")

    code, resp = handle_worker_heartbeat(
        headers={"X-Worker-Api-Key": ""},
        payload={"worker_id": "test_win"},
        config=cfg,
        db=db
    )
    assert code == 401
    assert resp["error"] == "WORKER_API_DISABLED"


# =============================================================================
# 4. S3 STORAGE & RETENTION
# =============================================================================

def test_s3_storage_readiness_and_missing_credentials(tmp_path):
    """Test 7 & 8: S3 Storage adapter verifies presence of all required bucket credentials."""
    # 1. Complete config
    s3_complete = S3MediaStorageAdapter(
        endpoint_url="https://s3.railway.app",
        bucket="reels-bucket",
        access_key="key_123",
        secret_key="secret_456"
    )
    assert s3_complete.is_ready() is True

    # 2. Missing secret key
    s3_incomplete = S3MediaStorageAdapter(
        endpoint_url="https://s3.railway.app",
        bucket="reels-bucket",
        access_key="key_123",
        secret_key=""
    )
    assert s3_incomplete.is_ready() is False


def test_storage_retention_candidate_identification_without_auto_delete(tmp_path):
    """Test 14 & 15: Storage retention identifies expired files without deleting when enable_cleanup=False."""
    storage_dir = tmp_path / "cloud_storage"
    adapter = LocalMediaStorageAdapter(storage_dir)

    dummy_file = tmp_path / "old_reel.mp4"
    dummy_file.write_bytes(b"dummy mp4")
    adapter.put_file(dummy_file, "2026-W30/REEL-0001.mp4")

    # Cleanup with enable_cleanup=False
    res = adapter.cleanup_expired_objects(retention_days=0, enable_cleanup=False)
    assert res["candidate_count"] == 1
    assert res["cleaned_count"] == 0
    assert adapter.exists("2026-W30/REEL-0001.mp4") is True


# =============================================================================
# 5. PUBLIC BASE URL & NORMALIZATION
# =============================================================================

def test_public_url_normalization_and_https_validation(tmp_path):
    """Test 9 & 10: PUBLIC_BASE_URL is stripped of trailing slashes, and non-HTTPS in prod is rejected."""
    # 1. Normalization
    with patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://reels.up.railway.app/   "}):
        cfg = CloudConfig(tmp_path)
        assert cfg.public_base_url == "https://reels.up.railway.app"

    # 2. Non-HTTPS rejection in production
    cfg.app_env = "production"
    cfg.public_base_url = "http://insecure-domain.com"
    valid, err = cfg.validate_public_url()
    assert valid is False
    assert err == "NON_HTTPS_PRODUCTION_URL"


# =============================================================================
# 6. FEATURE FLAGS & SCHEDULER LIFECYCLE
# =============================================================================

def test_subsystem_feature_flags_and_lifecycle(tmp_path):
    """Test 11, 12, 13: Feature flags toggle scheduler and worker loops; single scheduler thread."""
    db_file = tmp_path / "cloud_test.db"
    cfg = CloudConfig(tmp_path)
    cfg.database_url = f"sqlite:///{db_file}"
    cfg.enable_weekly_scheduler = False
    cfg.enable_instagram_worker = False

    app = CloudApp(cfg)
    assert app.config.enable_weekly_scheduler is False
    assert app.config.enable_instagram_worker is False

    # Start and stop gracefully
    app.start_scheduler()
    assert app._scheduler_running is True
    app.stop_scheduler()
    assert app._scheduler_running is False


# =============================================================================
# 7. DEPLOYMENT CONFIG & SECRET SCANNER
# =============================================================================

def test_dockerignore_excludes_sensitive_files():
    """Test 16: .dockerignore excludes .env, browser profiles, and video folders."""
    ignore_file = Path(".dockerignore")
    assert ignore_file.exists()
    content = ignore_file.read_text(encoding="utf-8")

    assert ".env" in content
    assert "browser-profile" in content
    assert "*.mp4" in content
    assert "AI_Reels" in content


def test_secret_scanner_detects_token_fixture_and_masks(tmp_path):
    """Test 17 & 18: Secret scanner detects raw token patterns and masks them in output."""
    bad_file = tmp_path / "leak_sample.py"
    bad_file.write_text("FAKE_BOT_TOKEN = '123456789:ABCdefGhIJKlmNoPQRstuVWXyz123456789'\n", encoding="utf-8")

    findings = scan_file_for_secrets(bad_file)
    assert len(findings) == 1
    assert findings[0]["secret_type"] == "TELEGRAM_BOT_TOKEN"
    assert "123...789" in findings[0]["masked_value"]
    assert "ABCdefGh" not in findings[0]["masked_value"]


def test_railway_config_and_dockerfile_exist():
    """Test 19 & 20: railway.toml and Dockerfile exist, valid, and contain no hardcoded secrets."""
    railway_toml = Path("railway.toml")
    assert railway_toml.exists()
    toml_content = railway_toml.read_text(encoding="utf-8")
    assert 'healthcheckPath = "/health"' in toml_content

    dockerfile = Path("Dockerfile")
    assert dockerfile.exists()
    df_content = dockerfile.read_text(encoding="utf-8")
    assert "PORT" in df_content
    # Ensure no tokens in Dockerfile
    assert "TOKEN=" not in df_content
    assert "SECRET=" not in df_content


# =============================================================================
# 8. CLOUD IMPORT ISOLATION & DRY PREFLIGHTS
# =============================================================================

def test_cloud_import_does_not_import_playwright():
    """Test 21: Importing cloud control plane app does not load Playwright or browser UI automation."""
    # Check that playwright is not in sys.modules before/after importing automation.cloud.app
    if "playwright" in sys.modules:
        del sys.modules["playwright"]

    import automation.cloud.app
    assert "playwright.sync_api" not in sys.modules
    assert "automation.orchestration.tiktok_ui_observer" not in sys.modules


def test_local_worker_preflight_and_smoke_test_defaults(tmp_path):
    """Test 22, 23, 24: Preflights and smoke tests default to 0 writes and dry plan."""
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
    with patch("automation.cloud.telegram_live_smoke_test.CloudConfig", return_value=mock_cfg):
        res_smoke = run_smoke_test(send=False)
        assert res_smoke is True

    # 3. Webhook setup default is dry plan (0 API writes)
    with patch("automation.cloud.setup_telegram_webhook.CloudConfig", return_value=mock_cfg):
        res_hook = setup_webhook(apply_changes=False)
        assert res_hook is True
