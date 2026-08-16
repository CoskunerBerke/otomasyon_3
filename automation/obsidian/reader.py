"""
Obsidian Vault reader for scanning past Reels, managing sequential IDs, and resuming incomplete Reels.
"""
import os
import re
import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import datetime

REEL_ID_PATTERN = re.compile(r'REEL-(\d{4})-(\d{4})', re.IGNORECASE)

class ObsidianReader:
    """Scans and parses notes in the Obsidian Vault."""

    SCAN_FOLDERS = [
        "03_SCRIPTS",
        "04_PRODUCTION",
        "05_READY",
        "06_PUBLISHED",
        "07_REJECTED",
        "01_TOPICS",
        "02_IDEAS"
    ]

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path).resolve()

    def parse_note_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Parse frontmatter and relaxed key-value pairs from a Markdown note.
        """
        meta: Dict[str, Any] = {
            "path": str(file_path),
            "filename": file_path.name,
            "id": None,
            "title": "",
            "category": "",
            "topic": "",
            "topic_key": "",
            "status": "UNKNOWN",
            "video_file": "",
            "prompt": ""
        }

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return meta

        # Try standard frontmatter YAML
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1]
                try:
                    parsed = yaml.safe_load(frontmatter_text)
                    if isinstance(parsed, dict):
                        for k, v in parsed.items():
                            meta[str(k).lower()] = v
                except Exception:
                    pass

        # Relaxed regex scanning for key fields if not found or malformed
        def extract_field(pattern: str, default: str = "") -> str:
            m = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
            return m.group(1).strip() if m else default

        if not meta.get("id"):
            meta["id"] = extract_field(r'(?:^|\n)#*\s*id\s*:\s*([^\n\r]+)')
        if not meta.get("title"):
            meta["title"] = extract_field(r'(?:^|\n)#*\s*title\s*:\s*([^\n\r]+)')
        if not meta.get("category"):
            meta["category"] = extract_field(r'(?:^|\n)#*\s*category\s*:\s*([^\n\r]+)')
        if not meta.get("topic"):
            meta["topic"] = extract_field(r'(?:^|\n)#*\s*topic\s*:\s*([^\n\r]+)')
        if not meta.get("topic_key"):
            meta["topic_key"] = extract_field(r'(?:^|\n)#*\s*topic_key\s*:\s*([^\n\r]+)')
        if meta.get("status") == "UNKNOWN" or not meta.get("status"):
            status_val = extract_field(r'(?:^|\n)#*\s*status\s*:\s*([^\n\r]+)')
            if status_val:
                meta["status"] = status_val
        if not meta.get("video_file"):
            meta["video_file"] = extract_field(r'(?:^|\n)#*\s*video_file\s*:\s*([^\n\r]+)')

        # Parse new pipeline metadata
        if "content_mode" not in meta:
            meta["content_mode"] = extract_field(r'(?:^|\n)#*\s*content_mode\s*:\s*([^\n\r]+)')
        if "pipeline_version" not in meta:
            p_ver = extract_field(r'(?:^|\n)#*\s*pipeline_version\s*:\s*([^\n\r]+)')
            meta["pipeline_version"] = int(p_ver) if p_ver and p_ver.isdigit() else 1
        if "legacy" not in meta:
            leg_val = extract_field(r'(?:^|\n)#*\s*legacy\s*:\s*([^\n\r]+)')
            meta["legacy"] = True if leg_val and leg_val.lower() == "true" else False
        if "resume_allowed" not in meta:
            res_val = extract_field(r'(?:^|\n)#*\s*resume_allowed\s*:\s*([^\n\r]+)')
            meta["resume_allowed"] = False if res_val and res_val.lower() == "false" else True
        if "retry_allowed" not in meta:
            ret_val = extract_field(r'(?:^|\n)#*\s*retry_allowed\s*:\s*([^\n\r]+)')
            meta["retry_allowed"] = True if ret_val and ret_val.lower() == "true" else False
        if "flow_project_url" not in meta:
            meta["flow_project_url"] = extract_field(r'(?:^|\n)#*\s*flow_project_url\s*:\s*([^\n\r]+)')
        if "prompt_hash" not in meta:
            meta["prompt_hash"] = extract_field(r'(?:^|\n)#*\s*prompt_hash\s*:\s*([^\n\r]+)')
        if "resume_from" not in meta:
            meta["resume_from"] = extract_field(r'(?:^|\n)#*\s*resume_from\s*:\s*([^\n\r]+)')
        if "final_duration_seconds" not in meta:
            fds = extract_field(r'(?:^|\n)#*\s*final_duration_seconds\s*:\s*([^\n\r]+)')
            meta["final_duration_seconds"] = int(fds) if fds and fds.isdigit() else 30
        if "segment_count" not in meta:
            sc = extract_field(r'(?:^|\n)#*\s*segment_count\s*:\s*([^\n\r]+)')
            meta["segment_count"] = int(sc) if sc and sc.isdigit() else 3
        if "segment_duration_seconds" not in meta:
            sds = extract_field(r'(?:^|\n)#*\s*segment_duration_seconds\s*:\s*([^\n\r]+)')
            meta["segment_duration_seconds"] = int(sds) if sds and sds.isdigit() else 10
        if "segments_completed" not in meta:
            scomp = extract_field(r'(?:^|\n)#*\s*segments_completed\s*:\s*([^\n\r]+)')
            meta["segments_completed"] = int(scomp) if scomp and scomp.isdigit() else 0

        # Extract prompt block
        prompt_match = re.search(r'# Prompt\s*```(?:text)?\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
        if prompt_match:
            meta["prompt"] = prompt_match.group(1).strip()

        # Extract segment prompts if present
        meta["segment_prompts"] = {}
        for seg_m in re.finditer(r'## Segment (\d+).*?```(?:text)?\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE):
            s_idx = int(seg_m.group(1))
            meta["segment_prompts"][s_idx] = seg_m.group(2).strip()

        # Also extract ID from filename if present
        if not meta["id"]:
            fn_match = REEL_ID_PATTERN.search(file_path.name)
            if fn_match:
                meta["id"] = f"REEL-{fn_match.group(1)}-{fn_match.group(2)}"

        return meta

    def get_all_reels(self) -> List[Dict[str, Any]]:
        """Scan all relevant folders in the vault and return parsed records."""
        reels: List[Dict[str, Any]] = []
        if not self.vault_path.exists():
            return reels

        for folder_name in self.SCAN_FOLDERS:
            folder_path = self.vault_path / folder_name
            if folder_path.exists() and folder_path.is_dir():
                for file_path in folder_path.glob("*.md"):
                    meta = self.parse_note_metadata(file_path)
                    reels.append(meta)

        return reels

    def get_completed_reels(self) -> List[Dict[str, Any]]:
        """Return only successfully completed or published reels for history analysis."""
        completed: List[Dict[str, Any]] = []
        for r in self.get_all_reels():
            status = str(r.get("status", "")).upper()
            video_file = str(r.get("video_file", "")).strip()
            if status in ["READY", "PUBLISHED", "APPROVED"]:
                completed.append(r)
            elif video_file and Path(video_file).exists():
                completed.append(r)
        return completed

    def get_past_visual_history(self) -> List[Dict[str, Any]]:
        """
        Return all visual transformation reels (completed, published, legacy silent visual)
        to prevent duplicate topics and ensure maximum diversity.
        """
        visual_history: List[Dict[str, Any]] = []
        for r in self.get_all_reels():
            c_mode = str(r.get("content_mode", ""))
            status = str(r.get("status", "")).upper()
            if c_mode in ["silent_global_visual", "silent_global_step_by_step"] or status in ["READY", "PUBLISHED", "APPROVED"]:
                visual_history.append(r)
        return visual_history

    def get_incomplete_reels(self) -> List[Dict[str, Any]]:
        """
        Return existing reels that were initiated under pipeline v2 or v3 (silent visual)
        and are eligible for resumption.
        Strictly excludes legacy notes, spoken information videos, and 07_REJECTED (unless retry_allowed=True).
        """
        incomplete: List[Dict[str, Any]] = []
        for folder_name in ["03_SCRIPTS", "04_PRODUCTION", "07_REJECTED"]:
            fdir = self.vault_path / folder_name
            if not fdir.exists() or not fdir.is_dir():
                continue

            for fpath in fdir.glob("*.md"):
                meta = self.parse_note_metadata(fpath)
                status = str(meta.get("status", "")).upper()
                video_file = str(meta.get("video_file", "")).strip()

                # Rule 1: Exclude legacy notes and explicit non-resumables
                if meta.get("legacy") is True or meta.get("resume_allowed") is False:
                    continue
                if meta.get("content_mode") in ["legacy_information", "legacy_manual"]:
                    continue

                # Rule 2: 07_REJECTED is excluded unless explicit retry_allowed: true
                if folder_name == "07_REJECTED" and not meta.get("retry_allowed"):
                    continue

                # Rule 3: Exclude finished or archived statuses
                if status in ["READY", "PUBLISHED", "REJECTED", "LEGACY", "ARCHIVED"]:
                    continue

                # Rule 4: Must have pipeline_version >= 2 and silent visual content mode
                p_ver = int(meta.get("pipeline_version", 1))
                c_mode = str(meta.get("content_mode", ""))
                if p_ver < 2 or c_mode not in ["silent_global_visual", "silent_global_step_by_step"]:
                    continue

                # Rule 5: Resumable status check
                if status in ["PROMPT_READY", "FLOW_SUBMITTING", "MEDIA_GENERATING", "MEDIA_READY", "DOWNLOADING", "FAILED_TECHNICAL", "FAILED_TECHNICAL_DOWNLOAD", "GENERATING"]:
                    if not video_file or not Path(video_file).exists():
                        incomplete.append(meta)

        # Sort by reel ID descending (highest / most recent ID first)
        def get_id_sort_key(m: dict) -> Tuple[int, int]:
            r_id = str(m.get("id") or "")
            match = REEL_ID_PATTERN.search(r_id)
            if match:
                return (int(match.group(1)), int(match.group(2)))
            return (0, 0)

        incomplete.sort(key=get_id_sort_key, reverse=True)
        return incomplete

    def get_next_reel_id(self, year: Optional[int] = None) -> str:
        """
        Scan all notes in the vault, find highest existing ID number,
        and generate next consecutive ID: REEL-YYYY-NNNN.
        """
        current_year = year or datetime.datetime.now().year
        max_num = 0

        for r in self.get_all_reels():
            reel_id = str(r.get("id") or "")
            match = REEL_ID_PATTERN.search(reel_id)
            if match:
                r_year = int(match.group(1))
                r_num = int(match.group(2))
                if r_year == current_year:
                    if r_num > max_num:
                        max_num = r_num
                elif r_num > max_num:
                    max_num = r_num

        next_num = max_num + 1
        return f"REEL-{current_year}-{next_num:04d}"
