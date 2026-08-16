"""
Unit tests for fast-skipping disabled download button candidates
and immediate recovery to enabled download buttons.
"""
import time
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from automation.flow.downloader import FlowDownloader

def test_disabled_download_button_skipped_immediately():
    downloader = FlowDownloader(downloads_dir=Path("./tmp_dl"))

    mock_page = MagicMock()
    mock_btn = MagicMock()
    # Simulate disabled button
    mock_btn.get_attribute.return_value = "true"
    mock_btn.is_enabled.return_value = False

    start = time.time()
    with pytest.raises(RuntimeError) as exc_info:
        downloader.trigger_and_save_download(
            page=mock_page,
            download_button_locator=mock_btn,
            target_filename="test.mp4"
        )
    elapsed = time.time() - start

    # Must fail immediately (< 0.5s), NEVER waiting 30 seconds
    assert elapsed < 1.0
    assert "DOWNLOAD_BUTTON_DISABLED" in str(exc_info.value)
    # mock_btn.click should NEVER have been called on disabled button
    mock_btn.click.assert_not_called()

def test_enabled_download_button_clicks_successfully(tmp_path: Path):
    dl_dir = tmp_path / "downloads"
    downloader = FlowDownloader(downloads_dir=dl_dir)

    target_file = dl_dir / "success.mp4"

    mock_page = MagicMock()
    mock_btn = MagicMock()
    mock_btn.get_attribute.return_value = "false"
    mock_btn.is_enabled.return_value = True

    # Simulate expect_download context manager writing the file
    class MockDownloadContext:
        def __enter__(self):
            mock_val = MagicMock()
            def mock_save(path):
                Path(path).write_bytes(b"x" * 20000)
            mock_val.save_as.side_effect = mock_save
            self.value = mock_val
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    mock_page.expect_download.return_value = MockDownloadContext()

    res_path = downloader.trigger_and_save_download(
        page=mock_page,
        download_button_locator=mock_btn,
        target_filename="success.mp4"
    )

    assert res_path.exists()
    assert res_path.stat().st_size == 20000
    mock_btn.click.assert_called_once()
