"""
Video validation utility for Instagram Reels publishing.
Inspects local video files using ffprobe to ensure compliance with Meta Reels guidelines.
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ReelsAIFactory.InstagramValidator")
from automation.publishing.instagram_models import InstagramMediaValidationResult


def validate_instagram_reel_media(video_path: Path) -> InstagramMediaValidationResult:
    """
    Validates a local MP4/MOV video file against Meta Instagram Reels specifications.
    
    Specs:
    - Container: MP4 or MOV
    - Duration: 3 to 90 seconds (Target V3: ~30s)
    - Aspect Ratio: 9:16 (recommended: 1080x1920, min: 540x960)
    - Codec: H.264 / AVC or HEVC
    - Audio: AAC or silent
    - Frame rate: 23 to 60 fps
    - File size: < 100MB recommended (Meta max: 1GB)
    """
    res = InstagramMediaValidationResult()

    if not isinstance(video_path, Path):
        video_path = Path(video_path)

    if not video_path.exists():
        res.is_valid = False
        res.errors.append(f"FILE_NOT_FOUND: '{video_path}' does not exist.")
        return res

    res.file_size_bytes = video_path.stat().st_size
    ext = video_path.suffix.lower()
    if ext not in (".mp4", ".mov"):
        res.errors.append(f"UNSUPPORTED_EXTENSION: '{ext}' is not supported (expected .mp4 or .mov).")

    if res.file_size_bytes > 1024 * 1024 * 1024:  # 1 GB
        res.errors.append(f"FILE_TOO_LARGE: File size {res.file_size_bytes} bytes exceeds Meta 1GB limit.")
    elif res.file_size_bytes > 100 * 1024 * 1024:  # 100 MB warning
        res.warnings.append(f"FILE_SIZE_WARNING: File size is {res.file_size_bytes / (1024*1024):.1f}MB (recommended < 100MB).")

    # Run ffprobe to extract stream metadata
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path.resolve())
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if proc.returncode != 0:
            res.errors.append(f"FFPROBE_FAILED: ffprobe returned error code {proc.returncode}.")
            res.is_valid = False
            return res

        data = json.loads(proc.stdout)
        fmt = data.get("format", {})
        streams = data.get("streams", [])

        # Duration
        dur_str = fmt.get("duration")
        if dur_str:
            try:
                res.duration_seconds = float(dur_str)
            except ValueError:
                pass

        # Streams inspection
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        if not video_stream:
            res.errors.append("NO_VIDEO_STREAM: Video stream missing from file.")
        else:
            res.width = int(video_stream.get("width", 0))
            res.height = int(video_stream.get("height", 0))
            res.video_codec = str(video_stream.get("codec_name", "")).lower()

            # FPS parsing (e.g. "30/1" -> 30.0)
            r_frame_rate = video_stream.get("r_frame_rate", "0/1")
            try:
                num, den = map(int, r_frame_rate.split("/"))
                res.fps = num / den if den != 0 else 0.0
            except Exception:
                res.fps = 0.0

            if res.duration_seconds == 0.0 and video_stream.get("duration"):
                try:
                    res.duration_seconds = float(video_stream.get("duration"))
                except ValueError:
                    pass

        if audio_stream:
            res.audio_codec = str(audio_stream.get("codec_name", "")).lower()
            # Meta accepts AAC audio for Reels. Silent Reels are fine (no stream at all),
            # but a non-AAC track fails at upload, so catch it here instead of there.
            if res.audio_codec != "aac":
                res.errors.append(
                    f"UNSUPPORTED_AUDIO_CODEC: '{res.audio_codec}' is not AAC, which Meta requires for Reels audio."
                )

        # Validate duration
        if res.duration_seconds < 3.0:
            res.errors.append(f"DURATION_TOO_SHORT: {res.duration_seconds:.1f}s is less than Meta minimum 3.0s.")
        elif res.duration_seconds > 90.0:
            res.errors.append(f"DURATION_TOO_LONG: {res.duration_seconds:.1f}s exceeds Meta maximum 90.0s.")

        # Validate aspect ratio & resolution
        if res.width > 0 and res.height > 0:
            ratio = res.width / res.height
            res.aspect_ratio = f"{res.width}:{res.height}"
            # 9:16 is 0.5625. Allow tolerance between 0.50 and 0.60
            if not (0.50 <= ratio <= 0.60):
                res.errors.append(
                    f"INVALID_ASPECT_RATIO: {res.width}x{res.height} (ratio {ratio:.3f}) is not vertical 9:16."
                )
            if res.width < 540 or res.height < 960:
                res.warnings.append(
                    f"LOW_RESOLUTION_WARNING: {res.width}x{res.height} is below recommended 1080x1920."
                )

        # Validate codec
        if res.video_codec and res.video_codec not in ("h264", "avc", "avc1", "hevc", "h265"):
            res.errors.append(f"UNSUPPORTED_VIDEO_CODEC: '{res.video_codec}' is not recommended (expected h264/hevc).")

        # Validate FPS
        if res.fps > 0 and (res.fps < 23.0 or res.fps > 60.5):
            res.warnings.append(f"FPS_WARNING: Frame rate {res.fps:.1f} fps outside typical 23-60 fps range.")

    except FileNotFoundError:
        # ffprobe binary not available on PATH
        res.warnings.append("FFPROBE_NOT_AVAILABLE: Detailed stream inspection skipped.")
    except Exception as e:
        res.warnings.append(f"INSPECTION_WARNING: ffprobe inspection exception: {e}")

    res.is_valid = (len(res.errors) == 0)
    logger.info(
        f"[INSTAGRAM VALIDATOR] Validation result for '{video_path.name}': "
        f"is_valid={res.is_valid}, duration={res.duration_seconds:.1f}s, "
        f"res={res.width}x{res.height}, codec={res.video_codec}, errors={len(res.errors)}"
    )
    return res
