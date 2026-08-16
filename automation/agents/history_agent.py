"""
History Agent: Analyzes completed and legacy visual transformation reels to enforce diversity.
"""
from typing import List, Dict, Any, Optional
from .base import BaseAgent, AgentStatus

class HistoryAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_id="HISTORY_AGENT",
            display_name="History Agent",
            role="history_and_diversity",
            description="Geçmiş tüm tamamlanmış ve görsel Reel kayıtlarını analiz eder; tekrarı önlemek için Diversity kurallarını uygular.",
            initial_status=AgentStatus.IDLE
        )

    def analyze_history(self, history_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.start_task(
            task=f"Analyzing {len(history_records)} past visual transformation records"
        )
        avoid_topics = [rec.get("title", "") for rec in history_records[-5:] if rec.get("title")]
        recent_cats = [rec.get("category", "") for rec in history_records[-3:] if rec.get("category")]

        res = {
            "past_reels_count": len(history_records),
            "avoid_topics": avoid_topics,
            "recent_categories": recent_cats
        }
        self.stats["analyzed_count"] = len(history_records)
        self.complete_task(f"Analyzed {len(history_records)} past reels. Diversity constraints extracted.")
        return res
