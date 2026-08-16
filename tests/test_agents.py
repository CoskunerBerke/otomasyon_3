"""
Unit and integration tests for Multi-Agent Orchestration, Control Center,
and Obsidian Live Knowledge Graph.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.config import AppConfig
from automation.agents import (
    BaseAgent,
    AgentStatus,
    AgentMessage,
    MessageType,
    MEANINGFUL_MESSAGE_TYPES,
    AgentRunContext,
    ObsidianGraphWriter,
    AgentMessageBus,
    AgentManager,
    ContentDirectorAgent,
    HistoryAgent,
    IdeaAgent,
    SegmentPlannerAgent,
    FlowAgent,
    QualityAgent,
    PublishAgent,
    AnalyticsAgent
)
from automation.content.engine import ContentEngine
from automation.obsidian.writer import ObsidianWriter
from automation.obsidian.reader import ObsidianReader

def test_base_agent_lifecycle_and_disabled_state():
    agent = ContentDirectorAgent()
    assert agent.status == AgentStatus.IDLE

    agent.start_task("Supervising test run", run_id="RUN-TEST-01", reel_id="REEL-2026-0001")
    assert agent.status == AgentStatus.RUNNING
    assert agent.current_task == "Supervising test run"
    assert agent.current_run_id == "RUN-TEST-01"
    assert agent.current_reel_id == "REEL-2026-0001"

    agent.complete_task("Completed supervision")
    assert agent.status == AgentStatus.DONE
    assert agent.current_task == "Completed supervision"

    agent.fail_task("Fatal network timeout")
    assert agent.status == AgentStatus.FAILED
    assert agent.last_error == "Fatal network timeout"

    # Disabled agent check
    pub_agent = PublishAgent()
    assert pub_agent.status == AgentStatus.DISABLED
    pub_agent.start_task("Attempt start")
    assert pub_agent.status == AgentStatus.DISABLED  # Must remain DISABLED

    analytics_agent = AnalyticsAgent()
    assert analytics_agent.status == AgentStatus.DISABLED

def test_agent_message_creation_and_meaningful_flag():
    msg_meaningful = AgentMessage(
        message_id="MSG-20260816-00001",
        run_id="RUN-2026-08-16-0001",
        from_agent="IDEA_AGENT",
        to_agent="SEGMENT_PLANNER_AGENT",
        message_type=MessageType.CONCEPT_SELECTED,
        summary="Concept selected",
        reel_id="REEL-2026-0012"
    )
    assert msg_meaningful.is_meaningful is True

    msg_poll = AgentMessage(
        message_id="MSG-20260816-00002",
        run_id="RUN-2026-08-16-0001",
        from_agent="FLOW_AGENT",
        to_agent="QUALITY_AGENT",
        message_type=MessageType.FLOW_GENERATION_PROGRESS,
        summary="Polling status...",
        reel_id="REEL-2026-0012"
    )
    assert msg_poll.is_meaningful is False

def test_graph_writer_initializes_agent_notes_and_architecture(tmp_path: Path):
    vault = tmp_path / "Vault"
    gw = ObsidianGraphWriter(vault)
    mgr = AgentManager(vault)

    # Check 00_AGENTS directory
    agents_dir = vault / "00_AGENTS"
    assert agents_dir.exists()
    assert (agents_dir / "CONTENT_DIRECTOR.md").exists()
    assert (agents_dir / "HISTORY_AGENT.md").exists()
    assert (agents_dir / "IDEA_AGENT.md").exists()
    assert (agents_dir / "SEGMENT_PLANNER_AGENT.md").exists()
    assert (agents_dir / "FLOW_AGENT.md").exists()
    assert (agents_dir / "QUALITY_AGENT.md").exists()
    assert (agents_dir / "PUBLISH_AGENT.md").exists()
    assert (agents_dir / "ANALYTICS_AGENT.md").exists()
    assert (agents_dir / "AGENT_ARCHITECTURE.md").exists()

    # Check wikilinks in Idea Agent note
    idea_content = (agents_dir / "IDEA_AGENT.md").read_text(encoding="utf-8")
    assert "[[CONTENT_DIRECTOR]]" in idea_content
    assert "[[HISTORY_AGENT]]" in idea_content
    assert "[[SEGMENT_PLANNER_AGENT]]" in idea_content
    assert "[[AGENT_CONTROL_CENTER]]" in idea_content

    # Check Architecture note mermaid diagram
    arch_content = (agents_dir / "AGENT_ARCHITECTURE.md").read_text(encoding="utf-8")
    assert "flowchart TD" in arch_content
    assert "CD[CONTENT_DIRECTOR] --> HA[HISTORY_AGENT]" in arch_content
    assert "FLOW_AGENT" in arch_content

def test_control_center_atomic_updates(tmp_path: Path):
    vault = tmp_path / "Vault"
    mgr = AgentManager(vault)

    ctx = mgr.start_run(requested_reels=["REEL-2026-0012", "REEL-2026-0013"])
    cc_file = vault / "AGENT_CONTROL_CENTER.md"
    assert cc_file.exists()

    content = cc_file.read_text(encoding="utf-8")
    assert "REELS AI FACTORY — AGENT CONTROL CENTER" in content
    assert f"[[{ctx.run_id}]]" in content
    assert "[[REEL-2026-0012]]" in content

    # Test milestone updates
    engine = ContentEngine()
    plan = engine.generate_next_reels(count=1, past_records=[], duration_seconds=10)[0]
    mgr.record_concept_selection("REEL-2026-0012", plan)

    content_updated = cc_file.read_text(encoding="utf-8")
    assert "CONCEPT_SELECTED" in content_updated
    assert plan.title in content_updated

def test_segment_notes_and_linear_chain(tmp_path: Path):
    vault = tmp_path / "Vault"
    mgr = AgentManager(vault)
    ctx = mgr.start_run(requested_reels=["REEL-2026-0012"])

    engine = ContentEngine()
    plan = engine.generate_next_reels(count=1, past_records=[], duration_seconds=10)[0]
    mgr.record_segment_planning("REEL-2026-0012", plan)

    seg_dir = vault / "12_SEGMENTS"
    s1_file = seg_dir / "REEL-2026-0012_SEGMENT-01.md"
    s2_file = seg_dir / "REEL-2026-0012_SEGMENT-02.md"
    s3_file = seg_dir / "REEL-2026-0012_SEGMENT-03.md"

    assert s1_file.exists()
    assert s2_file.exists()
    assert s3_file.exists()

    s1_content = s1_file.read_text(encoding="utf-8")
    assert "[[REEL-2026-0012]]" in s1_content
    assert "[[FLOW_AGENT]]" in s1_content
    assert "[[QUALITY_AGENT]]" in s1_content
    assert "None (Start of Reel)" in s1_content
    assert "[[REEL-2026-0012_SEGMENT-02]]" in s1_content

    s2_content = s2_file.read_text(encoding="utf-8")
    assert "[[REEL-2026-0012_SEGMENT-01]]" in s2_content
    assert "[[REEL-2026-0012_SEGMENT-03]]" in s2_content

    s3_content = s3_file.read_text(encoding="utf-8")
    assert "[[REEL-2026-0012_SEGMENT-02]]" in s3_content
    assert "None (Final Segment)" in s3_content

def test_run_note_and_message_log_creation(tmp_path: Path):
    vault = tmp_path / "Vault"
    mgr = AgentManager(vault)
    ctx = mgr.start_run(requested_reels=["REEL-2026-0012", "REEL-2026-0013", "REEL-2026-0014"])

    run_file = vault / "10_AGENT_RUNS" / f"{ctx.run_id}.md"
    msg_log_file = vault / "11_AGENT_MESSAGES" / f"{ctx.run_id}_MESSAGES.md"

    assert run_file.exists()
    assert msg_log_file.exists()

    run_content = run_file.read_text(encoding="utf-8")
    assert "[[REEL-2026-0012]]" in run_content
    assert "[[REEL-2026-0013]]" in run_content
    assert "[[REEL-2026-0014]]" in run_content
    assert "[[CONTENT_DIRECTOR]]" in run_content
    assert "[[FLOW_AGENT]]" in run_content

    msg_log_content = msg_log_file.read_text(encoding="utf-8")
    assert "TASK_REQUEST" in msg_log_content

def test_meaningful_message_creates_standalone_graph_node(tmp_path: Path):
    vault = tmp_path / "Vault"
    mgr = AgentManager(vault)
    ctx = mgr.start_run(requested_reels=["REEL-2026-0012"])

    engine = ContentEngine()
    plan = engine.generate_next_reels(count=1, past_records=[], duration_seconds=10)[0]
    mgr.record_concept_selection("REEL-2026-0012", plan)

    # Check if a standalone message node was created under 11_AGENT_MESSAGES/
    msg_files = list((vault / "11_AGENT_MESSAGES").glob("MSG-*.md"))
    assert len(msg_files) >= 1

    msg_content = msg_files[0].read_text(encoding="utf-8")
    assert "[[IDEA_AGENT]]" in msg_content or "[[CONTENT_DIRECTOR]]" in msg_content
    assert f"[[{ctx.run_id}]]" in msg_content

def test_reel_note_contains_agent_graph_links(tmp_path: Path):
    vault = tmp_path / "Vault"
    writer = ObsidianWriter(vault)

    engine = ContentEngine()
    plan = engine.generate_next_reels(count=1, past_records=[], duration_seconds=10)[0]
    note_path = writer.create_reel_note("REEL-2026-0012", plan, run_id="RUN-2026-08-16-0001")

    content = note_path.read_text(encoding="utf-8")
    assert "## Agent Graph" in content or "# Agent Graph" in content
    assert "[[IDEA_AGENT]]" in content
    assert "[[SEGMENT_PLANNER_AGENT]]" in content
    assert "[[FLOW_AGENT]]" in content
    assert "[[QUALITY_AGENT]]" in content
    assert "[[CONTENT_DIRECTOR]]" in content
    assert "[[RUN-2026-08-16-0001]]" in content
    assert "[[REEL-2026-0012_SEGMENT-01]]" in content
    assert "[[REEL-2026-0012_SEGMENT-02]]" in content
    assert "[[REEL-2026-0012_SEGMENT-03]]" in content

def test_observability_write_failure_does_not_crash():
    writer = ObsidianGraphWriter(Path("Z:/NonExistentPath/Drive"))
    # Should safely catch and log warning without raising exception
    writer._safe_write(Path("Z:/NonExistentPath/Drive/test.md"), "content")
