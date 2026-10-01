"""
Security and Authentication Utilities for Cloud Control Plane and Telegram Webhooks.
Prevents timing attacks, masks tokens, and verifies user/chat authorization.
"""
import hmac
import hashlib
import logging
from typing import Optional

logger = logging.getLogger("ReelsAIFactory.Security")


def mask_secret(secret: Optional[str], show_first: int = 4, show_last: int = 4) -> str:
    """Masks sensitive tokens and credentials."""
    if not secret:
        return "<EMPTY>"
    s = str(secret).strip()
    if len(s) <= (show_first + show_last):
        return "***"
    return f"{s[:show_first]}...{s[-show_last:]}"


def verify_webhook_secret(received_secret: Optional[str], expected_secret: Optional[str]) -> bool:
    """
    Constant-time comparison for Telegram Webhook secret token header (X-Telegram-Bot-Api-Secret-Token).
    """
    if not expected_secret or not received_secret:
        return False
    return hmac.compare_digest(str(received_secret).strip(), str(expected_secret).strip())


def verify_worker_api_key(received_key: Optional[str], expected_key: Optional[str]) -> bool:
    """
    Constant-time comparison for Local Worker API Key header (X-Worker-Api-Key).
    """
    if not expected_key or not received_key:
        return False
    return hmac.compare_digest(str(received_key).strip(), str(expected_key).strip())


def verify_telegram_user(user_id: Optional[int], allowed_user_id: Optional[int]) -> bool:
    """
    Ensures that a Telegram action or callback is strictly from the authorized user.
    Fails closed: with TELEGRAM_ALLOWED_USER_ID unset, no user is authorized.
    """
    if allowed_user_id is None:
        logger.warning("[SECURITY] TELEGRAM_ALLOWED_USER_ID is not set; rejecting Telegram user %s.", user_id)
        return False
    if user_id is None:
        return False
    return int(user_id) == int(allowed_user_id)


def verify_telegram_chat(chat_id: Optional[int], allowed_chat_id: Optional[int]) -> bool:
    """
    Ensures that a Telegram message originated from the authorized chat ID.
    Fails closed: with TELEGRAM_CHAT_ID unset, no chat is authorized.
    """
    if allowed_chat_id is None:
        logger.warning("[SECURITY] TELEGRAM_CHAT_ID is not set; rejecting Telegram chat %s.", chat_id)
        return False
    if chat_id is None:
        return True  # Update carries no chat (e.g. inline message); the user check is the gate
    return int(chat_id) == int(allowed_chat_id)


def compute_payload_hash(data: str) -> str:
    """Computes SHA256 hex digest for notification deduplication."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
