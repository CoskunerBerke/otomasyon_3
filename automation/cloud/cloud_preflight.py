"""
Cloud Control Plane Preflight Diagnostic Runner.
Verifies readiness of all cloud subsystem components before deployment.
"""
import sys
import logging
from typing import Dict, Any, Tuple, List

logger = logging.getLogger("ReelsAIFactory.CloudPreflight")

from .config import CloudConfig
from .database import Database
from .media_storage import get_media_storage


def run_cloud_preflight() -> Tuple[bool, List[str]]:
    """Runs diagnostics across database, Telegram, Meta, and storage."""
    config = CloudConfig()
    errors = []

    print("=" * 60)
    print("REELS AI FACTORY - CLOUD CONTROL PLANE PREFLIGHT")
    print("=" * 60)
    sanitized = config.to_sanitized_dict()
    for k, v in sanitized.items():
        print(f"{k.ljust(28)}: {v}")
    print("=" * 60 + "\n")

    # 1. Database Check
    try:
        db = Database(config.database_url)
        print("[PASS 1/5] Database connected and schema verified.")
    except Exception as e:
        errors.append(f"[FAIL 1/5] Database error: {e}")

    # 2. Media Storage Check
    try:
        storage = get_media_storage(config)
        print(f"[PASS 2/5] Media storage initialized ({config.media_storage_backend}).")
    except Exception as e:
        errors.append(f"[FAIL 2/5] Media storage error: {e}")

    # 3. Telegram Config Check
    if config.is_telegram_configured:
        print("[PASS 3/5] Telegram credentials configured.")
    else:
        print("[WARN 3/5] Telegram credentials incomplete (run TELEGRAM_PREFLIGHT.bat).")

    # 4. Meta Instagram Config Check
    if config.meta_access_token and config.instagram_account_id:
        print(f"[PASS 4/5] Meta credentials configured for @{config.instagram_expected_username}.")
    else:
        errors.append("[FAIL 4/5] Meta Graph API credentials missing.")

    # 5. Worker Key Check
    if config.local_worker_api_key:
        print("[PASS 5/5] Local worker API key configured.")
    else:
        errors.append("[FAIL 5/5] LOCAL_WORKER_API_KEY is empty.")

    if errors:
        print("\n[CLOUD PREFLIGHT FAILED]")
        for err in errors:
            print(f"- {err}")
        return False, errors

    print("\n[CLOUD PREFLIGHT SUCCESS] All subsystems ready.")
    return True, []


def main():
    ok, _ = run_cloud_preflight()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
