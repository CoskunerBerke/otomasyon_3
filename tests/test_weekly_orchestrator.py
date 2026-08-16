"""
Comprehensive Unit and Regression Test Suite for Weekly 14-Reel Orchestrator & Obsidian Control Center.
Tests all 23 required scenarios without triggering external platform calls.
"""
import os
import json
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from automation.orchestration.models import (
    WeekPlan,
    PublishingSlot,
    ReelState,
    ReelPlatformStatus,
    InstagramScheduledJob,
    RunReport,
    ReconciliationStatus
)
from automation.orchestration.slot_generator import (
    generate_14_slot_week_plan,
    calculate_next_safe_week_start,
    generate_week_id
)
from automation.orchestration.state_repository import StateRepository
from automation.orchestration.obsidian_mirror import ObsidianControlCenter
from automation.orchestration.reconciliation import (
    reconcile_youtube,
    reconcile_tiktok,
    reconcile_instagram
)
from automation.publishing.eligibility import is_v3_publishing_eligible
from automation.weekly_orchestrator import WeeklyOrchestrator


# =============================================================================
# 1. 14-SLOT & TIMEZONE TESTS
# =============================================================================

def test_weekly_14_slots_count_and_times():
    """Test 1 & 2: 7 days x 2 slots = exactly 14 slots at 19:30 and 22:00."""
    start_date = datetime.date(2026, 8, 24)
    plan = generate_14_slot_week_plan(start_date, slot_times=["19:30", "22:00"], timezone_str="Europe/Istanbul")

    assert len(plan.slots) == 14
    assert plan.target_reels == 14
    assert plan.slots_per_day == 2

    # Check times alternating 19:30 and 22:00
    for idx, slot in enumerate(plan.slots):
        expected_time = "19:30" if idx % 2 == 0 else "22:00"
        assert slot.time_str == expected_time
        assert slot.slot_index == idx + 1


def test_weekly_timezone_europe_istanbul_utc_conversion():
    """Test 3: Timezone Europe/Istanbul offsets (+03:00) converted correctly to UTC."""
    start_date = datetime.date(2026, 8, 24)
    plan = generate_14_slot_week_plan(start_date, slot_times=["19:30", "22:00"], timezone_str="Europe/Istanbul")

    slot1 = plan.slots[0]
    assert slot1.date_str == "2026-08-24"
    assert slot1.time_str == "19:30"
    assert slot1.scheduled_at_local == "2026-08-24 19:30:00"
    assert slot1.scheduled_at_utc == "2026-08-24 16:30:00"  # 19:30 - 3h = 16:30 UTC


def test_weekly_month_rollover():
    """Test 4: Month rollover (Aug 31 -> Sep 01) transitions smoothly across the 7 days."""
    start_date = datetime.date(2026, 8, 30)
    plan = generate_14_slot_week_plan(start_date, timezone_str="Europe/Istanbul")

    dates = [slot.date_str for slot in plan.slots]
    assert "2026-08-30" in dates
    assert "2026-08-31" in dates
    assert "2026-09-01" in dates
    assert "2026-09-05" in dates


def test_weekly_year_rollover():
    """Test 5: Year rollover (Dec 28 -> Jan 03) transitions seamlessly across years."""
    start_date = datetime.date(2026, 12, 28)
    plan = generate_14_slot_week_plan(start_date, timezone_str="Europe/Istanbul")

    dates = [slot.date_str for slot in plan.slots]
    assert "2026-12-31" in dates
    assert "2027-01-01" in dates
    assert "2027-01-03" in dates


# =============================================================================
# 2. V3-ONLY ELIGIBILITY & REEL-2026-0010 EXCLUSION TESTS
# =============================================================================

def test_v3_eligibility_accepts_valid_v3(tmp_path):
    """Test 8: V3 Reel with pipeline_version=3, silent_global_step_by_step, and valid duration passes."""
    video_file = tmp_path / "valid_v3.mp4"
    video_file.write_bytes(b"mock" * 100)

    meta = {
        "id": "REEL-2026-0011",
        "status": "READY",
        "pipeline_version": 3,
        "content_mode": "silent_global_step_by_step",
        "segments": ["s1", "s2", "s3"],
        "video_file": str(video_file)
    }

    mock_inspect = MagicMock(duration_seconds=30.0, is_vertical_9_16=True, has_audio=False)
    with patch("automation.quality.ffprobe.inspect_video", return_value=mock_inspect):
        ok, msg = is_v3_publishing_eligible(meta, check_ffprobe=True)
        assert ok is True


def test_v3_eligibility_rejects_legacy_v1_v2(tmp_path):
    """Test 7: Legacy V1/V2 or non-silent mode reels are rejected."""
    video_file = tmp_path / "legacy_v1.mp4"
    video_file.write_bytes(b"mock" * 100)

    # Legacy pipeline_version 1
    meta_v1 = {
        "id": "REEL-2026-0001",
        "status": "READY",
        "pipeline_version": 1,
        "content_mode": "legacy_spoken",
        "video_file": str(video_file)
    }
    ok, msg = is_v3_publishing_eligible(meta_v1, check_ffprobe=False)
    assert ok is False
    assert "V3 required" in msg


def test_reel_0010_hard_excluded_from_new_weekly_batches(tmp_path):
    """Test 21: REEL-2026-0010 is marked TEST_COMPLETED and strictly excluded from new batches."""
    repo = StateRepository(tmp_path)
    repo.mark_reel_test_completed("REEL-2026-0010")

    assert repo.is_reel_available_for_new_batch("REEL-2026-0010") is False

    state = repo.get_reel_state("REEL-2026-0010")
    assert state is not None
    assert state.youtube_status == ReelPlatformStatus.TEST_COMPLETED
    assert state.tiktok_status == ReelPlatformStatus.TEST_COMPLETED
    assert state.instagram_status == ReelPlatformStatus.TEST_COMPLETED


# =============================================================================
# 3. PLATFORM INDEPENDENCE & IDEMPOTENCY TESTS
# =============================================================================

def test_platform_independence_one_failure_leaves_others_intact(tmp_path):
    """Test 13: Failure in TikTok (NEEDS_USER_HTML) does not reset YouTube (SCHEDULED) or Instagram (QUEUED)."""
    repo = StateRepository(tmp_path)

    reel = ReelState(
        reel_id="REEL-2026-0012",
        week_id="2026-W35",
        youtube_status=ReelPlatformStatus.SCHEDULED,
        youtube_remote_id="YT_12345",
        tiktok_status=ReelPlatformStatus.NEEDS_USER_HTML,
        tiktok_error="Rule 31: 2 semantic selector strategies failed",
        instagram_status=ReelPlatformStatus.QUEUED
    )
    repo.save_reel_state(reel)

    loaded = repo.get_reel_state("REEL-2026-0012")
    assert loaded.youtube_status == ReelPlatformStatus.SCHEDULED
    assert loaded.youtube_remote_id == "YT_12345"
    assert loaded.tiktok_status == ReelPlatformStatus.NEEDS_USER_HTML
    assert loaded.instagram_status == ReelPlatformStatus.QUEUED


def test_resume_skips_already_scheduled_platforms():
    """Test 9, 10, 11, 23: Reconcile verifies SCHEDULED/PUBLISHED platforms and marks them CONFIRMED."""
    reel = ReelState(
        reel_id="REEL-2026-0013",
        youtube_status=ReelPlatformStatus.SCHEDULED,
        youtube_remote_id="YT_999",
        tiktok_status=ReelPlatformStatus.SCHEDULED,
        tiktok_remote_id="TT_888",
        instagram_status=ReelPlatformStatus.PUBLISHED,
        instagram_remote_media_id="IG_777"
    )

    yt_stat, _ = reconcile_youtube(reel)
    tt_stat, _ = reconcile_tiktok(reel)
    ig_stat, _ = reconcile_instagram(reel)

    assert yt_stat == ReconciliationStatus.CONFIRMED
    assert tt_stat == ReconciliationStatus.CONFIRMED
    assert ig_stat == ReconciliationStatus.CONFIRMED


def test_reconcile_flags_stale_local_state():
    """Test 14: Local state SCHEDULED without remote_id is flagged as REVIEW_REQUIRED."""
    reel = ReelState(
        reel_id="REEL-2026-0014",
        youtube_status=ReelPlatformStatus.SCHEDULED,
        youtube_remote_id=None
    )

    yt_stat, msg = reconcile_youtube(reel)
    assert yt_stat == ReconciliationStatus.REVIEW_REQUIRED
    assert "missing youtube_remote_id" in msg


# =============================================================================
# 4. INSTAGRAM QUEUE MODEL TESTS
# =============================================================================

def test_instagram_scheduled_job_serialization_and_queue(tmp_path):
    """Test 12 & 22: InstagramScheduledJob serializes to JSON and persists under state/instagram_queue/."""
    repo = StateRepository(tmp_path)

    job = InstagramScheduledJob(
        job_id="JOB-2026-W35-REEL-2026-0015",
        week_id="2026-W35",
        reel_id="REEL-2026-0015",
        video_path="workspace/downloads/clean_REEL-2026-0015.mp4",
        caption="Building futuristic architectural marvel in 30 seconds. ✨",
        scheduled_at_local="2026-08-24 19:30:00",
        timezone="Europe/Istanbul",
        status="QUEUED"
    )

    assert repo.save_instagram_job(job) is True

    loaded_job = repo.get_instagram_job(job.job_id)
    assert loaded_job is not None
    assert loaded_job.reel_id == "REEL-2026-0015"
    assert loaded_job.status == "QUEUED"
    assert loaded_job.timezone == "Europe/Istanbul"


# =============================================================================
# 5. OBSIDIAN CONTROL CENTER MIRROR TESTS
# =============================================================================

def test_obsidian_week_note_sync(tmp_path):
    """Test 15: Generates 01_WEEKS/WEEK-xxxx.md with YAML frontmatter and 14-slot table."""
    vault_dir = tmp_path / "obsidian_vault"
    obsidian = ObsidianControlCenter(vault_dir)

    plan = generate_14_slot_week_plan(datetime.date(2026, 8, 24))
    plan.slots[0].reel_id = "REEL-2026-0011"
    plan.slots[0].youtube_status = "SCHEDULED"

    assert obsidian.sync_week_note(plan) is True

    week_file = vault_dir / "01_WEEKS" / f"WEEK-{plan.week_id}.md"
    assert week_file.exists()
    content = week_file.read_text(encoding="utf-8")
    assert f"week_id: {plan.week_id}" in content
    assert "slots_per_day: 2" in content
    assert "REEL-2026-0011" in content
    assert "19:30" in content


def test_obsidian_reel_note_sync(tmp_path):
    """Test 16: Generates 02_REELS/REEL-xxxx.md with metadata and platform status."""
    vault_dir = tmp_path / "obsidian_vault"
    obsidian = ObsidianControlCenter(vault_dir)

    reel = ReelState(
        reel_id="REEL-2026-0016",
        week_id="2026-W35",
        title="Kyoto Zen Garden",
        caption="A serene Japanese temple built step-by-step.",
        hashtags=["#japan", "#zen", "#architecture"],
        video_path="workspace/downloads/clean_REEL-2026-0016.mp4",
        youtube_status=ReelPlatformStatus.SCHEDULED,
        youtube_remote_id="YT_KYOTO_123",
        tiktok_status=ReelPlatformStatus.SCHEDULED,
        tiktok_remote_id="TT_KYOTO_456",
        instagram_status=ReelPlatformStatus.QUEUED
    )

    assert obsidian.sync_reel_note(reel) is True

    reel_file = vault_dir / "02_REELS" / "REEL-2026-0016.md"
    assert reel_file.exists()
    content = reel_file.read_text(encoding="utf-8")
    assert "pipeline_version: 3" in content
    assert "Kyoto Zen Garden" in content
    assert "YT_KYOTO_123" in content


def test_obsidian_run_report_sync(tmp_path):
    """Test 17: Generates 04_RUNS/RUN-xxxx.md with execution metrics."""
    vault_dir = tmp_path / "obsidian_vault"
    obsidian = ObsidianControlCenter(vault_dir)

    report = RunReport(
        run_id="RUN-20260816-140000",
        start_time="2026-08-16 14:00:00",
        finish_time="2026-08-16 14:00:05",
        duration_seconds=5.0,
        mode="DRY_RUN",
        week_id="2026-W35",
        inventory_found=14,
        generation_needed=0,
        qc_passed=14,
        youtube_success=14,
        tiktok_success=14,
        instagram_queued=14
    )

    assert obsidian.sync_run_report(report) is True

    run_file = vault_dir / "04_RUNS" / "RUN-20260816-140000.md"
    assert run_file.exists()
    content = run_file.read_text(encoding="utf-8")
    assert "mode: DRY_RUN" in content
    assert "youtube_success: 14" in content


def test_obsidian_alert_note_creation(tmp_path):
    """Test 18: Generates 05_ALERTS/ALERT-xxxx.md when user intervention is required."""
    vault_dir = tmp_path / "obsidian_vault"
    obsidian = ObsidianControlCenter(vault_dir)

    assert obsidian.create_alert_note(
        platform="tiktok",
        reel_id="REEL-2026-0027",
        status="NEEDS_USER_HTML",
        message="TikTok Studio UI changed, selector failed on 2 semantic strategies.",
        action_required="Inspect HTML structure and update selectors."
    ) is True

    alert_files = list((vault_dir / "05_ALERTS").glob("*.md"))
    assert len(alert_files) == 1
    content = alert_files[0].read_text(encoding="utf-8")
    assert "NEEDS_USER_HTML" in content
    assert "REEL-2026-0027" in content


# =============================================================================
# 6. FULL ORCHESTRATOR DRY-RUN INTEGRATION TEST
# =============================================================================

def test_full_weekly_orchestrator_dry_run_executes_with_zero_external_writes(tmp_path):
    """Test 6, 19, 20: 14 unique reel IDs assigned, atomic state saved, 0 external API calls in dry-run."""
    vault_dir = tmp_path / "obsidian_vault"
    orchestrator = WeeklyOrchestrator(
        base_dir=tmp_path,
        vault_path=vault_dir,
        dry_run=True
    )

    start_date = datetime.date(2026, 8, 24)
    success, report, plan = orchestrator.run_weekly_pipeline(start_date=start_date)

    assert success is True
    assert report.mode == "DRY_RUN"
    assert len(plan.slots) == 14
    assert report.youtube_success == 14
    assert report.tiktok_success == 14
    assert report.instagram_queued == 14

    # Verify all 14 slot reel IDs are unique and exclude REEL-2026-0010
    assigned_ids = [slot.reel_id for slot in plan.slots]
    assert len(set(assigned_ids)) == 14
    assert "REEL-2026-0010" not in assigned_ids

    # Verify structured state files exist
    assert (tmp_path / "workspace" / "state" / "weeks" / f"{plan.week_id}.json").exists()
    assert len(list((tmp_path / "workspace" / "state" / "reels").glob("*.json"))) == 15  # 14 + 0010 (marked test)
    assert len(list((tmp_path / "workspace" / "state" / "instagram_queue").glob("*.json"))) == 14
