"""
Base Agent interface and state model for Reels AI Factory deterministic agents.
"""
from abc import ABC
from enum import Enum
import datetime
from typing import Dict, Any, Optional

class AgentStatus(str, Enum):
    IDLE = "IDLE"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    DISABLED = "DISABLED"

class BaseAgent(ABC):
    """Abstract base class for all deterministic orchestration agents."""

    def __init__(
        self,
        agent_id: str,
        display_name: str,
        role: str,
        description: str,
        initial_status: AgentStatus = AgentStatus.IDLE
    ):
        self.agent_id = agent_id
        self.display_name = display_name
        self.role = role
        self.description = description
        self.status = initial_status
        self.current_run_id: Optional[str] = None
        self.current_reel_id: Optional[str] = None
        self.current_segment: Optional[int] = None
        self.current_task: Optional[str] = None
        self.last_error: Optional[str] = None
        self.last_updated: str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.stats: Dict[str, Any] = {}

    def start_task(
        self,
        task: str,
        run_id: Optional[str] = None,
        reel_id: Optional[str] = None,
        segment: Optional[int] = None
    ) -> None:
        """Mark agent as actively running a task."""
        if self.status == AgentStatus.DISABLED:
            return
        self.status = AgentStatus.RUNNING
        self.current_task = task
        if run_id:
            self.current_run_id = run_id
        if reel_id:
            self.current_reel_id = reel_id
        if segment is not None:
            self.current_segment = segment
        self.last_error = None
        self.last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def complete_task(self, task_summary: Optional[str] = None) -> None:
        """Mark current task as completed successfully."""
        if self.status == AgentStatus.DISABLED:
            return
        self.status = AgentStatus.DONE
        if task_summary:
            self.current_task = task_summary
        self.last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def fail_task(self, error_message: str) -> None:
        """Mark current task as failed with an error message."""
        if self.status == AgentStatus.DISABLED:
            return
        self.status = AgentStatus.FAILED
        self.last_error = error_message
        self.last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def update_status(self, status: AgentStatus, task: Optional[str] = None) -> None:
        """Update agent status and task description."""
        if self.status == AgentStatus.DISABLED and status != AgentStatus.DISABLED:
            return
        self.status = status
        if task is not None:
            self.current_task = task
        self.last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def clear_task(self) -> None:
        """Reset agent task context back to idle."""
        if self.status == AgentStatus.DISABLED:
            return
        self.status = AgentStatus.IDLE
        self.current_task = None
        self.current_reel_id = None
        self.current_segment = None
        self.last_updated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize agent state to dictionary."""
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "role": self.role,
            "description": self.description,
            "status": self.status.value,
            "current_run_id": self.current_run_id,
            "current_reel_id": self.current_reel_id,
            "current_segment": self.current_segment,
            "current_task": self.current_task,
            "last_error": self.last_error,
            "last_updated": self.last_updated,
            "stats": self.stats
        }
