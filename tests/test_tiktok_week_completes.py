"""
Regression tests for finishing a whole week on TikTok.

Two defects sat between craftsbyman and its first complete TikTok week, and neither
would have shown up until the run was already live on a real account.

1. TikTok's scheduler hands back no per-post id, so the publisher records the fixed
   marker "tiktok_scheduled_post" on every Reel. The week-level collision guard added on
   2026-08-21 compares recorded ids literally, so Reel 2 would have been refused as
   REEL_ID_MEDIA_MISMATCH against Reel 1 -- both of them correctly scheduled -- and the
   platform would have stopped there. Every week, on its second Reel.

2. The login helper opened TikTok's other upload URL, so the one-time new-account tour
   that blocks the caption editor was never met on the page the publisher actually
   drives. That tour is what stopped CBM-REEL-2026-0001 on 2026-08-21, and it appears
   once per account and never again -- there is no second chance to capture it.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REPO = Path(__file__).resolve().parents[1]


def test_tiktoks_fixed_marker_is_not_treated_as_a_collision():
    """Reel 2 must not be refused for carrying the same marker as Reel 1."""
    from automation.simple_weekly_pipeline import NON_IDENTIFYING_REMOTE_IDS

    assert "tiktok_scheduled_post" in NON_IDENTIFYING_REMOTE_IDS


def test_the_marker_the_publisher_records_is_the_one_exempted():
    """
    The exemption is a literal string, so it silently stops matching if the publisher
    ever renames its marker -- and the week would break on Reel 2 again.
    """
    from automation.simple_weekly_pipeline import NON_IDENTIFYING_REMOTE_IDS

    src = (REPO / "automation" / "publishing" / "tiktok_publisher.py").read_text(encoding="utf-8")
    # Literal ids only. The mock publisher derives its id per Reel, so it is genuinely
    # identifying and must NOT be exempt.
    recorded = {
        line.split('remote_id="', 1)[1].split('"', 1)[0]
        for line in src.splitlines()
        if 'remote_id="' in line
    }
    assert recorded, "the publisher no longer records a remote_id at all"
    assert recorded <= set(NON_IDENTIFYING_REMOTE_IDS), (
        f"TikTok records {recorded - set(NON_IDENTIFYING_REMOTE_IDS)}, which the week-level "
        f"collision guard would read as one Reel stealing another's video"
    )


def test_a_real_youtube_id_is_still_guarded():
    """The exemption must not become a hole: real per-video ids still collide."""
    from automation.simple_weekly_pipeline import NON_IDENTIFYING_REMOTE_IDS

    assert "VTMhhYTl9Co" not in NON_IDENTIFYING_REMOTE_IDS
    assert "A_-ciGRmRQc" not in NON_IDENTIFYING_REMOTE_IDS


def test_the_collision_guard_consults_the_exemption():
    """Guards the wiring, not just the constant."""
    import inspect
    from automation import simple_weekly_pipeline as swp

    src = inspect.getsource(swp.SimpleWeeklyPipeline._run_platform_phase)
    before_guard = src.split("_reel_already_using_remote_id")[0]
    condition = "\n".join(before_guard.rstrip().splitlines()[-6:])

    assert "NON_IDENTIFYING_REMOTE_IDS" in condition
    assert "if res_rec.remote_id" in condition


def test_login_lands_on_the_page_the_publisher_drives():
    """
    The new-account tour appears once, on the upload page the automation uses. Opening a
    different URL for the human means they dismiss nothing the automation will meet.
    """
    from automation.publishing.config import PublishingConfig

    src = (REPO / "automation" / "publishing" / "brand_login.py").read_text(encoding="utf-8")
    assert "launch_chrome_for_tiktok(start_url=PublishingConfig().tiktok_url)" in src, (
        "the login helper must open the publisher's own TikTok upload URL"
    )
    assert PublishingConfig().tiktok_url.startswith("https://www.tiktok.com/")
