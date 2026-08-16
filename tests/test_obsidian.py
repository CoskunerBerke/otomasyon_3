"""
Unit tests for Obsidian note writing, atomic updates, and status transitions.
"""
import pytest
from pathlib import Path
from automation.content.concepts import CATEGORIES
from automation.content.prompt_engine import PromptEngine
from automation.obsidian.writer import ObsidianWriter
from automation.obsidian.reader import ObsidianReader
from automation.obsidian.reel_repository import ObsidianReelRepository

@pytest.fixture
def test_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "Reels_AI_Studio"
    vault.mkdir(parents=True)
    (vault / "03_SCRIPTS").mkdir()
    (vault / "04_PRODUCTION").mkdir()
    (vault / "05_READY").mkdir()
    (vault / "07_REJECTED").mkdir()
    return vault

def test_create_and_read_reel_note(test_vault: Path):
    repo = ObsidianReelRepository(test_vault)
    plan = PromptEngine.build_concept_plan(
        concept=CATEGORIES[0],
        env=CATEGORIES[0].environments[0],
        arch=CATEGORIES[0].architectures[0],
        transformation=CATEGORIES[0].transformations[0],
        camera=CATEGORIES[0].camera_styles[0],
        lighting=CATEGORIES[0].lighting_schemes[0],
        materials=CATEGORIES[0].materials[0],
        reveal=CATEGORIES[0].reveals[0],
        diversity_score=0.95
    )

    reel_id = "REEL-2026-0003"
    note_path = repo.create_new_reel(reel_id, plan)
    assert note_path.exists()

    # Read back metadata
    reader = ObsidianReader(test_vault)
    meta = reader.parse_note_metadata(note_path)
    assert meta["id"] == "REEL-2026-0003"
    assert meta["status"] == "PROMPT_READY"
    assert meta["topic_key"] == plan.topic_key

def test_lifecycle_transitions(test_vault: Path):
    repo = ObsidianReelRepository(test_vault)
    plan = PromptEngine.build_concept_plan(
        concept=CATEGORIES[1],
        env=CATEGORIES[1].environments[0],
        arch=CATEGORIES[1].architectures[0],
        transformation=CATEGORIES[1].transformations[0],
        camera=CATEGORIES[1].camera_styles[0],
        lighting=CATEGORIES[1].lighting_schemes[0],
        materials=CATEGORIES[1].materials[0],
        reveal=CATEGORIES[1].reveals[0],
        diversity_score=0.91
    )

    reel_id = "REEL-2026-0004"
    repo.create_new_reel(reel_id, plan)

    # Move to production (GENERATING)
    repo.mark_generating(reel_id)
    assert (test_vault / "04_PRODUCTION" / f"{reel_id}.md").exists()
    assert not (test_vault / "03_SCRIPTS" / f"{reel_id}.md").exists()

    # Move to READY
    dummy_video = test_vault / "dummy.mp4"
    dummy_video.write_bytes(b"dummy")
    dummy_json = test_vault / "dummy.json"
    dummy_json.write_text("{}", encoding="utf-8")

    ready_path = repo.mark_ready(
        reel_id=reel_id,
        video_path=dummy_video,
        metadata_path=dummy_json,
        qc_details={"technical_pass": True, "ratio_pass": True, "audio_stripped": True, "visual_pass": True}
    )

    assert ready_path.exists()
    assert (test_vault / "05_READY" / f"{reel_id}.md").exists()
    assert not (test_vault / "04_PRODUCTION" / f"{reel_id}.md").exists()

    content = ready_path.read_text(encoding="utf-8")
    assert "status: READY" in content
    assert "Teknik QC (FFprobe):** PASS" in content
