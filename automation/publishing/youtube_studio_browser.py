"""
YouTube Studio Chrome CDP Browser Manager on dedicated port 9224.
Maintains independent profile in %LOCALAPPDATA%\\ReelsAIFactory\\youtube-studio-profile.
"""
import os
import sys
import time
import socket
import logging
import subprocess
from pathlib import Path
from typing import Tuple, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger("ReelsAIFactory.YouTubeStudioBrowser")

def get_default_youtube_studio_profile_path() -> Path:
    """Returns %LOCALAPPDATA%\\ReelsAIFactory\\youtube-studio-profile on Windows."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ReelsAIFactory" / "youtube-studio-profile"
    return Path.home() / ".reels_ai_factory" / "youtube-studio-profile"

class YouTubeStudioBrowserManager:
    """Manages dedicated Chrome instance for YouTube Studio on Port 9224."""

    def __init__(
        self,
        debug_port: int = 9224,
        profile_dir: Optional[Path] = None,
        chrome_path: Optional[str] = None
    ):
        self.debug_port = debug_port
        self.profile_dir = (profile_dir or get_default_youtube_studio_profile_path()).resolve()
        self.chrome_path = chrome_path or self._detect_chrome_executable()

    def _detect_chrome_executable(self) -> str:
        """Locate Google Chrome executable on Windows."""
        candidates = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe"
        ]
        for c in candidates:
            if c and Path(c).exists():
                return c
        return "chrome.exe"

    def is_cdp_available(self) -> bool:
        """Check if port 9224 is open and responding."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            return s.connect_ex(("127.0.0.1", self.debug_port)) == 0

    def launch_chrome_for_youtube_studio(self, url: str = "https://studio.youtube.com/") -> subprocess.Popen:
        """Launch dedicated Chrome instance for interactive YouTube Studio login."""
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.chrome_path,
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={str(self.profile_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            url
        ]

        logger.info(f"Launching YouTube Studio Chrome on port {self.debug_port} with profile: {self.profile_dir}")
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.0)
        return proc

    @contextmanager
    def connect(self):
        """Connect to running YouTube Studio Chrome instance over Playwright CDP."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright is not installed. Run: pip install playwright")

        if not self.is_cdp_available():
            # Try to launch automatically
            self.launch_chrome_for_youtube_studio()
            # Wait up to 10 seconds for CDP
            cdp_ready = False
            for _ in range(20):
                if self.is_cdp_available():
                    cdp_ready = True
                    break
                time.sleep(0.5)

            if not cdp_ready:
                raise ConnectionError(
                    f"Could not connect to YouTube Studio Chrome CDP on port {self.debug_port}.\n"
                    f"Lütfen önce 'YOUTUBE_STUDIO_LOGIN.bat' dosyasını çalıştırın."
                )

        p = sync_playwright().start()
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{self.debug_port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            yield browser, context
        finally:
            try:
                p.stop()
            except Exception:
                pass
