"""
FFprobe metadata inspector for video streams and format verification.
"""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any

@dataclass
class VideoMetadata:
    width: int
    height: int
    duration_seconds: float
    video_codec: str
    has_video: bool
    has_audio: bool
    audio_codec: Optional[str]
    file_size_bytes: int
    aspect_ratio: float
    is_vertical_9_16: bool

def inspect_video(video_path: Path) -> VideoMetadata:
    """Run ffprobe on given video and extract metadata."""
    video_path = Path(video_path).resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(video_path)
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"FFprobe execution failed: {e.stderr}")
    except json.JSONDecodeError:
        raise RuntimeError("Failed to parse FFprobe JSON output.")

    streams = data.get("streams", [])
    format_info = data.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not video_stream:
        return VideoMetadata(
            width=0,
            height=0,
            duration_seconds=0.0,
            video_codec="",
            has_video=False,
            has_audio=bool(audio_stream),
            audio_codec=audio_stream.get("codec_name") if audio_stream else None,
            file_size_bytes=int(format_info.get("size", 0)),
            aspect_ratio=0.0,
            is_vertical_9_16=False
        )

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))

    duration_str = video_stream.get("duration") or format_info.get("duration", "0")
    duration = float(duration_str) if duration_str else 0.0

    ratio = (width / height) if height > 0 else 0.0
    # 9/16 = 0.5625. Allow tolerance between 0.50 and 0.60
    is_9_16 = 0.50 <= ratio <= 0.60

    return VideoMetadata(
        width=width,
        height=height,
        duration_seconds=duration,
        video_codec=video_stream.get("codec_name", ""),
        has_video=True,
        has_audio=bool(audio_stream),
        audio_codec=audio_stream.get("codec_name") if audio_stream else None,
        file_size_bytes=int(format_info.get("size", 0)),
        aspect_ratio=round(ratio, 4),
        is_vertical_9_16=is_9_16
    )
