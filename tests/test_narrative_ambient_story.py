"""
Regression tests for narrative_ambient_story -- the 30s real-history Reels that keep
Flow's own ambient audio.

Two properties matter most here and are covered in both directions:

1. Audio follows the Reel's content_mode. Silent Reels must still come out silent, and a
   story Reel that lost its track must be blocked rather than published as a silent
   "story". The old pipeline hardcoded silence in four places, so a one-sided test would
   pass while half the chain still stripped the audio.
2. Metadata cannot claim the wrong history. Titles are chosen per narrative_frame,
   because "Why Nobody Lives Here Anymore" is false for Gobekli Tepe (never inhabited)
   and for Lalibela (still in use).

No real browser, no Flow, no platform calls -- fakes only.
"""
import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.content.content_modes import (
    AUDIO_FORBIDDEN,
    AUDIO_REQUIRED,
    LIVE_ELIGIBLE_CONTENT_MODES,
    NARRATIVE_AMBIENT_STORY,
    SILENT_STEP_BY_STEP,
    audio_policy,
    check_audio_stream,
    is_live_eligible_mode,
    requires_audio,
)
from automation.content.concepts import CATEGORIES
from automation.content.engine import ContentEngine, StoryContentProvider
from automation.content.prompt_engine import PromptEngine
from automation.content.story_concepts import STORY_CONCEPTS, get_story_concept
from automation.orchestration.batch_manifest import BatchManifest, BatchReel, BatchRepository
from automation.publishing.eligibility import is_live_production_eligible
from automation.publishing.metadata_builder import PublishingMetadataBuilder
from automation.publishing.preflight_gate import is_placeholder_metadata
from automation.simple_weekly_pipeline import SimpleWeeklyPipeline


class FakeReelState:
    """Minimal stand-in for a persisted ReelState that passes every non-audio check."""

    def __init__(self, content_mode, reel_id="REEL-2026-9999"):
        self.reel_id = reel_id
        self.source = "flow_live_generation"
        self.pipeline_version = 3
        self.content_mode = content_mode
        self.generation_status = "COMPLETE"
        self.qc_status = "PASS"
        self.video_sha256 = None
        self.quarantine_reason = None


class FakeMeta:
    def __init__(self, has_audio, width=720, height=1280):
        self.has_audio = has_audio
        self.width = width
        self.height = height
        self.audio_codec = "aac" if has_audio else None


@pytest.fixture
def video_file(tmp_path):
    """A file that is real enough for the gate's existence and size checks."""
    f = tmp_path / "clean_REEL-2026-9999_story.mp4"
    f.write_bytes(b"NOT_REAL_MP4_BYTES" * 64)
    return f


def _patch_inspect(monkeypatch, has_audio, width=720, height=1280):
    """Point the gate's lazily-imported ffprobe at a fake, so no media is needed."""
    import automation.quality.ffprobe as ffprobe_mod

    monkeypatch.setattr(
        ffprobe_mod, "inspect_video", lambda path: FakeMeta(has_audio, width, height)
    )


# ---------------------------------------------------------------- mode registry

def test_both_modes_are_live_eligible_and_typos_are_not():
    assert is_live_eligible_mode(SILENT_STEP_BY_STEP)
    assert is_live_eligible_mode(NARRATIVE_AMBIENT_STORY)
    assert LIVE_ELIGIBLE_CONTENT_MODES == {SILENT_STEP_BY_STEP, NARRATIVE_AMBIENT_STORY}

    for bogus in ["narrative_story", "silent", "", None]:
        assert not is_live_eligible_mode(bogus)
        # Fail closed: an unrecognised mode is treated as silent-only, never as audio-ok.
        assert audio_policy(bogus) == AUDIO_FORBIDDEN


def test_audio_policy_per_mode():
    assert audio_policy(SILENT_STEP_BY_STEP) == AUDIO_FORBIDDEN
    assert audio_policy(NARRATIVE_AMBIENT_STORY) == AUDIO_REQUIRED
    assert requires_audio(NARRATIVE_AMBIENT_STORY)
    assert not requires_audio(SILENT_STEP_BY_STEP)


@pytest.mark.parametrize(
    "mode,has_audio,expected_ok",
    [
        (SILENT_STEP_BY_STEP, False, True),
        (SILENT_STEP_BY_STEP, True, False),
        (NARRATIVE_AMBIENT_STORY, True, True),
        (NARRATIVE_AMBIENT_STORY, False, False),
    ],
)
def test_check_audio_stream_both_directions(mode, has_audio, expected_ok):
    ok, reason = check_audio_stream(mode, has_audio)
    assert ok is expected_ok
    assert (reason == "") is expected_ok


# ---------------------------------------------------------------- publishing gate

@pytest.mark.parametrize(
    "mode,has_audio,expected_ok",
    [
        (SILENT_STEP_BY_STEP, False, True),
        (SILENT_STEP_BY_STEP, True, False),
        (NARRATIVE_AMBIENT_STORY, True, True),
        (NARRATIVE_AMBIENT_STORY, False, False),
    ],
)
def test_gate_enforces_audio_policy(monkeypatch, video_file, mode, has_audio, expected_ok):
    _patch_inspect(monkeypatch, has_audio)
    ok, reason = is_live_production_eligible(FakeReelState(mode), video_file)
    assert ok is expected_ok, reason
    if not expected_ok:
        assert "audio" in reason.lower()


def test_gate_rejects_unregistered_mode(monkeypatch, video_file):
    _patch_inspect(monkeypatch, True)
    ok, reason = is_live_production_eligible(FakeReelState("narrative_story"), video_file)
    assert not ok
    assert "not a registered live-eligible mode" in reason


def test_mock_resolution_still_blocks_story_reels(monkeypatch, video_file):
    """Audio support must not open a hole for mock media -- the 2026-08-16 incident."""
    _patch_inspect(monkeypatch, True, width=540, height=960)
    ok, reason = is_live_production_eligible(FakeReelState(NARRATIVE_AMBIENT_STORY), video_file)
    assert not ok
    assert "mock" in reason.lower()


# ---------------------------------------------------------------- story planning

def test_every_story_concept_is_complete():
    assert len(STORY_CONCEPTS) == len({c.id_slug for c in STORY_CONCEPTS})
    for c in STORY_CONCEPTS:
        assert c.real_basis, f"{c.id_slug} has no factual basis"
        assert set(c.ambient_sounds) == {"before", "turn", "after"}, c.id_slug
        assert all(c.ambient_sounds.values()), c.id_slug
        assert c.narrative_frame in {"abandonment", "burial", "vanishing", "creation"}, c.id_slug


def test_story_plan_has_three_beats_with_sound_and_no_narration():
    concept = get_story_concept("pompeii")
    plan = PromptEngine.build_story_concept_plan(
        concept=concept,
        env=concept.environments[0], arch=concept.architectures[0],
        transformation=concept.transformations[0], camera=concept.camera_styles[0],
        lighting=concept.lighting_schemes[0], materials=concept.materials[0],
        reveal=concept.reveals[0], diversity_score=0.9,
    )

    assert plan.content_mode == NARRATIVE_AMBIENT_STORY
    assert [s.stage_name for s in plan.segments] == ["BEFORE", "THE_TURN", "WHAT_REMAINS"]
    assert len({s.prompt_hash for s in plan.segments}) == 3

    for seg in plan.segments:
        assert "SOUND:" in seg.prompt
        assert concept.real_basis in seg.prompt
        # Ambience yes, speech no -- these Reels have no script and no voice.
        for banned in ["no narration", "no dialogue", "no intelligible speech"]:
            assert banned in seg.prompt, f"beat {seg.index} does not ban: {banned}"


def test_silent_pipeline_is_untouched():
    plan = PromptEngine.build_concept_plan(
        concept=CATEGORIES[0],
        env="empty barren plains", arch="sleek parametric glass towers",
        transformation="t", camera="c", lighting="l", materials="m", reveal="r",
        diversity_score=0.5,
    )
    assert plan.content_mode == SILENT_STEP_BY_STEP
    assert len(plan.segments) == 3
    assert not requires_audio(plan.content_mode)


def test_story_selection_is_unique_and_spread_across_groups():
    plans = ContentEngine(content_mode=NARRATIVE_AMBIENT_STORY).generate_next_reels(
        count=14, past_records=[], duration_seconds=10
    )
    assert len(plans) == 14
    assert len({p.concept_def.id_slug for p in plans}) == 14

    # Selection order is publishing order: consecutive slots must not repeat a theme.
    groups = [p.concept_def.category_group for p in plans]
    assert all(a != b for a, b in zip(groups, groups[1:])), groups
    assert len(set(groups)) >= 5, groups


def test_interleave_preserves_every_plan():
    plans = ContentEngine(content_mode=NARRATIVE_AMBIENT_STORY).generate_next_reels(
        count=27, past_records=[], duration_seconds=10
    )
    assert len(plans) == len(STORY_CONCEPTS)
    assert {p.concept_def.id_slug for p in plans} == {c.id_slug for c in STORY_CONCEPTS}


# ---------------------------------------------------------------- metadata truth

def test_titles_match_the_narrative_frame():
    """Gobekli Tepe was never inhabited; Lalibela is still in use. Neither was abandoned."""
    for slug in ["gobekli-tepe", "lalibela", "surtsey", "rapa-nui"]:
        concept = get_story_concept(slug)
        for i in range(8):
            title, _desc, _tags = PublishingMetadataBuilder.build_story_youtube_metadata(
                reel_id=f"REEL-2026-00{20 + i}",
                name=concept.name,
                category_group=concept.category_group,
                real_basis=concept.real_basis,
                topic_description=concept.topic_description,
                narrative_frame=concept.narrative_frame,
            )
            assert "Nobody Lives" not in title, f"{slug}: {title}"
            assert "Left Behind" not in title, f"{slug}: {title}"


def test_story_description_quotes_the_documented_basis():
    concept = get_story_concept("pripyat")
    title, desc, tags = PublishingMetadataBuilder.build_story_youtube_metadata(
        reel_id="REEL-2026-0025",
        name=concept.name,
        category_group=concept.category_group,
        real_basis=concept.real_basis,
        topic_description=concept.topic_description,
        narrative_frame=concept.narrative_frame,
    )
    assert concept.real_basis in desc
    assert "AI-generated" in desc, "AI disclosure must survive in the description"
    assert not is_placeholder_metadata(title, desc)
    assert "#Pripyat" in tags


def test_place_hashtag_belongs_to_the_place():
    """A group tag must never be another member's name (#Pompeii on a Kolmanskop Reel)."""
    for concept in STORY_CONCEPTS:
        _t, _d, tags = PublishingMetadataBuilder.build_story_youtube_metadata(
            reel_id=f"REEL-2026-{abs(hash(concept.id_slug)) % 9000 + 1000}",
            name=concept.name,
            category_group=concept.category_group,
            real_basis=concept.real_basis,
            topic_description=concept.topic_description,
            narrative_frame=concept.narrative_frame,
        )
        other_names = {c.name for c in STORY_CONCEPTS if c.id_slug != concept.id_slug}
        for tag in tags:
            bare = tag.lstrip("#").lower()
            for other in other_names:
                assert bare != other.replace(" ", "").replace(",", "").lower(), (
                    f"{concept.id_slug} carries another place's tag: {tag}"
                )


# ---------------------------------------------------------------- manifest & pipeline

def test_manifest_round_trips_content_mode():
    m = BatchManifest(
        week_id="2026-W35", start_date="2026-08-24",
        content_mode=NARRATIVE_AMBIENT_STORY,
        reels=[BatchReel(1, "REEL-2026-0025", "2026-08-24 19:30:00", "2026-08-24 16:30:00",
                         content_mode=NARRATIVE_AMBIENT_STORY)],
    )
    back = BatchManifest.from_dict(m.to_dict())
    assert back.content_mode == NARRATIVE_AMBIENT_STORY
    assert back.reels[0].content_mode == NARRATIVE_AMBIENT_STORY


def test_legacy_manifest_without_content_mode_defaults_to_silent():
    """W34 and earlier were written before the field existed."""
    legacy = {
        "week_id": "2026-W34", "start_date": "2026-08-17", "status": "LOCKED",
        "reels": [{"index": 1, "reel_id": "REEL-2026-0011",
                   "scheduled_at_local": "2026-08-17 19:30:00",
                   "scheduled_at_utc": "2026-08-17 16:30:00"}],
    }
    m = BatchManifest.from_dict(legacy)
    assert m.content_mode == SILENT_STEP_BY_STEP
    assert m.reels[0].content_mode == SILENT_STEP_BY_STEP


def test_pipeline_rejects_unknown_content_mode(tmp_path):
    with pytest.raises(ValueError, match="Unknown content_mode"):
        SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v",
                             dry_run=True, content_mode="narrative_story")


def test_plan_phase_builds_a_story_week(tmp_path):
    pipe = SimpleWeeklyPipeline(
        base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=True,
        start_date=datetime.date(2026, 8, 24),
        content_mode=NARRATIVE_AMBIENT_STORY,
    )
    manifest = pipe._get_or_create_manifest()

    assert manifest.week_id == "2026-W35"
    assert manifest.content_mode == NARRATIVE_AMBIENT_STORY
    assert len(manifest.reels) == 14
    assert all(r.content_mode == NARRATIVE_AMBIENT_STORY for r in manifest.reels)
    assert len({r.reel_id for r in manifest.reels}) == 14

    # Each entry must rebuild into the same story plan on a later, separate run.
    for reel in manifest.reels:
        plan = pipe._rebuild_concept_plan(reel)
        assert plan.content_mode == NARRATIVE_AMBIENT_STORY
        assert len(plan.segments) == 3
        assert plan.concept_def.id_slug == reel.concept_id_slug


def test_resuming_a_week_keeps_its_planned_mode(tmp_path):
    """A rerun with the wrong flag must not half-convert a week already in flight."""
    first = SimpleWeeklyPipeline(
        base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=True,
        start_date=datetime.date(2026, 8, 24), content_mode=NARRATIVE_AMBIENT_STORY,
    )
    manifest = first._get_or_create_manifest()

    second = SimpleWeeklyPipeline(
        base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=True,
        week_id=manifest.week_id, content_mode=SILENT_STEP_BY_STEP,
    )
    resumed = second._get_or_create_manifest()

    assert resumed.content_mode == NARRATIVE_AMBIENT_STORY
    assert second.content_mode == NARRATIVE_AMBIENT_STORY


# ---------------------------------------------------------------- continue from last

def _make_week(tmp_path, week_id, start_date, statuses, count=14):
    """Writes a LOCKED batch whose reels carry `statuses` (one dict per reel)."""
    repo = BatchRepository(tmp_path)
    reels = []
    for i in range(count):
        day = start_date + datetime.timedelta(days=i // 2)
        time_str = "19:30:00" if i % 2 == 0 else "22:00:00"
        reels.append(BatchReel(
            index=i + 1,
            reel_id=f"REEL-2026-{1000 + i}",
            scheduled_at_local=f"{day.isoformat()} {time_str}",
            scheduled_at_utc=f"{day.isoformat()} 16:30:00",
            generation_status="COMPLETE",
        ))
    manifest = BatchManifest(
        week_id=week_id, start_date=start_date.isoformat(), status="LOCKED", reels=reels
    )
    repo.save_manifest(manifest)
    repo.ensure_progress_entries(week_id, [r.reel_id for r in reels])

    progress = repo.load_progress(week_id)
    for reel, status in zip(reels, statuses):
        progress[reel.reel_id] = status
    repo.save_progress(week_id, progress)
    return manifest


def _scheduled_everywhere():
    return {
        "youtube": {"status": "SCHEDULED", "remote_id": "x", "url": "u", "error": None},
        "tiktok": {"status": "SCHEDULED", "remote_id": "x", "url": "u", "error": None},
        "instagram": {"status": "MEDIA_READY", "remote_media_id": "m", "error": None},
    }


def _nothing_published():
    return {
        "youtube": {"status": "PENDING", "remote_id": None, "url": None, "error": None},
        "tiktok": {"status": "PENDING", "remote_id": None, "url": None, "error": None},
        "instagram": {"status": "PENDING", "remote_media_id": None, "error": None},
    }


def _pipeline(tmp_path, **kwargs):
    return SimpleWeeklyPipeline(
        base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=True,
        content_mode=NARRATIVE_AMBIENT_STORY, **kwargs
    )


def test_last_scheduled_date_is_the_latest_published_slot(tmp_path):
    _make_week(tmp_path, "2026-W34", datetime.date(2026, 8, 17), [_scheduled_everywhere()] * 14)
    assert _pipeline(tmp_path).find_last_scheduled_date() == datetime.date(2026, 8, 23)


def test_unpublished_slots_do_not_occupy_their_dates(tmp_path):
    """A week that was planned but never reached a platform must not push the start date."""
    _make_week(tmp_path, "2026-W34", datetime.date(2026, 8, 17), [_scheduled_everywhere()] * 14)
    _make_week(tmp_path, "2026-W40", datetime.date(2026, 9, 28), [_nothing_published()] * 14)

    assert _pipeline(tmp_path).find_last_scheduled_date() == datetime.date(2026, 8, 23)


def test_partially_published_week_counts_only_what_landed(tmp_path):
    statuses = [_scheduled_everywhere()] * 6 + [_nothing_published()] * 8
    _make_week(tmp_path, "2026-W34", datetime.date(2026, 8, 17), statuses)

    # Reels 1-6 cover 17-19 August; the rest never went anywhere.
    assert _pipeline(tmp_path).find_last_scheduled_date() == datetime.date(2026, 8, 19)


def test_start_date_is_the_day_after_the_last_scheduled_video(tmp_path, monkeypatch):
    _make_week(tmp_path, "2026-W34", datetime.date(2026, 8, 17), [_scheduled_everywhere()] * 14)
    pipe = _pipeline(tmp_path)
    assert pipe._resolve_start_date() == datetime.date(2026, 8, 24)


def test_start_date_never_lands_in_the_past(tmp_path):
    """An old batch must not schedule a new week into dates that have already gone by."""
    _make_week(tmp_path, "2020-W10", datetime.date(2020, 3, 2), [_scheduled_everywhere()] * 14)
    pipe = _pipeline(tmp_path)
    resolved = pipe._resolve_start_date()
    assert resolved > datetime.date.today()


def test_explicit_start_date_wins(tmp_path):
    _make_week(tmp_path, "2026-W34", datetime.date(2026, 8, 17), [_scheduled_everywhere()] * 14)
    pipe = _pipeline(tmp_path, start_date=datetime.date(2026, 12, 7))
    assert pipe._resolve_start_date() == datetime.date(2026, 12, 7)


def test_first_ever_run_falls_back_to_the_calendar(tmp_path):
    pipe = _pipeline(tmp_path)
    assert pipe.find_last_scheduled_date() is None
    assert pipe._resolve_start_date() > datetime.date.today()


def test_new_week_starts_where_the_last_one_ended(tmp_path):
    _make_week(tmp_path, "2026-W34", datetime.date(2026, 8, 17), [_scheduled_everywhere()] * 14)
    manifest = _pipeline(tmp_path)._get_or_create_manifest()

    assert manifest.start_date == "2026-08-24"
    assert manifest.reels[0].scheduled_at_local == "2026-08-24 19:30:00"
    assert manifest.reels[-1].scheduled_at_local == "2026-08-30 22:00:00"
    # No date may be reused from the finished week.
    assert all(r.scheduled_at_local > "2026-08-23 22:00:00" for r in manifest.reels)


# ---------------------------------------------------------------- generate fail-fast

class _ExplodingProvider:
    """Fails every Reel the same way, counting how many times it was asked."""

    def __init__(self, message="QC_FAILED: AUDIO_MISSING: no audio stream"):
        self.calls = 0
        self.message = message

    def generate_single_video(self, plan, reel_id, target_filename, **kwargs):
        self.calls += 1
        raise RuntimeError(self.message)


def test_generate_stops_after_the_same_failure_repeats(tmp_path):
    """Flow returning silent renders must not burn credits on all 14 Reels."""
    pipe = _pipeline(tmp_path, start_date=datetime.date(2026, 8, 24))
    provider = _ExplodingProvider()
    pipe.flow_provider = provider

    manifest = pipe._get_or_create_manifest()
    result = pipe._run_generate_phase(manifest)

    assert not result.success
    assert result.detail["stopped_early"] is True
    assert "AUDIO_MISSING" in result.detail["repeated_failure"]
    assert provider.calls == SimpleWeeklyPipeline.MAX_CONSECUTIVE_SAME_FAILURES
    assert sum(1 for r in manifest.reels if r.generation_status == "FAILED") == 2


def test_failure_signature_groups_the_same_cause(tmp_path):
    sig = SimpleWeeklyPipeline._failure_signature
    a = sig(RuntimeError("QC_FAILED: AUDIO_MISSING: ambient audio required but REEL-1 has none"))
    b = sig(RuntimeError("QC_FAILED: AUDIO_MISSING: ambient audio required but REEL-2 has none"))
    c = sig(RuntimeError("FLOW_TIMEOUT: segment 2 never finished"))
    assert a == b, "same cause on different Reels must share a signature"
    assert a != c
