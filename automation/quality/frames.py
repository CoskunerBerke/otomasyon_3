"""
Visual QC frame extractor and analyzer using FFmpeg and Pillow / NumPy.
"""
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import numpy as np
from PIL import Image

@dataclass
class VisualCheckResult:
    is_valid: bool
    is_black_screen: bool
    is_low_variance: bool
    is_frozen: bool
    frame_count_extracted: int
    message: str

def extract_and_analyze_frames(video_path: Path, duration: float) -> VisualCheckResult:
    """
    Extract 5 sample frames (0%, 25%, 50%, 75%, 100%) and perform basic visual sanity checks.
    """
    video_path = Path(video_path).resolve()
    if duration <= 0.5:
        duration = 5.0

    timestamps = [
        0.0,
        duration * 0.25,
        duration * 0.50,
        duration * 0.75,
        max(0.1, duration - 0.2)
    ]

    with tempfile.TemporaryDirectory(prefix="reel_qc_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        frame_files: List[Path] = []

        for idx, ts in enumerate(timestamps):
            out_frame = tmp_path / f"frame_{idx:02d}.png"
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", f"{ts:.2f}",
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",
                str(out_frame)
            ]
            try:
                subprocess.run(cmd, capture_output=True, check=True)
                if out_frame.exists() and out_frame.stat().st_size > 0:
                    frame_files.append(out_frame)
            except Exception:
                pass

        if len(frame_files) < 2:
            return VisualCheckResult(
                is_valid=False,
                is_black_screen=False,
                is_low_variance=False,
                is_frozen=False,
                frame_count_extracted=len(frame_files),
                message="Failed to extract sufficient frames for visual analysis."
            )

        arrays: List[np.ndarray] = []
        is_black_screen = False
        is_low_variance = False

        for fpath in frame_files:
            try:
                img = Image.open(fpath).convert("L")  # Grayscale
                arr = np.array(img, dtype=np.float32)
                arrays.append(arr)

                mean_val = float(np.mean(arr))
                std_val = float(np.std(arr))

                # If average brightness is less than 5/255 -> black screen
                if mean_val < 5.0:
                    is_black_screen = True
                # If standard deviation is less than 4.0 -> completely solid/empty
                if std_val < 4.0:
                    is_low_variance = True
            except Exception:
                pass

        # Check for frozen video (difference between frame 0 and last frame is near zero)
        is_frozen = False
        if len(arrays) >= 2:
            first_arr = arrays[0]
            last_arr = arrays[-1]
            diff = np.abs(first_arr - last_arr)
            mean_diff = float(np.mean(diff))
            if mean_diff < 3.0:
                is_frozen = True

        if is_black_screen:
            return VisualCheckResult(
                is_valid=False,
                is_black_screen=True,
                is_low_variance=is_low_variance,
                is_frozen=is_frozen,
                frame_count_extracted=len(frame_files),
                message="Video contains completely black frames."
            )

        if is_low_variance:
            return VisualCheckResult(
                is_valid=False,
                is_black_screen=False,
                is_low_variance=True,
                is_frozen=is_frozen,
                frame_count_extracted=len(frame_files),
                message="Video frames have unnaturally low variance (empty/corrupt frames)."
            )

        if is_frozen:
            return VisualCheckResult(
                is_valid=False,
                is_black_screen=False,
                is_low_variance=False,
                is_frozen=True,
                frame_count_extracted=len(frame_files),
                message="Video appears to be a static frozen image with no kinetic transformation."
            )

        return VisualCheckResult(
            is_valid=True,
            is_black_screen=False,
            is_low_variance=False,
            is_frozen=False,
            frame_count_extracted=len(frame_files),
            message="Visual QC passed (clear contrast and continuous motion detected)."
        )
