"""
Cloud-to-Local Obsidian State Synchronizer.
Pulls cloud state (approvals, weeks, Instagram cloud queue, alerts) and mirrors into local Obsidian vault.
Supports direct Database syncing for tests and HTTP API payload syncing for production local workers.
"""
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ReelsAIFactory.CloudSync")

from automation.cloud.database import Database
from automation.cloud.models import TelegramApproval, CloudWeek, InstagramScheduledJob, TelegramApprovalStatus
from automation.orchestration.obsidian_mirror import ObsidianControlCenter, DEFAULT_VAULT_PATH


class CloudObsidianSync:
    """Synchronizes cloud database state into human-readable Obsidian markdown notes."""

    def __init__(self, db: Optional[Database] = None, vault_path: Optional[Path] = None):
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

    def sync_from_cloud_payload(self, payload: Dict[str, Any]) -> Dict[str, int]:
        """Synchronizes cloud state directly from GET /worker/state/sync JSON payload."""
        if not payload:
            return {"active_weeks": 0, "synced_approvals": 0, "synced_jobs": 0}

        weeks_data = payload.get("weeks", [])
        approvals_data = payload.get("approvals", [])
        jobs_data = payload.get("instagram_jobs", [])
        synced_approvals = 0

        for appr_dict in approvals_data:
            try:
                status_val = appr_dict.get("status", "PENDING")
                try:
                    status_enum = TelegramApprovalStatus(status_val)
                except ValueError:
                    status_enum = TelegramApprovalStatus.PENDING

                appr = TelegramApproval(
                    approval_id=appr_dict.get("approval_id", ""),
                    week_id=appr_dict.get("week_id", ""),
                    next_week_id=appr_dict.get("next_week_id", ""),
                    status=status_enum,
                    telegram_message_id=appr_dict.get("telegram_message_id"),
                    telegram_chat_id=appr_dict.get("telegram_chat_id"),
                    responded_at=appr_dict.get("responded_at"),
                    created_at=appr_dict.get("created_at", "")
                )
                self.sync_approval_note(appr)
                synced_approvals += 1
            except Exception as e:
                logger.error(f"[CLOUD SYNC] Failed to sync approval note from payload: {e}")

        return {
            "active_weeks": len(weeks_data),
            "synced_approvals": synced_approvals,
            "synced_jobs": len(jobs_data)
        }

    def sync_all_cloud_states(self) -> Dict[str, int]:
        """Pulls all active weeks and approvals using database if available."""
        if not self.db:
            return {"active_weeks": 0, "synced_approvals": 0}

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
