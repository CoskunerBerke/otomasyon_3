"""
Content Director Agent: Orchestrates top-level batch runs and oversees pipeline execution.
"""
from typing import Optional, List
from .base import BaseAgent, AgentStatus

class ContentDirectorAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="CONTENT_DIRECTOR",
            display_name="Content Director",
            role="orchestration",
            description="Üst seviye üretim planını hazırlar, batch akışını başlatır ve Agentlar arası koordinasyonu denetler.",
            initial_status=AgentStatus.IDLE
        )

    def start_batch_run(self, run_id: str, requested_reels: List[str]) -> None:
        self.start_task(
            task=f"Supervising batch run ({len(requested_reels)} Reels)",
            run_id=run_id
        )

    def approve_reel_completion(self, reel_id: str) -> None:
        self.update_status(
            AgentStatus.RUNNING,
            task=f"Approved completion of {reel_id}"
        )
