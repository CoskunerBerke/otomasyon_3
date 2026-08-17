"""
Live UI DOM Diagnostic Probe for Reels AI Factory.
Connects via Playwright CDP to:
- YouTube Studio on port 9224
- TikTok Studio on port 9223

Inspects real DOM structures without triggering any upload, schedule, or publish actions.
"""
import sys
import os
import json
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from automation.publishing.youtube_studio_browser import YouTubeStudioBrowserManager
from automation.publishing.tiktok_browser import TikTokBrowserManager

REMOTE_VIDEO_ID = "Sq1nDGQPpOc"
YOUTUBE_EDIT_URL = f"https://studio.youtube.com/video/{REMOTE_VIDEO_ID}/edit"

def probe_youtube():
    print("\n" + "="*60)
    print("[YOUTUBE LIVE DOM PROBE]")
    print("="*60)
    results = {
        "cdp_connected": False,
        "remote_draft_opened": False,
        "draft_banner_found": False,
        "edit_draft_button_found": False,
        "edit_draft_button_text": None,
        "wizard_ready": False,
        "active_step": None,
        "stepper_labels": [],
        "audience_yes": None,
        "audience_no": None,
        "audience_current_checked": None,
        "paper_inputs": [],
        "schedule_time_input": None,
        "schedule_date_input": None,
        "final_schedule_button": None
    }

    yt_mgr = YouTubeStudioBrowserManager(debug_port=9224)
    try:
        with yt_mgr.connect() as (browser, context):
            results["cdp_connected"] = True
            print(f"[OK] Connected to YouTube Studio Chrome on port 9224")

            page = None
            for p_cand in context.pages:
                if "studio.youtube.com" in p_cand.url:
                    page = p_cand
                    break
            if not page:
                page = context.new_page()

            print(f"Current page URL: {page.url}")

            # Navigate to exact remote edit URL if not already there or in wizard
            if REMOTE_VIDEO_ID not in page.url:
                print(f"Navigating to exact remote draft: {YOUTUBE_EDIT_URL}")
                page.goto(YOUTUBE_EDIT_URL, wait_until="domcontentloaded", timeout=25000)
                time.sleep(3.0)
            else:
                print(f"Already on remote draft URL: {page.url}")

            results["remote_draft_opened"] = True

            # Check Draft Banner
            banner_cands = page.locator("div:has-text('Bu video taslak durumunda'), div:has-text('This video is a draft'), ytcp-banner:has-text('taslak'), ytcp-banner:has-text('draft')")
            if banner_cands.count() > 0:
                results["draft_banner_found"] = True
                print("[PASS] Draft banner found in DOM.")

            # Check 'Taslağı düzenle' / 'Edit draft' Button
            edit_btn_cands = [
                "button:has-text('Taslağı düzenle')",
                "ytcp-button:has-text('Taslağı düzenle')",
                "button:has-text('Edit draft')",
                "button:has-text('Continue editing')",
                "ytcp-button#edit-draft-button",
                "button[aria-label*='Taslağı düzenle']",
                "button[aria-label*='Edit draft']",
                "#edit-draft-button"
            ]

            edit_btn = None
            for sel in edit_btn_cands:
                loc = page.locator(sel).first
                try:
                    loc.wait_for(state="visible", timeout=800)
                    edit_btn = loc
                    results["edit_draft_button_found"] = True
                    results["edit_draft_button_text"] = loc.inner_text().strip()
                    print(f"[PASS] Found 'Taslağı düzenle' button via '{sel}': '{results['edit_draft_button_text']}'")
                    break
                except Exception:
                    pass

            # Check if wizard is already open or needs click
            stepper_loc = page.locator("ytcp-stepper, div[role='tablist'], ytcp-uploads-dialog").first
            if not (stepper_loc.count() > 0 and stepper_loc.is_visible()):
                if edit_btn:
                    print("Clicking 'Taslağı düzenle' button to open wizard...")
                    edit_btn.click()
                    time.sleep(2.5)

            # Re-check wizard stepper
            stepper = page.locator("ytcp-stepper, div[role='tablist'], ytcp-uploads-dialog").first
            if stepper.count() > 0 and stepper.is_visible():
                results["wizard_ready"] = True
                print("[PASS] YouTube Upload/Edit Draft Wizard is READY (YOUTUBE_DRAFT_WIZARD_READY).")

                # Read stepper tabs
                tabs = page.locator("tp-yt-paper-tab, ytcp-stepper-step")
                tab_texts = []
                for i in range(tabs.count()):
                    t_loc = tabs.nth(i)
                    txt = t_loc.inner_text().strip().replace("\n", " ")
                    if txt:
                        tab_texts.append(txt)
                results["stepper_labels"] = tab_texts
                print(f"Stepper Steps: {tab_texts}")

            # Probe Audience Section (Details Tab)
            print("\n--- Probing Audience (Kitle) in Active Wizard ---")
            radios = page.locator("tp-yt-paper-radio-button, div[role='radio']")
            r_count = radios.count()
            print(f"Total radio elements in DOM: {r_count}")

            for i in range(r_count):
                r = radios.nth(i)
                try:
                    vis = r.is_visible()
                    name = r.get_attribute("name") or ""
                    aria_chk = r.get_attribute("aria-checked") or ""
                    txt = r.inner_text().strip()
                    html_snippet = r.evaluate("el => el.outerHTML.substring(0, 150)")

                    if "çocuklara özel" in txt.lower() or "made for kids" in txt.lower() or "MFK" in name:
                        is_no = ("hayır" in txt.lower() or "not" in txt.lower() or "NOT_MFK" in name)
                        label_type = "NO (Not Made for Kids)" if is_no else "YES (Made for Kids)"
                        radio_info = {
                            "index": i,
                            "label_type": label_type,
                            "name": name,
                            "visible": vis,
                            "aria_checked": aria_chk,
                            "text": txt,
                            "html": html_snippet
                        }
                        if is_no:
                            results["audience_no"] = radio_info
                        else:
                            results["audience_yes"] = radio_info

                        print(f"  [{label_type}] Visible: {vis} | aria-checked: {aria_chk} | name: {name} | Text: '{txt}'")
                except Exception:
                    pass

            # Progress through wizard to Visibility tab to inspect schedule card (Read-Only probe, NO publish)
            print("\n--- Navigating to Visibility Tab to inspect Schedule DOM ---")
            next_btns = page.locator("#next-button, button:has-text('İleri'), button:has-text('Next')")
            for _ in range(4):
                # Check if Visibility is active
                vis_tab = page.locator("tp-yt-paper-tab[aria-selected='true']:has-text('Görünürlük'), tp-yt-paper-tab[aria-selected='true']:has-text('Visibility')").first
                if vis_tab.count() > 0 and vis_tab.is_visible():
                    print("[PASS] Visibility tab is active.")
                    break
                if next_btns.first.is_visible() and next_btns.first.is_enabled():
                    next_btns.first.click()
                    time.sleep(1.0)

            # Inspect Schedule Accordion
            sched_headers = page.locator("#second-container-expand-button, #schedule-section ytcp-icon-button, [aria-label*='Planlayın'], [aria-label*='Schedule'], #heading:has-text('Planlayın'), #heading:has-text('Schedule')")
            for i in range(sched_headers.count()):
                sh = sched_headers.nth(i)
                if sh.is_visible():
                    print(f"Expanding schedule card header {i}...")
                    sh.click()
                    time.sleep(1.0)
                    break

            # Probe all Paper Inputs in Visibility / Schedule card
            print("\n--- Probing tp-yt-paper-input Elements ---")
            paper_inps = page.locator("input.style-scope.tp-yt-paper-input, input[aria-labelledby]")
            p_count = paper_inps.count()
            print(f"Found {p_count} paper input elements in DOM.")

            for i in range(p_count):
                inp = paper_inps.nth(i)
                try:
                    vis = inp.is_visible()
                    val = inp.input_value() if hasattr(inp, "input_value") else ""
                    lbl_id = inp.get_attribute("aria-labelledby") or ""
                    lbl_text = ""
                    if lbl_id:
                        lbl_el = page.locator(f"#{lbl_id}, [id='{lbl_id}']").first
                        if lbl_el.count() > 0:
                            lbl_text = lbl_el.inner_text().strip()
                    html_snip = inp.evaluate("el => el.outerHTML.substring(0, 180)")

                    inp_info = {
                        "index": i,
                        "visible": vis,
                        "value": val,
                        "aria_labelledby": lbl_id,
                        "resolved_label": lbl_text,
                        "html": html_snip
                    }
                    results["paper_inputs"].append(inp_info)
                    print(f"  Input [{i}] Visible: {vis} | Label ID: '{lbl_id}' -> Label Text: '{lbl_text}' | Value: '{val}' | HTML: {html_snip}")

                    if "saat" in lbl_text.lower() or "time" in lbl_text.lower() or ":" in val:
                        results["schedule_time_input"] = inp_info
                    if "tarih" in lbl_text.lower() or "date" in lbl_text.lower() or "2026" in val:
                        results["schedule_date_input"] = inp_info

                except Exception as e:
                    print(f"  Input [{i}] probe error: {e}")

            # Check Final Schedule button (Read-Only probe, DO NOT CLICK)
            final_btns = page.locator("#done-button, ytcp-button#done-button, button:has-text('Planla'), button:has-text('Schedule')")
            for i in range(final_btns.count()):
                fb = final_btns.nth(i)
                if fb.is_visible():
                    btn_txt = fb.inner_text().strip()
                    results["final_schedule_button"] = {
                        "text": btn_txt,
                        "enabled": fb.is_enabled(),
                        "html": fb.evaluate("el => el.outerHTML.substring(0, 150)")
                    }
                    print(f"[PASS] Final Schedule Button Detected (READ-ONLY): '{btn_txt}' | Enabled: {fb.is_enabled()}")
                    break

    except Exception as e:
        print(f"[ERROR] YouTube Probe encountered error: {e}")

    return results


def probe_tiktok():
    print("\n" + "="*60)
    print("[TIKTOK LIVE DOM PROBE]")
    print("="*60)
    results = {
        "cdp_connected": False,
        "editor_detected": False,
        "joyride_overlay_found": False,
        "joyride_buttons": [],
        "caption_editor_found": False,
        "caption_current_text": None,
        "planla_radio_found": False,
        "simdi_radio_found": False,
        "date_input": None,
        "time_input": None,
        "final_action_button": None
    }

    tt_mgr = TikTokBrowserManager(debug_port=9223)
    try:
        with tt_mgr.connect() as (browser, context):
            results["cdp_connected"] = True
            print(f"[OK] Connected to TikTok Studio Chrome on port 9223")

            print(f"Total open TikTok pages in context: {len(context.pages)}")
            for idx, p_cand in enumerate(context.pages):
                print(f"  Tab [{idx}] URL: {p_cand.url} | Title: '{p_cand.title()}'")
                if "tiktok.com" in p_cand.url:
                    page = p_cand

            if not page:
                page = context.pages[0] if context.pages else context.new_page()

            # Bring active page to front
            try:
                page.bring_to_front()
            except Exception:
                pass

            print(f"Inspecting TikTok page URL: {page.url}")
            print(f"Page frames count: {len(page.frames)}")
            for f_idx, f in enumerate(page.frames):
                print(f"  Frame [{f_idx}] Name: '{f.name}' | URL: {f.url}")

            # Check if there is an upload button or upload container or editor
            print("\n--- TikTok Top Level Elements ---")
            btns = page.locator("button, div[role='button'], input[type='file']")
            print(f"Found {btns.count()} button/input elements on TikTok page.")
            for i in range(min(btns.count(), 15)):
                b = btns.nth(i)
                try:
                    txt = b.inner_text().strip().replace('\n', ' ')
                    tag = b.evaluate("el => el.tagName")
                    role = b.get_attribute("role") or ""
                    print(f"  El [{i}] Tag: {tag} | Role: {role} | Text: '{txt[:50]}'")
                except Exception:
                    pass

            # Check for Editor / Uploaded state
            content_text = page.content().lower()
            if "yüklendi" in content_text or "uploaded" in content_text or "zen_temple" in content_text or "oasis" in content_text:
                results["editor_detected"] = True
                print("[PASS] TikTok Studio Editor session detected with uploaded video.")

            # Check React Joyride Overlay
            joyride_portals = page.locator("#react-joyride-portal, div[data-test-id='overlay'], div.react-joyride__overlay, div[class*='joyride']")
            if joyride_portals.count() > 0:
                for i in range(joyride_portals.count()):
                    jp = joyride_portals.nth(i)
                    if jp.is_visible():
                        results["joyride_overlay_found"] = True
                        print(f"[DETECTED] React Joyride Overlay visible in DOM ({i}): {jp.evaluate('el => el.outerHTML.substring(0, 120)')}")

            # Check buttons inside Joyride Portal
            j_btns = page.locator("#react-joyride-portal button, div[class*='joyride'] button")
            for i in range(j_btns.count()):
                jb = j_btns.nth(i)
                try:
                    if jb.is_visible():
                        b_txt = jb.inner_text().strip()
                        b_html = jb.evaluate("el => el.outerHTML.substring(0, 150)")
                        results["joyride_buttons"].append({"text": b_txt, "html": b_html})
                        print(f"  Joyride Button [{i}]: '{b_txt}' | HTML: {b_html}")
                except Exception:
                    pass

            # Probe Caption Editor
            print("\n--- Probing Caption Editor (DraftEditor) ---")
            caption_cands = page.locator("div[contenteditable='true'][role='combobox'], div[contenteditable='true'][class*='editor'], div[class*='public-DraftEditor-content']")
            for i in range(caption_cands.count()):
                ce = caption_cands.nth(i)
                try:
                    if ce.is_visible():
                        results["caption_editor_found"] = True
                        c_txt = ce.inner_text().strip()
                        results["caption_current_text"] = c_txt
                        c_html = ce.evaluate("el => el.outerHTML.substring(0, 200)")
                        print(f"[PASS] Found Caption Editor: Current text: '{c_txt}' | HTML: {c_html}")
                        break
                except Exception:
                    pass

            # Probe Planla / Şimdi Radios
            print("\n--- Probing Schedule Mode Radios (Planla / Şimdi) ---")
            radios = page.locator("div[role='radio'], input[type='radio'], div[class*='radio'], label[class*='radio']")
            for i in range(radios.count()):
                r = radios.nth(i)
                try:
                    if r.is_visible():
                        txt = r.inner_text().strip()
                        r_html = r.evaluate("el => el.outerHTML.substring(0, 160)")
                        if "planla" in txt.lower() or "schedule" in txt.lower():
                            results["planla_radio_found"] = True
                            print(f"[PASS] Found 'Planla' radio: '{txt}' | HTML: {r_html}")
                        elif "şimdi" in txt.lower() or "now" in txt.lower():
                            results["simdi_radio_found"] = True
                            print(f"[PASS] Found 'Şimdi' radio: '{txt}' | HTML: {r_html}")
                except Exception:
                    pass

            # Check Final Action Button (Read-Only probe, DO NOT CLICK)
            final_btns = page.locator("button:has-text('Planla'), button:has-text('Schedule'), button:has-text('Paylaş'), button:has-text('Post')")
            for i in range(final_btns.count()):
                fb = final_btns.nth(i)
                if fb.is_visible():
                    b_txt = fb.inner_text().strip()
                    results["final_action_button"] = {
                        "text": b_txt,
                        "enabled": fb.is_enabled(),
                        "html": fb.evaluate("el => el.outerHTML.substring(0, 150)")
                    }
                    print(f"[PASS] Final Action Button Detected (READ-ONLY): '{b_txt}' | Enabled: {fb.is_enabled()}")
                    break

    except Exception as e:
        print(f"[ERROR] TikTok Probe encountered error: {e}")

    return results

if __name__ == "__main__":
    yt_res = probe_youtube()
    tt_res = probe_tiktok()

    # Save probe dump to diagnostics output
    out_dir = Path("automation/diagnostics")
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "last_probe_result.json", "w", encoding="utf-8") as f:
        json.dump({"youtube": yt_res, "tiktok": tt_res}, f, indent=2, ensure_ascii=False)

    print("\n" + "="*60)
    print("PROBE COMPLETED. Saved to automation/diagnostics/last_probe_result.json")
    print("="*60)
