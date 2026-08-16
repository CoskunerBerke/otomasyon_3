"""
Chrome launcher and CDP (Chrome DevTools Protocol) helper for Reels AI Factory.
Launches genuine Google Chrome with dedicated user data directory and remote debugging port.
"""
import os
import sys
import time
import urllib.request
import urllib.error
import subprocess
import shutil
from pathlib import Path
from typing import Optional

def get_default_chrome_profile_path() -> Path:
    """
    Get the default dedicated Chrome profile path outside of OneDrive.
    Defaults to %LOCALAPPDATA%\\ReelsAIFactory\\chrome-profile.
    """
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data)
    else:
        base_dir = Path.home() / "AppData" / "Local"

    profile_dir = (base_dir / "ReelsAIFactory" / "chrome-profile").resolve()
    return profile_dir

def detect_chrome_path() -> Path:
    """
    Detect the real Google Chrome executable on Windows without using bundled Chromium.
    Checks Registry App Paths and standard program file directories.
    """
    # 1. Check Windows Registry App Paths
    if sys.platform == "win32":
        try:
            import winreg
            for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    reg_key = winreg.OpenKey(
                        root_key,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
                    )
                    val, _ = winreg.QueryValueEx(reg_key, "")
                    winreg.CloseKey(reg_key)
                    if val and Path(val).exists():
                        return Path(val).resolve()
                except OSError:
                    continue
        except Exception:
            pass

    # 2. Check standard Windows file system paths
    program_files = os.getenv("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_app_data = os.getenv("LOCALAPPDATA", r"C:\Users\Default\AppData\Local")

    candidates = [
        Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    # 3. Check system PATH
    which_chrome = shutil.which("chrome")
    if which_chrome and Path(which_chrome).exists():
        return Path(which_chrome).resolve()

    raise FileNotFoundError(
        "GOOGLE_CHROME_NOT_FOUND: Google Chrome tarayıcısı bulunamadı. "
        "Lütfen sisteminizde Google Chrome'un kurulu olduğundan emin olun."
    )

def is_cdp_available(port: int = 9222) -> bool:
    """
    Check if Chrome DevTools Protocol endpoint is responding on the given port.
    """
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False

def launch_chrome_debug(
    chrome_path: Path,
    profile_dir: Path,
    port: int = 9222,
    url: str = "https://labs.google/fx/tools/flow"
) -> subprocess.Popen:
    """
    Launch real Google Chrome with a dedicated non-default user data directory
    and remote debugging port.
    """
    profile_dir = Path(profile_dir).resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        url
    ]

    # Launch detached process on Windows so it continues running independently
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True
    )
    return proc

def wait_for_cdp(port: int = 9222, timeout_seconds: int = 15) -> bool:
    """
    Poll until Chrome's CDP endpoint is responding or timeout occurs.
    """
    start = time.time()
    while time.time() - start < timeout_seconds:
        if is_cdp_available(port):
            return True
        time.sleep(0.5)
    return False

def ensure_chrome_running(
    chrome_path: Optional[Path] = None,
    profile_dir: Optional[Path] = None,
    port: int = 9222,
    url: str = "https://labs.google/fx/tools/flow",
    timeout_seconds: int = 15
) -> bool:
    """
    Ensure a dedicated Chrome instance is active with remote debugging enabled.
    Auto-launches Chrome if not already running.
    """
    if is_cdp_available(port):
        return True

    if chrome_path is None:
        chrome_path = detect_chrome_path()

    if profile_dir is None:
        profile_dir = get_default_chrome_profile_path()

    launch_chrome_debug(chrome_path, profile_dir, port, url)
    return wait_for_cdp(port, timeout_seconds)

def main_login_flow():
    """
    Entry point for FLOW_LOGIN.bat.
    Opens Chrome for manual human login.
    """
    print("========================================================")
    print("      GOOGLE FLOW - GOOGLE CHROME GİRİŞİ")
    print("========================================================")

    try:
        chrome_path = detect_chrome_path()
        print(f"Tespit Edilen Chrome: {chrome_path}")
    except FileNotFoundError as e:
        print(f"\n[HATA] {e}")
        input("\nDevam etmek için Enter'a basın...")
        sys.exit(1)

    profile_dir = get_default_chrome_profile_path()
    port = 9222
    url = "https://labs.google/fx/tools/flow"

    # Attempt to load custom config if available
    try:
        from automation.config import load_config
        cfg = load_config()
        profile_dir = cfg.chrome_profile_dir
        port = cfg.chrome_debug_port
        url = cfg.flow_url
    except Exception:
        pass

    profile_dir.mkdir(parents=True, exist_ok=True)
    print(f"Dedicated Profil Yolu: {profile_dir}")
    print(f"Remote Debugging Port: {port}")
    print(f"Hedef URL: {url}")
    print("--------------------------------------------------------")

    if is_cdp_available(port):
        print("[BİLGİ] Chrome zaten remote debugging modunda açık.")
    else:
        print("Google Chrome başlatılıyor...")
        launch_chrome_debug(chrome_path, profile_dir, port, url)
        if wait_for_cdp(port, 15):
            print("[BİLGİ] Chrome başarıyla bağlandı (CDP Aktif).")
        else:
            print("[UYARI] Chrome başlatıldı ancak CDP portuna hemen bağlanılamadı.")

    print()
    print("========================================================")
    print("👉 TALİMAT:")
    print("1. Açılan Google Chrome penceresinde Google hesabınıza")
    print("   tamamen MANUEL olarak giriş yapın.")
    print("2. Google Flow ana ekranının açıldığından emin olun.")
    print("3. CHROME PENCERESİNİ AÇIK BIRAKIN!")
    print("   (Otomasyon bu açık Chrome penceresine bağlanacaktır.)")
    print("========================================================")
    print()

if __name__ == "__main__":
    main_login_flow()
