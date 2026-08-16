"""
Unit tests for Chrome executable detection, dedicated profile isolation,
CDP endpoint checks, and CDPBrowserManager functionality.
"""
import os
import json
import pytest
from pathlib import Path
from automation.flow.chrome_launcher import (
    detect_chrome_path,
    get_default_chrome_profile_path,
    is_cdp_available
)
from automation.flow.browser import CDPBrowserManager
from automation.config import load_config, AppConfig

def test_detect_chrome_executable():
    chrome_path = detect_chrome_path()
    assert chrome_path is not None
    assert chrome_path.exists()
    assert "chrome.exe" in str(chrome_path).lower()

def test_default_chrome_profile_in_localappdata():
    profile_path = get_default_chrome_profile_path()
    assert profile_path is not None
    assert "ReelsAIFactory" in str(profile_path)
    assert "chrome-profile" in str(profile_path)

    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        assert str(profile_path).lower().startswith(local_app_data.lower())

def test_custom_chrome_profile_override(tmp_path: Path):
    vault_dir = tmp_path / "Vault"
    vault_dir.mkdir(parents=True)
    custom_profile = tmp_path / "Custom_Chrome_Profile"

    cfg_file = tmp_path / "custom_config.json"
    cfg_data = {
        "vault_path": str(vault_dir),
        "chrome_profile_path": str(custom_profile),
        "chrome_debug_port": 9333,
        "videos_per_run": 1
    }
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    cfg = load_config(config_file=str(cfg_file))
    assert cfg.chrome_profile_dir == custom_profile.resolve()
    assert cfg.chrome_debug_port == 9333

def test_cdp_availability_on_closed_port():
    # An unused high port should return False
    assert is_cdp_available(port=59999) is False

def test_cdp_browser_manager_instantiation(tmp_path: Path):
    vault_dir = tmp_path / "Vault"
    vault_dir.mkdir(parents=True)
    output_dir = tmp_path / "Output"

    cfg = AppConfig(
        vault_path=vault_dir,
        output_path=output_dir,
        chrome_debug_port=9222
    )
    mgr = CDPBrowserManager(cfg)
    assert mgr.config.chrome_debug_port == 9222
