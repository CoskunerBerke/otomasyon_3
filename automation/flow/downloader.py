"""
Download manager for capturing and saving completed video files from Google Flow.
Includes Playwright expect_download handling, fast-skip for disabled buttons,
user Downloads folder fallback, and file integrity verification.
"""
import time
import shutil
from pathlib import Path
from typing import Optional
from playwright.sync_api import Page, Download, Locator

class FlowDownloader:
    """Manages file download events and verifies saved files."""

    def __init__(self, downloads_dir: Path):
        self.downloads_dir = Path(downloads_dir).resolve()
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def trigger_and_save_download(
        self,
        page: Page,
        download_button_locator: Locator,
        target_filename: str,
        timeout_seconds: int = 60
    ) -> Path:
        """
        Click the download button and save video to workspace downloads folder.
        Pre-checks that button is enabled (skips immediately if disabled) with fast 2s click timeout.
        """
        target_path = self.downloads_dir / target_filename
        if target_path.exists():
            target_path.unlink(missing_ok=True)

        # Pre-check: button MUST be enabled before attempting click
        try:
            aria_dis = download_button_locator.get_attribute("aria-disabled")
            if aria_dis == "true" or not download_button_locator.is_enabled():
                raise RuntimeError("DOWNLOAD_BUTTON_DISABLED: İndirme butonu pasif (disabled).")
        except Exception as e:
            if "DOWNLOAD_BUTTON_DISABLED" in str(e):
                raise
            # If locator is stale / detached, fail fast to allow recovery
            raise RuntimeError(f"Download button check failed: {e}")

        user_downloads_dir = Path.home() / "Downloads"
        pre_download_time = time.time() - 2

        # Method 1: Playwright expect_download event with fast click timeout
        download_succeeded = False
        try:
            with page.expect_download(timeout=timeout_seconds * 1000) as download_info:
                # Fast 2-second timeout to avoid Playwright waiting 30s for disabled elements
                download_button_locator.click(timeout=2000)
            download: Download = download_info.value
            download.save_as(str(target_path))
            download_succeeded = True
        except Exception as e:
            # Method 2: Fallback - if Chrome saved the download directly to user's Downloads folder
            time.sleep(2.0)
            if user_downloads_dir.exists():
                recent_mp4s = [
                    f for f in user_downloads_dir.glob("*.mp4")
                    if f.stat().st_mtime >= pre_download_time
                ]
                if recent_mp4s:
                    latest_mp4 = max(recent_mp4s, key=lambda f: f.stat().st_mtime)
                    if latest_mp4.stat().st_size > 10000:
                        shutil.copy2(str(latest_mp4), str(target_path))
                        download_succeeded = True

            if not download_succeeded and not target_path.exists():
                raise RuntimeError(f"Download failed: {e}")

        # Verification
        if not target_path.exists() or target_path.stat().st_size < 10000:
            raise RuntimeError(f"Downloaded file is missing or invalid size: {target_path}")

        return target_path
