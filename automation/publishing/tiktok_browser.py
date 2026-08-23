"""
Dedicated Chrome CDP Browser Manager for TikTok Studio on port 9223.
Isolated from Google Flow CDP (port 9222).
"""
import os
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional, Tuple
from contextlib import contextmanager

from automation.brands import login_bat_for_profile

logger = logging.getLogger("ReelsAIFactory.TikTokBrowser")

class TikTokBrowserManager:
    """Manages dedicated Chrome profile and CDP connection for TikTok Studio."""

    def __init__(self, debug_port: int = 9223, profile_dir: Optional[Path] = None):
        self.debug_port = debug_port
        if profile_dir is None:
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                self.profile_dir = Path(local_app_data) / "ReelsAIFactory" / "tiktok-profile"
            else:
                self.profile_dir = Path.home() / ".reels_ai_factory" / "tiktok-profile"
        else:
            self.profile_dir = Path(profile_dir).resolve()

        self.profile_dir.mkdir(parents=True, exist_ok=True)

    def is_cdp_available(self) -> bool:
        """Check if Chrome is currently running with remote debugging on port 9223."""
        import urllib.request
        try:
            url = f"http://127.0.0.1:{self.debug_port}/json/version"
            with urllib.request.urlopen(url, timeout=1.5) as response:
                return response.status == 200
        except Exception:
            return False

    def launch_chrome_for_tiktok(self, start_url: str = "https://www.tiktok.com/creator-center/upload") -> subprocess.Popen:
        """Launch dedicated Chrome instance for TikTok Studio."""
        chrome_exe = self._find_chrome_executable()
        if not chrome_exe:
            raise FileNotFoundError("Google Chrome executable not found on system.")

        args = [
            str(chrome_exe),
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={str(self.profile_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            start_url
        ]
        logger.info(f"Launching TikTok dedicated Chrome on port {self.debug_port}...")
        return subprocess.Popen(args)

    @contextmanager
    def connect(self):
        """Playwright Sync CDP connection context manager for TikTok Studio."""
        from playwright.sync_api import sync_playwright

        if not self.is_cdp_available():
            # Attempt to auto-launch Chrome
            self.launch_chrome_for_tiktok()
            # Wait for CDP port to open
            for _ in range(20):
                time.sleep(0.5)
                if self.is_cdp_available():
                    break
            if not self.is_cdp_available():
                raise ConnectionError(
                    f"TikTok Chrome CDP port {self.debug_port} is not responding.\n"
                    f"Lütfen önce bu markanın giriş dosyasını çalıştırın "
                    f"({login_bat_for_profile(self.profile_dir)})."
                )

        pw = sync_playwright().start()
        try:
            cdp_url = f"http://127.0.0.1:{self.debug_port}"
            browser = pw.chromium.connect_over_cdp(cdp_url)
            contexts = browser.contexts
            context = contexts[0] if contexts else browser.new_context()
            yield browser, context
        finally:
            pw.stop()

    def _find_chrome_executable(self) -> Optional[Path]:
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local")) / "Google" / "Chrome" / "Application" / "chrome.exe"
        ]
        for c in candidates:
            if c.exists():
                return c
        return None
