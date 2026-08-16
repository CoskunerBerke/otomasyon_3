"""
Obsidian Reel repository coordinating reads, writes, and status updates.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional

from .reader import ObsidianReader
from .writer import ObsidianWriter
from ..content.prompt_engine import ReelConceptPlan

class ObsidianReelRepository:
    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path).resolve()
        self.reader = ObsidianReader(self.vault_path)
        self.writer = ObsidianWriter(self.vault_path)

    def get_past_reels(self) -> List[Dict[str, Any]]:
        return self.reader.get_all_reels()

    def get_completed_reels(self) -> List[Dict[str, Any]]:
        return self.reader.get_completed_reels()

    def get_past_visual_history(self) -> List[Dict[str, Any]]:
        return self.reader.get_past_visual_history()

    def get_incomplete_reels(self) -> List[Dict[str, Any]]:
        return self.reader.get_incomplete_reels()

    def get_next_id(self) -> str:
        return self.reader.get_next_reel_id()

    def create_new_reel(self, reel_id: str, plan: ReelConceptPlan, run_id: Optional[str] = None) -> Path:
        return self.writer.create_reel_note(reel_id, plan, run_id=run_id)

    def mark_submitting(self, reel_id: str) -> None:
        self.writer.update_status(reel_id, "FLOW_SUBMITTING")

    def mark_generating(self, reel_id: str) -> None:
        self.writer.move_to_production(reel_id)

    def mark_downloading(self, reel_id: str) -> None:
        self.writer.update_status(reel_id, "DOWNLOADING")

    def mark_validating(self, reel_id: str) -> None:
        self.writer.update_status(reel_id, "VALIDATING")

    def mark_ready(
        self,
        reel_id: str,
        video_path: Path,
        metadata_path: Path,
        qc_details: Optional[Dict[str, Any]] = None
    ) -> Path:
        return self.writer.move_to_ready(reel_id, video_path, metadata_path, qc_details)

    def mark_rejected(self, reel_id: str, reason: str) -> Path:
        return self.writer.move_to_rejected(reel_id, reason)
