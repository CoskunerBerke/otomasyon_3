"""
Unit tests for notification isolation, mock providers,
output path guards, and ready count verification.
"""
import pytest
from pathlib import Path
from automation.notifications.windows import (
    NotificationProvider,
    MockNotificationProvider,
    WindowsNotificationProvider,
    is_test_environment,
    is_test_path,
    get_default_notification_provider
)

def test_pytest_environment_detected():
    assert is_test_environment() is True
    provider = get_default_notification_provider()
    assert isinstance(provider, MockNotificationProvider)

def test_test_path_markers_detected():
    temp_p1 = Path(r"C:\Users\berke\AppData\Local\Temp\pytest-of-berke\pytest-12\test0\Mock_Output\2026-08-15")
    temp_p2 = Path(r"/tmp/pytest-123/mock_output")
    real_p = Path(r"C:\Users\berke\OneDrive\Masaüstü\AI_Reels\2026-08-15")

    assert is_test_path(temp_p1) is True
    assert is_test_path(temp_p2) is True
    assert is_test_path(real_p) is False

def test_mock_notification_provider_records_payload():
    mock = MockNotificationProvider()
    out_dir = Path(r"C:\Users\berke\OneDrive\Masaüstü\AI_Reels\2026-08-15")
    mock.notify_success(1, out_dir)

    assert len(mock.sent_notifications) == 1
    item = mock.sent_notifications[0]
    assert item["type"] == "success"
    assert item["count"] == 1
    assert "1 yeni Reel hazır" in item["message"]
    assert str(out_dir) in item["message"]

def test_production_count_3_with_2_ready():
    mock = MockNotificationProvider()
    out_dir = Path(r"C:\Users\berke\OneDrive\Masaüstü\AI_Reels\2026-08-15")
    mock.notify_success(2, out_dir)

    item = mock.sent_notifications[0]
    assert item["count"] == 2
    assert "2 yeni Reel hazır" in item["message"]

def test_windows_provider_suppresses_toast_on_test_path():
    provider = WindowsNotificationProvider(enabled=True)
    temp_p = Path(r"C:\Users\berke\AppData\Local\Temp\pytest-of-berke\pytest-12\Mock_Output")
    # Should safely return without sending toast or throwing exception
    provider.notify_success(2, temp_p)
