"""
Content mode registry -- the single source of truth for what a Reel's content_mode
means to the rest of the pipeline, above all its audio policy.

Before this module the "silent" decision was hardcoded in four independent places
(concatenator -an, validator -an, eligibility has_audio rejection, and the Flow prompt's
negative exclusions). Adding a second mode by editing all four separately is exactly how
they drift apart, so every one of them now asks this module instead.

Registration is fail-closed: an unknown content_mode is never live-eligible, and its
audio policy is FORBIDDEN. A Reel whose mode nobody recognises does not reach a platform.
"""
from dataclasses import dataclass
from typing import Dict, FrozenSet, Optional

# Audio policies. FORBIDDEN and REQUIRED are both hard gates -- a mode that requires
# ambient audio is just as broken when the track is missing as a silent mode is when a
# stray track survives.
AUDIO_FORBIDDEN = "FORBIDDEN"
AUDIO_REQUIRED = "REQUIRED"

# The original V3 mode: 30s silent step-by-step architectural construction.
SILENT_STEP_BY_STEP = "silent_global_step_by_step"

# 2026-08-19: 30s dramatised real-history story Reels that keep Flow's own diegetic
# ambience (wind, water, birds, crowd murmur, collapsing stone). Still no narration and
# no dialogue -- see StoryPlanner.NEGATIVE_EXCLUSIONS, which keeps banning both.
NARRATIVE_AMBIENT_STORY = "narrative_ambient_story"


@dataclass(frozen=True)
class ContentModeSpec:
    mode: str
    audio_policy: str
    segment_count: int
    live_eligible: bool
    description: str


_REGISTRY: Dict[str, ContentModeSpec] = {
    SILENT_STEP_BY_STEP: ContentModeSpec(
        mode=SILENT_STEP_BY_STEP,
        audio_policy=AUDIO_FORBIDDEN,
        segment_count=3,
        live_eligible=True,
        description="Silent 30s step-by-step architectural construction (V3 original).",
    ),
    NARRATIVE_AMBIENT_STORY: ContentModeSpec(
        mode=NARRATIVE_AMBIENT_STORY,
        audio_policy=AUDIO_REQUIRED,
        segment_count=3,
        live_eligible=True,
        description="30s dramatised real-history story with Flow's native ambient audio.",
    ),
}

LIVE_ELIGIBLE_CONTENT_MODES: FrozenSet[str] = frozenset(
    spec.mode for spec in _REGISTRY.values() if spec.live_eligible
)


def get_spec(content_mode: Optional[str]) -> Optional[ContentModeSpec]:
    """Returns the registered spec, or None for an unknown/missing mode."""
    if not content_mode:
        return None
    return _REGISTRY.get(str(content_mode))


def is_live_eligible_mode(content_mode: Optional[str]) -> bool:
    spec = get_spec(content_mode)
    return spec is not None and spec.live_eligible


def audio_policy(content_mode: Optional[str]) -> str:
    """Audio policy for a mode. Unknown modes are treated as silent-only (fail-closed)."""
    spec = get_spec(content_mode)
    return spec.audio_policy if spec is not None else AUDIO_FORBIDDEN


def requires_audio(content_mode: Optional[str]) -> bool:
    return audio_policy(content_mode) == AUDIO_REQUIRED


def forbids_audio(content_mode: Optional[str]) -> bool:
    return audio_policy(content_mode) == AUDIO_FORBIDDEN


def check_audio_stream(content_mode: Optional[str], has_audio: bool) -> tuple:
    """
    Validates an actual media file's audio presence against its mode.
    Returns (ok, reason) -- reason is "" when ok.
    """
    if requires_audio(content_mode):
        if not has_audio:
            return False, f"Video has no audio stream (content_mode '{content_mode}' requires ambient audio)"
        return True, ""

    if has_audio:
        return False, f"Video contains audio stream (content_mode '{content_mode}' requires a silent video)"
    return True, ""
