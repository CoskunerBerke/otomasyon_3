"""
Regression tests for two ways a week quietly loses slots.

1. A new week always began tomorrow. Both of today's slots were thrown away even when
   the run started at breakfast and the whole day was still ahead -- a seventh of the
   week gone for nothing, and the reason a morning run published nothing until the
   following evening.

2. --dry-run wrote its mock results into the real progress.json. The mock publishers
   return SCHEDULED with an invented remote id, the publishing phases record whatever a
   publisher hands back, and SCHEDULED is exactly what the "already done, skip" test
   looks for. Rehearsing a live week would therefore have made the next live run skip
   every Reel in it, leaving the slots empty while the state file claimed the week was
   finished. The repo's own .bat advertised --dry-run as the safe option.
"""
import datetime
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.simple_weekly_pipeline import (
    DAILY_SLOT_TIMES,
    SAME_DAY_START_LEAD_HOURS,
    SimpleWeeklyPipeline,
)
from automation.orchestration.slot_generator import get_timezone

TZ = get_timezone("Europe/Istanbul")


def _at(hour, minute=0, day=22):
    return datetime.datetime(2026, 8, day, hour, minute, tzinfo=TZ)


def _earliest(now):
    return SimpleWeeklyPipeline.__new__(SimpleWeeklyPipeline)._earliest_usable_start(now)


# ---------------------------------------------------------------- start date

def test_a_day_that_has_not_started_yet_is_used():
    """The complaint that prompted this: the day is not over, so its slots still count."""
    assert _earliest(_at(8, 0)) == datetime.date(2026, 8, 22)


def test_a_day_whose_first_slot_is_too_close_is_skipped():
    """Scheduling into a moment that passes mid-run is worse than starting tomorrow."""
    assert _earliest(_at(18, 0)) == datetime.date(2026, 8, 23)


def test_a_day_whose_slots_have_passed_is_skipped():
    assert _earliest(_at(23, 30)) == datetime.date(2026, 8, 23)


def test_the_boundary_is_the_declared_lead_time():
    hour, minute = (int(p) for p in DAILY_SLOT_TIMES[0].split(":"))
    first_slot = _at(hour, minute)
    exactly = first_slot - datetime.timedelta(hours=SAME_DAY_START_LEAD_HOURS)

    assert _earliest(exactly) == datetime.date(2026, 8, 22)
    assert _earliest(exactly + datetime.timedelta(minutes=1)) == datetime.date(2026, 8, 23)


def test_the_planner_and_the_start_rule_share_one_definition():
    """
    Two copies of "19:30" would drift, and the start rule would then guard a slot time
    the planner no longer uses.
    """
    src = (Path(__file__).resolve().parents[1] / "automation" / "simple_weekly_pipeline.py").read_text(
        encoding="utf-8"
    )
    assert "slot_times=list(DAILY_SLOT_TIMES)" in src
    assert DAILY_SLOT_TIMES == ("19:30", "22:00")


# ---------------------------------------------------------------- dry run

def _week_on_disk(tmp_path, week_id, remote_id):
    """A locked week carrying one platform record, live or mock depending on remote_id."""
    batch = tmp_path / "workspace" / "batches" / week_id
    batch.mkdir(parents=True)

    reels = [
        {
            "index": 1,
            "reel_id": "CBM-REEL-2026-0001",
            "scheduled_at_local": "2026-08-22 19:30:00",
            "scheduled_at_utc": "2026-08-22 16:30:00",
            "topic_key": "aircraft-garden-hidden",
            "title": "A title",
            "caption": "A caption",
            "hashtags": ["#Shorts"],
            "pipeline_version": 3,
            "content_mode": "hidden_build_story",
            "video_path": str(tmp_path / "v.mp4"),
            "video_sha256": "0" * 64,
            "generation_status": "COMPLETE",
        }
    ]
    (batch / "manifest.json").write_text(
        json.dumps(
            {
                "week_id": week_id,
                "start_date": "2026-08-22",
                "timezone": "Europe/Istanbul",
                "target_reels": 14,
                "status": "LOCKED",
                "content_mode": "hidden_build_story",
                "reels": reels,
            }
        ),
        encoding="utf-8",
    )
    (batch / "progress.json").write_text(
        json.dumps(
            {
                "CBM-REEL-2026-0001": {
                    "youtube": {"status": "SCHEDULED", "remote_id": remote_id, "url": None, "error": None},
                    "tiktok": {"status": "PENDING", "remote_id": None, "url": None, "error": None},
                    "instagram": {"status": "PENDING", "remote_media_id": None, "error": None},
                }
            }
        ),
        encoding="utf-8",
    )
    return batch


def _pipeline(tmp_path, week_id, dry_run):
    from automation.brands import get_brand

    return SimpleWeeklyPipeline(
        base_dir=tmp_path,
        vault_path=tmp_path / "vault",
        dry_run=dry_run,
        week_id=week_id,
        brand=get_brand("craftsbyman"),
    )


def test_a_rehearsal_refuses_to_overwrite_a_live_week(tmp_path):
    week_id = "CBM-2026-W34"
    _week_on_disk(tmp_path, week_id, remote_id="IQUBc21t6is")

    with pytest.raises(RuntimeError) as excinfo:
        _pipeline(tmp_path, week_id, dry_run=True).run(phase="youtube")

    assert "DRY_RUN_OVER_LIVE_WEEK" in str(excinfo.value)
    assert week_id in str(excinfo.value)


def test_a_rehearsal_over_its_own_mock_records_is_allowed(tmp_path):
    """
    Rehearsing a week that has published nothing real is the whole point of the flag,
    and it is how the suite drives full dry-run runs.
    """
    week_id = "CBM-2026-W40"
    _week_on_disk(tmp_path, week_id, remote_id="mock_yt_abc123")

    pipeline = _pipeline(tmp_path, week_id, dry_run=True)
    pipeline._refuse_dry_run_over_live_week(pipeline._get_or_create_manifest())


def test_a_live_run_is_never_blocked_by_this_guard(tmp_path):
    week_id = "CBM-2026-W34"
    _week_on_disk(tmp_path, week_id, remote_id="IQUBc21t6is")

    pipeline = _pipeline(tmp_path, week_id, dry_run=False)
    pipeline._refuse_dry_run_over_live_week(pipeline._get_or_create_manifest())


# ---------------------------------------------------------------- rehearsal records

def test_a_rehearsals_records_are_stamped_as_a_rehearsal(tmp_path):
    """
    Otherwise a rehearsal's records are indistinguishable from real ones, and the next
    live run skips the whole week as "already done" -- slots empty, state file confident.
    """
    week_id = "CBM-2026-W41"
    _week_on_disk(tmp_path, week_id, remote_id=None)
    reel_id = "CBM-REEL-2026-0001"

    rehearsal = _pipeline(tmp_path, week_id, dry_run=True)
    rehearsal._record_platform_status(
        week_id, reel_id, "youtube", "SCHEDULED", remote_id="mock_yt_abc123"
    )
    rehearsed = rehearsal.batch_repo.load_progress(week_id)[reel_id]["youtube"]
    assert rehearsed["status"] == "SCHEDULED", "the rehearsal still runs end to end"
    assert rehearsed["dry_run"] is True, "and says what it was"

    live = _pipeline(tmp_path, week_id, dry_run=False)
    live._record_platform_status(week_id, reel_id, "tiktok", "SCHEDULED")
    assert live.batch_repo.load_progress(week_id)[reel_id]["tiktok"]["dry_run"] is False


def test_only_a_live_run_discards_a_rehearsed_record(tmp_path):
    """
    Both halves matter. A live run must redo rehearsed work, or the slot stays empty --
    but the rehearsal itself must still trust its own records, or the thirty-minute hold
    re-runs the whole week every time it retries a phase.
    """
    week_id = "CBM-2026-W41"
    _week_on_disk(tmp_path, week_id, remote_id=None)
    rehearsed = {"status": "SCHEDULED", "remote_id": "mock_yt_abc123", "dry_run": True}
    real = {"status": "SCHEDULED", "remote_id": "IQUBc21t6is", "dry_run": False}

    live = _pipeline(tmp_path, week_id, dry_run=False)
    rehearsal = _pipeline(tmp_path, week_id, dry_run=True)

    assert live._counts_as_done(rehearsed) is False
    assert live._counts_as_done(real) is True
    assert rehearsal._counts_as_done(rehearsed) is True


def test_a_live_run_does_not_skip_a_rehearsed_reel():
    """The stamp is only worth anything if the skip consults it."""
    import inspect
    from automation import simple_weekly_pipeline as swp

    src = inspect.getsource(swp.SimpleWeeklyPipeline._run_platform_phase)
    assert "in PLATFORM_SUCCESS_STATUSES and self._counts_as_done(entry)" in src

    ig = inspect.getsource(swp.SimpleWeeklyPipeline._run_instagram_web_phase)
    assert "in INSTAGRAM_TERMINAL_STATUSES and self._counts_as_done(entry)" in ig


def test_a_rehearsed_record_is_not_evidence_of_an_upload(tmp_path):
    """
    The publisher decides between "resume the existing draft" and "upload from scratch" on
    this evidence. A mock id must never send a live run looking for a draft that only ever
    existed in a rehearsal.
    """
    from automation.publishing.models import Platform

    week_id = "CBM-2026-W42"
    _week_on_disk(tmp_path, week_id, remote_id=None)
    pipeline = _pipeline(tmp_path, week_id, dry_run=False)
    manifest = pipeline._get_or_create_manifest()

    rehearsed = {"status": "SCHEDULED", "remote_id": "mock_yt_abc123", "dry_run": True}
    record = pipeline._build_publish_record(manifest.reels[0], Platform.YOUTUBE, rehearsed)

    assert record.upload_started is False
    assert record.remote_draft_exists is False
