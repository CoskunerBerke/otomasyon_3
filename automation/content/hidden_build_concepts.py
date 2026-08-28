"""
Concept library for hidden_build_story Reels -- an unexpected object is buried in a yard
and revealed as something nobody expects.

The format was proven manually on 2026-08-21 with a school bus that turned out to be an
underground pool, and an aircraft fuselage that turned out to be an underground garden.
Both held their setting and their craftsman across three beats, which is what makes the
format viable at all.

Two things carry every Reel and must not drift:

    the craftsman   -- the same man in all fourteen Reels, because the channel's profile
                       picture on all three platforms is his face. He is defined once, in
                       HiddenBuildPlanner.CRAFTSMAN, never here.
    the surprise    -- the reveal must contradict what the burial implies. A bus that
                       becomes a shelter is not a story; a bus that becomes a lit pool is.

HiddenBuildConcept extends ConceptDefinition so the existing diversity ranking, manifest
round-trip and concept-slug rebuild keep working unchanged. The inherited fields carry
this format's meaning:

    environments   -> the neglected yard before anything happens
    architectures  -> the buried object itself
    transformations-> how it goes into the ground and disappears
    reveals        -> what is found down the stairs
"""
from dataclasses import dataclass, field
from typing import Dict, List

from .concepts import ConceptDefinition


@dataclass
class HiddenBuildConcept(ConceptDefinition):
    """One buried object, the surprise it hides, and who watches it happen."""

    # What goes into the ground. Named plainly so Flow renders a recognisable object.
    buried_object: str = ""

    # What the camera finds underground. This is the payoff and must contradict the
    # expectation the burial sets up.
    surprise_reveal: str = ""

    # Who watches from outside, and who is enjoying the result in the final beat. Kept
    # deliberately plain: distinctive props (headscarves, patterned coats) are the first
    # thing to drift between segments.
    observer: str = ""

    # Diegetic sound per beat. Keys: "before", "turn", "after". Never speech.
    ambient_sounds: Dict[str, str] = field(default_factory=dict)


def _c(**kw) -> HiddenBuildConcept:
    """Fills the inherited list fields, which this format uses one value at a time."""
    kw.setdefault("camera_styles", ["high wide static shot from the back of the yard"])
    kw.setdefault("lighting_schemes", ["overcast soft daylight, cool natural tones"])
    return HiddenBuildConcept(**kw)


HIDDEN_BUILD_CONCEPTS: List[HiddenBuildConcept] = [
    # ---------------------------------------------------------------- 2026-08-28
    # The pool held exactly fourteen concepts and a week needs fourteen, so the second
    # week came out a repeat of the first: same slugs, same titles, same videos. The
    # cross-week id guard caught it -- verification searches the channel by title, found
    # LAST week's identical Reel and claimed its video id -- but that guard is the alarm,
    # not the fix. These fourteen make two distinct weeks possible.
    _c(
        id_slug="locomotive-sauna",
        name="Locomotive Sauna",
        category_group="Industrial",
        buried_object="a black steam locomotive",
        surprise_reveal="a cedar sauna",
        observer="a middle-aged man in a plain dark jacket",
        environments=["a flat gravel yard behind a stone cottage, bare hills beyond"],
        architectures=["a black steam locomotive with its boiler and cab intact"],
        transformations=["lowered nose-first into a long trench until the cab roof sits level with the gravel, then covered over"],
        materials=["pale cedar planking, blackened iron rivets, brass gauges, hot stones on a steel grate"],
        reveals=["a cedar-lined sauna running the length of the boiler, iron rivets showing through the timber, steam rising off hot stones under the old pressure gauges"],
        default_title="He Buried a Locomotive. It Is Warm Inside",
        topic_description="A steam locomotive buried in a gravel yard turns out to be an underground cedar sauna",
        ambient_sounds={
            "before": "wind across open hills, gravel underfoot, a crow",
            "turn": "crane motor, iron groaning, earth pouring over steel plate",
            "after": "water hissing on hot stones, timber ticking as it warms, a long enclosed quiet",
        },
    ),
    _c(
        id_slug="watertower-cellar",
        name="Water Tower Cellar",
        category_group="Industrial",
        buried_object="a riveted steel water tower tank",
        surprise_reveal="a wine cellar",
        observer="an older woman in a plain brown coat",
        environments=["a bare chalk field with a single track running past it"],
        architectures=["a riveted cylindrical steel water tower tank, its legs cut away"],
        transformations=["lowered upright into a round shaft until its rim sits flush with the field, then earthed over"],
        materials=["riveted steel, oak racking, chalk walls, low amber lamps"],
        reveals=["a circular cellar lined floor to ceiling with oak racking, bottles catching amber lamplight, riveted steel curving overhead"],
        default_title="A Water Tower Went Into the Ground. Look Inside",
        topic_description="A steel water tower tank buried in a chalk field turns out to be a circular underground wine cellar",
        ambient_sounds={
            "before": "open field wind, a distant train, skylarks",
            "turn": "chain hoist clicking, steel ringing, chalk and soil sliding",
            "after": "footsteps on stone, glass touching glass, a deep cool silence",
        },
    ),
    _c(
        id_slug="helicopter-observatory",
        name="Helicopter Observatory",
        category_group="Vehicles",
        buried_object="a retired passenger helicopter fuselage",
        surprise_reveal="a star observatory",
        observer="a young man in a plain grey sweater",
        environments=["a bare moorland clearing, heather and loose stone, no buildings in sight"],
        architectures=["a retired passenger helicopter fuselage with its rotors removed"],
        transformations=["lowered tail-first into a sloped trench until only a glazed hatch remains at ground level, then buried"],
        materials=["white aluminium skin, black rubber seals, brass telescope fittings, deep blue felt lining"],
        reveals=["a small domed room lined in deep blue felt, a brass telescope aimed through the glazed hatch, star charts pinned along the curved fuselage wall"],
        default_title="He Buried a Helicopter to Look at the Sky",
        topic_description="A helicopter fuselage buried in moorland turns out to be an underground star observatory",
        ambient_sounds={
            "before": "moorland wind, curlew calls, boots on loose stone",
            "turn": "crane motor, aluminium flexing, heather and peat falling over the hull",
            "after": "a telescope mount turning slowly, paper rustling, wind muffled far above",
        },
    ),
    _c(
        id_slug="caravan-bakery",
        name="Caravan Bakery",
        category_group="Vehicles",
        buried_object="a small cream-coloured touring caravan",
        surprise_reveal="a bread bakery",
        observer="a woman in a plain dark apron",
        environments=["a small walled yard of cracked concrete behind a terraced house"],
        architectures=["a small cream-coloured touring caravan"],
        transformations=["lowered flat into a shallow pit until its roof sits below the concrete, then slabbed over"],
        materials=["fire brick, dusted flour, blackened steel oven door, worn beech worktop"],
        reveals=["a brick-vaulted bakery filling the caravan shell, a wood oven glowing at one end, loaves cooling on a beech bench under warm light"],
        default_title="They Buried a Caravan. Now It Bakes Bread",
        topic_description="A touring caravan buried in a walled yard turns out to be an underground wood-fired bakery",
        ambient_sounds={
            "before": "a quiet back yard, a gate, distant traffic",
            "turn": "small excavator, concrete cracking, soil raked flat",
            "after": "a wood fire drawing, a peel scraping brick, a soft enclosed warmth",
        },
    ),
    _c(
        id_slug="crane-cab-study",
        name="Crane Cab Study",
        category_group="Industrial",
        buried_object="a tower crane operator cab",
        surprise_reveal="a writing study",
        observer="a man in a plain navy jacket",
        environments=["a bare clay building plot, orange soil and puddles, hoardings behind"],
        architectures=["a glazed tower crane operator cab lifted off its mast"],
        transformations=["lowered glass-down into a square pit until its roof is level with the clay, then covered"],
        materials=["yellow painted steel, green glass, dark walnut desk, brass lamp"],
        reveals=["a small study inside the cab shell, a walnut desk under a brass lamp, books stacked to the green glass roof with daylight falling through it"],
        default_title="A Crane Cab Went Under the Mud. Look Now",
        topic_description="A tower crane cab buried in a clay plot turns out to be an underground writing study",
        ambient_sounds={
            "before": "site hoarding rattling in wind, water in a puddle, a lorry passing",
            "turn": "hoist motor, steel settling, wet clay slapping against glass",
            "after": "a chair creaking, pages turning, rain drumming faintly on the glass above",
        },
    ),
    _c(
        id_slug="submarine-gym",
        name="Submarine Gym",
        category_group="Vessels",
        buried_object="a small black research submarine",
        surprise_reveal="a training gym",
        observer="a young woman in plain dark sportswear",
        environments=["a flat shingle yard beside a sea wall, grey water beyond"],
        architectures=["a small black research submarine with its conning tower intact"],
        transformations=["lowered on its side into a long trench until the tower is the only thing left above the shingle, then buried"],
        materials=["black steel plate, rubber matting, chromed bars, cold white strip light"],
        reveals=["a narrow gym running the hull length, chromed bars bolted between the ribs, rubber matting underfoot, white light along the spine of the boat"],
        default_title="He Buried a Submarine and Trains Inside It",
        topic_description="A small submarine buried beside a sea wall turns out to be an underground training gym",
        ambient_sounds={
            "before": "waves on shingle, wind over a sea wall, gulls",
            "turn": "crane motor, steel hull ringing, shingle pouring over plate",
            "after": "metal plates settling on a rack, breathing, a hard enclosed echo",
        },
    ),
    _c(
        id_slug="tugboat-kitchen",
        name="Tugboat Kitchen",
        category_group="Vessels",
        buried_object="a red and black harbour tugboat",
        surprise_reveal="a working kitchen",
        observer="a man in a plain white shirt",
        environments=["a bare gravel hardstanding beside a tidal creek, mud flats beyond"],
        architectures=["a red and black harbour tugboat with its wheelhouse still on"],
        transformations=["lowered keel-first into a hull-shaped pit until the deck is level with the gravel, then covered over"],
        materials=["riveted red steel, stainless benches, copper pans, warm filament bulbs"],
        reveals=["a long kitchen filling the hull, stainless benches down one side, copper pans hanging under the old deck beams, filament bulbs warm against red steel"],
        default_title="A Tugboat Went Into the Mud. It Is a Kitchen",
        topic_description="A harbour tugboat buried beside a tidal creek turns out to be an underground kitchen",
        ambient_sounds={
            "before": "creek water, wind over mud flats, a distant boat engine",
            "turn": "crane motor, hull plates flexing, wet gravel sliding down steel",
            "after": "a gas ring lighting, pans touching, a low enclosed hum",
        },
    ),
    _c(
        id_slug="combine-workshop",
        name="Combine Workshop",
        category_group="Vehicles",
        buried_object="a green combine harvester body",
        surprise_reveal="a woodworking workshop",
        observer="an older man in a plain canvas coat",
        environments=["a stubble field after harvest, flat to the horizon"],
        architectures=["a green combine harvester with its header removed"],
        transformations=["lowered into a wide trench until the cab roof sits below the stubble, then ploughed over"],
        materials=["green painted steel, pale birch bench, hand tools on a board, sawdust"],
        reveals=["a workshop built into the machine body, a birch bench along one wall, hand tools ranked on a board, sawdust catching low light"],
        default_title="They Buried a Combine. Now He Works Down There",
        topic_description="A combine harvester buried in a stubble field turns out to be an underground woodworking workshop",
        ambient_sounds={
            "before": "wind across stubble, a tractor far off, rooks",
            "turn": "excavator tracks, steel groaning, dry soil pouring over panels",
            "after": "a hand plane on timber, tools set down, a close wooden quiet",
        },
    ),
    _c(
        id_slug="mixer-pottery",
        name="Cement Mixer Pottery",
        category_group="Vehicles",
        buried_object="the drum of a concrete mixer truck",
        surprise_reveal="a pottery studio",
        observer="a woman in a plain grey smock",
        environments=["a bare yard of broken concrete behind a low workshop"],
        architectures=["the ribbed steel drum of a concrete mixer truck, cut from its chassis"],
        transformations=["lowered mouth-up into a round pit until the rim is flush with the broken concrete, then sealed around"],
        materials=["ribbed grey steel, wet clay, pale glaze pots, an orange kiln glow"],
        reveals=["a round studio inside the drum, a wheel at its centre, glaze pots ranked along the ribbed wall, a kiln glowing orange at the back"],
        default_title="A Mixer Drum Went Underground. Look Inside",
        topic_description="A concrete mixer drum buried in a yard turns out to be a round underground pottery studio",
        ambient_sounds={
            "before": "a quiet industrial yard, loose concrete underfoot, a distant saw",
            "turn": "chain hoist, steel ringing hollow, rubble poured around the rim",
            "after": "a potter wheel turning, water in a bowl, a kiln ticking as it heats",
        },
    ),
    _c(
        id_slug="windmill-music-room",
        name="Windmill Music Room",
        category_group="Industrial",
        buried_object="the timber cap and shaft of an old windmill",
        surprise_reveal="a music room",
        observer="a young man in a plain black jumper",
        environments=["a bare rise of short grass, wide sky, no trees"],
        architectures=["the tarred timber cap and drive shaft of an old windmill, sails removed"],
        transformations=["lowered shaft-down into a deep round shaft until the cap sits like a lid on the grass, then turfed around"],
        materials=["tarred oak, iron banding, dark felt lining, black piano lacquer"],
        reveals=["a round felt-lined room under the cap, an upright piano against the oak, the old drive shaft running down through the middle of the floor"],
        default_title="He Buried a Windmill Cap. Listen to What Is Under It",
        topic_description="A windmill cap buried in a grass rise turns out to be a round underground music room",
        ambient_sounds={
            "before": "steady open wind, grass moving, a skylark",
            "turn": "hoist chain, oak creaking, turf laid back over timber",
            "after": "a piano note held and decaying, felt absorbing it, wind gone entirely",
        },
    ),
    _c(
        id_slug="icecream-van-florist",
        name="Ice Cream Van Florist",
        category_group="Vehicles",
        buried_object="a pale blue ice cream van",
        surprise_reveal="a flower room",
        observer="a woman in a plain green apron",
        environments=["a narrow strip of bare earth between two brick walls"],
        architectures=["a pale blue ice cream van with its serving hatch still fitted"],
        transformations=["lowered flat into a van-length trench until the roof is below the earth, then levelled over"],
        materials=["pale blue steel, zinc buckets, cut stems, cold white light"],
        reveals=["a cool flower room filling the van, zinc buckets of cut stems along both sides, the serving hatch glazed and glowing at one end"],
        default_title="They Buried an Ice Cream Van. It Is Full of Flowers",
        topic_description="An ice cream van buried between two walls turns out to be an underground flower room",
        ambient_sounds={
            "before": "a narrow alley, dripping from a gutter, muffled street",
            "turn": "small excavator, panel steel bending, earth raked level",
            "after": "water poured into a zinc bucket, stems cut, a cool close quiet",
        },
    ),
    _c(
        id_slug="postbus-archive",
        name="Post Bus Archive",
        category_group="Vehicles",
        buried_object="a yellow rural post bus",
        surprise_reveal="a map archive",
        observer="an older man in a plain dark waistcoat",
        environments=["a bare alpine meadow, cut grass, mountains behind"],
        architectures=["a yellow rural post bus with its destination board still fitted"],
        transformations=["lowered into a long trench until the roofline sits under the meadow, then re-turfed"],
        materials=["yellow painted steel, oak drawer fronts, rolled paper, low green lamps"],
        reveals=["a long archive down the length of the bus, shallow oak drawers to the ceiling, rolled maps stacked at one end under low green lamps"],
        default_title="A Post Bus Went Under a Meadow. Look Inside",
        topic_description="A rural post bus buried in an alpine meadow turns out to be an underground map archive",
        ambient_sounds={
            "before": "cowbells far off, wind through cut grass, a stream",
            "turn": "excavator, steel panels flexing, turf rolled back over the roof",
            "after": "a drawer sliding open, paper unrolling, a still dry quiet",
        },
    ),
    _c(
        id_slug="trawler-smokehouse",
        name="Trawler Smokehouse",
        category_group="Vessels",
        buried_object="a wooden fishing trawler hull",
        surprise_reveal="a smokehouse",
        observer="a man in a plain oilskin coat",
        environments=["a bare shingle bank above a harbour, boats drawn up beyond"],
        architectures=["a wooden fishing trawler hull, mast and rigging removed"],
        transformations=["lowered upright into a hull-shaped pit until the gunwales are level with the shingle, then covered"],
        materials=["tarred planking, iron hooks, hanging fish, blue smoke"],
        reveals=["a smokehouse filling the hull, iron hooks along the ribs, blue smoke drifting up between the planks toward a vent at deck level"],
        default_title="He Buried a Trawler. Something Is Cooking",
        topic_description="A wooden trawler hull buried above a harbour turns out to be an underground smokehouse",
        ambient_sounds={
            "before": "harbour water, rigging tapping, gulls",
            "turn": "crane motor, timber groaning, shingle pouring against planking",
            "after": "a low fire drawing, wood ticking, smoke moving through a narrow space",
        },
    ),
    _c(
        id_slug="steamroller-forge",
        name="Steam Roller Forge",
        category_group="Industrial",
        buried_object="a green steam road roller",
        surprise_reveal="a blacksmith forge",
        observer="a man in a plain leather apron",
        environments=["a bare compacted-earth yard beside a stone barn"],
        architectures=["a green steam road roller with its canopy and flywheel intact"],
        transformations=["lowered into a deep pit until the canopy is level with the earth, then filled around"],
        materials=["green painted iron, firebrick, glowing coals, hammered steel"],
        reveals=["a forge built into the roller frame, a firebrick hearth glowing under the old canopy, hammers ranked along the flywheel housing"],
        default_title="A Steam Roller Went Down. It Is Burning Inside",
        topic_description="A steam road roller buried in an earth yard turns out to be an underground blacksmith forge",
        ambient_sounds={
            "before": "wind around a stone barn, loose earth underfoot, a dog far off",
            "turn": "crane motor, cast iron settling, earth thudding against the frame",
            "after": "bellows drawing, coals shifting, a hammer on hot steel ringing in a closed space",
        },
    ),
    _c(
        id_slug="school-bus-pool",
        name="School Bus Pool",
        category_group="Vehicles",
        buried_object="a full-size yellow American school bus",
        surprise_reveal="a private swimming pool",
        observer="an elderly couple, both with white hair, in plain grey and navy knitwear",
        environments=["a long narrow suburban backyard overgrown with tall wild grass"],
        architectures=["a full-size yellow American school bus"],
        transformations=["lowered into a bus-length trench until its roof sits below ground level, then buried under earth and fresh turf"],
        materials=["turquoise and deep-blue mosaic tile, pale stone coping, honey-toned timber ceiling slats"],
        reveals=["a long turquoise mosaic pool running the length of the bus, warm timber curved ceiling, a wall-mounted television, and a mirror ball scattering blue and violet light across the water"],
        default_title="They Buried a School Bus. Look What's Under It",
        topic_description="A yellow school bus buried in a suburban backyard turns out to be a private underground pool",
        ambient_sounds={
            "before": "excavator engine, soil and gravel falling, rake scraping, distant suburban birdsong",
            "turn": "crane motor, metal creaking, soil pouring over steel, turf unrolling, a drill on timber",
            "after": "footsteps on timber stairs, a door opening, water lapping and echoing in an enclosed space, faint television murmur",
        },
    ),
    _c(
        id_slug="container-cinema",
        name="Container Cinema",
        category_group="Industrial",
        buried_object="a rusty dark-red steel shipping container",
        surprise_reveal="a private cinema",
        observer="a woman in her late sixties with short white hair in a plain grey cardigan",
        environments=["a bare suburban backyard of patchy dirt, dry weeds and scattered rubble"],
        architectures=["a rusty dark-red steel shipping container"],
        transformations=["craned into a deep rectangular pit, then covered over with earth and rolled turf until nothing shows"],
        materials=["burgundy velvet, dark acoustic wall panels, warm amber light strips, dark patterned carpet"],
        reveals=["four deep burgundy velvet recliners facing a huge glowing screen, dark acoustic ceiling panels edged with amber light, and a small popcorn machine glowing on a side console"],
        default_title="He Buried a Shipping Container in His Yard",
        topic_description="A steel shipping container buried in a backyard turns out to be an underground cinema",
        ambient_sounds={
            "before": "excavator engine, rubble and soil falling, distant traffic",
            "turn": "crane motor, heavy steel groaning, soil pouring, turf unrolling, a drill on timber",
            "after": "footsteps on timber stairs, a door opening, a low cinematic rumble from the screen, a popcorn machine ticking",
        },
    ),
    _c(
        id_slug="aircraft-garden",
        name="Aircraft Garden",
        category_group="Vehicles",
        buried_object="the white fuselage of a retired passenger aircraft with its wings removed",
        surprise_reveal="an underground garden",
        observer="a woman in her early seventies with white hair in a plain olive cardigan",
        environments=["a flat rural yard of dry cracked earth behind a farmhouse, a red barn and open fields beyond"],
        architectures=["the white fuselage of a retired passenger aircraft"],
        transformations=["lowered by two cranes into an unusually long channel, then buried under earth and laid turf"],
        materials=["tiered planting beds, gravel path, curved white cabin walls, deep pink and violet grow-lights"],
        reveals=["tiered planting beds of ferns, vines, herbs and young fruit trees running the full length of the cabin under deep pink and violet grow-lights, thin mist drifting between the leaves, and the original aircraft windows glowing from within"],
        default_title="A Plane Went Into the Ground. This Is Inside It",
        topic_description="An aircraft fuselage buried behind a farmhouse turns out to be an underground garden",
        ambient_sounds={
            "before": "excavator tracks and engine, dry soil falling, wind across open fields, a distant dog",
            "turn": "crane motors, aluminium creaking, soil pouring, turf unrolling, hammering",
            "after": "footsteps on timber stairs, a door opening, misters hissing, leaves rustling, enclosed room tone",
        },
    ),
    _c(
        id_slug="carriage-diner",
        name="Railway Carriage Diner",
        category_group="Vehicles",
        buried_object="a dark green vintage railway carriage",
        surprise_reveal="a 1950s American diner",
        observer="two teenage neighbours in plain hooded sweatshirts",
        environments=["a narrow back garden of flattened weeds behind a brick terrace"],
        architectures=["a dark green vintage railway carriage"],
        transformations=["slid down rails into a long trench, then sealed under earth and new grass"],
        materials=["red vinyl booths, polished chrome, chequerboard floor tiles, warm neon tubing"],
        reveals=["red vinyl booths down both sides of the carriage, a polished chrome counter with stools, a chequerboard floor, and warm neon tubing tracing the curved ceiling"],
        default_title="Nobody Expected What Was Under the Garden",
        topic_description="A vintage railway carriage buried behind a terrace turns out to be an underground diner",
        ambient_sounds={
            "before": "spades in soil, weeds being cut, distant town traffic",
            "turn": "steel wheels on rail, heavy machinery, soil pouring, turf unrolling",
            "after": "footsteps on timber stairs, a door opening, a neon tube humming, a coffee machine hissing, cutlery clinking",
        },
    ),
    _c(
        id_slug="silo-bowling",
        name="Grain Silo Bowling Alley",
        category_group="Industrial",
        buried_object="a long corrugated steel grain silo laid on its side",
        surprise_reveal="a two-lane bowling alley",
        observer="an elderly farmer in a plain checked shirt",
        environments=["a wide bare farmyard of dry rutted soil beside a weathered barn"],
        architectures=["a long corrugated steel grain silo laid on its side"],
        transformations=["rolled into a long trench by two excavators, then covered with earth and reseeded grass"],
        materials=["pale polished lane timber, black rubber flooring, cool neon strip lighting, corrugated curved ceiling"],
        reveals=["two polished timber bowling lanes running the length of the silo, pins standing at the far end under cool neon strips, black rubber flooring and a ball return rack along the curved corrugated wall"],
        default_title="He Buried a Grain Silo. Then He Went Bowling",
        topic_description="A grain silo buried in a farmyard turns out to be an underground bowling alley",
        ambient_sounds={
            "before": "excavator engine, dry soil and stones falling, wind across the farmyard",
            "turn": "steel rolling and booming, heavy machinery, soil pouring, seed spreading",
            "after": "footsteps on timber stairs, a door opening, a bowling ball rolling and pins scattering, neon humming",
        },
    ),
    _c(
        id_slug="doubledecker-library",
        name="Double-Decker Library",
        category_group="Vehicles",
        buried_object="a red London double-decker bus",
        surprise_reveal="a two-storey library",
        observer="a man in his sixties with white hair in a plain brown jumper",
        environments=["a deep narrow garden of long unmown grass behind a stone cottage"],
        architectures=["a red London double-decker bus"],
        transformations=["craned upright into a deep shaft, then buried under earth and turf"],
        materials=["dark oak shelving, brass reading lamps, a spiral iron staircase, deep green carpet"],
        reveals=["dark oak shelves packed with books rising through both decks, a spiral iron staircase joining them, brass reading lamps glowing over a leather armchair, and deep green carpet underfoot"],
        default_title="A Bus Went Down. A Library Came Back",
        topic_description="A double-decker bus buried behind a cottage turns out to be a two-storey underground library",
        ambient_sounds={
            "before": "scythe through long grass, excavator engine, birdsong",
            "turn": "crane motor, metal groaning, soil pouring over the roof, turf unrolling",
            "after": "footsteps on timber stairs, a door opening, pages turning, a clock ticking, enclosed room tone",
        },
    ),
    _c(
        id_slug="yacht-cellar",
        name="Yacht Wine Cellar",
        category_group="Vessels",
        buried_object="the white hull of a stripped motor yacht",
        surprise_reveal="a stone wine cellar",
        observer="a couple in their fifties in plain dark clothing",
        environments=["a sloping garden of bare clay and gravel behind a stucco house"],
        architectures=["the white hull of a stripped motor yacht"],
        transformations=["lowered keel-down into a shaped pit, then packed over with earth and gravel paths"],
        materials=["rough stone cladding, dark timber racking, wrought iron candle sconces, slate floor"],
        reveals=["dark timber wine racking following the curve of the hull on both sides, rough stone cladding between the racks, wrought iron sconces throwing candlelight, and a slate floor with a small tasting table"],
        default_title="They Buried a Boat. Then They Went Down for a Drink",
        topic_description="A yacht hull buried in a garden turns out to be an underground wine cellar",
        ambient_sounds={
            "before": "spades in clay, gravel shifting, excavator engine, distant gulls",
            "turn": "crane motor, fibreglass creaking, earth packing, gravel raking",
            "after": "footsteps on timber stairs, a door opening, glass touching glass, a cork drawn, deep enclosed quiet",
        },
    ),
    _c(
        id_slug="tanker-spa",
        name="Tanker Spa",
        category_group="Industrial",
        buried_object="a steel road tanker barrel",
        surprise_reveal="a sauna and ice plunge",
        observer="two neighbours in plain winter coats",
        environments=["a frost-covered back garden of hard bare ground behind a timber house"],
        architectures=["a steel road tanker barrel"],
        transformations=["rolled into a curved trench and sealed under earth and frosted turf"],
        materials=["pale cedar benches, black slate, a glass partition, cold blue-white light over dark water"],
        reveals=["a cedar-lined sauna filling one half of the barrel behind a glass partition, and a black slate ice plunge pool in the other half under cold blue-white light, steam drifting between the two"],
        default_title="Under the Frozen Garden Was Something Warmer",
        topic_description="A steel tanker buried in a frozen garden turns out to be an underground sauna and ice plunge",
        ambient_sounds={
            "before": "picks on frozen ground, excavator engine, wind, boots on frost",
            "turn": "steel booming and rolling, frozen soil falling, hammering",
            "after": "footsteps on timber stairs, a door opening, sauna stones hissing, water sloshing, timber ticking as it warms",
        },
    ),
    _c(
        id_slug="subway-studio",
        name="Subway Car Studio",
        category_group="Vehicles",
        buried_object="a graffiti-covered subway car",
        surprise_reveal="a recording studio",
        observer="a young neighbour in a plain black t-shirt",
        environments=["a rubble-strewn urban back lot behind a brick warehouse"],
        architectures=["a graffiti-covered subway car"],
        transformations=["craned into a rectangular pit between the walls, then buried under earth and paving"],
        materials=["black acoustic foam wedges, warm oak panelling, a glass control window, small blue and red console lights"],
        reveals=["a live room lined with black acoustic wedges at one end of the car, a glass window through to a mixing desk glowing with small blue and red lights, warm oak panelling and a microphone standing under a single warm spotlight"],
        default_title="A Subway Car Disappeared Into This Yard",
        topic_description="A subway car buried in an urban back lot turns out to be an underground recording studio",
        ambient_sounds={
            "before": "excavator engine, brick rubble falling, city traffic beyond the wall",
            "turn": "crane motor, steel groaning, soil pouring, paving slabs set down",
            "after": "footsteps on timber stairs, a heavy door sealing, sudden acoustic deadness, a single guitar note, faint console hum",
        },
    ),
    _c(
        id_slug="lifeboat-aquarium",
        name="Lifeboat Aquarium",
        category_group="Vessels",
        buried_object="a bright orange enclosed lifeboat",
        surprise_reveal="an aquarium tunnel",
        observer="a grandmother with white hair and a small child, both plainly dressed",
        environments=["a sandy coastal garden of marram grass and bare dune behind a clapboard house"],
        architectures=["a bright orange enclosed lifeboat"],
        transformations=["dropped into a dune hollow and covered over with sand and planted grass"],
        materials=["curved glass panels, blue-lit water, pale sand-coloured floor, soft rippling light"],
        reveals=["curved glass tanks along both sides of the hull filled with fish and swaying weed, blue light rippling across a pale floor and across the faces of anyone standing in the narrow walkway between them"],
        default_title="They Buried a Lifeboat in the Dunes",
        topic_description="A lifeboat buried in a coastal garden turns out to be an underground aquarium tunnel",
        ambient_sounds={
            "before": "spades in sand, marram grass in the wind, distant surf, gulls",
            "turn": "crane motor, fibreglass creaking, sand pouring, grass being planted",
            "after": "footsteps on timber stairs, a door opening, water filtration humming, muffled surf above",
        },
    ),
    _c(
        id_slug="firetruck-playroom",
        name="Fire Truck Playroom",
        category_group="Vehicles",
        buried_object="a red fire engine with its ladder removed",
        surprise_reveal="a children's playroom",
        observer="a mother and two small children, plainly dressed",
        environments=["a small suburban back garden of trampled mud and a broken fence"],
        architectures=["a red fire engine with its ladder removed"],
        transformations=["lowered into a short deep pit, then covered with earth and soft new lawn"],
        materials=["padded floor matting, a brass sliding pole, primary-coloured climbing nets, warm ceiling lights"],
        reveals=["a brass pole dropping through the ceiling into a padded play floor, climbing nets and a small slide built into the old crew compartment, and warm lights along the curved red ceiling"],
        default_title="The Fire Engine Went Under the Lawn",
        topic_description="A fire engine buried in a small garden turns out to be an underground playroom",
        ambient_sounds={
            "before": "spades in wet mud, a fence panel dropped, excavator engine, suburban birdsong",
            "turn": "crane motor, steel creaking, soil pouring, turf unrolling",
            "after": "footsteps on timber stairs, a door opening, small feet on padded matting, a ball bouncing",
        },
    ),
    _c(
        id_slug="gondola-teahouse",
        name="Cable Car Tea House",
        category_group="Vessels",
        buried_object="two red alpine cable car cabins",
        surprise_reveal="a tea house",
        observer="an elderly couple in plain wool coats",
        environments=["a steep mountain garden of loose scree and coarse grass behind a stone chalet"],
        architectures=["two red alpine cable car cabins joined end to end"],
        transformations=["winched down into a cut in the slope and buried under stone and turf"],
        materials=["low pale wood tables, floor cushions, paper lanterns, a copper kettle"],
        reveals=["low pale wood tables and floor cushions running through both joined cabins, paper lanterns glowing overhead, a copper kettle steaming on a small stove, and the original cabin windows now looking into lit stone"],
        default_title="Two Cable Cars Went Into the Mountain",
        topic_description="Two cable car cabins buried in a mountain garden turn out to be an underground tea house",
        ambient_sounds={
            "before": "scree shifting, picks on stone, wind across the slope, a distant cowbell",
            "turn": "winch cable straining, cabins knocking together, stone and soil falling",
            "after": "footsteps on timber stairs, a door sliding, a kettle coming to the boil, water poured, deep mountain quiet",
        },
    ),
    _c(
        id_slug="ambulance-darkroom",
        name="Ambulance Darkroom",
        category_group="Vehicles",
        buried_object="a boxy white ambulance",
        surprise_reveal="a photography darkroom",
        observer="a man in his forties in a plain grey shirt",
        environments=["a walled back yard of cracked concrete and dead planters"],
        architectures=["a boxy white ambulance"],
        transformations=["lowered through the broken concrete into a pit, then sealed under new paving and gravel"],
        materials=["deep red safelight, stainless developing trays, drying lines of hanging prints, matte black walls"],
        reveals=["deep red safelight over stainless developing trays down one wall, prints hanging from drying lines the length of the ambulance, matte black walls, and a single enlarger glowing at the far end"],
        default_title="An Ambulance Went Under the Concrete",
        topic_description="An ambulance buried in a walled yard turns out to be an underground darkroom",
        ambient_sounds={
            "before": "concrete breaker, slabs cracking, excavator engine, city hum",
            "turn": "crane motor, steel creaking, soil pouring, paving slabs set down, gravel raked",
            "after": "footsteps on timber stairs, a door sealing, liquid poured into trays, a timer ticking, enclosed quiet",
        },
    ),
    _c(
        id_slug="tram-greenhouse",
        name="Tram Greenhouse",
        category_group="Vehicles",
        buried_object="a cream and maroon vintage tram",
        surprise_reveal="an orchid house",
        observer="two elderly sisters in plain matching cardigans",
        environments=["a long municipal allotment plot of turned earth and bare canes"],
        architectures=["a cream and maroon vintage tram"],
        transformations=["slid into a trench along the plot and buried under soil and planted beds"],
        materials=["glass propagation shelves, brass misting pipes, warm white grow-lights, terracotta pots"],
        reveals=["tiers of orchids on glass shelves down both sides of the tram under warm white grow-lights, brass misting pipes threading the curved ceiling, terracotta pots along the old passenger windows, and mist drifting the length of the car"],
        default_title="The Tram Was Never Coming Back Up",
        topic_description="A vintage tram buried in an allotment turns out to be an underground orchid house",
        ambient_sounds={
            "before": "forks turning soil, canes knocking, allotment birdsong",
            "turn": "steel sliding on rail, soil pouring, beds raked and planted",
            "after": "footsteps on timber stairs, a door opening, misters hissing, water dripping from leaves",
        },
    ),
]

CONCEPTS_BY_SLUG = {c.id_slug: c for c in HIDDEN_BUILD_CONCEPTS}


def get_hidden_build_concept(id_slug: str) -> HiddenBuildConcept:
    if id_slug not in CONCEPTS_BY_SLUG:
        raise KeyError(f"Unknown hidden-build concept '{id_slug}'")
    return CONCEPTS_BY_SLUG[id_slug]
