"""
Download manager for capturing and saving completed video files from Google Flow.
Includes Playwright expect_download handling, fast-skip for disabled buttons,
user Downloads folder fallback, and file integrity verification.
"""
import re
import time
import shutil
from pathlib import Path
from typing import Optional
from playwright.sync_api import Page, Download, Locator

# How long the download button is given to become clickable.
#
# This was 2000ms, justified as "avoid Playwright waiting 30s for disabled elements" --
# but the disabled case is already ruled out by the aria-disabled/is_enabled pre-check
# a few lines above, so the short timeout was guarding a possibility that cannot reach
# it. What it actually caught was a button that is enabled but still SETTLING: Flow
# animates its result panel, and Playwright refuses to click an unstable element.
#
# CBM-REEL-2026-0027 failed exactly that way on 2026-08-27 -- the locator resolved, the
# button was there and enabled, and the click gave up while it was still moving. The
# video had already been generated, so the Flow credit was spent and the file simply
# never came down.
DOWNLOAD_CLICK_TIMEOUT_MS = 15000


# Quality-menu entries that bill. The upscaled entries spend credits -- 50 for 4K -- so
# an entry whose label carries an upscale or credit marker is never clicked, even if it
# also says "original".
_PAID_ENTRY_PATTERN = re.compile(
    r"y[uü]kseltilmi[sş]|upscal|\d+\s*(kredi|credit)", re.IGNORECASE
)


def _is_paid_entry(label: str) -> bool:
    return bool(_PAID_ENTRY_PATTERN.search(label or ""))


def _capture_menu_diagnostics(page: Page) -> str:
    """
    Dump the open quality menu when no entry matched, and return its visible labels.

    Without this, a refusal says only that the menu was unrecognised -- which is what the
    2026-09-17 failure looked like, leaving no way to tell a wrong word from a wrong role
    without another live run. The labels go into the error the operator sees, the markup
    into screenshots/errors/ (Kural 31: fix from real DOM, never from a guess).
    """
    labels = ""
    try:
        menu = page.locator("[role='menu']").first
        labels = " | ".join(t for t in (menu.inner_text() or "").splitlines() if t.strip())[:300]
        html = menu.evaluate("el => el.outerHTML")
        out_dir = Path(__file__).resolve().parents[2] / "screenshots" / "errors"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        (out_dir / f"error_download_quality_menu_{stamp}.html").write_text(
            html, encoding="utf-8"
        )
    except Exception:
        pass
    return labels


def _choose_original_quality(page: Page) -> None:
    """
    Flow's download control opens a quality menu instead of downloading.

    The menu offers 270p GIF, 720p original, 1080p upscaled and 4K upscaled -- and the
    upscaled entries spend credits, 50 of them for 4K. Only the original-size entry
    re-downloads what was already generated, so that is the only one this will click.

    A click that downloads directly (older UI, or a menu that never opens) is left alone.
    """
    try:
        page.wait_for_selector("[role='menu']", timeout=4000)
    except Exception:
        return

    # The entry reads "720p / Orijinal boyut". Turkish spells it "Orijinal" -- the earlier
    # "Orjinal" is a substring of nothing on that menu, so the match never happened and
    # every download ended in the refusal below with the video already generated and its
    # credit already spent (CBM-REEL-2026-0058, 2026-09-17).
    #
    # Two strategies for this one action, Turkish then English (Kural 31). The role picks
    # the entry, the text keeps us off the paid ones, and the marker check below is what
    # actually guards the credits if Flow ever renames an upscale to mention "original".
    paid_lookalike = None
    for sel in ("[role='menuitem']:has-text('Orijinal')",
                "[role='menuitem']:has-text('Original')"):
        items = page.locator(sel)
        try:
            count = items.count()
        except Exception:
            continue

        # Angular Material can leave a closed panel in the DOM, so the first match is not
        # necessarily the one on screen -- walk them and take the first visible entry.
        for i in range(count):
            item = items.nth(i)
            try:
                if not item.is_visible():
                    continue
                label = (item.inner_text() or "").strip()
            except Exception:
                continue
            if _is_paid_entry(label):
                paid_lookalike = label
                continue
            try:
                item.click(timeout=5000)
                return
            except Exception:
                continue

    if paid_lookalike:
        raise RuntimeError(
            "DOWNLOAD_QUALITY_MENU_PAID_ONLY: Indirme menusunde orijinal boyut girdisi yok; "
            f"eslesen tek girdi kredi harciyor ({paid_lookalike!r}). Tiklanmadi."
        )
    seen = _capture_menu_diagnostics(page)
    raise RuntimeError(
        "DOWNLOAD_QUALITY_MENU_UNRECOGNISED: Indirme menusu acildi ancak 'Orijinal boyut' "
        "secenegi bulunamadi. Kredi harcayan yukseltilmis secenekler bilerek secilmedi. "
        f"Menude gorulen girdiler: {seen or '(okunamadi)'} -- menunun HTML'i "
        "screenshots/errors/ altina yazildi."
    )


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
                # One click, but given time to become actionable. Playwright's own
                # actionability wait is the retry here -- a click that times out never
                # dispatched, so there is no risk of starting two downloads.
                download_button_locator.click(timeout=DOWNLOAD_CLICK_TIMEOUT_MS)
                # ...which now opens a quality menu rather than starting the download.
                _choose_original_quality(page)
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
