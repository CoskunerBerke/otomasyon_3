"""
Message Bus for inter-agent communication, activity tracking, and Obsidian Graph synchronization.
"""
import datetime
import logging
from typing import Dict, Any, Optional, List

from .base import BaseAgent
from .messages import AgentMessage, MessageType, MEANINGFUL_MESSAGE_TYPES
from .run_context import AgentRunContext
from .graph_writer import ObsidianGraphWriter

logger = logging.getLogger("ReelsAIFactory.MessageBus")

class AgentMessageBus:
    """Central deterministic message bus for agent events."""

    def __init__(
        self,
        graph_writer: ObsidianGraphWriter,
        agents: Dict[str, BaseAgent],
        enabled: bool = True,
        message_logging: bool = True,
        graph_nodes_enabled: bool = True,
        control_center_enabled: bool = True
    ):
        self.graph_writer = graph_writer
        self.agents = agents
        self.enabled = enabled
        self.message_logging = message_logging
        self.graph_nodes_enabled = graph_nodes_enabled
        self.control_center_enabled = control_center_enabled
        self._msg_counter = 0

    def _next_message_id(self) -> str:
        self._msg_counter += 1
        today_str = datetime.datetime.now().strftime("%Y%m%d")
        return f"MSG-{today_str}-{self._msg_counter:05d}"

    def send(
        self,
        context: AgentRunContext,
        from_agent: str,
        to_agent: str,
        message_type: MessageType,
        summary: str,
        payload: Optional[Dict[str, Any]] = None,
        reel_id: Optional[str] = None,
        segment_index: Optional[int] = None
    ) -> AgentMessage:
        """Dispatch a structured agent message and sync with Obsidian Graph."""
        msg_id = self._next_message_id()
        msg = AgentMessage(
            message_id=msg_id,
            run_id=context.run_id,
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            summary=summary,
            payload=payload or {},
            reel_id=reel_id,
            segment_index=segment_index
        )

        context.messages.append(msg)
        context.log_activity(f"{from_agent} -> {to_agent} [{msg.message_type.value if hasattr(msg.message_type, 'value') else msg.message_type}]: {summary}")

        if not self.enabled:
            return msg

        try:
            # 1. Append to chronological message log (11_AGENT_MESSAGES/<RUN_ID>_MESSAGES.md)
            if self.message_logging:
                self.graph_writer.append_to_message_log(context, msg)

            # 2. Write standalone graph node for meaningful milestones (11_AGENT_MESSAGES/<MSG_ID>.md)
            if self.graph_nodes_enabled and msg.is_meaningful:
                self.graph_writer.write_meaningful_message_node(msg)

            # 3. Update live Control Center (AGENT_CONTROL_CENTER.md)
            if self.control_center_enabled:
                self.graph_writer.update_control_center(context, self.agents, last_message=msg)

            # 4. Update Run note (10_AGENT_RUNS/<RUN_ID>.md)
            if self.graph_nodes_enabled:
                self.graph_writer.write_run_note(context, self.agents)

        except Exception as e:
            logger.warning(f"Error handling message dispatch in message bus: {e}")

        return msg
