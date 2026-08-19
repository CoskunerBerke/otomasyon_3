"""
Tests for V3-Only Publishing Eligibility Hard Gate.
Ensures legacy 8s/9s, spoken legacy_information, and non-V3 videos are rejected,
while 30s silent visual 3-segment V3 videos are accepted.
"""
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch

from automation.publishing.eligibility import is_v3_publishing_eligible
from automation.publishing.models import Platform, PlatformPublicationStatus
from automation.publishing.publisher import PublishingOrchestrator
from automation.publishing.config import load_publishing_config

def test_v3_eligibility_accepts_v3_30s_silent(tmp_path: Path):
    video = tmp_path / "v3_30s.mp4"
    video.write_bytes(b"dummy video data 30s")

    meta = {
        "id": "REEL-2026-0010",
        "status": "READY",
        "pipeline_version": 3,
        "content_mode": "silent_global_step_by_step",
        "segments": [{"index": 1}, {"index": 2}, {"index": 3}],
        "video_file": str(video),
        "duration": 30.0
    }

    ok, reason = is_v3_publishing_eligible(meta, check_ffprobe=False)
    assert ok is True
    assert "Eligible" in reason

def test_v3_eligibility_rejects_legacy_pipeline_version_2(tmp_path: Path):
    video = tmp_path / "v2_8s.mp4"
    video.write_bytes(b"dummy video data")

    meta = {
        "id": "REEL-2026-0003",
        "status": "READY",
        "pipeline_version": 2,
        "content_mode": "silent_global_visual",
        "video_file": str(video),
        "duration": 8.0
    }

    ok, reason = is_v3_publishing_eligible(meta, check_ffprobe=False)
    assert ok is False
    assert "V3 required" in reason

def test_v3_eligibility_rejects_legacy_information_mode(tmp_path: Path):
    video = tmp_path / "v1_spoken.mp4"
    video.write_bytes(b"dummy video data")

    meta = {
        "id": "REEL-2026-0001",
        "status": "READY",
        "pipeline_version": 3,
        "content_mode": "legacy_information",
        "video_file": str(video),
        "duration": 30.0
    }

    ok, reason = is_v3_publishing_eligible(meta, check_ffprobe=False)
    assert ok is False
    # Rejection is now stated in terms of the mode registry: legacy_information is not a
    # registered live-eligible mode. Silent is no longer the only accepted mode -- see
    # tests/test_narrative_ambient_story.py for the audio-mode side of this gate.
    assert "not a registered live-eligible mode" in reason

def test_v3_eligibility_rejects_non_3_segments(tmp_path: Path):
    video = tmp_path / "v3_bad_seg.mp4"
    video.write_bytes(b"dummy video data")

    meta = {
        "id": "REEL-2026-0012",
        "status": "READY",
        "pipeline_version": 3,
        "content_mode": "silent_global_step_by_step",
        "segments": [{"index": 1}],
        "video_file": str(video),
        "duration": 30.0
    }

    ok, reason = is_v3_publishing_eligible(meta, check_ffprobe=False)
    assert ok is False
    assert "3 segments required" in reason

def test_v3_eligibility_ffprobe_duration_bounds(tmp_path: Path):
    video = tmp_path / "v3_ffprobe.mp4"
    video.write_bytes(b"dummy video data")

    meta = {
        "id": "REEL-2026-0010",
        "status": "READY",
        "pipeline_version": 3,
        "content_mode": "silent_global_step_by_step",
        "segments": [{"index": 1}, {"index": 2}, {"index": 3}],
        "video_file": str(video)
    }

    # Duration 9.0s (legacy) -> must fail
    mock_ffprobe_meta_9s = MagicMock()
    mock_ffprobe_meta_9s.duration_seconds = 9.2
    mock_ffprobe_meta_9s.is_vertical_9_16 = True
    mock_ffprobe_meta_9s.has_audio = False

    with patch("automation.quality.ffprobe.inspect_video", return_value=mock_ffprobe_meta_9s):
        ok, reason = is_v3_publishing_eligible(meta, check_ffprobe=True)
        assert ok is False
        assert "Actual video duration" in reason

    # Duration 30.0s -> must pass
    mock_ffprobe_meta_30s = MagicMock()
    mock_ffprobe_meta_30s.duration_seconds = 30.0
    mock_ffprobe_meta_30s.is_vertical_9_16 = True
    mock_ffprobe_meta_30s.has_audio = False

    with patch("automation.quality.ffprobe.inspect_video", return_value=mock_ffprobe_meta_30s):
        ok, reason = is_v3_publishing_eligible(meta, check_ffprobe=True)
        assert ok is True

def test_publisher_get_eligible_ready_reels_filters_legacy(tmp_path: Path):
    vault_dir = tmp_path / "vault"
    vault_dir.mkdir(parents=True)
    ready_dir = vault_dir / "05_READY"
    ready_dir.mkdir(parents=True)

    # Legacy 9s reel
    v_legacy = tmp_path / "legacy_0003.mp4"
    v_legacy.write_bytes(b"legacy")
    (ready_dir / "REEL-2026-0003.md").write_text(f"""---
id: REEL-2026-0003
status: READY
pipeline_version: 2
content_mode: silent_global_visual
video_file: "{v_legacy}"
duration: 9.0
---
""", encoding="utf-8")

    # V3 30s reel
    v_v3 = tmp_path / "v3_0010.mp4"
    v_v3.write_bytes(b"v3 mp4 dummy bytes" * 100)
    (ready_dir / "REEL-2026-0010.md").write_text(f"""---
id: REEL-2026-0010
status: READY
pipeline_version: 3
content_mode: silent_global_step_by_step
video_file: "{v_v3}"
duration: 30.0
segments:
  - index: 1
  - index: 2
  - index: 3
---
""", encoding="utf-8")

    cfg = load_publishing_config(base_dir=tmp_path)
    cfg.vault_path = vault_dir

    orch = PublishingOrchestrator(vault_path=vault_dir, config=cfg, mock=True)
    eligible = orch.get_eligible_ready_reels(count=1)

    assert len(eligible) == 1
    # Must pick REEL-2026-0010 and NEVER REEL-2026-0003
    assert eligible[0]["id"] == "REEL-2026-0010"
