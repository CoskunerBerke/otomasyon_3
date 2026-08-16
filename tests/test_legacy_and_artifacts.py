"""
Unit tests for legacy Reel exclusions, baseline artifact fingerprinting,
one-project-per-reel policy, and stale artifact false-positive protection.
"""
import pytest
from pathlib import Path
from automation.obsidian.reader import ObsidianReader
from automation.obsidian.writer import ObsidianWriter
from automation.flow.ui_observer import FlowUISnapshot
from automation.flow.state_machine import (
    FlowDecisionEngine,
    FlowDecisionAction,
    GenerationLifecycleState,
    GenerationSession
)
from automation.content.engine import ContentEngine

def test_legacy_reel_0001_not_resumable(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "07_REJECTED").mkdir(parents=True)
    note = vault / "07_REJECTED" / "REEL-2026-0001.md"
    note.write_text("""---
id: REEL-2026-0001
title: GPS Video
category: Teknoloji
status: REJECTED
legacy: true
content_mode: legacy_information
resume_allowed: false
---
# Content
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    incomplete = reader.get_incomplete_reels()
    assert len(incomplete) == 0

def test_legacy_silent_visual_is_not_resumable(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "03_SCRIPTS").mkdir(parents=True)
    note = vault / "03_SCRIPTS" / "REEL-2026-0002.md"
    note.write_text("""---
id: REEL-2026-0002
title: Futuristic City Build
category: Satisfying Transformation
topic: Empty land transforming into a futuristic miniature city
topic_key: futuristic-city-build
status: SCRIPT
legacy: true
content_mode: silent_global_visual
resume_allowed: false
pipeline_version: 1
---
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    incomplete = reader.get_incomplete_reels()
    assert len(incomplete) == 0

def test_legacy_silent_visual_still_contributes_to_diversity_history(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "03_SCRIPTS").mkdir(parents=True)
    note = vault / "03_SCRIPTS" / "REEL-2026-0002.md"
    note.write_text("""---
id: REEL-2026-0002
title: Futuristic City Build
category: Satisfying Transformation
topic: Empty land transforming into a futuristic miniature city
topic_key: futuristic-city-build
status: SCRIPT
legacy: true
content_mode: silent_global_visual
resume_allowed: false
pipeline_version: 1
---
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    history = reader.get_past_visual_history()
    assert len(history) == 1
    assert history[0]["id"] == "REEL-2026-0002"
    assert history[0]["topic_key"] == "futuristic-city-build"

    # Verify diversity engine uses this history
    content_engine = ContentEngine()
    new_plans = content_engine.generate_next_reels(count=2, past_records=history)
    assert len(new_plans) == 2
    # The generated plans should have valid diversity score
    for p in new_plans:
        assert p.diversity_score > 0.0

def test_legacy_information_does_not_resume(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "03_SCRIPTS").mkdir(parents=True)
    note = vault / "03_SCRIPTS" / "REEL-2026-0001.md"
    note.write_text("""---
id: REEL-2026-0001
title: Old Info
status: SCRIPT
content_mode: legacy_information
---
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    incomplete = reader.get_incomplete_reels()
    assert len(incomplete) == 0

def test_rejected_excluded_by_default_unless_retry_allowed(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "07_REJECTED").mkdir(parents=True)

    # Note 1: Standard rejected
    n1 = vault / "07_REJECTED" / "REEL-2026-0010.md"
    n1.write_text("""---
id: REEL-2026-0010
title: Bad Reel
status: REJECTED
pipeline_version: 2
content_mode: silent_global_visual
---
""", encoding="utf-8")

    # Note 2: Explicit retry allowed
    n2 = vault / "07_REJECTED" / "REEL-2026-0011.md"
    n2.write_text("""---
id: REEL-2026-0011
title: Retryable Reel
status: PROMPT_READY
pipeline_version: 2
content_mode: silent_global_visual
retry_allowed: true
---
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    incomplete = reader.get_incomplete_reels()
    assert len(incomplete) == 1
    assert incomplete[0]["id"] == "REEL-2026-0011"

def test_ready_and_published_excluded_from_incomplete(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "05_READY").mkdir(parents=True)
    (vault / "06_PUBLISHED").mkdir(parents=True)

    n1 = vault / "05_READY" / "REEL-2026-0003.md"
    n1.write_text("""---
id: REEL-2026-0003
status: READY
pipeline_version: 2
content_mode: silent_global_visual
video_file: "some_path.mp4"
---
""", encoding="utf-8")

    n2 = vault / "06_PUBLISHED" / "REEL-2026-0002.md"
    n2.write_text("""---
id: REEL-2026-0002
status: PUBLISHED
pipeline_version: 2
content_mode: silent_global_visual
video_file: "some_path.mp4"
---
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    incomplete = reader.get_incomplete_reels()
    assert len(incomplete) == 0

def test_stale_baseline_artifact_ignored_before_submit():
    engine = FlowDecisionEngine()
    session = GenerationSession(
        reel_id="REEL-2026-0004",
        prompt_hash="1234abcd",
        baseline_artifact_fingerprints={"video:/fx/api/media?name=old_oasis"},
        submit_attempted=False
    )

    # Snapshot shows 1 video artifact, but it is NOT new (same old oasis artifact)
    snapshot = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow/project/xyz",
        video_artifact_count=1,
        new_video_artifact_detected=False,  # Baseline was present
        download_button_visible=True
    )

    action = engine.decide_next_action(snapshot, session=session)
    # Must NOT download! Must start media generation instead
    assert action == FlowDecisionAction.START_MEDIA_GENERATION
    assert engine.state != GenerationLifecycleState.MEDIA_READY

def test_new_artifact_after_submit_triggers_download():
    engine = FlowDecisionEngine()
    session = GenerationSession(
        reel_id="REEL-2026-0004",
        prompt_hash="1234abcd",
        baseline_artifact_fingerprints={"video:/fx/api/media?name=old_oasis"},
        submit_attempted=True
    )

    # Snapshot shows newly detected artifact
    snapshot = FlowUISnapshot(
        page_url="https://labs.google/fx/tools/flow/project/xyz",
        video_artifact_count=2,
        new_video_artifact_detected=True,
        new_artifact_fingerprint="video:/fx/api/media?name=new_island",
        download_button_visible=True
    )

    action = engine.decide_next_action(snapshot, session=session)
    assert action == FlowDecisionAction.DOWNLOAD_MEDIA
    assert engine.state == GenerationLifecycleState.MEDIA_READY
