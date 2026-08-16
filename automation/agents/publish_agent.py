"""
Publish Agent: Social media scheduling and publishing interface for YouTube Shorts and TikTok Studio.
"""
from typing import Optional, Dict, Any, List
from .base import BaseAgent, AgentStatus

class PublishAgent(BaseAgent):
    def __init__(self, initial_status: AgentStatus = AgentStatus.DISABLED):
        super().__init__(
            agent_id="PUBLISH_AGENT",
            display_name="Publish Agent",
            role="social_publishing",
            description="YouTube Shorts ve TikTok Studio web arayüzü üzerinden dikey videoların otomatik metadata hazırlama ve zamanlanmış yayın (schedule) yönetimini gerçekleştiren ajan.",
            initial_status=initial_status
        )

    def enable(self) -> None:
        """Enable Publish Agent for active scheduling/publishing tasks."""
        if self.status == AgentStatus.DISABLED:
            self.status = AgentStatus.IDLE
            self.current_task = "Publishing Layer active. Ready to schedule."

    def disable(self) -> None:
        """Disable Publish Agent."""
        self.status = AgentStatus.DISABLED
        self.current_task = "Publishing Layer disabled."

