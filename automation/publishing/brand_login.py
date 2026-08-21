"""
Open a brand's Chrome profile so a human can sign in to that channel.

Each brand publishes as a different account, so each needs its own logged-in Chrome on
its own CDP port. Signing the shared profile into a second channel would not just be
untidy -- it is how a video reaches the wrong audience, which this system cannot undo.

Read-only: it opens browsers and reports what it finds. Nothing is uploaded, scheduled
or published from here.

    python -m automation.publishing.brand_login --brand hiddenbuild
    python -m automation.publishing.brand_login --brand hiddenbuild --platform youtube
"""
import argparse
import logging
import sys
from typing import List, Tuple

logging.basicConfig(level=logging.WARNING, format="%(message)s")

from automation.brands import Brand, BRANDS, get_brand
from automation.publishing.instagram_web_browser import InstagramWebBrowserManager
from automation.publishing.tiktok_browser import TikTokBrowserManager
from automation.publishing.youtube_studio_browser import YouTubeStudioBrowserManager

PLATFORMS = ("youtube", "tiktok", "instagram")


def _open(brand: Brand, platform: str) -> Tuple[bool, str]:
    """Launch (or attach to) this brand's Chrome for one platform."""
    try:
        if platform == "youtube":
            mgr = YouTubeStudioBrowserManager(
                debug_port=brand.youtube_port, profile_dir=brand.youtube_profile_dir
            )
            if mgr.is_cdp_available():
                return True, f"zaten acik (port {brand.youtube_port})"
            mgr.launch_chrome_for_youtube_studio()
            return True, f"acildi (port {brand.youtube_port}) -> {brand.youtube_handle}"

        if platform == "tiktok":
            mgr = TikTokBrowserManager(
                debug_port=brand.tiktok_port, profile_dir=brand.tiktok_profile_dir
            )
            if mgr.is_cdp_available():
                return True, f"zaten acik (port {brand.tiktok_port})"
            mgr.launch_chrome_for_tiktok()
            return True, f"acildi (port {brand.tiktok_port}) -> {brand.tiktok_username}"

        mgr = InstagramWebBrowserManager(
            debug_port=brand.instagram_port, profile_dir=brand.instagram_profile_dir
        )
        if mgr.is_cdp_available():
            return True, f"zaten acik (port {brand.instagram_port})"
        mgr.launch_chrome(start_url="https://www.instagram.com/scheduled_content/")
        return True, f"acildi (port {brand.instagram_port})"
    except Exception as e:
        return False, f"acilamadi: {e}"


def run(brand_id: str, platforms: List[str]) -> int:
    brand = get_brand(brand_id)

    print("=" * 62)
    print(f"KANAL GIRISI -- {brand.display_name} ({brand.brand_id})")
    print("=" * 62)
    print(f"YouTube  : {brand.youtube_handle}  [{brand.youtube_channel_id}]")
    print(f"TikTok   : {brand.tiktok_username}")
    print(f"Portlar  : YT {brand.youtube_port} | TT {brand.tiktok_port} | IG {brand.instagram_port}")
    print("=" * 62)
    print()
    print("Acilan pencerelerde YALNIZCA bu kanalin hesabina giris yapin.")
    print("Baska bir hesaba girmek videolarin yanlis kanala dusmesine yol acar.")
    print("Pencereleri ACIK BIRAKIN.")
    print()

    failures = 0
    for platform in platforms:
        ok, message = _open(brand, platform)
        print(f"  {'[OK]  ' if ok else '[HATA]'} {platform:10s} {message}")
        if not ok:
            failures += 1

    print()
    if failures:
        print(f"{failures} tarayici acilamadi.")
        return 1

    missing = brand.unconfigured_accounts()
    if missing:
        print(f"UYARI: bu markanin hesap bilgileri eksik ({', '.join(missing)}).")
        print("automation/brands.py doldurulmadan canli calistirma reddedilir.")
        return 2

    print("Giris yaptiktan sonra haftalik calistirmayi baslatabilirsiniz.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Bir markanin kanal tarayicilarini acar (giris icin)")
    parser.add_argument("--brand", default="hiddenbuild", choices=sorted(BRANDS))
    parser.add_argument("--platform", default="all", choices=("all",) + PLATFORMS)
    args = parser.parse_args()

    platforms = list(PLATFORMS) if args.platform == "all" else [args.platform]
    sys.exit(run(args.brand, platforms))


if __name__ == "__main__":
    main()
