"""
Unit and integration tests for Publishing Agent V1 (YouTube Shorts + TikTok Studio).
"""
import pytest
from pathlib import Path
import datetime
from unittest.mock import MagicMock, patch

from automation.publishing.models import (
    Platform,
    PlatformPublicationStatus,
    PublishRecord,
    PublishingBatch
)
from automation.publishing.config import PublishingConfig, load_publishing_config
from automation.publishing.schedule_planner import SchedulePlanner
from automation.publishing.metadata_builder import PublishingMetadataBuilder
from automation.publishing.idempotency import IdempotencyManager
from automation.publishing.repository import PublishingRepository
from automation.publishing.youtube_auth import YouTubeAuthManager, AuthRequiredError
from automation.publishing.youtube_publisher import MockYouTubePublisher, YouTubePublisher
from automation.publishing.tiktok_publisher import MockTikTokPublisher, TikTokPublisher
from automation.publishing.tiktok_selectors import TikTokSelectors
from automation.publishing.tiktok_ui_observer import TikTokUIObserver
from automation.publishing.publisher import PublishingOrchestrator
from automation.agents import AgentManager, AgentStatus

def test_publishing_config_defaults_and_paths(tmp_path: Path):
    cfg = load_publishing_config(base_dir=tmp_path)
    assert cfg.enabled is True
    assert cfg.timezone == "Europe/Istanbul"
    assert cfg.daily_slots == ["19:30", "22:00"]
    assert cfg.schedule_start_date == "2026-08-16"
    assert cfg.youtube_enabled is True
    assert cfg.youtube_mode == "studio"
    assert cfg.youtube_studio_debug_port == 9224
    assert cfg.tiktok_enabled is True
    assert cfg.tiktok_debug_port == 9223
    assert "tiktok-profile" in str(cfg.tiktok_profile_dir)

def test_schedule_planner_14_videos_distribution():
    start_date = "2026-08-20"
    slots = SchedulePlanner.generate_slots(
        start_date_str=start_date,
        count=14,
        daily_slots=["18:00", "20:00"],
        timezone_str="Europe/Istanbul",
        allow_past_for_testing=True
    )
    assert len(slots) == 14

    # Slot 0: 2026-08-20 18:00 (+03:00) -> 15:00Z
    local_0, utc_0 = slots[0]
    assert "2026-08-20T18:00:00" in local_0
    assert "2026-08-20T15:00:00Z" == utc_0

    # Slot 1: 2026-08-20 20:00 (+03:00) -> 17:00Z
    local_1, utc_1 = slots[1]
    assert "2026-08-20T20:00:00" in local_1
    assert "2026-08-20T17:00:00Z" == utc_1

    # Slot 2: 2026-08-21 18:00
    local_2, _ = slots[2]
    assert "2026-08-21T18:00:00" in local_2

    # Slot 13: 2026-08-26 20:00 (7th day)
    local_13, _ = slots[13]
    assert "2026-08-26T20:00:00" in local_13

def test_schedule_planner_null_date_refusal():
    with pytest.raises(ValueError, match="schedule_start_date is NULL"):
        SchedulePlanner.generate_slots(start_date_str=None, count=1, daily_slots=["18:00"])

def test_metadata_builder_generates_distinct_content():
    yt_title, yt_desc, yt_tags = PublishingMetadataBuilder.build_youtube_metadata(
        reel_id="REEL-2026-0012",
        title="Japanese Zen Temple",
        category="Historic & Ancient Wonders",
        environment="misty bamboo forest",
        architecture="five-story cedar pagoda",
        transformation="timber assembly",
        reveal="illuminated ancient sanctuary"
    )
    assert "Japanese Zen Temple" in yt_title
    assert any(k in yt_title for k in ("30 Seconds", "Built", "Transformation", "Step-by-Step", "From", "Rise", "Life"))
    assert "#Shorts" in yt_tags
    assert len(yt_desc) > 30

    tt_caption, tt_tags = PublishingMetadataBuilder.build_tiktok_metadata(
        reel_id="REEL-2026-0012",
        title="Japanese Zen Temple",
        category="Historic & Ancient Wonders",
        environment="misty bamboo forest",
        architecture="five-story cedar pagoda",
        transformation="timber assembly",
        reveal="illuminated ancient sanctuary"
    )
    assert "Japanese Zen Temple" in tt_caption or "misty bamboo forest" in tt_caption
    assert "#satisfying" in tt_tags
    assert "#aitok" in tt_tags

def test_idempotency_sha256_and_skip_logic(tmp_path: Path):
    dummy_video = tmp_path / "test.mp4"
    dummy_video.write_bytes(b"dummy video content for sha256 calculation")

    sha = IdempotencyManager.compute_file_sha256(dummy_video)
    assert len(sha) == 64

    existing = {
        "REEL-2026-0003_youtube": PublishRecord(
            publish_id="PUB-REEL-2026-0003-YOUTUBE",
            batch_id="PUB-BATCH-01",
            reel_id="REEL-2026-0003",
            platform=Platform.YOUTUBE,
            video_file=dummy_video,
            video_sha256=sha,
            title="Test",
            description="Test",
            hashtags=[],
            scheduled_at_local="2026-08-20T18:00:00",
            scheduled_at_utc="2026-08-20T15:00:00Z",
            status=PlatformPublicationStatus.SCHEDULED,
            remote_id="yt_12345"
        ),
        "REEL-2026-0003_tiktok": PublishRecord(
            publish_id="PUB-REEL-2026-0003-TIKTOK",
            batch_id="PUB-BATCH-01",
            reel_id="REEL-2026-0003",
            platform=Platform.TIKTOK,
            video_file=dummy_video,
            video_sha256=sha,
            title="Test",
            description="Test",
            hashtags=[],
            scheduled_at_local="2026-08-20T18:00:00",
            scheduled_at_utc="2026-08-20T15:00:00Z",
            status=PlatformPublicationStatus.FAILED,
            last_error="AUTH_REQUIRED"
        )
    }

    # YouTube should be skipped
    yt_skip, yt_reason = IdempotencyManager.should_skip_platform("REEL-2026-0003", Platform.YOUTUBE, existing)
    assert yt_skip is True
    assert "Already SCHEDULED" in yt_reason

    # TikTok should be retried
    tt_skip, tt_reason = IdempotencyManager.should_skip_platform("REEL-2026-0003", Platform.TIKTOK, existing)
    assert tt_skip is False
    assert "Eligible for upload/retry" in tt_reason

def test_publishing_repository_writes_records_and_queue(tmp_path: Path):
    vault = tmp_path / "Vault"
    repo = PublishingRepository(vault)

    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"video bytes")

    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0012-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0012",
        platform=Platform.YOUTUBE,
        video_file=dummy_video,
        video_sha256="abc123sha",
        title="Japanese Zen Temple Built in 30 Seconds",
        description="Step by step transformation...",
        hashtags=["#Shorts", "#Satisfying"],
        scheduled_at_local="2026-08-20T18:00:00+03:00",
        scheduled_at_utc="2026-08-20T15:00:00Z",
        status=PlatformPublicationStatus.SCHEDULED,
        remote_id="yt_mock_id_999"
    )

    rec_file = repo.save_publish_record(rec)
    assert rec_file.exists()
    content = rec_file.read_text(encoding="utf-8")
    assert "node_type: publish_record" in content
    assert "[[REEL-2026-0012]]" in content
    assert "[[PUBLISH_AGENT]]" in content
    assert "yt_mock_id_999" in content

    # Test Queue creation
    queue_file = repo.update_publishing_queue([rec])
    assert queue_file.exists()
    q_content = queue_file.read_text(encoding="utf-8")
    assert "REELS AI FACTORY — LIVE PUBLISHING QUEUE" in q_content
    assert "[[REEL-2026-0012]]" in q_content
    assert "SCHEDULED" in q_content

def test_youtube_auth_raises_auth_required_when_secret_missing(tmp_path: Path):
    sec_path = tmp_path / "non_existent_secret.json"
    tok_path = tmp_path / "non_existent_token.json"

    with pytest.raises(AuthRequiredError, match="client_secret file not found"):
        YouTubeAuthManager.get_authenticated_service(sec_path, tok_path, interactive=False)

def test_mock_youtube_publisher_schedules_successfully(tmp_path: Path):
    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"content")

    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0012-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0012",
        platform=Platform.YOUTUBE,
        video_file=dummy_video,
        video_sha256="abc",
        title="Title",
        description="Desc",
        hashtags=["#Shorts"],
        scheduled_at_local="2026-08-20T18:00:00",
        scheduled_at_utc="2026-08-20T15:00:00Z"
    )

    pub = MockYouTubePublisher()
    updated_rec = pub.upload_and_schedule(rec)
    assert updated_rec.status == PlatformPublicationStatus.SCHEDULED
    assert updated_rec.remote_id.startswith("mock_yt_")
    assert "https://youtu.be/" in updated_rec.remote_url

def test_mock_tiktok_publisher_schedules_successfully(tmp_path: Path):
    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"content")

    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0012-TIKTOK",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0012",
        platform=Platform.TIKTOK,
        video_file=dummy_video,
        video_sha256="abc",
        title="Caption",
        description="",
        hashtags=["#satisfying"],
        scheduled_at_local="2026-08-20T18:00:00",
        scheduled_at_utc="2026-08-20T15:00:00Z"
    )

    pub = MockTikTokPublisher()
    updated_rec = pub.upload_and_schedule(rec)
    assert updated_rec.status == PlatformPublicationStatus.SCHEDULED
    assert updated_rec.remote_id.startswith("mock_tt_")
    assert "tiktok.com" in updated_rec.remote_url

def test_publishing_orchestrator_mock_run_and_agent_lifecycle(tmp_path: Path):
    vault = tmp_path / "Vault"
    ready_dir = vault / "05_READY"
    ready_dir.mkdir(parents=True, exist_ok=True)

    dummy_video = tmp_path / "REEL-2026-0012_Japanese_Zen_Temple.mp4"
    dummy_video.write_bytes(b"dummy mp4 video bytes" * 1000)

    # Create a 05_READY Reel note
    note_file = ready_dir / "REEL-2026-0012.md"
    note_file.write_text(f"""---
id: REEL-2026-0012
title: Japanese Zen Temple
category: Historic & Ancient Wonders
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{dummy_video}"
---

# REEL-2026-0012: Japanese Zen Temple

# Agent Graph
- [[IDEA_AGENT]]
""", encoding="utf-8")

    agent_mgr = AgentManager(vault)
    pub_agent = agent_mgr.agents["PUBLISH_AGENT"]
    pub_agent.enable()
    assert pub_agent.status == AgentStatus.IDLE

    # Ensure ANALYTICS_AGENT remains DISABLED
    assert agent_mgr.agents["ANALYTICS_AGENT"].status == AgentStatus.DISABLED

    cfg = PublishingConfig(
        schedule_start_date="2026-08-20",
        daily_slots=["18:00", "20:00"],
        timezone="Europe/Istanbul"
    )

    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=cfg,
        agent_manager=agent_mgr,
        mock=True
    )

    # Execute Mock Publishing
    batch = orchestrator.execute_publishing_batch(count=1, dry_run=False)

    assert batch.status == "COMPLETED"
    assert len(batch.records) == 2  # 1 YouTube + 1 TikTok
    assert all(r.status == PlatformPublicationStatus.SCHEDULED for r in batch.records)

    # Verify 13_PUBLISHING was created with queue and record notes
    pub_dir = vault / "13_PUBLISHING"
    assert pub_dir.exists()
    assert (pub_dir / "PUBLISHING_QUEUE.md").exists()
    assert (pub_dir / "PUB-REEL-2026-0012-YOUTUBE.md").exists()
    assert (pub_dir / "PUB-REEL-2026-0012-TIKTOK.md").exists()

    # Verify Reel note received ## Publishing Metadata and record links
    updated_note = note_file.read_text(encoding="utf-8")
    assert "Publishing Metadata" in updated_note
    assert "[[PUB-REEL-2026-0012-YOUTUBE]]" in updated_note
    assert "[[PUB-REEL-2026-0012-TIKTOK]]" in updated_note

def test_dry_run_never_creates_scheduled_and_remote_id_is_null(tmp_path: Path):
    vault = tmp_path / "Vault"
    ready_dir = vault / "05_READY"
    ready_dir.mkdir(parents=True, exist_ok=True)

    dummy_video = tmp_path / "REEL-2026-0013.mp4"
    dummy_video.write_bytes(b"dummy mp4" * 1000)

    note_file = ready_dir / "REEL-2026-0013.md"
    note_file.write_text(f"""---
id: REEL-2026-0013
title: Desert Oasis Palace
category: Extreme & Off-Grid Habitats
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{dummy_video}"
---
# REEL-2026-0013
""", encoding="utf-8")

    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=PublishingConfig(),
        mock=False
    )

    batch = orchestrator.execute_publishing_batch(count=1, start_date_override="2026-08-25", dry_run=True)
    assert batch.status == "COMPLETED"
    assert len(batch.records) == 2
    for r in batch.records:
        assert r.status == PlatformPublicationStatus.METADATA_READY
        assert r.remote_id is None
        assert r.remote_url is None
        assert r.dry_run is True

def test_dry_run_record_does_not_block_later_live_upload(tmp_path: Path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"content")

    existing_dry_run = {
        "REEL-2026-0013_youtube": PublishRecord(
            publish_id="PUB-REEL-2026-0013-YOUTUBE",
            batch_id="PUB-BATCH-01",
            reel_id="REEL-2026-0013",
            platform=Platform.YOUTUBE,
            account_handle="@BuiIdVerse",
            video_file=dummy_video,
            video_sha256="abc",
            title="Title",
            description="Desc",
            hashtags=[],
            scheduled_at_local="2026-08-25T18:00:00",
            scheduled_at_utc="2026-08-25T15:00:00Z",
            status=PlatformPublicationStatus.METADATA_READY,
            dry_run=True,
            remote_id=None
        )
    }

    should_skip, reason = IdempotencyManager.should_skip_platform("REEL-2026-0013", Platform.YOUTUBE, existing_dry_run)
    assert should_skip is False
    assert "Eligible for live upload" in reason

def test_live_verified_scheduled_record_blocks_duplicate(tmp_path: Path):
    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"content")

    existing_live = {
        "REEL-2026-0013_youtube": PublishRecord(
            publish_id="PUB-REEL-2026-0013-YOUTUBE",
            batch_id="PUB-BATCH-01",
            reel_id="REEL-2026-0013",
            platform=Platform.YOUTUBE,
            account_handle="@BuiIdVerse",
            video_file=dummy_video,
            video_sha256="abc",
            title="Title",
            description="Desc",
            hashtags=[],
            scheduled_at_local="2026-08-25T18:00:00",
            scheduled_at_utc="2026-08-25T15:00:00Z",
            status=PlatformPublicationStatus.SCHEDULED,
            dry_run=False,
            remote_id="real_yt_id_12345"
        )
    }

    should_skip, reason = IdempotencyManager.should_skip_platform("REEL-2026-0013", Platform.YOUTUBE, existing_live)
    assert should_skip is True
    assert "Already SCHEDULED" in reason

def test_live_scheduling_with_null_start_date_aborts(tmp_path: Path):
    vault = tmp_path / "Vault"
    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=PublishingConfig(schedule_start_date=None)
    )

    with pytest.raises(ValueError, match="LIVE SCHEDULING BLOCKED"):
        orchestrator.execute_publishing_batch(count=1, start_date_override=None, dry_run=False)

def test_strict_count_aborts_when_fewer_eligible_reels(tmp_path: Path):
    vault = tmp_path / "Vault"
    ready_dir = vault / "05_READY"
    ready_dir.mkdir(parents=True, exist_ok=True)

    # Only 2 reels exist
    for i in [1, 2]:
        v = tmp_path / f"video_{i}.mp4"
        v.write_bytes(b"mp4 content" * 100)
        (ready_dir / f"REEL-2026-{i:04d}.md").write_text(f"""---
id: REEL-2026-{i:04d}
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{v}"
---""", encoding="utf-8")

    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=PublishingConfig(strict_count=True, schedule_start_date="2026-08-25")
    )

    # Request 14 reels when only 2 are available
    with pytest.raises(ValueError, match="STRICT COUNT ABORT"):
        orchestrator.execute_publishing_batch(count=14, start_date_override="2026-08-25", dry_run=False, allow_partial=False)

def test_allow_partial_flag_succeeds_when_requested_exceeds_available(tmp_path: Path):
    vault = tmp_path / "Vault"
    ready_dir = vault / "05_READY"
    ready_dir.mkdir(parents=True, exist_ok=True)

    v = tmp_path / "video_1.mp4"
    v.write_bytes(b"mp4 content" * 100)
    (ready_dir / "REEL-2026-0001.md").write_text(f"""---
id: REEL-2026-0001
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{v}"
---""", encoding="utf-8")

    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=PublishingConfig(strict_count=True, schedule_start_date="2026-08-25"),
        mock=True
    )

    batch = orchestrator.execute_publishing_batch(count=14, start_date_override="2026-08-25", dry_run=False, allow_partial=True)
    assert batch.status == "COMPLETED"
    assert len(batch.requested_reels) == 1

def test_youtube_scopes_contain_upload_and_readonly():
    from automation.publishing.youtube_auth import SCOPES
    assert "https://www.googleapis.com/auth/youtube.upload" in SCOPES
    assert "https://www.googleapis.com/auth/youtube.readonly" in SCOPES

def test_youtube_account_verification_pass_and_mismatch():
    mock_client = MagicMock()
    # Correct account with handle
    mock_client.channels().list().execute.return_value = {
        "items": [{
            "id": "UC12345678",
            "snippet": {
                "title": "BuildVerse Channel",
                "customUrl": "@BuiIdVerse"
            }
        }]
    }

    is_match, msg, info = YouTubeAuthManager.verify_authenticated_channel(mock_client, expected_handle="@BuiIdVerse")
    assert is_match is True
    assert "Verified" in msg
    assert info.get("channel_id") == "UC12345678"

    # Mismatch account
    mock_client.channels().list().execute.return_value = {
        "items": [{
            "id": "UC99999999",
            "snippet": {
                "title": "Wrong Gaming Channel",
                "customUrl": "@WrongAccount"
            }
        }]
    }

    is_match_bad, msg_bad, info_bad = YouTubeAuthManager.verify_authenticated_channel(mock_client, expected_handle="@BuiIdVerse")
    assert is_match_bad is False
    assert "ACCOUNT_MISMATCH" in msg_bad
    assert info_bad.get("error_type") == "ACCOUNT_MISMATCH"

def test_youtube_insufficient_permissions_returns_reauth_required_not_account_mismatch():
    mock_client = MagicMock()
    mock_client.channels().list().execute.side_effect = Exception(
        "<HttpError 403 when requesting https://youtube.googleapis.com/youtube/v3/channels?mine=true&part=snippet%2Cid returned 'The request cannot be completed because you have exceeded your quota or have insufficient permissions.' Details: [{'message': 'insufficient permissions', 'domain': 'youtube.quota', 'reason': 'insufficientPermissions'}]>"
    )

    is_match, msg, info = YouTubeAuthManager.verify_authenticated_channel(mock_client, expected_handle="@BuiIdVerse")
    assert is_match is False
    assert "REAUTH_REQUIRED" in msg
    assert "ACCOUNT_MISMATCH" not in msg
    assert info.get("error_type") == "REAUTH_REQUIRED"

def test_youtube_missing_custom_url_matching_channel_id_passes():
    mock_client = MagicMock()
    # Channel without customUrl / handle, but channel ID matches persisted ID
    mock_client.channels().list().execute.return_value = {
        "items": [{
            "id": "UC_EXACT_PERSISTED_ID",
            "snippet": {
                "title": "BuildVerse Official",
                "customUrl": None
            }
        }]
    }

    is_match, msg, info = YouTubeAuthManager.verify_authenticated_channel(
        mock_client,
        expected_handle="@BuiIdVerse",
        expected_channel_id="UC_EXACT_PERSISTED_ID"
    )
    assert is_match is True
    assert "Verified" in msg
    assert info.get("channel_id") == "UC_EXACT_PERSISTED_ID"

def test_mock_youtube_publisher_mismatch_returns_account_mismatch(tmp_path: Path):
    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"content")

    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0012-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0012",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="abc",
        title="Title",
        description="Desc",
        hashtags=["#Shorts"],
        scheduled_at_local="2026-08-20T18:00:00",
        scheduled_at_utc="2026-08-20T15:00:00Z"
    )

    pub = MockYouTubePublisher(simulate_mismatch=True, expected_handle="@BuiIdVerse")
    res = pub.upload_and_schedule(rec)
    assert res.status == PlatformPublicationStatus.ACCOUNT_MISMATCH
    assert "ACCOUNT_MISMATCH" in res.last_error

def test_mock_tiktok_publisher_mismatch_returns_account_mismatch(tmp_path: Path):
    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"content")

    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0012-TIKTOK",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0012",
        platform=Platform.TIKTOK,
        account_handle="@kitchenverse360",
        video_file=dummy_video,
        video_sha256="abc",
        title="Title",
        description="",
        hashtags=["#satisfying"],
        scheduled_at_local="2026-08-20T18:00:00",
        scheduled_at_utc="2026-08-20T15:00:00Z"
    )

    pub = MockTikTokPublisher(simulate_mismatch=True, expected_username="@kitchenverse360")
    res = pub.upload_and_schedule(rec)
    assert res.status == PlatformPublicationStatus.ACCOUNT_MISMATCH
    assert "ACCOUNT_MISMATCH" in res.last_error

def test_sanitize_existing_dry_run_records_in_repository(tmp_path: Path):
    vault = tmp_path / "Vault"
    repo = PublishingRepository(vault)

    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"content")

    # Save a record with fake remote_id and dry_run: true
    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0001-YOUTUBE",
        batch_id="PUB-BATCH-01",
        reel_id="REEL-2026-0001",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="abc",
        title="Title",
        description="",
        hashtags=[],
        scheduled_at_local="2026-08-20T18:00:00",
        scheduled_at_utc="2026-08-20T15:00:00Z",
        status=PlatformPublicationStatus.SCHEDULED,
        remote_id="mock_yt_12345",
        dry_run=True
    )
    repo.save_publish_record(rec)

    # Sanitize
    count = repo.sanitize_existing_dry_run_records()
    assert count >= 1

    # Reload record
    records = repo.load_all_records()
    sanitized_rec = records["REEL-2026-0001_youtube"]
    assert sanitized_rec.status == PlatformPublicationStatus.METADATA_READY
    assert sanitized_rec.remote_id is None
    assert sanitized_rec.remote_url is None
    assert sanitized_rec.dry_run is True

def test_youtube_login_bat_syntax_and_encoding():
    bat_file = Path("YOUTUBE_LOGIN.bat").resolve()
    assert bat_file.exists(), "YOUTUBE_LOGIN.bat must exist in project root"
    raw_bytes = bat_file.read_bytes()

    # Must NOT start with UTF-8 BOM
    assert not raw_bytes.startswith(b"\xef\xbb\xbf"), "YOUTUBE_LOGIN.bat must NOT contain UTF-8 BOM"

    text = raw_bytes.decode("ascii")  # Strict ASCII validation
    assert "@echo off" in text
    assert "PYTHON_EXE" in text
    assert "googleapiclient" in text
    assert "secrets\\youtube\\client_secret.json" in text
    assert "automation\\publish.py --youtube-auth" in text

def test_google_oauth_dependencies_importable():
    import googleapiclient
    import google_auth_oauthlib
    import google.auth
    assert googleapiclient is not None
    assert google_auth_oauthlib is not None
    assert google.auth is not None

def test_client_secret_detection():
    secret_path = Path("secrets/youtube/client_secret.json").resolve()
    assert secret_path.exists(), "secrets/youtube/client_secret.json should exist for production OAuth"
    assert secret_path.stat().st_size > 0


def test_orchestrator_execute_preflight_success_both_ready(tmp_path: Path):
    """Test execute_preflight prepares metadata, runs both preflights, and returns True with 0 final clicks."""
    vault = tmp_path / "Vault"
    ready_dir = vault / "05_READY"
    ready_dir.mkdir(parents=True, exist_ok=True)

    v = tmp_path / "video_1.mp4"
    v.write_bytes(b"mp4 content" * 100)
    (ready_dir / "REEL-2026-0010.md").write_text(f"""---
id: REEL-2026-0010
title: "Japanese Zen Temple"
concept: "Japanese Zen Temple"
location: "Kyoto"
architecture: "Traditional Zen"
transformation: "Construction"
reveal: "Sunset"
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{v}"
youtube_remote_id: "Sq1nDGQPpOc"
---""", encoding="utf-8")

    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=PublishingConfig(schedule_start_date="2026-08-16"),
        mock=True
    )

    success, records = orchestrator.execute_preflight(count=1, start_date_override="2026-08-16")
    assert success is True
    assert len(records) == 2

    yt_rec = [r for r in records if r.platform == Platform.YOUTUBE][0]
    tt_rec = [r for r in records if r.platform == Platform.TIKTOK][0]

    # Preflight status must NOT be SCHEDULED (verification requires commit)
    assert yt_rec.status == PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
    assert yt_rec.schedule_verified is False
    assert tt_rec.status == PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
    assert tt_rec.schedule_verified is False


def test_orchestrator_execute_commit_submits_both_and_marks_scheduled(tmp_path: Path):
    """Test execute_commit submits final schedules and marks both records SCHEDULED with verification."""
    vault = tmp_path / "Vault"
    ready_dir = vault / "05_READY"
    ready_dir.mkdir(parents=True, exist_ok=True)

    v = tmp_path / "video_1.mp4"
    v.write_bytes(b"mp4 content" * 100)
    (ready_dir / "REEL-2026-0010.md").write_text(f"""---
id: REEL-2026-0010
title: "Japanese Zen Temple"
concept: "Japanese Zen Temple"
location: "Kyoto"
architecture: "Traditional Zen"
transformation: "Construction"
reveal: "Sunset"
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{v}"
youtube_remote_id: "Sq1nDGQPpOc"
---""", encoding="utf-8")

    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=PublishingConfig(schedule_start_date="2026-08-16"),
        mock=True
    )

    # 1. Run Preflight first
    preflight_ok, p_records = orchestrator.execute_preflight(count=1, start_date_override="2026-08-16")
    assert preflight_ok is True

    # 2. Run Commit
    commit_ok, c_records = orchestrator.execute_commit(count=1, start_date_override="2026-08-16")
    assert commit_ok is True
    assert len(c_records) == 2

    yt_rec = [r for r in c_records if r.platform == Platform.YOUTUBE][0]
    tt_rec = [r for r in c_records if r.platform == Platform.TIKTOK][0]

    assert yt_rec.status == PlatformPublicationStatus.SCHEDULED
    assert yt_rec.schedule_verified is True
    assert tt_rec.status == PlatformPublicationStatus.SCHEDULED
    assert tt_rec.schedule_verified is True


def test_orchestrator_preflight_fail_fast_skips_tiktok(tmp_path: Path):
    """Test that if YouTube preflight fails, TikTok preflight is skipped immediately."""
    vault = tmp_path / "Vault"
    ready_dir = vault / "05_READY"
    ready_dir.mkdir(parents=True, exist_ok=True)

    v = tmp_path / "video_1.mp4"
    v.write_bytes(b"mp4 content" * 100)
    (ready_dir / "REEL-2026-0010.md").write_text(f"""---
id: REEL-2026-0010
title: "Japanese Zen Temple"
concept: "Japanese Zen Temple"
location: "Kyoto"
architecture: "Traditional Zen"
transformation: "Construction"
reveal: "Sunset"
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{v}"
youtube_remote_id: "Sq1nDGQPpOc"
---""", encoding="utf-8")

    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=PublishingConfig(schedule_start_date="2026-08-16"),
        mock=True
    )

    # Force YouTube publisher preflight to fail
    orchestrator.yt_publisher.prepare_preflight = MagicMock(return_value=(False, "YOUTUBE_SIMULATED_FAIL"))
    orchestrator.tt_publisher.prepare_preflight = MagicMock()

    ok, records = orchestrator.execute_preflight(count=1, start_date_override="2026-08-16")
    assert ok is False
    # TikTok preflight must NOT have been called due to fail-fast
    orchestrator.tt_publisher.prepare_preflight.assert_not_called()



