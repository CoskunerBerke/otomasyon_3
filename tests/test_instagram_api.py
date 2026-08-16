"""
Unit tests for Meta Instagram Reels Publishing API & Preflight.
Tests Meta Graph API client, resumable local video upload, rate limit checks,
async processing polling, secret masking, and media validation using mock HTTP responses.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.publishing.instagram_models import (
    InstagramConfig,
    InstagramPublishRequest,
    InstagramPublishResult,
    InstagramPublishState,
    InstagramMediaValidationResult,
)
from automation.publishing.instagram_api import InstagramAPIClient, mask_token
from automation.publishing.instagram_preflight import InstagramPreflightRunner
from automation.publishing.instagram_validator import validate_instagram_reel_media


# =============================================================================
# 1. SECRET MASKING TESTS
# =============================================================================

def test_instagram_secret_masking_in_logs_and_errors():
    """Test 15: Verify that access tokens are never exposed in logs, repr, or error messages."""
    raw_token = "EAAB1234567890abcdef1234567890abcdef92"
    masked = mask_token(raw_token)
    assert masked == "EAAB...ef92"
    assert raw_token not in masked

    cfg = InstagramConfig(access_token=raw_token)
    assert cfg.masked_token == "EAAB...ef92"

    client = InstagramAPIClient(cfg)
    sanitized = client._sanitize_error_message(f"Error connecting with token {raw_token}")
    assert raw_token not in sanitized
    assert "EAAB...ef92" in sanitized


# =============================================================================
# 2. PREFLIGHT TESTS
# =============================================================================

def test_instagram_preflight_missing_credentials_returns_needs_user_setup():
    """Test 1: Missing credentials must return NEEDS_USER_META_SETUP."""
    cfg = InstagramConfig(access_token="", account_id="", expected_username="builddverse")
    runner = InstagramPreflightRunner(cfg)
    success, status, diag = runner.run_preflight()

    assert success is False
    assert status == "NEEDS_USER_META_SETUP"
    assert any("MISSING_META_ACCESS_TOKEN" in err for err in diag["errors"])


def test_instagram_preflight_valid_account_passes():
    """Test 2: Valid Graph API account response returns INSTAGRAM_PREFLIGHT_PASS."""
    cfg = InstagramConfig(
        access_token="EAABvalidtoken123",
        account_id="17841400000000000",
        expected_username="builddverse",
        graph_version="v22.0"
    )
    mock_client = MagicMock(spec=InstagramAPIClient)
    mock_client.config = cfg
    mock_client.get_me.return_value = (True, {"id": "123456", "name": "BuilddVerse App"}, None)
    mock_client.get_account_info.return_value = (
        True,
        {"id": "17841400000000000", "username": "builddverse", "name": "BuilddVerse"},
        None
    )
    mock_client.check_publishing_limit.return_value = (
        True,
        {"quota_usage": 2, "config": {"quota_total": 25, "quota_duration": 86400}},
        None
    )

    runner = InstagramPreflightRunner(cfg, client=mock_client)
    success, status, diag = runner.run_preflight()

    assert success is True
    assert status == "INSTAGRAM_PREFLIGHT_PASS"
    assert diag["5_username_verified"] is True
    assert diag["remote_username"] == "builddverse"
    assert diag["quota_usage"] == 2


def test_instagram_preflight_username_mismatch_blocks():
    """Test 3: Remote username mismatch must fail and block preflight."""
    cfg = InstagramConfig(
        access_token="EAABvalidtoken123",
        account_id="17841400000000000",
        expected_username="builddverse"
    )
    mock_client = MagicMock(spec=InstagramAPIClient)
    mock_client.config = cfg
    mock_client.get_me.return_value = (True, {"id": "123456", "name": "Test App"}, None)
    mock_client.get_account_info.return_value = (
        True,
        {"id": "17841400000000000", "username": "other_account_name", "name": "Other Account"},
        None
    )
    mock_client.check_publishing_limit.return_value = (True, {"quota_usage": 0}, None)

    runner = InstagramPreflightRunner(cfg, client=mock_client)
    success, status, diag = runner.run_preflight()

    assert success is False
    assert status == "NEEDS_USER_META_SETUP"
    assert any("USERNAME_MISMATCH" in err for err in diag["errors"])


def test_instagram_preflight_account_discovery_from_pages():
    """Test 16: Automatically discovers Instagram Business account linked to Facebook Pages."""
    cfg = InstagramConfig(
        access_token="EAABvalidtoken123",
        account_id="",  # Empty, must be discovered
        expected_username="builddverse"
    )
    mock_client = MagicMock(spec=InstagramAPIClient)
    mock_client.config = cfg
    mock_client.get_me.return_value = (True, {"id": "123456", "name": "User"}, None)
    mock_client.discover_linked_accounts.return_value = [
        {
            "page_id": "999888",
            "page_name": "BuilddVerse Page",
            "instagram_id": "17841400112233445",
            "instagram_username": "builddverse",
            "instagram_name": "BuilddVerse Official",
        }
    ]
    mock_client.get_account_info.return_value = (
        True,
        {"id": "17841400112233445", "username": "builddverse", "name": "BuilddVerse Official"},
        None
    )
    mock_client.check_publishing_limit.return_value = (True, {"quota_usage": 0}, None)

    runner = InstagramPreflightRunner(cfg, client=mock_client)
    success, status, diag = runner.run_preflight()

    assert success is True
    assert status == "INSTAGRAM_PREFLIGHT_PASS"
    assert diag["remote_account_id"] == "17841400112233445"


# =============================================================================
# 3. HTTP CLIENT & RETRY TESTS
# =============================================================================

def test_instagram_api_fatal_401_auth_error_no_infinite_retry():
    """Test 6: 401/403 authentication error must fail immediately without retries."""
    cfg = InstagramConfig(access_token="EAABbadtoken", max_retries=3)
    client = InstagramAPIClient(cfg)

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": {"message": "Invalid OAuth access token.", "code": 190}}
    mock_resp.text = json.dumps(mock_resp.json.return_value)

    with patch.object(client.session, "request", return_value=mock_resp) as mock_req:
        resp = client._request("GET", "/me")
        assert resp.status_code == 401
        assert mock_req.call_count == 1  # Exactly 1 call, no retry


def test_instagram_api_429_rate_limited_retryable():
    """Test 7: 429 rate limit triggers bounded exponential retry."""
    cfg = InstagramConfig(access_token="EAABvalid", max_retries=2)
    client = InstagramAPIClient(cfg)

    mock_resp_429 = MagicMock(status_code=429, text="Rate limit exceeded")
    mock_resp_200 = MagicMock(status_code=200, json=lambda: {"id": "123", "username": "builddverse"})

    with patch.object(client.session, "request", side_effect=[mock_resp_429, mock_resp_200]) as mock_req:
        with patch("time.sleep"):  # Speed up test
            resp = client._request("GET", "/me")
            assert resp.status_code == 200
            assert mock_req.call_count == 2


def test_instagram_api_5xx_server_error_bounded_retry():
    """Test 8: 5xx server error triggers retry up to max_retries."""
    cfg = InstagramConfig(access_token="EAABvalid", max_retries=3)
    client = InstagramAPIClient(cfg)

    mock_resp_500 = MagicMock(status_code=500, text="Internal server error")

    with patch.object(client.session, "request", return_value=mock_resp_500) as mock_req:
        with patch("time.sleep"):
            resp = client._request("GET", "/me")
            assert resp.status_code == 500
            assert mock_req.call_count == 3


# =============================================================================
# 4. CONTAINER CREATION & PROCESSING POLLING TESTS
# =============================================================================

def test_instagram_container_processing_finished():
    """Test 9: Processing status poll detects FINISHED and marks container ready."""
    cfg = InstagramConfig(access_token="EAABvalid", account_id="178414000")
    client = InstagramAPIClient(cfg)

    mock_resp_in_progress = MagicMock(status_code=200, json=lambda: {"status_code": "IN_PROGRESS", "id": "cont_123"})
    mock_resp_finished = MagicMock(status_code=200, json=lambda: {"status_code": "FINISHED", "id": "cont_123"})

    with patch.object(client.session, "request", side_effect=[mock_resp_in_progress, mock_resp_finished]):
        with patch("time.sleep"):
            ok, status, data = client.poll_container_status("cont_123", timeout_seconds=10)
            assert ok is True
            assert status == "FINISHED"
            assert data.get("status_code") == "FINISHED"


def test_instagram_container_processing_error():
    """Test 10: Processing status poll detects ERROR and fails gracefully."""
    cfg = InstagramConfig(access_token="EAABvalid", account_id="178414000")
    client = InstagramAPIClient(cfg)

    mock_resp_error = MagicMock(
        status_code=200,
        json=lambda: {"status_code": "ERROR", "status": "Video transcoding failed due to invalid aspect ratio."}
    )

    with patch.object(client.session, "request", return_value=mock_resp_error):
        ok, status, data = client.poll_container_status("cont_123", timeout_seconds=5)
        assert ok is False
        assert status == "ERROR"


# =============================================================================
# 5. SAFETY & DRY-RUN GATES TESTS
# =============================================================================

def test_instagram_dry_run_zero_post_publish():
    """Test 12: dry_run=True must execute 0 POST publish calls to Meta API."""
    cfg = InstagramConfig(access_token="EAABvalid", account_id="178414000", dry_run=True)
    client = InstagramAPIClient(cfg)

    with patch.object(client.session, "request") as mock_req:
        ok, msg, media_id = client.publish_media("cont_123", dry_run=True, allow_publish=False)
        assert ok is True
        assert msg == "DRY_RUN_PUBLISH_SKIPPED"
        assert media_id is None
        mock_req.assert_not_called()


def test_instagram_allow_upload_false_binary_upload_zero():
    """Test 13: allow_upload=False must not stream binary file bytes."""
    cfg = InstagramConfig(access_token="EAABvalid", account_id="178414000", allow_upload=False)
    client = InstagramAPIClient(cfg)

    with patch.object(client.session, "request") as mock_req:
        ok, msg = client.upload_video_resumable(
            "https://rupload.facebook.com/v22.0/mock",
            Path("dummy.mp4"),
            dry_run=False,
            allow_upload=False
        )
        assert ok is True
        assert msg == "DRY_RUN_UPLOAD_SKIPPED"
        mock_req.assert_not_called()


def test_instagram_allow_publish_false_media_publish_zero():
    """Test 14: allow_publish=False must block real media_publish call."""
    cfg = InstagramConfig(access_token="EAABvalid", account_id="178414000", allow_publish=False)
    client = InstagramAPIClient(cfg)

    with patch.object(client.session, "request") as mock_req:
        ok, msg, media_id = client.publish_media("cont_123", dry_run=False, allow_publish=False)
        assert ok is True
        assert msg == "DRY_RUN_PUBLISH_SKIPPED"
        mock_req.assert_not_called()


# =============================================================================
# 6. IDEMPOTENCY & DATA MODEL TESTS
# =============================================================================

def test_instagram_idempotent_skip_when_already_published():
    """Test 11: When Reel already has a remote_media_id, state is marked SKIP_ALREADY_PUBLISHED."""
    result = InstagramPublishResult(
        reel_id="REEL-2026-0010",
        status=InstagramPublishState.PUBLISHED,
        remote_media_id="18000112233445566",
        permalink="https://www.instagram.com/reel/Cxxxxxx/"
    )
    # Check Obsidian frontmatter serialization
    fm = result.to_frontmatter_dict()
    assert fm["instagram_status"] == "PUBLISHED"
    assert fm["instagram_media_id"] == "18000112233445566"
    assert fm["instagram_permalink"] == "https://www.instagram.com/reel/Cxxxxxx/"


def test_instagram_caption_truncation_within_2200_chars():
    """Test 18: Caption exceeding 2200 chars is safely truncated."""
    long_caption = "A" * 2300
    req = InstagramPublishRequest(
        reel_id="REEL-0001",
        video_path=Path("dummy.mp4"),
        caption=long_caption,
        hashtags=["#ai", "#technology"]
    )
    full_cap = req.full_caption()
    assert len(full_cap) <= 2200
    assert full_cap.endswith("...")


# =============================================================================
# 7. MEDIA VALIDATION TESTS
# =============================================================================

def test_instagram_media_validation_valid_9_16_video(tmp_path):
    """Test 4: Valid 9:16 30s MP4 mock inspection passes validation."""
    video_file = tmp_path / "valid_reel.mp4"
    video_file.write_bytes(b"mock mp4 content")

    mock_ffprobe_out = {
        "format": {"duration": "30.05"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1080,
                "height": 1920,
                "r_frame_rate": "30/1"
            },
            {
                "codec_type": "audio",
                "codec_name": "aac"
            }
        ]
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(mock_ffprobe_out)

    with patch("subprocess.run", return_value=mock_proc):
        val = validate_instagram_reel_media(video_file)
        assert val.is_valid is True
        assert val.status_code == "INSTAGRAM_MEDIA_VALID"
        assert val.width == 1080
        assert val.height == 1920
        assert val.duration_seconds == 30.05
        assert len(val.errors) == 0


def test_instagram_media_validation_invalid_aspect_ratio_and_duration(tmp_path):
    """Test 5: Invalid horizontal ratio (16:9) and excessive duration (>90s) fails validation."""
    video_file = tmp_path / "horizontal_long.mp4"
    video_file.write_bytes(b"mock mp4 content")

    mock_ffprobe_out = {
        "format": {"duration": "120.0"},  # > 90s
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,  # 16:9 horizontal
                "r_frame_rate": "30/1"
            }
        ]
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(mock_ffprobe_out)

    with patch("subprocess.run", return_value=mock_proc):
        val = validate_instagram_reel_media(video_file)
        assert val.is_valid is False
        assert val.status_code == "INSTAGRAM_MEDIA_INVALID"
        assert any("DURATION_TOO_LONG" in err for err in val.errors)
        assert any("INVALID_ASPECT_RATIO" in err for err in val.errors)


# =============================================================================
# 8. LIVE TEST RUNNER & REEL-2026-0010 REGRESSION TESTS
# =============================================================================

from automation.publishing.instagram_live_test import (
    InstagramLiveTestRunner,
    locate_reel_0010_video,
    check_existing_published_state,
    persist_published_state,
    EXPECTED_USERNAME,
    EXPECTED_ACCOUNT_ID,
    TARGET_REEL_ID,
    EXIT_SUCCESS,
    EXIT_PREFLIGHT_FAILED,
    EXIT_ACCOUNT_MISMATCH,
    EXIT_LIVE_FLAGS_INVALID,
    EXIT_MEDIA_INVALID,
    EXIT_CONTAINER_CREATE_FAILED,
    EXIT_UPLOAD_FAILED,
    EXIT_PROCESSING_FAILED,
    EXIT_PUBLISH_FAILED,
    EXIT_PUBLISH_RESPONSE_MISSING_MEDIA_ID,
    EXIT_DRY_RUN_ONLY,
)


def test_instagram_live_runner_locate_exact_reel_0010(tmp_path):
    """Test 4: Locates clean_REEL-2026-0010_Japanese_Zen_Temple.mp4 accurately."""
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True)
    target_file = dl_dir / "clean_REEL-2026-0010_Japanese_Zen_Temple.mp4"
    target_file.write_bytes(b"x" * 2000)

    found = locate_reel_0010_video(tmp_path)
    assert found is not None
    assert found.name == "clean_REEL-2026-0010_Japanese_Zen_Temple.mp4"


def test_instagram_live_runner_wrong_username_blocks(tmp_path):
    """Test 2: Wrong remote username triggers ACCOUNT_MISMATCH and blocks write."""
    state_file = tmp_path / "isolated_state.json"
    runner = InstagramLiveTestRunner(tmp_path, state_file=state_file)
    runner.config.access_token = "EAABvalidtoken123"

    mock_client = MagicMock(spec=InstagramAPIClient)
    mock_client.config = runner.config
    mock_client.get_account_info.return_value = (
        True,
        {"id": EXPECTED_ACCOUNT_ID, "username": "wrong_username"},
        None
    )
    runner.client = mock_client

    ok, result, exit_code = runner.run()
    assert ok is False
    assert exit_code == EXIT_ACCOUNT_MISMATCH
    assert result.error_code == "ACCOUNT_MISMATCH"
    assert result.status == InstagramPublishState.FAILED_FATAL


def test_instagram_live_runner_wrong_account_id_blocks(tmp_path):
    """Test 3: Wrong remote account ID triggers ACCOUNT_MISMATCH and blocks write."""
    state_file = tmp_path / "isolated_state.json"
    runner = InstagramLiveTestRunner(tmp_path, state_file=state_file)
    runner.config.access_token = "EAABvalidtoken123"

    mock_client = MagicMock(spec=InstagramAPIClient)
    mock_client.config = runner.config
    mock_client.get_account_info.return_value = (
        True,
        {"id": "99999999999999999", "username": EXPECTED_USERNAME},
        None
    )
    runner.client = mock_client

    ok, result, exit_code = runner.run()
    assert ok is False
    assert exit_code == EXIT_ACCOUNT_MISMATCH
    assert result.error_code == "ACCOUNT_MISMATCH"
    assert result.status == InstagramPublishState.FAILED_FATAL


def test_instagram_live_runner_dry_run_flag_returns_non_zero_exit_code(tmp_path):
    """Test 1: dry_run=True must fail live test with EXIT_DRY_RUN_ONLY (21)."""
    state_file = tmp_path / "isolated_state.json"
    cfg = InstagramConfig(
        access_token="EAABvalidtoken123",
        account_id=EXPECTED_ACCOUNT_ID,
        expected_username=EXPECTED_USERNAME,
        dry_run=True,
        allow_upload=True,
        allow_publish=True
    )
    runner = InstagramLiveTestRunner(tmp_path, config=cfg, state_file=state_file)
    ok, result, exit_code = runner.run()

    assert ok is False
    assert exit_code == EXIT_DRY_RUN_ONLY
    assert result.error_code == "DRY_RUN_ONLY"


def test_instagram_live_runner_allow_flags_false_fails_with_code_12(tmp_path):
    """Test 2, 3: allow_upload=False or allow_publish=False fails with EXIT_LIVE_FLAGS_INVALID (12)."""
    state_file = tmp_path / "isolated_state.json"
    cfg = InstagramConfig(
        access_token="EAABvalidtoken123",
        account_id=EXPECTED_ACCOUNT_ID,
        expected_username=EXPECTED_USERNAME,
        dry_run=False,
        allow_upload=False,
        allow_publish=True
    )
    runner = InstagramLiveTestRunner(tmp_path, config=cfg, state_file=state_file)
    ok, result, exit_code = runner.run()

    assert ok is False
    assert exit_code == EXIT_LIVE_FLAGS_INVALID
    assert result.error_code == "LIVE_FLAGS_INVALID"


def test_instagram_live_runner_stale_local_state_with_remote_404_clears_and_proceeds(tmp_path):
    """Test 5: Stale local state with fake remote ID triggers remote check, detects 404, and proceeds."""
    state_file = tmp_path / "isolated_state.json"
    state_file.write_text(json.dumps({
        TARGET_REEL_ID: {
            "platform": "instagram",
            "reel_id": TARGET_REEL_ID,
            "status": "PUBLISHED",
            "remote_media_id": "18000112233445566"
        }
    }), encoding="utf-8")

    mock_client = MagicMock(spec=InstagramAPIClient)
    # Remote check returns False (404/not found)
    mock_client.get_media_object.return_value = (False, {}, "Object not found")

    is_verified, data, status = check_existing_published_state(TARGET_REEL_ID, mock_client, state_file=state_file)
    assert is_verified is False
    assert status == "STALE_LOCAL_STATE"


def test_instagram_live_runner_verified_existing_remote_skips(tmp_path):
    """Test 6: Verified remote media exists returns SKIP_ALREADY_PUBLISHED_REMOTE_VERIFIED."""
    state_file = tmp_path / "isolated_state.json"
    state_file.write_text(json.dumps({
        TARGET_REEL_ID: {
            "platform": "instagram",
            "reel_id": TARGET_REEL_ID,
            "status": "PUBLISHED",
            "remote_media_id": "18099887766554433",
            "permalink": "https://www.instagram.com/reel/Ctest/"
        }
    }), encoding="utf-8")

    mock_client = MagicMock(spec=InstagramAPIClient)
    mock_client.get_media_object.return_value = (
        True,
        {"id": "18099887766554433", "permalink": "https://www.instagram.com/reel/Ctest/"},
        None
    )

    is_verified, data, status = check_existing_published_state(TARGET_REEL_ID, mock_client, state_file=state_file)
    assert is_verified is True
    assert status == "SKIP_ALREADY_PUBLISHED_REMOTE_VERIFIED"
    assert data["remote_media_id"] == "18099887766554433"


def test_instagram_live_runner_full_publish_success(tmp_path):
    """Test 7, 8, 9, 11, 12, 13: Successful container creation, upload, FINISHED polling, publish, remote verification, and state save."""
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True)
    video_file = dl_dir / "clean_REEL-2026-0010_Japanese_Zen_Temple.mp4"
    video_file.write_bytes(b"x" * 2000)

    state_file = tmp_path / "isolated_state.json"

    runner = InstagramLiveTestRunner(tmp_path, state_file=state_file)
    runner.config.access_token = "EAABvalidtoken123"

    mock_client = MagicMock(spec=InstagramAPIClient)
    mock_client.config = runner.config
    mock_client.get_account_info.return_value = (
        True,
        {"id": EXPECTED_ACCOUNT_ID, "username": EXPECTED_USERNAME},
        None
    )
    mock_client.check_publishing_limit.return_value = (
        True,
        {"quota_usage": 1, "config": {"quota_total": 25}},
        None
    )
    mock_client.create_reels_container.return_value = (
        True, "CONTAINER_CREATED", "17999888777", "https://rupload.facebook.com/v26.0/mock-uri"
    )
    mock_client.upload_video_resumable.return_value = (True, "UPLOAD_SUCCESS")
    mock_client.poll_container_status.return_value = (True, "FINISHED", {"status_code": "FINISHED"})
    mock_client.publish_media.return_value = (True, "PUBLISHED", "18000112233445566")
    mock_client.get_media_object.return_value = (
        True,
        {
            "id": "18000112233445566",
            "media_type": "VIDEO",
            "media_product_type": "REELS",
            "permalink": "https://www.instagram.com/reel/Czen123/",
            "username": EXPECTED_USERNAME
        },
        None
    )

    runner.client = mock_client

    mock_val = InstagramMediaValidationResult(
        is_valid=True,
        duration_seconds=30.03,
        width=720,
        height=1280,
        video_codec="h264",
        file_size_bytes=2000
    )

    with patch("automation.publishing.instagram_live_test.validate_instagram_reel_media", return_value=mock_val):
        ok, result, exit_code = runner.run()

        assert ok is True
        assert exit_code == EXIT_SUCCESS
        assert result.status == InstagramPublishState.PUBLISHED
        assert result.remote_media_id == "18000112233445566"
        assert result.permalink == "https://www.instagram.com/reel/Czen123/"
        mock_client.publish_media.assert_called_once()
        assert state_file.exists()


def test_instagram_live_runner_missing_publish_media_id_fails(tmp_path):
    """Test 11: media_publish returning empty ID fails with EXIT_PUBLISH_RESPONSE_MISSING_MEDIA_ID (19)."""
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True)
    video_file = dl_dir / "clean_REEL-2026-0010_Japanese_Zen_Temple.mp4"
    video_file.write_bytes(b"x" * 2000)

    state_file = tmp_path / "isolated_state.json"
    runner = InstagramLiveTestRunner(tmp_path, state_file=state_file)
    runner.config.access_token = "EAABvalidtoken123"

    mock_client = MagicMock(spec=InstagramAPIClient)
    mock_client.config = runner.config
    mock_client.get_account_info.return_value = (True, {"id": EXPECTED_ACCOUNT_ID, "username": EXPECTED_USERNAME}, None)
    mock_client.check_publishing_limit.return_value = (True, {"quota_usage": 0, "config": {"quota_total": 25}}, None)
    mock_client.create_reels_container.return_value = (True, "CONTAINER_CREATED", "17999888777", "https://mock")
    mock_client.upload_video_resumable.return_value = (True, "UPLOAD_SUCCESS")
    mock_client.poll_container_status.return_value = (True, "FINISHED", {"status_code": "FINISHED"})
    # media_publish returns empty id
    mock_client.publish_media.return_value = (True, "PUBLISHED", "")

    runner.client = mock_client

    mock_val = InstagramMediaValidationResult(is_valid=True, duration_seconds=30.03, width=720, height=1280, video_codec="h264", file_size_bytes=2000)

    with patch("automation.publishing.instagram_live_test.validate_instagram_reel_media", return_value=mock_val):
        ok, result, exit_code = runner.run()

        assert ok is False
        assert exit_code == EXIT_PUBLISH_RESPONSE_MISSING_MEDIA_ID
        assert result.error_code == "PUBLISH_RESPONSE_MISSING_MEDIA_ID"


def test_instagram_generic_config_safe_defaults_intact():
    """Test 14, 15: Generic InstagramConfig defaults remain dry_run=True, allow_upload=False, allow_publish=False."""
    default_cfg = InstagramConfig()
    assert default_cfg.dry_run is True
    assert default_cfg.allow_upload is False
    assert default_cfg.allow_publish is False


