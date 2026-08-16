"""
Atomic writer and lifecycle state manager for Obsidian Reel notes.
Supports V3 30-Second 3-Segment Step-by-Step Reels.
"""
import os
import re
import shutil
import datetime
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
import yaml

from ..content.prompt_engine import ReelConceptPlan

class ObsidianWriter:
    """Manages creation, atomic updates, and lifecycle file movements."""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path).resolve()
        self.template_path = self.vault_path / "09_TEMPLATES" / "SILENT_REEL_TEMPLATE.md"

    def _atomic_write(self, target_file: Path, content: str) -> None:
        """Write content safely with atomic rename and retry on Windows file lock."""
        target_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = target_file.with_suffix(".tmp")
        for attempt in range(3):
            try:
                tmp_file.write_text(content, encoding="utf-8")
                tmp_file.replace(target_file)
                return
            except PermissionError:
                import time
                time.sleep(0.2)
            except Exception:
                if tmp_file.exists():
                    tmp_file.unlink(missing_ok=True)
                raise

        # Direct write fallback if rename is blocked by indexer
        try:
            target_file.write_text(content, encoding="utf-8")
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
        except Exception:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            raise

    def create_reel_note(self, reel_id: str, plan: ReelConceptPlan, run_id: Optional[str] = None) -> Path:
        """
        Create initial Markdown file for a new Reel in 03_SCRIPTS/.
        Supports V3 30-second 3-segment structure.
        """
        scripts_dir = self.vault_path / "03_SCRIPTS"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        target_file = scripts_dir / f"{reel_id}.md"

        today_str = datetime.date.today().isoformat()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        prompt_hash = plan.segments[0].prompt_hash if plan.segments else hashlib.sha256(plan.prompt.strip().encode("utf-8")).hexdigest()[:16]

        # Build segments YAML block
        segments_yaml_lines = ["segments:"]
        for seg in plan.segments:
            segments_yaml_lines.extend([
                f"  - index: {seg.index}",
                f"    stage: {seg.stage_name}",
                f"    duration_seconds: {seg.duration_seconds}",
                f"    status: {seg.status}",
                f"    prompt_hash: {seg.prompt_hash}",
                f"    local_file: \"{str(seg.local_file) if seg.local_file else ''}\"",
                f"    end_frame: \"{str(seg.end_frame_file) if seg.end_frame_file else ''}\""
            ])
        segments_yaml_str = "\n".join(segments_yaml_lines) if plan.segments else "segments: []"

        content = f"""---
id: {reel_id}
title: {plan.title}
category: {plan.category}
topic: {plan.topic_description}
topic_key: {plan.topic_key}
status: PROMPT_READY
pipeline_version: 3
content_mode: silent_global_step_by_step
provider: google_flow
created: {today_str}
video_file: ""
final_duration_seconds: {plan.final_duration_seconds}
segment_count: {len(plan.segments) if plan.segments else 3}
segment_duration_seconds: {plan.segment_duration_seconds}
aspect_ratio: "9:16"
segments_completed: 0
diversity_score: {plan.diversity_score}
prompt_hash: {prompt_hash}
flow_project_url: ""
run_id: "{run_id or ''}"
tags:
  - reel
  - pipeline-v3
{segments_yaml_str}
---

# Concept

**Kategori:** {plan.concept_def.name} ({plan.concept_def.category_group})
**Ortam & Başlangıç:** {plan.environment}
**Dönüşüm / İnşa:** {plan.transformation}
**Mimari Stil:** {plan.architecture}
**Aydınlatma & Atmosfer:** {plan.lighting}
**Kullanılan Malzemeler:** {plan.materials}
**Final Reveal:** {plan.reveal}

---

# Multi-Segment Construction Breakdown (30s)

"""
        if plan.segments:
            for seg in plan.segments:
                content += f"""## Segment {seg.index} ({seg.stage_name} — {seg.duration_seconds}s)

**Başlangıç:** {seg.starting_state}
**İnşa Aşaması:** {seg.action_description}
**Bitiş Durumu:** {seg.ending_state}

```text
{seg.prompt}
```

---

"""
        else:
            content += f"""# Prompt

```text
{plan.prompt}
```

---

"""

        content += f"""# Generation

- **Provider:** Google Flow Web Automation
- **Oluşturulma Tarihi:** {today_str}
- **Başlangıç:** {now_str}
- **Tamamlanma:** -
- **Segment Durumları:**
  - Segment 1 (Foundation): PENDING
  - Segment 2 (Main Construction): PENDING
  - Segment 3 (Details & Reveal): PENDING

---

# Quality Control

- **Teknik QC (FFprobe):** PENDING
- **Segment 1 QC:** PENDING
- **Segment 2 QC:** PENDING
- **Segment 3 QC:** PENDING
- **Final Concat (30s):** PENDING
- **En-Boy Oranı (9:16):** PENDING
- **Ses Kanalı Temizleme:** PENDING
- **Görsel QC (Frame Variance):** PENDING

---

# Agent Graph

- **Selected by:** [[IDEA_AGENT]]
- **Planned by:** [[SEGMENT_PLANNER_AGENT]]
- **Generated by:** [[FLOW_AGENT]]
- **Quality checked by:** [[QUALITY_AGENT]]
- **Directed by:** [[CONTENT_DIRECTOR]]
- **Run:** [[{run_id or "AGENT_CONTROL_CENTER"}]]

### Segments
- [[{reel_id}_SEGMENT-01]]
- [[{reel_id}_SEGMENT-02]]
- [[{reel_id}_SEGMENT-03]]

---

# Final File

- **Dosya Yolu:** -
- **Metadata JSON:** -

---

# Publishing

- **Instagram:** Hazır
- **TikTok:** Hazır
- **YouTube Shorts:** Hazır
"""
        self._atomic_write(target_file, content)
        return target_file

    def find_note_file(self, reel_id: str) -> Optional[Path]:
        """Find the note path for a given reel ID across folders."""
        for folder in ["03_SCRIPTS", "04_PRODUCTION", "05_READY", "06_PUBLISHED", "07_REJECTED"]:
            fpath = self.vault_path / folder / f"{reel_id}.md"
            if fpath.exists():
                return fpath
        return None

    def update_status(self, reel_id: str, new_status: str, extra_meta: Optional[Dict[str, Any]] = None) -> Optional[Path]:
        """
        Update the status frontmatter field of a note in-place.
        """
        note_file = self.find_note_file(reel_id)
        if not note_file or not note_file.exists():
            return None

        content = note_file.read_text(encoding="utf-8", errors="ignore")

        # Update status in frontmatter
        if re.search(r'status:\s*[^\n\r]+', content):
            content = re.sub(r'status:\s*[^\n\r]+', f'status: {new_status}', content, count=1)
        else:
            # Insert if missing
            content = f"---\nstatus: {new_status}\n---\n" + content

        # Update any extra metadata
        if extra_meta:
            for key, val in extra_meta.items():
                val_str = str(val)
                pattern = rf'({key}:\s*)[^\n\r]+'
                if re.search(pattern, content):
                    content = re.sub(pattern, lambda m, v=val_str: f"{m.group(1)}{v}", content, count=1)
                else:
                    # Append right before closing frontmatter
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        parts[1] = f"{parts[1]}\n{key}: {val_str}"
                        content = "---".join(parts)

        self._atomic_write(note_file, content)
        return note_file

    def update_segment_progress(
        self,
        reel_id: str,
        segment_index: int,
        status: str,
        local_file: Optional[Path] = None,
        end_frame: Optional[Path] = None
    ) -> Optional[Path]:
        """Update progress for a specific segment inside the note."""
        note_file = self.find_note_file(reel_id)
        if not note_file or not note_file.exists():
            return None

        content = note_file.read_text(encoding="utf-8", errors="ignore")

        # Update segments_completed count if status is READY
        if status == "READY":
            content = re.sub(
                r'segments_completed:\s*\d+',
                f'segments_completed: {segment_index}',
                content
            )
            stage_names = {1: "Foundation", 2: "Main Construction", 3: "Details & Reveal"}
            st_name = stage_names.get(segment_index, f"Stage {segment_index}")
            content = content.replace(
                f"- Segment {segment_index} ({st_name}): PENDING",
                f"- Segment {segment_index} ({st_name}): READY ({local_file.name if local_file else 'PASS'})"
            )
            content = content.replace(
                f"- Segment {segment_index} QC: PENDING",
                f"- Segment {segment_index} QC: PASS"
            )

        self._atomic_write(note_file, content)
        return note_file

    def move_to_production(self, reel_id: str) -> Path:
        """Move note to 04_PRODUCTION folder."""
        current_path = self.find_note_file(reel_id)
        if not current_path:
            raise FileNotFoundError(f"Note for {reel_id} not found.")

        dest_dir = self.vault_path / "04_PRODUCTION"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{reel_id}.md"

        self.update_status(reel_id, "GENERATING")
        if current_path != dest_path:
            shutil.move(str(current_path), str(dest_path))
        return dest_path

    def move_to_ready(
        self,
        reel_id: str,
        video_path: Path,
        metadata_path: Path,
        qc_details: Optional[Dict[str, Any]] = None
    ) -> Path:
        """Move note to 05_READY folder upon successful generation and QC."""
        current_path = self.find_note_file(reel_id)
        if not current_path:
            raise FileNotFoundError(f"Note for {reel_id} not found.")

        dest_dir = self.vault_path / "05_READY"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{reel_id}.md"

        extra_meta = {
            "video_file": str(video_path),
            "status": "READY",
            "segments_completed": "3"
        }
        self.update_status(reel_id, "READY", extra_meta)

        # Update body fields with final info
        content = current_path.read_text(encoding="utf-8")
        content = content.replace("- **Dosya Yolu:** -", f"- **Dosya Yolu:** `{video_path}`")
        content = content.replace("- **Metadata JSON:** -", f"- **Metadata JSON:** `{metadata_path}`")
        content = content.replace("- **Tamamlanma:** -", f"- **Tamamlanma:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content = content.replace("- **Final Concat (30s):** PENDING", "- **Final Concat (30s):** PASS (30s Silent H.264)")

        if qc_details:
            tech_status = "PASS" if qc_details.get("technical_pass") else "FAIL"
            ratio_status = "9:16 (Valid)" if qc_details.get("ratio_pass") else "Ratio Invalid"
            audio_status = "Stripped (Clean Silent)" if qc_details.get("audio_stripped") else "No Audio"
            vis_status = "PASS (Consistent Motion)" if qc_details.get("visual_pass") else "FAIL"

            content = content.replace("- **Teknik QC (FFprobe):** PENDING", f"- **Teknik QC (FFprobe):** {tech_status}")
            content = content.replace("- **En-Boy Oranı (9:16):** PENDING", f"- **En-Boy Oranı (9:16):** {ratio_status}")
            content = content.replace("- **Ses Kanalı Temizleme:** PENDING", f"- **Ses Kanalı Temizleme:** {audio_status}")
            content = content.replace("- **Görsel QC (Frame Variance):** PENDING", f"- **Görsel QC (Frame Variance):** {vis_status}")

        self._atomic_write(current_path, content)

        if current_path != dest_path:
            shutil.move(str(current_path), str(dest_path))
        return dest_path

    def move_to_rejected(self, reel_id: str, reason: str) -> Path:
        """Move note to 07_REJECTED folder upon failure."""
        current_path = self.find_note_file(reel_id)
        if not current_path:
            raise FileNotFoundError(f"Note for {reel_id} not found.")

        dest_dir = self.vault_path / "07_REJECTED"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / f"{reel_id}.md"

        self.update_status(reel_id, "REJECTED")

        content = current_path.read_text(encoding="utf-8")
        content += f"\n\n# Rejection Reason\n\n- **Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n- **Reason:** {reason}\n"
        self._atomic_write(current_path, content)

        if current_path != dest_path:
            shutil.move(str(current_path), str(dest_path))
        return dest_path
