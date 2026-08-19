"""
Main Content Engine interface and Provider implementation.
Provides candidate generation, diversity ranking, and prompt planning.
"""
from abc import ABC, abstractmethod
import random
from typing import List, Dict, Any, Optional

from .concepts import CATEGORIES, ConceptDefinition
from .content_modes import NARRATIVE_AMBIENT_STORY, SILENT_STEP_BY_STEP
from .diversity import calculate_diversity_score, compute_similarity
from .prompt_engine import PromptEngine, ReelConceptPlan
from .story_concepts import STORY_CONCEPTS

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

    def _build_plan(self, **kwargs) -> ReelConceptPlan:
        """Which kind of plan this provider produces. Overridden by StoryContentProvider."""
        return PromptEngine.build_concept_plan(**kwargs)

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
                        plan = self._build_plan(
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

class StoryContentProvider(TemplateContentProvider):
    """
    Same candidate/diversity/selection loop as the construction provider, over the real
    places in STORY_CONCEPTS, producing narrative_ambient_story plans.
    """

    def __init__(self, categories: Optional[List[ConceptDefinition]] = None):
        super().__init__(categories or STORY_CONCEPTS)

    def _build_plan(self, **kwargs) -> ReelConceptPlan:
        return PromptEngine.build_story_concept_plan(**kwargs)

    def generate_plans(
        self,
        count: int,
        past_records: List[Dict[str, Any]],
        duration_seconds: int = 10
    ) -> List[ReelConceptPlan]:
        """
        Ranks every story concept as the base provider does, then round-robins across
        category groups before truncating to `count`.

        Taking the base provider's top N directly would be wrong twice over: selection
        order is publishing order and STORY_CONCEPTS is grouped by theme, so the first
        six slots would all be "Buried by Nature" -- and with novelty scores tied on a
        fresh history, four whole groups would never be reached at all.
        """
        ranked = super().generate_plans(len(self.categories), past_records, duration_seconds)
        return self._interleave_by_group(ranked)[:count]

    @staticmethod
    def _interleave_by_group(plans: List[ReelConceptPlan]) -> List[ReelConceptPlan]:
        """Round-robin across category groups, preserving each group's internal order."""
        buckets: Dict[str, List[ReelConceptPlan]] = {}
        for plan in plans:
            buckets.setdefault(plan.concept_def.category_group, []).append(plan)

        ordered: List[ReelConceptPlan] = []
        while any(buckets.values()):
            for group in list(buckets.keys()):
                if buckets[group]:
                    ordered.append(buckets[group].pop(0))
        return ordered


def provider_for_mode(content_mode: str) -> ContentProvider:
    """Maps a content_mode to the provider that produces it."""
    if content_mode == NARRATIVE_AMBIENT_STORY:
        return StoryContentProvider()
    if content_mode == SILENT_STEP_BY_STEP:
        return TemplateContentProvider()
    raise ValueError(f"No content provider registered for content_mode '{content_mode}'")


class ContentEngine:
    """High level facade for content generation."""

    def __init__(self, provider: Optional[ContentProvider] = None, content_mode: Optional[str] = None):
        if provider is None and content_mode is not None:
            provider = provider_for_mode(content_mode)
        self.provider = provider or TemplateContentProvider()

    def generate_next_reels(
        self,
        count: int,
        past_records: List[Dict[str, Any]],
        duration_seconds: int = 10
    ) -> List[ReelConceptPlan]:
        return self.provider.generate_plans(count, past_records, duration_seconds)
