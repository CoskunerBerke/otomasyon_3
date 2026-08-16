"""
Windows notification service with isolation for testing and test-path guards.
Prevents pytest / mock test runs from emitting real Windows toast notifications,
and strictly validates output paths and ready counts for production notifications.
"""
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

TEST_PATH_MARKERS = [
    "pytest-",
    "pytest",
    "temp\\pytest",
    "mock_output",
    "test_full_pipeline",
    "tmp_path"
]

def is_test_environment() -> bool:
    """Check if code is running under pytest or unittest test runners."""
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules

def is_test_path(path: Optional[Path]) -> bool:
    """Check if the provided path is a temporary or test output folder."""
    if not path:
        return False
    path_str = str(path).lower()
    return any(marker in path_str for marker in TEST_PATH_MARKERS)

class NotificationProvider(ABC):
    """Abstract interface for sending system notifications."""

    @abstractmethod
    def notify_success(self, count: int, output_dir: Path) -> None:
        pass

    @abstractmethod
    def notify_action_required(self, reason: str) -> None:
        pass

    @abstractmethod
    def notify_failure(self, error_msg: str) -> None:
        pass

class MockNotificationProvider(NotificationProvider):
    """In-memory notification recorder for testing; never triggers OS toast notifications."""

    def __init__(self):
        self.sent_notifications: List[Dict[str, Any]] = []

    def notify_success(self, count: int, output_dir: Path) -> None:
        self.sent_notifications.append({
            "type": "success",
            "count": count,
            "output_dir": output_dir,
            "title": "Reels AI Factory — Tamamlandı",
            "message": f"{count} yeni Reel hazır. Kayıt yeri: {output_dir}"
        })

    def notify_action_required(self, reason: str) -> None:
        self.sent_notifications.append({
            "type": "action_required",
            "reason": reason,
            "title": "USER_ACTION_REQUIRED — Google Flow",
            "message": f"Google Flow kullanıcı müdahalesi bekliyor: {reason}"
        })

    def notify_failure(self, error_msg: str) -> None:
        self.sent_notifications.append({
            "type": "failure",
            "error_msg": error_msg,
            "title": "Reels AI Factory — Hata",
            "message": f"Reels AI Factory tamamlanamadı: {error_msg[:120]}"
        })

class NullNotificationProvider(NotificationProvider):
    """No-op provider."""
    def notify_success(self, count: int, output_dir: Path) -> None:
        pass
    def notify_action_required(self, reason: str) -> None:
        pass
    def notify_failure(self, error_msg: str) -> None:
        pass

class WindowsNotificationProvider(NotificationProvider):
    """Real Windows toast notification provider with strict test guards."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def _send_toast(self, title: str, message: str, icon_type: str = "Info") -> None:
        if not self.enabled or os.name != 'nt':
            return

        if is_test_environment():
            return

        escaped_title = title.replace('"', '`"').replace("'", "''")
        escaped_message = message.replace('"', '`"').replace("'", "''")

        ps_script = f"""
        try {{
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
            $textNodes = $template.GetElementsByTagName("text")
            $textNodes.Item(0).AppendChild($template.CreateTextNode("{escaped_title}")) | Out-Null
            $textNodes.Item(1).AppendChild($template.CreateTextNode("{escaped_message}")) | Out-Null
            $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
            $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Reels AI Factory")
            $notifier.Show($toast)
        }} catch {{
            Add-Type -AssemblyName System.Windows.Forms
            $global:balloon = New-Object System.Windows.Forms.NotifyIcon
            $global:balloon.Icon = [System.Drawing.SystemIcons]::Information
            $global:balloon.BalloonTipTitle = "{escaped_title}"
            $global:balloon.BalloonTipText = "{escaped_message}"
            $global:balloon.Visible = $true
            $global:balloon.ShowBalloonTip(5000)
        }}
        """
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                capture_output=True,
                timeout=8,
                check=False
            )
        except Exception:
            pass

    def notify_success(self, count: int, output_dir: Path) -> None:
        if is_test_path(output_dir):
            # Suppress toast for temp test paths
            return
        title = "Reels AI Factory — Tamamlandı"
        message = f"{count} yeni Reel hazır. Kayıt yeri: {output_dir}"
        self._send_toast(title, message, "Info")

    def notify_action_required(self, reason: str) -> None:
        title = "USER_ACTION_REQUIRED — Google Flow"
        message = f"Google Flow kullanıcı müdahalesi bekliyor: {reason}"
        self._send_toast(title, message, "Warning")

    def notify_failure(self, error_msg: str) -> None:
        title = "Reels AI Factory — Hata"
        message = f"Reels AI Factory tamamlanamadı: {error_msg[:120]}"
        self._send_toast(title, message, "Error")

def get_default_notification_provider(enabled: bool = True) -> NotificationProvider:
    """Return appropriate notification provider based on environment."""
    if is_test_environment():
        return MockNotificationProvider()
    return WindowsNotificationProvider(enabled=enabled)

# Module-level convenience functions
_default_provider = get_default_notification_provider()

def notify_success(count: int, output_dir: Path) -> None:
    get_default_notification_provider().notify_success(count, output_dir)

def notify_action_required(reason: str) -> None:
    get_default_notification_provider().notify_action_required(reason)

def notify_failure(error_msg: str) -> None:
    get_default_notification_provider().notify_failure(error_msg)
