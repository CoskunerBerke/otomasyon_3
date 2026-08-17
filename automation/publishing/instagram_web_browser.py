"""
Dedicated Chrome CDP Browser Manager for instagram.com on port 9225.

Isolated from Google Flow (9222), TikTok Studio (9223) and YouTube Studio (9224) so an
Instagram session never disturbs — or inherits state from — the other platforms.
"""
import os
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger("ReelsAIFactory.InstagramWebBrowser")


def get_default_instagram_profile_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ReelsAIFactory" / "instagram-profile"
    return Path.home() / ".reels_ai_factory" / "instagram-profile"


class InstagramWebBrowserManager:
    """Manages the dedicated Chrome profile and CDP connection for instagram.com."""

    def __init__(self, debug_port: int = 9225, profile_dir: Optional[Path] = None):
        self.debug_port = debug_port
        self.profile_dir = Path(profile_dir or get_default_instagram_profile_path()).resolve()
        self.profile_dir.mkdir(parents=True, exist_ok=True)

    def _find_chrome_executable(self) -> Optional[str]:
        candidates = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Google\Chrome\Application\chrome.exe",
            os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
        ]
        for c in candidates:
            if c and Path(c).exists():
                return c
        return None

    def is_cdp_available(self) -> bool:
        import urllib.request
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.debug_port}/json/version", timeout=1.5) as r:
                return r.status == 200
        except Exception:
            return False

    def launch_chrome(self, start_url: str = "https://www.instagram.com/") -> subprocess.Popen:
        chrome = self._find_chrome_executable()
        if not chrome:
            raise FileNotFoundError("Google Chrome bulunamadi.")
        cmd = [
            chrome,
            f"--remote-debugging-port={self.debug_port}",
            f"--user-data-dir={str(self.profile_dir)}",
            "--no-first-run",
            "--no-default-browser-check",
            start_url,
        ]
        logger.info(f"[IG BROWSER] Chrome baslatiliyor (port {self.debug_port}).")
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.0)
        return proc

    @contextmanager
    def connect(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError("Playwright kurulu degil: pip install playwright")

        if not self.is_cdp_available():
            self.launch_chrome()
            for _ in range(20):
                if self.is_cdp_available():
                    break
                time.sleep(0.5)
            else:
                raise ConnectionError(
                    f"instagram.com Chrome CDP baglantisi kurulamadi (port {self.debug_port}).\n"
                    f"Acilan pencerede Instagram'a giris yapip tekrar deneyin."
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
