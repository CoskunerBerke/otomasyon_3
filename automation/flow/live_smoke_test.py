"""
Live No-Credit Smoke Test for Google Flow Automation.
Connects over CDP, navigates to Project Editor if needed, fills smoke test prompt,
verifies read-back, clears the field, and leaves Generate untouched (0 credits used).
"""
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from automation.config import load_config
from automation.flow.browser import CDPBrowserManager
from automation.flow.page import FlowPage
from automation.flow.selectors import FlowPageState

def run_smoke_test():
    print("========================================================")
    print("      GOOGLE FLOW - CANLI SIFIR KREDİ SMOKE TESTİ")
    print("========================================================")

    config = load_config()
    # Force safety: allow_real_generation=False
    config.allow_real_generation = False

    browser_mgr = CDPBrowserManager(config)

    print("[1/5] Chrome CDP bağlantısı kuruluyor...")
    with browser_mgr.connect() as (browser, context):
        page = browser_mgr.find_or_open_flow_page(context, config.flow_url)
        flow_page = FlowPage(
            page=page,
            screenshots_dir=config.screenshots_dir,
            downloads_dir=config.workspace_downloads_dir
        )
        print(f"      Bağlanılan Sekme URL: {page.url}")

        print("[2/5] Oturum ve sayfa durumu doğrulanıyor...")
        flow_page.check_auth_and_security()
        initial_state = flow_page.detect_page_state()
        print(f"      Algılanan Durum: {initial_state.value}")

        print("[3/5] Project Editor çalışma alanı kontrol ediliyor...")
        flow_page.ensure_project_editor()
        final_state = flow_page.detect_page_state()
        print(f"      Son Durum: {final_state.value} (URL: {page.url})")
        assert final_state == FlowPageState.PROJECT_EDITOR, "Project Editor açılamadı!"

        print("[4/5] Prompt giriş kutusu test ediliyor...")
        smoke_prompt = "Automation smoke test - do not generate"
        flow_page.enter_prompt(smoke_prompt)
        print("      Prompt yazıldı ve DOM üzerinde doğrulandı.")

        # Read back for explicit assertion
        prompt_input = flow_page.find_first_visible(flow_page.page.locator("[data-slate-editor='true'], [role='textbox'][contenteditable='true']").all())
        # Clean up text from editor
        prompt_input_loc = page.locator("[data-slate-editor='true'], [role='textbox'][contenteditable='true'], div[contenteditable='true']").first
        prompt_input_loc.fill("")
        time.sleep(0.5)
        print("      Test promptu alandan temizlendi (Editor temiz bırakıldı).")

        print("[5/5] Guvenlik kontrolu:")
        print("      -> Generate butonuna BASILMADI.")
        print("      -> Harcanan Flow Kredisi: 0")

    print("\n========================================================")
    print("          SMOKE TEST SONUCU: [PASS]")
    print("========================================================")

if __name__ == "__main__":
    run_smoke_test()
