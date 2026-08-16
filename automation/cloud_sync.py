"""
Cloud-to-Local Obsidian State Synchronizer.
Pulls cloud state (approvals, weeks, Instagram cloud queue, alerts) and mirrors into local Obsidian vault.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ReelsAIFactory.CloudSync")

from automation.cloud.database import Database
from automation.cloud.models import TelegramApproval, CloudWeek, InstagramScheduledJob
from automation.orchestration.obsidian_mirror import ObsidianControlCenter, DEFAULT_VAULT_PATH


class CloudObsidianSync:
    """Synchronizes cloud database state into human-readable Obsidian markdown notes."""

    def __init__(self, db: Database, vault_path: Optional[Path] = None):
        self.db = db
        self.obsidian = ObsidianControlCenter(vault_path or DEFAULT_VAULT_PATH)

    def sync_approval_note(self, approval: TelegramApproval) -> bool:
        """Generates or updates 03_APPROVALS/APPROVAL-WEEK-xxxx.md note."""
        file_path = self.obsidian.approvals_dir / f"APPROVAL-{approval.next_week_id}.md"

        content = [
            "---",
            f"approval_id: {approval.approval_id}",
            f"week_id: {approval.week_id}",
            f"next_week_id: {approval.next_week_id}",
            f"status: {approval.status.value}",
            f"source: telegram",
            f"telegram_message_id: {approval.telegram_message_id or 'null'}",
            f"telegram_chat_id: {approval.telegram_chat_id or 'null'}",
            f"responded_at: {approval.responded_at or 'null'}",
            f"created_at: {approval.created_at}",
            "---",
            "",
            f"# Telegram Approval: {approval.next_week_id}",
            "",
            f"- **Current Week**: `{approval.week_id}`",
            f"- **Next Week Target**: `{approval.next_week_id}`",
            f"- **Approval Status**: `{approval.status.value}`",
            f"- **Responded At**: `{approval.responded_at or 'Pending'}`",
            ""
        ]

        return self.obsidian._write_note(file_path, "\n".join(content))

    def sync_all_cloud_states(self) -> Dict[str, int]:
        """Pulls all active weeks, approvals, and jobs from cloud DB to mirror in Obsidian."""
        active_weeks = self.db.list_active_weeks()
        synced_approvals = 0

        for w in active_weeks:
            appr = self.db.get_pending_approval_for_week(w.week_id)
            if appr:
                self.sync_approval_note(appr)
                synced_approvals += 1

        return {
            "active_weeks": len(active_weeks),
            "synced_approvals": synced_approvals
        }
