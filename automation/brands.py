"""
Brand registry -- which channel a weekly run belongs to, and everything that differs
between channels.

This factory runs more than one channel. Each brand has its own accounts, its own Chrome
profiles, its own content mode, and its own inventory; nothing may leak between them.
The failure this exists to prevent is the worst one available here: publishing brand B's
video to brand A's audience, which cannot be undone because this system may not delete
remote content.

Two rules hold the design together.

1. The default brand reproduces the pre-brand behaviour EXACTLY -- same week ids, same
   Reel ids, same workspace paths, same accounts, same ports. A run that does not name a
   brand behaves as it always did, because the 14-Reel series that is already live on
   three platforms must not shift by a single filename.

2. A brand whose accounts are not configured yet FAILS CLOSED. Placeholder handles are
   rejected before any browser opens, so a half-set-up brand can never fall back to
   another brand's channel. The ACCOUNT_MISMATCH guards in the publishers stay exactly as
   they are; this module feeds them the right expectation, it does not weaken them.

Isolation is by id prefix rather than by directory nesting. A brand's weeks are named
"CBM-2026-W36" and its Reels "CBM-REEL-2026-0001", so every existing path,
repository and state file keeps working untouched while the two brands' inventories can
never collide or resume each other.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import os

from automation.content.content_modes import (
    HIDDEN_BUILD_STORY,
    NARRATIVE_AMBIENT_STORY,
    is_live_eligible_mode,
)

# Marks an account that has not been set up yet. Any brand still carrying one of these
# refuses to publish -- see Brand.ensure_publishable.
UNCONFIGURED = "UNCONFIGURED"


def _profile_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ReelsAIFactory"
    return Path.home() / ".reels_ai_factory"


@dataclass(frozen=True)
class Brand:
    """One channel identity: what it publishes, where, and as whom."""

    brand_id: str
    display_name: str
    content_mode: str

    # Prepended to week ids and Reel ids. Empty for the default brand, which must keep
    # producing "2026-W36" and "REEL-2026-0001" exactly as before.
    id_prefix: str

    # Account identities. These become the ACCOUNT_MISMATCH expectations.
    youtube_handle: str
    youtube_channel_id: Optional[str]
    tiktok_username: str

    # Each brand needs its own logged-in Chrome, so the profiles and CDP ports differ.
    # Flow (9222) is deliberately shared: generation is account-agnostic and both brands
    # draw from the same Flow credits.
    youtube_port: int
    tiktok_port: int
    instagram_port: int
    profile_suffix: str


    # Instagram delivery is per-brand: the first channel was handed to the cloud worker
    # before the composer route existed.
    instagram_delivery: str = "web"

    # Which platforms this brand publishes to. A platform left out is skipped entirely --
    # not failed, not retried, not counted against the week -- while generation continues
    # as normal, so the videos are on disk and ready the moment it is switched back on.
    # Re-enabling one makes every past week read as unfinished again, which is exactly
    # right: the next run picks up only the missing platform and leaves the rest alone.
    platforms: Tuple[str, ...] = ("youtube", "tiktok", "instagram")

    @property
    def login_bat(self) -> str:
        """
        The .bat that signs THIS brand in.

        Derived from the brand id rather than stored, so a new brand cannot be added with
        a name that disagrees with its files -- and every error message that names it
        stays correct by construction. Messages used to name one file for everybody: a
        dropped craftsbyman session sent the operator to the FIRST channel's TikTok
        browser on port 9223, while the session that had actually expired was the second
        channel's on 9233. Signing in there fixed nothing and made the guard look broken.
        """
        return f"{self.brand_id.upper()}_GIRIS.bat"

    @property
    def weekly_bat(self) -> str:
        """The .bat that runs this brand's week, named when a run stops part-way."""
        return f"{self.brand_id.upper()}_HAFTALIK_14_REEL.bat"

    def publishes_to(self, platform: str) -> bool:
        return platform in self.platforms

    @property
    def youtube_profile_dir(self) -> Path:
        return _profile_root() / f"youtube-studio-profile{self.profile_suffix}"

    @property
    def tiktok_profile_dir(self) -> Path:
        return _profile_root() / f"tiktok-profile{self.profile_suffix}"

    @property
    def instagram_profile_dir(self) -> Path:
        return _profile_root() / f"instagram-profile{self.profile_suffix}"

    def week_id(self, iso_week_id: str) -> str:
        """'2026-W36' -> the brand's own week id."""
        return f"{self.id_prefix}{iso_week_id}"

    def owns_week_id(self, week_id: str) -> bool:
        """
        Whether a week belongs to this brand.

        The default brand has no prefix, so it must additionally reject anything carrying
        another brand's prefix -- otherwise it would claim every week on disk and could
        resume, or schedule into, a different channel's batch.
        """
        if self.id_prefix:
            return week_id.startswith(self.id_prefix)
        return not any(
            b.id_prefix and week_id.startswith(b.id_prefix) for b in BRANDS.values()
        )

    def reel_id(self, number: int) -> str:
        return f"{self.id_prefix}REEL-2026-{number:04d}"

    def owns_reel_id(self, reel_id: str) -> bool:
        if self.id_prefix:
            return reel_id.startswith(self.id_prefix)
        return not any(
            b.id_prefix and reel_id.startswith(b.id_prefix) for b in BRANDS.values()
        )

    def unconfigured_accounts(self) -> List[str]:
        missing = []
        if self.youtube_handle == UNCONFIGURED:
            missing.append("youtube_handle")
        if self.youtube_channel_id in (None, UNCONFIGURED):
            missing.append("youtube_channel_id")
        if self.tiktok_username == UNCONFIGURED:
            missing.append("tiktok_username")
        return missing

    def ensure_publishable(self) -> None:
        """
        Raise before anything opens a browser if this brand is not fully set up.

        Publishing with a placeholder expectation is the one thing that could put a video
        on the wrong channel, so it is refused loudly rather than left to a downstream
        guard.
        """
        missing = self.unconfigured_accounts()
        if missing:
            raise ValueError(
                f"BRAND_NOT_CONFIGURED: '{self.brand_id}' henuz yayina hazir degil. "
                f"Eksik: {', '.join(missing)}. automation/brands.py icinde gercek hesap "
                f"kimliklerini girin; placeholder ile yayin yapilmaz."
            )
        if not is_live_eligible_mode(self.content_mode):
            raise ValueError(
                f"BRAND_MODE_NOT_LIVE_ELIGIBLE: '{self.brand_id}' modu "
                f"'{self.content_mode}' canli yayina uygun degil."
            )

    def apply_to_publishing_config(self, cfg):
        """
        Point a PublishingConfig at this brand's accounts and browsers.

        Mutates in place and returns it. The default brand's values are identical to the
        dataclass defaults, so applying it is a no-op by construction -- which is what
        keeps the existing series byte-for-byte unchanged.
        """
        cfg.youtube_expected_handle = self.youtube_handle
        cfg.youtube_expected_channel_id = self.youtube_channel_id
        cfg.youtube_studio_debug_port = self.youtube_port
        cfg.youtube_studio_profile_dir = self.youtube_profile_dir
        cfg.tiktok_expected_username = self.tiktok_username
        cfg.tiktok_debug_port = self.tiktok_port
        cfg.tiktok_profile_dir = self.tiktok_profile_dir
        cfg.login_bat = self.login_bat
        return cfg


# The original channel. Every value here MUST match the pre-brand defaults in
# publishing/config.py -- this brand is the running 14-Reel series.
BUILDVERSE = Brand(
    brand_id="buildverse",
    display_name="BuildVerse",
    content_mode=NARRATIVE_AMBIENT_STORY,
    id_prefix="",
    youtube_handle="@BuiIdVerse",
    youtube_channel_id="UCahsmsqzTCtwTDDtvCurtBA",
    tiktok_username="@kitchenverse360",
    youtube_port=9224,
    tiktok_port=9223,
    instagram_port=9225,
    profile_suffix="",
    instagram_delivery="web",
)

# The second channel: buried-object transformation stories with a recurring craftsman.
# Accounts confirmed by the operator on 2026-08-21. The channel id is what actually
# gates YouTube -- verify_logged_in_channel matches it against the Studio URL and returns
# before the handle is ever read -- so it is the value that must be exact here.
CRAFTSBYMAN = Brand(
    brand_id="craftsbyman",
    display_name="Crafts By Man",
    content_mode=HIDDEN_BUILD_STORY,
    id_prefix="CBM-",
    youtube_handle="@craftsbyman",
    youtube_channel_id="UCcZow6RbRyK3xH-KymR_9KQ",
    tiktok_username="@craftsbyman",
    youtube_port=9234,
    tiktok_port=9233,
    instagram_port=9235,
    profile_suffix="-craftsbyman",
    instagram_delivery="web",
    # Instagram is off for this channel while its scheduling side is unusable
    # (2026-08-21). Generation is unaffected: the 14 finished videos sit in the workspace,
    # and putting "instagram" back in this tuple is the whole of what re-enabling takes.
    platforms=("youtube", "tiktok"),
)

BRANDS: Dict[str, Brand] = {b.brand_id: b for b in (BUILDVERSE, CRAFTSBYMAN)}

DEFAULT_BRAND_ID = BUILDVERSE.brand_id


def login_bat_for_profile(profile_dir) -> str:
    """
    Which brand's login .bat owns this Chrome profile directory.

    The browser managers know the profile they were handed but not the brand behind it,
    and they are exactly where a dropped session surfaces. Naming one file for everybody
    sent the operator to the wrong channel's browser; the profile suffix is the one thing
    on hand that identifies the brand.
    """
    name = str(profile_dir or "").lower()
    for brand in BRANDS.values():
        if brand.profile_suffix and name.endswith(brand.profile_suffix.lower()):
            return brand.login_bat
    return BRANDS[DEFAULT_BRAND_ID].login_bat


def get_brand(brand_id: Optional[str] = None) -> Brand:
    """Resolve a brand id, defaulting to the original channel."""
    key = (brand_id or DEFAULT_BRAND_ID).strip().lower()
    if key not in BRANDS:
        raise ValueError(
            f"UNKNOWN_BRAND: '{brand_id}'. Taninan markalar: {', '.join(sorted(BRANDS))}."
        )
    return BRANDS[key]
