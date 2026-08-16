"""
Comprehensive Unit Test Suite for Weekly 14-Reel Orchestrator.
Tests 14 slots (19:30 & 22:00), Flow generation wiring, YouTube Studio wiring, TikTok Studio wiring,
media handoff wiring, exclusion of REEL-2026-0010, idempotency/resume, and independent platform failures.
Uses strict mocks only: 0 real Flow calls, 0 real YouTube writes, 0 real TikTok writes, 0 real S3 uploads.
"""
import os
import datetime
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.weekly_orchestrator import WeeklyOrchestrator
from automation.orchestration.models import (
    WeekPlan,
    PublishingSlot,
    ReelState,
    ReelPlatformStatus,
    RunReport
)
from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord


def test_weekly_orchestrator_generates_14_slots(tmp_path):
    """Test: Weekly orchestrator generates exactly 14 slots (7 days x 19:30 & 22:00)."""
    orchestrator = WeeklyOrchestrator(base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=True)
    start_date = datetime.date(2026, 8, 17)

    ok, report, plan = orchestrator.run_weekly_pipeline(start_date=start_date, week_id="2026-W34")

    assert ok is True
    assert len(plan.slots) == 14
    assert plan.target_reels == 14

    times = [s.time_str for s in plan.slots]
    assert times == ["19:30", "22:00"] * 7


def test_weekly_orchestrator_excludes_reel_0010(tmp_path):
    """Test: REEL-2026-0010 is strictly excluded and marked TEST_COMPLETED."""
    orchestrator = WeeklyOrchestrator(base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=True)
    start_date = datetime.date(2026, 8, 17)

    # Pre-create REEL-2026-0010 video in downloads
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    (dl_dir / "clean_REEL-2026-0010.mp4").write_bytes(b"test completed reel bytes")

    ok, report, plan = orchestrator.run_weekly_pipeline(start_date=start_date, week_id="2026-W34")

    assigned_reel_ids = [s.reel_id for s in plan.slots]
    assert "REEL-2026-0010" not in assigned_reel_ids
    assert orchestrator.repo.is_reel_available_for_new_batch("REEL-2026-0010") is False


def test_weekly_orchestrator_live_pipeline_wiring(tmp_path):
    """Test: Live pipeline calls Flow generator, YouTube publisher, TikTok publisher, and media handoff."""
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)

    # Mock Flow provider
    mock_flow = MagicMock()
    def fake_generate(plan, reel_id, target_filename, **kwargs):
        fake_video = dl_dir / f"clean_{reel_id}.mp4"
        fake_video.write_bytes(b"mock video bytes 1234567890")
        return fake_video
    mock_flow.generate_single_video.side_effect = fake_generate

    # Mock YouTube publisher
    mock_yt = MagicMock()
    def fake_yt_schedule(record: PublishRecord):
        record.status = PlatformPublicationStatus.SCHEDULED
        record.remote_video_id = f"yt_vid_{record.reel_id}"
        record.remote_url = f"https://youtube.com/shorts/{record.reel_id}"
        return record
    mock_yt.upload_and_schedule.side_effect = fake_yt_schedule

    # Mock TikTok publisher
    mock_tt = MagicMock()
    def fake_tt_schedule(record: PublishRecord):
        record.status = PlatformPublicationStatus.SCHEDULED
        record.remote_video_id = f"tt_vid_{record.reel_id}"
        return record
    mock_tt.upload_and_schedule.side_effect = fake_tt_schedule

    # Mock Cloud Client for media handoff
    mock_client = MagicMock()
    mock_client.upload_media_for_instagram.return_value = (
        True,
        {
            "ok": True,
            "status": "MEDIA_READY",
            "media_object_key": "media/2026-W34/REEL-2026-0011/sha.mp4",
            "idempotent": False
        },
        None
    )

    orchestrator = WeeklyOrchestrator(
        base_dir=tmp_path,
        vault_path=tmp_path / "vault",
        dry_run=False,
        flow_provider=mock_flow,
        yt_publisher=mock_yt,
        tt_publisher=mock_tt,
        cloud_client=mock_client
    )

    start_date = datetime.date(2026, 8, 17)
    with patch("automation.weekly_orchestrator.VideoValidator") as mock_validator_cls:
        mock_val = MagicMock()
        mock_val.process_and_validate.side_effect = lambda input_video, output_dir: MagicMock(
            is_passed=True,
            processed_video_path=input_video
        )
        mock_validator_cls.return_value = mock_val

        ok, report, plan = orchestrator.run_weekly_pipeline(start_date=start_date, week_id="2026-W34")

    assert ok is True
    assert report.youtube_success == 14
    assert report.tiktok_success == 14
    assert report.instagram_queued == 14
    assert len(report.errors) == 0

    assert mock_flow.generate_single_video.call_count == 14
    assert mock_yt.upload_and_schedule.call_count == 14
    assert mock_tt.upload_and_schedule.call_count == 14
    assert mock_client.upload_media_for_instagram.call_count == 14


def test_weekly_orchestrator_handles_independent_platform_failures(tmp_path):
    """Test: If YouTube fails, TikTok and Instagram continue independently."""
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)

    # Pre-populate 14 ready videos
    for i in range(11, 25):
        vid = dl_dir / f"clean_REEL-2026-{i:04d}.mp4"
        vid.write_bytes(b"ready reel content")

    # YouTube fails
    mock_yt = MagicMock()
    def failing_yt(record: PublishRecord):
        record.status = PlatformPublicationStatus.FAILED_RETRYABLE
        record.error_message = "YouTube Studio connection timeout"
        return record
    mock_yt.upload_and_schedule.side_effect = failing_yt

    # TikTok succeeds
    mock_tt = MagicMock()
    def succeeding_tt(record: PublishRecord):
        record.status = PlatformPublicationStatus.SCHEDULED
        return record
    mock_tt.upload_and_schedule.side_effect = succeeding_tt

    # Instagram handoff succeeds
    mock_client = MagicMock()
    mock_client.upload_media_for_instagram.return_value = (
        True,
        {"ok": True, "status": "MEDIA_READY", "media_object_key": "media/test.mp4"},
        None
    )

    orchestrator = WeeklyOrchestrator(
        base_dir=tmp_path,
        vault_path=tmp_path / "vault",
        dry_run=False,
        yt_publisher=mock_yt,
        tt_publisher=mock_tt,
        cloud_client=mock_client
    )

    start_date = datetime.date(2026, 8, 17)
    ok, report, plan = orchestrator.run_weekly_pipeline(start_date=start_date, week_id="2026-W34")

    # Pipeline tracks YouTube errors but TikTok and Instagram succeed
    assert report.youtube_success == 0
    assert report.tiktok_success == 14
    assert report.instagram_queued == 14
    assert len(report.errors) == 14

    for slot in plan.slots:
        assert slot.youtube_status == "FAILED_RETRYABLE"
        assert slot.tiktok_status == "SCHEDULED"
        assert slot.instagram_status == "MEDIA_READY"


def test_weekly_orchestrator_preserves_needs_user_html(tmp_path):
    """Test: If TikTok returns NEEDS_USER_HTML (Rule 31), the state is preserved."""
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)

    for i in range(11, 25):
        vid = dl_dir / f"clean_REEL-2026-{i:04d}.mp4"
        vid.write_bytes(b"ready reel content")

    mock_yt = MagicMock()
    mock_yt.upload_and_schedule.side_effect = lambda r: setattr(r, "status", PlatformPublicationStatus.SCHEDULED) or r

    mock_tt = MagicMock()
    def user_html_tt(record: PublishRecord):
        record.status = "NEEDS_USER_HTML"
        record.error_message = "TikTok Studio UI changed (Rule 31: max 2 attempts reached)"
        return record
    mock_tt.upload_and_schedule.side_effect = user_html_tt

    mock_client = MagicMock()
    mock_client.upload_media_for_instagram.return_value = (
        True,
        {"ok": True, "status": "MEDIA_READY", "media_object_key": "media/test.mp4"},
        None
    )

    orchestrator = WeeklyOrchestrator(
        base_dir=tmp_path,
        vault_path=tmp_path / "vault",
        dry_run=False,
        yt_publisher=mock_yt,
        tt_publisher=mock_tt,
        cloud_client=mock_client
    )

    start_date = datetime.date(2026, 8, 17)
    ok, report, plan = orchestrator.run_weekly_pipeline(start_date=start_date, week_id="2026-W34")

    for slot in plan.slots:
        assert slot.tiktok_status == "NEEDS_USER_HTML"


def test_weekly_orchestrator_resume_skips_already_done(tmp_path):
    """Test: Re-running on an already completed week skips re-executing publishers."""
    mock_yt = MagicMock()
    mock_tt = MagicMock()
    mock_client = MagicMock()

    orchestrator = WeeklyOrchestrator(
        base_dir=tmp_path,
        vault_path=tmp_path / "vault",
        dry_run=False,
        yt_publisher=mock_yt,
        tt_publisher=mock_tt,
        cloud_client=mock_client
    )
    start_date = datetime.date(2026, 8, 17)

    # Pre-populate 14 video files on disk so resolution succeeds
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    for i in range(14):
        (dl_dir / f"clean_REEL-2026-{11 + i:04d}.mp4").write_bytes(b"ready video")

    # Pre-save week plan with all slots SCHEDULED & MEDIA_READY
    plan = WeekPlan(
        week_id="2026-W34",
        start_date="2026-08-17",
        timezone="Europe/Istanbul",
        target_reels=14,
        slots_per_day=2,
        slots=[
            PublishingSlot(
                slot_index=i + 1,
                day_number=(i // 2) + 1,
                date_str="2026-08-17",
                time_str="19:30" if i % 2 == 0 else "22:00",
                scheduled_at_local="2026-08-17 19:30:00",
                scheduled_at_utc="2026-08-17 16:30:00",
                reel_id=f"REEL-2026-{11 + i:04d}",
                youtube_status="SCHEDULED",
                tiktok_status="SCHEDULED",
                instagram_status="MEDIA_READY",
                qc_status="PASS"
            )
            for i in range(14)
        ]
    )
    orchestrator.repo.save_week_plan(plan)

    ok, report, res_plan = orchestrator.run_weekly_pipeline(start_date=start_date, week_id="2026-W34")

    assert ok is True
    # Publishers should not be called again
    mock_yt.upload_and_schedule.assert_not_called()
    mock_tt.upload_and_schedule.assert_not_called()
    mock_client.upload_media_for_instagram.assert_not_called()
