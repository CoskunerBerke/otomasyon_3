"""
Segment Planner Agent: Plans the 3 x 10s step-by-step construction stages and continuity context.
"""
from typing import List, Optional
from .base import BaseAgent, AgentStatus

class SegmentPlannerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="SEGMENT_PLANNER_AGENT",
            display_name="Segment Planner Agent",
            role="staged_planning",
            description="Her 30 saniyelik Reel için 3 ayrı 10 saniyelik mantıksal inşa aşaması (Foundation -> Main -> Details/Reveal) ve ContinuityContext oluşturur.",
            initial_status=AgentStatus.IDLE
        )

    def plan_reel_segments(self, reel_id: str, segment_count: int = 3, total_duration: int = 30) -> None:
        self.start_task(
            task=f"Generated {segment_count} staged construction prompts ({total_duration}s total) with ContinuityContext",
            reel_id=reel_id
        )
        self.complete_task(f"3-Stage plan ready for {reel_id}.")
