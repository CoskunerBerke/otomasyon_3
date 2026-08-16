"""
Telegram Bot API Client for Cloud Control Plane.
Provides safe HTTP communication, secret masking, inline keyboards, and webhook management.
"""
import logging
import requests
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("ReelsAIFactory.TelegramBot")

from .security import mask_secret


class TelegramBotClient:
    """HTTP Client for interacting with the official Telegram Bot API."""

    def __init__(self, token: str, timeout: int = 15):
        self.token = token.strip()
        self.timeout = timeout
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.session = requests.Session()

    def _sanitize(self, text: str) -> str:
        """Removes the bot token from any error message or text string."""
        if self.token and self.token in text:
            return text.replace(self.token, mask_secret(self.token))
        return text

    def get_me(self) -> Tuple[bool, Dict[str, Any], Optional[str]]:
        """Tests the bot token and retrieves bot metadata."""
        if not self.token:
            return False, {}, "TOKEN_MISSING"
        try:
            resp = self.session.get(f"{self.base_url}/getMe", timeout=self.timeout)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, data.get("result", {}), None
            err = self._sanitize(data.get("description", resp.text))
            return False, {}, f"HTTP_{resp.status_code}: {err}"
        except Exception as e:
            return False, {}, f"EXCEPTION: {self._sanitize(str(e))}"

    def get_updates(self, offset: Optional[int] = None, limit: int = 100) -> Tuple[bool, List[Dict[str, Any]], Optional[str]]:
        """Fetches pending updates (used in setup/identity helper)."""
        if not self.token:
            return False, [], "TOKEN_MISSING"
        params: Dict[str, Any] = {"limit": limit}
        if offset is not None:
            params["offset"] = offset
        try:
            resp = self.session.get(f"{self.base_url}/getUpdates", params=params, timeout=self.timeout)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, data.get("result", []), None
            err = self._sanitize(data.get("description", resp.text))
            return False, [], f"HTTP_{resp.status_code}: {err}"
        except Exception as e:
            return False, [], f"EXCEPTION: {self._sanitize(str(e))}"

    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: Optional[str] = None
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Sends a text message with optional inline keyboard buttons."""
        if not self.token:
            return False, None, "TOKEN_MISSING"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            resp = self.session.post(f"{self.base_url}/sendMessage", json=payload, timeout=self.timeout)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                msg_id = data.get("result", {}).get("message_id")
                return True, msg_id, None
            err = self._sanitize(data.get("description", resp.text))
            logger.error(f"[TELEGRAM] Send message failed: {err}")
            return False, None, f"HTTP_{resp.status_code}: {err}"
        except Exception as e:
            err = self._sanitize(str(e))
            logger.error(f"[TELEGRAM] Send message exception: {err}")
            return False, None, f"EXCEPTION: {err}"

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Edits an existing message (e.g. after user clicks inline button)."""
        if not self.token:
            return False, "TOKEN_MISSING"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup

        try:
            resp = self.session.post(f"{self.base_url}/editMessageText", json=payload, timeout=self.timeout)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, None
            err = self._sanitize(data.get("description", resp.text))
            return False, f"HTTP_{resp.status_code}: {err}"
        except Exception as e:
            return False, f"EXCEPTION: {self._sanitize(str(e))}"

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> Tuple[bool, Optional[str]]:
        """Answers an incoming callback query to dismiss loading spinners."""
        if not self.token:
            return False, "TOKEN_MISSING"
        payload: Dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert
        }
        if text:
            payload["text"] = text

        try:
            resp = self.session.post(f"{self.base_url}/answerCallbackQuery", json=payload, timeout=self.timeout)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, None
            err = self._sanitize(data.get("description", resp.text))
            return False, f"HTTP_{resp.status_code}: {err}"
        except Exception as e:
            return False, f"EXCEPTION: {self._sanitize(str(e))}"

    def set_webhook(
        self,
        url: str,
        secret_token: Optional[str] = None,
        allowed_updates: Optional[List[str]] = None
    ) -> Tuple[bool, Optional[str]]:
        """Registers a webhook URL with Telegram."""
        if not self.token:
            return False, "TOKEN_MISSING"
        payload: Dict[str, Any] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        if allowed_updates:
            payload["allowed_updates"] = allowed_updates

        try:
            resp = self.session.post(f"{self.base_url}/setWebhook", json=payload, timeout=self.timeout)
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, None
            err = self._sanitize(data.get("description", resp.text))
            return False, f"HTTP_{resp.status_code}: {err}"
        except Exception as e:
            return False, f"EXCEPTION: {self._sanitize(str(e))}"

    def delete_webhook(self, drop_pending_updates: bool = False) -> Tuple[bool, Optional[str]]:
        """Removes webhook configuration."""
        if not self.token:
            return False, "TOKEN_MISSING"
        try:
            resp = self.session.post(
                f"{self.base_url}/deleteWebhook",
                json={"drop_pending_updates": drop_pending_updates},
                timeout=self.timeout
            )
            data = resp.json()
            if resp.status_code == 200 and data.get("ok"):
                return True, None
            err = self._sanitize(data.get("description", resp.text))
            return False, f"HTTP_{resp.status_code}: {err}"
        except Exception as e:
            return False, f"EXCEPTION: {self._sanitize(str(e))}"
