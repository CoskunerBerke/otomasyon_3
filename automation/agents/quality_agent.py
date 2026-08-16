"""
Quality Agent: Manages segment validation, end-frame extraction, and final 30s concatenation.
"""
from typing import Optional, Dict, Any
from .base import BaseAgent, AgentStatus

class QualityAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="QUALITY_AGENT",
            display_name="Quality Agent",
            role="quality_control",
            description="İndirilen segment videolarının teknik/görsel kontrolünü yapar, ses kanalını temizler, son kareleri çıkarır ve 30s final videoyu birleştirir.",
            initial_status=AgentStatus.IDLE
        )

    def start_segment_qc(self, reel_id: str, segment_index: int) -> None:
        self.start_task(
            task=f"Inspecting technical QC & extracting end-frame for Segment {segment_index}/3",
            reel_id=reel_id,
            segment=segment_index
        )

    def pass_segment_qc(self, reel_id: str, segment_index: int) -> None:
        self.update_status(
            AgentStatus.RUNNING,
            task=f"Segment {segment_index}/3 passed QC (Clean Silent H.264)"
        )

    def start_final_concat(self, reel_id: str) -> None:
        self.update_status(
            AgentStatus.RUNNING,
            task=f"Concatenating 3 segments into final 30s silent MP4 for {reel_id}"
        )

    def pass_final_qc(self, reel_id: str, duration: float) -> None:
        self.complete_task(f"{reel_id} final 30s video validated (Duration: {duration:.1f}s, 9:16, Silent).")
