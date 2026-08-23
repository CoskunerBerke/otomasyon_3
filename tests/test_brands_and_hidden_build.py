"""
Regression tests for running a second channel alongside the first.

The original 14-Reel series is live on three platforms and must not shift by a single
filename. The second brand publishes different content to different accounts from the
same machine, and the failure to prevent is the worst one available here: brand B's video
appearing on brand A's channel, which cannot be undone because this system may not delete
remote content.

Three properties are load-bearing:

  1. The default brand reproduces the pre-brand behaviour exactly -- same week ids, same
     Reel ids, same accounts, same ports.
  2. The two brands cannot see each other's inventory. Neither resumes, schedules into,
     or allocates ids from the other's namespace.
  3. A brand whose accounts are still placeholders refuses to publish rather than falling
     back to whatever account the browser happens to be signed into.

Also covered: the hidden_build content mode itself, including the two defects the manual
proving runs exposed -- a character block that rendered as an on-screen caption, and a
craftsman who must stay identical because his face is the channel's profile picture.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.brands import (
    BRANDS,
    BUILDVERSE,
    CRAFTSBYMAN,
    UNCONFIGURED,
    Brand,
    get_brand,
)
from automation.content.content_modes import (
    HIDDEN_BUILD_STORY,
    NARRATIVE_AMBIENT_STORY,
    is_live_eligible_mode,
    requires_audio,
)
from automation.content.engine import provider_for_mode
from automation.content.hidden_build_concepts import HIDDEN_BUILD_CONCEPTS
from automation.content.hidden_build_planner import HiddenBuildPlanner
from automation.publishing.config import PublishingConfig
from automation.simple_weekly_pipeline import SimpleWeeklyPipeline


# ---------------------------------------------------------------- the default must not move

def test_default_brand_keeps_the_original_accounts_and_ports():
    """These are the live channel's values; changing them redirects a running series."""
    fresh = PublishingConfig()
    applied = BUILDVERSE.apply_to_publishing_config(PublishingConfig())

    assert applied.youtube_expected_handle == fresh.youtube_expected_handle
    assert applied.youtube_expected_channel_id == fresh.youtube_expected_channel_id
    assert applied.youtube_studio_debug_port == fresh.youtube_studio_debug_port
    assert applied.tiktok_expected_username == fresh.tiktok_expected_username
    assert applied.tiktok_debug_port == fresh.tiktok_debug_port


def test_default_brand_keeps_the_original_id_shapes():
    assert BUILDVERSE.id_prefix == ""
    assert BUILDVERSE.week_id("2026-W36") == "2026-W36"
    assert BUILDVERSE.reel_id(25) == "REEL-2026-0025"


def test_default_brand_still_runs_the_original_content_mode():
    assert BUILDVERSE.content_mode == NARRATIVE_AMBIENT_STORY


def test_an_unnamed_run_is_the_original_brand(tmp_path):
    pipe = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v", dry_run=True)
    assert pipe.brand.brand_id == BUILDVERSE.brand_id
    assert pipe.content_mode == NARRATIVE_AMBIENT_STORY


# ---------------------------------------------------------------- isolation

def test_brands_do_not_share_a_namespace():
    assert CRAFTSBYMAN.id_prefix and CRAFTSBYMAN.id_prefix != BUILDVERSE.id_prefix
    assert CRAFTSBYMAN.week_id("2026-W36") != BUILDVERSE.week_id("2026-W36")
    assert CRAFTSBYMAN.reel_id(1) != BUILDVERSE.reel_id(1)


def test_neither_brand_claims_the_other_s_weeks():
    """The default brand has no prefix, so it must actively reject prefixed ids."""
    assert BUILDVERSE.owns_week_id("2026-W35")
    assert not BUILDVERSE.owns_week_id("CBM-2026-W35")
    assert CRAFTSBYMAN.owns_week_id("CBM-2026-W35")
    assert not CRAFTSBYMAN.owns_week_id("2026-W35")


def test_neither_brand_claims_the_other_s_reels():
    assert BUILDVERSE.owns_reel_id("REEL-2026-0025")
    assert not BUILDVERSE.owns_reel_id("CBM-REEL-2026-0001")
    assert CRAFTSBYMAN.owns_reel_id("CBM-REEL-2026-0001")
    assert not CRAFTSBYMAN.owns_reel_id("REEL-2026-0025")


def test_brands_use_separate_browsers():
    """One Chrome profile cannot be signed into two channels at once."""
    ports = [
        (BUILDVERSE.youtube_port, CRAFTSBYMAN.youtube_port),
        (BUILDVERSE.tiktok_port, CRAFTSBYMAN.tiktok_port),
        (BUILDVERSE.instagram_port, CRAFTSBYMAN.instagram_port),
    ]
    for a, b in ports:
        assert a != b
    assert BUILDVERSE.youtube_profile_dir != CRAFTSBYMAN.youtube_profile_dir
    assert BUILDVERSE.tiktok_profile_dir != CRAFTSBYMAN.tiktok_profile_dir
    assert BUILDVERSE.instagram_profile_dir != CRAFTSBYMAN.instagram_profile_dir


def test_all_ports_across_all_brands_are_unique():
    used = []
    for brand in BRANDS.values():
        used += [brand.youtube_port, brand.tiktok_port, brand.instagram_port]
    assert len(used) == len(set(used)), "two channels would fight over one CDP port"
    assert 9222 not in used, "9222 is Flow's port and is shared deliberately"


def test_a_brand_scans_only_its_own_batches(tmp_path):
    """
    The calendar must not leak: the other channel's schedule cannot push this one's start
    date, and an unfinished week of theirs must not be resumed here.
    """
    import datetime
    from automation.orchestration.batch_manifest import BatchManifest, BatchReel, BatchRepository

    repo = BatchRepository(tmp_path)
    base = datetime.date(2026, 8, 24)
    reels = [BatchReel(
        index=1, reel_id="REEL-2026-0025",
        scheduled_at_local=f"{base.isoformat()} 19:30:00",
        scheduled_at_utc=f"{base.isoformat()} 16:30:00",
        generation_status="COMPLETE",
    )]
    repo.save_manifest(BatchManifest(week_id="2026-W35", start_date=base.isoformat(),
                                    status="LOCKED", reels=reels))
    repo.ensure_progress_entries("2026-W35", ["REEL-2026-0025"])
    progress = repo.load_progress("2026-W35")
    progress["REEL-2026-0025"] = {
        "youtube": {"status": "SCHEDULED", "remote_id": "x", "url": "u", "error": None},
        "tiktok": {"status": "SCHEDULED", "remote_id": "x", "url": "u", "error": None},
        "instagram": {"status": "SCHEDULED", "remote_media_id": None, "error": None},
    }
    repo.save_progress("2026-W35", progress)

    other = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v",
                                 dry_run=True, brand=get_brand("craftsbyman"))
    assert other.find_last_scheduled_date() is None, "another brand's schedule leaked in"
    assert other._find_unfinished_week_id() is None

    mine = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v", dry_run=True)
    assert mine.find_last_scheduled_date() == base


# ---------------------------------------------------------------- fail closed

def test_an_unconfigured_brand_refuses_to_publish():
    """The guard itself, on a brand built for the test -- the real ones are configured."""
    blank = Brand(
        brand_id="blank", display_name="Blank", content_mode=HIDDEN_BUILD_STORY, id_prefix="B-",
        youtube_handle=UNCONFIGURED, youtube_channel_id=UNCONFIGURED, tiktok_username=UNCONFIGURED,
        youtube_port=9264, tiktok_port=9263, instagram_port=9265, profile_suffix="-blank",
    )
    assert blank.unconfigured_accounts() == ["youtube_handle", "youtube_channel_id", "tiktok_username"]
    with pytest.raises(ValueError, match="BRAND_NOT_CONFIGURED"):
        blank.ensure_publishable()


def test_every_registered_brand_is_ready_to_publish():
    """A registered brand with a placeholder left in it would fail on a live run."""
    for brand in BRANDS.values():
        brand.ensure_publishable()


def test_the_second_channel_points_at_the_right_accounts():
    """
    The channel id is the value that actually gates YouTube: verify_logged_in_channel
    matches it against the Studio URL and returns before the handle is read.
    """
    assert CRAFTSBYMAN.youtube_channel_id == "UCcZow6RbRyK3xH-KymR_9KQ"
    assert CRAFTSBYMAN.youtube_handle == "@craftsbyman"
    assert CRAFTSBYMAN.tiktok_username == "@craftsbyman"


def test_a_brand_with_no_history_starts_at_once_and_an_established_one_does_not(tmp_path):
    """
    A new channel has no rhythm to align to, so it starts as soon as it can rather than
    waiting for a calendar Monday. A brand that has published continues from its own last
    slot and never reaches that branch.

    "As soon as it can" is today while today's slots are still ahead, and tomorrow once
    they are not -- see _earliest_usable_start. Asserting the soonest usable day rather
    than a literal "tomorrow" keeps this test honest at every hour of the day.
    """
    import datetime
    from automation.orchestration.batch_manifest import BatchManifest, BatchReel, BatchRepository
    from automation.orchestration.slot_generator import get_timezone

    fresh = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v",
                                 dry_run=True, brand=get_brand("craftsbyman"))
    now = datetime.datetime.now(get_timezone("Europe/Istanbul"))
    assert fresh.find_last_scheduled_date() is None
    assert fresh._resolve_start_date() == fresh._earliest_usable_start(now)
    assert fresh._resolve_start_date() >= now.date()

    repo = BatchRepository(tmp_path)
    last = datetime.date.today() + datetime.timedelta(days=20)
    reels = [BatchReel(index=1, reel_id="REEL-2026-0025",
                       scheduled_at_local=f"{last.isoformat()} 22:00:00",
                       scheduled_at_utc=f"{last.isoformat()} 19:00:00",
                       generation_status="COMPLETE")]
    repo.save_manifest(BatchManifest(week_id="2026-W40", start_date=last.isoformat(),
                                     status="LOCKED", reels=reels))
    repo.ensure_progress_entries("2026-W40", ["REEL-2026-0025"])
    progress = repo.load_progress("2026-W40")
    progress["REEL-2026-0025"]["youtube"]["status"] = "SCHEDULED"
    repo.save_progress("2026-W40", progress)

    established = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v", dry_run=True)
    assert established._resolve_start_date() == last + datetime.timedelta(days=1)


def test_a_configured_brand_passes_the_guard():
    ready = Brand(
        brand_id="test", display_name="Test", content_mode=HIDDEN_BUILD_STORY, id_prefix="T-",
        youtube_handle="@test", youtube_channel_id="UC_test", tiktok_username="@test",
        youtube_port=9244, tiktok_port=9243, instagram_port=9245, profile_suffix="-test",
    )
    ready.ensure_publishable()


def test_a_brand_on_an_unregistered_mode_is_refused():
    bogus = Brand(
        brand_id="bogus", display_name="Bogus", content_mode="not_a_mode", id_prefix="X-",
        youtube_handle="@x", youtube_channel_id="UC_x", tiktok_username="@x",
        youtube_port=9254, tiktok_port=9253, instagram_port=9255, profile_suffix="-x",
    )
    with pytest.raises(ValueError, match="BRAND_MODE_NOT_LIVE_ELIGIBLE"):
        bogus.ensure_publishable()


def test_an_unknown_brand_id_is_rejected():
    with pytest.raises(ValueError, match="UNKNOWN_BRAND"):
        get_brand("nosuchbrand")


# ---------------------------------------------------------------- the content mode

def test_hidden_build_is_registered_and_needs_audio():
    assert is_live_eligible_mode(HIDDEN_BUILD_STORY)
    assert requires_audio(HIDDEN_BUILD_STORY)


def test_a_full_week_of_concepts_exists_without_repeats():
    assert len(HIDDEN_BUILD_CONCEPTS) >= 14
    slugs = [c.id_slug for c in HIDDEN_BUILD_CONCEPTS]
    assert len(slugs) == len(set(slugs))


def test_every_concept_has_a_surprise_and_per_beat_sound():
    for c in HIDDEN_BUILD_CONCEPTS:
        assert c.buried_object, c.id_slug
        assert c.surprise_reveal, c.id_slug
        assert c.observer, c.id_slug
        assert set(c.ambient_sounds) == {"before", "turn", "after"}, c.id_slug
        assert all(c.ambient_sounds.values()), c.id_slug


def test_a_week_selects_fourteen_distinct_concepts():
    plans = provider_for_mode(HIDDEN_BUILD_STORY).generate_plans(14, [])
    assert len(plans) == 14
    assert len({p.concept_def.id_slug for p in plans}) == 14
    assert all(p.content_mode == HIDDEN_BUILD_STORY for p in plans)
    assert all(len(p.segments) == 3 for p in plans)


def test_the_week_does_not_open_with_four_of_the_same_group():
    """A channel about "what got buried this time" cannot start with four buses."""
    plans = provider_for_mode(HIDDEN_BUILD_STORY).generate_plans(14, [])
    first_four = [p.concept_def.category_group for p in plans[:4]]
    assert len(set(first_four)) > 1


# ---------------------------------------------------------------- the two proving-run defects

def test_prompts_contain_no_cast_list_labels():
    """
    2026-08-21: a hand-written prompt listed "CRAFTSMAN:" and "NEIGHBOURS:" as labelled
    lines and Flow drew a caption box reading "CRAFTSMAN / NEIGHBOUR" into the video.
    Nothing in a generated prompt may look like a name tag.
    """
    plans = provider_for_mode(HIDDEN_BUILD_STORY).generate_plans(3, [])
    for plan in plans:
        for seg in plan.segments:
            labels = re.findall(r"^[A-Z][A-Z ]{3,}:", seg.prompt, re.M)
            assert not labels, f"{plan.concept_def.id_slug} beat {seg.index}: {labels}"


def test_on_screen_text_is_banned_including_labels():
    banned = " ".join(HiddenBuildPlanner.NEGATIVE_EXCLUSIONS)
    for term in ("captions", "written text", "on-screen labels", "name tags", "watermarks"):
        assert term in banned


def test_the_craftsman_is_identical_in_every_beat_of_every_reel():
    """His face is the profile picture on all three platforms; he cannot drift."""
    plans = provider_for_mode(HIDDEN_BUILD_STORY).generate_plans(14, [])
    for plan in plans:
        for seg in plan.segments:
            assert HiddenBuildPlanner.CRAFTSMAN in seg.prompt, plan.concept_def.id_slug


def test_the_craftsman_carries_no_drift_prone_props():
    """Distinctive accessories were the first thing to change between segments."""
    lowered = HiddenBuildPlanner.CRAFTSMAN.lower()
    for prop in ("headscarf", "hat", "flag", "logo", "badge", "glasses"):
        assert prop not in lowered


def test_the_first_two_beats_share_one_camera_and_the_third_goes_underground():
    plan = provider_for_mode(HIDDEN_BUILD_STORY).generate_plans(1, [])[0]
    beat1, beat2, beat3 = plan.segments

    def camera_of(seg):
        return next(l for l in seg.prompt.splitlines() if l.startswith("Camera:"))

    assert camera_of(beat1) == camera_of(beat2), "the repeated framing is what reads as transformation"
    assert "descend" in camera_of(beat3).lower()


def test_the_object_is_gone_before_the_reveal():
    """The surprise only works if beat 2 ends with nothing but a stairway showing."""
    plan = provider_for_mode(HIDDEN_BUILD_STORY).generate_plans(1, [])[0]
    beat2_end = next(l for l in plan.segments[1].prompt.splitlines() if l.startswith("Ends as:"))
    assert "invisible" in beat2_end
    assert "staircase" in beat2_end


def test_every_beat_bans_speech_and_asks_for_diegetic_sound():
    plan = provider_for_mode(HIDDEN_BUILD_STORY).generate_plans(1, [])[0]
    for seg in plan.segments:
        assert "Sound:" in seg.prompt
        assert "no intelligible speech" in seg.prompt.lower()
        assert "no narration" in seg.prompt.lower()


def test_the_other_two_modes_still_produce_their_own_plans():
    """Adding a third mode must not disturb the two that are already live."""
    from automation.content.content_modes import SILENT_STEP_BY_STEP

    story = provider_for_mode(NARRATIVE_AMBIENT_STORY).generate_plans(2, [])
    silent = provider_for_mode(SILENT_STEP_BY_STEP).generate_plans(2, [])

    assert all(p.content_mode == NARRATIVE_AMBIENT_STORY for p in story)
    assert all(p.content_mode == SILENT_STEP_BY_STEP for p in silent)


# ---------------------------------------------------------------- switched-off platforms

def test_the_original_channel_still_publishes_everywhere():
    assert BUILDVERSE.platforms == ("youtube", "tiktok", "instagram")
    assert BUILDVERSE.publishes_to("instagram")


def test_the_second_channel_has_instagram_switched_off():
    """Instagram's scheduling side was unusable for this account on 2026-08-21."""
    assert CRAFTSBYMAN.platforms == ("youtube", "tiktok")
    assert not CRAFTSBYMAN.publishes_to("instagram")
    assert CRAFTSBYMAN.publishes_to("youtube")
    assert CRAFTSBYMAN.publishes_to("tiktok")


def _locked_week_for(pipe, tmp_path, week_id, n=2):
    import datetime
    from automation.orchestration.batch_manifest import BatchManifest, BatchReel

    base = datetime.date.today() + datetime.timedelta(days=5)
    reels = []
    for i in range(n):
        v = tmp_path / f"v{i}.mp4"
        v.write_bytes(b"v" * 32)
        reels.append(BatchReel(
            index=i + 1, reel_id=pipe.brand.reel_id(i + 1),
            scheduled_at_local=f"{base.isoformat()} 19:30:00",
            scheduled_at_utc=f"{base.isoformat()} 16:30:00",
            video_path=str(v), generation_status="COMPLETE",
        ))
    manifest = BatchManifest(week_id=week_id, start_date=base.isoformat(),
                             status="LOCKED", reels=reels)
    pipe.batch_repo.save_manifest(manifest)
    pipe.batch_repo.ensure_progress_entries(week_id, [r.reel_id for r in reels])
    return manifest


def test_a_week_is_finished_without_the_switched_off_platform(tmp_path):
    """Otherwise the run would hold forever waiting for a platform nobody is publishing to."""
    pipe = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v",
                                dry_run=True, brand=get_brand("craftsbyman"))
    manifest = _locked_week_for(pipe, tmp_path, "CBM-2026-W40")

    progress = pipe.batch_repo.load_progress(manifest.week_id)
    for reel in manifest.reels:
        progress[reel.reel_id]["youtube"]["status"] = "SCHEDULED"
        progress[reel.reel_id]["tiktok"]["status"] = "SCHEDULED"
    pipe.batch_repo.save_progress(manifest.week_id, progress)

    assert pipe._is_batch_finished(manifest), "YouTube + TikTok done should finish this week"
    assert pipe._find_unfinished_week_id() is None


def test_the_same_week_is_unfinished_once_instagram_is_switched_back_on(tmp_path):
    """
    Re-enabling a platform must reopen past weeks so the next run completes them there --
    and only there, since the others are already done and get skipped.
    """
    import dataclasses

    pipe = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v",
                                dry_run=True, brand=get_brand("craftsbyman"))
    manifest = _locked_week_for(pipe, tmp_path, "CBM-2026-W40")
    progress = pipe.batch_repo.load_progress(manifest.week_id)
    for reel in manifest.reels:
        progress[reel.reel_id]["youtube"]["status"] = "SCHEDULED"
        progress[reel.reel_id]["tiktok"]["status"] = "SCHEDULED"
    pipe.batch_repo.save_progress(manifest.week_id, progress)

    reopened = dataclasses.replace(
        get_brand("craftsbyman"), platforms=("youtube", "tiktok", "instagram")
    )
    later = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v",
                                 dry_run=True, brand=reopened)
    assert not later._is_batch_finished(manifest)
    assert later._find_unfinished_week_id() == manifest.week_id


def test_a_disabled_platform_cannot_be_run_by_hand(tmp_path):
    """Opening a browser for an account this brand does not use is how a video misfires."""
    pipe = SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v",
                                dry_run=True, brand=get_brand("craftsbyman"))
    _locked_week_for(pipe, tmp_path, "CBM-2026-W40")

    with pytest.raises(ValueError, match="PLATFORM_DISABLED_FOR_BRAND"):
        pipe.run(phase="instagram")


# ---------------------------------------------------------------- per-brand entry points

def test_every_brand_names_files_that_exist():
    """
    The .bat names are derived from the brand id, and error messages print them. A name
    that does not exist on disk sends the operator looking for a file nobody shipped.
    """
    from pathlib import Path

    from automation.brands import BRANDS

    root = Path(__file__).resolve().parents[1]
    missing = [
        bat
        for brand in BRANDS.values()
        for bat in (brand.login_bat, brand.weekly_bat)
        if not (root / bat).exists()
    ]
    assert not missing, f"named but not shipped: {missing}"


def test_each_brand_names_its_own_files():
    """
    One shared name is what sent a dropped craftsbyman session to the first channel's
    browser on port 9223, while the session that had expired was on 9233.
    """
    from automation.brands import BRANDS

    logins = [b.login_bat for b in BRANDS.values()]
    assert len(logins) == len(set(logins)), "two brands must not share a login file"

    for brand in BRANDS.values():
        assert brand.brand_id.upper() in brand.login_bat
        assert brand.brand_id.upper() in brand.weekly_bat


def test_a_dropped_session_names_the_right_brands_file():
    """The browser managers know only a profile directory, so they resolve it back."""
    from automation.brands import get_brand, login_bat_for_profile

    for brand_id in ("buildverse", "craftsbyman"):
        brand = get_brand(brand_id)
        for profile in (brand.tiktok_profile_dir, brand.youtube_profile_dir):
            assert login_bat_for_profile(profile) == brand.login_bat


def test_login_opens_only_the_platforms_a_brand_publishes_to():
    """
    Opening a browser for a switched-off platform invites the operator to sign an account
    in somewhere it will never be used, and makes the platform look switched on.
    """
    from automation.brands import get_brand
    from automation.publishing.brand_login import PLATFORMS

    craftsbyman = get_brand("craftsbyman")
    opened = [p for p in PLATFORMS if craftsbyman.publishes_to(p)]
    assert "instagram" not in opened
    assert opened == ["youtube", "tiktok"]

    buildverse = get_brand("buildverse")
    assert [p for p in PLATFORMS if buildverse.publishes_to(p)] == list(PLATFORMS)
