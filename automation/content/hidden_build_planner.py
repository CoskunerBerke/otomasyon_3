"""
Beat planner for hidden_build_story -- three continuity-locked beats around one buried
object and one recurring craftsman.

Unlike the other two modes this one puts people on screen deliberately, and one of them
is the channel's identity: the same craftsman appears in all fourteen Reels and his face
is the profile picture on all three platforms. He is therefore defined ONCE, in
CRAFTSMAN, and pasted verbatim into every beat of every concept. Rewriting him per Reel
is how a channel ends up with fourteen different men.

Two lessons from the manual proving runs on 2026-08-21 are baked in here.

Character blocks must not look like name tags. The first hand-written prompt listed
"CRAFTSMAN: ..." and "NEIGHBOURS: ..." as labelled lines, and Flow rendered a caption box
reading "CRAFTSMAN / NEIGHBOUR" into the corner of the finished video -- misspelled, as
generated text always is. Everyone is described in plain prose here for that reason, and
nothing in a prompt is ever formatted as a cast list.

Continuity comes from the seam, not from adjectives. Beats 1 and 2 share one camera
position word for word, and the generator chains each beat's closing frame into the next
as its opening reference. The run that skipped that chaining changed neighbourhood
between beats; the run that used it held the same barn, fields and man across all three.
"""
import hashlib
from typing import Dict, List, Tuple

from .duration_rules import DEFAULT_SEGMENT_DURATION
from .hidden_build_concepts import HiddenBuildConcept
from .segment_planner import ContinuityContext, SegmentPlan

# The three beats. Deliberately the same names the other story mode uses: the shape of a
# 30-second story does not change with its subject, and the shared vocabulary keeps the
# QC, manifest and Obsidian layers reading both modes the same way.
HIDDEN_BUILD_BEATS = ("BEFORE", "THE_TURN", "WHAT_REMAINS")


class HiddenBuildPlanner:
    """Builds the three beats of a buried-object transformation."""

    # THE CHANNEL'S FACE. Identical in every beat of every Reel -- this is the man the
    # profile pictures are taken from. Plain prose, no labels, no distinctive props:
    # every unusual accessory is one more thing for the model to drift on, and the
    # headscarf in the first hand-written test drifted within two segments.
    CRAFTSMAN = (
        "a man in his mid-30s with short dark hair and light stubble, wearing a plain "
        "black t-shirt, grey work trousers and work boots, working alone and unhurried"
    )

    # No speech, for the same reason as the other story mode: a voiceover would need a
    # script, a language and a voice, none of which this pipeline has. Text of any kind is
    # banned twice over here -- once as a caption and once as a label -- because a prompt
    # that names its characters can otherwise end up drawing their names on screen.
    NEGATIVE_EXCLUSIONS = [
        "narration",
        "voiceover",
        "dialogue",
        "intelligible speech",
        "music soundtrack",
        "captions",
        "subtitles",
        "on-screen labels",
        "name tags",
        "title cards",
        "written text",
        "letters",
        "numbers",
        "logos",
        "brand names",
        "watermarks",
        "distorted faces",
        "extra limbs",
        "changing faces between shots",
        "changing clothing between shots",
        "changing background houses between shots",
        "floating objects",
        "instant finished result",
        "magic morph",
        "grainy artifacts",
        "blurry textures",
        "jittery animations",
    ]

    AUDIO_DIRECTION = (
        "Diegetic sound only, recorded as if on location. No narration, no dialogue, "
        "no intelligible speech, no music"
    )

    @classmethod
    def create_continuity_context(
        cls,
        concept: HiddenBuildConcept,
        env: str,
        arch: str,
        camera: str,
        lighting: str,
        materials: str,
    ) -> ContinuityContext:
        """The visual anchor every beat repeats verbatim."""
        return ContinuityContext(
            environment=env,
            terrain=env,
            architecture_style=arch,
            structure_identity=f"{concept.name} ({concept.category_group})",
            materials=materials,
            scale="domestic yard scale, the object filling most of its length",
            camera_direction=camera,
            camera_height="high enough to see the whole yard from back to street",
            lighting=lighting,
            time_of_day="overcast daylight",
            color_palette="neutral daylight outside, warm and saturated once underground",
        )

    @classmethod
    def get_beats(cls, concept: HiddenBuildConcept, env: str, transformation: str, reveal: str) -> Dict[str, str]:
        """
        What each beat starts as, does, and ends as.

        The shape is fixed because the surprise depends on it: beat 2 must end with the
        object GONE and only a stairway left, so that beat 3 can contradict what the
        viewer has been led to expect underneath it.
        """
        obj = concept.buried_object
        return {
            "s1_start": (
                f"{env}, neglected and unused, with nothing built on it. "
                f"{concept.observer} stands at the boundary fence watching"
            ),
            "s1_action": (
                f"the craftsman clears the ground and marks out a long rectangle the length of "
                f"{obj}, then an excavator digs, earth heaping along one edge as the pit deepens "
                f"down the yard while the onlookers keep watching"
            ),
            "s1_end": (
                "a deep, clean-edged rectangular pit running down the yard with fresh earth "
                "heaped beside it, nothing placed in it yet"
            ),
            "s2_start": "the deep pit from the previous shot, earth heaped beside it, the onlookers still at the fence",
            "s2_action": (
                f"{obj} is {transformation}, and a timber staircase opening is built down to its "
                f"end door with a handrail and a dark double door, while the onlookers lean closer, astonished"
            ),
            "s2_end": (
                f"a smooth, neat green surface where the pit was. {obj} is completely invisible "
                f"from above. The only thing left above ground is the timber staircase entrance"
            ),
            "s3_start": "the neat green surface with the timber staircase entrance leading down",
            "s3_action": (
                f"the camera moves down the timber stairs, through the door, and inside. "
                f"It is not a shelter and not a storage room: it is {concept.surprise_reveal}, "
                f"with {reveal}, and with {concept.observer} already inside, enjoying it"
            ),
            "s3_reveal": (
                f"a wide symmetrical view down the full length of {concept.surprise_reveal}, "
                f"the onlookers enjoying it"
            ),
        }

    @classmethod
    def _build_beat_prompt(
        cls,
        concept: HiddenBuildConcept,
        continuity: ContinuityContext,
        index: int,
        beat_name: str,
        starting_state: str,
        action: str,
        ending_state: str,
        ambient: str,
        duration: int,
    ) -> str:
        """
        One Flow prompt for one beat.

        Beats 1 and 2 are given the same camera sentence deliberately: repeating one
        framing across the dig and the burial is what makes the transformation readable.
        Beat 3 has to move, because the payoff is underground.
        """
        if index < 3:
            camera = (
                f"{continuity.camera_direction}, static, {continuity.camera_height}. "
                f"Use exactly this framing in both of the first two beats so they cut together."
            )
        else:
            camera = (
                "descend the timber stairs, then push slowly down the centre line of the "
                "interior, holding it symmetrical so its full length is in frame."
            )

        return "\n".join([
            f"{duration}-second photorealistic cinematic shot, vertical 9:16.",
            f"Beat {index} of 3 of one continuous story: {concept.topic_description}.",
            "",
            f"The same man appears in every beat: {cls.CRAFTSMAN}.",
            f"Watching him: {concept.observer}.",
            f"The location is the same in every beat: {continuity.terrain}.",
            f"The object is the same in every beat: {continuity.architecture_style}.",
            f"Materials once underground: {continuity.materials}.",
            "",
            f"Starts as: {starting_state}.",
            f"What happens: {action}.",
            f"Ends as: {ending_state}.",
            "",
            f"Camera: {camera}",
            f"Light: {continuity.lighting}.",
            f"Colour: {continuity.color_palette}.",
            "",
            f"Sound: {ambient}. {cls.AUDIO_DIRECTION}.",
            "",
            f"Avoid: {', '.join(cls.NEGATIVE_EXCLUSIONS)}.",
            "Keep one continuous location, one continuous set of people and one continuous "
            "camera language so this beat cuts seamlessly against the other two.",
        ])

    @classmethod
    def plan_segments(
        cls,
        concept: HiddenBuildConcept,
        env: str,
        arch: str,
        transformation: str,
        camera: str,
        lighting: str,
        materials: str,
        reveal: str,
        duration_per_segment: int = DEFAULT_SEGMENT_DURATION,
    ) -> Tuple[ContinuityContext, List[SegmentPlan]]:
        """Builds the continuity context and the three SegmentPlans."""
        continuity = cls.create_continuity_context(
            concept=concept, env=env, arch=arch, camera=camera, lighting=lighting, materials=materials
        )
        beats = cls.get_beats(concept=concept, env=env, transformation=transformation, reveal=reveal)

        ambience = concept.ambient_sounds or {}
        specs = [
            (1, HIDDEN_BUILD_BEATS[0], beats["s1_start"], beats["s1_action"], beats["s1_end"], ambience.get("before", "")),
            (2, HIDDEN_BUILD_BEATS[1], beats["s2_start"], beats["s2_action"], beats["s2_end"], ambience.get("turn", "")),
            (3, HIDDEN_BUILD_BEATS[2], beats["s3_start"], beats["s3_action"], beats["s3_reveal"], ambience.get("after", "")),
        ]

        segments: List[SegmentPlan] = []
        for index, beat_name, start, action, end, ambient in specs:
            prompt = cls._build_beat_prompt(
                concept=concept, continuity=continuity, index=index, beat_name=beat_name,
                starting_state=start, action=action, ending_state=end,
                ambient=ambient or "natural on-location ambience",
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
