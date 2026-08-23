"""
Instagram web readiness check and login helper.

Opens the dedicated instagram.com Chrome profile (port 9225) and reports whether the
weekly run would actually be able to schedule: is there a logged-in session, and does
the scheduled-content page expose its "İçeriği planla" entry point.

Read-only. It never opens a composer, never uploads, never schedules anything.

    python -m automation.publishing.instagram_web_login
"""
import logging
import sys

logging.basicConfig(level=logging.WARNING, format="%(message)s")

from automation.publishing.instagram_web_browser import InstagramWebBrowserManager
from automation.publishing.instagram_web_selectors import InstagramWebSelectors
from .ui_wait import visible as is_element_visible

SCHEDULED_CONTENT_URL = "https://www.instagram.com/scheduled_content/"

# Present only when nobody is signed in.
LOGGED_OUT_MARKERS = (
    "giriş yap",
    "log in",
    "sign up",
    "kaydol",
    "phone number, username, or email",
)


def check() -> int:
    print("=" * 62)
    print("INSTAGRAM WEB HAZIRLIK KONTROLU")
    print("=" * 62)
    print("Chrome aciliyor (port 9225, Instagram'a ozel profil)...")
    print("Giris yapilmamissa acilan pencerede giris yapin, sonra bu komutu tekrar calistirin.")
    print()

    mgr = InstagramWebBrowserManager()
    try:
        with mgr.connect() as (_browser, context):
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(SCHEDULED_CONTENT_URL, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"[HATA] {SCHEDULED_CONTENT_URL} acilamadi: {e}")
                return 1

            page.wait_for_timeout(2500)

            try:
                body = (page.inner_text("body") or "").lower()
            except Exception:
                body = ""

            if any(marker in body for marker in LOGGED_OUT_MARKERS):
                print("[HAYIR] Instagram'a giris yapilmamis gorunuyor.")
                print()
                print("Acik duran Chrome penceresinde hesabiniza giris yapin,")
                print("sonra bu komutu tekrar calistirin. Pencereyi kapatmayin.")
                return 2

            print("[OK] Giris yapilmis bir Instagram oturumu var.")

            # The composer entry point is what the weekly run actually needs. Its absence
            # usually means a professional/creator account is required, or the UI moved.
            try:
                entry = page.locator(InstagramWebSelectors.OPEN_COMPOSER_BUTTONS[0]).first
                visible = is_element_visible(entry, 4000)
            except Exception:
                visible = False

            if visible:
                print("[OK] 'Icerigi planla' butonu bulundu -- haftalik calistirma planlama yapabilir.")
                print()
                print("Hazirsiniz. BUILDVERSE_HAFTALIK_14_REEL.bat calistirilabilir.")
                return 0

            print("[HAYIR] 'Icerigi planla' butonu bulunamadi.")
            print()
            print("Instagram'in yerel planlama ozelligi yalnizca profesyonel (isletme/icerik")
            print("uretici) hesaplarda cikar. Hesap turunu kontrol edin.")
            print("Sayfa acikken buton gercekten goruntuleniyorsa, o butonun outerHTML'ini")
            print("paylasin: selector guncellenmesi gerekiyor demektir (NEEDS_USER_HTML).")
            return 3
    except Exception as e:
        print(f"[HATA] Chrome baglantisi kurulamadi: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(check())
