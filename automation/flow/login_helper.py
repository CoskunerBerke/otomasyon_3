"""
Interactive login helper for Google Flow.
Opens Chromium with persistent profile outside of OneDrive (%LOCALAPPDATA%\\ReelsAIFactory\\browser-profile),
navigates to Google Flow / Sign in, and waits for user to close browser window.
"""
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from automation.config import load_config, get_default_browser_profile_path

def interactive_login():
    try:
        config = load_config()
        profile_dir = config.browser_profile_dir
        downloads_dir = config.workspace_downloads_dir
        flow_url = config.flow_url
    except Exception:
        profile_dir = get_default_browser_profile_path()
        downloads_dir = (_project_root / "workspace" / "downloads").resolve()
        flow_url = "https://labs.google/fx/tools/flow"

    profile_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)

    print("========================================================")
    print("      GOOGLE FLOW - MANUEL OTURUM AÇMA YARDIMCISI")
    print("========================================================")
    print(f"Kalıcı Profil Konumu (OneDrive Dışı):")
    print(f"👉 {profile_dir}")
    print()
    print("1. Açılan tarayıcıda Google hesabınızla oturum açın.")
    print("2. Google Flow sayfasına eriştiğinizden emin olun.")
    print("3. Giriş tamamlandığında TARAYICIYI KAPATIN.")
    print("   (Oturumunuz kalıcı olarak bu profile kaydedilecektir.)")
    print("========================================================\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            downloads_path=str(downloads_dir),
            viewport=None,
            args=["--start-maximized"]
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(flow_url)

        print("[BİLGİ] Tarayıcı açık. Giriş yapıp tarayıcıyı kapattığınızda bu pencere tamamlanacaktır...")

        # Wait until user closes the browser context
        try:
            while len(context.pages) > 0:
                time.sleep(1.0)
        except Exception:
            pass

    # Verify profile directory
    if profile_dir.exists() and any(profile_dir.iterdir()):
        print("\n[BAŞARILI] Oturum profili kaydedildi ve doğrulandı.")
        print(f"Profil Dizini: {profile_dir}")
        print("Artık 1_YENI_REEL_URET.bat veya 3_YENI_REEL_URET.bat ile üretim yapabilirsiniz!")
    else:
        print("\n[UYARI] Profil dizini oluşturuldu fakat içi boş görünüyor.")

if __name__ == "__main__":
    interactive_login()
