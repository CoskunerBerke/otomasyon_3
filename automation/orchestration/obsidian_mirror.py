"""
Obsidian Control Center Synchronizer and State Mirror.
Generates human-readable Markdown notes in Obsidian Vault for weeks, reels, runs, and alerts.
"""
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ReelsAIFactory.ObsidianMirror")

from .models import (
    WeekPlan,
    PublishingSlot,
    ReelState,
    ReelPlatformStatus,
    RunReport
)


DEFAULT_VAULT_PATH = Path(r"C:\Users\berke\obsidian\Reels_AI_Studio")


class ObsidianControlCenter:
    """
    Manages structured Obsidian Markdown notes mirroring the execution state.
    """

    def __init__(self, vault_path: Optional[Path] = None):
        self.vault_path = (vault_path or DEFAULT_VAULT_PATH).resolve()
        self.system_dir = self.vault_path / "00_SYSTEM"
        self.weeks_dir = self.vault_path / "01_WEEKS"
        self.reels_dir = self.vault_path / "02_REELS"
        self.approvals_dir = self.vault_path / "03_APPROVALS"
        self.runs_dir = self.vault_path / "04_RUNS"
        self.alerts_dir = self.vault_path / "05_ALERTS"
        self.reports_dir = self.vault_path / "06_REPORTS"
        self._ensure_folders()

    def _ensure_folders(self) -> None:
        """Creates the required 7 folders if they do not exist."""
        for d in [
            self.system_dir,
            self.weeks_dir,
            self.reels_dir,
            self.approvals_dir,
            self.runs_dir,
            self.alerts_dir,
            self.reports_dir
        ]:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"[OBSIDIAN] Could not create folder {d}: {e}")

    def _write_note(self, target_file: Path, content: str) -> bool:
        """Writes note content atomically."""
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = target_file.with_suffix(".tmp")
            tmp_file.write_text(content, encoding="utf-8")
            tmp_file.replace(target_file)
            return True
        except Exception as e:
            logger.error(f"[OBSIDIAN] Error writing {target_file.name}: {e}")
            return False

    # =========================================================================
    # 1. WEEK NOTE (01_WEEKS/WEEK-YYYY-Wxx.md)
    # =========================================================================

    def sync_week_note(self, plan: WeekPlan) -> bool:
        """Generates or updates the 01_WEEKS/WEEK-xxxx.md note with frontmatter and table."""
        file_path = self.weeks_dir / f"WEEK-{plan.week_id}.md"

        frontmatter = [
            "---",
            f"week_id: {plan.week_id}",
            f"status: {plan.status}",
            f"timezone: {plan.timezone}",
            f"target_reels: {plan.target_reels}",
            f"slots_per_day: {plan.slots_per_day}",
            "slot_times:",
        ]
        for st in plan.slot_times:
            frontmatter.append(f'  - "{st}"')
        frontmatter.append("platforms:")
        for p in plan.platforms:
            frontmatter.append(f"  - {p}")
        frontmatter.extend([
            f"approved: {str(plan.approved).lower()}",
            f"start_date: {plan.start_date}",
            f"created_at: {plan.created_at}",
            f"updated_at: {plan.updated_at}",
            "---",
            "",
            f"# Weekly Plan: {plan.week_id}",
            f"**Start Date**: {plan.start_date} | **Timezone**: `{plan.timezone}` | **Status**: `{plan.status}`",
            "",
            "## 14-Slot Publishing Schedule",
            "",
            "| Slot | Reel ID | Date | Time | YouTube | TikTok | Instagram | QC |",
            "| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: |"
        ])

        for slot in plan.slots:
            reel_link = f"[[{slot.reel_id}]]" if slot.reel_id else "_Unassigned_"
            row = (
                f"| {slot.slot_index} "
                f"| {reel_link} "
                f"| {slot.date_str} "
                f"| {slot.time_str} "
                f"| `{slot.youtube_status}` "
                f"| `{slot.tiktok_status}` "
                f"| `{slot.instagram_status}` "
                f"| `{slot.qc_status}` |"
            )
            frontmatter.append(row)

        frontmatter.append("")
        return self._write_note(file_path, "\n".join(frontmatter))

    # =========================================================================
    # 2. REEL NOTE (02_REELS/REEL-YYYY-xxxx.md)
    # =========================================================================

    def sync_reel_note(self, reel: ReelState) -> bool:
        """Generates or updates the 02_REELS/REEL-xxxx.md note."""
        file_path = self.reels_dir / f"{reel.reel_id}.md"

        yt_status = reel.youtube_status.value if isinstance(reel.youtube_status, ReelPlatformStatus) else str(reel.youtube_status)
        tt_status = reel.tiktok_status.value if isinstance(reel.tiktok_status, ReelPlatformStatus) else str(reel.tiktok_status)
        ig_status = reel.instagram_status.value if isinstance(reel.instagram_status, ReelPlatformStatus) else str(reel.instagram_status)

        source = getattr(reel, "source", "legacy_unverified")
        quarantine_reason = getattr(reel, "quarantine_reason", None)

        frontmatter = [
            "---",
            f"reel_id: {reel.reel_id}",
            f"week_id: {reel.week_id or 'UNASSIGNED'}",
            f"pipeline_version: {reel.pipeline_version}",
            f"content_mode: {reel.content_mode}",
            f"scheduled_at_local: {reel.scheduled_at_local or 'null'}",
            f"generation_status: {reel.generation_status}",
            f"qc_status: {reel.qc_status}",
            f"source: {source}",
            f"quarantined: {str(bool(quarantine_reason)).lower()}",
            f"youtube_status: {yt_status}",
            f"youtube_remote_id: {reel.youtube_remote_id or 'null'}",
            f"tiktok_status: {tt_status}",
            f"tiktok_remote_id: {reel.tiktok_remote_id or 'null'}",
            f"instagram_status: {ig_status}",
            f"instagram_remote_media_id: {reel.instagram_remote_media_id or 'null'}",
            f"created_at: {reel.created_at}",
            f"updated_at: {reel.updated_at}",
            "---",
            "",
            f"# {reel.reel_id}: {reel.title or 'Untitled Reel'}",
            "",
        ]

        if quarantine_reason:
            frontmatter.extend([
                "> [!danger] QUARANTINED -- excluded from live inventory",
                f"> {quarantine_reason}",
                ""
            ])

        frontmatter.extend([
            "## Content Metadata",
            f"- **Source**: `{source}`" + (" ⚠️ NOT live-eligible" if source != "flow_live_generation" else " ✅ live-eligible"),
            f"- **Caption**: {reel.caption or 'N/A'}",
            f"- **Hashtags**: {' '.join(reel.hashtags) if reel.hashtags else 'N/A'}",
            f"- **Video Path**: `{reel.video_path or 'N/A'}`",
            f"- **SHA256**: `{reel.video_sha256 or 'N/A'}`",
            "",
            "## Publishing Status",
            f"- **YouTube**: `{yt_status}` (ID: `{reel.youtube_remote_id or 'None'}`)",
            f"- **TikTok**: `{tt_status}` (ID: `{reel.tiktok_remote_id or 'None'}`)",
            f"- **Instagram**: `{ig_status}` (Media ID: `{reel.instagram_remote_media_id or 'None'}`)",
            ""
        ])

        return self._write_note(file_path, "\n".join(frontmatter))

    # =========================================================================
    # 3. RUN REPORT NOTE (04_RUNS/RUN-YYYYMMDD-HHMMSS.md)
    # =========================================================================

    def sync_run_report(self, report: RunReport) -> bool:
        """Writes execution summary note to 04_RUNS/."""
        file_path = self.runs_dir / f"{report.run_id}.md"

        content = [
            "---",
            f"run_id: {report.run_id}",
            f"week_id: {report.week_id}",
            f"mode: {report.mode}",
            f"start_time: {report.start_time}",
            f"finish_time: {report.finish_time or 'N/A'}",
            f"duration_seconds: {report.duration_seconds:.2f}",
            f"inventory_found: {report.inventory_found}",
            f"generation_needed: {report.generation_needed}",
            f"qc_passed: {report.qc_passed}",
            f"youtube_success: {report.youtube_success}",
            f"tiktok_success: {report.tiktok_success}",
            f"instagram_queued: {report.instagram_queued}",
            "---",
            "",
            f"# Run Report: {report.run_id}",
            "",
            "## Summary",
            f"- **Mode**: `{report.mode}`",
            f"- **Week**: `[[WEEK-{report.week_id}]]`",
            f"- **Duration**: {report.duration_seconds:.2f}s",
            f"- **Inventory Found**: {report.inventory_found}",
            f"- **Generation Needed**: {report.generation_needed}",
            f"- **QC Passed**: {report.qc_passed}",
            f"- **YouTube Success**: {report.youtube_success}",
            f"- **TikTok Success**: {report.tiktok_success}",
            f"- **Instagram Queued**: {report.instagram_queued}",
            ""
        ]

        if report.errors:
            content.extend([
                "## Errors & Diagnostics",
                ""
            ])
            for err in report.errors:
                content.append(f"- ⚠️ {err}")
            content.append("")

        return self._write_note(file_path, "\n".join(content))

    # =========================================================================
    # 4. ALERT NOTE (05_ALERTS/ALERT-YYYYMMDD-PLATFORM-REEL.md)
    # =========================================================================

    def create_alert_note(
        self,
        platform: str,
        reel_id: str,
        status: str,
        message: str,
        action_required: str
    ) -> bool:
        """Creates an urgent alert note when a step requires user intervention (Rule 31 fail-safe)."""
        import datetime
        now_str = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        alert_id = f"ALERT-{now_str}-{platform.upper()}-{reel_id}"
        file_path = self.alerts_dir / f"{alert_id}.md"

        content = [
            "---",
            f"alert_id: {alert_id}",
            f"platform: {platform}",
            f"reel_id: {reel_id}",
            f"status: {status}",
            f"created_at: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "---",
            "",
            f"# Alert: {platform.upper()} Intervention Required ({reel_id})",
            "",
            f"**Status**: `{status}`",
            f"**Message**: {message}",
            "",
            "## Action Required",
            action_required,
            ""
        ]

        return self._write_note(file_path, "\n".join(content))
