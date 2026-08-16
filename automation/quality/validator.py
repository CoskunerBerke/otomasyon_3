"""
Comprehensive Quality Control Validator and Audio Stripper.
"""
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

from .ffprobe import inspect_video, VideoMetadata
from .frames import extract_and_analyze_frames, VisualCheckResult

@dataclass
class QCResult:
    is_passed: bool
    technical_pass: bool
    ratio_pass: bool
    audio_stripped: bool
    visual_pass: bool
    processed_video_path: Optional[Path]
    error_message: str
    metadata: Optional[VideoMetadata] = None

class VideoValidator:
    """Validates video format, aspect ratio, motion, and strips audio."""

    def __init__(self, reject_wrong_ratio: bool = True, audio_enabled: bool = False):
        self.reject_wrong_ratio = reject_wrong_ratio
        self.audio_enabled = audio_enabled

    def process_and_validate(self, input_video: Path, output_dir: Optional[Path] = None) -> QCResult:
        """
        Execute full technical and visual validation pipeline.
        Strips audio tracks and applies +faststart.
        """
        input_video = Path(input_video).resolve()
        if not input_video.exists() or input_video.stat().st_size == 0:
            return QCResult(
                is_passed=False,
                technical_pass=False,
                ratio_pass=False,
                audio_stripped=False,
                visual_pass=False,
                processed_video_path=None,
                error_message=f"Video file does not exist or is 0 bytes: {input_video}"
            )

        # 1. FFprobe Technical Inspection
        try:
            meta = inspect_video(input_video)
        except Exception as e:
            return QCResult(
                is_passed=False,
                technical_pass=False,
                ratio_pass=False,
                audio_stripped=False,
                visual_pass=False,
                processed_video_path=None,
                error_message=f"FFprobe inspection failed: {e}"
            )

        if not meta.has_video or meta.duration_seconds <= 0.5:
            return QCResult(
                is_passed=False,
                technical_pass=False,
                ratio_pass=False,
                audio_stripped=False,
                visual_pass=False,
                processed_video_path=None,
                error_message="Video stream is missing or duration is too short (<0.5s)",
                metadata=meta
            )

        # 2. Aspect Ratio Check (9:16)
        if self.reject_wrong_ratio and not meta.is_vertical_9_16:
            return QCResult(
                is_passed=False,
                technical_pass=True,
                ratio_pass=False,
                audio_stripped=False,
                visual_pass=False,
                processed_video_path=None,
                error_message=f"Aspect ratio {meta.aspect_ratio} ({meta.width}x{meta.height}) is not 9:16 vertical.",
                metadata=meta
            )

        # 3. Visual QC Frame Analysis
        visual_res = extract_and_analyze_frames(input_video, meta.duration_seconds)
        if not visual_res.is_valid:
            return QCResult(
                is_passed=False,
                technical_pass=True,
                ratio_pass=True,
                audio_stripped=False,
                visual_pass=False,
                processed_video_path=None,
                error_message=f"Visual QC failed: {visual_res.message}",
                metadata=meta
            )

        # 4. Post-processing: Audio Stripping & Faststart
        target_dir = output_dir or input_video.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        clean_video_path = target_dir / f"clean_{input_video.name}"

        # FFmpeg command: copy video codec, strip audio (-an), add faststart for instant streaming
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_video),
            "-c:v", "copy",
            "-an",
            "-movflags", "+faststart",
            str(clean_video_path)
        ]

        try:
            subprocess.run(cmd, capture_output=True, check=True)
            audio_stripped = meta.has_audio
        except Exception as e:
            # Fallback if faststart/copy failed: keep original
            clean_video_path = input_video
            audio_stripped = False

        return QCResult(
            is_passed=True,
            technical_pass=True,
            ratio_pass=True,
            audio_stripped=audio_stripped,
            visual_pass=True,
            processed_video_path=clean_video_path,
            error_message="",
            metadata=meta
        )
