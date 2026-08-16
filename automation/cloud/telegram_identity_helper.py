"""
Telegram Identity Resolver Helper.
Reads recent /start messages from the Telegram bot to display User ID and Chat ID for .env setup.
"""
import sys
import logging
from pathlib import Path

logger = logging.getLogger("ReelsAIFactory.TelegramIdentityHelper")

from .config import CloudConfig
from .telegram_bot import TelegramBotClient


def resolve_telegram_identity() -> None:
    """Fetches recent updates to extract user ID and chat ID."""
    config = CloudConfig()
    if not config.telegram_bot_token:
        print("=" * 60)
        print("ERROR: TELEGRAM_BOT_TOKEN is not set in .env")
        print("Lütfen önce @BotFather'dan aldığınız token'ı .env dosyasına ekleyin.")
        print("=" * 60)
        sys.exit(1)

    bot = TelegramBotClient(config.telegram_bot_token)
    print("=" * 60)
    print("REELS AI FACTORY - TELEGRAM IDENTITY RESOLVER")
    print("=" * 60)
    print(f"Bot Token Status : LOADED ({config.masked_bot_token})")
    print("Querying Telegram getMe...")

    ok, bot_info, err = bot.get_me()
    if not ok:
        print(f"\n[FAIL] getMe failed: {err}")
        print("Lütfen bot token'ınızın doğruluğunu kontrol edin.")
        sys.exit(1)

    print(f"[OK] Connected to bot: @{bot_info.get('username')} ({bot_info.get('first_name')})\n")
    print("Fetching recent updates from bot (getUpdates)...")

    ok_up, updates, up_err = bot.get_updates(limit=10)
    if not ok_up:
        print(f"[WARNING] getUpdates error: {up_err}")
        if "webhook" in str(up_err).lower():
            print("Webhook aktif olduğu için getUpdates çalışmayabilir.")
        sys.exit(1)

    if not updates:
        print("\n[INFO] Henüz botunuza gönderilmiş bir mesaj bulunamadı.")
        print(f"Lütfen Telegram'da @{bot_info.get('username')} botunu açın ve '/start' mesajı gönderin.")
        print("Ardından bu scripti tekrar çalıştırın.\n")
        return

    print(f"[OK] Found {len(updates)} recent update(s):\n")
    found_users = set()
    for u in updates:
        msg = u.get("message") or u.get("callback_query", {}).get("message", {})
        from_user = msg.get("from") or u.get("callback_query", {}).get("from", {})
        chat = msg.get("chat", {})

        user_id = from_user.get("id")
        chat_id = chat.get("id")
        username = from_user.get("username", "N/A")
        first_name = from_user.get("first_name", "N/A")

        if user_id and user_id not in found_users:
            found_users.add(user_id)
            print("-" * 50)
            print(f"User Name  : {first_name} (@{username})")
            print(f"User ID    : {user_id}  --> TELEGRAM_ALLOWED_USER_ID={user_id}")
            print(f"Chat ID    : {chat_id}  --> TELEGRAM_CHAT_ID={chat_id}")
            print("-" * 50)

    print("\n.env dosyanıza yukarıdaki değerleri kopyalayabilirsiniz:")
    print("TELEGRAM_ALLOWED_USER_ID=<User_ID>")
    print("TELEGRAM_CHAT_ID=<Chat_ID>\n")


if __name__ == "__main__":
    resolve_telegram_identity()
