"""
Unit tests for token normalization, similarity calculation, and diversity ranking.
"""
import pytest
from automation.content.concepts import CATEGORIES
from automation.content.diversity import (
    normalize_text,
    compute_jaccard_similarity,
    calculate_diversity_score
)
from automation.content.engine import TemplateContentProvider

def test_token_normalization():
    tokens = normalize_text("Futuristic-City & Megacity Construction!!")
    assert "futuristic" in tokens
    assert "city" in tokens
    assert "megacity" in tokens
    assert "construction" in tokens

def test_jaccard_similarity_exact_and_disjoint():
    tokens1 = ["desert", "megacity", "futuristic"]
    tokens2 = ["desert", "megacity", "futuristic"]
    tokens3 = ["underwater", "ocean", "coral"]

    assert compute_jaccard_similarity(tokens1, tokens2) == 1.0
    assert compute_jaccard_similarity(tokens1, tokens3) == 0.0

def test_diversity_score_penalizes_past_concept():
    concept = CATEGORIES[0] # futuristic-city
    past_records = [
        {
            "id": "REEL-2026-0001",
            "title": "Futuristic City Build",
            "topic": "barren plains transforming into futuristic city",
            "topic_key": "futuristic-city-plains-towers"
        }
    ]

    score_repeat, novelty_repeat, penalty_repeat = calculate_diversity_score(
        concept=concept,
        selected_env=concept.environments[0],
        selected_arch=concept.architectures[0],
        past_records=past_records,
        recently_used_categories=["futuristic-city"]
    )

    # Different concept: luxury island
    diff_concept = CATEGORIES[1]
    score_diff, novelty_diff, penalty_diff = calculate_diversity_score(
        concept=diff_concept,
        selected_env=diff_concept.environments[0],
        selected_arch=diff_concept.architectures[0],
        past_records=past_records,
        recently_used_categories=["futuristic-city"]
    )

    assert score_diff > score_repeat
    assert novelty_diff > novelty_repeat

def test_template_provider_generates_distinct_categories():
    provider = TemplateContentProvider()
    plans = provider.generate_plans(count=3, past_records=[])
    assert len(plans) == 3

    # Ensure no duplicates in the chosen 3 plans
    slugs = [p.concept_def.id_slug for p in plans]
    assert len(set(slugs)) == 3
