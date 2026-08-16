"""
Deterministic and concept-driven metadata generator for YouTube Shorts and TikTok Studio.
Generates unique English titles, descriptions, captions, and curated hashtags tailored to each concept.
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
