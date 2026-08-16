"""
Idea Agent: Selects diverse, high-aesthetic architectural construction concepts.
"""
from typing import Optional, Dict, Any
from .base import BaseAgent, AgentStatus

class IdeaAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="IDEA_AGENT",
            display_name="Idea Agent",
            role="content_ideation",
            description="Yeni, tekrar etmeyen ve görsel olarak tatmin edici mimari inşa konseptlerini seçer ve başlık/ortam/stil parametrelerini belirler.",
            initial_status=AgentStatus.IDLE
        )

    def select_concept(self, reel_id: str, plan_title: str, category: str, diversity_score: float) -> None:
        self.start_task(
            task=f"Selected concept: '{plan_title}' ({category}) [Diversity: {diversity_score:.2f}]",
            reel_id=reel_id
        )
        self.complete_task(f"Concept '{plan_title}' approved for staged planning.")
