"""
Publishing configuration loader and schema validation.
"""
from dataclasses import dataclass, field
import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

def get_default_tiktok_profile_path() -> Path:
    """Returns %LOCALAPPDATA%\\ReelsAIFactory\\tiktok-profile on Windows."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ReelsAIFactory" / "tiktok-profile"
def get_default_youtube_studio_profile_path() -> Path:
    """Returns %LOCALAPPDATA%\\ReelsAIFactory\\youtube-studio-profile on Windows."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "ReelsAIFactory" / "youtube-studio-profile"
    return Path.home() / ".reels_ai_factory" / "youtube-studio-profile"

@dataclass
class PublishingConfig:
    """Configuration settings for YouTube Shorts and TikTok Studio publishing."""
    enabled: bool = True
    timezone: str = "Europe/Istanbul"
    platforms: List[str] = field(default_factory=lambda: ["youtube", "tiktok"])
    daily_slots: List[str] = field(default_factory=lambda: ["19:30", "22:00"])
    schedule_start_date: Optional[str] = "2026-08-16"
    strict_count: bool = True
    ai_disclosure: bool = True
    auto_publish_immediately: bool = False
    max_retries: int = 1
    live_publish_enabled: bool = False
    single_live_test_passed: bool = False
    fail_fast_live_test: bool = True
    two_phase_live_test: bool = True

    # YouTube Specific
    youtube_enabled: bool = True
    youtube_mode: str = "studio"  # 'studio' (Playwright CDP Web UI) or 'api' (YouTube Data API v3)
    youtube_expected_handle: str = "@BuiIdVerse"
    youtube_expected_channel_id: Optional[str] = "UCahsmsqzTCtwTDDtvCurtBA"
    youtube_studio_debug_port: int = 9224
    youtube_studio_profile_dir: Path = field(default_factory=get_default_youtube_studio_profile_path)
    youtube_studio_url: str = "https://studio.youtube.com/"
    youtube_client_secret_path: Path = field(default_factory=lambda: Path("secrets/youtube/client_secret.json").resolve())
    youtube_token_path: Path = field(default_factory=lambda: Path("secrets/youtube/token.json").resolve())
    youtube_privacy_status: str = "private"
    youtube_made_for_kids: bool = False

    # TikTok Specific
    tiktok_enabled: bool = True
    tiktok_expected_username: str = "@kitchenverse360"
    tiktok_debug_port: int = 9223
    tiktok_profile_dir: Path = field(default_factory=get_default_tiktok_profile_path)
    tiktok_url: str = "https://www.tiktok.com/tiktokstudio/upload"
    tiktok_headless: bool = False

    def validate(self) -> None:
        if not self.daily_slots:
            raise ValueError("daily_slots cannot be empty.")
        if self.youtube_enabled and self.youtube_mode == "api" and not self.youtube_client_secret_path:
            raise ValueError("youtube_client_secret_path must be configured for API mode.")

def load_publishing_config(
    config_dict: Optional[Dict[str, Any]] = None,
    base_dir: Optional[Path] = None
) -> PublishingConfig:
    """Load publishing config from dict or local config files."""
    if base_dir is None:
        base_dir = Path(__file__).parent.parent.parent.resolve()

    data: Dict[str, Any] = {}
    local_pub_cfg = base_dir / "publishing.local.json"
    local_main_cfg = base_dir / "config.local.json"

    if local_pub_cfg.exists():
        try:
            with open(local_pub_cfg, "r", encoding="utf-8") as f:
                data.update(json.load(f))
        except Exception:
            pass
    elif local_main_cfg.exists():
        try:
            with open(local_main_cfg, "r", encoding="utf-8") as f:
                main_data = json.load(f)
                if "publishing" in main_data and isinstance(main_data["publishing"], dict):
                    data.update(main_data["publishing"])
        except Exception:
            pass

    if config_dict:
        data.update(config_dict)

    # Resolve paths
    yt_sec_str = data.get("youtube_client_secret_path", "secrets/youtube/client_secret.json")
    yt_secret_path = Path(yt_sec_str) if Path(yt_sec_str).is_absolute() else (base_dir / yt_sec_str).resolve()

    yt_tok_str = data.get("youtube_token_path", "secrets/youtube/token.json")
    yt_tok_path = Path(yt_tok_str) if Path(yt_tok_str).is_absolute() else (base_dir / yt_tok_str).resolve()

    yt_studio_prof_str = data.get("youtube_studio_profile_dir") or data.get("youtube_studio_profile_path")
    yt_studio_prof_path = Path(yt_studio_prof_str).resolve() if yt_studio_prof_str else get_default_youtube_studio_profile_path()

    tt_prof_str = data.get("tiktok_profile_path") or data.get("tiktok_profile_dir")
    tt_prof_path = Path(tt_prof_str).resolve() if tt_prof_str else get_default_tiktok_profile_path()

    cfg = PublishingConfig(
        enabled=data.get("enabled", True),
        timezone=data.get("timezone", "Europe/Istanbul"),
        platforms=data.get("platforms", ["youtube", "tiktok"]),
        daily_slots=data.get("daily_slots", ["19:30", "22:00"]),
        schedule_start_date=data.get("schedule_start_date", "2026-08-16"),
        strict_count=data.get("strict_count", True),
        ai_disclosure=data.get("ai_disclosure", True),
        auto_publish_immediately=data.get("auto_publish_immediately", False),
        max_retries=data.get("max_retries", 1),
        live_publish_enabled=data.get("live_publish_enabled", False),
        single_live_test_passed=data.get("single_live_test_passed", False),
        youtube_enabled=data.get("youtube_enabled", True),
        youtube_mode=data.get("youtube_mode", "studio"),
        youtube_expected_handle=data.get("youtube_expected_handle", "@BuiIdVerse"),
        youtube_expected_channel_id=data.get("youtube_expected_channel_id", "UCahsmsqzTCtwTDDtvCurtBA"),
        youtube_studio_debug_port=int(data.get("youtube_studio_debug_port", 9224)),
        youtube_studio_profile_dir=yt_studio_prof_path,
        youtube_studio_url=data.get("youtube_studio_url", "https://studio.youtube.com/"),
        youtube_client_secret_path=yt_secret_path,
        youtube_token_path=yt_tok_path,
        youtube_privacy_status=data.get("youtube_privacy_status", "private"),
        youtube_made_for_kids=data.get("youtube_made_for_kids", False),
        tiktok_enabled=data.get("tiktok_enabled", True),
        tiktok_expected_username=data.get("tiktok_expected_username", "@kitchenverse360"),
        tiktok_debug_port=int(data.get("tiktok_debug_port", 9223)),
        tiktok_profile_dir=tt_prof_path,
        tiktok_url=data.get("tiktok_url", "https://www.tiktok.com/creator-center/upload"),
        tiktok_headless=data.get("tiktok_headless", False)
    )

    # Ensure profile directories exist
    cfg.youtube_studio_profile_dir.mkdir(parents=True, exist_ok=True)
    cfg.tiktok_profile_dir.mkdir(parents=True, exist_ok=True)
    cfg.youtube_client_secret_path.parent.mkdir(parents=True, exist_ok=True)

    return cfg
