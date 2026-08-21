"""
Regression tests for the 2026-08-21 duplicate-upload incident.

Fourteen planned Reels became twenty-eight videos on a live YouTube channel, and this
system may not delete remote content, so the cleanup was manual.

Two defects combined:

  1. _build_publish_record rebuilt every record with status PENDING and derived
     upload_started from remote_id alone. Seven Reels whose id capture failed therefore
     looked untouched on retry, and the publisher's "is there remote evidence?" check --
     the only thing standing between a retry and a fresh upload -- said no. The
     30-minute hold ran two passes: 14 + 7 + 7 = 28.

  2. Those same seven, plus the first seven, came back carrying ONE shared remote id,
     because capture fell through to a browser URL still showing the previous video.
     Recording it ties a Reel's state to another Reel's video, which is what CLAUDE.md's
     Reel ID invariant forbids.

The properties pinned here: an upload that happened is remembered even when its id was
not, and a remote id may belong to only one Reel.
"""
import datetime
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from automation.orchestration.batch_manifest import BatchManifest, BatchReel, BatchRepository
from automation.publishing.models import Platform, PlatformPublicationStatus
from automation.simple_weekly_pipeline import (
    UPLOAD_ALREADY_ATTEMPTED_STATUSES,
    SimpleWeeklyPipeline,
)


def _pipe(tmp_path):
    return SimpleWeeklyPipeline(base_dir=tmp_path, vault_path=tmp_path / "v", dry_run=True)


def _reel(tmp_path, n=1):
    v = tmp_path / f"clean_REEL-2026-{n:04d}_x.mp4"
    v.write_bytes(b"v" * 64)
    base = datetime.date.today() + datetime.timedelta(days=5)
    return BatchReel(
        index=n, reel_id=f"REEL-2026-{n:04d}",
        scheduled_at_local=f"{base.isoformat()} 19:30:00",
        scheduled_at_utc=f"{base.isoformat()} 16:30:00",
        title=f"T{n}", caption="c", hashtags=["#x"],
        video_path=str(v), generation_status="COMPLETE",
    )


# ---------------------------------------------------------------- an upload is remembered

def test_a_failed_upload_without_an_id_is_still_remote_evidence(tmp_path):
    """The exact gap: uploaded, id never read, retried, uploaded again."""
    pipe = _pipe(tmp_path)
    entry = {"status": "SCHEDULE_RESUME_REQUIRED", "remote_id": None, "url": None, "error": "id missing"}

    rec = pipe._build_publish_record(_reel(tmp_path), Platform.YOUTUBE, entry)

    assert rec.upload_started is True, "a retry would upload this file a second time"
    assert rec.remote_draft_exists is True
    assert rec.status == PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED


@pytest.mark.parametrize("status", UPLOAD_ALREADY_ATTEMPTED_STATUSES)
def test_every_attempted_status_counts_as_evidence(tmp_path, status):
    pipe = _pipe(tmp_path)
    rec = pipe._build_publish_record(
        _reel(tmp_path), Platform.YOUTUBE, {"status": status, "remote_id": None}
    )
    assert rec.upload_started is True, f"{status} must not read as never-uploaded"


def test_a_genuinely_untouched_reel_is_still_uploadable(tmp_path):
    """The guard must not block the first upload."""
    pipe = _pipe(tmp_path)
    for status in ("PENDING", "NOT_STARTED", ""):
        rec = pipe._build_publish_record(
            _reel(tmp_path), Platform.YOUTUBE, {"status": status, "remote_id": None}
        )
        assert rec.upload_started is False, f"{status!r} should allow a first upload"


def test_an_unknown_status_fails_towards_not_re_uploading(tmp_path):
    """Fail-closed: an unrecognised status must not read as PENDING and invite a re-upload."""
    pipe = _pipe(tmp_path)
    rec = pipe._build_publish_record(
        _reel(tmp_path), Platform.YOUTUBE,
        {"status": "SOMETHING_NEW", "remote_id": "abc12345678"},
    )
    assert rec.upload_started is True


def test_the_attempt_is_written_before_the_upload_runs():
    """A process that dies mid-upload must still leave evidence behind."""
    src = (Path(__file__).resolve().parents[1] / "automation" / "simple_weekly_pipeline.py").read_text(encoding="utf-8")
    block = src[src.index("siraya alindi") if "siraya alindi" in src else src.index("sıraya alındı"):]
    block = block[:block.index("res_rec = publisher.upload_and_schedule")]
    assert "UPLOAD_ATTEMPTED" in block


# ---------------------------------------------------------------- one id per Reel

def _week(tmp_path, n=3):
    repo = BatchRepository(tmp_path)
    reels = [_reel(tmp_path, i + 1) for i in range(n)]
    m = BatchManifest(week_id="2026-W41", start_date=str(datetime.date.today()),
                      status="LOCKED", reels=reels)
    repo.save_manifest(m)
    repo.ensure_progress_entries(m.week_id, [r.reel_id for r in reels])
    return m


def test_a_remote_id_claimed_by_another_reel_is_detected(tmp_path):
    pipe = _pipe(tmp_path)
    manifest = _week(tmp_path)
    pipe.batch_repo.update_platform_status(
        manifest.week_id, "REEL-2026-0001", "youtube", "SCHEDULED", remote_id="VTMhhYTl9Co"
    )

    clash = pipe._reel_already_using_remote_id(manifest, "youtube", "VTMhhYTl9Co", "REEL-2026-0002")
    assert clash == "REEL-2026-0001"


def test_a_reel_does_not_clash_with_itself(tmp_path):
    """Re-verifying the same Reel must stay allowed."""
    pipe = _pipe(tmp_path)
    manifest = _week(tmp_path)
    pipe.batch_repo.update_platform_status(
        manifest.week_id, "REEL-2026-0001", "youtube", "SCHEDULED", remote_id="VTMhhYTl9Co"
    )

    assert pipe._reel_already_using_remote_id(manifest, "youtube", "VTMhhYTl9Co", "REEL-2026-0001") is None


def test_a_fresh_id_is_not_a_clash(tmp_path):
    pipe = _pipe(tmp_path)
    manifest = _week(tmp_path)
    assert pipe._reel_already_using_remote_id(manifest, "youtube", "brandNewId1", "REEL-2026-0002") is None


def test_the_clash_stops_the_platform_rather_than_recording_it():
    """Recording it would tie this Reel's state to another Reel's video."""
    src = (Path(__file__).resolve().parents[1] / "automation" / "simple_weekly_pipeline.py").read_text(encoding="utf-8")
    # The call site, not the definition -- the definition sorts earlier in the file.
    block = src[src.index("clash = self._reel_already_using_remote_id"):][:2000]
    assert "REEL_ID_MEDIA_MISMATCH" in block
    assert "hard_stop" in block
    assert "FAILED_FATAL" in block
