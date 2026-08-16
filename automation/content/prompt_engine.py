"""
Prompt Generation Engine for Google Flow satisfying transformation videos.
Builds 30-second 3-segment plans with timing breakdown, strict negative exclusions,
and robust visual continuity across all three 10-second segments.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from .concepts import ConceptDefinition
from .duration_rules import (
    DEFAULT_VIDEO_DURATION,
    DEFAULT_SEGMENT_DURATION,
    DEFAULT_FINAL_DURATION,
    sanitize_video_duration
)
from .segment_planner import ContinuityContext, SegmentPlan, SegmentPlanner

@dataclass
class ReelConceptPlan:
    concept_def: ConceptDefinition
    title: str
    topic_description: str
    topic_key: str
    category: str
    environment: str
    architecture: str
    transformation: str
    camera_style: str
    lighting: str
    materials: str
    reveal: str
    prompt: str
    diversity_score: float
    pipeline_version: int = 3
    content_mode: str = "silent_global_step_by_step"
    final_duration_seconds: int = DEFAULT_FINAL_DURATION
    segment_count: int = 3
    segment_duration_seconds: int = DEFAULT_SEGMENT_DURATION
    continuity: Optional[ContinuityContext] = None
    segments: List[SegmentPlan] = field(default_factory=list)

class PromptEngine:
    """Builds structured, high-conversion staged prompts for Google Flow."""

    NEGATIVE_EXCLUSIONS = SegmentPlanner.NEGATIVE_EXCLUSIONS

    @classmethod
    def generate_prompt(
        cls,
        concept: ConceptDefinition,
        env: str,
        arch: str,
        transformation: str,
        camera: str,
        lighting: str,
        materials: str,
        reveal: str,
        duration_seconds: int = DEFAULT_SEGMENT_DURATION
    ) -> str:
        """Construct prompt for a single segment (or Segment 1 by default)."""
        _, segments = SegmentPlanner.plan_segments(
            concept=concept,
            env=env,
            arch=arch,
            transformation=transformation,
            camera=camera,
            lighting=lighting,
            materials=materials,
            reveal=reveal,
            duration_per_segment=duration_seconds
        )
        return segments[0].prompt

    @classmethod
    def build_concept_plan(
        cls,
        concept: ConceptDefinition,
        env: str,
        arch: str,
        transformation: str,
        camera: str,
        lighting: str,
        materials: str,
        reveal: str,
        diversity_score: float,
        duration_seconds: int = DEFAULT_SEGMENT_DURATION
    ) -> ReelConceptPlan:
        """Assemble full 3-segment concept plan object."""
        continuity, segments = SegmentPlanner.plan_segments(
            concept=concept,
            env=env,
            arch=arch,
            transformation=transformation,
            camera=camera,
            lighting=lighting,
            materials=materials,
            reveal=reveal,
            duration_per_segment=duration_seconds
        )

        topic_key = f"{concept.id_slug}-{env.split()[-1]}-{arch.split()[-1]}".lower().replace(" ", "-")

        return ReelConceptPlan(
            concept_def=concept,
            title=f"{concept.default_title}",
            topic_description=f"{env.capitalize()} transforming into {arch} ({concept.name})",
            topic_key=topic_key,
            category="Satisfying Transformation",
            environment=env,
            architecture=arch,
            transformation=transformation,
            camera_style=camera,
            lighting=lighting,
            materials=materials,
            reveal=reveal,
            prompt=segments[0].prompt,
            diversity_score=diversity_score,
            pipeline_version=3,
            content_mode="silent_global_step_by_step",
            final_duration_seconds=30,
            segment_count=len(segments),
            segment_duration_seconds=duration_seconds,
            continuity=continuity,
            segments=segments
        )
