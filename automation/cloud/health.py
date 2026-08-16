"""
Health and Status Diagnostics Endpoint for Cloud Control Plane.
Exposes sanitized system diagnostics for Railway health checks and monitoring.
Strictly ensures no secrets or sensitive tokens are exposed.
"""
import datetime
from zoneinfo import ZoneInfo
from typing import Dict, Any

from .config import CloudConfig
from .database import Database


def get_health_status(config: CloudConfig, db: Database) -> Dict[str, Any]:
    """Generates sanitized system health dictionary."""
    utc_now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    try:
        tz = ZoneInfo(config.timezone_str)
        local_now = datetime.datetime.now(tz).strftime(f"%Y-%m-%d %H:%M:%S {config.timezone_str}")
    except Exception:
        local_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S Local")

    db_status = "CONNECTED"
    try:
        with db.get_connection():
            pass
    except ValueError as ve:
        if "PRODUCTION_DATABASE_INVALID" in str(ve):
            db_status = "PRODUCTION_DATABASE_INVALID"
        else:
            db_status = "ERROR"
    except Exception:
        db_status = "ERROR"

    latest_hb = None
    try:
        latest_hb = db.get_latest_heartbeat()
    except Exception:
        pass

    worker_online = False
    if latest_hb:
        try:
            hb_dt = datetime.datetime.strptime(latest_hb.last_seen_at, "%Y-%m-%d %H:%M:%S")
            worker_online = (datetime.datetime.now() - hb_dt).total_seconds() < 180
        except Exception:
            pass

    storage_ok = config.is_storage_configured

    # Health status calculation
    if db_status == "CONNECTED" and storage_ok:
        overall_status = "HEALTHY"
    elif db_status == "CONNECTED" and not storage_ok:
        overall_status = "DEGRADED"
    else:
        overall_status = "UNHEALTHY"

    return {
        "status": overall_status,
        "database": db_status,
        "scheduler": "ENABLED" if config.enable_weekly_scheduler else "DISABLED",
        "telegram_configured": config.is_telegram_configured,
        "instagram_worker": "ENABLED" if config.enable_instagram_worker else "DISABLED",
        "storage_configured": storage_ok,
        "local_worker_online": worker_online,
        "media_storage_backend": config.media_storage_backend,
        "timezone": config.timezone_str,
        "current_time_utc": utc_now,
        "current_time_istanbul": local_now
    }
