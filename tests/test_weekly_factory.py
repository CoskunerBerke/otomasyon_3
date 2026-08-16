"""
Unit tests for Weekly Factory V1: 14 new reels, 42 generations, concept metadata,
7-day schedule distribution, manifest generation, safety gates, and TikTok window validation.
"""
import pytest
import json
from pathlib import Path

from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord, PublishingBatch
from automation.publishing.config import PublishingConfig
from automation.publishing.metadata_builder import PublishingMetadataBuilder
from automation.publishing.schedule_planner import SchedulePlanner
from automation.publishing.weekly_manifest import WeeklyManifestManager
from automation.publishing.publisher import PublishingOrchestrator
from automation.content.engine import ContentEngine
from automation.content.segment_planner import SegmentPlanner
from automation.content.concepts import CATEGORIES

def test_weekly_14_slots_distribution_7_days():
    slots = SchedulePlanner.generate_slots(
        start_date_str="2026-08-16",
        count=14,
        daily_slots=["19:30", "22:00"],
        timezone_str="Europe/Istanbul",
        allow_past_for_testing=True
    )
    assert len(slots) == 14

    # Slot 1 & 2: 16.08.2026 (19:30 and 22:00)
    assert slots[0][0].startswith("2026-08-16T19:30:00")
    assert slots[1][0].startswith("2026-08-16T22:00:00")

    # Slot 13 & 14: 22.08.2026 (19:30 and 22:00)
    assert slots[12][0].startswith("2026-08-22T19:30:00")
    assert slots[13][0].startswith("2026-08-22T22:00:00")

def test_tiktok_scheduling_window_validation():
    # Valid slot (e.g. 2 days ahead)
    val, msg = SchedulePlanner.validate_tiktok_schedule_window(
        local_iso_str="2026-08-18T19:30:00+03:00",
        timezone_str="Europe/Istanbul"
    )
    # We test the method signature and return format
    assert isinstance(val, bool)
    assert isinstance(msg, str)

def test_14_reels_metadata_quality_and_diversity():
    # Ensure all 14 categories generate distinct, concept-specific titles, descriptions, and hashtags
    titles = set()
    captions = set()
    hashtags_list = []

    for i, cat in enumerate(CATEGORIES[:14]):
        reel_id = f"REEL-2026-{100 + i:04d}"
        concept_title = f"{cat.architectures[0]} in {cat.environments[0]}" if cat.architectures and cat.environments else cat.category_group
        yt_t, yt_d, yt_tags = PublishingMetadataBuilder.build_youtube_metadata(
            reel_id=reel_id,
            title=concept_title,
            category=cat.category_group,
            environment=cat.environments[0] if cat.environments else "",
            architecture=cat.architectures[0] if cat.architectures else "",
            transformation=cat.transformations[0] if cat.transformations else "",
            reveal=cat.reveals[0] if cat.reveals else ""
        )
        tt_c, tt_tags = PublishingMetadataBuilder.build_tiktok_metadata(
            reel_id=reel_id,
            title=concept_title,
            category=cat.category_group,
            environment=cat.environments[0] if cat.environments else "",
            architecture=cat.architectures[0] if cat.architectures else "",
            transformation=cat.transformations[0] if cat.transformations else "",
            reveal=cat.reveals[0] if cat.reveals else ""
        )

        titles.add(yt_t)
        captions.add(tt_c)
        hashtags_list.append(yt_tags)

        # Asserts
        assert len(yt_t) <= 100
        assert len(yt_d.split(".")) >= 3  # 2-4 sentences
        assert 3 <= len(yt_tags) <= 7
        assert 3 <= len(tt_tags) <= 7
        assert "30 Seconds" in yt_t or "Step-by-Step" in yt_t or "Build" in yt_t or "Life" in yt_t or "From" in yt_t

    # Multiple distinct titles across categories
    assert len(titles) >= 4

def test_14_reels_planned_generation_count():
    engine = ContentEngine()
    history = []
    plans = engine.generate_next_reels(count=14, past_records=history)
    assert len(plans) == 14

    # 14 Reels * 3 Segments = 42 Flow generations
    total_segments = sum(len(p.segments) for p in plans)
    assert total_segments == 42
    for p in plans:
        assert p.pipeline_version == 3
        assert len(p.segments) == 3

def test_weekly_manifest_and_dashboard_generation(tmp_path: Path):
    vault = tmp_path / "Vault"
    vault.mkdir(parents=True, exist_ok=True)

    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"content" * 100)

    slots = SchedulePlanner.generate_slots(
        start_date_str="2026-08-16",
        count=2,
        daily_slots=["19:30", "22:00"],
        timezone_str="Europe/Istanbul",
        allow_past_for_testing=True
    )

    rec1 = PublishRecord(
        publish_id="PUB-REEL-2026-0001-YOUTUBE",
        batch_id="WEEKLY-BATCH-01",
        reel_id="REEL-2026-0001",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="hash1",
        title="Temple Build in 30 Seconds",
        description="Historic temple build.",
        hashtags=["#Shorts", "#Temple"],
        scheduled_at_local=slots[0][0],
        scheduled_at_utc=slots[0][1],
        status=PlatformPublicationStatus.SCHEDULED,
        remote_url="https://studio.youtube.com/video/1/edit"
    )

    rec2 = PublishRecord(
        publish_id="PUB-REEL-2026-0001-TIKTOK",
        batch_id="WEEKLY-BATCH-01",
        reel_id="REEL-2026-0001",
        platform=Platform.TIKTOK,
        account_handle="@kitchenverse360",
        video_file=dummy_video,
        video_sha256="hash1",
        title="Temple Build in 30 Seconds",
        description="Historic temple build.",
        hashtags=["#satisfying", "#build"],
        scheduled_at_local=slots[0][0],
        scheduled_at_utc=slots[0][1],
        status=PlatformPublicationStatus.SCHEDULED,
        remote_url="https://www.tiktok.com/@kitchenverse360/video/1"
    )

    batch = PublishingBatch(
        batch_id="WEEKLY-BATCH-01",
        start_date="2026-08-16",
        timezone="Europe/Istanbul",
        slots=["19:30", "22:00"],
        requested_reels=["REEL-2026-0001"],
        records=[rec1, rec2],
        schedule_slots=[("REEL-2026-0001", slots[0][0], slots[0][1])],
        status="COMPLETED"
    )

    cfg = PublishingConfig(
        schedule_start_date="2026-08-16",
        daily_slots=["19:30", "22:00"],
        youtube_expected_handle="@BuiIdVerse",
        tiktok_expected_username="@kitchenverse360"
    )

    json_p, md_p = WeeklyManifestManager.write_manifest_files(vault, batch, cfg)

    assert json_p.exists()
    assert md_p.exists()

    with open(json_p, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["batch_id"] == "WEEKLY-BATCH-01"
        assert len(data["slots"]) == 1

    md_text = md_p.read_text(encoding="utf-8")
    assert "WEEKLY PUBLISHING DASHBOARD" in md_text
    assert "@BuiIdVerse" in md_text
    assert "@kitchenverse360" in md_text
    assert "REEL-2026-0001" in md_text

def test_live_publish_safety_gate_aborts_when_disabled(tmp_path: Path):
    vault = tmp_path / "Vault"
    ready_dir = vault / "05_READY"
    ready_dir.mkdir(parents=True, exist_ok=True)

    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"content" * 100)

    (ready_dir / "REEL-2026-0001.md").write_text(f"""---
id: REEL-2026-0001
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{dummy_video}"
---""", encoding="utf-8")

    cfg = PublishingConfig(
        schedule_start_date="2026-08-16",
        live_publish_enabled=False  # Safety gate ACTIVE
    )

    orchestrator = PublishingOrchestrator(
        vault_path=vault,
        config=cfg,
        mock=False  # Attempt real
    )

    with pytest.raises(RuntimeError) as exc_info:
        orchestrator.execute_publishing_batch(count=1, dry_run=False)

    assert "LIVE PUBLISH SAFETY GATE" in str(exc_info.value)
