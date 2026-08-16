"""
Unit tests for Agent Settings, Omni Flash duration compatibility,
prompt duration sanitization, and follow-up question detection.
"""
import pytest
from pathlib import Path
from automation.content.duration_rules import (
    MODEL_DURATION_RULES,
    DEFAULT_VIDEO_DURATION,
    sanitize_video_duration
)
from automation.content.prompt_engine import PromptEngine
from automation.flow.selectors import FlowSelectors

def test_model_duration_rules_omni_flash():
    assert "Omni Flash" in MODEL_DURATION_RULES
    assert 8 in MODEL_DURATION_RULES["Omni Flash"]
    assert 10 in MODEL_DURATION_RULES["Omni Flash"]
    assert 5 not in MODEL_DURATION_RULES["Omni Flash"]
    assert DEFAULT_VIDEO_DURATION == 10

def test_duration_sanitizer_converts_5_to_8():
    raw_prompt = "Create a mesmerizing 5-second vertical 9:16 satisfying transformation video. Aspect ratio: 9:16 vertical. Duration: 5 seconds."
    sanitized = sanitize_video_duration(raw_prompt, target_duration=8)
    assert "8-second" in sanitized
    assert "5-second" not in sanitized
    assert "Duration: 8 seconds" in sanitized
    assert "Duration: 5 seconds" not in sanitized

def test_duration_sanitizer_converts_15_to_8():
    raw_prompt = "Create a 15-second video. Duration: 15 seconds."
    sanitized = sanitize_video_duration(raw_prompt, target_duration=8)
    assert "8-second" in sanitized
    assert "Duration: 8 seconds" in sanitized

def test_prompt_engine_generates_8s_default():
    from automation.content.concepts import CATEGORIES
    concept = CATEGORIES[0]
    prompt = PromptEngine.generate_prompt(
        concept=concept,
        env="desert dunes",
        arch="modern villa",
        transformation="building walls",
        camera="aerial view",
        lighting="sunset",
        materials="limestone",
        reveal="villa completed",
        duration_seconds=8
    )
    assert "8-second" in prompt
    assert "Duration: 8 seconds" in prompt
    assert "5-second" not in prompt

def test_settings_selectors_defined():
    assert any("tune" in s for s in FlowSelectors.SETTINGS_BUTTON_SELECTORS)
    assert any("AUTO_APPROVE" in s for s in FlowSelectors.APPROVAL_NEVER_SELECTORS)
    assert any("Kaydet" in s or "Save" in s for s in FlowSelectors.SAVE_SETTINGS_BUTTON_SELECTORS)
