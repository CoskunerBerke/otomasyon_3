"""
Targeted Unit Tests for Dynamic YouTube Schedule Verification.
Tests that parse_schedule_datetime dynamically extracts date (DD.MM.YYYY) and time (HH:MM)
for 19:30, 22:00, and arbitrary future dates across all weeks.
Uses strict mocks: 0 real browser launches, 0 real uploads.
"""
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation.publishing.youtube_studio_publisher import (
    parse_schedule_datetime,
    YouTubeStudioPublisher
)
from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord
from automation.publishing.config import PublishingConfig


def test_parse_schedule_datetime_1930():
    """Test: 2026-08-17 19:30:00 correctly converts to Turkish format 17.08.2026 / 19:30."""
    date_str, time_str = parse_schedule_datetime("2026-08-17 19:30:00")
    assert date_str == "17.08.2026"
    assert time_str == "19:30"


def test_parse_schedule_datetime_2200():
    """Test: 2026-08-17 22:00:00 correctly converts to Turkish format 17.08.2026 / 22:00."""
    date_str, time_str = parse_schedule_datetime("2026-08-17 22:00:00")
    assert date_str == "17.08.2026"
    assert time_str == "22:00"


def test_parse_schedule_datetime_various_weeks_and_formats():
    """Test: Works across different weeks and ISO format variations."""
    # Week 35
    d1, t1 = parse_schedule_datetime("2026-08-24 19:30:00")
    assert d1 == "24.08.2026"
    assert t1 == "19:30"

    # Week 36
    d2, t2 = parse_schedule_datetime("2026-08-31 22:00:00")
    assert d2 == "31.08.2026"
    assert t2 == "22:00"

    # ISO with 'T'
    d3, t3 = parse_schedule_datetime("2026-09-05T22:00:00")
    assert d3 == "05.09.2026"
    assert t3 == "22:00"

    # Year 2099
    d4, t4 = parse_schedule_datetime("2099-12-28 19:30:00")
    assert d4 == "28.12.2099"
    assert t4 == "19:30"


def test_youtube_studio_publisher_calls_dynamic_verification(tmp_path):
    """Test: upload_and_schedule passes dynamic expected date/time to observer.verify_remote_scheduled_status."""
    config = PublishingConfig()
    mock_repo = MagicMock()
    mock_repo.merge_with_existing.side_effect = lambda r: r
    mock_repo.get_publish_record.return_value = None
    publisher = YouTubeStudioPublisher(config=config, repo=mock_repo)

    dummy_video = tmp_path / "video.mp4"
    dummy_video.write_bytes(b"sample video bytes")

    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0012-YOUTUBE",
        batch_id="2026-08-17",
        reel_id="REEL-2026-0012",
        platform=Platform.YOUTUBE,
        account_handle="@BuiIdVerse",
        video_file=dummy_video,
        video_sha256="fake_sha",
        title="Test Reel 0012",
        description="Caption",
        hashtags=["#shorts"],
        scheduled_at_local="2026-08-17 22:00:00",
        scheduled_at_utc="2026-08-17 19:00:00",
        timezone="Europe/Istanbul",
        status=PlatformPublicationStatus.PENDING,
        dry_run=False,
        ai_generated=True,
        synthetic_media_disclosed=True
    )

    mock_observer = MagicMock()
    mock_observer.is_logged_in.return_value = True
    mock_observer.verify_logged_in_channel.return_value = (True, "@BuiIdVerse", "OK")
    mock_observer.advance_wizard_to_visibility.return_value = (True, "OK")
    mock_observer.find_and_expand_schedule_card.return_value = True
    mock_observer.set_schedule_datetime.return_value = True
    mock_observer.click_schedule_and_verify.return_value = (True, "submitted")
    mock_observer.verify_remote_scheduled_status.return_value = (True, "verified")

    with patch.object(publisher.browser_mgr, "connect") as mock_connect:
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_context.pages = [mock_page]
        mock_page.url = "https://studio.youtube.com/channel/test"
        mock_connect.return_value.__enter__.return_value = (mock_browser, mock_context)

        with patch("automation.publishing.youtube_studio_publisher.YouTubeStudioUIObserver", return_value=mock_observer):
            res = publisher.upload_and_schedule(rec)

    assert res.status == PlatformPublicationStatus.SCHEDULED
    mock_observer.verify_remote_scheduled_status.assert_called_once()
    _, kwargs = mock_observer.verify_remote_scheduled_status.call_args
    # Confirms 22:00 slot dynamically passed (NOT hardcoded 19:30 or 16.08.2026)
    assert kwargs["expected_date_str"] == "17.08.2026"
    assert kwargs["expected_time_str"] == "22:00"
