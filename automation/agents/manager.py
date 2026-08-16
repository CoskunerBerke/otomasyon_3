"""
Agent Manager: Coordinates the lifecycle of agents, active run contexts, and message routing.
"""
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from .base import BaseAgent, AgentStatus
from .messages import AgentMessage, MessageType
from .run_context import AgentRunContext
from .graph_writer import ObsidianGraphWriter
from .message_bus import AgentMessageBus
from .content_director import ContentDirectorAgent
from .history_agent import HistoryAgent
from .idea_agent import IdeaAgent
from .segment_planner_agent import SegmentPlannerAgent
from .flow_agent import FlowAgent
from .quality_agent import QualityAgent
from .publish_agent import PublishAgent
from .analytics_agent import AnalyticsAgent

logger = logging.getLogger("ReelsAIFactory.AgentManager")

class AgentManager:
    """Orchestration coordinator and observability bridge for all agents."""

    def __init__(self, vault_path: Path, config: Any = None):
        self.vault_path = Path(vault_path).resolve()
        self.config = config

        obs_enabled = getattr(config, "agent_observability_enabled", True) if config else True
        msg_logging = getattr(config, "agent_message_logging", True) if config else True
        graph_nodes = getattr(config, "agent_graph_nodes_enabled", True) if config else True
        ctrl_center = getattr(config, "agent_control_center_enabled", True) if config else True

        self.graph_writer = ObsidianGraphWriter(self.vault_path)

        self.agents: Dict[str, BaseAgent] = {
            "CONTENT_DIRECTOR": ContentDirectorAgent(),
            "HISTORY_AGENT": HistoryAgent(),
            "IDEA_AGENT": IdeaAgent(),
            "SEGMENT_PLANNER_AGENT": SegmentPlannerAgent(),
            "FLOW_AGENT": FlowAgent(),
            "QUALITY_AGENT": QualityAgent(),
            "PUBLISH_AGENT": PublishAgent(),
            "ANALYTICS_AGENT": AnalyticsAgent(),
        }

        self.bus = AgentMessageBus(
            graph_writer=self.graph_writer,
            agents=self.agents,
            enabled=obs_enabled,
            message_logging=msg_logging,
            graph_nodes_enabled=graph_nodes,
            control_center_enabled=ctrl_center
        )

        self.current_context: Optional[AgentRunContext] = None

        # Initialize base agent notes and architecture note in Obsidian
        if obs_enabled:
            self.graph_writer.initialize_agent_notes(self.agents)

    def start_run(self, requested_reels: List[str], run_id_override: Optional[str] = None) -> AgentRunContext:
        """Initialize a new production or dry-run execution context."""
        if not run_id_override:
            run_id = f"RUN-{datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
        else:
            run_id = run_id_override

        self.current_context = AgentRunContext(
            run_id=run_id,
            requested_reels=requested_reels,
            current_reel_id=requested_reels[0] if requested_reels else None,
            current_action="Batch run initialized"
        )

        # Update Content Director
        cd = self.agents["CONTENT_DIRECTOR"]
        cd.start_task(f"Supervising batch of {len(requested_reels)} Reels", run_id=run_id)

        # Write initial run note and control center
        self.graph_writer.write_run_note(self.current_context, self.agents)
        self.graph_writer.update_control_center(self.current_context, self.agents)

        # Dispatch RUN_STARTED task request
        self.bus.send(
            context=self.current_context,
            from_agent="CONTENT_DIRECTOR",
            to_agent="HISTORY_AGENT",
            message_type=MessageType.TASK_REQUEST,
            summary=f"Run started for {len(requested_reels)} Reels ({', '.join(requested_reels)}). Analyze visual history.",
            payload={"requested_reels": requested_reels}
        )

        return self.current_context

    def record_history_analysis(self, history_records: List[Dict[str, Any]]) -> None:
        """Record history analysis event and notify Idea Agent."""
        if not self.current_context:
            return

        ha: HistoryAgent = self.agents["HISTORY_AGENT"] # type: ignore
        res = ha.analyze_history(history_records)

        self.bus.send(
            context=self.current_context,
            from_agent="HISTORY_AGENT",
            to_agent="IDEA_AGENT",
            message_type=MessageType.HISTORY_RESULT,
            summary=f"Analyzed {res['past_reels_count']} past visual reels. Diversity parameters generated.",
            payload=res
        )

    def record_concept_selection(self, reel_id: str, plan: Any) -> None:
        """Record concept selection by Idea Agent and pass to Segment Planner."""
        if not self.current_context:
            return

        self.current_context.current_reel_id = reel_id
        ia: IdeaAgent = self.agents["IDEA_AGENT"] # type: ignore
        score = getattr(plan, "diversity_score", 0.85)
        ia.select_concept(reel_id, plan.title, plan.category, score)

        self.bus.send(
            context=self.current_context,
            from_agent="IDEA_AGENT",
            to_agent="SEGMENT_PLANNER_AGENT",
            message_type=MessageType.CONCEPT_SELECTED,
            summary=f"Concept '{plan.title}' ({plan.category}) selected with diversity score {score:.2f}.",
            payload={
                "title": plan.title,
                "category": plan.category,
                "diversity_score": score,
                "environment": getattr(plan, "environment", ""),
                "architecture": getattr(plan, "architecture", "")
            },
            reel_id=reel_id
        )

    def record_segment_planning(self, reel_id: str, plan: Any) -> None:
        """Record 3-stage segment planning by Segment Planner Agent and pass to Flow Agent."""
        if not self.current_context:
            return

        spa: SegmentPlannerAgent = self.agents["SEGMENT_PLANNER_AGENT"] # type: ignore
        seg_count = getattr(plan, "segment_count", len(getattr(plan, "segments", []))) or 3
        spa.plan_reel_segments(reel_id, segment_count=seg_count, total_duration=getattr(plan, "final_duration_seconds", 30))

        # Write segment notes to 12_SEGMENTS/
        if hasattr(plan, "segments") and plan.segments:
            for seg in plan.segments:
                self.graph_writer.write_segment_node(
                    reel_id=reel_id,
                    segment_index=seg.index,
                    total_segments=seg_count,
                    run_id=self.current_context.run_id,
                    stage_name=seg.stage_name,
                    duration_seconds=seg.duration_seconds,
                    status="PENDING",
                    starting_state=seg.starting_state,
                    action_description=seg.action_description,
                    ending_state=seg.ending_state,
                    prompt=seg.prompt
                )

        self.bus.send(
            context=self.current_context,
            from_agent="SEGMENT_PLANNER_AGENT",
            to_agent="FLOW_AGENT",
            message_type=MessageType.SEGMENT_PLAN_READY,
            summary=f"3-stage continuous plan created for {reel_id} (10s x 3 = 30s) with ContinuityContext.",
            payload={"segment_count": seg_count},
            reel_id=reel_id
        )

    def record_flow_generation_start(self, reel_id: str, segment_index: int, total_segments: int = 3) -> None:
        """Record start of generation on Google Flow for a segment."""
        if not self.current_context:
            return

        self.current_context.current_reel_id = reel_id
        self.current_context.current_segment_index = segment_index
        self.current_context.current_action = f"Generating Segment {segment_index}/{total_segments}"

        fa: FlowAgent = self.agents["FLOW_AGENT"] # type: ignore
        fa.start_segment_generation(reel_id, segment_index, total_segments)

        self.bus.send(
            context=self.current_context,
            from_agent="FLOW_AGENT",
            to_agent="QUALITY_AGENT",
            message_type=MessageType.FLOW_GENERATION_STARTED,
            summary=f"Submitted prompt for Segment {segment_index}/{total_segments} to Google Flow.",
            reel_id=reel_id,
            segment_index=segment_index
        )

    def record_flow_segment_downloaded(self, reel_id: str, segment_index: int) -> None:
        """Record segment artifact download completion."""
        if not self.current_context:
            return

        fa: FlowAgent = self.agents["FLOW_AGENT"] # type: ignore
        fa.complete_segment(reel_id, segment_index)

        self.bus.send(
            context=self.current_context,
            from_agent="FLOW_AGENT",
            to_agent="QUALITY_AGENT",
            message_type=MessageType.SEGMENT_READY,
            summary=f"Segment {segment_index}/3 artifact downloaded successfully.",
            reel_id=reel_id,
            segment_index=segment_index
        )

    def record_segment_qc_pass(self, reel_id: str, segment_index: int) -> None:
        """Record successful technical QC & frame extraction for a segment."""
        if not self.current_context:
            return

        qa: QualityAgent = self.agents["QUALITY_AGENT"] # type: ignore
        qa.pass_segment_qc(reel_id, segment_index)

        self.bus.send(
            context=self.current_context,
            from_agent="QUALITY_AGENT",
            to_agent="FLOW_AGENT",
            message_type=MessageType.QC_PASS,
            summary=f"Segment {segment_index}/3 passed QC (Clean Silent H.264, End-Frame extracted).",
            reel_id=reel_id,
            segment_index=segment_index
        )

    def record_final_concat_start(self, reel_id: str) -> None:
        """Record start of FFmpeg final concat."""
        if not self.current_context:
            return

        qa: QualityAgent = self.agents["QUALITY_AGENT"] # type: ignore
        qa.start_final_concat(reel_id)

        self.bus.send(
            context=self.current_context,
            from_agent="QUALITY_AGENT",
            to_agent="CONTENT_DIRECTOR",
            message_type=MessageType.FINAL_CONCAT_STARTED,
            summary=f"Assembling 3 segments into final 30s MP4 for {reel_id}.",
            reel_id=reel_id
        )

    def record_final_qc_pass(self, reel_id: str, duration: float) -> None:
        """Record final 30s video QC pass and notify Publish Agent."""
        if not self.current_context:
            return

        qa: QualityAgent = self.agents["QUALITY_AGENT"] # type: ignore
        qa.pass_final_qc(reel_id, duration)

        self.bus.send(
            context=self.current_context,
            from_agent="QUALITY_AGENT",
            to_agent="PUBLISH_AGENT",
            message_type=MessageType.FINAL_QC_PASS,
            summary=f"{reel_id} final 30s video QC passed (Duration: {duration:.1f}s, 9:16, Clean Silent).",
            payload={"duration": duration},
            reel_id=reel_id
        )

        # Also emit PUBLISH_READY for social media readiness
        self.bus.send(
            context=self.current_context,
            from_agent="PUBLISH_AGENT",
            to_agent="CONTENT_DIRECTOR",
            message_type=MessageType.PUBLISH_READY,
            summary=f"{reel_id} is marked READY and queued for future social publishing.",
            reel_id=reel_id
        )

    def record_reel_completed(self, reel_id: str) -> None:
        """Mark reel as completed in active run context."""
        if not self.current_context:
            return

        if reel_id not in self.current_context.completed_reels:
            self.current_context.completed_reels.append(reel_id)

        cd = self.agents["CONTENT_DIRECTOR"]
        cd.approve_reel_completion(reel_id)

        self.graph_writer.write_run_note(self.current_context, self.agents)
        self.graph_writer.update_control_center(self.current_context, self.agents)

    def record_reel_failed(self, reel_id: str, error_message: str) -> None:
        """Record failure of a reel."""
        if not self.current_context:
            return

        if reel_id not in self.current_context.failed_reels:
            self.current_context.failed_reels.append(reel_id)

        fa = self.agents["FLOW_AGENT"]
        fa.fail_task(error_message)

        self.bus.send(
            context=self.current_context,
            from_agent="FLOW_AGENT",
            to_agent="CONTENT_DIRECTOR",
            message_type=MessageType.ERROR,
            summary=f"Failed processing {reel_id}: {error_message}",
            payload={"error": error_message},
            reel_id=reel_id
        )

    def record_resume_event(self, reel_id: str, resume_stage: str) -> None:
        """Record resumption of an incomplete Reel."""
        if not self.current_context:
            return

        self.bus.send(
            context=self.current_context,
            from_agent="CONTENT_DIRECTOR",
            to_agent="FLOW_AGENT",
            message_type=MessageType.RESUME,
            summary=f"Resuming incomplete Reel {reel_id} from stage: {resume_stage}.",
            payload={"stage": resume_stage},
            reel_id=reel_id
        )

    def complete_run(self) -> None:
        """Finalize the active run."""
        if not self.current_context:
            return

        self.current_context.complete_run()
        for a in self.agents.values():
            if a.status == AgentStatus.RUNNING:
                a.complete_task("Batch run finished.")

        self.graph_writer.write_run_note(self.current_context, self.agents)
        self.graph_writer.update_control_center(self.current_context, self.agents)

    def fail_run(self, error_message: str) -> None:
        """Mark active run as failed."""
        if not self.current_context:
            return

        self.current_context.fail_run(error_message)
        self.graph_writer.write_run_note(self.current_context, self.agents)
        self.graph_writer.update_control_center(self.current_context, self.agents)
