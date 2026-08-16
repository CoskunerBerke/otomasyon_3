"""
Desktop output manager for organizing finalized MP4 videos and companion JSON metadata.
"""
import json
import re
import shutil
import datetime
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

from ..content.prompt_engine import ReelConceptPlan
from ..quality.validator import QCResult

def sanitize_filename(name: str) -> str:
    """Sanitize string for Windows filename safety."""
    # Replace spaces with underscores and remove invalid characters
    cleaned = re.sub(r'[<>:"/\\|?*]', '', name)
    cleaned = re.sub(r'\s+', '_', cleaned.strip())
    # Keep it reasonably short
    return cleaned[:40]

class DesktopOutputManager:
    """Manages creation of daily desktop folders, moving final videos, and writing metadata JSON."""

    def __init__(self, base_output_path: Path):
        self.base_output_path = Path(base_output_path).resolve()

    def get_today_folder(self, date: Optional[datetime.date] = None) -> Path:
        """Get or create daily output directory (YYYY-MM-DD)."""
        target_date = date or datetime.date.today()
        folder_name = target_date.strftime("%Y-%m-%d")
        daily_path = self.base_output_path / folder_name
        daily_path.mkdir(parents=True, exist_ok=True)
        return daily_path

    def save_final_reel(
        self,
        reel_id: str,
        plan: ReelConceptPlan,
        processed_video_path: Path,
        qc_result: QCResult,
        started_at: datetime.datetime,
        finished_at: datetime.datetime
    ) -> Tuple[Path, Path]:
        """
        Move video to daily desktop folder and write accompanying metadata JSON.
        Returns (final_mp4_path, final_json_path).
        """
        daily_dir = self.get_today_folder(finished_at.date())
        clean_title = sanitize_filename(plan.title)

        filename_base = f"{reel_id}_{clean_title}"
        final_mp4 = daily_dir / f"{filename_base}.mp4"
        final_json = daily_dir / f"{filename_base}.json"

        # Move / copy video to final location
        shutil.copy2(str(processed_video_path), str(final_mp4))

        # Compile metadata dictionary
        meta = qc_result.metadata
        metadata_dict = {
            "id": reel_id,
            "title": plan.title,
            "category": plan.category,
            "topic": plan.topic_description,
            "topic_key": plan.topic_key,
            "prompt": plan.prompt,
            "created_at": started_at.isoformat(),
            "generation_started_at": started_at.strftime("%Y-%m-%d %H:%M:%S"),
            "generation_finished_at": finished_at.strftime("%Y-%m-%d %H:%M:%S"),
            "duration": meta.duration_seconds if meta else 5.0,
            "resolution": f"{meta.width}x{meta.height}" if meta else "1080x1920",
            "file_size_bytes": final_mp4.stat().st_size if final_mp4.exists() else 0,
            "provider": "google_flow",
            "status": "READY",
            "qc_summary": {
                "technical_pass": qc_result.technical_pass,
                "ratio_pass": qc_result.ratio_pass,
                "audio_stripped": qc_result.audio_stripped,
                "visual_pass": qc_result.visual_pass
            },
            "diversity_score": plan.diversity_score
        }

        # Write JSON metadata atomically
        tmp_json = final_json.with_suffix(".tmp")
        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)
        tmp_json.replace(final_json)

        return final_mp4, final_json
