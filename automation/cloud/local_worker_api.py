"""
REST Handlers for Local Windows Worker Communication with Cloud Control Plane.
Protects endpoints with Worker API Key authentication.
"""
import json
import logging
import datetime
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("ReelsAIFactory.LocalWorkerAPI")

from .config import CloudConfig
from .database import Database
from .models import (
    WorkerHeartbeat,
    LocalWorkerCommand,
    CommandStatus
)
from .security import verify_worker_api_key


def _authenticate_worker(headers: Dict[str, str], config: CloudConfig) -> Tuple[bool, Optional[str]]:
    """Verifies X-Worker-Api-Key header."""
    if not config.is_worker_api_enabled:
        return False, "WORKER_API_DISABLED"
    received_key = (
        headers.get("X-Worker-Api-Key") or
        headers.get("x-worker-api-key") or
        headers.get("HTTP_X_WORKER_API_KEY")
    )
    if verify_worker_api_key(received_key, config.local_worker_api_key):
        return True, None
    return False, "UNAUTHORIZED_WORKER_KEY"


def handle_worker_heartbeat(
    headers: Dict[str, str],
    payload: Dict[str, Any],
    config: CloudConfig,
    db: Database
) -> Tuple[int, Dict[str, Any]]:
    """Handles POST /worker/heartbeat."""
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    worker_id = payload.get("worker_id", "local_win_worker")
    hostname_hash = payload.get("hostname_hash", "win_hash")
    version = payload.get("version", "1.0.0")
    capabilities = payload.get("capabilities", ["FLOW", "YOUTUBE", "TIKTOK", "MEDIA_UPLOAD", "OBSIDIAN_SYNC"])

    hb = WorkerHeartbeat(
        worker_id=worker_id,
        hostname_hash=hostname_hash,
        version=version,
        capabilities=capabilities,
        last_seen_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.record_heartbeat(hb)
    return 200, {"ok": True, "status": "HEARTBEAT_ACKNOWLEDGED"}


def handle_get_next_command(
    headers: Dict[str, str],
    worker_id: str,
    config: CloudConfig,
    db: Database
) -> Tuple[int, Dict[str, Any]]:
    """Handles GET /worker/commands/next (Atomically claims next pending command)."""
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    cmd = db.get_next_pending_command()
    if not cmd:
        return 200, {"ok": True, "command": None}

    # Atomically claim
    claimed = db.claim_command(cmd.command_id, worker_id)
    if claimed:
        cmd.status = CommandStatus.CLAIMED
        cmd.claimed_by = worker_id
        logger.info(f"[WORKER API] Command {cmd.command_id} ({cmd.type.value}) claimed by {worker_id}")
        return 200, {"ok": True, "command": cmd.to_dict()}

    return 200, {"ok": True, "command": None}


def handle_complete_command(
    headers: Dict[str, str],
    command_id: str,
    payload: Dict[str, Any],
    config: CloudConfig,
    db: Database
) -> Tuple[int, Dict[str, Any]]:
    """Handles POST /worker/commands/{command_id}/complete."""
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    status_str = payload.get("status", "COMPLETE")
    error_msg = payload.get("error_message")

    try:
        status_enum = CommandStatus(status_str)
    except ValueError:
        status_enum = CommandStatus.COMPLETE

    ok = db.complete_command(command_id, status_enum, error_msg)
    if ok:
        logger.info(f"[WORKER API] Command {command_id} marked as {status_str}")
        return 200, {"ok": True, "command_id": command_id, "status": status_str}

    return 404, {"ok": False, "error": "COMMAND_NOT_FOUND"}


def handle_sync_cloud_state(
    headers: Dict[str, str],
    config: CloudConfig,
    db: Database
) -> Tuple[int, Dict[str, Any]]:
    """Handles GET /worker/state/sync to mirror cloud data into local Obsidian vault."""
    auth_ok, auth_err = _authenticate_worker(headers, config)
    if not auth_ok:
        return 401, {"ok": False, "error": auth_err}

    active_weeks = db.list_active_weeks()
    all_weeks_data = [w.to_dict() for w in active_weeks]

    # Collect approvals and Instagram jobs for active weeks
    approvals_data = []
    ig_jobs_data = []
    for w in active_weeks:
        appr = db.get_pending_approval_for_week(w.week_id)
        if appr:
            approvals_data.append(appr.to_dict())
        jobs = db.list_instagram_jobs_for_week(w.week_id)
        ig_jobs_data.extend([j.to_dict() for j in jobs])

    return 200, {
        "ok": True,
        "weeks": all_weeks_data,
        "approvals": approvals_data,
        "instagram_jobs": ig_jobs_data
    }
