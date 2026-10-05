"""
Spoken narration for each concept, one line per beat, mixed over the finished Reel by
automation/audio/voiceover.py.

Flow still renders every segment without speech -- its prompts ban narration outright --
because a voice it invents changes from segment to segment. The narration is added
afterwards in one fixed voice per brand, so every Reel on a channel sounds like the same
narrator.

Keys are concept slugs; values carry exactly "before", "turn" and "after", the same beats
the segments are built on. Each line has to finish inside its own ten-second segment, so
lines stay short (see MAX_WORDS_PER_LINE). A concept with no entry here is published as
before, with its ambient sound only.

    BuildVerse     -- third person, plain documentary voice. Every fact comes from the
                      concept's own real_basis; nothing is added that it does not support.
    Crafts By Man  -- first person: the craftsman tells what he is doing.
"""
from typing import Dict

BEATS = ("before", "turn", "after")

# About 2.3 words a second at the narration rate leaves room for the pause at the start of
# each segment.
MAX_WORDS_PER_LINE = 17


def _n(before: str, turn: str, after: str) -> Dict[str, str]:
    return {"before": before, "turn": turn, "after": after}


NARRATION_LINES: Dict[str, Dict[str, str]] = {
    # ------------------------------------------------------------ BuildVerse: story
    "pompeii": _n(
        "In AD 79, Pompeii was a busy Roman town at the foot of Mount Vesuvius.",
        "Then the mountain erupted, burying every street under ash and pumice.",
        "Dug out since 1748, its streets stand exactly where the ash stopped them.",
    ),
    "herculaneum": _n(
        "Herculaneum was a wealthy Roman town on the shore of the Bay of Naples.",
        "In AD 79, scorching flows from Vesuvius buried it far deeper than Pompeii.",
        "The heat turned its wooden beams to charcoal, and preserved them.",
    ),
    "kolmanskop": _n(
        "In 1908, diamonds turned Kolmanskop into a wealthy town in the Namib Desert.",
        "When richer deposits were found further south, the people simply left.",
        "By the 1950s it was empty, and the sand moved into every room.",
    ),
    "plymouth-montserrat": _n(
        "Plymouth was the capital of Montserrat, a small island in the Caribbean.",
        "From 1995, the Soufriere Hills volcano buried the town under ash and flows.",
        "It was evacuated for good. The capital is still under the ash today.",
    ),
    "skara-brae": _n(
        "Over five thousand years ago, farmers built a stone village on Orkney.",
        "Then the sand dunes covered it, and Skara Brae vanished for millennia.",
        "In 1850, a great storm stripped the sand away and revealed the houses.",
    ),
    "gobekli-tepe": _n(
        "Around 9500 BC, people at Gobekli Tepe raised giant carved stone pillars.",
        "Later, the enclosures were deliberately buried under rubble.",
        "Older than pottery, metal and the wheel, it is still being uncovered.",
    ),
    "angkor-wat": _n(
        "Angkor was the capital of the Khmer Empire, one of the largest cities on earth.",
        "After the fifteenth century, the court moved away and the forest moved in.",
        "Today, fig roots grip the temple walls, holding them and tearing them apart.",
    ),
    "tikal": _n(
        "Tikal was one of the greatest Maya cities in the rainforest of Guatemala.",
        "By the end of the tenth century, its people had left.",
        "The jungle covered everything, but its temples still rise above the trees.",
    ),
    "ciudad-perdida": _n(
        "Around AD 800, the Tayrona built a stone city high in Colombia's mountains.",
        "In the era of the Spanish conquest it was abandoned, and the cloud forest took it.",
        "It stayed lost until 1972. Its stone terraces still climb the ridge.",
    ),
    "ross-island": _n(
        "From 1858, Ross Island was the British headquarters in the Andaman Islands.",
        "An earthquake damaged it in 1941, and soon after it was abandoned.",
        "Now banyan roots wrap the walls of its church and its ballroom.",
    ),
    "pripyat": _n(
        "Pripyat was built in 1970 for the workers of the Chernobyl power plant.",
        "On 27 April 1986, its 49,000 residents were evacuated by bus.",
        "Nobody came back. The forest has been taking the city ever since.",
    ),
    "hashima": _n(
        "Hashima, off Nagasaki, was once one of the most crowded places on earth.",
        "When its coal mine closed in 1974, everyone left within weeks.",
        "Its concrete blocks still stand on the island, empty, facing the sea.",
    ),
    "bodie": _n(
        "Around 1880, Bodie was a booming California gold town of thousands.",
        "Then the mines failed, and over decades the people drained away.",
        "What they left still stands, as if the last residents just walked out.",
    ),
    "centralia": _n(
        "Centralia was an ordinary mining town in Pennsylvania.",
        "In 1962, a coal seam caught fire beneath it. It is still burning.",
        "The town was cleared above ground. Only its empty streets remain.",
    ),
    "craco": _n(
        "Craco has stood on its hilltop in southern Italy since the eighth century.",
        "Landslides kept striking, and after a major one in 1963 the people left.",
        "Today the whole town stands empty on its ridge.",
    ),
    "fordlandia": _n(
        "In 1928, Henry Ford began building an American town in the Amazon.",
        "It was meant to grow rubber. By 1945 it had been abandoned.",
        "The jungle has been reclaiming its houses and water tower ever since.",
    ),
    "petra": _n(
        "Petra was a rich caravan capital, carved into the sandstone cliffs of Jordan.",
        "Earthquakes shook the city, and in time its people left it to the desert.",
        "Its rock-cut facades still glow red in the canyon.",
    ),
    "derinkuyu": _n(
        "Beneath Cappadocia, people carved a city deep into soft volcanic rock.",
        "It could shelter thousands, level after level, with shafts bringing in air.",
        "Sealed up and forgotten, it was only rediscovered in 1963.",
    ),
    "mesa-verde": _n(
        "In the 1190s, Ancestral Puebloans built their homes into the cliffs of Colorado.",
        "In less than a century, the people had moved away.",
        "Their cliff dwellings are still sitting in the canyon walls.",
    ),
    "ani": _n(
        "Around AD 1000, Ani was an Armenian capital said to hold 100,000 people.",
        "It was sacked in 1064, then devastated by an earthquake, and slowly emptied.",
        "Today only its churches stand, alone on the open steppe.",
    ),
    "lalibela": _n(
        "In medieval Ethiopia, builders started at the top of the rock.",
        "Instead of building up, they carved down, cutting churches out of solid stone.",
        "Eleven of these churches still stand at Lalibela.",
    ),
    "aral-sea": _n(
        "The Aral Sea was once the fourth-largest lake in the world.",
        "Soviet irrigation diverted its rivers, and the water began to retreat.",
        "Fishing boats now sit rusting on dry seabed, far from any water.",
    ),
    "salton-sea": _n(
        "In 1905, river water broke through a canal and created the Salton Sea.",
        "In the 1950s it was a popular resort. Then the water turned to salt.",
        "Its shoreline towns now sit half empty beside the shrinking lake.",
    ),
    "nan-madol": _n(
        "In Micronesia, people built Nan Madol on nearly a hundred artificial islets.",
        "They stacked basalt columns like logs into walls above the tide.",
        "Abandoned around 1800, the stone city still stands in the tidal water.",
    ),
    "machu-picchu": _n(
        "In the fifteenth century, the Inca built a royal estate on a Peruvian ridge.",
        "About a century later, around the Spanish conquest, it was abandoned.",
        "Hidden by cloud forest, Machu Picchu still stands on its ridge.",
    ),
    "rapa-nui": _n(
        "On Rapa Nui, Polynesian islanders carved nearly 900 giant moai statues.",
        "They cut them straight out of the quarry rock.",
        "Hundreds were left unfinished, exactly where the carving stopped.",
    ),
    "surtsey": _n(
        "In November 1963, the sea off southern Iceland started to boil.",
        "An eruption on the seafloor built a brand new island, until 1967.",
        "Surtsey has been protected ever since, as life arrives on its own.",
    ),
    "kuldhara": _n(
        "Around the thirteenth century, Paliwal Brahmins settled Kuldhara in Rajasthan.",
        "By the early nineteenth century, every family had gone.",
        "Its sandstone streets are still standing, empty, in the desert.",
    ),
    "hampi": _n(
        "Around 1500, Vijayanagara at Hampi was one of the largest cities in the world.",
        "After 1565, the city was plundered and abandoned.",
        "Its temples and bazaars still stand among the boulders of Karnataka.",
    ),
    "fatehpur-sikri": _n(
        "From 1571, the emperor Akbar built a new capital in red sandstone.",
        "Within about fifteen years, Fatehpur Sikri was largely abandoned.",
        "Its palaces and courtyards near Agra still stand almost untouched.",
    ),
    "dhanushkodi": _n(
        "Dhanushkodi was a railway town and ferry port at the tip of India.",
        "In 1964, a cyclone struck in the night and destroyed it.",
        "It was never rebuilt. Its ruined church still stands on the sand.",
    ),
    "ajanta-caves": _n(
        "From the second century BC, monks carved prayer halls into a gorge in Maharashtra.",
        "Over the centuries, the caves were left, and the forest hid them.",
        "Found again in 1819, their painted walls are still there inside the rock.",
    ),
    "dholavira": _n(
        "Around 3000 BCE, an Indus Valley city rose in the salt desert of Gujarat.",
        "It was later abandoned and buried under mounds of earth.",
        "Excavated from 1990, Dholavira is back in the light.",
    ),
    # ------------------------------------------------------------ BuildVerse: cutaway
    "canal-lock-chamber": _n(
        "It looks like a still stretch of canal, with a gate across it.",
        "But hidden culverts in the walls can fill the whole chamber with water.",
        "That is how a lock lifts a boat from one level to the next.",
    ),
    "church-floor-crypt": _n(
        "It looks like a plain, worn stone floor.",
        "But many old churches stand on a vaulted crypt.",
        "Those vaults carry the whole floor, and are often older than the church.",
    ),
    "stadium-pitch-services": _n(
        "It looks like an ordinary green football pitch.",
        "Underneath are layers of sand and gravel, drains and heating pipes.",
        "That is why a modern pitch drains fast and stays playable in frost.",
    ),
    "motorway-embankment-culvert": _n(
        "It looks like a plain grass bank under a motorway.",
        "But many embankments hide a culvert, carrying a stream straight through.",
        "Some even have dry ledges, so animals can cross under the road.",
    ),
    "city-street-cistern": _n(
        "It looks like a plain paved street, with nothing to see.",
        "But under some city streets, huge covered cisterns still hold water.",
        "Istanbul's Basilica Cistern alone stands on 336 columns.",
    ),
    "dam-wall-galleries": _n(
        "It looks like a featureless wall of concrete.",
        "But inside a large dam, galleries and stairs run through the whole structure.",
        "Engineers use them to watch for seepage and move through the dam.",
    ),
    "quiet-field-underground-city": _n(
        "It looks like an empty ploughed field.",
        "But in Cappadocia, whole cities were carved into the rock beneath the fields.",
        "Derinkuyu goes down about sixty metres, and its air shafts still work.",
    ),
    "salt-mine-chamber": _n(
        "It looks like an ordinary wooded hill.",
        "But in Poland's Wieliczka mine, miners carved whole halls out of rock salt.",
        "Even the chandeliers and the reliefs on the walls are made of salt.",
    ),
    "roman-bath-hypocaust": _n(
        "It looks like an ordinary tiled floor.",
        "But in a Roman bath, the floor sat on rows of short brick pillars.",
        "Hot air from a furnace flowed between them, heating the room from below.",
    ),
    "lighthouse-spiral": _n(
        "It looks like a plain white tower.",
        "Inside, a spiral stair climbs past rooms stacked one above another.",
        "At the top, a great Fresnel lens turns, throwing light out to sea.",
    ),
    "grain-silo-interior": _n(
        "They look like blank concrete towers beside a railway.",
        "Inside, each tower is a tall cell, filled with grain from a conveyor on top.",
        "Another conveyor at the base draws the grain out again.",
    ),
    "amphitheatre-hypogeum": _n(
        "It looks like a plain sand floor.",
        "But under the Colosseum's arena ran two levels of corridors and lift shafts.",
        "Lifts in those shafts raised animals and scenery straight up into the arena.",
    ),
    "victorian-sewer-cathedral": _n(
        "It looks like a plain grass embankment.",
        "But beneath London run Victorian sewers, built by Joseph Bazalgette from 1859.",
        "Their huge brick vaults are still carrying the city's water today.",
    ),
    "glacier-moulin": _n(
        "It looks like a flat white field of ice.",
        "But meltwater drills shafts, called moulins, straight down through the glacier.",
        "Some reach the bed of the glacier, hundreds of metres below.",
    ),
    "bridge-pier-hollow": _n(
        "It looks like a solid concrete bridge pier.",
        "But many large piers are hollow, with ladders running up inside.",
        "Platforms inside let engineers inspect the structure from within.",
    ),
    "rock-overhang-town": _n(
        "It looks like a normal whitewashed street in Spain.",
        "But in Setenil de las Bodegas, the houses are built under a rock overhang.",
        "The rock itself is their roof, and the rooms run back into the cliff.",
    ),
    # ------------------------------------------------------------ BuildVerse: 2026-10-06
    "kaymakli": _n(
        "Beneath the village of Kaymakli, in Cappadocia, people carved a city into the rock.",
        "Stables, storerooms and wine presses ran down level after level, a refuge for centuries.",
        "Opened to visitors in 1964, four of its levels can still be entered.",
    ),
    "anak-krakatau": _n(
        "In 1883, Krakatoa erupted, and most of the island was destroyed.",
        "In 1927, a new island began rising out of the drowned crater.",
        "They named it Anak Krakatau, the child of Krakatoa.",
    ),
    "coober-pedy": _n(
        "In 1915, opal was found in the middle of the Australian outback.",
        "Summer there often passes forty degrees, so people dug their homes into the hills.",
        "In Coober Pedy, homes, shops and even churches are underground.",
    ),
    "matera": _n(
        "In southern Italy, people lived in caves cut into the ravine at Matera for millennia.",
        "In the 1950s, the government moved everyone out over the living conditions.",
        "Restored since, the Sassi became a World Heritage Site in 1993.",
    ),
    "kailasa-ellora": _n(
        "In eighth century India, carvers at Ellora chose a single basalt cliff.",
        "They did not build. They cut downward from the top, removing the rock around it.",
        "The Kailasa temple is one piece of stone, carved out of the mountain.",
    ),
    "akrotiri": _n(
        "On the Greek island of Santorini, Akrotiri was a busy Bronze Age harbour town.",
        "The great eruption of Thera buried it under volcanic ash.",
        "Dug out from 1967, its houses still stand two and three storeys high.",
    ),
    "villa-epecuen": _n(
        "Villa Epecuen was a spa town on a salt lake in Argentina.",
        "On 10 November 1985, an embankment gave way and the lake poured in.",
        "Decades later the water pulled back, and the town came out bleached white.",
    ),
    "champagne-chalk-cellars": _n(
        "It looks like an ordinary vineyard hillside in Champagne.",
        "But under it are chalk pits first dug in Roman times.",
        "Today kilometres of those tunnels are cellars, full of ageing bottles.",
    ),
    "gotthard-base-tunnel": _n(
        "It looks like a quiet valley in the Swiss Alps.",
        "But straight through the mountains runs the Gotthard Base Tunnel.",
        "At 57 kilometres, it is the longest railway tunnel in the world.",
    ),
    "tokyo-flood-tank": _n(
        "It looks like an ordinary football field outside Tokyo.",
        "But underneath is a flood tank 177 metres long and 25 metres high.",
        "Fifty-nine giant pillars hold it up, waiting for the next flood.",
    ),
    "electric-mountain": _n(
        "It looks like a bare mountain in Snowdonia, in Wales.",
        "But hidden inside it is the Dinorwig power station, built over ten years.",
        "Water falls through the mountain, and it reaches full power in about sixteen seconds.",
    ),
    "edinburgh-buried-close": _n(
        "It looks like a busy street on Edinburgh's Royal Mile.",
        "But in the 1750s, a building was raised right over an old lane.",
        "Mary King's Close is still down there, its seventeenth century houses intact.",
    ),
    "seattle-underground": _n(
        "It looks like an ordinary sidewalk in downtown Seattle.",
        "After the great fire of 1889, the city raised its streets by up to two storeys.",
        "The old shopfronts and sidewalks are still down there, under your feet.",
    ),
    "svalbard-seed-vault": _n(
        "It looks like a snowy mountainside in the Arctic.",
        "But deep inside, in the permafrost, is the Svalbard Global Seed Vault.",
        "It holds backup copies of more than a million seed samples from around the world.",
    ),
    # ------------------------------------------------------------ Crafts By Man
    # Only the concepts added on 2026-10-01; the older ones stay ambient-only for now.
    "excavator-glassworks": _n(
        "This old excavator was headed for scrap. I had a better idea.",
        "So I buried it, right here in the quarry yard.",
        "Now it holds my glass furnace. Look at it glow.",
    ),
    "lighthouse-clockmaker": _n(
        "I found the top of an old lighthouse, and I knew what to do with it.",
        "Down it goes into the cliff, until only the dome shows.",
        "Underneath is my clock workshop. Listen to them all ticking.",
    ),
    "minecage-candles": _n(
        "This old cage used to carry miners down the shaft.",
        "So I sent it back down, one last time.",
        "Now it is my candle workshop, lit by hundreds of small flames.",
    ),
    "radardome-planetarium": _n(
        "This radar dome used to watch the weather. I wanted it to watch the stars.",
        "So I buried it on the hilltop, until only the top showed.",
        "Now we lie back underneath it, and the stars come out.",
    ),
    "armouredvan-jeweller": _n(
        "An armoured van, built to keep valuables safe. I kept it that way.",
        "I buried it under the yard and paved right over it.",
        "Inside is my jewellery workshop. Everything in here shines.",
    ),
    "snowcat-chocolatier": _n(
        "This snowcat spent its whole life up on the mountain.",
        "So I buried it in the snow, right beside the chalet.",
        "Inside, it is warm. That is my chocolate kitchen.",
    ),
    "taxi-luthier": _n(
        "This old taxi had carried its last passenger.",
        "I lowered it under the courtyard and laid the cobbles back.",
        "Now it is where I make violins. Listen.",
    ),
    "garbagetruck-perfumery": _n(
        "Everyone thinks a garbage truck smells bad.",
        "I buried this one behind the rose garden.",
        "Now it is my perfume lab, and it smells of roses.",
    ),
    "milkfloat-butterflies": _n(
        "Nobody wanted this old milk float anymore. I did.",
        "I buried it in my back garden, roof and all.",
        "Now step inside. It is full of butterflies.",
    ),
    "foodtruck-fern-grotto": _n(
        "This old food truck had served its last meal.",
        "So I buried it under the gravel lot.",
        "Inside, I grew a fern grotto, with a waterfall pouring out of the hatch.",
    ),
    "divingbell-distillery": _n(
        "This brass diving bell spent years under the sea.",
        "I buried it in the harbour yard, crown and all.",
        "Inside, my copper still is bubbling away.",
    ),
    "lightship-bellfoundry": _n(
        "This lightship used to warn ships away from danger.",
        "I buried it in the marsh, with only the mast showing.",
        "Inside is my bell foundry. Listen to it ring.",
    ),
    "hovercraft-pizzeria": _n(
        "This rescue hovercraft has done its last rescue.",
        "So I buried it in the sand, above the tide line.",
        "Inside, the oak fire is burning, and the pizza is ready.",
    ),
    "narrowboat-roastery": _n(
        "This narrowboat spent its whole life on the canal.",
        "I buried it in the bank, right beside the lock.",
        "Now I roast coffee inside it. You can smell it from the towpath.",
    ),
}


def narration_for(id_slug: str) -> Dict[str, str]:
    """The three lines for a concept, or an empty dict when it has none."""
    return NARRATION_LINES.get(id_slug, {})
