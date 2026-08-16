"""
Unit tests for prompt formatting, exclusions, and aspect ratio instructions.
"""
import pytest
from automation.content.concepts import CATEGORIES
from automation.content.prompt_engine import PromptEngine

def test_prompt_generation_contains_critical_tokens():
    concept = CATEGORIES[0]
    prompt = PromptEngine.generate_prompt(
        concept=concept,
        env="empty volcanic island",
        arch="futuristic eco resort",
        transformation="wooden boardwalks and glass villas expanding across water",
        camera="cinematic aerial pullback",
        lighting="sunset glow",
        materials="teak wood and structural glass",
        reveal="fully illuminated futuristic resort",
        duration_seconds=5
    )

    assert "vertical 9:16" in prompt
    assert "satisfying transformation" in prompt
    assert "empty volcanic island" in prompt
    assert "futuristic eco resort" in prompt
    assert "no people" in prompt
    assert "no dialogue" in prompt
    assert "no voiceover" in prompt
    assert "no written text" in prompt
    assert "no watermarks" in prompt
    assert "Aspect ratio: 9:16 vertical" in prompt

def test_build_concept_plan_generates_valid_object():
    concept = CATEGORIES[1]
    plan = PromptEngine.build_concept_plan(
        concept=concept,
        env=concept.environments[0],
        arch=concept.architectures[0],
        transformation=concept.transformations[0],
        camera=concept.camera_styles[0],
        lighting=concept.lighting_schemes[0],
        materials=concept.materials[0],
        reveal=concept.reveals[0],
        diversity_score=0.88,
        duration_seconds=5
    )

    assert plan.title is not None
    assert plan.topic_key.startswith("luxury-island")
    assert plan.diversity_score == 0.88
    assert len(plan.prompt) > 100
