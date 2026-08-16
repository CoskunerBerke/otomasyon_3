"""
Unit tests for QC validator and FFprobe inspection parsing.
"""
import pytest
import subprocess
from pathlib import Path
from automation.quality.ffprobe import inspect_video, VideoMetadata
from automation.quality.validator import VideoValidator

def create_synthetic_mp4(path: Path, width: int = 540, height: int = 960, duration: int = 2) -> None:
    """Helper to generate a real valid MP4 using ffmpeg for testing."""
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i", f"testsrc=size={width}x{height}:rate=25",
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(path)
    ]
    subprocess.run(cmd, capture_output=True, check=True)

def test_ffprobe_validates_9_16(tmp_path: Path):
    video_path = tmp_path / "valid_vertical.mp4"
    create_synthetic_mp4(video_path, width=540, height=960, duration=2)

    meta = inspect_video(video_path)
    assert meta.has_video is True
    assert meta.width == 540
    assert meta.height == 960
    assert meta.is_vertical_9_16 is True
    assert meta.duration_seconds >= 1.9

def test_validator_passes_valid_video(tmp_path: Path):
    video_path = tmp_path / "test_reel.mp4"
    create_synthetic_mp4(video_path, width=540, height=960, duration=2)

    validator = VideoValidator(reject_wrong_ratio=True, audio_enabled=False)
    qc_res = validator.process_and_validate(video_path, output_dir=tmp_path / "qc_out")

    assert qc_res.is_passed is True
    assert qc_res.technical_pass is True
    assert qc_res.ratio_pass is True
    assert qc_res.visual_pass is True
    assert qc_res.processed_video_path is not None
    assert qc_res.processed_video_path.exists()

def test_validator_rejects_horizontal_video(tmp_path: Path):
    video_path = tmp_path / "horizontal.mp4"
    create_synthetic_mp4(video_path, width=960, height=540, duration=2)

    validator = VideoValidator(reject_wrong_ratio=True, audio_enabled=False)
    qc_res = validator.process_and_validate(video_path, output_dir=tmp_path / "qc_out")

    assert qc_res.is_passed is False
    assert qc_res.ratio_pass is False
    assert "not 9:16 vertical" in qc_res.error_message
