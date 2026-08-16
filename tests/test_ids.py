"""
Unit tests for sequential Reel ID generation and collision avoidance.
"""
import pytest
from pathlib import Path
from automation.obsidian.reader import ObsidianReader

def test_id_increment_from_empty_vault(tmp_path: Path):
    reader = ObsidianReader(tmp_path)
    next_id = reader.get_next_reel_id(year=2026)
    assert next_id == "REEL-2026-0001"

def test_id_increment_with_existing_reels(tmp_path: Path):
    scripts_dir = tmp_path / "03_SCRIPTS"
    scripts_dir.mkdir(parents=True)

    # Create dummy existing notes
    (scripts_dir / "REEL-2026-0001.md").write_text("---\nid: REEL-2026-0001\n---", encoding="utf-8")
    (scripts_dir / "REEL-2026-0002.md").write_text("---\nid: REEL-2026-0002\n---", encoding="utf-8")

    ready_dir = tmp_path / "05_READY"
    ready_dir.mkdir(parents=True)
    (ready_dir / "REEL-2026-0005.md").write_text("## id: REEL-2026-0005\n", encoding="utf-8")

    reader = ObsidianReader(tmp_path)
    next_id = reader.get_next_reel_id(year=2026)
    assert next_id == "REEL-2026-0006"

def test_id_parsing_relaxed_headings(tmp_path: Path):
    scripts_dir = tmp_path / "03_SCRIPTS"
    scripts_dir.mkdir(parents=True)
    note_file = scripts_dir / "custom_name.md"
    note_file.write_text(
        "# REEL-2026-0042 — Test\n\n## id: REEL-2026-0042\ntitle: Test Title\ntopic_key: test-key\n",
        encoding="utf-8"
    )

    reader = ObsidianReader(tmp_path)
    meta = reader.parse_note_metadata(note_file)
    assert meta["id"] == "REEL-2026-0042"
    assert meta["title"] == "Test Title"
    assert meta["topic_key"] == "test-key"
