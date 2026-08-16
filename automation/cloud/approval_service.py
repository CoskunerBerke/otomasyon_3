"""
Approval Service for Weekly Planning via Telegram Interactive Buttons.
Coordinates Day-6 approval requests, handles callbacks with strict authorization and idempotency.
"""
import uuid
import logging
import datetime
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("ReelsAIFactory.ApprovalService")

from .config import CloudConfig
from .database import Database
from .models import (
    CloudWeek,
    CloudWeekStatus,
    TelegramApproval,
    TelegramApprovalStatus,
    LocalWorkerCommand,
    CommandType,
    CommandStatus
)
from .telegram_bot import TelegramBotClient
from .security import verify_telegram_user, verify_telegram_chat


def format_approval_message(current_week_id: str, next_week_id: str) -> str:
    """Formats the official Day-6 Telegram interactive approval message."""
    return (
        "🤖 REELS AI FACTORY\n\n"
        "Bu haftanın sonuna yaklaşıyoruz.\n\n"
        f"Mevcut hafta:\n{current_week_id}\n\n"
        f"Yeni hafta:\n{next_week_id}\n\n"
        "Yeni 7 günlük içerik paketi:\n\n"
        "14 Reel\n"
        "7 gün\n"
        "19:30 / 22:00\n"
        "YouTube\n"
        "TikTok\n"
        "Instagram\n\n"
        "Yeni haftayı hazırlayalım mı?"
    )


def build_approval_inline_keyboard(approval_id: str) -> Dict[str, Any]:
    """Constructs Telegram inline keyboard markup with EVET / HAYIR buttons."""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ EVET", "callback_data": f"weekly_approve:{approval_id}"},
                {"text": "❌ HAYIR", "callback_data": f"weekly_reject:{approval_id}"}
            ]
        ]
    }


class ApprovalService:
    """Manages the lifecycle of Telegram approvals and response processing."""

    def __init__(self, config: CloudConfig, db: Database, bot: TelegramBotClient):
        self.config = config
        self.db = db
        self.bot = bot

    def create_and_send_approval(
        self,
        current_week_id: str,
        next_week_id: str,
        expires_hours: int = 48
    ) -> Tuple[bool, Optional[str]]:
        """
        Creates a new Telegram approval record and dispatches the interactive message.
        Guarantees no duplicate messages if an approval is already pending.
        """
        existing = self.db.get_pending_approval_for_week(current_week_id)
        if existing:
            logger.info(f"[APPROVAL] Pending approval {existing.approval_id} already exists for {current_week_id}.")
            return True, existing.approval_id

        if not self.config.telegram_chat_id:
            logger.error("[APPROVAL] Cannot send approval: TELEGRAM_CHAT_ID not configured.")
            return False, None

        approval_id = f"APPR-{uuid.uuid4().hex[:8].upper()}"
        now_dt = datetime.datetime.now()
        expires_at = (now_dt + datetime.timedelta(hours=expires_hours)).strftime("%Y-%m-%d %H:%M:%S")

        approval = TelegramApproval(
            approval_id=approval_id,
            week_id=current_week_id,
            next_week_id=next_week_id,
            status=TelegramApprovalStatus.PENDING,
            telegram_chat_id=self.config.telegram_chat_id,
            expires_at=expires_at
        )

        message_text = format_approval_message(current_week_id, next_week_id)
        keyboard = build_approval_inline_keyboard(approval_id)

        # Dispatch via Telegram Bot
        ok, msg_id, err = self.bot.send_message(
            chat_id=self.config.telegram_chat_id,
            text=message_text,
            reply_markup=keyboard
        )

        if not ok or not msg_id:
            logger.error(f"[APPROVAL] Failed to send Telegram message: {err}")
            return False, None

        approval.telegram_message_id = msg_id
        self.db.save_approval(approval)

        # Update current week approval status
        week = self.db.get_week(current_week_id)
        if week:
            week.approval_status = "SENT"
            week.approval_sent_at = now_dt.strftime("%Y-%m-%d %H:%M:%S")
            self.db.save_week(week)

        logger.info(f"[APPROVAL] Approval {approval_id} sent successfully (Message ID: {msg_id})")
        return True, approval_id

    def handle_callback_query(self, callback_query: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handles user interaction on the Telegram inline keyboard buttons.
        Enforces user authorization, idempotency, and command dispatch.
        """
        cq_id = callback_query.get("id", "")
        from_user = callback_query.get("from", {})
        user_id = from_user.get("id")
        data_str = callback_query.get("data", "")
        message = callback_query.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        msg_id = message.get("message_id")

        # 1. Authorization Gate
        if not verify_telegram_user(user_id, self.config.telegram_allowed_user_id):
            logger.warning(f"[SECURITY] Unauthorized callback from User ID: {user_id}. Expected: {self.config.telegram_allowed_user_id}")
            self.bot.answer_callback_query(cq_id, text="⚠️ Yetkisiz işlem.", show_alert=True)
            return {"status": "UNAUTHORIZED", "message": "Unauthorized Telegram user"}

        if not verify_telegram_chat(chat_id, self.config.telegram_chat_id):
            logger.warning(f"[SECURITY] Unauthorized chat ID: {chat_id}")
            self.bot.answer_callback_query(cq_id, text="⚠️ Yetkisiz sohbet.", show_alert=True)
            return {"status": "UNAUTHORIZED", "message": "Unauthorized chat ID"}

        # 2. Parse Action and Approval ID
        if ":" not in data_str:
            self.bot.answer_callback_query(cq_id, text="Geçersiz işlem.")
            return {"status": "INVALID_DATA"}

        action, approval_id = data_str.split(":", 1)
        approval = self.db.get_approval(approval_id)
        if not approval:
            self.bot.answer_callback_query(cq_id, text="Onay kaydı bulunamadı.", show_alert=True)
            return {"status": "NOT_FOUND"}

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 3. Expiration Check
        if approval.expires_at and approval.expires_at < now_str and approval.status == TelegramApprovalStatus.PENDING:
            approval.status = TelegramApprovalStatus.EXPIRED
            self.db.save_approval(approval)
            self.bot.answer_callback_query(cq_id, text="Bu onayın süresi dolmuş.", show_alert=True)
            self.bot.edit_message_text(chat_id, msg_id, "⌛ Bu haftalık onayın süresi dolmuştur.")
            return {"status": "EXPIRED"}

        # 4. Idempotency Gate (Already Processed)
        if approval.status != TelegramApprovalStatus.PENDING:
            status_text = "onaylandı" if approval.status == TelegramApprovalStatus.APPROVED else "reddedildi"
            self.bot.answer_callback_query(cq_id, text=f"Bu işlem daha önce {status_text}.")
            return {"status": "ALREADY_PROCESSED", "approval_status": approval.status.value}

        # 5. Handle EVET (Approval)
        if action == "weekly_approve":
            approval.status = TelegramApprovalStatus.APPROVED
            approval.responded_at = now_str
            approval.response = "APPROVED"
            self.db.save_approval(approval)

            # Update Next Week state
            next_week = self.db.get_week(approval.next_week_id)
            if next_week:
                next_week.status = CloudWeekStatus.APPROVED
                next_week.approval_status = "APPROVED"
                next_week.approved_at = now_str
                self.db.save_week(next_week)

            # Create LocalWorkerCommand (Unique constraint in DB prevents duplicate commands)
            cmd_id = f"CMD-{uuid.uuid4().hex[:8].upper()}"
            cmd = LocalWorkerCommand(
                command_id=cmd_id,
                type=CommandType.GENERATE_WEEK,
                week_id=approval.next_week_id,
                status=CommandStatus.PENDING,
                payload={"week_id": approval.next_week_id}
            )
            self.db.create_command(cmd)

            # Answer callback and edit message
            self.bot.answer_callback_query(cq_id, text="✅ Yeni hafta onaylandı!")
            updated_text = (
                f"✅ ONAYLANDI ({approval.next_week_id})\n\n"
                "14 Reel üretim kuyruğuna alındı.\n\n"
                "Bilgisayar/yerel worker çevrimiçiyse üretim başlayacak.\n"
                "Çevrimdışıysa ilk bağlantıda otomatik devam edecek."
            )
            self.bot.edit_message_text(chat_id, msg_id, updated_text)
            logger.info(f"[APPROVAL] Week {approval.next_week_id} APPROVED by user.")
            return {"status": "APPROVED", "week_id": approval.next_week_id, "command_id": cmd_id}

        # 6. Handle HAYIR (Rejection)
        elif action == "weekly_reject":
            approval.status = TelegramApprovalStatus.REJECTED
            approval.responded_at = now_str
            approval.response = "REJECTED"
            self.db.save_approval(approval)

            next_week = self.db.get_week(approval.next_week_id)
            if next_week:
                next_week.status = CloudWeekStatus.REJECTED
                next_week.approval_status = "REJECTED"
                next_week.rejected_at = now_str
                self.db.save_week(next_week)

            self.bot.answer_callback_query(cq_id, text="❌ Yeni hafta reddedildi.")
            updated_text = (
                f"❌ REDDEDİLDİ ({approval.next_week_id})\n\n"
                "Yeni hafta oluşturulmadı. Mevcut yayın planı değişmedi."
            )
            self.bot.edit_message_text(chat_id, msg_id, updated_text)
            logger.info(f"[APPROVAL] Week {approval.next_week_id} REJECTED by user.")
            return {"status": "REJECTED", "week_id": approval.next_week_id}

        return {"status": "UNKNOWN_ACTION"}
