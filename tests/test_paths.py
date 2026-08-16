"""
Unit tests for Windows Path resolution, OneDrive redirected desktop detection,
and LocalAppData browser profile isolation.
"""
import os
import json
import pytest
from pathlib import Path
from automation.config import (
    get_real_windows_desktop,
    get_default_browser_profile_path,
    load_config,
    AppConfig
)

def test_default_browser_profile_in_localappdata():
    profile_path = get_default_browser_profile_path()
    assert profile_path is not None
    # Ensure profile path contains ReelsAIFactory and profile
    assert "ReelsAIFactory" in str(profile_path)
    assert "profile" in str(profile_path)
    # Ensure profile path does NOT contain OneDrive by default
    local_app_data = os.getenv("LOCALAPPDATA", "")
    if local_app_data:
        assert str(profile_path).lower().startswith(local_app_data.lower())

def test_real_windows_desktop_exists():
    desktop_path = get_real_windows_desktop()
    assert desktop_path is not None
    assert desktop_path.exists()
    assert desktop_path.is_dir()

def test_custom_output_path_override(tmp_path: Path):
    vault_dir = tmp_path / "Vault"
    vault_dir.mkdir(parents=True)
    custom_output = tmp_path / "Custom_Reels_Output"

    cfg_file = tmp_path / "custom_config.json"
    cfg_data = {
        "vault_path": str(vault_dir),
        "output_path": str(custom_output),
        "videos_per_run": 1
    }
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    cfg = load_config(config_file=str(cfg_file))
    assert cfg.output_path == custom_output.resolve()

def test_custom_browser_profile_override(tmp_path: Path):
    vault_dir = tmp_path / "Vault"
    vault_dir.mkdir(parents=True)
    custom_profile = tmp_path / "Custom_Browser_Profile"

    cfg_file = tmp_path / "custom_config.json"
    cfg_data = {
        "vault_path": str(vault_dir),
        "browser_profile_path": str(custom_profile),
        "videos_per_run": 1
    }
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    cfg = load_config(config_file=str(cfg_file))
    assert cfg.browser_profile_dir == custom_profile.resolve()

def test_default_output_path_resolves_to_real_desktop(tmp_path: Path):
    vault_dir = tmp_path / "Vault"
    vault_dir.mkdir(parents=True)

    cfg_file = tmp_path / "default_config.json"
    cfg_data = {
        "vault_path": str(vault_dir),
        "output_path": "",
        "videos_per_run": 1
    }
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    cfg = load_config(config_file=str(cfg_file))
    real_desktop = get_real_windows_desktop()
    expected_output = (real_desktop / "AI_Reels").resolve()
    assert cfg.output_path == expected_output
