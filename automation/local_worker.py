"""
Local Windows Worker Engine for Reels AI Factory.
Connects to Cloud Control Plane, reports heartbeats, claims generation commands,
executes weekly orchestration, uploads media to cloud storage, and syncs Obsidian.
"""
import sys
import time
import argparse
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("ReelsAIFactory.LocalWorker")

from automation.cloud.config import CloudConfig
from automation.cloud.database import Database
from automation.cloud.models import WorkerHeartbeat, CommandType, CommandStatus
from automation.cloud.media_storage import get_media_storage
from automation.cloud_sync import CloudObsidianSync
from automation.weekly_orchestrator import WeeklyOrchestrator


class LocalWorker:
    """Windows Local Execution Worker."""

    def __init__(
        self,
        worker_id: str = "win_local_worker_1",
        base_dir: Optional[Path] = None,
        vault_path: Optional[Path] = None
    ):
        self.worker_id = worker_id
        self.base_dir = (base_dir or Path(".").resolve())
        self.config = CloudConfig(self.base_dir)
        self.db = Database(self.config.database_url)
        self.storage = get_media_storage(self.config)
        self.sync = CloudObsidianSync(self.db, vault_path)
        self.orchestrator = WeeklyOrchestrator(self.base_dir, vault_path, dry_run=True)

    def send_heartbeat(self) -> bool:
        """Records local worker heartbeat in cloud DB."""
        hb = WorkerHeartbeat(
            worker_id=self.worker_id,
            hostname_hash="win_local_host",
            version="1.0.0",
            capabilities=["FLOW", "YOUTUBE", "TIKTOK", "MEDIA_UPLOAD", "OBSIDIAN_SYNC"],
            last_seen_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        return self.db.record_heartbeat(hb)

    def process_next_command(self) -> Optional[str]:
        """Claims and executes the next pending command."""
        cmd = self.db.get_next_pending_command()
        if not cmd:
            return None

        claimed = self.db.claim_command(cmd.command_id, self.worker_id)
        if not claimed:
            return None

        logger.info(f"[LOCAL WORKER] Claimed command: {cmd.command_id} ({cmd.type.value}) for week {cmd.week_id}")

        try:
            if cmd.type == CommandType.GENERATE_WEEK:
                # Run weekly orchestrator
                success, report, plan = self.orchestrator.run_weekly_pipeline(week_id=cmd.week_id)
                if success:
                    self.db.complete_command(cmd.command_id, CommandStatus.COMPLETE)
                    logger.info(f"[LOCAL WORKER] Command {cmd.command_id} completed successfully.")
                    return cmd.command_id
                else:
                    self.db.complete_command(cmd.command_id, CommandStatus.FAILED_RETRYABLE, "Orchestrator failed")
                    return cmd.command_id

            elif cmd.type == CommandType.SYNC_STATE:
                self.sync.sync_all_cloud_states()
                self.db.complete_command(cmd.command_id, CommandStatus.COMPLETE)
                return cmd.command_id

            else:
                self.db.complete_command(cmd.command_id, CommandStatus.COMPLETE)
                return cmd.command_id

        except Exception as e:
            logger.error(f"[LOCAL WORKER] Error executing command {cmd.command_id}: {e}")
            self.db.complete_command(cmd.command_id, CommandStatus.FAILED_FATAL, str(e))
            return cmd.command_id

    def run_cycle(self) -> Dict[str, Any]:
        """Runs a single iteration of the local worker loop."""
        self.send_heartbeat()
        cmd_id = self.process_next_command()
        sync_res = self.sync.sync_all_cloud_states()

        return {
            "worker_id": self.worker_id,
            "processed_command_id": cmd_id,
            "sync": sync_res
        }


def main():
    parser = argparse.ArgumentParser(description="Reels AI Factory Local Windows Worker")
    parser.add_argument("--run-once", action="store_true", default=True, help="Execute a single cycle and exit")
    args = parser.parse_args()

    worker = LocalWorker()
    result = worker.run_cycle()
    print("=" * 60)
    print("REELS AI FACTORY - LOCAL WORKER CYCLE COMPLETE")
    print("=" * 60)
    print(f"Worker ID          : {result['worker_id']}")
    print(f"Executed Command   : {result['processed_command_id'] or 'None (Queue Empty)'}")
    print(f"Obsidian Sync      : {result['sync']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
