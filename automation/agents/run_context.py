"""
Run Context model for managing batch runs and tracking agent states.
"""
from dataclasses import dataclass, field
import datetime
from typing import List, Dict, Any, Optional
from .messages import AgentMessage

@dataclass
class AgentRunContext:
    """Tracks global state, active reels, and timeline for a single execution run."""
    run_id: str
    started_at: str = field(default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    finished_at: Optional[str] = None
    status: str = "RUNNING"  # RUNNING, COMPLETED, FAILED, RESUMED
    requested_reels: List[str] = field(default_factory=list)
    completed_reels: List[str] = field(default_factory=list)
    failed_reels: List[str] = field(default_factory=list)
    current_reel_id: Optional[str] = None
    current_segment_index: Optional[int] = None
    current_action: str = "Initializing"
    messages: List[AgentMessage] = field(default_factory=list)
    agent_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timeline: List[str] = field(default_factory=list)

    def log_activity(self, entry: str) -> None:
        """Add timestamped entry to run timeline."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.timeline.append(f"[{ts}] {entry}")

    def complete_run(self) -> None:
        """Mark run as completed."""
        self.status = "COMPLETED"
        self.finished_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_activity("Run finished successfully.")

    def fail_run(self, error_message: str) -> None:
        """Mark run as failed."""
        self.status = "FAILED"
        self.finished_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_activity(f"Run failed: {error_message}")
