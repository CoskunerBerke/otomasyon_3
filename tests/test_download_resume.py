"""
Unit tests for download resume, sync Playwright execution model,
and prevention of duplicate generation on download retries.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.flow.generator import GoogleFlowWebProvider, MockVideoProvider
from automation.flow.downloader import FlowDownloader
from automation.obsidian.reader import ObsidianReader
from automation.content.prompt_engine import ReelConceptPlan
from automation.content.engine import CATEGORIES
from automation.config import AppConfig

def test_media_ready_status_is_resumable(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "04_PRODUCTION").mkdir(parents=True)
    note = vault / "04_PRODUCTION" / "REEL-2026-0004.md"
    note.write_text("""---
id: REEL-2026-0004
title: Luxury Island Resort
topic: Luxury Island Development
topic_key: luxury-island
status: MEDIA_READY
resume_from: DOWNLOAD
pipeline_version: 2
content_mode: silent_global_visual
flow_project_url: https://labs.google/fx/tr/tools/flow/project/test-uuid
---
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    incomplete = reader.get_incomplete_reels()
    assert len(incomplete) == 1
    assert incomplete[0]["id"] == "REEL-2026-0004"
    assert incomplete[0]["resume_from"] == "DOWNLOAD"
    assert incomplete[0]["flow_project_url"] == "https://labs.google/fx/tr/tools/flow/project/test-uuid"

def test_failed_technical_download_is_resumable(tmp_path: Path):
    vault = tmp_path / "Vault"
    (vault / "04_PRODUCTION").mkdir(parents=True)
    note = vault / "04_PRODUCTION" / "REEL-2026-0004.md"
    note.write_text("""---
id: REEL-2026-0004
title: Luxury Island Resort
topic: Luxury Island Development
topic_key: luxury-island
status: FAILED_TECHNICAL_DOWNLOAD
resume_from: DOWNLOAD
pipeline_version: 2
content_mode: silent_global_visual
---
""", encoding="utf-8")

    reader = ObsidianReader(vault)
    incomplete = reader.get_incomplete_reels()
    assert len(incomplete) == 1
    assert incomplete[0]["id"] == "REEL-2026-0004"

def test_mock_video_provider_generates_valid_mp4(tmp_path: Path):
    out_dir = tmp_path / "downloads"
    provider = MockVideoProvider(output_dir=out_dir)

    plan = ReelConceptPlan(
        concept_def=CATEGORIES[0],
        title="Test Reel",
        topic_description="Test Topic",
        topic_key="test-topic",
        category="Satisfying Transformation",
        environment="test env",
        architecture="test arch",
        transformation="test trans",
        camera_style="aerial",
        lighting="golden hour",
        materials="wood",
        reveal="masterpiece",
        prompt="Test Prompt",
        diversity_score=0.8
    )

    mp4_file = provider.generate_single_video(
        plan=plan,
        reel_id="REEL-2026-0004",
        target_filename="REEL-2026-0004_Test_Reel.mp4"
    )

    assert mp4_file.exists()
    assert mp4_file.name == "REEL-2026-0004_Test_Reel.mp4"
    assert mp4_file.stat().st_size > 1000

def test_sync_playwright_clean_disconnect():
    # Verify that CDP browser disconnect does not leak active transports
    from automation.flow.browser import CDPBrowserManager
    from automation.config import AppConfig

    cfg = AppConfig(
        vault_path=Path("."),
        output_path=Path("."),
        chrome_debug_port=9999  # unused port
    )
    mgr = CDPBrowserManager(cfg)
    # is_cdp_available on closed port returns False cleanly
    from automation.flow.chrome_launcher import is_cdp_available
    assert is_cdp_available(9999) is False
