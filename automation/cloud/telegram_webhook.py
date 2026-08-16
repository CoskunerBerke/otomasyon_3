"""
Telegram Webhook Handler for Cloud Control Plane.
Validates secret token headers and dispatches callback queries to the approval service.
Enforces strict secret header requirement in production.
"""
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("ReelsAIFactory.TelegramWebhook")

from .config import CloudConfig
from .security import verify_webhook_secret
from .approval_service import ApprovalService


def handle_webhook_request(
    headers: Dict[str, str],
    update: Dict[str, Any],
    config: CloudConfig,
    approval_service: ApprovalService
) -> Tuple[int, Dict[str, Any]]:
    """
    Processes an incoming Telegram Webhook update.
    Returns (http_status_code, response_dict).
    """
    # 1. Production Webhook Secret Hard Gate
    if config.is_production and not config.telegram_webhook_secret:
        logger.error("[SECURITY] Webhook blocked: TELEGRAM_WEBHOOK_SECRET is required in production.")
        return 403, {"ok": False, "error": "TELEGRAM_WEBHOOK_SECRET_MISSING"}

    # 2. Webhook Secret Validation (if secret is configured)
    if config.telegram_webhook_secret:
        received_secret = (
            headers.get("X-Telegram-Bot-Api-Secret-Token") or
            headers.get("x-telegram-bot-api-secret-token") or
            headers.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN")
        )
        if not verify_webhook_secret(received_secret, config.telegram_webhook_secret):
            logger.warning("[SECURITY] Webhook rejected: Invalid or missing X-Telegram-Bot-Api-Secret-Token header.")
            return 403, {"ok": False, "error": "FORBIDDEN_INVALID_WEBHOOK_SECRET"}

    # 3. Dispatch Callback Query
    if "callback_query" in update:
        cq = update["callback_query"]
        result = approval_service.handle_callback_query(cq)
        return 200, {"ok": True, "result": result}

    # 4. Message handler (e.g. /start acknowledgment)
    if "message" in update:
        msg = update["message"]
        text = msg.get("text", "")
        if text.startswith("/start"):
            logger.info(f"[TELEGRAM] /start received from user {msg.get('from', {}).get('id')}")
            return 200, {"ok": True, "action": "START_ACK"}

    return 200, {"ok": True, "action": "IGNORED_UPDATE"}
