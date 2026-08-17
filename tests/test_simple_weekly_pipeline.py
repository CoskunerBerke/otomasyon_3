"""
Consolidated regression suite for automation/simple_weekly_pipeline.py -- the new
deterministic, sequential, single-direction production entrypoint that replaces
weekly_orchestrator.py for live weekly execution.

Covers: manifest/Reel ID allocation, generate->lock->youtube->tiktok->instagram
phase gating, fail-fast + resume semantics, LOCKED-manifest immutability, and
production-media-guardian's eligibility/placeholder/hard-excluded rules as applied
inside this new pipeline.

Strictly mocks/fakes only: 0 real browsers, 0 real Flow generation, 0 real platform calls.
"""
import datetime
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from automation.simple_weekly_pipeline import SimpleWeeklyPipeline
from automation.orchestration.batch_manifest import BatchRepository, BatchReel, BatchManifest
from automation.orchestration.state_repository import StateRepository
from automation.orchestration.models import ReelState, ReelProvenance
from automation.publishing.models import PlatformPublicationStatus


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _fake_flow_provider(dl_dir: Path, content: bytes = b"real video bytes" * 200) -> MagicMock:
    mock_flow = MagicMock()

    def fake_generate(plan, reel_id, target_filename, **kwargs):
        p = dl_dir / target_filename
        p.write_bytes(content)
        return p

    mock_flow.generate_single_video.side_effect = fake_generate
    return mock_flow


def _ok_publisher() -> MagicMock:
    mock = MagicMock()

    def side_effect(rec):
        rec.status = PlatformPublicationStatus.SCHEDULED
        rec.remote_id = f"remote_{rec.reel_id}"
        rec.remote_url = f"https://example.com/{rec.reel_id}"
        rec.last_error = None
        return rec

    mock.upload_and_schedule.side_effect = side_effect
    return mock


def _ok_cloud_client() -> MagicMock:
    mock = MagicMock()
    mock.upload_media_for_instagram.return_value = (
        True, {"ok": True, "status": "MEDIA_READY", "media_object_key": "media/x.mp4"}, None
    )
    return mock


def _patched_validator():
    """Context manager patching VideoValidator to always pass QC on whatever file was written."""
    return patch(
        "automation.simple_weekly_pipeline.VideoValidator",
        return_value=MagicMock(process_and_validate=MagicMock(
            side_effect=lambda input_video, output_dir: MagicMock(is_passed=True, processed_video_path=input_video)
        )),
    )


def _make_pipeline(tmp_path, dry_run=False, week_id="2026-W99", **kwargs):
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    defaults = dict(
        base_dir=tmp_path,
        vault_path=tmp_path / "vault",
        dry_run=dry_run,
        week_id=week_id,
        start_date=datetime.date(2026, 8, 17),
        flow_provider=_fake_flow_provider(dl_dir),
        yt_publisher=_ok_publisher(),
        tt_publisher=_ok_publisher(),
        cloud_client=_ok_cloud_client(),
    )
    defaults.update(kwargs)
    return SimpleWeeklyPipeline(**defaults), dl_dir


def _run_full_happy_path(tmp_path, **kwargs):
    pipeline, dl_dir = _make_pipeline(tmp_path, **kwargs)
    with _patched_validator():
        success, results, manifest = pipeline.run()
    return pipeline, success, results, manifest


# ---------------------------------------------------------------------------
# 1-3: Manifest / plan creation
# ---------------------------------------------------------------------------

def test_plan_creates_14_unique_reels_with_correct_slot_times(tmp_path):
    pipeline, _dl = _make_pipeline(tmp_path, dry_run=True)
    manifest = pipeline._get_or_create_manifest()

    assert len(manifest.reels) == 14
    ids = [r.reel_id for r in manifest.reels]
    assert len(set(ids)) == 14

    times = sorted(set(r.scheduled_at_local.split()[1] for r in manifest.reels))
    assert times == ["19:30:00", "22:00:00"]


def test_reel_id_allocation_skips_already_used_ids(tmp_path):
    repo = StateRepository(tmp_path)
    for i in range(11, 20):
        repo.save_reel_state(ReelState(reel_id=f"REEL-2026-{i:04d}", source=ReelProvenance.FLOW_LIVE_GENERATION.value))

    pipeline, _dl = _make_pipeline(tmp_path, dry_run=True)
    allocated = pipeline._allocate_reel_ids(count=5)

    assert not (set(allocated) & {f"REEL-2026-{i:04d}" for i in range(11, 20)})
    assert "REEL-2026-0010" not in allocated
    assert "REEL-2026-0001" not in allocated
    assert len(set(allocated)) == 5


# ---------------------------------------------------------------------------
# 5-7: Generation gating and LOCK
# ---------------------------------------------------------------------------

def test_youtube_never_starts_before_generation_complete(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path)
    # Break generation for one reel so 14/14 is never reached.
    call_count = {"n": 0}

    def flaky_generate(plan, reel_id, target_filename, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 5:
            raise RuntimeError("Flow generation failed for this reel")
        p = dl_dir / target_filename
        p.write_bytes(b"x" * 500)
        return p

    pipeline.flow_provider.generate_single_video.side_effect = flaky_generate

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert success is False
    assert results[0].phase == "GENERATE"
    assert manifest.status == "DRAFT"
    pipeline.yt_publisher.upload_and_schedule.assert_not_called()


def test_manifest_locks_only_after_all_14_generated(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path)
    with _patched_validator():
        pipeline._get_or_create_manifest()
        manifest = pipeline.batch_repo.load_manifest(pipeline.week_id)
        assert manifest.status == "DRAFT"
        pipeline._run_generate_phase(manifest)
        assert pipeline.all_generated(manifest)
        result = pipeline._run_validate_and_lock_phase(manifest)
    assert result.success is True
    assert manifest.status == "LOCKED"


def test_locked_manifest_reel_mapping_is_immutable_on_reload(tmp_path):
    pipeline, success, results, manifest = _run_full_happy_path(tmp_path)
    original_ids = [r.reel_id for r in manifest.reels]
    original_videos = [r.video_path for r in manifest.reels]

    # A brand new pipeline instance (simulating a fresh process) must load the exact
    # same locked content plan, never regenerate or reassign it.
    pipeline2, _dl2 = _make_pipeline(tmp_path, week_id=pipeline.week_id)
    reloaded = pipeline2._get_or_create_manifest()

    assert reloaded.status == "LOCKED"
    assert [r.reel_id for r in reloaded.reels] == original_ids
    assert [r.video_path for r in reloaded.reels] == original_videos
    pipeline2.flow_provider.generate_single_video.assert_not_called()


# ---------------------------------------------------------------------------
# 8-12: YouTube sequential / fail-fast / skip / resume
# ---------------------------------------------------------------------------

def test_youtube_processes_reels_in_manifest_order(tmp_path):
    pipeline, success, results, manifest = _run_full_happy_path(tmp_path)
    called_ids = [c.args[0].reel_id for c in pipeline.yt_publisher.upload_and_schedule.call_args_list]
    assert called_ids == [r.reel_id for r in manifest.reels]


def test_youtube_skips_already_scheduled_reels(tmp_path):
    pipeline, success, results, manifest = _run_full_happy_path(tmp_path)
    assert success is True
    assert pipeline.yt_publisher.upload_and_schedule.call_count == 14

    # Re-run with a fresh publisher mock: nothing should be re-uploaded.
    pipeline2, _dl2 = _make_pipeline(tmp_path, week_id=pipeline.week_id)
    with _patched_validator():
        pipeline2.run()
    pipeline2.yt_publisher.upload_and_schedule.assert_not_called()


def test_youtube_resume_carries_remote_id_from_progress(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path)
    with _patched_validator():
        manifest = pipeline._get_or_create_manifest()
        pipeline._run_generate_phase(manifest)
        pipeline._run_validate_and_lock_phase(manifest)

    first_reel = manifest.reels[0]
    pipeline.batch_repo.update_platform_status(
        manifest.week_id, first_reel.reel_id, "youtube", "FAILED_RETRYABLE",
        remote_id="existing_draft_123", url="https://youtube.com/shorts/existing_draft_123",
    )

    captured = {}
    def capture(rec):
        if rec.reel_id == first_reel.reel_id:
            captured["remote_id"] = rec.remote_id
            captured["upload_started"] = rec.upload_started
        rec.status = PlatformPublicationStatus.SCHEDULED
        rec.remote_id = rec.remote_id or f"remote_{rec.reel_id}"
        return rec
    pipeline.yt_publisher.upload_and_schedule.side_effect = capture

    pipeline._run_youtube_phase(manifest)
    assert captured["remote_id"] == "existing_draft_123"
    assert captured["upload_started"] is True


def test_youtube_hard_failure_stops_remaining_youtube_reels(tmp_path):
    """A broken session (ACCOUNT_MISMATCH) must stop the rest of the YouTube queue,
    because continuing would cascade the same failure into every remaining Reel."""
    pipeline, dl_dir = _make_pipeline(tmp_path)
    n = {"i": 0}

    def fail_third(rec):
        n["i"] += 1
        if n["i"] == 3:
            rec.status = PlatformPublicationStatus.ACCOUNT_MISMATCH
            rec.last_error = "ACCOUNT_MISMATCH: test"
            return rec
        rec.status = PlatformPublicationStatus.SCHEDULED
        rec.remote_id = f"remote_{rec.reel_id}"
        return rec
    pipeline.yt_publisher.upload_and_schedule.side_effect = fail_third

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert success is False
    assert pipeline.yt_publisher.upload_and_schedule.call_count == 3
    yt = next(r for r in results if r.phase == "YOUTUBE")
    assert yt.detail["failed_reel"] == manifest.reels[2].reel_id
    assert yt.detail.get("hard_stop") is True


def test_youtube_failure_does_not_block_other_platforms(tmp_path):
    """Platforms are independent once the manifest is LOCKED -- the same 14 videos go to
    the same slots everywhere, so a YouTube problem is no reason to skip TikTok/Instagram."""
    pipeline, dl_dir = _make_pipeline(tmp_path)
    pipeline.yt_publisher.upload_and_schedule.side_effect = lambda rec: (
        setattr(rec, "status", PlatformPublicationStatus.ACCOUNT_MISMATCH),
        setattr(rec, "last_error", "boom"),
        rec,
    )[2]

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert success is False
    assert pipeline.tt_publisher.upload_and_schedule.call_count == 14
    assert pipeline.cloud_client.upload_media_for_instagram.call_count == 14


# ---------------------------------------------------------------------------
# 13-17: TikTok sequencing and platform independence
# ---------------------------------------------------------------------------

def test_tiktok_runs_even_if_youtube_not_fully_verified(tmp_path):
    """An unverified (soft) YouTube result must not hold TikTok back."""
    pipeline, dl_dir = _make_pipeline(tmp_path)
    n = {"i": 0}

    def soft_on_last(rec):
        n["i"] += 1
        if n["i"] == 14:
            rec.status = PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
            rec.last_error = "not verified"
            return rec
        rec.status = PlatformPublicationStatus.SCHEDULED
        rec.remote_id = f"remote_{rec.reel_id}"
        return rec
    pipeline.yt_publisher.upload_and_schedule.side_effect = soft_on_last

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert pipeline.yt_publisher.upload_and_schedule.call_count == 14
    assert pipeline.tt_publisher.upload_and_schedule.call_count == 14


def test_tiktok_processes_reels_in_manifest_order(tmp_path):
    pipeline, success, results, manifest = _run_full_happy_path(tmp_path)
    called_ids = [c.args[0].reel_id for c in pipeline.tt_publisher.upload_and_schedule.call_args_list]
    assert called_ids == [r.reel_id for r in manifest.reels]


def test_tiktok_hard_failure_stops_tiktok_but_instagram_still_runs(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path)
    n = {"i": 0}

    def fail_fifth(rec):
        n["i"] += 1
        if n["i"] == 5:
            rec.status = "NEEDS_USER_HTML"
            rec.last_error = "Rule 31"
            return rec
        rec.status = PlatformPublicationStatus.SCHEDULED
        return rec
    pipeline.tt_publisher.upload_and_schedule.side_effect = fail_fifth

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert success is False
    assert pipeline.tt_publisher.upload_and_schedule.call_count == 5
    tt = next(r for r in results if r.phase == "TIKTOK")
    assert tt.detail.get("hard_stop") is True
    assert pipeline.cloud_client.upload_media_for_instagram.call_count == 14


def test_generation_gate_still_blocks_all_publishing(tmp_path):
    """The ONE gate that must never loosen: nothing publishes until 14/14 real videos
    exist and the manifest is LOCKED."""
    pipeline, dl_dir = _make_pipeline(tmp_path)

    def flaky(plan, reel_id, target_filename, **kwargs):
        if reel_id.endswith("0015"):
            raise RuntimeError("Flow failed")
        p = dl_dir / target_filename
        p.write_bytes(b"x" * 500)
        return p
    pipeline.flow_provider.generate_single_video.side_effect = flaky

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert success is False
    assert manifest.status == "DRAFT"
    pipeline.yt_publisher.upload_and_schedule.assert_not_called()
    pipeline.tt_publisher.upload_and_schedule.assert_not_called()
    pipeline.cloud_client.upload_media_for_instagram.assert_not_called()


# ---------------------------------------------------------------------------
# 18-19, 24-26: Instagram uses locked manifest; metadata/manifest immutability
# ---------------------------------------------------------------------------

def test_instagram_handoff_uses_locked_manifest_video_and_metadata(tmp_path):
    pipeline, success, results, manifest = _run_full_happy_path(tmp_path)
    assert success is True

    first_call_kwargs = pipeline.cloud_client.upload_media_for_instagram.call_args_list[0].kwargs
    first_reel = manifest.reels[0]
    assert first_call_kwargs["local_path"] == Path(first_reel.video_path)
    assert first_reel.caption in first_call_kwargs["caption"]


def test_file_not_referenced_by_manifest_is_never_published(tmp_path):
    """A stray file dropped in workspace/downloads/ (e.g. leftover mock/test output)
    must never be picked up -- only manifest.reels[i].video_path is ever touched."""
    pipeline, dl_dir = _make_pipeline(tmp_path)
    (dl_dir / "clean_REEL-2026-9999_intruder.mp4").write_bytes(b"MOCK_INTRUDER" * 100)

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert success is True
    published_paths = {Path(c.args[0].video_file).name for c in pipeline.yt_publisher.upload_and_schedule.call_args_list}
    assert "clean_REEL-2026-9999_intruder.mp4" not in published_paths
    assert "REEL-2026-9999" not in {r.reel_id for r in manifest.reels}


def test_metadata_unchanged_between_generate_and_publish(tmp_path):
    pipeline, success, results, manifest = _run_full_happy_path(tmp_path)
    assert success is True
    first_reel = manifest.reels[0]
    sent_rec = pipeline.yt_publisher.upload_and_schedule.call_args_list[0].args[0]
    assert sent_rec.title == first_reel.title
    assert sent_rec.description == first_reel.caption
    assert sent_rec.hashtags == first_reel.hashtags


def test_progress_update_does_not_mutate_manifest_content(tmp_path):
    pipeline, success, results, manifest = _run_full_happy_path(tmp_path)
    manifest_before = pipeline.batch_repo.load_manifest(pipeline.week_id)
    ids_before = [r.reel_id for r in manifest_before.reels]
    titles_before = [r.title for r in manifest_before.reels]

    pipeline.batch_repo.update_platform_status(pipeline.week_id, manifest.reels[0].reel_id, "youtube", "PUBLISHED")

    manifest_after = pipeline.batch_repo.load_manifest(pipeline.week_id)
    assert [r.reel_id for r in manifest_after.reels] == ids_before
    assert [r.title for r in manifest_after.reels] == titles_before


def test_reel_id_never_assigned_to_two_slots(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path, dry_run=True)
    manifest = pipeline._get_or_create_manifest()
    ids = [r.reel_id for r in manifest.reels]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# 20-22: Mock/quarantined/hard-excluded media rejection at LOCK
# ---------------------------------------------------------------------------

def test_lock_rejects_mock_provenance_media(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path, dry_run=True)
    manifest = pipeline._get_or_create_manifest()
    reel = manifest.reels[0]

    video = dl_dir / "clean_mock.mp4"
    video.write_bytes(b"MOCK_MP4_SEGMENT_BYTES" * 20)
    reel.video_path = str(video.resolve())
    reel.video_sha256 = hashlib.sha256(video.read_bytes()).hexdigest()
    reel.generation_status = "COMPLETE"
    for r in manifest.reels[1:]:
        r.generation_status = "FAILED"  # irrelevant to this check, just avoid confusion

    pipeline.state_repo.save_reel_state(ReelState(
        reel_id=reel.reel_id, source=ReelProvenance.MOCK_TEST_PROVIDER.value,
        generation_status="COMPLETE", qc_status="PASS",
        video_path=reel.video_path, video_sha256=reel.video_sha256,
    ))

    result = pipeline._run_validate_and_lock_phase(manifest)
    assert result.success is False
    assert manifest.status == "DRAFT"


def test_lock_rejects_hard_excluded_reel_ids(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path, dry_run=True)
    manifest = pipeline._get_or_create_manifest()
    for bad_id in ("REEL-2026-0001", "REEL-2026-0010"):
        manifest.reels[0].reel_id = bad_id
        video = dl_dir / f"clean_{bad_id}_x.mp4"
        video.write_bytes(b"x" * 500)
        manifest.reels[0].video_path = str(video.resolve())
        manifest.reels[0].video_sha256 = hashlib.sha256(video.read_bytes()).hexdigest()
        manifest.reels[0].generation_status = "COMPLETE"
        pipeline.state_repo.save_reel_state(ReelState(
            reel_id=bad_id, source=ReelProvenance.FLOW_LIVE_GENERATION.value,
            generation_status="COMPLETE", qc_status="PASS",
            video_path=manifest.reels[0].video_path, video_sha256=manifest.reels[0].video_sha256,
        ))
        result = pipeline._run_validate_and_lock_phase(manifest)
        assert result.success is False, f"{bad_id} should be rejected at LOCK"


# ---------------------------------------------------------------------------
# 27-28: dry-run isolation, Obsidian failure tolerance
# ---------------------------------------------------------------------------

def test_dry_run_never_touches_real_publisher_classes(tmp_path):
    """dry_run=True must lazily construct Mock* adapters, never the real
    GoogleFlowWebProvider/YouTubeStudioPublisher/TikTokPublisher classes. Exercises the
    lazy-init methods directly rather than a full pipeline.run() cascade, since the real
    Mock* classes construct fine on their own without needing a real ffmpeg binary on
    PATH (which a full GENERATE phase would require)."""
    pipeline, dl_dir = _make_pipeline(tmp_path, dry_run=True, flow_provider=None, yt_publisher=None, tt_publisher=None, cloud_client=None)

    pipeline._init_flow_provider_if_needed()
    pipeline._init_youtube_publisher_if_needed()
    pipeline._init_tiktok_publisher_if_needed()

    from automation.publishing.youtube_studio_publisher import MockYouTubeStudioPublisher, YouTubeStudioPublisher
    from automation.publishing.tiktok_publisher import MockTikTokPublisher, TikTokPublisher
    from automation.flow.generator import MockVideoProvider, GoogleFlowWebProvider
    assert isinstance(pipeline.flow_provider, MockVideoProvider)
    assert not isinstance(pipeline.flow_provider, GoogleFlowWebProvider)
    assert isinstance(pipeline.yt_publisher, MockYouTubeStudioPublisher)
    assert not isinstance(pipeline.yt_publisher, YouTubeStudioPublisher)
    assert isinstance(pipeline.tt_publisher, MockTikTokPublisher)
    assert not isinstance(pipeline.tt_publisher, TikTokPublisher)


def test_obsidian_sync_failure_does_not_break_pipeline(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path)
    pipeline.obsidian.sync_reel_note = MagicMock(side_effect=Exception("disk full"))

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert success is True
    assert manifest.status == "LOCKED"


# ---------------------------------------------------------------------------
# 29: W34-style migration preserves remote evidence (synthetic scenario, mirroring
# the real 2026-08-17 migration without depending on this machine's local files)
# ---------------------------------------------------------------------------

def test_migrating_existing_real_state_preserves_remote_evidence(tmp_path):
    repo = StateRepository(tmp_path)
    batch_repo = BatchRepository(tmp_path)
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)

    video = dl_dir / "clean_REEL-2026-0011_example.mp4"
    video.write_bytes(b"real bytes" * 200)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()

    # Simulate a pre-existing real Reel with partial remote evidence, exactly like
    # REEL-2026-0011's real state on 2026-08-17 (YouTube draft uploaded but not
    # scheduled, TikTok confirmed scheduled).
    reel_state = ReelState(
        reel_id="REEL-2026-0011", pipeline_version=3, content_mode="silent_global_step_by_step",
        generation_status="COMPLETE", qc_status="PASS", video_path=str(video.resolve()), video_sha256=sha,
        source=ReelProvenance.FLOW_LIVE_GENERATION.value, title="Real Title", caption="Real caption", hashtags=["#Shorts"],
    )
    repo.save_reel_state(reel_state)

    manifest = BatchManifest(
        week_id="2026-W34", start_date="2026-08-17", status="DRAFT", target_reels=1,
        reels=[BatchReel(
            index=1, reel_id="REEL-2026-0011", scheduled_at_local="2026-08-17 19:30:00",
            scheduled_at_utc="2026-08-17 16:30:00", title="Real Title", caption="Real caption",
            hashtags=["#Shorts"], video_path=str(video.resolve()), video_sha256=sha,
            generation_status="COMPLETE", concept_id_slug="futuristic-city", environment="e", architecture="a",
            transformation="t", camera_style="c", lighting="l", materials="m", reveal="r",
        )],
    )
    batch_repo.save_manifest(manifest)
    batch_repo.update_platform_status(
        "2026-W34", "REEL-2026-0011", "youtube", "FAILED_RETRYABLE",
        remote_id="a9RnSvejU2Q", url="https://youtube.com/shorts/a9RnSvejU2Q",
        error="UPLOADED_DRAFT but schedule not confirmed",
    )
    batch_repo.update_platform_status("2026-W34", "REEL-2026-0011", "tiktok", "SCHEDULED", error="Confirmed via manual review")

    progress = batch_repo.load_progress("2026-W34")
    assert progress["REEL-2026-0011"]["youtube"]["remote_id"] == "a9RnSvejU2Q"
    assert progress["REEL-2026-0011"]["tiktok"]["status"] == "SCHEDULED"

    # A resume run must never re-upload YouTube (has draft evidence) or re-schedule
    # TikTok (already SCHEDULED).
    pipeline = SimpleWeeklyPipeline(
        base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=False, week_id="2026-W34",
        start_date=datetime.date(2026, 8, 17),
        yt_publisher=_ok_publisher(), tt_publisher=_ok_publisher(), cloud_client=_ok_cloud_client(),
    )
    pipeline._run_validate_and_lock_phase(manifest)
    assert pipeline.all_platform_done("2026-W34", ["REEL-2026-0011"], "tiktok") is True

    # Capture the incoming remote_id/upload_started *before* the mock mutates the same
    # PublishRecord object in place -- call_args_list holds a reference, not a copy, so
    # inspecting it after the call would see the post-mutation state instead.
    captured = {}
    def capture(rec):
        captured["remote_id"] = rec.remote_id
        captured["upload_started"] = rec.upload_started
        rec.status = PlatformPublicationStatus.SCHEDULED
        rec.remote_id = rec.remote_id or f"remote_{rec.reel_id}"
        return rec
    pipeline.yt_publisher.upload_and_schedule.side_effect = capture

    pipeline._run_youtube_phase(manifest)
    assert captured["remote_id"] == "a9RnSvejU2Q"
    assert captured["upload_started"] is True


# ---------------------------------------------------------------------------
# 30: phase resume picks up from the correct phase
# ---------------------------------------------------------------------------

def test_pipeline_resumes_from_correct_phase_across_runs(tmp_path):
    week_id = "2026-W99"
    pipeline1, dl_dir = _make_pipeline(tmp_path, week_id=week_id)
    with _patched_validator():
        pipeline1._get_or_create_manifest()
        manifest = pipeline1.batch_repo.load_manifest(week_id)
        pipeline1._run_generate_phase(manifest)
    assert pipeline1.all_generated(manifest)
    assert manifest.status == "DRAFT"

    # Next invocation (fresh pipeline object) must go straight to LOCK, not GENERATE.
    pipeline2, _dl2 = _make_pipeline(tmp_path, week_id=week_id)
    with _patched_validator():
        success, results, manifest2 = pipeline2.run()

    assert success is True
    assert results[0].phase == "LOCK"
    pipeline2.flow_provider.generate_single_video.assert_not_called()


# ---------------------------------------------------------------------------
# Order independence, soft-failure tolerance, and Telegram completion notice
# (2026-08-17: a correctly-scheduled Short was reported unverified because the
# check looked at the wrong Studio tab, and that single false negative halted
# all three platforms for the whole week.)
# ---------------------------------------------------------------------------

def _status_publisher(status, last_error=None):
    mock = MagicMock()

    def side_effect(rec):
        rec.status = status
        rec.last_error = last_error
        rec.remote_id = f"remote_{rec.reel_id}"
        return rec

    mock.upload_and_schedule.side_effect = side_effect
    return mock


def test_soft_failure_does_not_stop_remaining_reels(tmp_path):
    """An inconclusive verification (submit went through) must keep processing the rest."""
    pipeline, dl_dir = _make_pipeline(tmp_path)
    n = {"i": 0}

    def soft_on_third(rec):
        n["i"] += 1
        if n["i"] == 3:
            rec.status = PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
            rec.last_error = "REMOTE_SCHEDULE_NOT_VERIFIED"
            return rec
        rec.status = PlatformPublicationStatus.SCHEDULED
        rec.remote_id = f"remote_{rec.reel_id}"
        return rec

    pipeline.yt_publisher.upload_and_schedule.side_effect = soft_on_third

    with _patched_validator():
        success, results, manifest = pipeline.run()

    # All 14 were still attempted despite the soft failure on #3.
    assert pipeline.yt_publisher.upload_and_schedule.call_count == 14
    yt = next(r for r in results if r.phase == "YOUTUBE")
    assert yt.detail.get("hard_stop") is False
    assert manifest.reels[2].reel_id in yt.detail["soft_failures"]


def test_soft_failure_still_runs_other_platforms(tmp_path):
    """YouTube being unverified must not block TikTok or the Instagram handoff."""
    pipeline, dl_dir = _make_pipeline(tmp_path)
    pipeline.yt_publisher = _status_publisher(
        PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED, "REMOTE_SCHEDULE_NOT_VERIFIED"
    )

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert pipeline.tt_publisher.upload_and_schedule.call_count == 14
    assert pipeline.cloud_client.upload_media_for_instagram.call_count == 14


def test_hard_failure_stops_its_platform_but_not_the_others(tmp_path):
    """A broken session (ACCOUNT_MISMATCH) stops that platform only."""
    pipeline, dl_dir = _make_pipeline(tmp_path)
    pipeline.yt_publisher = _status_publisher(PlatformPublicationStatus.ACCOUNT_MISMATCH, "wrong channel")

    with _patched_validator():
        success, results, manifest = pipeline.run()

    assert success is False
    assert pipeline.yt_publisher.upload_and_schedule.call_count == 1  # stopped immediately
    yt = next(r for r in results if r.phase == "YOUTUBE")
    assert yt.detail.get("hard_stop") is True
    # Other platforms still ran.
    assert pipeline.tt_publisher.upload_and_schedule.call_count == 14
    assert pipeline.cloud_client.upload_media_for_instagram.call_count == 14


def test_telegram_completion_message_sent_on_success(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path)
    sent = {}

    class _FakeBot:
        def __init__(self, token):
            sent["token_used"] = bool(token)

        def send_message(self, chat_id, text):
            sent["chat_id"] = chat_id
            sent["text"] = text
            return True, 1, None

    fake_cfg = MagicMock()
    fake_cfg.telegram_bot_token = "dummy-token"
    fake_cfg.telegram_chat_id = 12345

    with _patched_validator(), \
         patch("automation.cloud.config.CloudConfig", return_value=fake_cfg), \
         patch("automation.cloud.telegram_bot.TelegramBotClient", _FakeBot):
        success, results, manifest = pipeline.run()

    assert success is True
    assert sent["chat_id"] == 12345
    assert "TAMAMLANDI" in sent["text"]
    assert "YouTube : 14/14" in sent["text"]


def test_telegram_failure_never_breaks_pipeline(tmp_path):
    pipeline, dl_dir = _make_pipeline(tmp_path)

    with _patched_validator(), \
         patch("automation.cloud.config.CloudConfig", side_effect=Exception("no config")):
        success, results, manifest = pipeline.run()

    assert success is True
