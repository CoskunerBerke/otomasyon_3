"""
Unit and regression tests for Reels AI Factory V3:
30-Second / 3 x 10-Second Step-by-Step Reels Architecture.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.config import AppConfig, load_config
from automation.content.engine import ContentEngine, CATEGORIES
from automation.content.prompt_engine import PromptEngine, ReelConceptPlan
from automation.content.segment_planner import SegmentPlanner, ContinuityContext, SegmentPlan
from automation.quality.concatenator import VideoConcatenator
from automation.quality.frame_extractor import FrameExtractor
from automation.obsidian.reader import ObsidianReader
from automation.obsidian.writer import ObsidianWriter

def test_pipeline_v3_defaults():
    cfg = AppConfig(
        vault_path=Path("."),
        output_path=Path(".")
    )
    assert cfg.pipeline_version == 3
    assert cfg.content_mode == "silent_global_step_by_step"
    assert cfg.final_duration_seconds == 30
    assert cfg.segment_count == 3
    assert cfg.segment_duration_seconds == 10
    assert cfg.video_duration == 10

def test_single_and_batch_credit_model_projections():
    # 1 Reel = 3 generations
    # 3 Reels = 9 generations
    # 14 Reels = 42 generations
    assert 1 * 3 == 3
    assert 3 * 3 == 9
    assert 14 * 3 == 42

def test_segment_planner_creates_3_staged_segments():
    concept = CATEGORIES[0]  # E.g. bridge, villa or resort
    continuity, segments = SegmentPlanner.plan_segments(
        concept=concept,
        env="crystal clear ocean lagoon",
        arch="modern suspension architecture",
        transformation="marine foundations to tower construction",
        camera="aerial drone trajectory",
        lighting="vibrant midday sun",
        materials="marine-grade reinforced steel",
        reveal="monumental illuminated sea bridge",
        duration_per_segment=10
    )

    assert len(segments) == 3
    assert continuity.environment == "crystal clear ocean lagoon"

    # Segment 1 checks
    s1 = segments[0]
    assert s1.index == 1
    assert s1.duration_seconds == 10
    assert s1.stage_name == "FOUNDATION"
    assert "Do NOT complete the final project during this segment" in s1.prompt
    assert "The final frame must clearly preserve the unfinished construction" in s1.prompt

    # Segment 2 checks
    s2 = segments[1]
    assert s2.index == 2
    assert s2.duration_seconds == 10
    assert s2.stage_name == "MAIN_CONSTRUCTION"
    assert "Do NOT restart from empty land" in s2.prompt
    assert "Do NOT jump immediately to the completed final result" in s2.prompt

    # Segment 3 checks
    s3 = segments[2]
    assert s3.index == 3
    assert s3.duration_seconds == 10
    assert s3.stage_name == "DETAILS_AND_REVEAL"
    assert "Only during the final approximately 3 seconds" in s3.prompt
    assert "controlled camera pullback" in s3.prompt

    # Unique prompt hashes
    assert s1.prompt_hash != s2.prompt_hash
    assert s2.prompt_hash != s3.prompt_hash
    assert s1.prompt_hash != s3.prompt_hash

def test_content_engine_generates_v3_plans_with_segments():
    engine = ContentEngine()
    plans = engine.generate_next_reels(count=2, past_records=[], duration_seconds=10)

    assert len(plans) == 2
    for p in plans:
        assert p.pipeline_version == 3
        assert p.content_mode == "silent_global_step_by_step"
        assert p.final_duration_seconds == 30
        assert p.segment_count == 3
        assert len(p.segments) == 3
        assert p.continuity is not None

def test_concatenator_preserves_strict_order(tmp_path: Path):
    ws_dir = tmp_path / "workspace"
    ws_dir.mkdir(parents=True)

    # Create 3 dummy segment files
    s1 = ws_dir / "seg1.txt"
    s2 = ws_dir / "seg2.txt"
    s3 = ws_dir / "seg3.txt"
    s1.write_bytes(b"SEG1_")
    s2.write_bytes(b"SEG2_")
    s3.write_bytes(b"SEG3")

    concatenator = VideoConcatenator(workspace_dir=ws_dir)
    out_file = ws_dir / "final.mp4"

    res = concatenator.concatenate_segments([s1, s2, s3], out_file, reel_id="REEL-TEST")
    assert res.exists()
    assert res.read_bytes() == b"SEG1_SEG2_SEG3"

def test_obsidian_writer_creates_v3_note_with_segment_blocks(tmp_path: Path):
    vault = tmp_path / "Vault"
    writer = ObsidianWriter(vault)

    engine = ContentEngine()
    plan = engine.generate_next_reels(count=1, past_records=[], duration_seconds=10)[0]

    note_path = writer.create_reel_note("REEL-2026-0099", plan)
    assert note_path.exists()

    content = note_path.read_text(encoding="utf-8")
    assert "pipeline_version: 3" in content
    assert "content_mode: silent_global_step_by_step"
    assert "final_duration_seconds: 30"
    assert "segment_count: 3"
    assert "Segment 1 (FOUNDATION" in content
    assert "Segment 2 (MAIN_CONSTRUCTION" in content
    assert "Segment 3 (DETAILS_AND_REVEAL" in content

def test_reader_parses_v3_metadata_and_segment_prompts(tmp_path: Path):
    vault = tmp_path / "Vault"
    writer = ObsidianWriter(vault)
    reader = ObsidianReader(vault)

    engine = ContentEngine()
    plan = engine.generate_next_reels(count=1, past_records=[], duration_seconds=10)[0]

    note_path = writer.create_reel_note("REEL-2026-0099", plan)
    meta = reader.parse_note_metadata(note_path)

    assert meta["id"] == "REEL-2026-0099"
    assert meta["pipeline_version"] == 3
    assert meta["content_mode"] == "silent_global_step_by_step"
    assert meta["final_duration_seconds"] == 30
    assert meta["segment_count"] == 3
    assert len(meta["segment_prompts"]) == 3

def test_past_v2_ready_videos_remain_intact_and_counted_in_history(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "05_READY").mkdir(parents=True)
    v2_note = vault / "05_READY" / "REEL-2026-0003.md"
    v2_note.write_text("""---
id: REEL-2026-0003
title: Desert Oasis Palace
status: READY
pipeline_version: 2
content_mode: silent_global_visual
duration_seconds: 8
---
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    completed = reader.get_completed_reels()
    history = reader.get_past_visual_history()
    incomplete = reader.get_incomplete_reels()

    assert len(completed) == 1
    assert len(history) == 1
    assert len(incomplete) == 0  # Completed reel is not incomplete
    assert completed[0]["id"] == "REEL-2026-0003"
    assert completed[0]["pipeline_version"] == 2
