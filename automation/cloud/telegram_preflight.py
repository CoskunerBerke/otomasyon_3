"""
Telegram Preflight Verification Runner.
Validates bot credentials, authorization gates, database, and approval schedule.
"""
import sys
import logging
from pathlib import Path
from typing import Dict, Any, Tuple, List

logger = logging.getLogger("ReelsAIFactory.TelegramPreflight")

from .config import CloudConfig
from .database import Database
from .telegram_bot import TelegramBotClient


def run_telegram_preflight() -> Tuple[bool, str, List[str]]:
    """
    Executes 8 preflight checks for Telegram bot readiness.
    """
    config = CloudConfig()
    errors = []

    print("=" * 60)
    print("REELS AI FACTORY - TELEGRAM APPROVAL BOT PREFLIGHT")
    print("=" * 60)
    print(f"Bot Token Status : {config.masked_bot_token}")
    print(f"Allowed User ID  : {config.telegram_allowed_user_id or '<NOT_SET>'}")
    print(f"Chat ID          : {config.telegram_chat_id or '<NOT_SET>'}")
    print(f"Approval Time    : {config.weekly_approval_local_time or '<NEEDS_USER_APPROVAL_TIME>'}")
    print(f"Timezone         : {config.timezone_str}")
    print("=" * 60 + "\n")

    # 1. Check Bot Token
    if not config.telegram_bot_token:
        errors.append("[FAIL 1/8] TELEGRAM_BOT_TOKEN missing in .env")
    else:
        print("[PASS 1/8] TELEGRAM_BOT_TOKEN configured.")

    # 2. Test getMe
    bot = TelegramBotClient(config.telegram_bot_token)
    ok_me, bot_data, me_err = bot.get_me()
    if not ok_me:
        errors.append(f"[FAIL 2/8] Telegram getMe failed: {me_err}")
    else:
        print(f"[PASS 2/8] Telegram getMe OK: @{bot_data.get('username')}")

    # 3. Check Allowed User ID
    if not config.telegram_allowed_user_id:
        errors.append("[FAIL 3/8] TELEGRAM_ALLOWED_USER_ID missing in .env")
    else:
        print(f"[PASS 3/8] TELEGRAM_ALLOWED_USER_ID verified: {config.telegram_allowed_user_id}")

    # 4. Check Chat ID
    if not config.telegram_chat_id:
        errors.append("[FAIL 4/8] TELEGRAM_CHAT_ID missing in .env")
    else:
        print(f"[PASS 4/8] TELEGRAM_CHAT_ID verified: {config.telegram_chat_id}")

    # 5. Check Webhook Secret
    if not config.telegram_webhook_secret:
        print("[WARN 5/8] TELEGRAM_WEBHOOK_SECRET not set (recommended for webhook security).")
    else:
        print("[PASS 5/8] TELEGRAM_WEBHOOK_SECRET configured.")

    # 6. Check Approval Local Time
    if not config.weekly_approval_local_time:
        errors.append("[FAIL 6/8] WEEKLY_APPROVAL_LOCAL_TIME missing (e.g. '12:00', '18:00', '20:00').")
    else:
        print(f"[PASS 6/8] WEEKLY_APPROVAL_LOCAL_TIME configured: {config.weekly_approval_local_time}")

    # 7. Check Database Connection
    try:
        db = Database(config.database_url)
        print(f"[PASS 7/8] Cloud database connected ({db.database_url.split('@')[-1]}).")
    except Exception as e:
        errors.append(f"[FAIL 7/8] Database connection failed: {e}")

    # 8. Check Public Base URL
    if not config.public_base_url:
        print("[INFO 8/8] PUBLIC_BASE_URL not set (required when deploying cloud webhook).")
    else:
        print(f"[PASS 8/8] PUBLIC_BASE_URL configured: {config.public_base_url}")

    if errors:
        print("\n" + "=" * 60)
        print("STATUS: NEEDS_USER_TELEGRAM_SETUP")
        print("=" * 60)
        for err in errors:
            print(f"- {err}")
        print("\nKurulum için lütfen docs/TELEGRAM_SETUP.md kılavuzunu inceleyin.")
        print("=" * 60 + "\n")
        return False, "NEEDS_USER_TELEGRAM_SETUP", errors

    print("\n" + "=" * 60)
    print("STATUS: TELEGRAM_PREFLIGHT_PASS")
    print("=" * 60 + "\n")
    return True, "TELEGRAM_PREFLIGHT_PASS", []


def main():
    ok, status, _ = run_telegram_preflight()
    if ok:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
