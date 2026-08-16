"""
Main Content Engine interface and Provider implementation.
Provides candidate generation, diversity ranking, and prompt planning.
"""
from abc import ABC, abstractmethod
import random
from typing import List, Dict, Any, Optional

from .concepts import CATEGORIES, ConceptDefinition
from .diversity import calculate_diversity_score, compute_similarity
from .prompt_engine import PromptEngine, ReelConceptPlan

class ContentProvider(ABC):
    """Abstract interface for generating video concept plans."""

    @abstractmethod
    def generate_plans(
        self,
        count: int,
        past_records: List[Dict[str, Any]],
        duration_seconds: int = 10
    ) -> List[ReelConceptPlan]:
        pass

class TemplateContentProvider(ContentProvider):
    """Deterministic, rule-based content provider using curated categories & diversity ranking."""

    def __init__(self, categories: Optional[List[ConceptDefinition]] = None):
        self.categories = categories or CATEGORIES

    def generate_plans(
        self,
        count: int,
        past_records: List[Dict[str, Any]],
        duration_seconds: int = 10
    ) -> List[ReelConceptPlan]:
        """
        Generate candidate combinatorial concepts, score each against history,
        and select top N diverse, non-duplicate plans.
        """
        # Collect recent category keys from past records (most recent first)
        recent_categories: List[str] = []
        for r in past_records:
            cat = r.get("topic_key") or r.get("category") or r.get("title", "")
            if cat:
                recent_categories.append(str(cat))

        # Generate pool of candidate variations (at least 25-40 candidates)
        candidates = []
        for concept in self.categories:
            for env in concept.environments[:2]:
                for arch in concept.architectures[:2]:
                    transformation = concept.transformations[0] if concept.transformations else "seamless construction progression"
                    camera = concept.camera_styles[0] if concept.camera_styles else "smooth cinematic camera movement"
                    lighting = concept.lighting_schemes[0] if concept.lighting_schemes else "crisp golden hour lighting"
                    materials = concept.materials[0] if concept.materials else "premium realistic materials"
                    reveal = concept.reveals[0] if concept.reveals else "completed architectural masterpiece"

                    final_score, novelty, penalty = calculate_diversity_score(
                        concept=concept,
                        selected_env=env,
                        selected_arch=arch,
                        past_records=past_records,
                        recently_used_categories=recent_categories
                    )

                    # Only consider candidates with reasonable novelty (no near-duplicates)
                    if novelty >= 0.40:
                        plan = PromptEngine.build_concept_plan(
                            concept=concept,
                            env=env,
                            arch=arch,
                            transformation=transformation,
                            camera=camera,
                            lighting=lighting,
                            materials=materials,
                            reveal=reveal,
                            diversity_score=final_score,
                            duration_seconds=duration_seconds
                        )
                        candidates.append((final_score, plan))

        # Sort candidates descending by diversity/novelty score
        candidates.sort(key=lambda x: x[0], reverse=True)

        # Pick top N non-colliding candidates
        selected_plans: List[ReelConceptPlan] = []
        selected_categories: set = set()

        for score, plan in candidates:
            if len(selected_plans) >= count:
                break

            # Avoid picking the same category twice in the same batch run
            cat_group = plan.concept_def.category_group
            slug = plan.concept_def.id_slug
            if slug in selected_categories:
                continue

            selected_plans.append(plan)
            selected_categories.add(slug)

        # Fallback if candidates were somehow restricted
        if len(selected_plans) < count:
            for score, plan in candidates:
                if len(selected_plans) >= count:
                    break
                if plan not in selected_plans:
                    selected_plans.append(plan)

        return selected_plans

class ContentEngine:
    """High level facade for content generation."""

    def __init__(self, provider: Optional[ContentProvider] = None):
        self.provider = provider or TemplateContentProvider()

    def generate_next_reels(
        self,
        count: int,
        past_records: List[Dict[str, Any]],
        duration_seconds: int = 10
    ) -> List[ReelConceptPlan]:
        return self.provider.generate_plans(count, past_records, duration_seconds)
