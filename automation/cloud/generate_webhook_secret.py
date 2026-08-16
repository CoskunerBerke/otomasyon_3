"""
Telegram Webhook Secret Generator.
Generates a cryptographically secure token for TELEGRAM_WEBHOOK_SECRET.
Does NOT modify files automatically.
"""
import secrets
import argparse


def generate_secret() -> str:
    """Generates a secure 32-byte URL-safe base64 string."""
    return secrets.token_urlsafe(32)


def main():
    parser = argparse.ArgumentParser(description="Generate cryptographically secure Telegram Webhook Secret")
    args = parser.parse_args()

    token = generate_secret()
    print("=" * 60)
    print("REELS AI FACTORY - TELEGRAM WEBHOOK SECRET GENERATOR")
    print("=" * 60)
    print("\nGenerated Secure Webhook Secret:")
    print(f"\n{token}\n")
    print("-" * 60)
    print("Kullanım:")
    print("1. Railway panelinde Cloud Control Plane Variables içine ekleyin:")
    print(f"   TELEGRAM_WEBHOOK_SECRET={token}")
    print("2. Yerel .env dosyanıza ekleyin:")
    print(f"   TELEGRAM_WEBHOOK_SECRET={token}")
    print("=" * 60)


if __name__ == "__main__":
    main()
