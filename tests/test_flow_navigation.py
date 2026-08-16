"""
Unit tests for Flow navigation, Slate.js prompt selector resolution,
incomplete Reel resumption, and pre-submit safety guards.
"""
import pytest
from pathlib import Path
from automation.flow.selectors import (
    FlowPageState,
    FlowSelectors,
    FlowUIChangedError,
    RealGenerationDisabled
)
from automation.obsidian.reader import ObsidianReader
from automation.obsidian.reel_repository import ObsidianReelRepository

def test_flow_selectors_contain_new_project_and_slate_editor():
    # Verify New Project selectors contain Turkish and English variations
    assert any("Yeni proje" in s for s in FlowSelectors.NEW_PROJECT_BUTTON_SELECTORS)
    assert any("New project" in s for s in FlowSelectors.NEW_PROJECT_BUTTON_SELECTORS)

    # Verify Prompt input selectors contain data-slate-editor and role=textbox
    assert any("data-slate-editor" in s for s in FlowSelectors.PROMPT_INPUT_SELECTORS)
    assert any("role='textbox'" in s or 'role="textbox"' in s for s in FlowSelectors.PROMPT_INPUT_SELECTORS)

def test_incomplete_reel_resumption(tmp_path: Path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    scripts_dir = vault / "03_SCRIPTS"
    scripts_dir.mkdir()

    # Create incomplete REEL-2026-0003 note
    note_file = scripts_dir / "REEL-2026-0003.md"
    note_file.write_text(
        "---\n"
        "id: REEL-2026-0003\n"
        "title: Desert Oasis Palace\n"
        "topic: Desert transforming into oasis\n"
        "topic_key: desert-oasis\n"
        "status: PROMPT_READY\n"
        "pipeline_version: 2\n"
        "content_mode: silent_global_visual\n"
        "video_file: ''\n"
        "---\n\n"
        "# Prompt\n\n```text\nCreate a mesmerizing vertical 9:16 video of a desert oasis.\n```\n",
        encoding="utf-8"
    )

    reader = ObsidianReader(vault)
    incomplete = reader.get_incomplete_reels()

    assert len(incomplete) == 1
    assert incomplete[0]["id"] == "REEL-2026-0003"
    assert incomplete[0]["title"] == "Desert Oasis Palace"
    assert "desert oasis" in incomplete[0]["prompt"].lower()

def test_completed_reels_exclude_incomplete_notes(tmp_path: Path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    scripts_dir = vault / "03_SCRIPTS"
    scripts_dir.mkdir()
    ready_dir = vault / "05_READY"
    ready_dir.mkdir()

    (scripts_dir / "REEL-2026-0003.md").write_text("---\nid: REEL-2026-0003\nstatus: PROMPT_READY\n---", encoding="utf-8")
    (ready_dir / "REEL-2026-0001.md").write_text("---\nid: REEL-2026-0001\nstatus: READY\n---", encoding="utf-8")

    reader = ObsidianReader(vault)
    completed = reader.get_completed_reels()

    assert len(completed) == 1
    assert completed[0]["id"] == "REEL-2026-0001"
