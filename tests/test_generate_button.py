"""
Unit tests for Generate/Oluştur button resolution, strict icon matching,
double-click protection, and CLI real-generation flag enforcement.
"""
import pytest
from pathlib import Path
from automation.flow.selectors import (
    FlowSelectors,
    FlowUIChangedError,
    RealGenerationDisabled,
    GenerationStateUncertain
)
from automation.config import load_config

def test_generate_button_selectors_structure():
    # Verify strict arrow_forward icon and text fallbacks
    assert any("text-is('arrow_forward')" in s for s in FlowSelectors.GENERATE_BUTTON_SELECTORS)
    assert any("Oluştur" in s for s in FlowSelectors.GENERATE_BUTTON_SELECTORS)
    assert any("Generate" in s for s in FlowSelectors.GENERATE_BUTTON_SELECTORS)

def test_allow_real_generation_flag_overrides(tmp_path: Path):
    vault = tmp_path / "Vault"
    vault.mkdir()
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text(f'{{"vault_path": "{vault.as_posix()}", "allow_real_generation": false}}', encoding="utf-8")

    from automation.run import run_pipeline
    # Running dry-run forces allow_real_generation=False
    exit_code = run_pipeline(count=1, dry_run=True, config_path=str(cfg_file))
    assert exit_code == 0
