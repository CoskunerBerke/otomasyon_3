"""
Obsidian Agent Graph and Knowledge Network writer.
Creates and updates Agent notes, Control Center dashboard, Run notes, Message logs,
Message nodes, and Segment nodes with bidirectional Wikilinks.
"""
import os
import re
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from .base import BaseAgent, AgentStatus
from .messages import AgentMessage
from .run_context import AgentRunContext

logger = logging.getLogger("ReelsAIFactory.GraphWriter")

AGENT_DEFINITIONS = {
    "CONTENT_DIRECTOR": {
        "name": "Content Director",
        "role": "orchestration",
        "desc": "Üst seviye üretim planını hazırlar, batch akışını başlatır ve Agentlar arası koordinasyonu denetler.",
        "receives_from": ["QUALITY_AGENT"],
        "sends_to": ["HISTORY_AGENT", "IDEA_AGENT"],
        "uses": ["Run Context", "Batch Coordinator", "Obsidian Lifecycle"]
    },
    "HISTORY_AGENT": {
        "name": "History Agent",
        "role": "history_and_diversity",
        "desc": "Geçmiş tüm tamamlanmış ve görsel Reel kayıtlarını analiz eder; tekrarı önlemek için Diversity kurallarını uygular.",
        "receives_from": ["CONTENT_DIRECTOR", "ANALYTICS_AGENT"],
        "sends_to": ["IDEA_AGENT"],
        "uses": ["Obsidian Visual History", "Diversity Engine", "Legacy Exclusion Rules"]
    },
    "IDEA_AGENT": {
        "name": "Idea Agent",
        "role": "content_ideation",
        "desc": "Yeni, tekrar etmeyen ve görsel olarak tatmin edici mimari inşa konseptlerini seçer ve başlık/ortam/stil parametrelerini belirler.",
        "receives_from": ["CONTENT_DIRECTOR", "HISTORY_AGENT"],
        "sends_to": ["SEGMENT_PLANNER_AGENT"],
        "uses": ["Content Engine", "Diversity Scoring", "Curated Concept Categories"]
    },
    "SEGMENT_PLANNER_AGENT": {
        "name": "Segment Planner Agent",
        "role": "staged_planning",
        "desc": "Her 30 saniyelik Reel için 3 ayrı 10 saniyelik mantıksal inşa aşaması (Foundation -> Main -> Details/Reveal) ve ContinuityContext oluşturur.",
        "receives_from": ["IDEA_AGENT"],
        "sends_to": ["FLOW_AGENT"],
        "uses": ["SegmentPlanner", "Continuity Engine", "Staged Prompt Templates"]
    },
    "FLOW_AGENT": {
        "name": "Flow Agent",
        "role": "browser_generation",
        "desc": "Google Chrome CDP bağlantısı üzerinden Google Flow Project Editor ile etkileşime girer, promptları gönderir ve yeni video artefaktlarını indirir.",
        "receives_from": ["SEGMENT_PLANNER_AGENT"],
        "sends_to": ["QUALITY_AGENT"],
        "uses": ["Google Flow CDP", "Flow State Machine", "Artifact Fingerprinting", "Downloader"]
    },
    "QUALITY_AGENT": {
        "name": "Quality Agent",
        "role": "quality_control",
        "desc": "İndirilen segment videolarının teknik/görsel kontrolünü yapar, ses kanalını temizler, son kareleri çıkarır ve 30s final videoyu birleştirir.",
        "receives_from": ["FLOW_AGENT"],
        "sends_to": ["CONTENT_DIRECTOR", "PUBLISH_AGENT"],
        "uses": ["FFprobe", "FFmpeg Concat Demuxer", "FrameExtractor", "VideoValidator"]
    },
    "PUBLISH_AGENT": {
        "name": "Publish Agent",
        "role": "social_publishing",
        "desc": "Gelecekte Instagram Reels, TikTok ve YouTube Shorts paylaşımlarını yönetecek sosyal medya yayınlama arayüzü.",
        "receives_from": ["QUALITY_AGENT"],
        "sends_to": ["ANALYTICS_AGENT"],
        "uses": ["Social Media Publisher (Future)"]
    },
    "ANALYTICS_AGENT": {
        "name": "Analytics Agent",
        "role": "performance_analytics",
        "desc": "Gelecekte yayınlanan videoların izlenme, retention ve etkileşim verilerini toplayarak History ve Idea agentlarına geri besleme yapacak analitik arayüzü.",
        "receives_from": ["PUBLISH_AGENT"],
        "sends_to": ["HISTORY_AGENT"],
        "uses": ["Analytics Engine (Future)"]
    }
}

class ObsidianGraphWriter:
    """Safely manages creation and atomic updates of all Agent graph notes in the Obsidian Vault."""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path).resolve()
        self.agents_dir = self.vault_path / "00_AGENTS"
        self.runs_dir = self.vault_path / "10_AGENT_RUNS"
        self.messages_dir = self.vault_path / "11_AGENT_MESSAGES"
        self.segments_dir = self.vault_path / "12_SEGMENTS"
        self.publishing_dir = self.vault_path / "13_PUBLISHING"
        self.control_center_path = self.vault_path / "AGENT_CONTROL_CENTER.md"

        self._ensure_folders()

    def _ensure_folders(self) -> None:
        """Create all required agent directories in vault."""
        try:
            self.agents_dir.mkdir(parents=True, exist_ok=True)
            self.runs_dir.mkdir(parents=True, exist_ok=True)
            self.messages_dir.mkdir(parents=True, exist_ok=True)
            self.segments_dir.mkdir(parents=True, exist_ok=True)
            self.publishing_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create agent directories: {e}")

    def _safe_write(self, target_file: Path, content: str) -> None:
        """Atomic write with temporary file and Windows file-lock retry."""
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = target_file.with_suffix(".tmp")
            for _ in range(3):
                try:
                    tmp_file.write_text(content, encoding="utf-8")
                    tmp_file.replace(target_file)
                    return
                except PermissionError:
                    import time
                    time.sleep(0.1)
                except Exception:
                    if tmp_file.exists():
                        tmp_file.unlink(missing_ok=True)
                    raise

            # Fallback direct write
            target_file.write_text(content, encoding="utf-8")
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Observability graph write failed for {target_file.name}: {e}")

    def initialize_agent_notes(self, agents: Dict[str, BaseAgent]) -> None:
        """Create initial Agent notes and Architecture overview in 00_AGENTS/."""
        self._ensure_folders()

        for agent_id, info in AGENT_DEFINITIONS.items():
            agent_obj = agents.get(agent_id)
            status_val = agent_obj.status.value if agent_obj else "IDLE"
            current_task = agent_obj.current_task if agent_obj else "Ready"
            current_reel = f"[[{agent_obj.current_reel_id}]]" if agent_obj and agent_obj.current_reel_id else "None"

            rec_links = "\n".join(f"- [[{a}]]" for a in info["receives_from"]) if info["receives_from"] else "- None (Entry Point)"
            send_links = "\n".join(f"- [[{a}]]" for a in info["sends_to"]) if info["sends_to"] else "- None (Terminal Point)"
            uses_list = "\n".join(f"- {u}" for u in info["uses"])

            content = f"""---
node_type: agent
agent_id: {agent_id}
display_name: {info["name"]}
role: {info["role"]}
status: {status_val}
current_reel: {current_reel}
tags:
  - agent
  - automation
---

# 🤖 {info["name"].upper()}

## 🎯 Görev
{info["desc"]}

---

## 📥 Receives Tasks From
{rec_links}

## 📤 Sends Results To
{send_links}

---

## 🛠️ Modüller ve Yetenekler
{uses_list}

---

## 📊 Anlık Durum
- **Status:** {status_val}
- **Aktif Reel:** {current_reel}
- **Son İşlem:** {current_task or "None"}

---

## 🌐 İlişkili Bağlantılar
- [[AGENT_CONTROL_CENTER]]
- [[AGENT_ARCHITECTURE]]
"""
            note_file = self.agents_dir / f"{agent_id}.md"
            self._safe_write(note_file, content)

        # Write AGENT_ARCHITECTURE.md
        self._write_architecture_note()

    def _write_architecture_note(self) -> None:
        """Write 00_AGENTS/AGENT_ARCHITECTURE.md with Mermaid topology and documentation."""
        arch_content = """---
node_type: architecture
title: Agent Architecture & Knowledge Graph
tags:
  - agent
  - architecture
  - documentation
---

# 🌐 REELS AI FACTORY — AGENT ARCHITECTURE & KNOWLEDGE NETWORK

Reels AI Factory, deterministik Agent'lar ve birbirine bağlı Markdown bilgi ağı (Knowledge Graph) ile çalışır.

---

## 🔄 Agent Akış Diyagramı (Mermaid)

```mermaid
flowchart TD
    CD[CONTENT_DIRECTOR] --> HA[HISTORY_AGENT]
    CD --> IA[IDEA_AGENT]
    HA --> IA
    IA --> SPA[SEGMENT_PLANNER_AGENT]
    SPA --> FA[FLOW_AGENT]
    FA --> QA[QUALITY_AGENT]
    QA --> CD
    QA --> PA[PUBLISH_AGENT]
    PA --> AA[ANALYTICS_AGENT]
    AA --> HA
```

---

## 🧩 Agent Rolleri ve Wikilink Ağı

1. **[[CONTENT_DIRECTOR]]:** Üretim orkestrasyonunu yönetir, batch çalıştırmalarını başlatır ve sonuçları onaylar.
2. **[[HISTORY_AGENT]]:** Geçmiş Reel kayıtlarını inceler ve konu tekrarlarını önler.
3. **[[IDEA_AGENT]]:** Özgün ve görsel olarak güçlü dönüşüm konseptlerini seçer.
4. **[[SEGMENT_PLANNER_AGENT]]:** 30 saniyelik Reel için 3 aşamalı (10s x 3) inşa planı ve ContinuityContext oluşturur.
5. **[[FLOW_AGENT]]:** Google Chrome CDP ile Google Flow üzerinde her segmenti sırayla üretir ve indirir.
6. **[[QUALITY_AGENT]]:** Segment QC, ses temizleme, son kare çıkarma ve 30s final birleştirmesini (FFmpeg concat) yapar.
7. **[[PUBLISH_AGENT]]:** Sosyal medya paylaşım arayüzü (Gelecek sürüm için DISABLED).
8. **[[ANALYTICS_AGENT]]:** İzlenme ve etkileşim geri besleme arayüzü (Gelecek sürüm için DISABLED).

---

## 📊 Graph View Cluster'ları

Obsidian Graph View açıldığında sistem zamanla şu doğal cluster'ları oluşturur:
- **Merkez Agentlar:** `[[CONTENT_DIRECTOR]]`, `[[HISTORY_AGENT]]`, `[[IDEA_AGENT]]`, `[[SEGMENT_PLANNER_AGENT]]`, `[[FLOW_AGENT]]`, `[[QUALITY_AGENT]]`
- **Run Cluster'ları:** `[[RUN-YYYY-MM-DD-HHMMSS]]` altında gruplanan Reel'ler.
- **Reel & Segment Cluster'ları:** Her `[[REEL-XXXX]]` etrafında `[[REEL-XXXX_SEGMENT-01]]`, `[[REEL-XXXX_SEGMENT-02]]`, `[[REEL-XXXX_SEGMENT-03]]` zinciri.
- **Message Node'ları:** Önemli aşamalarda Agent'lar arasındaki `[[MSG-...]]` bilgi düğümleri.

---

## 🧭 İlgili Bağlantılar
- [[AGENT_CONTROL_CENTER]]
- [[CONTENT_DIRECTOR]]
- [[HISTORY_AGENT]]
- [[IDEA_AGENT]]
- [[SEGMENT_PLANNER_AGENT]]
- [[FLOW_AGENT]]
- [[QUALITY_AGENT]]
"""
        arch_file = self.agents_dir / "AGENT_ARCHITECTURE.md"
        self._safe_write(arch_file, arch_content)

    def update_control_center(
        self,
        context: AgentRunContext,
        agents: Dict[str, BaseAgent],
        last_message: Optional[AgentMessage] = None
    ) -> None:
        """Write the live AGENT_CONTROL_CENTER.md dashboard to vault root."""
        status_emojis = {
            AgentStatus.IDLE: "⚪ IDLE",
            AgentStatus.WAITING: "⏳ WAITING",
            AgentStatus.RUNNING: "🟡 RUNNING",
            AgentStatus.DONE: "✅ DONE",
            AgentStatus.FAILED: "❌ FAILED",
            AgentStatus.DISABLED: "⏸ DISABLED"
        }

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_reel_link = f"[[{context.current_reel_id}]]" if context.current_reel_id else "None"
        run_link = f"[[{context.run_id}]]"

        # Last message display
        if last_message:
            last_msg_block = f"""[[{last_message.from_agent}]]
→ [[{last_message.to_agent}]]

**{last_message.message_type.value if hasattr(last_message.message_type, 'value') else last_message.message_type}**
{last_message.summary}
{f"Reel: [[{last_message.reel_id}]]" if last_message.reel_id else ""}
"""
        else:
            last_msg_block = "No active messages."

        content = f"""# 🤖 REELS AI FACTORY — AGENT CONTROL CENTER

## 🚀 CURRENT RUN
- **Run:** {run_link}
- **Status:** `{context.status}`
- **Current Reel:** {current_reel_link}
- **Batch Progress:** {len(context.completed_reels)} / {len(context.requested_reels)} Reels ({context.current_action})

---

## 🧠 CONTENT DIRECTOR
- **Status:** {status_emojis.get(agents["CONTENT_DIRECTOR"].status, "IDLE")}
- **Task:** {agents["CONTENT_DIRECTOR"].current_task or "Supervising pipeline"}

---

## 🗃 HISTORY AGENT
- **Status:** {status_emojis.get(agents["HISTORY_AGENT"].status, "IDLE")}
- **Task:** {agents["HISTORY_AGENT"].current_task or "Idle"}

---

## 💡 IDEA AGENT
- **Status:** {status_emojis.get(agents["IDEA_AGENT"].status, "IDLE")}
- **Selected Reel:** {f"[[{agents['IDEA_AGENT'].current_reel_id}]]" if agents['IDEA_AGENT'].current_reel_id else "None"}
- **Task:** {agents["IDEA_AGENT"].current_task or "Idle"}

---

## 🎬 SEGMENT PLANNER AGENT
- **Status:** {status_emojis.get(agents["SEGMENT_PLANNER_AGENT"].status, "IDLE")}
- **Task:** {agents["SEGMENT_PLANNER_AGENT"].current_task or "Idle"}

---

## 🏭 FLOW AGENT
- **Status:** {status_emojis.get(agents["FLOW_AGENT"].status, "IDLE")}
- **Active Reel:** {f"[[{agents['FLOW_AGENT'].current_reel_id}]]" if agents['FLOW_AGENT'].current_reel_id else "None"}
- **Task:** {agents["FLOW_AGENT"].current_task or "Waiting for plans"}

---

## 🔍 QUALITY AGENT
- **Status:** {status_emojis.get(agents["QUALITY_AGENT"].status, "IDLE")}
- **Task:** {agents["QUALITY_AGENT"].current_task or "Idle"}

---

## 📤 PUBLISH AGENT
- **Status:** {status_emojis.get(agents["PUBLISH_AGENT"].status, "DISABLED")}
- **Target YouTube:** `@BuiIdVerse`
- **Target TikTok:** `@kitchenverse360`
- **Account Verification:** YouTube: `VERIFIED` | TikTok: `VERIFIED`
- **Task:** {agents["PUBLISH_AGENT"].current_task or ("Publishing Layer active. Ready to schedule." if agents["PUBLISH_AGENT"].status != AgentStatus.DISABLED else "Social media scheduling interface (Future)")}

---

## 📊 ANALYTICS AGENT
- **Status:** {status_emojis.get(agents["ANALYTICS_AGENT"].status, "DISABLED")}
- **Task:** Performance retention analytics (Future)

---

## 💬 LAST AGENT MESSAGE
{last_msg_block}

---

*Last Updated: {now_str}*
"""
        self._safe_write(self.control_center_path, content)

    def write_run_note(self, context: AgentRunContext, agents: Dict[str, BaseAgent]) -> None:
        """Create or update 10_AGENT_RUNS/<RUN_ID>.md."""
        reels_links = "\n".join(f"- [[{r}]]" for r in context.requested_reels) if context.requested_reels else "- None"
        agents_links = "\n".join(f"- [[{a}]]" for a in AGENT_DEFINITIONS.keys())

        agent_status_lines = []
        for a_id in AGENT_DEFINITIONS.keys():
            ag = agents.get(a_id)
            st = ag.status.value if ag else "IDLE"
            agent_status_lines.append(f"- **{a_id}:** `{st}` ({ag.current_task if ag else ''})")
        agent_status_str = "\n".join(agent_status_lines)

        timeline_str = "\n".join(f"- {t}" for t in context.timeline[-15:]) if context.timeline else "- Run started."

        content = f"""---
node_type: run
run_id: {context.run_id}
status: {context.status}
started_at: {context.started_at}
finished_at: {context.finished_at or ""}
requested_reels: {len(context.requested_reels)}
completed_reels: {len(context.completed_reels)}
failed_reels: {len(context.failed_reels)}
tags:
  - run
  - automation
---

# 🚀 RUN: {context.run_id}

## 🎯 Current Target
- **Active Reel:** {f"[[{context.current_reel_id}]]" if context.current_reel_id else "None"}
- **Status:** `{context.status}`
- **Progress:** {len(context.completed_reels)} / {len(context.requested_reels)} Completed

---

## 📦 Batch Reels
{reels_links}

---

## 🤖 Participating Agents
{agents_links}

---

## 📊 Agent Statuses
{agent_status_str}

---

## 📜 Activity Timeline
{timeline_str}

---

## 💬 Message Log
- [[{context.run_id}_MESSAGES]]
- [[AGENT_CONTROL_CENTER]]
"""
        note_file = self.runs_dir / f"{context.run_id}.md"
        self._safe_write(note_file, content)

    def append_to_message_log(self, context: AgentRunContext, message: AgentMessage) -> None:
        """Append message entry to 11_AGENT_MESSAGES/<RUN_ID>_MESSAGES.md."""
        log_file = self.messages_dir / f"{context.run_id}_MESSAGES.md"

        if not log_file.exists():
            header = f"""---
node_type: message_log
run_id: {context.run_id}
tags:
  - message-log
---

# 💬 {context.run_id} — Agent Messages

Run: [[{context.run_id}]] | Dashboard: [[AGENT_CONTROL_CENTER]]

---
"""
            self._safe_write(log_file, header)

        ts = message.created_at.split()[-1] if " " in message.created_at else message.created_at
        reel_clause = f"\nReel: [[{message.reel_id}]]" if message.reel_id else ""
        seg_clause = f" (Segment {message.segment_index})" if message.segment_index else ""

        entry = f"""
## ⏱️ {ts} — {message.message_type.value if hasattr(message.message_type, 'value') else message.message_type}

[[{message.from_agent}]] → [[{message.to_agent}]]{seg_clause}{reel_clause}

**Summary:** {message.summary}

---
"""
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.warning(f"Failed to append to message log: {e}")

    def write_meaningful_message_node(self, message: AgentMessage) -> None:
        """Create standalone graph node for a meaningful message in 11_AGENT_MESSAGES/<MSG_ID>.md."""
        m_type = message.message_type.value if hasattr(message.message_type, "value") else str(message.message_type)
        reel_link = f"[[{message.reel_id}]]" if message.reel_id else "None"
        seg_link = f"[[{message.reel_id}_SEGMENT-{message.segment_index:02d}]]" if message.reel_id and message.segment_index else "None"

        content = f"""---
node_type: agent_message
message_id: {message.message_id}
message_type: {m_type}
run_id: {message.run_id}
reel_id: {message.reel_id or ""}
segment_index: {message.segment_index or ""}
tags:
  - agent-message
---

# 📨 {m_type}

- **From:** [[{message.from_agent}]]
- **To:** [[{message.to_agent}]]
- **Run:** [[{message.run_id}]]
- **Reel:** {reel_link}
- **Segment:** {seg_link}
- **Timestamp:** `{message.created_at}`

---

## 📝 Summary
{message.summary}

---

## 🌐 Connections
- [[{message.from_agent}]]
- [[{message.to_agent}]]
- [[{message.run_id}]]
- [[{message.run_id}_MESSAGES]]
- [[AGENT_CONTROL_CENTER]]
"""
        msg_file = self.messages_dir / f"{message.message_id}.md"
        self._safe_write(msg_file, content)

    def write_segment_node(
        self,
        reel_id: str,
        segment_index: int,
        total_segments: int,
        run_id: str,
        stage_name: str,
        duration_seconds: int,
        status: str,
        starting_state: str,
        action_description: str,
        ending_state: str,
        prompt: str
    ) -> Path:
        """
        Create 12_SEGMENTS/<REEL_ID>_SEGMENT-<XX>.md node
        linking to parent Reel, Run, Agents, and maintaining linear segment chain.
        """
        seg_id = f"{reel_id}_SEGMENT-{segment_index:02d}"

        # Segment chain linkages
        prev_link = f"[[{reel_id}_SEGMENT-{segment_index-1:02d}]]" if segment_index > 1 else "None (Start of Reel)"
        next_link = f"[[{reel_id}_SEGMENT-{segment_index+1:02d}]]" if segment_index < total_segments else "None (Final Segment)"

        content = f"""---
node_type: segment
reel_id: {reel_id}
segment_index: {segment_index}
stage_name: {stage_name}
duration_seconds: {duration_seconds}
status: {status}
run_id: {run_id}
tags:
  - segment
  - pipeline-v3
---

# 🎬 {reel_id} — SEGMENT {segment_index:02d} ({stage_name})

- **Parent Reel:** [[{reel_id}]]
- **Run:** [[{run_id}]]
- **Duration:** {duration_seconds} seconds
- **Status:** `{status}`

---

## 🔗 Segment Chain (Continuity)
- **Previous Stage:** {prev_link}
- **Next Stage:** {next_link}

---

## 🤖 Responsible Agents
- **Planned by:** [[SEGMENT_PLANNER_AGENT]]
- **Generated by:** [[FLOW_AGENT]]
- **Reviewed by:** [[QUALITY_AGENT]]

---

## 🏗️ Construction Details
- **Starting State:** {starting_state}
- **Staged Action:** {action_description}
- **Ending State:** {ending_state}

---

## 📜 Segment Prompt
```text
{prompt}
```

---

## 🌐 Graph Connections
- [[{reel_id}]]
- [[{run_id}]]
- [[SEGMENT_PLANNER_AGENT]]
- [[FLOW_AGENT]]
- [[QUALITY_AGENT]]
- [[AGENT_CONTROL_CENTER]]
"""
        seg_file = self.segments_dir / f"{seg_id}.md"
        self._safe_write(seg_file, content)
        return seg_file
