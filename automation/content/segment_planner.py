"""
Segment Planner and Continuity Engine for V3 30-Second Step-by-Step Reels.
Plans exactly 3 logical, staged construction segments (10s each) with strict visual continuity.
"""
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any

from .concepts import ConceptDefinition
from .duration_rules import DEFAULT_SEGMENT_DURATION, sanitize_video_duration

@dataclass
class ContinuityContext:
    """Immutable visual identity shared across all 3 segments of a Reel."""
    environment: str
    terrain: str
    architecture_style: str
    structure_identity: str
    materials: str
    scale: str
    camera_direction: str
    camera_height: str
    lighting: str
    time_of_day: str
    color_palette: str

    def to_prompt_clause(self) -> str:
        return (
            f"Environment: {self.environment} ({self.terrain}). "
            f"Architecture: {self.architecture_style} ({self.structure_identity}). "
            f"Materials: {self.materials}. Scale: {self.scale}. "
            f"Camera perspective: {self.camera_direction} at {self.camera_height}. "
            f"Lighting: {self.lighting}, time of day: {self.time_of_day}, palette: {self.color_palette}."
        )

@dataclass
class SegmentPlan:
    """Plan for a single 10-second segment of a 30-second Reel."""
    index: int  # 1, 2, 3
    duration_seconds: int  # 10
    stage_name: str  # "FOUNDATION", "MAIN_CONSTRUCTION", "DETAILS_AND_REVEAL"
    starting_state: str
    action_description: str
    ending_state: str
    prompt: str
    prompt_hash: str
    status: str = "PENDING"  # PENDING, GENERATING, MEDIA_READY, READY
    artifact_fingerprint: Optional[str] = None
    local_file: Optional[Path] = None
    end_frame_file: Optional[Path] = None

class SegmentPlanner:
    """Generates 3 logical, non-magic step-by-step construction segments for any concept."""

    NEGATIVE_EXCLUSIONS = [
        "people",
        "human faces",
        "dialogue",
        "voiceover",
        "captions",
        "subtitles",
        "written text",
        "letters",
        "numbers",
        "logos",
        "brand names",
        "watermarks",
        "distorted architecture",
        "melting objects",
        "chaotic camera movement",
        "random floating objects",
        "instant finished result",
        "instant pop-in",
        "magic morph",
        "teleporting buildings",
        "random architecture changes",
        "grainy artifacts",
        "blurry textures",
        "jittery animations"
    ]

    @classmethod
    def create_continuity_context(
        cls,
        concept: ConceptDefinition,
        env: str,
        arch: str,
        camera: str,
        lighting: str,
        materials: str
    ) -> ContinuityContext:
        """Create the immutable visual anchor context for the Reel."""
        slug = concept.id_slug.lower()

        # Derive scale & height
        if "city" in slug or "bridge" in slug or "metropolis" in slug:
            scale = "monumental mega-structure scale"
            cam_height = "elevated aerial drone altitude"
        elif "villa" in slug or "house" in slug or "resort" in slug:
            scale = "luxury architectural human scale"
            cam_height = "medium-high cinematic crane perspective"
        else:
            scale = "grand architectural scale"
            cam_height = "cinematic aerial perspective"

        time_of_day = "golden hour sunset" if "sunset" in lighting.lower() or "golden" in lighting.lower() else "vibrant clear midday"
        color_palette = "natural rich realistic tones with pristine material reflections"

        return ContinuityContext(
            environment=env,
            terrain=f"clean undeveloped {env}",
            architecture_style=arch,
            structure_identity=f"{concept.name} ({concept.category_group})",
            materials=materials,
            scale=scale,
            camera_direction=camera,
            camera_height=cam_height,
            lighting=lighting,
            time_of_day=time_of_day,
            color_palette=color_palette
        )

    @classmethod
    def get_category_stages(
        cls,
        concept: ConceptDefinition,
        env: str,
        arch: str,
        materials: str,
        transformation: str,
        reveal: str
    ) -> Dict[str, Any]:
        """Derive specialized construction stages based on project type."""
        slug = concept.id_slug.lower()

        if "bridge" in slug:
            s1_start = f"open pristine {env}, empty water surface and untouched shorelines"
            s1_action = f"deep marine foundation piles driving into seabed, reinforced concrete pylon bases rising above water level, heavy staging piers anchoring"
            s1_end = f"solid structural pylon bases and submerged foundation footings firmly anchored in water, ready for tower elevation (unfinished, no deck yet)"

            s2_start = f"marine pylon footings in {env} established from Segment 1"
            s2_action = f"massive twin suspension towers rising high into the sky, steel cross-bracing assembling, heavy roadway deck segments extending outward from towers and connecting mid-span"
            s2_end = f"completed tower superstructures and connected bridge deck with main cable stays attached (advanced construction, no asphalt paving or lighting yet)"

            s3_start = f"assembled bridge superstructure from Segment 2"
            s3_action = f"roadway surface asphalt laying, safety barriers installation, dynamic LED cable lighting activation, clean structural finishing touches"
            s3_reveal = f"sweeping aerial camera pullback showcasing the monumental illuminated {concept.name} spanning across {env} in breathtaking glory"

        elif "city" in slug or "cyber" in slug or "metropolis" in slug:
            s1_start = f"empty vast terrain in {env}, raw undeveloped land"
            s1_action = f"underground infrastructure excavation, subterranean transit grids mapping, heavy concrete foundation slabs pouring, initial structural columns rising"
            s1_end = f"active multi-block foundation grid with exposed steel framing and lower structural columns (unfinished, no upper towers yet)"

            s2_start = f"foundation grid and lower frame from Segment 1 in {env}"
            s2_action = f"multiple skyscraper steel skeletons rapidly ascending, modular floor plates locking into place, glass curtain facades climbing floor by floor, elevated skybridges connecting towers"
            s2_end = f"dense urban skyline with high-rise structures largely framed and glazed (advanced partial completion, no illumination or street landscaping yet)"

            s3_start = f"framed futuristic urban blocks from Segment 2"
            s3_action = f"futuristic street-level plazas finishing, lush rooftop gardens blooming, warm neon transit ribbons activating, facade architectural lighting glowing"
            s3_reveal = f"majestic ascending camera crane rise revealing the completed, fully illuminated futuristic {concept.name} bustling in {env}"

        elif "space" in slug or "mars" in slug or "moon" in slug or "orbital" in slug:
            s1_start = f"untouched alien regolith in {env}, rugged craters and barren terrain"
            s1_action = f"automated ground grading, blast-shield foundation anchors setting, primary airlock core module landing and securing, subterranean habitat vaults excavating"
            s1_end = f"anchored pressurized airlock base and foundation footings (unfinished, no main domes or solar arrays yet)"

            s2_start = f"pressurized base core in {env} from Segment 1"
            s2_action = f"interlocking geodesic dome framework assembling, reinforced pressurized habit corridor modules expanding, heavy life-support silo structures locking into position"
            s2_end = f"enclosed habitat dome complex and connecting pressurization tunnels (advanced shell, unpowered without solar arrays or landing pads yet)"

            s3_start = f"assembled habitat complex from Segment 2"
            s3_action = f"massive photovoltaic solar arrays unfolding, atmospheric beacon towers lighting up, illuminated landing pads activating, rover docking bays finishing"
            s3_reveal = f"spectacular high-orbit pullback revealing the complete, self-sustaining {concept.name} glowing against {env}"

        elif "resort" in slug or "villa" in slug or "mansion" in slug or "palace" in slug:
            s1_start = f"pristine empty {env}, completely undeveloped landscape"
            s1_action = f"site clearing, ground excavation, concrete foundation slab pouring, structural columns and lower frame rising with kinetic precision"
            s1_end = f"solid foundation slab with structural columns and lower level framing exposed (unfinished, no upper floors or roof yet)"

            s2_start = f"foundation slab and lower framework in {env} from Segment 1"
            s2_action = f"upper floor framing assembling, exterior perimeter walls rising, cantilevered roof structures installing, panoramic floor-to-ceiling glass glazing mounting"
            s2_end = f"fully framed and enclosed architectural structure crafted with {materials} (advanced shell, no pool, lighting, or landscaping yet)"

            s3_start = f"enclosed structural shell from Segment 2"
            s3_action = f"infinity-edge pools filling with crystal water, teak wood decking laying, lush tropical landscaping blooming, warm interior and exterior ambient lighting illuminating"
            s3_reveal = f"smooth elevated cinematic drone pullback revealing the completely finished, illuminated ultra-luxury {concept.name} in all its glory"

        else:
            # Generic satisfying step-by-step construction
            s1_start = f"pristine undeveloped {env}, empty and clean terrain"
            s1_action = f"site preparation, ground leveling, deep foundation footing pouring, initial structural support columns rising"
            s1_end = f"solid foundation platform with early structural framework exposed (unfinished, intermediate construction state)"

            s2_start = f"foundation and early frame in {env} from Segment 1"
            s2_action = f"main structural bodies assembling with kinetic precision, primary walls and levels rising, exterior facade and roof structures assembling with {materials}"
            s2_end = f"advanced structural body largely erected and enclosed (advanced partial completion, no landscaping, lighting, or finishing details yet)"

            s3_start = f"erected architectural structure from Segment 2"
            s3_action = f"exterior landscaping, perimeter pathways, decorative elements, warm architectural ambient lighting activating across all surfaces"
            s3_reveal = f"gentle cinematic camera pullback and slight rise showcasing the completed, magnificent {concept.name} in full glory"

        return {
            "s1_start": s1_start,
            "s1_action": s1_action,
            "s1_end": s1_end,
            "s2_start": s2_start,
            "s2_action": s2_action,
            "s2_end": s2_end,
            "s3_start": s3_start,
            "s3_action": s3_action,
            "s3_reveal": s3_reveal,
        }

    @classmethod
    def plan_segments(
        cls,
        concept: ConceptDefinition,
        env: str,
        arch: str,
        transformation: str,
        camera: str,
        lighting: str,
        materials: str,
        reveal: str,
        duration_per_segment: int = DEFAULT_SEGMENT_DURATION
    ) -> tuple[ContinuityContext, List[SegmentPlan]]:
        """Create the ContinuityContext and the 3 staged SegmentPlan objects."""
        continuity = cls.create_continuity_context(
            concept=concept,
            env=env,
            arch=arch,
            camera=camera,
            lighting=lighting,
            materials=materials
        )

        stages = cls.get_category_stages(
            concept=concept,
            env=env,
            arch=arch,
            materials=materials,
            transformation=transformation,
            reveal=reveal
        )

        negative_str = ", ".join(f"no {item}" for item in cls.NEGATIVE_EXCLUSIONS)

        # -------------------------------------------------------------
        # SEGMENT 1: Initial State + Foundation & Early Construction
        # -------------------------------------------------------------
        s1_prompt_lines = [
            f"Create a cinematic {duration_per_segment}-second vertical 9:16 step-by-step satisfying transformation video.",
            f"",
            f"This is SEGMENT 1 OF 3 of one continuous 30-second transformation.",
            f"",
            f"Project: {concept.name} ({concept.category_group}).",
            f"Environment: {env}.",
            f"",
            f"Begin with: {stages['s1_start']}. The terrain is viewed with {camera}.",
            f"",
            f"Immediately begin realistic construction.",
            f"",
            f"During this segment: {stages['s1_action']}. Structures built with {arch} rise with kinetic precision. Surfaces are crafted with {materials}.",
            f"",
            f"Lighting is set to {lighting}.",
            f"",
            f"Show clearly understandable staged construction.",
            f"",
            f"Do NOT complete the final project during this segment.",
            f"",
            f"End with: {stages['s1_end']}.",
            f"",
            f"The final frame must clearly preserve the unfinished construction so Segment 2 can continue from exactly this point.",
            f"",
            f"Visual identity: {continuity.to_prompt_clause()}",
            f"",
            f"Visual style: premium cinematic 3D realism, high-end architectural visualization, physically believable step-by-step construction, smooth continuous transformation, precise geometry, realistic materials.",
            f"",
            f"Audio: natural ambient environmental sound for {env} (wind, birds, distant water, or site ambience as fitting), layered with satisfying tactile early-construction sound effects (earth moving, foundation pouring, first structural pieces settling into place) precisely synchronized to the on-screen action. No dialogue, no voiceover, no spoken words, no lyrics.",
            f"",
            f"Negative prompt / Exclusions: {negative_str}.",
            f"",
            f"Aspect ratio: 9:16 vertical. Duration: {duration_per_segment} seconds. Optimized for Instagram Reels, TikTok and YouTube Shorts."
        ]
        s1_prompt = sanitize_video_duration("\n".join(s1_prompt_lines), target_duration=duration_per_segment)
        s1_hash = hashlib.sha256(s1_prompt.encode("utf-8")).hexdigest()[:16]

        plan_1 = SegmentPlan(
            index=1,
            duration_seconds=duration_per_segment,
            stage_name="FOUNDATION",
            starting_state=stages["s1_start"],
            action_description=stages["s1_action"],
            ending_state=stages["s1_end"],
            prompt=s1_prompt,
            prompt_hash=s1_hash
        )

        # -------------------------------------------------------------
        # SEGMENT 2: Main Construction Progression
        # -------------------------------------------------------------
        s2_prompt_lines = [
            f"Create a cinematic {duration_per_segment}-second vertical 9:16 continuation.",
            f"",
            f"This is SEGMENT 2 OF 3 of the same continuous 30-second construction.",
            f"",
            f"Continue the EXACT SAME project: {concept.name}.",
            f"",
            f"Starting state: {stages['s2_start']}.",
            f"",
            f"Preserve exactly: {continuity.to_prompt_clause()}",
            f"",
            f"During this segment: {stages['s2_action']}. Structures built with {arch} progress substantially. Surfaces crafted with {materials}.",
            f"",
            f"Lighting remains {lighting}.",
            f"",
            f"The project should progress substantially.",
            f"",
            f"Do NOT restart from empty land.",
            f"Do NOT redesign the building.",
            f"Do NOT jump immediately to the completed final result.",
            f"",
            f"End with: {stages['s2_end']}.",
            f"",
            f"The final frame must clearly preserve the advanced partial state so Segment 3 can add final details and reveal.",
            f"",
            f"Visual style: premium cinematic 3D realism, high-end architectural visualization, physically believable step-by-step construction, smooth continuous transformation, precise geometry, realistic materials.",
            f"",
            f"Audio: continuation of the same ambient soundscape from before, now layered with heavier, satisfying mechanical and structural sound effects (steel assembly, glass panels, concrete, cranes or lifts as fitting) precisely synchronized to the on-screen construction. No dialogue, no voiceover, no spoken words, no lyrics.",
            f"",
            f"Negative prompt / Exclusions: {negative_str}.",
            f"",
            f"Aspect ratio: 9:16 vertical. Duration: {duration_per_segment} seconds. Optimized for Instagram Reels, TikTok and YouTube Shorts."
        ]
        s2_prompt = sanitize_video_duration("\n".join(s2_prompt_lines), target_duration=duration_per_segment)
        s2_hash = hashlib.sha256(s2_prompt.encode("utf-8")).hexdigest()[:16]

        plan_2 = SegmentPlan(
            index=2,
            duration_seconds=duration_per_segment,
            stage_name="MAIN_CONSTRUCTION",
            starting_state=stages["s2_start"],
            action_description=stages["s2_action"],
            ending_state=stages["s2_end"],
            prompt=s2_prompt,
            prompt_hash=s2_hash
        )

        # -------------------------------------------------------------
        # SEGMENT 3: Details + Finishing Touches + Final Reveal
        # -------------------------------------------------------------
        s3_prompt_lines = [
            f"Create the final {duration_per_segment}-second vertical 9:16 continuation.",
            f"",
            f"This is SEGMENT 3 OF 3 of the same continuous 30-second construction.",
            f"",
            f"Project: {concept.name}.",
            f"",
            f"Starting state: {stages['s3_start']}.",
            f"",
            f"Preserve exactly: {continuity.to_prompt_clause()}",
            f"",
            f"During the first approximately 6–7 seconds: {stages['s3_action']}.",
            f"",
            f"Lighting is set to {lighting}.",
            f"",
            f"Only during the final approximately 3 seconds: {stages['s3_reveal']}.",
            f"",
            f"Use a controlled camera pullback / slight rise to reveal the completed project in full glory.",
            f"",
            f"Do not spend the full segment showing a static finished building.",
            f"",
            f"Visual style: premium cinematic 3D realism, high-end architectural visualization, smooth continuous transformation, majestic cinematic conclusion.",
            f"",
            f"Audio: satisfying finishing sound effects (water filling, lighting activating, final materials settling into place) synchronized to the on-screen action for the first 6-7 seconds, building into a subtle, non-lyrical cinematic orchestral swell that peaks precisely with the final reveal. No dialogue, no voiceover, no spoken words, no lyrics.",
            f"",
            f"Negative prompt / Exclusions: {negative_str}.",
            f"",
            f"Aspect ratio: 9:16 vertical. Duration: {duration_per_segment} seconds. Optimized for Instagram Reels, TikTok and YouTube Shorts."
        ]
        s3_prompt = sanitize_video_duration("\n".join(s3_prompt_lines), target_duration=duration_per_segment)
        s3_hash = hashlib.sha256(s3_prompt.encode("utf-8")).hexdigest()[:16]

        plan_3 = SegmentPlan(
            index=3,
            duration_seconds=duration_per_segment,
            stage_name="DETAILS_AND_REVEAL",
            starting_state=stages["s3_start"],
            action_description=stages["s3_action"],
            ending_state=stages["s3_reveal"],
            prompt=s3_prompt,
            prompt_hash=s3_hash
        )

        return continuity, [plan_1, plan_2, plan_3]
