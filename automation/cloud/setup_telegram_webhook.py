"""
Telegram Webhook Setup Script.
Registers or deletes the webhook URL with Telegram. Requires explicit --apply flag.
"""
import sys
import argparse
import logging
from typing import Optional

logger = logging.getLogger("ReelsAIFactory.WebhookSetup")

from .config import CloudConfig
from .telegram_bot import TelegramBotClient


def setup_webhook(apply_changes: bool = False, delete: bool = False) -> bool:
    """Configures Telegram webhook with safety flags."""
    config = CloudConfig()
    if not config.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set.")
        return False

    bot = TelegramBotClient(config.telegram_bot_token)

    if delete:
        print("=" * 60)
        print("TELEGRAM WEBHOOK REMOVAL")
        print("=" * 60)
        if not apply_changes:
            print("DRY-RUN: Would delete Telegram webhook.")
            print("Run with --apply to execute.")
            return True
        ok, err = bot.delete_webhook(drop_pending_updates=False)
        if ok:
            print("[SUCCESS] Telegram webhook removed.")
            return True
        print(f"[FAILED] Could not remove webhook: {err}")
        return False

    if not config.public_base_url:
        print("ERROR: PUBLIC_BASE_URL is not set in .env")
        return False

    target_url = f"{config.public_base_url}/telegram/webhook"
    print("=" * 60)
    print("TELEGRAM WEBHOOK REGISTRATION")
    print("=" * 60)
    print(f"Target Webhook URL : {target_url}")
    print(f"Secret Token Set   : {bool(config.telegram_webhook_secret)}")
    print(f"Allowed Updates    : ['message', 'callback_query']")
    print("=" * 60)

    if not apply_changes:
        print("\n[DRY-RUN] No changes applied.")
        print("To register webhook, run: python -m automation.cloud.setup_telegram_webhook --apply\n")
        return True

    ok, err = bot.set_webhook(
        url=target_url,
        secret_token=config.telegram_webhook_secret or None,
        allowed_updates=["message", "callback_query"]
    )
    if ok:
        print("\n[SUCCESS] Webhook successfully registered with Telegram!")
        return True
    else:
        print(f"\n[FAILED] Webhook registration failed: {err}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Telegram Webhook Setup")
    parser.add_argument("--apply", action="store_true", default=False, help="Apply real webhook configuration")
    parser.add_argument("--delete", action="store_true", default=False, help="Delete existing webhook")

    args = parser.parse_args()
    success = setup_webhook(apply_changes=args.apply, delete=args.delete)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
