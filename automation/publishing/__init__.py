"""
Publishing package exports.
Provides lightweight eager imports for data models and lazy dynamic imports
for heavy browser, UI, and orchestrator submodules to ensure cloud import isolation.
"""
import importlib
from typing import Any

# Eager lightweight models (No heavy browser / local dependencies)
from .models import (
    Platform,
    PlatformPublicationStatus,
    PublishRecord,
    PublishingBatch
)

# Lazy import map for heavy / local-only automation submodules
_LAZY_EXPORTS = {
    "PublishingConfig": (".config", "PublishingConfig"),
    "load_publishing_config": (".config", "load_publishing_config"),
    "get_default_tiktok_profile_path": (".config", "get_default_tiktok_profile_path"),
    "SchedulePlanner": (".schedule_planner", "SchedulePlanner"),
    "PublishingMetadataBuilder": (".metadata_builder", "PublishingMetadataBuilder"),
    "IdempotencyManager": (".idempotency", "IdempotencyManager"),
    "PublishingRepository": (".repository", "PublishingRepository"),
    "YouTubeAuthManager": (".youtube_auth", "YouTubeAuthManager"),
    "YouTubeAuthError": (".youtube_auth", "YouTubeAuthError"),
    "AuthRequiredError": (".youtube_auth", "AuthRequiredError"),
    "BaseYouTubePublisher": (".youtube_publisher", "BaseYouTubePublisher"),
    "YouTubePublisher": (".youtube_publisher", "YouTubePublisher"),
    "MockYouTubePublisher": (".youtube_publisher", "MockYouTubePublisher"),
    "TikTokBrowserManager": (".tiktok_browser", "TikTokBrowserManager"),
    "TikTokSelectors": (".tiktok_selectors", "TikTokSelectors"),
    "TikTokUIObserver": (".tiktok_ui_observer", "TikTokUIObserver"),
    "BaseTikTokPublisher": (".tiktok_publisher", "BaseTikTokPublisher"),
    "TikTokPublisher": (".tiktok_publisher", "TikTokPublisher"),
    "MockTikTokPublisher": (".tiktok_publisher", "MockTikTokPublisher"),
    "PublishingOrchestrator": (".publisher", "PublishingOrchestrator")
}


def __getattr__(name: str) -> Any:
    """Dynamically imports heavy components only when explicitly requested."""
    if name in _LAZY_EXPORTS:
        module_path, attr_name = _LAZY_EXPORTS[name]
        module = importlib.import_module(module_path, package=__package__)
        val = getattr(module, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __dir__():
    return sorted(list(globals().keys()) + list(_LAZY_EXPORTS.keys()))


__all__ = [
    "Platform",
    "PlatformPublicationStatus",
    "PublishRecord",
    "PublishingBatch",
    "PublishingConfig",
    "load_publishing_config",
    "get_default_tiktok_profile_path",
    "SchedulePlanner",
    "PublishingMetadataBuilder",
    "IdempotencyManager",
    "PublishingRepository",
    "YouTubeAuthManager",
    "YouTubeAuthError",
    "AuthRequiredError",
    "BaseYouTubePublisher",
    "YouTubePublisher",
    "MockYouTubePublisher",
    "TikTokBrowserManager",
    "TikTokSelectors",
    "TikTokUIObserver",
    "BaseTikTokPublisher",
    "TikTokPublisher",
    "MockTikTokPublisher",
    "PublishingOrchestrator"
]
