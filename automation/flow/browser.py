"""
Playwright Chrome DevTools Protocol (CDP) connection manager.
Connects to an existing or auto-launched real Google Chrome instance without automation flags.
"""
from pathlib import Path
from typing import Generator, Tuple, Optional
from contextlib import contextmanager
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

from .chrome_launcher import is_cdp_available, ensure_chrome_running, detect_chrome_path
from ..config import AppConfig

class CDPBrowserManager:
    """Manages connection to real Google Chrome via Chrome DevTools Protocol (CDP)."""

    def __init__(self, config: AppConfig):
        self.config = config

    def ensure_chrome(self) -> None:
        """Verify Chrome is running with remote debugging, auto-launch if needed."""
        if not is_cdp_available(self.config.chrome_debug_port):
            chrome_exe = detect_chrome_path()
            ready = ensure_chrome_running(
                chrome_path=chrome_exe,
                profile_dir=self.config.chrome_profile_dir,
                port=self.config.chrome_debug_port,
                url=self.config.flow_url,
                timeout_seconds=15
            )
            if not ready:
                raise ConnectionError(
                    f"Google Chrome remote debugging portuna ({self.config.chrome_debug_port}) bağlanılamadı. "
                    f"Lütfen FLOW_LOGIN.bat dosyasını çalıştırarak Chrome'u başlatın."
                )

    @contextmanager
    def connect(self) -> Generator[Tuple[Browser, BrowserContext], None, None]:
        """Connect to running Chrome instance via CDP and yield (browser, context)."""
        self.ensure_chrome()
        endpoint_url = f"http://127.0.0.1:{self.config.chrome_debug_port}"

        with sync_playwright() as p:
            browser: Browser = p.chromium.connect_over_cdp(endpoint_url)
            try:
                # Use default context from the running Chrome instance
                if browser.contexts:
                    context = browser.contexts[0]
                else:
                    context = browser.new_context()

                yield browser, context
            finally:
                # Disconnect CDP client from Chrome (does not kill the running Chrome process)
                try:
                    browser.close()
                except Exception:
                    pass

    @staticmethod
    def find_or_open_flow_page(context: BrowserContext, flow_url: str) -> Page:
        """
        Check existing open tabs in Chrome. If Flow is already open, use it.
        Otherwise open a new tab and navigate to Flow URL.
        """
        for p in context.pages:
            url_lower = p.url.lower()
            if "flow" in url_lower or "labs.google" in url_lower:
                try:
                    p.bring_to_front()
                    return p
                except Exception:
                    return p

        # If not found, open a new page
        new_p = context.new_page()
        try:
            new_p.goto(flow_url, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        return new_p
