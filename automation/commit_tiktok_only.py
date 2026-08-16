from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright
from automation.publishing.tiktok_ui_observer import TikTokUIObserver

LOG = logging.getLogger("ReelsAIFactory.TikTokOnlyCommit")


def _all_tiktok_pages(browser):
    pages = []
    for context in browser.contexts:
        for page in context.pages:
            if "tiktok.com" in (page.url or "").lower():
                pages.append(page)
    return pages


def _state(page):
    try:
        return TikTokUIObserver(page).detect_editor_state()
    except Exception:
        return "UNKNOWN"


def _find_loaded_editor(browser):
    for page in _all_tiktok_pages(browser):
        if _state(page) == "LOADED_EDITOR":
            return page, "EXISTING_LOADED_EDITOR"

    pages = _all_tiktok_pages(browser)
    if not pages:
        return None, "NO_TIKTOK_PAGE"

    page = next((p for p in pages if "tiktokstudio" in (p.url or "").lower()), pages[0])

    for attempt in range(3):
        try:
            before = page.url
            response = page.go_back(wait_until="domcontentloaded", timeout=8000)
            time.sleep(1.2)
            after = page.url
            print(f"[RECOVERY] Browser Back {attempt+1}: {before} -> {after}")
            if _state(page) == "LOADED_EDITOR":
                return page, "RECOVERED_FROM_BROWSER_HISTORY"
            if "tiktok.com" not in (after or "").lower():
                try:
                    page.go_forward(wait_until="domcontentloaded", timeout=5000)
                except Exception:
                    pass
                break
            if before == after and response is None:
                break
        except Exception as exc:
            print(f"[RECOVERY] Browser Back unavailable: {exc}")
            break

    try:
        upload_url = "https://www.tiktok.com/tiktokstudio/upload"
        print(f"[RECOVERY] Opening TikTok Studio upload route: {upload_url}")
        page.goto(upload_url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2.0)
        if _state(page) == "LOADED_EDITOR":
            return page, "RECOVERED_FROM_UPLOAD_ROUTE"
    except Exception as exc:
        print(f"[RECOVERY] Upload route recovery failed: {exc}")

    return page, _state(page)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduled-at", default="2026-08-16T19:30:00+03:00")
    parser.add_argument("--expected-user", default="@kitchenverse360")
    parser.add_argument("--reel-id", default="REEL-2026-0010")
    parser.add_argument("--title", default="Japanese Zen Temple Transformation in 30 Seconds")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    target_dt = datetime.fromisoformat(args.scheduled_at)
    if target_dt.tzinfo is None:
        print("[ABORT] scheduled-at timezone offset missing.")
        return 2

    now = datetime.now(target_dt.tzinfo)
    if target_dt <= now + timedelta(minutes=15):
        print(f"[ABORT] Target is too close/past. Target={target_dt.isoformat()} Now={now.isoformat()}")
        return 3

    print("=" * 62)
    print(" REELS AI FACTORY - TIKTOK ONLY LIVE COMMIT / RECOVERY")
    print("=" * 62)
    print("YouTube:      HARD SKIP")
    print("New upload:   FORBIDDEN")
    print(f"TikTok:       {args.expected_user}")
    print(f"Reel:         {args.reel_id}")
    print(f"Target slot:  {target_dt.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 62)

    record = SimpleNamespace(
        reel_id=args.reel_id,
        title=args.title,
        scheduled_at_local=args.scheduled_at,
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
            page, recovery = _find_loaded_editor(browser)

            if page is None:
                print("[ABORT] No TikTok page exists on CDP port 9223.")
                return 4

            print(f"[RECOVERY RESULT] {recovery}")
            print(f"[PAGE] {page.url}")

            observer = TikTokUIObserver(page)
            state = observer.detect_editor_state()
            print(f"[EDITOR] {state}")

            if state != "LOADED_EDITOR":
                print("[ABORT] TikTok editor session is genuinely gone.")
                print("[IMPORTANT] Nothing was uploaded and no final button was clicked.")
                print("[NEXT] The exact Reel must be re-loaded once into TikTok Studio before commit.")
                return 7

            if not observer.is_logged_in():
                print("[ABORT] TikTok session is not logged in.")
                return 5

            ok_user, detected, msg = observer.verify_logged_in_username(args.expected_user)
            print(f"[ACCOUNT] {msg}")
            if not ok_user:
                print(f"[ABORT] Wrong account: {detected}")
                return 6

            try:
                body = (page.inner_text("body") or "").lower()
            except Exception:
                body = (page.content() or "").lower()

            if not any(x in body for x in (
                "reel-2026-0010",
                "japanese_zen_temple",
                "japanese zen temple",
            )):
                print("[ABORT] Loaded editor does not match Japanese Zen Temple / REEL-2026-0010.")
                return 8

            ok_mode, mode_msg = observer.select_schedule_mode("SCHEDULE")
            print(f"[MODE] {mode_msg}")
            if not ok_mode:
                return 9

            ok_dt, dt_msg = observer.set_schedule_datetime(args.scheduled_at)
            print(f"[DATETIME SET] {dt_msg}")
            if not ok_dt:
                return 10

            ok_verify, verify_msg = observer.verify_schedule_datetime(args.scheduled_at)
            print(f"[DATETIME READBACK] {verify_msg}")
            if not ok_verify:
                print("[ABORT] Exact target slot read-back failed. Planla NOT clicked.")
                return 11

            actual_date, actual_time = observer.read_schedule_datetime()
            print(f"[FINAL PRECLICK READBACK] {actual_date} {actual_time}")
            if actual_date != target_dt.strftime("%Y-%m-%d") or actual_time != target_dt.strftime("%H:%M"):
                print("[ABORT] Final datetime mismatch. Planla NOT clicked.")
                return 12

            print("[READY] Exact 2026-08-16 19:30 verified.")
            print("[COMMIT] Clicking TikTok Planla only.")

            success, message = observer.commit_tiktok_schedule(record)
            if not success:
                print(f"[FAIL] {message}")
                return 13

            print("=" * 62)
            print(" TIKTOK ONLY COMMIT: PASS")
            print("=" * 62)
            print(message)
            print("YouTube was never opened or modified.")
            return 0

    except Exception as exc:
        LOG.exception("TikTok-only recovery commit crashed")
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
