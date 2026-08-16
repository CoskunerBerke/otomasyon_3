"""
Targeted Unit Tests for Config Loading and WeeklyOrchestrator Integration.
Tests:
1. load_config(base_dir=...) reads custom project config.local.json
2. load_config() without base_dir preserves default resolution
3. WeeklyOrchestrator loads real config from base_dir without triggering fallback
"""
import json
import pytest
from pathlib import Path

from automation.config import load_config, AppConfig
from automation.weekly_orchestrator import WeeklyOrchestrator


def test_load_config_with_custom_base_dir(tmp_path):
    """Test: load_config reads config.local.json from custom base_dir."""
    custom_vault = tmp_path / "CustomVault"
    custom_vault.mkdir()

    cfg_data = {
        "vault_path": str(custom_vault),
        "output_path": str(tmp_path / "CustomOutput"),
        "chrome_profile_dir": str(tmp_path / "CustomChrome"),
        "videos_per_run": 5
    }
    (tmp_path / "config.local.json").write_text(json.dumps(cfg_data), encoding="utf-8")

    loaded = load_config(base_dir=tmp_path)
    assert loaded.vault_path == custom_vault.resolve()
    assert loaded.videos_per_run == 5
    assert loaded.output_path == (tmp_path / "CustomOutput").resolve()


def test_load_config_without_base_dir_preserves_default():
    """Test: load_config() without base_dir preserves default repo root lookup."""
    loaded = load_config()
    assert isinstance(loaded, AppConfig)
    assert loaded.vault_path is not None


def test_weekly_orchestrator_loads_real_config_from_base_dir(tmp_path):
    """Test: WeeklyOrchestrator loads real config without falling back to defaults."""
    custom_vault = tmp_path / "OrchestratorVault"
    custom_vault.mkdir()

    cfg_data = {
        "vault_path": str(custom_vault),
        "output_path": str(tmp_path / "OrchOutput"),
        "chrome_profile_dir": str(tmp_path / "OrchChrome"),
        "videos_per_run": 14
    }
    (tmp_path / "config.local.json").write_text(json.dumps(cfg_data), encoding="utf-8")

    orchestrator = WeeklyOrchestrator(base_dir=tmp_path, dry_run=True)
    assert orchestrator.app_config.vault_path == custom_vault.resolve()
    assert orchestrator.app_config.videos_per_run == 14
    assert orchestrator.app_config.output_path == (tmp_path / "OrchOutput").resolve()
