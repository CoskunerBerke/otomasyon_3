"""
YouTube Data API mode: per-brand tokens, and picking the right publisher.

Driving Studio's web UI put two Reels on the wrong day on 2026-09-10, because the date
has to be typed into a locale-dependent calendar. The API takes publishAt as an RFC 3339
timestamp, so there is no calendar and no locale. It costs quota instead -- 1600 units
per videos.insert against a default 10,000 a day, about six uploads.

The risk this file guards is the one that would be worst: a single OAuth token shared
between the two channels. One token authorises one channel, so signing in for craftsbyman
would overwrite buildverse's token and the next run would upload to whichever channel was
authorised last.
"""
from pathlib import Path
from unittest.mock import MagicMock

from automation.brands import get_brand
from automation.publishing.config import PublishingConfig


def test_each_brand_gets_its_own_token_file():
    bv = get_brand("buildverse").youtube_token_path
    cbm = get_brand("craftsbyman").youtube_token_path
    assert bv != cbm, "iki kanal ayni token dosyasini paylasamaz"
    assert bv.name == "token.json", "varsayilan marka mevcut yolunu korumali"
    assert cbm.name == "token-craftsbyman.json"


def test_token_paths_are_absolute():
    """Resolved from the repo root, so the path does not depend on the working directory."""
    for brand_id in ("buildverse", "craftsbyman"):
        assert get_brand(brand_id).youtube_token_path.is_absolute()


def test_brand_application_sets_the_token_path():
    cfg = get_brand("craftsbyman").apply_to_publishing_config(PublishingConfig())
    assert cfg.youtube_token_path.name == "token-craftsbyman.json"
    # The channel identity travels with it -- the API publisher refuses a token that
    # authorises a different channel, so these two must always agree.
    assert cfg.youtube_expected_handle == "@craftsbyman"
    assert cfg.youtube_expected_channel_id == "UCcZow6RbRyK3xH-KymR_9KQ"


def test_default_brand_keeps_the_original_token_path():
    """Applying the default brand must stay a no-op for the running series."""
    cfg = get_brand("buildverse").apply_to_publishing_config(PublishingConfig())
    assert cfg.youtube_token_path.name == "token.json"
    assert cfg.youtube_expected_handle == "@BuiIdVerse"


def _pipeline_with_mode(mode, dry_run=False):
    from automation.simple_weekly_pipeline import SimpleWeeklyPipeline

    pipe = SimpleWeeklyPipeline.__new__(SimpleWeeklyPipeline)
    pipe.yt_publisher = None
    pipe.dry_run = dry_run
    pipe.brand = get_brand("craftsbyman")
    cfg = pipe.brand.apply_to_publishing_config(PublishingConfig())
    cfg.youtube_mode = mode
    pipe.pub_config = cfg
    return pipe


def test_api_mode_selects_the_data_api_publisher():
    from automation.publishing.youtube_publisher import YouTubePublisher

    pipe = _pipeline_with_mode("api")
    pipe._init_youtube_publisher_if_needed()
    assert isinstance(pipe.yt_publisher, YouTubePublisher)


def test_studio_mode_still_selects_the_web_publisher():
    from automation.publishing.youtube_studio_publisher import YouTubeStudioPublisher

    pipe = _pipeline_with_mode("studio")
    pipe._init_youtube_publisher_if_needed()
    assert isinstance(pipe.yt_publisher, YouTubeStudioPublisher)


def test_dry_run_never_builds_a_live_publisher():
    """A rehearsal must not reach a real channel in either mode."""
    from automation.publishing.youtube_publisher import MockYouTubePublisher
    from automation.publishing.youtube_studio_publisher import MockYouTubeStudioPublisher

    api = _pipeline_with_mode("api", dry_run=True)
    api._init_youtube_publisher_if_needed()
    assert isinstance(api.yt_publisher, MockYouTubePublisher)

    studio = _pipeline_with_mode("studio", dry_run=True)
    studio._init_youtube_publisher_if_needed()
    assert isinstance(studio.yt_publisher, MockYouTubeStudioPublisher)


def test_an_injected_publisher_is_left_alone():
    injected = MagicMock()
    pipe = _pipeline_with_mode("api")
    pipe.yt_publisher = injected
    pipe._init_youtube_publisher_if_needed()
    assert pipe.yt_publisher is injected
