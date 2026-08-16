"""
Telegram Live Smoke Test Helper.
Sends a harmless verification message to the authorized chat ID to confirm real-time connectivity.
Requires explicit --send flag; default is DRY PLAN ONLY.
"""
import sys
import argparse
import logging
from typing import Optional

logger = logging.getLogger("ReelsAIFactory.TelegramSmokeTest")

from .config import CloudConfig
from .telegram_bot import TelegramBotClient


def run_smoke_test(send: bool = False, config: Optional[CloudConfig] = None) -> bool:
    """Executes Telegram smoke test with strict safety defaults."""
    cfg = config or CloudConfig()
    if not cfg.telegram_bot_token:
        print("ERROR: TELEGRAM_BOT_TOKEN is not set.")
        return False
    if not cfg.telegram_chat_id:
        print("ERROR: TELEGRAM_CHAT_ID is not set.")
        return False

    print("=" * 60)
    print("REELS AI FACTORY - TELEGRAM LIVE SMOKE TEST")
    print("=" * 60)
    print(f"Target Chat ID : {cfg.telegram_chat_id}")
    print(f"Bot Token      : {cfg.masked_bot_token}")
    print("=" * 60)

    if not send:
        print("\n[DRY-RUN] No messages sent to Telegram.")
        print("To execute live test, run with --send:")
        print("python -m automation.cloud.telegram_live_smoke_test --send\n")
        return True

    bot = TelegramBotClient(cfg.telegram_bot_token)
    test_msg = (
        "🤖 REELS AI FACTORY — BAĞLANTI TESTİ\n\n"
        "Cloud Control Plane Telegram bağlantısı başarıyla kuruldu.\n\n"
        "Durum: Çevrimiçi\n"
        "Zaman Dilimi: Europe/Istanbul"
    )
    test_keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Test Butonu (Etkisiz)", "callback_data": "smoke_test_click"}
            ]
        ]
    }

    print("\nSending live test message to Telegram...")
    ok, msg_id, err = bot.send_message(
        chat_id=cfg.telegram_chat_id,
        text=test_msg,
        reply_markup=test_keyboard
    )

    if ok:
        print(f"\n[SUCCESS] Smoke test message sent! (Message ID: {msg_id})")
        return True
    else:
        print(f"\n[FAILED] Could not send message: {err}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Telegram Live Smoke Test")
    parser.add_argument("--send", action="store_true", default=False, help="Explicitly send live test message")
    args = parser.parse_args()

    success = run_smoke_test(send=args.send)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
