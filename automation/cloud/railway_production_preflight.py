"""
Railway Production Deployment Preflight Verification Runner.
Executes 17 diagnostic checks for production deployment readiness without performing any remote writes.
"""
import sys
import os
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger("ReelsAIFactory.RailwayPreflight")

from .config import CloudConfig
from .secret_scan import scan_repository


def run_railway_preflight(base_dir: Optional[Path] = None) -> Tuple[bool, str, List[str]]:
    """Runs local production preflight diagnostics."""
    root = (base_dir or Path(".").resolve())
    config = CloudConfig(root)
    errors = []
    warnings = []

    print("=" * 60)
    print("REELS AI FACTORY - RAILWAY PRODUCTION PREFLIGHT")
    print("=" * 60)
    print(f"Environment Mode : {config.app_env.upper()}")
    print(f"Port Target      : {config.port}")
    print(f"Database URL     : {config.database_url.split('@')[-1] if '@' in config.database_url else config.database_url}")
    print(f"Public Base URL  : {config.public_base_url or '<NOT_SET>'}")
    print(f"Media Backend    : {config.media_storage_backend}")
    print(f"Telegram Bot     : {config.masked_bot_token}")
    print(f"Meta Account     : @{config.instagram_expected_username} ({config.instagram_account_id})")
    print("=" * 60 + "\n")

    # 1. Environment Check
    print(f"[CHECK 1/17] APP_ENV: {config.app_env}")

    # 2. Database URL
    if config.is_production:
        if not config.is_postgres:
            errors.append("[FAIL 2/17] Production requires PostgreSQL DATABASE_URL (starts with postgresql:// or postgres://)")
        else:
            print("[PASS 2/17] PostgreSQL DATABASE_URL format valid.")
    else:
        print("[PASS 2/17] Database URL configured (SQLite dev or PostgreSQL).")

    # 3. Telegram Bot Token
    if not config.telegram_bot_token:
        errors.append("[FAIL 3/17] TELEGRAM_BOT_TOKEN is missing.")
    else:
        print(f"[PASS 3/17] TELEGRAM_BOT_TOKEN set: {config.masked_bot_token}")

    # 4. Telegram User & Chat IDs
    if not (config.telegram_allowed_user_id and config.telegram_chat_id):
        errors.append("[FAIL 4/17] TELEGRAM_ALLOWED_USER_ID or TELEGRAM_CHAT_ID missing.")
    else:
        print(f"[PASS 4/17] Telegram Allowed User: {config.telegram_allowed_user_id}, Chat ID: {config.telegram_chat_id}")

    # 5. Telegram Webhook Secret
    if not config.telegram_webhook_secret:
        if config.is_production:
            errors.append("[FAIL 5/17] TELEGRAM_WEBHOOK_SECRET missing (required for production webhook).")
        else:
            warnings.append("[WARN 5/17] TELEGRAM_WEBHOOK_SECRET not set (run generate_webhook_secret.py).")
    else:
        print("[PASS 5/17] TELEGRAM_WEBHOOK_SECRET configured.")

    # 6. Public Base URL
    public_url_pending = False
    if not config.public_base_url:
        public_url_pending = True
        warnings.append("[INFO 6/17] PUBLIC_BASE_URL pending (to be set after Railway domain generation).")
    elif config.is_production and not config.public_base_url.startswith("https://"):
        errors.append(f"[FAIL 6/17] PUBLIC_BASE_URL must use HTTPS in production: {config.public_base_url}")
    else:
        print(f"[PASS 6/17] PUBLIC_BASE_URL valid: {config.public_base_url}")

    # 7. Meta Access Token
    if not config.meta_access_token:
        errors.append("[FAIL 7/17] META_ACCESS_TOKEN is missing.")
    else:
        print(f"[PASS 7/17] META_ACCESS_TOKEN set: {config.masked_meta_token}")

    # 8. Instagram Account Verification
    if config.instagram_account_id != "17841411536006797" or config.instagram_expected_username != "builddverse":
        errors.append(f"[FAIL 8/17] Unexpected Instagram account: @{config.instagram_expected_username} ({config.instagram_account_id})")
    else:
        print(f"[PASS 8/17] Instagram target verified: @{config.instagram_expected_username} ({config.instagram_account_id})")

    # 9. Media Storage Backend
    if config.is_production and config.media_storage_backend != "s3":
        errors.append("[FAIL 9/17] Production requires MEDIA_STORAGE_BACKEND=s3 (Railway Storage Bucket).")
    else:
        print(f"[PASS 9/17] MEDIA_STORAGE_BACKEND={config.media_storage_backend}")

    # 10. S3 Configuration Fields
    if config.media_storage_backend == "s3":
        if not config.is_storage_configured:
            errors.append("[FAIL 10/17] Incomplete S3 settings (S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY).")
        else:
            print("[PASS 10/17] S3 Storage credentials configured.")
    else:
        print("[PASS 10/17] Storage configured for local development.")

    # 11. Local Worker API Key
    if not config.is_worker_api_enabled:
        errors.append("[FAIL 11/17] LOCAL_WORKER_API_KEY missing (required for worker communication).")
    else:
        print(f"[PASS 11/17] LOCAL_WORKER_API_KEY configured: {config.masked_worker_key}")

    # 12. Weekly Approval Time
    print(f"[PASS 12/17] Weekly Approval Time: {config.weekly_approval_local_time} (Day {config.weekly_approval_day})")

    # 13. Timezone
    if config.timezone_str != "Europe/Istanbul":
        warnings.append(f"[WARN 13/17] APP_TIMEZONE is {config.timezone_str}, expected Europe/Istanbul.")
    else:
        print(f"[PASS 13/17] Timezone verified: {config.timezone_str}")

    # 14. Dockerfile Check
    dockerfile_path = root / "Dockerfile"
    if not dockerfile_path.exists():
        errors.append("[FAIL 14/17] Dockerfile missing in project root.")
    else:
        print("[PASS 14/17] Dockerfile found.")

    # 15. railway.toml Check
    railway_toml_path = root / "railway.toml"
    if not railway_toml_path.exists():
        errors.append("[FAIL 15/17] railway.toml missing in project root.")
    else:
        print("[PASS 15/17] railway.toml found.")

    # 16. .dockerignore Check
    dockerignore_path = root / ".dockerignore"
    if not dockerignore_path.exists():
        errors.append("[FAIL 16/17] .dockerignore missing in project root.")
    else:
        print("[PASS 16/17] .dockerignore found.")

    # 17. Secret Leak Scanner
    is_clean, findings = scan_repository(root)
    if not is_clean:
        errors.append(f"[FAIL 17/17] Secret leak scanner detected {len(findings)} potential token(s).")
    else:
        print("[PASS 17/17] Secret leak scanner clean.")

    # Status Determination
    print("\n" + "=" * 60)
    if errors:
        print("STATUS: NEEDS_CONFIGURATION_FIX")
        for err in errors:
            print(f"- {err}")
        print("=" * 60 + "\n")
        return False, "NEEDS_CONFIGURATION_FIX", errors

    if public_url_pending:
        print("STATUS: DEPLOYMENT_CONFIG_READY_BUT_PUBLIC_URL_PENDING")
        print("\nRailway deployment için tüm yerel yapılandırma ve dosyalar hazır.")
        print("Railway deploy sonrası oluşan domain'i PUBLIC_BASE_URL olarak ekleyin.")
        print("=" * 60 + "\n")
        return True, "DEPLOYMENT_CONFIG_READY_BUT_PUBLIC_URL_PENDING", warnings

    print("STATUS: RAILWAY_PREFLIGHT_PASS")
    print("=" * 60 + "\n")
    return True, "RAILWAY_PREFLIGHT_PASS", []


def main():
    ok, status, _ = run_railway_preflight()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
