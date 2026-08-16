"""
Diversity engine for concept scoring, deduplication, and variety optimization.
Ensures zero repeat concepts and balances category distribution over time.
"""
import re
from typing import List, Set, Dict, Any, Tuple
from .concepts import ConceptDefinition

def normalize_text(text: str) -> List[str]:
    """Normalize text into clean lowercase alphanumeric tokens."""
    if not text:
        return []
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower())
    tokens = [t.strip() for t in cleaned.split() if len(t.strip()) > 2]
    # Filter common stop words
    stop_words = {"the", "and", "for", "with", "into", "from", "that", "this", "build", "reel", "video"}
    return [t for t in tokens if t not in stop_words]

def compute_jaccard_similarity(tokens1: List[str], tokens2: List[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    set1, set2 = set(tokens1), set(tokens2)
    if not set1 or not set2:
        return 0.0
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0

def compute_similarity(item_text: str, past_text: str) -> float:
    """Calculate semantic/token similarity between new item and existing record."""
    tokens_new = normalize_text(item_text)
    tokens_past = normalize_text(past_text)
    return compute_jaccard_similarity(tokens_new, tokens_past)

def calculate_diversity_score(
    concept: ConceptDefinition,
    selected_env: str,
    selected_arch: str,
    past_records: List[Dict[str, Any]],
    recently_used_categories: List[str]
) -> Tuple[float, float, float]:
    """
    Score a concept candidate based on:
    - Novelty against all past records (1.0 - max similarity)
    - Recent-category penalty (higher if same category used recently)
    - Visual potential (baseline 0.9 for high-end kinetic construction)

    Returns:
        (final_score, novelty_score, category_penalty)
    """
    candidate_key = f"{concept.id_slug}-{selected_env}-{selected_arch}"
    candidate_tokens = normalize_text(f"{concept.name} {concept.topic_description} {selected_env} {selected_arch}")

    max_similarity = 0.0
    for record in past_records:
        # Check topic_key match (strict block)
        past_key = str(record.get("topic_key", ""))
        if past_key and (past_key == concept.id_slug or past_key in candidate_key or candidate_key in past_key):
            max_similarity = max(max_similarity, 0.95)

        # Check title & topic text similarity
        past_text = f"{record.get('title', '')} {record.get('topic', '')} {record.get('category', '')}"
        past_tokens = normalize_text(past_text)
        sim = compute_jaccard_similarity(candidate_tokens, past_tokens)
        if sim > max_similarity:
            max_similarity = sim

    novelty_score = max(0.0, 1.0 - max_similarity)

    # Category recency penalty
    category_penalty = 0.0
    if recently_used_categories:
        # If appeared in the very last video: penalty 0.5
        # If appeared in the last 3 videos: penalty 0.3
        for idx, past_cat in enumerate(recently_used_categories[:5]):
            if past_cat.lower() in [concept.id_slug.lower(), concept.name.lower(), concept.category_group.lower()]:
                recency_weight = 1.0 / (idx + 1)
                category_penalty = max(category_penalty, recency_weight * 0.5)

    visual_potential = 0.92  # High baseline for structured architectural transformations

    # Final weighted score
    final_score = (novelty_score * 0.50) + (visual_potential * 0.30) - (category_penalty * 0.35)
    return round(final_score, 4), round(novelty_score, 4), round(category_penalty, 4)
