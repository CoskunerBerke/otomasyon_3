"""
Concept library for cutaway_reveal_story Reels -- an ordinary surface is opened in
cross-section and the working world inside it is revealed.

The hook is the same one that carries the other two channels, aimed at a different
subject: you have walked over this a hundred times and never known what was under it.
The first beat must therefore look *boring* -- a plain street, a bare field, a blank
concrete wall. If the surface already looks interesting, the reveal has nothing to
contradict.

Three things carry every Reel and must not drift:

    the plainness   -- beat one is deliberately unremarkable. The camera does not move,
                       so the viewer has nothing to look at but the surface about to open.
    the cut         -- the opening is a clean geometric section, like an architectural
                       drawing come alive. Not an explosion, not a collapse, not a hole.
    the working     -- what is inside is in USE. Water moving, machinery turning, lights
                       on, people small against the scale. A hollow space is a fact; a
                       working one is a story.

Every entry names a real kind of structure, and `real_basis` records what makes it real.
Keep that honest when adding concepts: these Reels claim "places like this exist", so a
concept that invents its subject breaks the claim the whole channel rests on. No invented
depths, no invented purposes, no attributing a structure to a builder who did not build it.

Why engineering and not anatomy: the request that prompted this format asked for what is
"inside" things, and the body was the first idea. Flow renders hard geometry, rock, water
and machinery convincingly and organic interiors poorly, so the inside of built things is
where this format actually looks good. It also keeps the channel clear of the platforms'
medical-misinformation policies, which apply to AI-generated depictions of the body
presented as fact.

CutawayConcept extends ConceptDefinition so the existing diversity ranking, manifest
round-trip and concept-slug rebuild keep working unchanged. The inherited fields carry
this format's meaning:

    environments   -> the ordinary surface, before anything opens
    architectures  -> the structure the section cuts through
    transformations-> the cut itself, opening cleanly
    reveals        -> the working interior, the payoff
"""
from dataclasses import dataclass, field
from typing import Dict, List

from .concepts import ConceptDefinition


@dataclass
class CutawayConcept(ConceptDefinition):
    """One ordinary surface, the working interior beneath it, and why it is really there."""

    # What makes this real. Never publish a claim this does not support.
    real_basis: str = ""

    # What the viewer sees in beat one. Must read as unremarkable at a glance.
    everyday_surface: str = ""

    # The payoff. Must be in use, not merely present.
    hidden_interior: str = ""

    # Diegetic sound per beat, handed to Flow as a positive instruction. Never speech.
    # Keys: "before", "turn", "after" -- the names StoryPlanner reads.
    ambient_sounds: Dict[str, str] = field(default_factory=dict)

    # Which title family the metadata builder draws from. Fixed for this format: the
    # payoff is a working interior, and the default family talks about abandonment.
    narrative_frame: str = "cutaway"


CUTAWAY_CONCEPTS: List[CutawayConcept] = [
    # Added 2026-08-28. Twelve concepts could not fill two weeks of evening slots at
    # seven a week, so the second week had to repeat -- the exact shortage that made
    # craftsbyman republish a whole week. Sixteen leaves headroom.
    CutawayConcept(
        id_slug="canal-lock-chamber",
        name="Canal Locks",
        category_group="Engineering Interiors",
        environments=["a still green canal between flat fields, one closed lock gate across it"],
        architectures=["a masonry lock chamber with its culverts and paddle gear"],
        transformations=["the water and one wall drawing back in a clean section, the chamber standing open"],
        camera_styles=["locked-off wide shot from the towpath, level with the water"],
        lighting_schemes=["flat overcast daylight, green light off the water"],
        materials=["wet coursed masonry", "black oak gates", "iron paddle gear", "slime-marked stone"],
        reveals=["a deep masonry chamber with water pouring through side culverts, the level climbing visibly up the stained walls"],
        default_title="What Is Actually Inside Canal Locks",
        topic_description="A canal lock opened in section to reveal the chamber and culverts that raise a boat",
        real_basis="Canal locks raise and lower boats by filling a masonry chamber through side culverts controlled by paddle gear; the mechanism is unchanged since the 18th century.",
        everyday_surface="a still stretch of canal with a gate across it",
        hidden_interior="a chamber filling through hidden culverts",
        ambient_sounds={
            "before": "flat water, moorhens, wind in reeds",
            "turn": "a paddle winding open, stone grinding",
            "after": "water thundering through culverts, boiling up the chamber walls",
        },
    ),
    CutawayConcept(
        id_slug="church-floor-crypt",
        name="Church Floors",
        category_group="Under the Ground",
        environments=["a plain flagstone church floor, empty pews, weak light from high windows"],
        architectures=["a vaulted stone crypt carrying the floor above it"],
        transformations=["the flagstones lifting away in a clean section, the vaults appearing beneath"],
        camera_styles=["locked-off wide shot down the nave, level with the floor"],
        lighting_schemes=["cool daylight above, warm candlelight below"],
        materials=["worn flagstone", "chalk-white vaulting", "carved memorial slabs", "iron candle stands"],
        reveals=["a low vaulted crypt running the length of the nave, carved slabs set into its floor, candlelight along the piers"],
        default_title="Nobody Ever Sees What Is Under Church Floors",
        topic_description="A flagstone church floor opened in section to reveal the vaulted crypt beneath it",
        real_basis="Many parish and cathedral churches are built over vaulted crypts carrying the floor above; the crypt often predates the building standing on it.",
        everyday_surface="a plain worn stone floor",
        hidden_interior="a vaulted crypt carrying the whole nave",
        ambient_sounds={
            "before": "an empty stone building, a door far off, wind at high windows",
            "turn": "stone lifting, dust falling into still air",
            "after": "a very long reverberation, a candle guttering, deep cold quiet",
        },
    ),
    CutawayConcept(
        id_slug="stadium-pitch-services",
        name="Football Pitches",
        category_group="Engineering Interiors",
        environments=["an empty green pitch under floodlights, tiers of seats dark around it"],
        architectures=["a service level of pipework, drainage and undersoil heating beneath the turf"],
        transformations=["the turf peeling back in a clean section, the layers and pipework appearing below"],
        camera_styles=["locked-off wide shot from the touchline, level with the grass"],
        lighting_schemes=["hard white floodlight above, cool service lamps below"],
        materials=["cut turf", "graded sand and gravel", "black heating pipe", "perforated drainage"],
        reveals=["ranks of heating pipe threaded through graded sand under the turf, drainage running away to one side, service lamps along a corridor beneath"],
        default_title="You Have Walked Over Football Pitches and Never Known",
        topic_description="A stadium pitch opened in section to reveal the drainage and undersoil heating beneath the turf",
        real_basis="Modern stadium pitches are built over graded sand and gravel with perforated drainage and undersoil heating pipes, which is why they drain and stay playable in frost.",
        everyday_surface="an ordinary green pitch",
        hidden_interior="heating and drainage working under the grass",
        ambient_sounds={
            "before": "an empty stadium, floodlights humming, wind in open tiers",
            "turn": "turf lifting, sand pouring",
            "after": "water moving in drainage pipe, a pump running somewhere below",
        },
    ),
    CutawayConcept(
        id_slug="motorway-embankment-culvert",
        name="Motorway Embankments",
        category_group="Under the Ground",
        environments=["a grass motorway embankment, traffic passing above, nothing else to see"],
        architectures=["a concrete culvert carrying a stream and a path through the embankment"],
        transformations=["the embankment opening in a clean section across its width"],
        camera_styles=["locked-off wide shot from the field below the embankment"],
        lighting_schemes=["flat daylight outside, a bright disc of daylight at the far end"],
        materials=["cut turf and clay", "ribbed concrete pipe", "shallow running water", "a gravel ledge"],
        reveals=["a concrete culvert running right through the bank, a stream along its invert, daylight at the far end and a dry ledge worn by animals"],
        default_title="Cut Open: Motorway Embankments",
        topic_description="A motorway embankment opened in section to reveal the culvert carrying a stream through it",
        real_basis="Road embankments are built over culverts that carry existing watercourses through them, and many are fitted with dry ledges so animals can cross under the road.",
        everyday_surface="a plain grass bank under a road",
        hidden_interior="a stream and a crossing running straight through it",
        ambient_sounds={
            "before": "traffic above, wind in long grass",
            "turn": "clay shearing, turf tearing",
            "after": "water running over concrete, traffic gone to a dull rumble overhead",
        },
    ),
    CutawayConcept(
        id_slug="city-street-cistern",
        name="City Streets",
        category_group="Under the City",
        environments=["a quiet stone-paved city street at dawn, shutters still closed"],
        architectures=["a vaulted brick cistern spanning the whole block beneath the paving"],
        transformations=["the street opening in a clean vertical section, paving and soil peeling back like a drawing"],
        camera_styles=["locked-off wide shot, dead level with the street"],
        lighting_schemes=["flat blue pre-dawn above, warm lamplight rising from below"],
        materials=["worn granite setts", "damp red brick vaulting", "still black water", "iron tie-rods"],
        reveals=["a forest of brick columns standing in still water, lamps reflected in it, the vaults running away into the dark"],
        default_title="What Is Under This Street",
        topic_description="An ordinary city street opened in section to reveal the vaulted water cistern beneath it",
        real_basis="Large covered cisterns under city streets are real and numerous -- Istanbul's Basilica Cistern is the best known, with 336 columns supporting a brick-vaulted roof under what is now street level.",
        everyday_surface="a plain paved street with nothing to look at",
        hidden_interior="a columned reservoir still holding water",
        ambient_sounds={
            "before": "early morning street quiet, distant gulls, one shutter rolling up",
            "turn": "a low stone grinding as the section opens, dust settling",
            "after": "water dripping into still water with a long echo under the vaults",
        },
    ),
    CutawayConcept(
        id_slug="dam-wall-galleries",
        name="Dam Walls",
        category_group="Engineering Interiors",
        environments=["a vast blank concrete dam face in flat daylight, still water behind it"],
        architectures=["inspection galleries and stairwells threading the full height of the dam"],
        transformations=["the concrete face opening in a clean section from crest to base"],
        camera_styles=["locked-off wide shot facing the dam square-on"],
        lighting_schemes=["overcast grey outside, strings of yellow service lamps inside"],
        materials=["board-marked concrete", "galvanised handrail", "seeping mineral stain", "steel stair treads"],
        reveals=["a lit stairwell falling the whole height of the wall, galleries branching off it, water threading down a drainage channel"],
        default_title="There Are Corridors Inside a Dam",
        topic_description="A blank dam face opened in section to reveal the inspection galleries running through it",
        real_basis="Large concrete dams contain internal inspection and drainage galleries running their full height, used to monitor seepage and movement. This is standard practice, not an exception.",
        everyday_surface="a featureless concrete wall",
        hidden_interior="lit galleries and stairs threading the structure",
        ambient_sounds={
            "before": "wind across open water, a distant spillway hum",
            "turn": "concrete parting with a deep resonant crack",
            "after": "dripping in a long concrete corridor, a ventilation fan turning somewhere below",
        },
    ),
    CutawayConcept(
        id_slug="quiet-field-underground-city",
        name="Quiet Fields",
        category_group="Under the Ground",
        environments=["a bare ploughed field on a plateau, one low stone wall crossing it"],
        architectures=["carved rooms and connecting shafts descending many levels into soft rock"],
        transformations=["the field opening in section, level after level appearing below"],
        camera_styles=["locked-off wide shot from the field's edge"],
        lighting_schemes=["hard noon light above, warm oil-lamp glow deepening downward"],
        materials=["dry tilled earth", "pale carved tuff", "smoke-blackened ceilings", "round stone doors"],
        reveals=["level upon level of carved rooms, ventilation shafts running the full depth, a round stone door standing open"],
        default_title="An Entire City Was Carved Under This Field",
        topic_description="An ordinary field opened in section to reveal a multi-level underground city carved into soft rock",
        real_basis="Multi-level underground cities carved into volcanic tuff exist in Cappadocia, Turkey; Derinkuyu descends roughly 60 metres with ventilation shafts and rolling stone doors.",
        everyday_surface="an empty ploughed field",
        hidden_interior="a carved city on many levels, still ventilated",
        ambient_sounds={
            "before": "wind over open farmland, a crow calling once",
            "turn": "dry earth shearing away, small stones falling",
            "after": "deep still air, a faint draught moving through the shafts",
        },
    ),
    CutawayConcept(
        id_slug="salt-mine-chamber",
        name="Salt Hills",
        category_group="Under the Ground",
        environments=["a low wooded hill in winter, a small brick shaft-head building at its foot"],
        architectures=["a vast chamber hewn entirely from rock salt, with carved stairs and chandeliers"],
        transformations=["the hillside opening in section, the shaft dropping away below the treeline"],
        camera_styles=["locked-off wide shot level with the hill's base"],
        lighting_schemes=["flat grey winter daylight above, warm chandelier light far below"],
        materials=["bare winter branches", "grey-green rock salt", "carved salt relief", "timber shaft framing"],
        reveals=["a chamber the size of a church cut from salt, its chandeliers lit, carved reliefs along the walls"],
        default_title="They Carved a Room Out of Salt",
        topic_description="A wooded hill opened in section to reveal an enormous chamber hewn from rock salt",
        real_basis="Chambers carved from rock salt, including chandeliers and reliefs cut from salt itself, exist in the Wieliczka mine in Poland, worked from the 13th century.",
        everyday_surface="an unremarkable wooded hill",
        hidden_interior="a lit hall carved entirely from salt",
        ambient_sounds={
            "before": "bare branches in wind, snow compacting underfoot",
            "turn": "a dry crystalline crack running down through the hill",
            "after": "a long dry echo, timber creaking under load",
        },
    ),
    CutawayConcept(
        id_slug="roman-bath-hypocaust",
        name="Old Tiled Floors",
        category_group="Engineering Interiors",
        environments=["a plain tiled floor in an empty stone room, weak light from one high window"],
        architectures=["a hypocaust of short brick pillars carrying the floor above a hot-air void"],
        transformations=["the floor lifting away in a clean section, the pillar field appearing beneath"],
        camera_styles=["locked-off wide shot from the room's corner, level with the floor"],
        lighting_schemes=["cool daylight above, orange furnace light washing the void below"],
        materials=["worn floor tile", "stacked brick pilae", "soot-blackened flue", "lime mortar"],
        reveals=["hundreds of short brick pillars in ranks, hot air moving between them, firelight from the furnace mouth at one end"],
        default_title="This Floor Was Heated From Underneath",
        topic_description="A plain tiled floor opened in section to reveal the Roman hot-air heating system beneath it",
        real_basis="Roman hypocaust heating raised floors on short brick pillars so hot furnace gases could circulate underneath; surviving examples are common across former Roman provinces.",
        everyday_surface="an ordinary tiled floor",
        hidden_interior="a field of brick pillars carrying hot air",
        ambient_sounds={
            "before": "an empty stone room, faint wind at the window",
            "turn": "tile and mortar parting cleanly",
            "after": "a low furnace roar, air drawing through the flues",
        },
    ),
    CutawayConcept(
        id_slug="lighthouse-spiral",
        name="Lighthouses",
        category_group="Engineering Interiors",
        environments=["a white lighthouse tower on a flat headland, grey sea behind it"],
        architectures=["a stone spiral stair winding the full height to the lamp room"],
        transformations=["the tower opening in a clean vertical section from base to lantern"],
        camera_styles=["locked-off wide shot facing the tower square-on"],
        lighting_schemes=["flat overcast daylight, the lamp turning warm at the top"],
        materials=["whitewashed masonry", "granite stair treads", "brass handrail", "cut-glass lens"],
        reveals=["a spiral stair climbing the whole tower, storerooms stacked up its height, the great lens turning above"],
        default_title="What a Lighthouse Looks Like Inside",
        topic_description="A lighthouse tower opened in section to reveal the spiral stair and lamp room within",
        real_basis="Masonry lighthouses are built around a spiral stair with stacked service rooms below the lantern, which houses a rotating Fresnel lens.",
        everyday_surface="a plain white tower",
        hidden_interior="a stair spiralling to a turning lens",
        ambient_sounds={
            "before": "sea wind, waves on rock, a gull",
            "turn": "masonry parting with a dull stone report",
            "after": "the slow mechanical turn of the lens bearing, wind against glass",
        },
    ),
    CutawayConcept(
        id_slug="grain-silo-interior",
        name="Grain Silos",
        category_group="Engineering Interiors",
        environments=["a row of blank concrete silos beside a rail siding, flat farmland behind"],
        architectures=["cylindrical storage cells with conveyors running along the top and base"],
        transformations=["the silo wall opening in a clean vertical section"],
        camera_styles=["locked-off wide shot level with the siding"],
        lighting_schemes=["hard afternoon sun outside, dusty shafts of light inside"],
        materials=["stained concrete", "galvanised ducting", "poured grain", "steel conveyor belt"],
        reveals=["a column of grain filling the cell, dust hanging in the light, a conveyor drawing it away at the base"],
        default_title="What Is Inside Those Concrete Towers",
        topic_description="A blank concrete silo opened in section to reveal the grain column and conveyors inside",
        real_basis="Concrete grain silos store grain in tall cylindrical cells, filled from a conveyor at the top and drawn off by another at the base.",
        everyday_surface="blank concrete towers by a railway",
        hidden_interior="a column of grain moving on conveyors",
        ambient_sounds={
            "before": "wind over open farmland, a distant freight coupling",
            "turn": "concrete shearing, a hollow boom inside the cell",
            "after": "grain pouring in a steady rush, a conveyor motor running",
        },
    ),
    CutawayConcept(
        id_slug="amphitheatre-hypogeum",
        name="Arena Floors",
        category_group="Under the Ground",
        environments=["a bare oval arena floor of packed sand, empty tiers rising around it"],
        architectures=["a two-level basement of corridors, cages and timber lifts under the floor"],
        transformations=["the sand floor opening in section, the corridors appearing beneath"],
        camera_styles=["locked-off wide shot from the arena's edge"],
        lighting_schemes=["bright open daylight above, torchlight and shafts of light below"],
        materials=["packed arena sand", "brick corridor walls", "timber lift frames", "rope and counterweight"],
        reveals=["a grid of brick corridors under the whole floor, timber lifts standing ready in their shafts"],
        default_title="There Was a Second Building Under the Floor",
        topic_description="An arena floor opened in section to reveal the two-level service basement beneath it",
        real_basis="The Colosseum's hypogeum is a two-level underground network of corridors and lift shafts beneath the arena floor, used to raise animals and scenery through trapdoors.",
        everyday_surface="a plain sand floor",
        hidden_interior="corridors and lifts waiting under it",
        ambient_sounds={
            "before": "open-air wind through empty stone tiers",
            "turn": "sand pouring away, timber creaking",
            "after": "rope running through blocks, a counterweight settling, muffled echo",
        },
    ),
    CutawayConcept(
        id_slug="victorian-sewer-cathedral",
        name="River Embankments",
        category_group="Under the City",
        environments=["a plain grass embankment beside a slow river, one brick vent stack on it"],
        architectures=["an interceptor sewer of cathedral-scale brick vaulting"],
        transformations=["the embankment opening in section, the vault appearing intact beneath the turf"],
        camera_styles=["locked-off wide shot along the embankment"],
        lighting_schemes=["flat river daylight above, lamplight catching the wet brick below"],
        materials=["cut turf", "engineering brick", "wet arch soffit", "cast-iron penstock"],
        reveals=["an ornate brick vault running away into the dark, water moving fast along its invert"],
        default_title="Victorians Built This Underground and Never Showed Anyone",
        topic_description="A grass embankment opened in section to reveal the ornate brick interceptor sewer beneath",
        real_basis="London's Victorian interceptor sewers, built under Joseph Bazalgette from 1859, are brick-vaulted on a monumental scale and remain in use; pumping stations such as Crossness are elaborately decorated.",
        everyday_surface="a plain grass embankment",
        hidden_interior="a brick vault carrying a river of water",
        ambient_sounds={
            "before": "river lapping, traffic somewhere behind",
            "turn": "turf and clay parting, brick ringing once",
            "after": "fast water in a brick channel, a long low echo",
        },
    ),
    CutawayConcept(
        id_slug="glacier-moulin",
        name="Glaciers",
        category_group="Under the Ground",
        environments=["a flat white glacier surface under thin cloud, one meltwater stream crossing it"],
        architectures=["a meltwater shaft dropping through the full thickness of the ice"],
        transformations=["the ice opening in a clean section, the shaft falling away below"],
        camera_styles=["locked-off wide shot level with the ice surface"],
        lighting_schemes=["flat white daylight above, deepening blue with depth"],
        materials=["granular surface ice", "polished blue ice", "meltwater", "trapped air bands"],
        reveals=["a polished blue shaft dropping through the ice, water spiralling down its wall, the light going deep blue"],
        default_title="Where the Water on a Glacier Goes",
        topic_description="A glacier surface opened in section to reveal the meltwater shaft running through the ice",
        real_basis="Moulins are near-vertical shafts melted through glacier ice by surface meltwater, sometimes reaching the bed hundreds of metres below.",
        everyday_surface="a flat white ice field",
        hidden_interior="a blue shaft carrying water into the ice",
        ambient_sounds={
            "before": "wind across open ice, a thin stream running",
            "turn": "ice cracking sharply, a report echoing",
            "after": "water falling a long way, a deep hollow resonance",
        },
    ),
    CutawayConcept(
        id_slug="bridge-pier-hollow",
        name="Bridge Piers",
        category_group="Engineering Interiors",
        environments=["a plain concrete bridge pier standing in a slow estuary, flat sky behind"],
        architectures=["a hollow pier with a ladder and inspection platforms running its height"],
        transformations=["the pier opening in a clean vertical section"],
        camera_styles=["locked-off wide shot from the water's level"],
        lighting_schemes=["flat marine daylight, a single service lamp inside"],
        materials=["tide-marked concrete", "steel ladder", "grated platform", "standing water at the base"],
        reveals=["a ladder climbing the hollow shaft, platforms at intervals, a tide mark high on the inner wall"],
        default_title="Bridge Piers Are Hollow",
        topic_description="A bridge pier opened in section to reveal the inspection shaft inside it",
        real_basis="Large bridge piers are commonly built hollow with internal ladders and inspection platforms so the structure can be examined from within.",
        everyday_surface="a solid-looking concrete pier",
        hidden_interior="a ladder shaft with inspection platforms",
        ambient_sounds={
            "before": "estuary water against concrete, wind, a distant horn",
            "turn": "concrete parting, a hollow boom inside",
            "after": "dripping into standing water, steel ringing faintly",
        },
    ),
    CutawayConcept(
        id_slug="rock-overhang-town",
        name="Rock Overhangs",
        category_group="Under the Ground",
        environments=["a narrow whitewashed street under a huge grey rock overhang"],
        architectures=["houses built directly into the overhang, the rock forming their roofs"],
        transformations=["the rock face opening in section, the rooms appearing inside the mass"],
        camera_styles=["locked-off wide shot along the street"],
        lighting_schemes=["bright sun on the street, cool shadow deep under the rock"],
        materials=["whitewashed render", "raw grey rock ceiling", "timber beams", "tiled floor"],
        reveals=["rooms running back into the rock, their ceilings the raw stone itself, lamps lit deep inside"],
        default_title="Their Roofs Are the Mountain",
        topic_description="A rock overhang opened in section to reveal the houses built into the stone beneath it",
        real_basis="At Setenil de las Bodegas in Spain, houses are built under and into a basalt overhang, which forms their roofs; comparable cave-dwelling towns include Matera in Italy.",
        everyday_surface="a normal whitewashed street",
        hidden_interior="rooms running back into solid rock",
        ambient_sounds={
            "before": "a quiet street, footsteps, a shutter",
            "turn": "rock parting with a dry grinding",
            "after": "close indoor quiet, a fire in a hearth, muffled street sound",
        },
    ),
]
