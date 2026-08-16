"""
Local Windows Worker Engine for Reels AI Factory.
Communicates exclusively with Railway Cloud Control Plane via authenticated HTTP REST API.
Reports heartbeats, polls and executes generation commands, uploads media, and syncs Obsidian.
Provides safe --heartbeat-only diagnostic mode for zero-write, zero-generation verification.
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
from automation.cloud.media_storage import get_media_storage, MediaStorageInterface
from automation.cloud_sync import CloudObsidianSync
from automation.local_worker_cloud_client import LocalWorkerCloudClient
from automation.weekly_orchestrator import WeeklyOrchestrator


class LocalWorker:
    """Windows Local Execution Worker communicating via Railway Cloud API."""

    def __init__(
        self,
        worker_id: str = "win_local_worker_1",
        base_dir: Optional[Path] = None,
        vault_path: Optional[Path] = None,
        cloud_client: Optional[LocalWorkerCloudClient] = None
    ):
        self.worker_id = worker_id
        self.base_dir = (base_dir or Path(".").resolve())
        self.config = CloudConfig(self.base_dir)
        self.storage: MediaStorageInterface = get_media_storage(self.config)
        self.sync = CloudObsidianSync(vault_path=vault_path)

        if cloud_client is not None:
            self.client = cloud_client
        else:
            self.client = LocalWorkerCloudClient(
                public_base_url=self.config.public_base_url,
                api_key=self.config.local_worker_api_key,
                worker_id=self.worker_id
            )

        self.orchestrator = WeeklyOrchestrator(
            base_dir=self.base_dir,
            vault_path=vault_path,
            dry_run=False,
            cloud_client=self.client
        )

    def send_heartbeat(self, status: str = "IDLE") -> bool:
        """Sends worker heartbeat to Railway Cloud API."""
        ok, data, err = self.client.send_heartbeat(status=status)
        if ok:
            logger.info(f"[LOCAL WORKER] Heartbeat sent successfully to {self.config.public_base_url}")
            return True
        logger.warning(f"[LOCAL WORKER] Heartbeat failed: {err}")
        return False

    def process_next_command(self) -> Optional[str]:
        """Polls next claimed command from Railway Cloud API and executes locally."""
        ok, cmd, err = self.client.get_next_command()
        if not ok:
            logger.warning(f"[LOCAL WORKER] Failed to poll command: {err}")
            return None

        if not cmd:
            logger.info("[LOCAL WORKER] No pending commands in cloud queue.")
            return None

        cmd_id = cmd.get("command_id")
        cmd_type = cmd.get("type")
        week_id = cmd.get("week_id")

        logger.info(f"[LOCAL WORKER] Received cloud command: {cmd_id} ({cmd_type}) for week {week_id}")

        try:
            if cmd_type == "GENERATE_WEEK":
                # Execute weekly pipeline locally
                success, report, plan = self.orchestrator.run_weekly_pipeline(week_id=week_id)
                if success:
                    self.client.complete_command(cmd_id, status="COMPLETE")
                    logger.info(f"[LOCAL WORKER] Command {cmd_id} completed successfully.")
                    return cmd_id
                else:
                    self.client.complete_command(cmd_id, status="FAILED_RETRYABLE", error_message="Orchestrator failed")
                    return cmd_id

            elif cmd_type == "SYNC_STATE":
                self.sync_cloud_to_obsidian()
                self.client.complete_command(cmd_id, status="COMPLETE")
                return cmd_id

            else:
                self.client.complete_command(cmd_id, status="COMPLETE")
                return cmd_id

        except Exception as e:
            logger.error(f"[LOCAL WORKER] Unhandled error executing command {cmd_id}: {e}")
            self.client.complete_command(cmd_id, status="FAILED_FATAL", error_message=str(e))
            return cmd_id

    def sync_cloud_to_obsidian(self) -> Dict[str, Any]:
        """Pulls latest cloud state via HTTP and updates local Obsidian vault."""
        ok, payload, err = self.client.get_cloud_state()
        if ok and payload:
            return self.sync.sync_from_cloud_payload(payload)
        logger.warning(f"[LOCAL WORKER] Cloud sync skipped: {err}")
        return {"active_weeks": 0, "synced_approvals": 0, "synced_jobs": 0}

    def run_cycle(self) -> Dict[str, Any]:
        """Runs a single iteration: heartbeat -> command -> obsidian sync."""
        hb_ok = self.send_heartbeat()
        cmd_id = self.process_next_command()
        sync_res = self.sync_cloud_to_obsidian()

        return {
            "worker_id": self.worker_id,
            "heartbeat_ok": hb_ok,
            "processed_command_id": cmd_id,
            "sync": sync_res
        }


def run_heartbeat_only(worker: LocalWorker) -> bool:
    """Executes single safe heartbeat without claiming commands or running generation."""
    print("=" * 60)
    print("REELS AI FACTORY - LOCAL WORKER HEARTBEAT")
    print("=" * 60)
    print(f"Cloud URL      : {worker.config.public_base_url or '<NOT_SET>'}")
    print(f"Worker ID      : {worker.worker_id}")
    
    ok, data, err = worker.client.send_heartbeat(status="IDLE")
    if ok:
        print("Heartbeat      : ACKNOWLEDGED")
        print("=" * 60)
        return True
    else:
        print(f"Heartbeat      : FAILED ({err})")
        print("=" * 60)
        return False


def main():
    parser = argparse.ArgumentParser(description="Reels AI Factory - Local Windows Worker")
    parser.add_argument("--heartbeat-only", action="store_true", default=False, help="Send single heartbeat and exit immediately (zero writes/generation)")
    parser.add_argument("--run-once", action="store_true", default=False, help="Execute single worker cycle (heartbeat + next command + sync)")
    args = parser.parse_args()

    worker = LocalWorker()

    if args.heartbeat_only or (not args.run_once):
        # Default mode is safe heartbeat-only
        success = run_heartbeat_only(worker)
        sys.exit(0 if success else 1)

    if args.run_once:
        print("=" * 60)
        print("REELS AI FACTORY - LOCAL WORKER (RUN ONCE)")
        print("=" * 60)
        res = worker.run_cycle()
        print(f"Worker ID        : {res['worker_id']}")
        print(f"Heartbeat        : {'OK' if res['heartbeat_ok'] else 'FAILED'}")
        print(f"Executed Command : {res['processed_command_id'] or 'None (Queue Empty)'}")
        print(f"Obsidian Synced  : {res['sync']}")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    main()
