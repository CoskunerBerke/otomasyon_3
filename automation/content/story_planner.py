"""
Segment planner for narrative_ambient_story Reels.

Where SegmentPlanner builds three construction stages (FOUNDATION -> MAIN -> DETAILS),
this builds three story beats over the same 3x10s structure and the same continuity
contract, so the downloader, concatenator and manifest round-trip need no special case:

    BEFORE    -- the place alive, as its history records it
    THE_TURN  -- the documented event that ended that life
    WHAT_REMAINS -- what a camera finds there today

The audio difference is deliberate and narrow. Narration and dialogue stay banned exactly
as in the silent pipeline -- the ambience is diegetic only (wind, water, birds, stone,
machinery, crowd murmur with no intelligible words). Flow is asked for that ambience
positively, per beat, instead of being asked for silence.
"""
import hashlib
from typing import Any, Dict, List, Tuple

from .duration_rules import DEFAULT_SEGMENT_DURATION
from .segment_planner import ContinuityContext, SegmentPlan
from .story_concepts import StoryConcept

STORY_BEATS = ("BEFORE", "THE_TURN", "WHAT_REMAINS")


class StoryPlanner:
    """Builds three continuity-locked story beats with per-beat diegetic sound design."""

    # Speech stays banned. The ambience these Reels want is environmental, not narrated:
    # a voiceover would also make every Reel need a script, a language and a voice, none
    # of which the pipeline has or wants.
    NEGATIVE_EXCLUSIONS = [
        "narration",
        "voiceover",
        "dialogue",
        "intelligible speech",
        "song lyrics",
        "music soundtrack",
        "captions",
        "subtitles",
        "written text",
        "letters",
        "numbers",
        "logos",
        "brand names",
        "watermarks",
        "recognisable human faces",
        "modern tourists",
        "gore",
        "human bodies",
        "distorted architecture",
        "melting objects",
        "chaotic camera movement",
        "random floating objects",
        "teleporting buildings",
        "magic morph",
        "grainy artifacts",
        "blurry textures",
        "jittery animations",
    ]

    # Every beat repeats these so Flow keeps one continuous place across three renders.
    AUDIO_DIRECTION = (
        "natural diegetic ambience only, recorded as if on location, no narration, "
        "no dialogue, no intelligible speech, no music track"
    )

    @classmethod
    def create_continuity_context(
        cls,
        concept: StoryConcept,
        env: str,
        arch: str,
        camera: str,
        lighting: str,
        materials: str,
    ) -> ContinuityContext:
        """
        Visual anchor shared by all three beats. Unlike the construction pipeline, the
        terrain here is the inhabited place itself -- the story changes what happens to
        it, never which place it is.
        """
        return ContinuityContext(
            environment=env,
            terrain=f"the real setting of {concept.name}: {env}",
            architecture_style=arch,
            structure_identity=f"{concept.name} ({concept.category_group})",
            materials=materials,
            scale="real-world documentary scale, true to the actual site",
            camera_direction=camera,
            camera_height="grounded cinematic documentary perspective",
            lighting=lighting,
            time_of_day="consistent single time of day across all three beats",
            color_palette="naturalistic documentary colour, no stylised grading",
        )

    @classmethod
    def get_story_beats(
        cls,
        concept: StoryConcept,
        env: str,
        arch: str,
        materials: str,
        transformation: str,
        reveal: str,
    ) -> Dict[str, Any]:
        """Derive the three beats from the concept's real history."""
        return {
            "s1_start": f"{env}, alive and in use exactly as {concept.name} was in its own time",
            "s1_action": (
                f"ordinary life continuing among {arch}: movement, work and weather in the place, "
                f"nothing yet wrong, the setting established clearly and calmly"
            ),
            "s1_end": (
                f"{concept.name} fully established and inhabited, {materials} intact and maintained "
                f"(the place before anything happens to it)"
            ),
            "s2_start": f"the same view of {concept.name} established in Beat 1, unchanged framing",
            "s2_action": transformation,
            "s2_end": (
                f"the event complete and the place changed by it, {arch} no longer in use "
                f"(the moment the site stops being lived in)"
            ),
            "s3_start": f"the changed site from Beat 2, same viewpoint held",
            "s3_action": (
                f"time passing over the abandoned site: weather, growth and decay settling in, "
                f"the place quietly becoming what visitors see now"
            ),
            "s3_reveal": reveal,
        }

    @classmethod
    def _build_beat_prompt(
        cls,
        concept: StoryConcept,
        continuity: ContinuityContext,
        index: int,
        beat_name: str,
        starting_state: str,
        action: str,
        ending_state: str,
        ambient: str,
        duration: int,
    ) -> str:
        """One Flow prompt for one beat, carrying both the visual and the sound direction."""
        return "\n".join([
            f"{duration}-second cinematic documentary shot, vertical 9:16, photorealistic.",
            f"BEAT {index} of 3 -- {beat_name} -- of a continuous story about {concept.name}.",
            f"HISTORICAL BASIS (depict faithfully, invent nothing): {concept.real_basis}",
            "",
            f"PLACE (identical in every beat): {continuity.structure_identity}.",
            f"SETTING: {continuity.terrain}.",
            f"ARCHITECTURE: {continuity.architecture_style}.",
            f"MATERIALS: {continuity.materials}.",
            f"CAMERA: {continuity.camera_direction}, {continuity.camera_height}.",
            f"LIGHT: {continuity.lighting}, {continuity.time_of_day}.",
            f"COLOUR: {continuity.color_palette}.",
            "",
            f"STARTS AS: {starting_state}",
            f"WHAT HAPPENS: {action}",
            f"ENDS AS: {ending_state}",
            "",
            f"SOUND: {ambient}. {cls.AUDIO_DIRECTION}.",
            "",
            f"AVOID: {', '.join(cls.NEGATIVE_EXCLUSIONS)}.",
            "Hold one continuous location and one continuous camera language so this beat "
            "cuts seamlessly against the other two.",
        ])

    @classmethod
    def plan_segments(
        cls,
        concept: StoryConcept,
        env: str,
        arch: str,
        transformation: str,
        camera: str,
        lighting: str,
        materials: str,
        reveal: str,
        duration_per_segment: int = DEFAULT_SEGMENT_DURATION,
    ) -> Tuple[ContinuityContext, List[SegmentPlan]]:
        """Builds the continuity context and the three story SegmentPlans."""
        continuity = cls.create_continuity_context(
            concept=concept, env=env, arch=arch, camera=camera, lighting=lighting, materials=materials
        )
        beats = cls.get_story_beats(
            concept=concept, env=env, arch=arch, materials=materials,
            transformation=transformation, reveal=reveal,
        )

        ambience = concept.ambient_sounds or {}
        specs = [
            (1, STORY_BEATS[0], beats["s1_start"], beats["s1_action"], beats["s1_end"], ambience.get("before", "")),
            (2, STORY_BEATS[1], beats["s2_start"], beats["s2_action"], beats["s2_end"], ambience.get("turn", "")),
            (3, STORY_BEATS[2], beats["s3_start"], beats["s3_action"], beats["s3_reveal"], ambience.get("after", "")),
        ]

        segments: List[SegmentPlan] = []
        for index, beat_name, start, action, end, ambient in specs:
            prompt = cls._build_beat_prompt(
                concept=concept, continuity=continuity, index=index, beat_name=beat_name,
                starting_state=start, action=action, ending_state=end,
                ambient=ambient or "natural ambience true to this place",
                duration=duration_per_segment,
            )
            segments.append(SegmentPlan(
                index=index,
                duration_seconds=duration_per_segment,
                stage_name=beat_name,
                starting_state=start,
                action_description=action,
                ending_state=end,
                prompt=prompt,
                prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16],
            ))

        return continuity, segments
