"""
Flow Agent: Manages Google Chrome CDP automation, Google Flow project interaction, and downloads.
"""
from typing import Optional
from .base import BaseAgent, AgentStatus

class FlowAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="FLOW_AGENT",
            display_name="Flow Agent",
            role="browser_generation",
            description="Google Chrome CDP bağlantısı üzerinden Google Flow Project Editor ile etkileşime girer, promptları gönderir ve yeni video artefaktlarını indirir.",
            initial_status=AgentStatus.IDLE
        )

    def start_segment_generation(self, reel_id: str, segment_index: int, total_segments: int = 3) -> None:
        self.start_task(
            task=f"Generating Segment {segment_index}/{total_segments} on Google Flow",
            reel_id=reel_id,
            segment=segment_index
        )

    def start_segment_download(self, reel_id: str, segment_index: int) -> None:
        self.update_status(
            AgentStatus.RUNNING,
            task=f"Downloading Segment {segment_index}/3 artifact"
        )

    def complete_segment(self, reel_id: str, segment_index: int) -> None:
        self.update_status(
            AgentStatus.RUNNING,
            task=f"Segment {segment_index}/3 downloaded successfully"
        )

    def complete_reel_flow(self, reel_id: str) -> None:
        self.complete_task(f"All 3 segments generated and downloaded for {reel_id}")
