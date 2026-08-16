from __future__ import annotations

import logging
import subprocess
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

TARGET_ISO = "2026-08-16T19:30:00+03:00"
EXPECTED_USER = "@kitchenverse360"
REEL_ID = "REEL-2026-0010"
TITLE = "Japanese Zen Temple Transformation in 30 Seconds"
DESCRIPTION = "Building Japanese Zen Temple from the ground up in 30 seconds. Would you live here? ✨"
HASHTAGS = ["#satisfying", "#transformation", "#build", "#architecture", "#timelapse", "#aitok"]

LOG = logging.getLogger("ReelsAIFactory.TikTokReuploadRecovery")


def ffprobe_duration(path: Path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=12,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def candidate_roots():
    roots = [PROJECT_ROOT]
    home = Path.home()
    for p in [
        home / "OneDrive" / "Masaüstü" / "AI_Reels",
        home / "Desktop" / "AI_Reels",
        home / "Masaüstü" / "AI_Reels",
    ]:
        if p.exists() and p not in roots:
            roots.append(p)
    return roots


def find_exact_final_video() -> Path | None:
    candidates = []
    seen = set()

    for base in candidate_roots():
        try:
            for p in base.rglob("*.mp4"):
                key = str(p.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)

                name = p.name.lower()
                if (
                    "reel-2026-0010" in name
                    or "japanese_zen_temple" in name
                    or ("japanese" in name and "zen" in name and "temple" in name)
                ):
                    duration = ffprobe_duration(p)
                    candidates.append((p, duration, p.stat().st_size))
        except Exception:
            continue

    if not candidates:
        print("[ABORT] REEL-2026-0010 MP4 file could not be found.")
        return None

    print("[VIDEO SEARCH] Candidates:")
    for p, duration, size in candidates:
        d = "unknown" if duration is None else f"{duration:.2f}s"
        print(f"  - {p} | duration={d} | size={size}")

    valid = [
        item for item in candidates
        if item[1] is not None and 29.0 <= item[1] <= 31.5
    ]

    if len(valid) == 1:
        return valid[0][0]

    if len(valid) > 1:
        # Prefer the largest final encode among 30-second candidates.
        valid.sort(key=lambda x: x[2], reverse=True)
        chosen = valid[0][0]
        print(f"[VIDEO SEARCH] Multiple ~30s files found; largest candidate selected: {chosen}")
        return chosen

    # If ffprobe was unavailable, accept only when exactly one named candidate exists.
    if len(candidates) == 1 and candidates[0][1] is None:
        print("[VIDEO SEARCH] ffprobe unavailable; only one named candidate exists, selecting it.")
        return candidates[0][0]

    print("[ABORT] Could not uniquely identify the final ~30s Reel. No upload performed.")
    return None


def find_tiktok_page(browser):
    pages = []
    for context in browser.contexts:
        for page in context.pages:
            if "tiktok.com" in (page.url or "").lower():
                pages.append(page)

    if not pages:
        return None

    for page in pages:
        if "tiktokstudio/upload" in (page.url or "").lower():
            return page

    return pages[0]


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    target_dt = datetime.fromisoformat(TARGET_ISO)
    now = datetime.now(target_dt.tzinfo)

    print("=" * 68)
    print(" REELS AI FACTORY - TIKTOK REUPLOAD + SCHEDULE RECOVERY")
    print("=" * 68)
    print("YouTube:       HARD SKIP - NEVER CONNECTED")
    print("TikTok:        @kitchenverse360")
    print("Reel:          REEL-2026-0010")
    print("Target:        2026-08-16 19:30")
    print("Upload policy: ONLY the exact existing REEL-2026-0010 final MP4")
    print("=" * 68)

    if target_dt <= now + timedelta(minutes=15):
        print(f"[ABORT] Target slot is too close or in the past. Now={now.isoformat()}")
        return 2

    video = find_exact_final_video()
    if video is None:
        return 3

    print(f"[VIDEO] Selected final file: {video}")

    record = SimpleNamespace(
        reel_id=REEL_ID,
        title=TITLE,
        description=DESCRIPTION,
        hashtags=HASHTAGS,
        scheduled_at_local=TARGET_ISO,
    )

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
            page = find_tiktok_page(browser)
            if page is None:
                print("[ABORT] No TikTok page found on CDP port 9223. Run TIKTOK_LOGIN.bat first.")
                return 4

            observer = TikTokUIObserver(page)

            if not observer.is_logged_in():
                print("[ABORT] TikTok Studio session is not logged in.")
                return 5

            ok_user, detected_user, user_msg = observer.verify_logged_in_username(EXPECTED_USER)
            print(f"[ACCOUNT] {user_msg}")
            if not ok_user:
                print(f"[ABORT] Wrong TikTok account: {detected_user}")
                return 6

            # Navigate only to TikTok Studio upload. Never YouTube.
            if "tiktokstudio/upload" not in (page.url or "").lower():
                page.goto("https://www.tiktok.com/tiktokstudio/upload", wait_until="domcontentloaded", timeout=15000)
                time.sleep(1.5)

            state = observer.detect_editor_state()
            print(f"[EDITOR BEFORE UPLOAD] {state}")

            # If the editor somehow came back, don't upload again.
            if state != "LOADED_EDITOR":
                print("[UPLOAD] Loading exact REEL-2026-0010 final MP4 into TikTok Studio...")
                if not observer.upload_file(video):
                    print("[ABORT] TikTok file input / file chooser could not be used.")
                    return 7

                if not observer.wait_for_upload_completion(timeout_seconds=120):
                    print("[ABORT] TikTok upload did not finish processing.")
                    return 8

                time.sleep(1.0)
                state = observer.detect_editor_state()
                print(f"[EDITOR AFTER UPLOAD] {state}")
                if state != "LOADED_EDITOR":
                    print("[ABORT] Upload finished but loaded editor was not detected.")
                    return 9
            else:
                print("[UPLOAD SKIPPED] Loaded editor is already present.")

            try:
                observer.dismiss_onboarding_overlay_if_present()
            except Exception:
                pass

            ok_cap, cap_msg = observer.replace_caption(DESCRIPTION, HASHTAGS)
            print(f"[CAPTION] {cap_msg}")
            if not ok_cap:
                print("[ABORT] Caption could not be replaced.")
                return 10

            # AI disclosure is mandatory for REEL-2026-0010
            ai_ok = observer.toggle_ai_disclosure(True)
            print(f"[AI DISCLOSURE] {'PASS' if ai_ok else 'FAILED'}")
            if not ai_ok:
                print("[ABORT] AI-generated content disclosure could not be enabled/verified. Planla NOT clicked.")
                return 101

            ok_mode, mode_msg = observer.select_schedule_mode("SCHEDULE")
            print(f"[MODE] {mode_msg}")
            if not ok_mode:
                print("[ABORT] Planla/Schedule mode could not be activated.")
                return 11

            ok_dt, dt_msg = observer.set_schedule_datetime(TARGET_ISO)
            print(f"[DATETIME SET] {dt_msg}")
            if not ok_dt:
                print("[ABORT] Exact TikTok target datetime could not be set.")
                return 12

            ok_verify, verify_msg = observer.verify_schedule_datetime(TARGET_ISO)
            print(f"[DATETIME READBACK] {verify_msg}")
            if not ok_verify:
                print("[ABORT] TikTok datetime read-back failed. Final Planla NOT clicked.")
                return 13

            actual_date, actual_time = observer.read_schedule_datetime()
            print(f"[FINAL PRECLICK READBACK] {actual_date} {actual_time}")

            if actual_date != "2026-08-16" or actual_time != "19:30":
                print("[ABORT] Final date/time is not exactly 2026-08-16 19:30. Planla NOT clicked.")
                return 14

            print("[READY] Exact TikTok slot verified: 2026-08-16 19:30")
            print("[COMMIT] Clicking TikTok Planla...")

            success, ref = observer.click_schedule_and_verify(
                schedule_mode_verified=True,
                timeout_seconds=45,
            )
            if not success:
                print(f"[FAIL] TikTok final schedule click/confirmation failed: {ref}")
                return 15

            try:
                verify_result = observer.verify_remote_scheduled_status(expected_title=TITLE)
                print(f"[REMOTE VERIFY] {verify_result}")
            except Exception as exc:
                print(f"[REMOTE VERIFY WARNING] {exc}")

            print("=" * 68)
            print(" TIKTOK RECOVERY: SCHEDULE ACTION COMPLETED")
            print("=" * 68)
            print("YouTube was never opened or modified by this recovery script.")
            return 0

    except Exception as exc:
        LOG.exception("TikTok recovery crashed")
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 20


if __name__ == "__main__":
    raise SystemExit(main())
