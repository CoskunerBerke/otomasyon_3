"""
Concepts library and combinatorial datasets for silent satisfying transformation Reels.
Contains 40+ structured categories and multi-dimensional visual descriptors.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any

@dataclass
class ConceptDefinition:
    id_slug: str
    name: str
    category_group: str
    environments: List[str]
    architectures: List[str]
    transformations: List[str]
    camera_styles: List[str]
    lighting_schemes: List[str]
    materials: List[str]
    reveals: List[str]
    default_title: str
    topic_description: str

CATEGORIES: List[ConceptDefinition] = [
    ConceptDefinition(
        id_slug="futuristic-city",
        name="Futuristic City Construction",
        category_group="Metropolis & Sci-Fi",
        environments=["empty barren plains", "dark sleek plateau", "coastal bay", "highland valley"],
        architectures=["sleek parametric glass towers", "curved kinetic skyscrapers", "hyper-modern tiered spires"],
        transformations=["glowing grid foundations expanding and rising into crystalline skyscrapers", "subterranean kinetic pillars lifting glass towers"],
        camera_styles=["elevated cinematic 45-degree angle slowly pulling back", "smooth sweeping orbit turning into high-angle aerial view"],
        lighting_schemes=["golden hour dusk with glowing neon accents", "cool blue atmospheric twilight with warm interior tower lights"],
        materials=["reflective architectural glass", "polished brushed titanium", "luminescent fiber-optic conduits"],
        reveals=["fully illuminated futuristic metropolis pulsing with ambient energy", "vast panoramic skyline of ultra-modern towers"],
        default_title="Futuristic City Build",
        topic_description="Empty barren land transforming into a futuristic miniature metropolis"
    ),
    ConceptDefinition(
        id_slug="luxury-island",
        name="Luxury Island Development",
        category_group="Luxury & Resorts",
        environments=["pristine untouched tropical atoll", "crystal clear turquoise lagoon", "volcanic ocean island"],
        architectures=["overwater private glass villas", "curved infinity pool terraces", "sculptural modern pavilions"],
        transformations=["wooden boardwalks branching across water, luxury villas blooming over the lagoon", "modern white stone terraces stepping down to the ocean"],
        camera_styles=["aerial drone descent tracking across the turquoise bay", "cinematic slow forward dolly transitioning to high overview"],
        lighting_schemes=["vibrant tropical midday sun with crystal water caustics", "magical pink and orange sunset reflecting on water"],
        materials=["natural teak wood", "seamless white travertine marble", "crystalline infinity glass"],
        reveals=["ultra-luxury private island resort fully assembled in emerald waters", "masterpiece tropical haven with illuminated water villas"],
        default_title="Luxury Island Resort",
        topic_description="Untouched tropical island transforming into a world-class luxury eco resort"
    ),
    ConceptDefinition(
        id_slug="desert-megacity",
        name="Desert Megacity",
        category_group="Metropolis & Sci-Fi",
        environments=["vast golden sand dunes", "arid desert canyon", "wind-swept sandstone plateau"],
        architectures=["mirrored monolith skyscrapers", "biomimetic shade canopies", "subterranean oasis towers"],
        transformations=["sand dunes parting smoothly as colossal mirrored structures rise from bedrock", "curved linear mega-structures self-assembling across desert sands"],
        camera_styles=["high-altitude aerial tracking shot across the desert floor", "dramatic low-to-high crane pullback"],
        lighting_schemes=["warm golden desert sunset with long dramatic shadows", "crisp morning sunrise casting sharp light on mirrored facades"],
        materials=["mirrored solar glass", "aerospace-grade gold alloys", "sandstone composite panels"],
        reveals=["shimmering desert hyper-city standing majestically amidst pristine dunes", "futuristic technological oasis glowing in the twilight"],
        default_title="Desert Megacity",
        topic_description="Vast golden desert sands transforming into an awe-inspiring futuristic megacity"
    ),
    ConceptDefinition(
        id_slug="tropical-resort",
        name="Tropical Resort Construction",
        category_group="Luxury & Resorts",
        environments=["lush coastal jungle clearing", "private emerald bay", "coconut grove coastline"],
        architectures=["bamboo-vaulted eco-lodges", "cascading infinity lagoons", "curved open-air pavilions"],
        transformations=["stone pathways laying themselves through palms while multi-level wooden villas rise", "natural stone pools filling with cascading water as villas assemble"],
        camera_styles=["smooth gliding camera following the central pool axis", "elevated diagonal pullback through palm canopies"],
        lighting_schemes=["warm golden sunlight filtering through tropical leaves", "dusk with soft amber lantern illumination"],
        materials=["curved treated bamboo", "local river stone", "handcrafted thatch and glass"],
        reveals=["breathtaking jungle eco-sanctuary fully integrated with lush nature", "cascading tropical resort sparkling with ambient warm lights"],
        default_title="Tropical Eco Resort",
        topic_description="Lush jungle shoreline transforming into an ultra-luxury eco retreat"
    ),
    ConceptDefinition(
        id_slug="mountain-village",
        name="Mountain Village",
        category_group="Nature & Landscape",
        environments=["steep alpine valley", "snow-dusted pine ridge", "misty rocky mountain basin"],
        architectures=["timber-framed modern alpine chalets", "stepped stone terraces", "cozy illuminated cottages"],
        transformations=["switchback cobblestone roads carving up the slope while cozy chalets emerge in sequence", "stone terraces building upward with smoking stone chimneys"],
        camera_styles=["cinematic sweeping panoramic reveal down the mountain valley", "slow diagonal ascent along the village ridgeline"],
        lighting_schemes=["crisp morning alpine glow with rising mist", "cozy blue hour twilight with glowing golden windows"],
        materials=["rustic slate stone", "dark aged pine wood", "frosted window glass"],
        reveals=["picturesque alpine village nestled harmoniously among dramatic peaks", "warm fairy-tale mountain settlement glowing in the twilight"],
        default_title="Alpine Mountain Village",
        topic_description="Rugged mountain valley transforming into a picturesque alpine village"
    ),
    ConceptDefinition(
        id_slug="cliffside-city",
        name="Cliffside Futuristic City",
        category_group="Metropolis & Sci-Fi",
        environments=["dramatic sheer ocean cliffs", "vertical basalt rock wall", "deep fjord canyon"],
        architectures=["cantilevered glass residences", "vertical transportation towers", "terraced hanging gardens"],
        transformations=["support anchors locking into the cliff face as tiered glass pods extend outward over the ocean", "vertical elevator shafts carving down the rock as terraces unfurl"],
        camera_styles=["dramatic vertiginous camera drop along the cliff face pulling out to wide view", "cinematic ocean-level upward crane reveal"],
        lighting_schemes=["dramatic stormy sunset with breaking ocean waves", "clean crisp dawn light illuminating rock textures"],
        materials=["reinforced sea-grade composites", "ultra-clear structural glass", "dark textured basalt stone"],
        reveals=["monumental cliffside metropolis suspended gracefully over crashing ocean waves", "futuristic vertical city integrated seamlessly into sheer sea cliffs"],
        default_title="Cliffside Cyber City",
        topic_description="Sheer vertical rock cliff transforming into a futuristic suspended city"
    ),
    ConceptDefinition(
        id_slug="mars-colony",
        name="Mars Colony",
        category_group="Space & Off-World",
        environments=["red Martian crater", "dusty rust-colored canyon", "vast Olympus Mons foothills"],
        architectures=["interconnected geodesic domes", "3D-printed regolith habitats", "solar array towers"],
        transformations=["automated rover tracks forming roads, modular pressure domes inflating and sealing", "regolith 3D printing arms weaving protective outer shells over transparent biosphere domes"],
        camera_styles=["orbital satellite descent into the crater bowl", "smooth low-angle rover perspective rising to wide base reveal"],
        lighting_schemes=["intense rusty red atmospheric daylight with sharp shadows", "Martian blue sunset glowing faintly on the horizon"],
        materials=["aerospace polymers", "pressurized reinforced glass", "sintered red basalt regolith"],
        reveals=["fully operational self-sustaining Martian habitat glowing with lush green interiors", "epic planetary outpost sprawling across the red landscape"],
        default_title="Mars Colony Outpost",
        topic_description="Barren Martian crater transforming into a self-sustaining futuristic human colony"
    ),
    ConceptDefinition(
        id_slug="moon-base",
        name="Moon Base",
        category_group="Space & Off-World",
        environments=["lunar highlands crater", "rim of Shackleton crater", "dark lunar mare basin"],
        architectures=["lunar lava tube entrances", "titanium habitat rings", "monumental radio telescope arrays"],
        transformations=["solar panel arrays unfolding like mechanical flowers, landing pads solidifying from lunar dust", "modular habitat modules docking together seamlessly in vacuum"],
        camera_styles=["slow cinematic lunar orbit sweep with Earth rising in the background", "high-angle perspective panning across the lunar crater"],
        lighting_schemes=["harsh contrast black space sky with radiant direct sunlight", "Earthshine softly illuminating lunar structures"],
        materials=["reflective gold insulation foil", "white thermal ceramics", "anodized aluminum frames"],
        reveals=["gleaming technological lunar station with Earth shining majestically in the star-filled black sky", "bustling lunar city active in the crater depths"],
        default_title="Lunar Base Alpha",
        topic_description="Desolate lunar crater transforming into an advanced scientific moon base"
    ),
    ConceptDefinition(
        id_slug="underwater-city",
        name="Underwater City",
        category_group="Aquatic & Ocean",
        environments=["deep ocean seabed", "coral reef trench", "submerged volcanic caldera"],
        architectures=["bioluminescent spherical pods", "acrylic underwater tunnel networks", "deep-sea hydrodynamic towers"],
        transformations=["subsea anchor pylons locking into the seabed, giant transparent domes expanding and illuminating", "tubular glass transit tunnels weaving between vibrant coral gardens"],
        camera_styles=["gentle subaquatic glide through schools of fish toward the city", "ascending panoramic camera rising through the aquatic layers"],
        lighting_schemes=["deep oceanic blue with shimmering sunlight rays penetrating the water", "bioluminescent glowing cyan and emerald ambient illumination"],
        materials=["multi-layered structural acrylic", "marine titanium", "bioluminescent crystal polymers"],
        reveals=["magnificent underwater metropolis glowing peacefully in the depths of the ocean", "futuristic subaquatic civilization surrounded by vibrant marine life"],
        default_title="Subsea Metropolis",
        topic_description="Deep seabed transforming into a mesmerizing glowing underwater city"
    ),
    ConceptDefinition(
        id_slug="floating-city",
        name="Floating City",
        category_group="Aquatic & Ocean",
        environments=["calm open ocean", "deep water archipelago", "sheltered coastal bay"],
        architectures=["hexagonal buoyant platforms", "wave-dampening perimeter barriers", "spiral wind-harvesting towers"],
        transformations=["hexagonal foundation modules interlocking across the water surface, modular gardens and towers rising in sync", "solar canopies unfolding as floating docks link into a vast network"],
        camera_styles=["aerial nautical flyover circling the expanding floating structure", "sea-level gliding shot lifting into wide bird's-eye view"],
        lighting_schemes=["bright sunny maritime daylight with shimmering ocean reflections", "golden twilight with calm reflective waters"],
        materials=["ultra-high-performance buoyant concrete", "solar glass panels", "white marine composites"],
        reveals=["futuristic floating ocean metropolis resting harmoniously on calm seas", "sustainable sea-steading megacity surrounded by endless blue horizon"],
        default_title="Ocean Floating City",
        topic_description="Open sea surface transforming into a high-tech modular floating metropolis"
    ),
    ConceptDefinition(
        id_slug="cyberpunk-metropolis",
        name="Cyberpunk Metropolis",
        category_group="Metropolis & Sci-Fi",
        environments=["dark rain-slicked city grid", "foggy industrial basin", "multi-level concrete underbelly"],
        architectures=["high-density stacked towers", "neon-rimmed skybridges", "massive holographic billboard towers"],
        transformations=["multi-layered road decks building on top of each other, dense neon skyscraper clusters rising into misty night air", "elevated monorail tracks spiraling between towering structures"],
        camera_styles=["dynamic descent between towering skyscrapers down to street level", "continuous cinematic crane pullback through neon fog"],
        lighting_schemes=["rainy night with vibrant magenta, cyan and amber neon reflections", "misty dark atmospheric lighting with volumetric neon beams"],
        materials=["dark wet asphalt", "chrome and matte black steel", "holographic neon glass"],
        reveals=["densely layered cyberpunk city alive with glowing neon lights and skybridge traffic", "awe-inspiring hyper-dense futuristic nighttime metropolis"],
        default_title="Cyberpunk Metropolis",
        topic_description="Dark empty grid transforming into a rain-slicked neon cyberpunk metropolis"
    ),
    ConceptDefinition(
        id_slug="solarpunk-city",
        name="Solarpunk City",
        category_group="Eco & Sustainable",
        environments=["rolling sunlit hills", "gentle river delta", "reclaimed green valley"],
        architectures=["spiral wooden timber towers", "integrated rooftop forests", "stained-glass solar panels"],
        transformations=["curved timber frameworks growing like natural trees, living vines and rooftop gardens blooming automatically", "crystal clean water canals weaving through solar-canopied pedestrian boulevards"],
        camera_styles=["sweeping sunlit drone arc revealing the integration of nature and tech", "gentle upward glide along a spiraling green skyscraper"],
        lighting_schemes=["glorious warm morning sunshine with dappled golden rays", "clean vibrant daylight showcasing rich greens and warm woods"],
        materials=["cross-laminated timber", "decorative stained solar glass", "living vertical foliage"],
        reveals=["utopian green solarpunk city where cutting-edge technology and nature thrive in unison", "breathtaking ecological metropolis overflowing with lush hanging gardens"],
        default_title="Solarpunk Eco City",
        topic_description="Open rolling countryside transforming into a lush, sun-drenched solarpunk eco city"
    ),
    ConceptDefinition(
        id_slug="medieval-castle",
        name="Medieval Castle Construction",
        category_group="Historical & Fantasy",
        environments=["rocky river promontory", "steep forest hill", "misty lakeside crag"],
        architectures=["massive stone curtain walls", "crenellated round towers", "grand central keep with drawbridge"],
        transformations=["stone blocks flying into precise alignment layer by layer, towering battlements and conical roofs assembling in seconds", "deep defensive moat carving into earth and filling with clear water"],
        camera_styles=["dramatic low-angle tilt up the rising stone keep", "slow 360-degree aerial orbit around the castle mount"],
        lighting_schemes=["atmospheric medieval sunrise with morning mist rising from the moat", "golden afternoon light striking weathered stone masonry"],
        materials=["hand-hewn granite blocks", "dark timber roof trusses", "wrought iron portcullises"],
        reveals=["imposing and magnificent medieval stone fortress standing proud atop the hill", "complete fortified medieval stronghold with banners and battlements"],
        default_title="Medieval Stone Castle",
        topic_description="Rugged rocky promontory transforming into a majestic stone medieval castle"
    ),
    ConceptDefinition(
        id_slug="fantasy-castle",
        name="Fantasy Castle",
        category_group="Historical & Fantasy",
        environments=["floating cloud peaks", "crystal waterfall canyon", "magical enchanted forest valley"],
        architectures=["impossible soaring spires", "arched crystalline bridges", "glowing fantasy towers"],
        transformations=["white marble arches weaving through air, glowing blue crystal spires crystallizing upwards", "cascading magical waterfalls forming around floating towers"],
        camera_styles=["cinematic sweeping flight through soaring crystalline arches", "majestic rising vertical panorama"],
        lighting_schemes=["ethereal magical twilight with celestial starlight", "radiant golden hour with shimmering rainbow prisms"],
        materials=["pure white alabaster marble", "glowing azure crystals", "ornate gold leaf filigree"],
        reveals=["enchanted fairy-tale palace radiating magical elegance in the clouds", "spellbinding fantasy kingdom perched high above mist-veiled valleys"],
        default_title="Fantasy Crystal Palace",
        topic_description="Misty mountain canyon transforming into a magical soaring fantasy palace"
    ),
    ConceptDefinition(
        id_slug="japanese-temple",
        name="Japanese Temple Complex",
        category_group="Historical & Fantasy",
        environments=["tranquil bamboo forest grove", "misty koi pond garden", "mossy mountain foothill"],
        architectures=["five-story pagoda", "curved Japanese eaves", "wooden Torii gates and zen gardens"],
        transformations=["raked gravel patterns appearing in waves, intricate interlocking timber joinery assembling without nails", "red lacquered pagoda stories stacking gracefully with curved tiled roofs"],
        camera_styles=["peaceful slow dolly tracking along the stone lantern pathway", "elevated diagonal view framing the pagoda and blooming cherry trees"],
        lighting_schemes=["soft morning mist with gentle golden sunbeams", "warm lantern-lit dusk with cherry blossom petals drifting"],
        materials=["dark cedar wood", "black ceramic roof tiles", "crimson lacquer and white shoji screen accents"],
        reveals=["harmonious and serene traditional Japanese temple garden in full cherry blossom bloom", "timeless zen monastery glowing peacefully among bamboo groves"],
        default_title="Japanese Zen Temple",
        topic_description="Quiet bamboo grove transforming into a traditional Japanese temple garden"
    ),
    ConceptDefinition(
        id_slug="luxury-mansion",
        name="Luxury Mansion Construction",
        category_group="Luxury & Interiors",
        environments=["cliffside private estate grounds", "manicured hillside lawn", "exclusive coastal ridge"],
        architectures=["ultra-modern cantilevered villa", "glass-walled showroom garages", "zero-edge infinity pool"],
        transformations=["foundation concrete curing instantly, floor-to-ceiling glass walls sliding into place, luxury sports cars appearing on illuminated driveway", "terrace stone tiles laying in rapid rhythm as water fills the multi-level pool"],
        camera_styles=["architectural dolly glide across the reflection pool", "slow ascending drone pullback showcasing the entire estate"],
        lighting_schemes=["luxurious dusk blue hour with warm accent pool lighting", "crisp bright daylight emphasizing architectural geometry"],
        materials=["black volcanic stone", "flawless floor-to-ceiling glass", "warm walnut architectural paneling"],
        reveals=["stunning architectural masterwork mansion overlooking endless scenic views", "ultimate dream luxury estate fully furnished and illuminated"],
        default_title="Modern Mega Mansion",
        topic_description="Empty hillside parcel transforming into an ultra-modern luxury mega mansion"
    ),
    ConceptDefinition(
        id_slug="tiny-house",
        name="Tiny House Transformation",
        category_group="Interiors & Micro-Builds",
        environments=["cozy forest clearing", "wildflower meadow", "scenic lake edge"],
        architectures=["scandinavian modern tiny house on wheels", "expandable container home", "a-frame micro cabin"],
        transformations=["trailer chassis leveling, walls unfolding outward, modular smart furniture sliding from walls", "compact loft stairs and fold-down deck extending smoothly"],
        camera_styles=["interior-to-exterior continuous fluid camera motion", "slow 3/4 isometric rotational reveal"],
        lighting_schemes=["warm golden afternoon sunlight streaming through oversized windows", "cozy twilight with warm string fairy lights"],
        materials=["natural cedar siding", "matte black metal standing seam roof", "light birch plywood interiors"],
        reveals=["perfectly optimized designer tiny house tucked peacefully into nature", "cozy modern micro-home fully expanded with welcoming outdoor deck"],
        default_title="Tiny House Build",
        topic_description="Empty meadow transforming into a fully optimized modern tiny cabin"
    ),
    ConceptDefinition(
        id_slug="modern-villa",
        name="Modern Villa",
        category_group="Luxury & Interiors",
        environments=["mediterranean coastal hillside", "desert plateau overlooking mountains", "private pine forest"],
        architectures=["minimalist white cubic architecture", "courtyard with olive tree", "sunken lounge fire pit"],
        transformations=["crisp white architectural volumes interlocking, water cascading into a central courtyard pool", "pergola louvers adjusting automatically as lush Mediterranean landscaping fills the garden"],
        camera_styles=["smooth low-angle architectural tracking along the terrace", "cinematic high-angle crane overview"],
        lighting_schemes=["warm late-afternoon Mediterranean sun", "magic hour dusk with glowing submerged pool lights"],
        materials=["smooth white stucco", "pale limestone pavers", "bronze aluminum window frames"],
        reveals=["flawless minimalist architectural villa basking in warm evening light", "luxurious private sanctuary blending clean lines and serene nature"],
        default_title="Modern Minimalist Villa",
        topic_description="Bare hillside transforming into a minimalist modern Mediterranean villa"
    ),
    ConceptDefinition(
        id_slug="gaming-room",
        name="Gaming Room Transformation",
        category_group="Interiors & Micro-Builds",
        environments=["empty bare concrete room", "dark unfinished attic", "empty basement space"],
        architectures=["ultimate dream battlestation", "acoustic geometric wall panels", "custom motorized desk setup"],
        transformations=["soundproofing panels snapping onto walls, multi-monitor curved displays mounting, RGB strip lighting pulsing to life", "ergonomic cockpit chair and collectible display shelves sliding into place"],
        camera_styles=["dynamic smooth forward push-in toward the glowing triple-monitor desk", "slow 180-degree panoramic sweep of the transformed room"],
        lighting_schemes=["dark ambient room with vibrant addressable RGB lighting (cyan, purple, amber)", "clean recessed LED ceiling track lights"],
        materials=["black acoustic foam tiles", "carbon fiber desk surface", "tempered smoked glass"],
        reveals=["jaw-dropping ultimate cyberpunk gaming sanctuary fully powered and glowing", "immaculate high-end setup with ambient multi-zone backlighting"],
        default_title="Ultimate Gaming Room",
        topic_description="Empty concrete room transforming into a high-end futuristic gaming setup"
    ),
    ConceptDefinition(
        id_slug="empty-room-luxury",
        name="Empty Room → Luxury Interior",
        category_group="Interiors & Micro-Builds",
        environments=["dusty empty loft space", "bare drywall penthouse", "empty concrete apartment"],
        architectures=["high-end contemporary living room", "double-height marble fireplace", "curved bouclé sofa seating"],
        transformations=["herringbone oak flooring laying automatically, floor-to-ceiling drapery dropping, sculptural chandelier assembling in mid-air", "luxury designer furniture, modern art, and indoor ficus trees arranging gracefully"],
        camera_styles=["smooth cinematic steadicam glide from entrance toward the panoramic window", "slow sweeping wide-angle lens rotation"],
        lighting_schemes=["warm afternoon sunlight streaming across the textured rug", "evening ambient lighting with glowing architectural niches"],
        materials=["honed Calacatta gold marble", "natural white oak herringbone", "bouclé and brushed brass"],
        reveals=["impeccably styled high-fashion penthouse interior worthy of an architectural magazine", "warm, luxurious, magazine-ready living room bathed in golden light"],
        default_title="Luxury Living Room Makeover",
        topic_description="Dusty empty room transforming into an ultra-luxurious designer penthouse interior"
    ),
    ConceptDefinition(
        id_slug="abandoned-restoration",
        name="Abandoned Building Restoration",
        category_group="Nature & Landscape",
        environments=["overgrown ruined stone mansion", "derelict brick warehouse", "decaying greenhouse estate"],
        architectures=["revitalized modern-industrial loft", "restored botanical conservatory", "heritage luxury residence"],
        transformations=["cracked walls healing seamlessly, broken glass reforming into pristine panes, weeds retracting into manicured gardens", "decaying brick cleaning and modern black steel beams reinforcing the structure"],
        camera_styles=["dramatic split-time forward dolly directly through the central hallway", "elevated diagonal before-and-after panoramic sweep"],
        lighting_schemes=["gloomy overcast light transforming into warm vibrant golden sunshine", "moody decay lighting shifting to pristine warm interior glow"],
        materials=["weathered heritage brick", "restored wrought iron", "crystal clear conservatory glass"],
        reveals=["spectacular restored architectural jewel standing proud in manicured gardens", "breathtaking rebirth of historic building into modern luxury estate"],
        default_title="Abandoned Estate Restoration",
        topic_description="Decaying overgrown ruin transforming into a restored luxury architectural masterpiece"
    ),
    ConceptDefinition(
        id_slug="stadium-construction",
        name="Stadium Construction",
        category_group="Mega Infrastructure",
        environments=["excavated circular ground basin", "flat urban development park", "coastal sports precinct"],
        architectures=["aerodynamic retractable roof mega-stadium", "tensile cable-supported canopy", "glowing LED facade"],
        transformations=["tiered spectator grandstands rising circularly, pitch grass rolling out in lush stripes, colossal roof trusses closing over the field", "giant video screens illuminating as floodlights power on across the arena"],
        camera_styles=["high-altitude spiral descent into the center circle of the pitch", "wide cinematic aerial orbit around the illuminated exterior"],
        lighting_schemes=["dramatic night-time stadium floodlight power-on with exterior LED light show", "crisp afternoon sun casting geometric roof shadows"],
        materials=["structural steel space frames", "translucent PTFE roof membrane", "hybrid sports turf"],
        reveals=["world-class architectural mega-stadium glowing brilliantly against the night sky", "colossal modern sports arena fully built and illuminated"],
        default_title="Mega Stadium Build",
        topic_description="Excavated circular ground transforming into an iconic futuristic sports mega-stadium"
    ),
    ConceptDefinition(
        id_slug="airport-construction",
        name="Airport Construction",
        category_group="Mega Infrastructure",
        environments=["vast coastal flatlands", "cleared valley basin", "reclaimed offshore bay"],
        architectures=["curved aerodynamic terminal canopy", "sculptural air traffic control tower", "parallel illuminated runways"],
        transformations=["parallel tarmac runways paving and painting automatically, undulating glass terminal roof flowing into shape", "boarding gates extending and runway centerline lights flashing on in sequence"],
        camera_styles=["sweeping runway-level approach shot lifting over the terminal roof", "commanding aerial bird's-eye view tracking the entire airport complex"],
        lighting_schemes=["twilight blue hour with hundreds of glowing runway taxiway lights", "crisp sunrise glinting off the polished terminal glass"],
        materials=["polished white architectural concrete", "high-span curved steel arches", "anti-reflective terminal glass"],
        reveals=["monumental futuristic international airport humming with illuminated runway lights", "state-of-the-art aviation hub sprawling across the landscape"],
        default_title="Futuristic Airport Hub",
        topic_description="Vast flat ground transforming into a sprawling futuristic international airport"
    ),
    ConceptDefinition(
        id_slug="railway-station",
        name="Futuristic Railway Station",
        category_group="Mega Infrastructure",
        environments=["deep urban transit corridor", "riverbank crossing hub", "mountain pass intersection"],
        architectures=["biomorphic vaulted train hall", "suspended monorail concourses", "kinetic canopy wings"],
        transformations=["high-speed magnetic rail tracks laying down, cathedral-like ribbed steel vaults curving overhead", "glass elevator tubes and platform walkways locking into place"],
        camera_styles=["low-angle track-level push-in expanding to wide cathedral hall view", "elevated transversal pan across multiple rail tracks"],
        lighting_schemes=["dramatic morning sunbeams cutting through the vast vaulted glass roof", "sleek modern cool white and amber platform lighting"],
        materials=["ribbed white structural steel", "high-clarity skylight glass", "polished terrazzo concourse floor"],
        reveals=["breathtaking biomorphic transit cathedral glowing with architectural majesty", "futuristic central station uniting multiple high-speed rail lines"],
        default_title="Futuristic Grand Central",
        topic_description="Urban corridor transforming into a biomorphic futuristic high-speed railway cathedral"
    ),
    ConceptDefinition(
        id_slug="mega-bridge",
        name="Mega Bridge Construction",
        category_group="Mega Infrastructure",
        environments=["deep ocean strait", "dramatic foggy sea channel", "wide river gorge"],
        architectures=["multi-tower cable-stayed suspension bridge", "double-deck transit roadway", "sculptural diamond bridge pylons"],
        transformations=["massive caisson foundations sinking into water, colossal diamond towers shooting upward, suspension cables weaving like harp strings", "road deck segments lifting from barges and locking together seamlessly"],
        camera_styles=["dramatic flight alongside the main suspension cables down to the road deck", "high-angle panoramic shot encompassing the entire sea strait"],
        lighting_schemes=["dawn with low-lying sea fog burning off under golden sunlight", "night time with continuous architectural LED cable illumination"],
        materials=["high-strength post-tensioned concrete", "tensile steel stay cables", "dark asphalt deck"],
        reveals=["colossal suspension mega-bridge spanning majestically across the open sea channel", "engineering triumph connecting two shorelines with glowing precision"],
        default_title="Mega Sea Bridge",
        topic_description="Foggy ocean strait transforming into a monumental cable-stayed mega suspension bridge"
    ),
    ConceptDefinition(
        id_slug="dam-construction",
        name="Dam Construction",
        category_group="Mega Infrastructure",
        environments=["deep granite canyon", "rushing mountain river gorge", "steep rocky valley"],
        architectures=["monumental curved arch-gravity dam", "overflow spillway ski-jumps", "hydroelectric turbine powerhouse"],
        transformations=["canyon walls reinforcing, colossal concrete monolithic blocks stepping upward layer by layer, reservoir water rising calmly behind the wall", "spillway gates installing and power lines stretching across canyon crest"],
        camera_styles=["towering top-of-dam crane pullback revealing both sides of the barrier", "ascending canyon flight from turbine base to the reservoir rim"],
        lighting_schemes=["dramatic late-afternoon sun striking the curved dam face", "golden hour creating shimmering reflection across the newly formed lake"],
        materials=["massive monolithic roller-compacted concrete", "steel flood gates", "natural granite bedrock"],
        reveals=["colossal curved concrete dam holding back a vast glistening emerald reservoir", "monumental hydroelectric masterpiece nestled in the canyon"],
        default_title="Hydroelectric Mega Dam",
        topic_description="Rocky river canyon transforming into a colossal curved hydroelectric arch dam"
    ),
    ConceptDefinition(
        id_slug="eco-city",
        name="Eco City",
        category_group="Eco & Sustainable",
        environments=["reclaimed wetlands basin", "coastal delta meadow", "verdant valley floor"],
        architectures=["circular passive energy towers", "vegetated bio-bridges", "algae-powered glass domes"],
        transformations=["clean blue waterways channeling through the land, circular timber-and-glass towers rising among green parks", "solar trees blossoming and pedestrian skyways connecting green rooftops"],
        camera_styles=["smooth sweeping drone orbit over the circular urban core", "diagonal glide along the central eco-corridor"],
        lighting_schemes=["crisp clean daylight with lush green saturation", "soft warm twilight with solar luminescent pathway glow"],
        materials=["mass timber columns", "photovoltaic transparent glass", "living sedum green roofs"],
        reveals=["harmonious sustainable eco-city flourishing with greenery and pristine waterways", "zero-carbon futuristic metropolis in total balance with nature"],
        default_title="Zero-Carbon Eco City",
        topic_description="Wetlands basin transforming into a zero-carbon sustainable circular eco-city"
    ),
    ConceptDefinition(
        id_slug="green-rooftop-city",
        name="Green Rooftop City",
        category_group="Eco & Sustainable",
        environments=["existing dense concrete cityscape", "urban rooftop skyline", "city center blocks"],
        architectures=["interconnected rooftop farms", "canopy sky-gardens", "suspended swimming pools between buildings"],
        transformations=["grey tar rooftops bursting with flower beds and vegetable farms, wooden bridges extending between high-rises", "solar greenhouses and outdoor lounges assembling across all rooftops"],
        camera_styles=["elevated rooftop-level sweeping track flying over building edges", "slow 360-degree aerial panorama over the transformed skyline"],
        lighting_schemes=["golden afternoon sun illuminating lush green rooftop trees", "twilight with warm ambient garden lanterns and fairy lights"],
        materials=["lightweight engineered soil beds", "treated cedar decking", "frameless glass parapets"],
        reveals=["vibrant continuous urban sky-forest blooming across the entire city skyline", "concrete city rooftops transformed into a lush paradise in the clouds"],
        default_title="Green Rooftop Oasis",
        topic_description="Grey concrete rooftop skyline transforming into an interconnected paradise of sky gardens"
    ),
    ConceptDefinition(
        id_slug="space-station",
        name="Space Station Construction",
        category_group="Space & Off-World",
        environments=["Earth orbit space vacuum", "deep starry cosmos", "lunar orbit background"],
        architectures=["rotating artificial gravity ring", "central docking hub", "massive solar radiator wings"],
        transformations=["truss segments connecting in microgravity, giant ring modules expanding and locking into a circle, solar wings extending smoothly", "docking ports illuminating as attitude thrusters stabilize the orbital station"],
        camera_styles=["majestic slow orbital flyby with blue Earth rotating below", "dynamic 3D camera rotation around the spinning torus ring"],
        lighting_schemes=["radiant direct sunlight highlighting metallic surfaces against pure black space", "soft blue Earthshine reflecting on white module hulls"],
        materials=["multi-layer insulation (MLI) gold foil", "anodized white aluminum hull", "solar panel silicon wafers"],
        reveals=["monumental rotating space station turning gracefully in Earth orbit", "gleaming orbital habitat complete with illuminated observation cupolas"],
        default_title="Orbital Space Station",
        topic_description="Empty orbit transforming into a colossal rotating artificial-gravity space station"
    ),
    ConceptDefinition(
        id_slug="giant-factory",
        name="Giant Factory Construction",
        category_group="Mega Infrastructure",
        environments=["vast graded industrial plain", "desert manufacturing zone", "river port logistics parcel"],
        architectures=["gigantic gigafactory building", "robotic gantry cranes", "automated logistics solar roof"],
        transformations=["steel columns planting into grid foundations, vast solar roof rolling out across hundreds of meters, automated conveyor arteries weaving inside", "high-bay storage racks shooting up and autonomous vehicle lanes marking"],
        camera_styles=["accelerated high-altitude aerial zoom-out showing sheer scale", "smooth low-level tracking along the monumental industrial facade"],
        lighting_schemes=["clean industrial daylight highlighting massive geometric clean lines", "sunset casting long metallic reflections across the solar roof"],
        materials=["standing seam white insulated panels", "monolithic solar glass arrays", "precision structural steel"],
        reveals=["mind-bogglingly vast automated gigafactory complex gleaming under the sun", "monumental high-tech manufacturing plant spanning as far as the eye can see"],
        default_title="Automated Gigafactory",
        topic_description="Empty graded ground transforming into an enormous automated solar gigafactory"
    ),
    ConceptDefinition(
        id_slug="harbor-transformation",
        name="Harbor Transformation",
        category_group="Aquatic & Ocean",
        environments=["old rusty shipping docks", "industrial tidal basin", "estuary port zone"],
        architectures=["waterfront cultural center", "promenade wooden boardwalks", "sculptural pedestrian footbridge"],
        transformations=["rusty shipping containers clearing, granite seawalls reconstructing, modern glass pavilions and yacht berths emerging", "lush waterfront parks, fountains and public terraces filling the shoreline"],
        camera_styles=["smooth nautical dolly shot tracking along the new waterfront", "ascending panoramic drone pullout over the transformed harbor"],
        lighting_schemes=["glorious sunset reflecting off calm harbor waters and glass facades", "twilight with illuminated fountain jets and promenade bollard lights"],
        materials=["natural granite promenade stones", "curved marine teak", "structural architectural glass"],
        reveals=["glamorous world-class waterfront promenade humming with beauty and calm water", "historic industrial harbor reborn as a pristine luxury maritime district"],
        default_title="Waterfront Harbor Rebirth",
        topic_description="Decaying industrial shipyard transforming into a world-class luxury waterfront harbor"
    ),
    ConceptDefinition(
        id_slug="marina-construction",
        name="Marina Construction",
        category_group="Aquatic & Ocean",
        environments=["sheltered coastal cove", "mediterranean bay", "barrier reef lagoon"],
        architectures=["custom teak floating finger piers", "sculptural yacht club clubhouse", "fuel and power utility pedestals"],
        transformations=["breakwater stone mounds placing into the sea, floating dock fingers extending rhythmically, luxury superyachts mooring into place", "clubhouse sail-shaped tensile roof unfurling over the marina basin"],
        camera_styles=["aerial spiral descending directly toward the marina center", "waterline glide between lines of moored luxury yachts"],
        lighting_schemes=["golden Mediterranean afternoon with turquoise water reflections", "blue hour with glowing underwater dock lighting"],
        materials=["treated teak deck boards", "extruded marine aluminum docks", "translucent tensile fabric"],
        reveals=["flawless high-end superyacht marina sparkling in azure coastal waters", "luxury nautical haven fully completed with sail-canopied clubhouse"],
        default_title="Luxury Superyacht Marina",
        topic_description="Empty coastal cove transforming into an exclusive luxury superyacht marina"
    ),
    ConceptDefinition(
        id_slug="island-airport",
        name="Island Airport",
        category_group="Mega Infrastructure",
        environments=["shallow turquoise reef lagoon", "open sea atoll", "coastal sandbar"],
        architectures=["man-made artificial runway island", "compact glass terminal dome", "overwater approach lighting piers"],
        transformations=["seawall perimeter locking together, sand reclamation filling the interior island, precision runway tarmac smoothing over the fill", "curved dome terminal rising and ocean approach lighting piers extending into the sea"],
        camera_styles=["cockpit-style aerial approach flight descending toward the runway island", "high-altitude bird's-eye view showcasing the emerald waters around the runway"],
        lighting_schemes=["dramatic tropical sunset with illuminated runway centerline lights", "bright tropical midday sun highlighting vivid turquoise waters"],
        materials=["marine armour rock", "grooved high-friction runway asphalt", "corrosion-resistant architectural glass"],
        reveals=["breathtaking engineering marvel runway island floating amidst crystal-clear turquoise waters", "pristine modern ocean airport welcoming arriving flights"],
        default_title="Ocean Runway Island",
        topic_description="Shallow ocean reef transforming into a breathtaking offshore island airport"
    ),
    ConceptDefinition(
        id_slug="ski-resort",
        name="Ski Resort",
        category_group="Nature & Landscape",
        environments=["untouched snow-covered mountain peak", "alpine forest basin", "glacier bowl"],
        architectures=["summit panoramic glass restaurant", "heated chairlift stations", "luxurious ski-in ski-out lodges"],
        transformations=["groomed ski pistes carving through pine trees, cable car steel towers stepping up the ridgeline, timber-and-glass lodges rising from snow", "night ski floodlights igniting in sequence down the mountain trails"],
        camera_styles=["fast-gliding drone flight carving down the ski slope", "panoramic summit orbit framing the resort and surrounding snow peaks"],
        lighting_schemes=["crisp cold blue mountain morning with radiant sun reflections on powder snow", "alpenglow pink sunset with glowing chalet windows"],
        materials=["heavy Douglas fir timbers", "heated triple-glazed glass", "natural slate stone"],
        reveals=["world-class luxury alpine ski resort nestled in pristine mountain snow", "vibrant winter wonderland village glowing warmly amidst snow-capped peaks"],
        default_title="Luxury Alpine Ski Resort",
        topic_description="Wild snowy mountain slopes transforming into a world-class luxury ski resort"
    ),
    ConceptDefinition(
        id_slug="jungle-resort",
        name="Jungle Eco Resort",
        category_group="Luxury & Resorts",
        environments=["dense tropical rainforest canopy", "misty jungle river valley", "ancient tree grove"],
        architectures=["elevated treetop canopy pods", "suspended rope bridges", "natural spring stone pools"],
        transformations=["spiral wooden staircases wrapping around ancient jungle trunks, teardrop glass pods hanging among branches", "stone walkways and natural plunge pools carving through lush ferns"],
        camera_styles=["cinematic descent through the misty rainforest canopy down to the river", "slow horizontal tracking shot across a suspended rope bridge"],
        lighting_schemes=["sunbeams piercing through dense jungle foliage and morning mist", "magical evening lantern illumination throughout the forest canopy"],
        materials=["sustainable reclaimed teak", "curved structural bamboo", "natural river rock"],
        reveals=["fairytale luxury eco-sanctuary suspended harmoniously in the virgin jungle canopy", "magical treehouse resort glowing warmly in the rainforest mist"],
        default_title="Jungle Canopy Retreat",
        topic_description="Untouched rainforest canopy transforming into an exclusive suspended eco treehouse resort"
    ),
    ConceptDefinition(
        id_slug="desert-oasis",
        name="Desert Oasis",
        category_group="Nature & Landscape",
        environments=["stark arid sand dune hollow", "desolate desert depression", "windblown sandstone basin"],
        architectures=["traditional mud-brick palatial arches", "shaded palm-lined irrigation channels", "central turquoise natural spring"],
        transformations=["crystal spring water bubbling from the sand and forming a serene pool, date palms sprouting in concentric rings, earthen palaces rising around the water", "ornate arched shaded walkways and flowering gardens blooming across the sands"],
        camera_styles=["elevated circular tracking shot centered around the vibrant blue spring", "low-angle pan through date palm fronds toward the desert architecture"],
        lighting_schemes=["intense golden hour light with long shadows across dune crests", "clear desert twilight with brilliant starry sky above"],
        materials=["compressed stabilized earth blocks", "carved cedar wood screens", "smooth polished plaster"],
        reveals=["breathtaking lush green oasis sanctuary shimmering like a mirage in the golden desert", "peaceful desert haven flourishing with cool water, palms and earthen architecture"],
        default_title="Desert Oasis Palace",
        topic_description="Barren sand dune basin transforming into a lush, water-rich desert oasis haven"
    ),
    ConceptDefinition(
        id_slug="ice-city",
        name="Ice City",
        category_group="Historical & Fantasy",
        environments=["frozen glacial plateau", "arctic tundra ice sheet", "blue ice canyon"],
        architectures=["translucent carved ice palaces", "illuminated ice spires", "crystalline archways and bridges"],
        transformations=["geometric ice blocks self-carving and stacking, soaring crystalline spires freezing upward, embedded fiber-optic lights pulsing with color inside the ice", "smooth ice walkways and frosted battlements locking together"],
        camera_styles=["gliding shot through a grand translucent ice colonnade", "elevated panoramic orbit around the glowing ice fortress"],
        lighting_schemes=["arctic blue daylight with internal glowing neon LED refraction", "dramatic green and purple Aurora Borealis dancing in the night sky above"],
        materials=["ultra-clear glacial ice blocks", "frosted compacted snow", "embedded multi-color LED filaments"],
        reveals=["spellbinding ice palace metropolis glowing brilliantly under the dancing Northern Lights", "magical frozen kingdom radiating internal vibrant colors"],
        default_title="Glacial Ice Kingdom",
        topic_description="Frozen arctic ice sheet transforming into a glowing illuminated ice palace metropolis"
    ),
    ConceptDefinition(
        id_slug="crystal-city",
        name="Crystal City",
        category_group="Historical & Fantasy",
        environments=["deep geode cavern", "subterranean quartz canyon", "prismatic mineral valley"],
        architectures=["giant geometric quartz spires", "floating crystal skybridges", "prismatic light towers"],
        transformations=["massive amethyst and quartz clusters growing rapidly from rock surfaces, crystalline structures linking into habitable towers", "refracted light rays solidifying into glowing energy bridges"],
        camera_styles=["sweeping fluid camera moving through towering crystal formations", "vertiginous upward crane reveal inside the geode cavern"],
        lighting_schemes=["prismatic rainbow light refractions splitting through crystal facets", "deep purple and amber ambient mineral glow"],
        materials=["natural optical quartz crystal", "deep purple amethyst matrix", "luminous prism glass"],
        reveals=["breathtaking subterranean civilization built entirely of glowing living crystals", "dazzling prismatic crystal city shimmering with radiant beauty"],
        default_title="Subterranean Crystal City",
        topic_description="Dark mineral geode cave transforming into a luminous crystalline wonderland city"
    ),
    ConceptDefinition(
        id_slug="floating-islands",
        name="Floating Island Civilization",
        category_group="Historical & Fantasy",
        environments=["endless sea of golden clouds", "sky canyon realm", "high-altitude mountain air"],
        architectures=["gravity-defying aerial temples", "suspended chain skybridges", "windmill aerostations"],
        transformations=["massive mossy land masses levitating gently from the cloud layer, white stone temples and cascading waterfalls forming on the floating rocks", "airship docking pylons and stone bridges connecting the floating islands"],
        camera_styles=["majestic cloud-surfing flight between hovering land masses", "slow upward crane shot following a cascading sky waterfall"],
        lighting_schemes=["heavenly golden hour sunlight breaking through layered storm clouds", "ethereal sunset casting purple and gold light across the floating rocks"],
        materials=["ancient weathered limestone", "verdant hanging moss and vines", "polished brass mechanisms"],
        reveals=["awe-inspiring civilization of floating islands suspended in a golden sky", "magnificent mythical aerial kingdom drifting above endless cloud oceans"],
        default_title="Floating Sky Islands",
        topic_description="Open sky above clouds transforming into a mythical archipelago of floating islands"
    ),
    ConceptDefinition(
        id_slug="miniature-world",
        name="Miniature World Construction",
        category_group="Interiors & Micro-Builds",
        environments=["wooden tabletop workbench", "vintage craftsman desk", "macro photography surface"],
        architectures=["intricately detailed miniature diorama", "micro-scale railway and village", "tiny rivers and mountains"],
        transformations=["miniature terrain foam sculpting instantly, tiny trees planting, tiny train tracks laying and a micro-scale locomotive steaming to life", "microscopic streetlights turning on and tiny cozy house windows lighting up"],
        camera_styles=["macro lens tilt-shift tracking shot with shallow depth of field", "slow rotational sweep around the miniature diorama"],
        lighting_schemes=["warm focused desk lamp lighting with soft cozy room shadows", "studio macro lighting highlighting ultra-fine textures"],
        materials=["sculpted model terrain", "balsa wood and brass wire", "micro LED filaments"],
        reveals=["exquisite, living, breathing miniature world masterpiece in stunning macro detail", "mesmerizing tilt-shift diorama bustling with tiny glowing details"],
        default_title="Miniature Diorama World",
        topic_description="Empty wooden workbench transforming into an exquisitely detailed living miniature diorama"
    ),
]


def find_concept_by_topic_key(topic_key: str) -> "ConceptDefinition | None":
    """
    Resolves the ConceptDefinition that produced a given topic_key
    (format: '{id_slug}-{env_last_word}-{arch_last_word}', see PromptEngine.build_concept_plan).
    Used to deterministically reconstruct real metadata for a Reel on resume, when the
    original ReelConceptPlan object is no longer in memory. Matches the longest id_slug
    that is a prefix of topic_key, since id_slug itself may contain hyphens.
    """
    if not topic_key:
        return None
    candidates = [c for c in CATEGORIES if topic_key.startswith(c.id_slug + "-") or topic_key == c.id_slug]
    if not candidates:
        return None
    return max(candidates, key=lambda c: len(c.id_slug))
