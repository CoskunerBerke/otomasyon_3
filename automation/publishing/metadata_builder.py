"""
Deterministic and concept-driven metadata generator for YouTube Shorts and TikTok Studio.
Generates unique English titles, descriptions, captions, and curated hashtags tailored to each concept.

Two families of builder live here. build_youtube_metadata/build_tiktok_metadata serve the
silent construction Reels ("Building X From Scratch"). build_story_* serve
narrative_ambient_story Reels, where that phrasing would be simply false -- nobody built
Pompeii in 30 seconds -- and where the copy must stay inside the concept's documented
real_basis rather than dramatising beyond it.
"""
import hashlib
from typing import Dict, Any, Tuple, List

class PublishingMetadataBuilder:
    """Builds concept-tailored metadata for YouTube Shorts and TikTok Studio."""

    CATEGORY_HASHTAG_MAP = {
        "Metropolis & Sci-Fi": ["#Cyberpunk", "#FuturisticCity", "#SciFiArchitecture", "#MegaCity", "#FutureDesign"],
        "Luxury & Modern Estates": ["#LuxuryVilla", "#Mansion", "#ModernArchitecture", "#DreamHome", "#ArchitecturalDesign"],
        "Historic & Ancient Wonders": ["#AncientWonders", "#HistoricalRestoration", "#TempleArchitecture", "#Heritage", "#CastleBuild"],
        "Extreme & Off-Grid Habitats": ["#OffGridLiving", "#IslandResort", "#LagoonVilla", "#ExtremeArchitecture", "#DesertOasis"],
        "Futuristic Transportation & Transit": ["#MegaBridge", "#Infrastructure", "#TransitEngineering", "#FutureTransit", "#CivilEngineering"],
        "Subterranean & Underwater": ["#UnderwaterCity", "#SubterraneanHome", "#Bioluminescent", "#OceanArchitecture", "#AquaticBuild"],
        "Eco & Biophilic Architecture": ["#BiophilicDesign", "#GreenArchitecture", "#EcoHome", "#SustainableLiving", "#LivingWalls"],
        "Satisfying Transformation": ["#Transformation", "#OddlySatisfying", "#Timelapse", "#SpeedBuild", "#ArchitectureTimelapse"]
    }

    YOUTUBE_TITLE_VARIATIONS = [
        "Building {title} From Scratch in 30 Seconds",
        "Watch {title} Rise Step-by-Step",
        "{title} Transformation in 30 Seconds",
        "From Empty Land to {title}",
        "Constructing {title} From the Ground Up",
        "How {title} Comes to Life in 30 Seconds",
        "From Ruins to {title}: Step-by-Step Build"
    ]

    TIKTOK_CAPTION_VARIATIONS = [
        "An empty {environment} transformed into {title} in 30 seconds. Would you live here? ✨",
        "Building {title} from the ground up in 30 seconds. Rate this architectural design 1-10! 🏗️",
        "From raw undeveloped land to {reveal}. Pure architectural satisfaction ⏳✨",
        "Watch this {title} rise step-by-step in 30 seconds. Which detail is your favorite? 🏛️",
        "Constructing a {architecture} masterpiece in {environment}. Total transformation! 🌟"
    ]

    @classmethod
    def _deterministic_hash(cls, seed_str: str) -> int:
        return int(hashlib.sha256(seed_str.encode("utf-8")).hexdigest(), 16)

    @classmethod
    def build_youtube_metadata(
        cls,
        reel_id: str,
        title: str,
        category: str,
        environment: str = "",
        architecture: str = "",
        transformation: str = "",
        reveal: str = ""
    ) -> Tuple[str, str, List[str]]:
        """Generate unique (title, description, hashtags) for YouTube Shorts."""
        clean_title = title.strip()
        h = cls._deterministic_hash(reel_id + clean_title)

        # 1. Title Generation
        tmpl = cls.YOUTUBE_TITLE_VARIATIONS[h % len(cls.YOUTUBE_TITLE_VARIATIONS)]
        yt_title = tmpl.format(
            title=clean_title,
            environment=environment or "ground",
            architecture=architecture or "structure"
        )

        # 2. Description Generation (2-4 natural sentences)
        env_text = f"an untouched {environment}" if environment else "a pristine setting"
        arch_text = f"{architecture}" if architecture else "modern architectural engineering"
        trans_text = f"{transformation}" if transformation else "continuous progression from foundation to superstructure"
        rev_text = f"{reveal}" if reveal else clean_title

        desc_sentences = [
            f"Watch the seamless 30-second transformation of {clean_title} in {env_text}.",
            f"The build advances through {trans_text}, incorporating {arch_text} into a breathtaking structure.",
            f"Final reveal showcases {rev_text} with photorealistic detail.",
            "Generated with continuous generative AI step-by-step visual modeling."
        ]
        yt_desc = " ".join(desc_sentences)

        # 3. Dynamic Category-Specific Hashtags (3-6 tags)
        base_tags = ["#Shorts", "#Architecture", "#Transformation"]
        category_tags = cls.CATEGORY_HASHTAG_MAP.get(category, ["#Satisfying", "#Design", "#Construction"])
        
        # Pick 2-3 category tags deterministically
        selected_cat_tags = []
        for i, tag in enumerate(category_tags):
            if (h + i) % 2 == 0 and tag not in base_tags:
                selected_cat_tags.append(tag)
        if not selected_cat_tags:
            selected_cat_tags = category_tags[:2]

        all_tags = base_tags + selected_cat_tags + ["#AI"]
        return yt_title, yt_desc, all_tags[:6]

    @classmethod
    def build_tiktok_metadata(
        cls,
        reel_id: str,
        title: str,
        category: str,
        environment: str = "",
        architecture: str = "",
        transformation: str = "",
        reveal: str = ""
    ) -> Tuple[str, List[str]]:
        """Generate unique (caption, hashtags) for TikTok Studio."""
        clean_title = title.strip()
        h = cls._deterministic_hash(reel_id + clean_title + "_tiktok")

        tmpl = cls.TIKTOK_CAPTION_VARIATIONS[h % len(cls.TIKTOK_CAPTION_VARIATIONS)]
        tt_caption = tmpl.format(
            title=clean_title,
            environment=environment or "location",
            architecture=architecture or "modern",
            reveal=reveal or clean_title
        )

        # Category-driven TikTok hashtags (4-7 tags)
        base_tt_tags = ["#satisfying", "#transformation", "#architecture"]
        cat_key = category.lower()
        if "sci-fi" in cat_key or "metropolis" in cat_key:
            extra_tags = ["#futuristic", "#cyberpunk", "#timelapse", "#aitok"]
        elif "luxury" in cat_key:
            extra_tags = ["#luxuryvilla", "#dreamhome", "#timelapse", "#aitok"]
        elif "historic" in cat_key:
            extra_tags = ["#history", "#ancientbuild", "#timelapse", "#aitok"]
        elif "extreme" in cat_key:
            extra_tags = ["#islandlife", "#offgrid", "#timelapse", "#aitok"]
        elif "transportation" in cat_key:
            extra_tags = ["#engineering", "#megabridge", "#timelapse", "#aitok"]
        else:
            extra_tags = ["#build", "#timelapse", "#oddlysatisfying", "#aitok"]

        all_tt_tags = base_tt_tags + extra_tags
        return tt_caption, list(dict.fromkeys(all_tt_tags))[:7]

    @classmethod
    def generate_metadata(
        cls,
        concept: str = "Japanese Zen Temple",
        location: str = "Kyoto",
        architecture: str = "Traditional Zen",
        transformation: str = "Timelapsed construction",
        reveal: str = "Golden glow at sunset",
        reel_id: str = "REEL-2026-0010"
    ) -> Dict[str, Any]:
        """Convenience method returning both YouTube and TikTok metadata dictionaries."""
        yt_title, yt_desc, yt_tags = cls.build_youtube_metadata(
            reel_id=reel_id,
            title=concept,
            category="Historic & Ancient Wonders",
            environment=location,
            architecture=architecture,
            transformation=transformation,
            reveal=reveal
        )
        tt_cap, tt_tags = cls.build_tiktok_metadata(
            reel_id=reel_id,
            title=concept,
            category="Historic & Ancient Wonders",
            environment=location,
            architecture=architecture,
            transformation=transformation,
            reveal=reveal
        )
        return {
            "youtube": {
                "title": yt_title,
                "description": yt_desc,
                "hashtags": yt_tags
            },
            "tiktok": {
                "caption": tt_cap,
                "hashtags": tt_tags
            }
        }

    STORY_HASHTAG_MAP = {
        "Buried by Nature": ["#BuriedCity", "#LostCity", "#Archaeology", "#History", "#Ruins"],
        "Reclaimed by the Jungle": ["#LostCity", "#Jungle", "#Ruins", "#Archaeology", "#AncientHistory"],
        "Abandoned Overnight": ["#AbandonedPlaces", "#GhostTown", "#UrbanExploration", "#History", "#Abandoned"],
        "Carved from Stone": ["#AncientArchitecture", "#RockCut", "#Archaeology", "#History", "#Wonders"],
        "Lost to the Water": ["#LostPlaces", "#Environment", "#History", "#Abandoned", "#Geography"],
        "Above the Clouds": ["#AncientWonders", "#LostCity", "#History", "#Archaeology", "#Mountains"],
        "Born from the Sea": ["#Volcano", "#Geology", "#Nature", "#Science", "#NewLand"],
    }

    # Titles are chosen per narrative_frame. A single shared pool would put "Why Nobody
    # Lives Here Anymore" on Gobekli Tepe, which was never inhabited, and on Lalibela,
    # whose churches are still in use -- the frame is what keeps the claim true.
    STORY_TITLE_VARIATIONS = {
        "abandonment": [
            "{title}: The Place That Was Left Behind",
            "What Happened to {title}",
            "Why Nobody Lives in {title} Anymore",
            "{title}, Then and Now",
            "The Day {title} Was Left Behind",
        ],
        # The cutaway format's payoff is a WORKING interior, so it cannot borrow the
        # abandonment titles the fallback would give it: "Why Nobody Lives Here Anymore"
        # is false for a dam that is running right now.
        "cutaway": [
            "What Is Actually Inside {title}",
            "Nobody Ever Sees What Is Under {title}",
            "{title}: What the Surface Hides",
            "Cut Open: {title}",
            "You Have Walked Over {title} and Never Known",
        ],
        "burial": [
            "{title}: Buried, Then Found Again",
            "What Was Buried at {title}",
            "{title} -- Before and After It Was Buried",
            "The Story of {title} in 30 Seconds",
            "How {title} Disappeared",
        ],
        "vanishing": [
            "{title}: Where the Water Went",
            "What's Left of {title}",
            "{title}, Then and Now",
            "The Story of {title} in 30 Seconds",
        ],
        "creation": [
            "The Making of {title}",
            "How {title} Came to Be",
            "The Story of {title} in 30 Seconds",
        ],
    }

    STORY_CAPTION_VARIATIONS = [
        "{topic_description}. Three moments: before, the turn, and what's left. 🏛️",
        "{name} — {topic_description}. Sound on. 🔊",
        "{topic_description}. Filmed as three continuous beats of the same place.",
        "{name}: three moments, one place, thirty seconds. {topic_description}",
    ]

    @staticmethod
    def _place_hashtag(name: str) -> str:
        """'Plymouth, Montserrat' -> '#PlymouthMontserrat'. Empty string if nothing usable."""
        letters = "".join(ch for ch in (name or "") if ch.isalnum() or ch.isspace())
        joined = "".join(word.capitalize() if word.islower() else word for word in letters.split())
        return f"#{joined}" if joined else ""

    @classmethod
    def build_story_youtube_metadata(
        cls,
        reel_id: str,
        name: str,
        category_group: str,
        real_basis: str,
        topic_description: str,
        narrative_frame: str = "abandonment"
    ) -> Tuple[str, str, List[str]]:
        """
        (title, description, hashtags) for a narrative_ambient_story Reel.

        The description is built from `real_basis` verbatim rather than from a template,
        so the published claim is exactly the documented one and cannot drift into
        invented history as the wording gets reshuffled.
        """
        clean_name = (name or "").strip()
        h = cls._deterministic_hash(reel_id + clean_name)

        variations = cls.STORY_TITLE_VARIATIONS.get(
            narrative_frame, cls.STORY_TITLE_VARIATIONS["abandonment"]
        )
        title = variations[h % len(variations)].format(title=clean_name)

        desc = " ".join([
            f"{topic_description}.",
            real_basis,
            "Reconstructed as three continuous 10-second beats -- the place in use, the event, and what remains today.",
            "AI-generated visualisation with natural ambient sound. Not documentary footage.",
        ])

        place_tag = cls._place_hashtag(clean_name)
        group_tags = cls.STORY_HASHTAG_MAP.get(
            category_group, ["#History", "#LostPlaces", "#Archaeology", "#Abandoned", "#Documentary"]
        )
        tags = ["#Shorts"] + ([place_tag] if place_tag else []) + group_tags + ["#AI"]
        return title, desc, list(dict.fromkeys(tags))[:8]

    @classmethod
    def build_story_tiktok_metadata(
        cls,
        reel_id: str,
        name: str,
        category_group: str,
        topic_description: str
    ) -> Tuple[str, List[str]]:
        """(caption, hashtags) for a narrative_ambient_story Reel."""
        clean_name = (name or "").strip()
        h = cls._deterministic_hash(reel_id + clean_name + "tiktok")

        tmpl = cls.STORY_CAPTION_VARIATIONS[h % len(cls.STORY_CAPTION_VARIATIONS)]
        caption = tmpl.format(name=clean_name, topic_description=topic_description.rstrip("."))

        place_tag = cls._place_hashtag(clean_name).lower()
        base = ([place_tag] if place_tag else []) + ["#history", "#abandoned", "#lostplaces"]
        group_tags = [t.lower() for t in cls.STORY_HASHTAG_MAP.get(category_group, ["#history"])]
        return caption, list(dict.fromkeys(base + group_tags + ["#aitok"]))[:7]
