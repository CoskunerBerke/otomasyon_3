"""
Consolidated regression suite for the 2026-08-16 live weekly pipeline safety repair.

Covers the full repaired contract in one file per repair policy: mock/test media
exclusion from live inventory, the REEL-2026-0010/0001 hard exclusions, the Reel ID
invariant, the pre-publish hard gate, real-content-plan metadata (no more generic
"Architectural Marvel" fallback), the single-layer hashtag contract, PublishRecord's
canonical `last_error` field, safe YouTube/TikTok review-modal handling, bounded remote
verification, and resume/idempotency for already-real Reels.

Strictly mocks/fakes only: 0 real browsers, 0 real Flow generation, 0 real platform calls.
"""
import datetime
import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from automation.orchestration.models import (
    ReelState,
    ReelPlatformStatus,
    ReelProvenance,
    PublishingSlot,
)
from automation.orchestration.state_repository import StateRepository
from automation.publishing.eligibility import (
    is_live_production_eligible,
    HARD_EXCLUDED_REEL_IDS,
    KNOWN_MOCK_RESOLUTIONS,
)
from automation.publishing.preflight_gate import (
    run_pre_publish_hard_gate,
    verify_reel_id_invariant,
    is_placeholder_metadata,
)
from automation.publishing.models import Platform, PlatformPublicationStatus, PublishRecord
from automation.weekly_orchestrator import WeeklyOrchestrator


def _make_state(reel_id, source=ReelProvenance.FLOW_LIVE_GENERATION.value, **overrides):
    defaults = dict(
        reel_id=reel_id,
        pipeline_version=3,
        content_mode="silent_global_step_by_step",
        generation_status="COMPLETE",
        qc_status="PASS",
        source=source,
        title=f"Real Title For {reel_id}",
        caption="Real caption derived from the content plan.",
        hashtags=["#Shorts", "#Architecture"],
    )
    defaults.update(overrides)
    return ReelState(**defaults)


def _write_video(tmp_path, reel_id, content=b"real production video bytes" * 50):
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    p = dl_dir / f"clean_{reel_id}.mp4"
    p.write_bytes(content)
    return p


# ---------------------------------------------------------------------------
# 1. Mock/test/legacy media exclusion from live inventory
# ---------------------------------------------------------------------------

def test_mock_provider_media_excluded_from_live_inventory(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0501")
    state = _make_state("REEL-2026-0501", source=ReelProvenance.MOCK_TEST_PROVIDER.value)
    ok, reason = is_live_production_eligible(state, video)
    assert ok is False
    assert "Provenance" in reason


def test_diagnostic_media_excluded_from_live_inventory(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0502")
    state = _make_state("REEL-2026-0502", source=ReelProvenance.DIAGNOSTIC_TEST.value)
    ok, reason = is_live_production_eligible(state, video)
    assert ok is False


def test_legacy_unverified_media_excluded_by_default(tmp_path):
    """No recorded provenance (the default for any pre-existing file) must be rejected,
    not silently accepted -- absence of evidence is not evidence of eligibility."""
    video = _write_video(tmp_path, "REEL-2026-0503")
    state = _make_state("REEL-2026-0503", source=ReelProvenance.LEGACY_UNVERIFIED.value)
    ok, reason = is_live_production_eligible(state, video)
    assert ok is False


def test_missing_state_excluded_by_default(tmp_path):
    """A file with NO persisted ReelState at all must be rejected, not admitted by default.
    This is the exact bug class that let the REEL-2026-0001 mock video through."""
    video = _write_video(tmp_path, "REEL-2026-0504")
    ok, reason = is_live_production_eligible(None, video)
    assert ok is False
    assert "provenance" in reason.lower()


def test_reel_0010_hard_excluded_even_with_forged_live_state(tmp_path):
    """Defense in depth: even if REEL-2026-0010's state is (incorrectly) tagged as real
    production provenance, the hard exclusion list still blocks it."""
    video = _write_video(tmp_path, "REEL-2026-0010")
    state = _make_state("REEL-2026-0010", source=ReelProvenance.FLOW_LIVE_GENERATION.value)
    ok, reason = is_live_production_eligible(state, video)
    assert ok is False
    assert "REEL-2026-0010" in reason


def test_reel_0001_hard_excluded_even_with_forged_live_state(tmp_path):
    """Same hard exclusion for REEL-2026-0001, the reel that was actually wrongly
    uploaded to YouTube on 2026-08-16."""
    video = _write_video(tmp_path, "REEL-2026-0001")
    state = _make_state("REEL-2026-0001", source=ReelProvenance.FLOW_LIVE_GENERATION.value)
    ok, reason = is_live_production_eligible(state, video)
    assert ok is False
    assert "REEL-2026-0001" in HARD_EXCLUDED_REEL_IDS


def test_known_mock_resolution_signature_is_540x960():
    """Documents the concrete evidence used for the resolution heuristic: real Flow
    output observed in this repo is 720x1280; MockVideoProvider's ffmpeg testsrc is
    540x960 (automation/flow/generator.py)."""
    assert (540, 960) in KNOWN_MOCK_RESOLUTIONS
    assert (720, 1280) not in KNOWN_MOCK_RESOLUTIONS


def test_quarantined_reel_excluded_regardless_of_other_fields(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0505")
    state = _make_state("REEL-2026-0505", quarantine_reason="Manually quarantined for review.")
    ok, reason = is_live_production_eligible(state, video)
    assert ok is False
    assert "quarantined" in reason.lower()


# ---------------------------------------------------------------------------
# 2. Real production reels (0011/0013/0014-style) remain eligible
# ---------------------------------------------------------------------------

def test_real_production_reel_is_eligible(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0013", content=b"real desert megacity bytes" * 100)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    state = _make_state("REEL-2026-0013", video_sha256=sha)
    ok, reason = is_live_production_eligible(state, video)
    assert ok is True, reason


def test_sha_mismatch_rejects_even_real_provenance(tmp_path):
    """A real-provenance state pointing at a file whose bytes no longer match its
    recorded SHA must be rejected -- protects against a stale/tampered/wrong file."""
    video = _write_video(tmp_path, "REEL-2026-0014")
    state = _make_state("REEL-2026-0014", video_sha256="0" * 64)
    ok, reason = is_live_production_eligible(state, video)
    assert ok is False
    assert "SHA256" in reason


def test_backfilled_real_reels_present_on_disk_are_recognized(tmp_path):
    """Simulates the actual repo state after the 2026-08-16 repair backfill: 0011/0013/0014
    have real production ReelState + real files, 0001/0010 do not."""
    repo = StateRepository(tmp_path)
    for reel_id in ("REEL-2026-0011", "REEL-2026-0013", "REEL-2026-0014"):
        video = _write_video(tmp_path, reel_id, content=(reel_id.encode() * 200))
        state = _make_state(reel_id, video_path=str(video), video_sha256=hashlib.sha256(video.read_bytes()).hexdigest())
        repo.save_reel_state(state)

    mock_video = _write_video(tmp_path, "REEL-2026-0001", content=b"MOCK_MP4_SEGMENT_BYTES" * 10)
    repo.save_reel_state(_make_state("REEL-2026-0001", source=ReelProvenance.MOCK_TEST_PROVIDER.value, video_path=str(mock_video)))
    repo.mark_reel_test_completed("REEL-2026-0010")

    orchestrator = WeeklyOrchestrator(base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=True)
    inventory_ids = {r["id"] for r in orchestrator._scan_v3_inventory()}

    assert inventory_ids == {"REEL-2026-0011", "REEL-2026-0013", "REEL-2026-0014"}
    assert "REEL-2026-0001" not in inventory_ids
    assert "REEL-2026-0010" not in inventory_ids


# ---------------------------------------------------------------------------
# 3. Reel ID invariant / pre-publish hard gate
# ---------------------------------------------------------------------------

def test_reel_id_invariant_passes_when_all_agree(tmp_path):
    video = tmp_path / "clean_REEL-2026-0777.mp4"
    video.write_bytes(b"x")
    ok, reason = verify_reel_id_invariant("REEL-2026-0777", "REEL-2026-0777", "REEL-2026-0777", video)
    assert ok is True


def test_reel_id_invariant_blocks_mismatch_between_state_and_slot(tmp_path):
    video = tmp_path / "clean_REEL-2026-0777.mp4"
    video.write_bytes(b"x")
    ok, reason = verify_reel_id_invariant("REEL-2026-0777", "REEL-2026-0001", "REEL-2026-0777", video)
    assert ok is False
    assert reason == "REEL_ID_MEDIA_MISMATCH"


def test_reel_id_invariant_blocks_when_filename_does_not_contain_reel_id(tmp_path):
    video = tmp_path / "clean_REEL-2026-0001_Futuristic_City_Build.mp4"
    video.write_bytes(b"x")
    ok, reason = verify_reel_id_invariant("REEL-2026-0777", "REEL-2026-0777", "REEL-2026-0777", video)
    assert ok is False
    assert reason == "REEL_ID_MEDIA_MISMATCH"


def test_placeholder_metadata_detected_and_rejected():
    assert is_placeholder_metadata("Architectural Marvel REEL-2026-0001", "Building from the ground up") is True
    assert is_placeholder_metadata("", "") is True
    assert is_placeholder_metadata("A Futuristic Megacity Rising From the Desert", "Real caption") is False


def test_pre_publish_gate_rejects_placeholder_metadata(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0013", content=b"real bytes" * 100)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    state = _make_state("REEL-2026-0013", video_sha256=sha)
    slot = PublishingSlot(
        slot_index=1, day_number=1, date_str="2026-08-25", time_str="19:30",
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00",
        reel_id="REEL-2026-0013"
    )
    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0013-YOUTUBE", batch_id="2026-08-25", reel_id="REEL-2026-0013",
        platform=Platform.YOUTUBE, video_file=video, video_sha256=sha,
        title="Architectural Marvel REEL-2026-0013", description="Building from the ground up in 30 seconds.",
        hashtags=[], scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00"
    )
    ok, reason = run_pre_publish_hard_gate(state, slot, rec, video)
    assert ok is False
    assert reason == "PLACEHOLDER_METADATA_REJECTED"


def test_pre_publish_gate_blocks_mock_media_end_to_end(tmp_path):
    """The exact scenario that caused the incident: a mock-provenance Reel with a
    PublishRecord ready to go must be blocked before upload."""
    video = _write_video(tmp_path, "REEL-2026-0001", content=b"MOCK_MP4_SEGMENT_BYTES" * 10)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    state = _make_state("REEL-2026-0001", source=ReelProvenance.MOCK_TEST_PROVIDER.value, video_sha256=sha)
    slot = PublishingSlot(
        slot_index=1, day_number=1, date_str="2026-08-17", time_str="19:30",
        scheduled_at_local="2026-08-17 19:30:00", scheduled_at_utc="2026-08-17 16:30:00",
        reel_id="REEL-2026-0001"
    )
    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0001-YOUTUBE", batch_id="2026-08-17", reel_id="REEL-2026-0001",
        platform=Platform.YOUTUBE, video_file=video, video_sha256=sha,
        title="A Real Sounding Title", description="A real sounding caption.",
        hashtags=["#test"], scheduled_at_local="2026-08-17 19:30:00", scheduled_at_utc="2026-08-17 16:30:00"
    )
    ok, reason = run_pre_publish_hard_gate(state, slot, rec, video)
    assert ok is False
    assert "PRE_PUBLISH_GATE_FAILED" in reason


def test_pre_publish_gate_skips_already_successful_platform(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0013", content=b"real bytes" * 100)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    state = _make_state("REEL-2026-0013", video_sha256=sha)
    slot = PublishingSlot(
        slot_index=1, day_number=1, date_str="2026-08-25", time_str="19:30",
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00",
        reel_id="REEL-2026-0013"
    )
    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0013-YOUTUBE", batch_id="2026-08-25", reel_id="REEL-2026-0013",
        platform=Platform.YOUTUBE, video_file=video, video_sha256=sha,
        title="A Real Title", description="A real caption.", hashtags=[],
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00"
    )
    ok, reason = run_pre_publish_hard_gate(state, slot, rec, video, already_platform_success=True)
    assert ok is False
    assert reason == "ALREADY_PUBLISHED_SKIP"


def test_pre_publish_gate_accepts_valid_real_record(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0013", content=b"real bytes" * 100)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    state = _make_state("REEL-2026-0013", video_sha256=sha)
    slot = PublishingSlot(
        slot_index=1, day_number=1, date_str="2026-08-25", time_str="19:30",
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00",
        reel_id="REEL-2026-0013"
    )
    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0013-YOUTUBE", batch_id="2026-08-25", reel_id="REEL-2026-0013",
        platform=Platform.YOUTUBE, video_file=video, video_sha256=sha,
        title="A Futuristic Megacity Rising From the Desert", description="Real caption.", hashtags=["#Shorts"],
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00"
    )
    ok, reason = run_pre_publish_hard_gate(state, slot, rec, video)
    assert ok is True, reason


# ---------------------------------------------------------------------------
# 4. No phantom COMPLETE/PASS slots without a real file
# ---------------------------------------------------------------------------

def test_live_assign_reels_leaves_missing_slots_waiting_for_generation(tmp_path):
    orchestrator = WeeklyOrchestrator(base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=False)
    start_date = datetime.date(2026, 8, 17)

    from automation.orchestration.slot_generator import generate_14_slot_week_plan
    plan = generate_14_slot_week_plan(start_date=start_date, slot_times=["19:30", "22:00"], timezone_str="Europe/Istanbul")

    assigned = orchestrator._assign_reels_to_slots(plan, available_reels=[])

    assert len(assigned) == 14
    for state in assigned:
        assert state.generation_status != "COMPLETE"
        assert state.qc_status != "PASS"
    for slot in plan.slots:
        assert slot.qc_status == "PENDING"


def test_live_pipeline_never_schedules_waiting_for_generation_slots(tmp_path):
    """End-to-end: with zero real inventory and generation disabled (needed reels simply
    can't be produced in this test), no platform publisher may ever be called."""
    mock_yt = MagicMock()
    mock_tt = MagicMock()
    mock_client = MagicMock()

    orchestrator = WeeklyOrchestrator(
        base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=False,
        yt_publisher=mock_yt, tt_publisher=mock_tt, cloud_client=mock_client
    )

    with patch.object(WeeklyOrchestrator, "_generate_missing_v3_reels", return_value=[]):
        ok, report, plan = orchestrator.run_weekly_pipeline(
            start_date=datetime.date(2026, 8, 17), week_id="2026-W99"
        )

    mock_yt.upload_and_schedule.assert_not_called()
    mock_tt.upload_and_schedule.assert_not_called()
    mock_client.upload_media_for_instagram.assert_not_called()
    for slot in plan.slots:
        assert slot.youtube_status == "WAITING_FOR_GENERATION"
        assert slot.tiktok_status == "WAITING_FOR_GENERATION"
        assert slot.instagram_status == "WAITING_FOR_GENERATION"


# ---------------------------------------------------------------------------
# 5. Real metadata from the content plan (no generic fallback)
# ---------------------------------------------------------------------------

def test_generated_reel_gets_real_metadata_not_generic_fallback(tmp_path):
    dl_dir = tmp_path / "workspace" / "downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)

    mock_flow = MagicMock()

    def fake_generate(plan, reel_id, target_filename, **kwargs):
        fake_video = dl_dir / target_filename
        fake_video.write_bytes(b"real generated video bytes" * 50)
        return fake_video
    mock_flow.generate_single_video.side_effect = fake_generate

    orchestrator = WeeklyOrchestrator(
        base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=False, flow_provider=mock_flow
    )

    with patch("automation.weekly_orchestrator.VideoValidator") as mock_validator_cls:
        mock_val = MagicMock()
        mock_val.process_and_validate.side_effect = lambda input_video, output_dir: MagicMock(
            is_passed=True, processed_video_path=input_video
        )
        mock_validator_cls.return_value = mock_val

        generated = orchestrator._generate_missing_v3_reels(needed=1, week_id="2026-W34")

    assert len(generated) == 1
    reel_id = generated[0]["id"]
    state = orchestrator.repo.get_reel_state(reel_id)
    assert state is not None
    assert state.source == ReelProvenance.FLOW_LIVE_GENERATION.value
    assert state.generation_status == "COMPLETE"
    assert state.qc_status == "PASS"
    assert "architectural marvel" not in state.title.lower()
    assert state.title.strip() != ""
    assert state.caption.strip() != ""
    assert len(state.hashtags) > 0


def test_topic_key_resolves_to_real_concept_metadata():
    """Documents the exact repair example: 'desert-megacity-dunes-skyscrapers' must
    resolve to the real Desert Megacity concept, not a generic string."""
    from automation.content.concepts import find_concept_by_topic_key
    concept = find_concept_by_topic_key("desert-megacity-dunes-skyscrapers")
    assert concept is not None
    assert concept.id_slug == "desert-megacity"
    assert "megacity" in concept.topic_description.lower() or "megacity" in concept.default_title.lower()

    concept2 = find_concept_by_topic_key("tropical-resort-clearing-eco-lodges")
    assert concept2 is not None
    assert concept2.id_slug == "tropical-resort"


# ---------------------------------------------------------------------------
# 6. Hashtags appear exactly once
# ---------------------------------------------------------------------------

def test_youtube_publish_record_description_excludes_hashtags(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0013", content=b"real bytes" * 100)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    r_state = _make_state("REEL-2026-0013", video_sha256=sha, hashtags=["#Shorts", "#Architecture"])

    mock_yt = MagicMock()
    mock_yt.upload_and_schedule.side_effect = lambda r: (setattr(r, "status", PlatformPublicationStatus.SCHEDULED), r)[1]

    orchestrator = WeeklyOrchestrator(base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=False, yt_publisher=mock_yt)
    slot = PublishingSlot(
        slot_index=1, day_number=1, date_str="2026-08-25", time_str="19:30",
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00",
        reel_id="REEL-2026-0013"
    )

    ok = orchestrator._schedule_youtube_slot(slot, r_state)
    assert ok is True

    sent_record = mock_yt.upload_and_schedule.call_args[0][0]
    assert sent_record.description == r_state.caption
    assert "#Shorts" not in sent_record.description
    assert sent_record.hashtags == r_state.hashtags


def test_tiktok_publish_record_description_excludes_hashtags(tmp_path):
    video = _write_video(tmp_path, "REEL-2026-0013", content=b"real bytes" * 100)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()
    r_state = _make_state("REEL-2026-0013", video_sha256=sha, hashtags=["#satisfying", "#aitok"])

    mock_tt = MagicMock()
    mock_tt.upload_and_schedule.side_effect = lambda r: (setattr(r, "status", PlatformPublicationStatus.SCHEDULED), r)[1]

    orchestrator = WeeklyOrchestrator(base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=False, tt_publisher=mock_tt)
    slot = PublishingSlot(
        slot_index=1, day_number=1, date_str="2026-08-25", time_str="19:30",
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00",
        reel_id="REEL-2026-0013"
    )

    ok = orchestrator._schedule_tiktok_slot(slot, r_state)
    assert ok is True

    sent_record = mock_tt.upload_and_schedule.call_args[0][0]
    assert sent_record.description == r_state.caption
    assert "#satisfying" not in sent_record.description


# ---------------------------------------------------------------------------
# 7. PublishRecord canonical error field
# ---------------------------------------------------------------------------

def test_publish_record_uses_last_error_not_error_message():
    rec = PublishRecord(
        publish_id="PUB-TEST", batch_id="2026-08-25", reel_id="REEL-2026-0013",
        platform=Platform.YOUTUBE, video_file=Path("x.mp4"), video_sha256="a" * 64,
        title="t", description="d", hashtags=[],
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00"
    )
    rec.mark_failed("boom")
    assert rec.last_error == "boom"
    assert "error_message" not in PublishRecord.__dataclass_fields__


# ---------------------------------------------------------------------------
# 8. YouTube content-review informational modal (safe, non-fatal)
# ---------------------------------------------------------------------------

class _FakeLocator:
    def __init__(self, visible=False):
        self._visible = visible
        self.clicked = False

    @property
    def first(self):
        return self

    def is_visible(self, timeout=None):
        return self._visible

    def wait_for(self, state="visible", timeout=None):
        # Mirrors real Playwright: raises if the element never reaches `state`
        # within timeout, returns None (silently) once it does. Unlike
        # is_visible(timeout=...), this fake actually enforces that contract.
        if state == "visible" and not self._visible:
            raise TimeoutError(f"locator did not become visible within {timeout}ms")

    def click(self, timeout=None):
        self.clicked = True


class _FakePage:
    """
    Minimal Playwright stand-in for selector-level assertions.

    Selectors in the production lists are comma-joined unions: Kural 31 caps the number
    of *semantic strategies* at 2 per UI action, but one strategy may name several
    equivalent DOM shapes (e.g. "button[aria-label='Anladım'], ytcp-button[aria-label=...]").
    Real Playwright resolves such a union to whichever alternative matches, so this fake
    must too. Exact-string matching on the whole union would report every grouped selector
    as invisible and quietly turn these tests into no-ops.
    """

    def __init__(self, inner_text="", visible_selectors=None):
        self._inner_text = inner_text
        self._visible_selectors = visible_selectors or {}
        self._locators = {}

    def inner_text(self, selector):
        return self._inner_text

    def _resolve(self, selector):
        """First comma-separated alternative this fake treats as present, if any."""
        for alternative in (part.strip() for part in selector.split(",")):
            if self._visible_selectors.get(alternative, False):
                return alternative, True
        return selector, False

    def locator(self, selector):
        # Key the cache by the matched alternative so a click recorded during the call
        # under test stays observable from an assertion that names that alternative on
        # its own, e.g. page.locator("button:has-text('Anladım')").
        key, visible = self._resolve(selector)
        if key not in self._locators:
            self._locators[key] = _FakeLocator(visible=visible)
        return self._locators[key]


def test_youtube_review_modal_dismissed_via_anladim_only():
    from automation.publishing.youtube_studio_selectors import YouTubeStudioSelectors
    from automation.publishing.youtube_studio_ui_observer import YouTubeStudioUIObserver

    # Take the selector from the source rather than restating it. The dismissal moved to
    # comma-grouped aria-label strategies (Kural 31) and this test kept naming the old
    # bare has-text selector, so its fake matched nothing and it had been failing --
    # quietly, in a suite nobody could read, while the code itself was fine.
    dismiss_selector = YouTubeStudioSelectors.CONTENT_REVIEW_INFO_DISMISS_BUTTONS[0]

    page = _FakePage(
        inner_text="İçeriğinizi kontrol etmeye devam ediyoruz. Anladım",
        visible_selectors={dismiss_selector: True}
    )
    observer = YouTubeStudioUIObserver(page)
    observer.dismiss_content_review_info_if_present()

    assert page.locator(dismiss_selector).clicked is True


def test_youtube_review_modal_dismissed_via_aria_label_strategy():
    """
    Strategy 1 (aria-label) is what actually fires in production, against the real DOM
    the operator supplied on 2026-08-17:
        <button aria-label="Anladım" aria-disabled="false" tabindex="0">
    """
    from automation.publishing.youtube_studio_ui_observer import YouTubeStudioUIObserver

    page = _FakePage(
        inner_text="İçeriğinizi kontrol etmeye devam ediyoruz.",
        visible_selectors={"button[aria-label='Anladım']": True}
    )
    observer = YouTubeStudioUIObserver(page)
    observer.dismiss_content_review_info_if_present()

    assert page.locator("button[aria-label='Anladım']").clicked is True


def test_youtube_review_modal_dismissed_even_when_marker_text_absent_from_dialog():
    """
    Regression for the stall fixed in c118658: the notice is a separate overlay, so its
    text is NOT inside ytcp-uploads-dialog. Gating the click on that text meant dismissal
    never fired and every live run blocked until a human clicked the button by hand.
    Dismissal must therefore key off the button itself, not the surrounding prose.
    """
    from automation.publishing.youtube_studio_ui_observer import YouTubeStudioUIObserver

    page = _FakePage(
        inner_text="Kontroller tamamlandı",
        visible_selectors={"button[aria-label='Anladım']": True}
    )
    observer = YouTubeStudioUIObserver(page)
    observer.dismiss_content_review_info_if_present()

    assert page.locator("button[aria-label='Anladım']").clicked is True


def test_youtube_review_modal_not_touched_when_button_absent():
    from automation.publishing.youtube_studio_ui_observer import YouTubeStudioUIObserver

    # Notice text on screen but no dismiss button: nothing may be clicked.
    page = _FakePage(inner_text="İçeriğinizi kontrol etmeye devam ediyoruz.", visible_selectors={})
    observer = YouTubeStudioUIObserver(page)
    observer.dismiss_content_review_info_if_present()

    assert all(loc.clicked is False for loc in page._locators.values())


def test_youtube_review_dismissal_can_only_match_an_acknowledgement_control():
    """
    Dismissal is deliberately not gated on the notice text, so the whole safety argument
    rests on these selectors being unable to match anything but an acknowledgement
    button. Guard that invariant, plus the Kural 31 two-strategy cap.
    """
    from automation.publishing.youtube_studio_selectors import YouTubeStudioSelectors

    selectors = YouTubeStudioSelectors.CONTENT_REVIEW_INFO_DISMISS_BUTTONS
    assert len(selectors) <= 2, "Kural 31: max 2 semantic selector strategies per action"

    joined = " ".join(selectors).lower()
    for forbidden in ("hemen payla", "şimdi payla", "post now", "publish now", "yayınla"):
        assert forbidden not in joined, f"dismissal selector could match publish control: {forbidden}"


# ---------------------------------------------------------------------------
# 9. TikTok never clicks immediate-publish; schedule mode must be verified
# ---------------------------------------------------------------------------

def test_tiktok_hard_safety_blocks_when_schedule_mode_unverified():
    from automation.publishing.tiktok_ui_observer import TikTokUIObserver

    observer = TikTokUIObserver(MagicMock())
    ok, reason = observer.click_schedule_and_verify(schedule_mode_verified=False)
    assert ok is False
    assert reason == "SCHEDULE_MODE_NOT_ACTIVE"


# ---------------------------------------------------------------------------
# 10. Flow "Yeni proje" landing-page detection (auth issue, not UI-changed bug)
# ---------------------------------------------------------------------------

def test_flow_landing_page_raises_user_action_required_not_ui_changed(tmp_path):
    from automation.flow.page import FlowPage
    from automation.flow.selectors import UserActionRequiredError

    class _LandingLocator:
        def __init__(self, visible):
            self._visible = visible

        @property
        def first(self):
            return self

        def is_visible(self, timeout=None):
            return self._visible

        def wait_for(self, state="visible", timeout=None):
            # Mirrors real Playwright: raises if the element never reaches `state`
            # within timeout, returns None (silently) once it does. Unlike
            # is_visible(timeout=...), this fake actually enforces that contract.
            if state == "visible" and not self._visible:
                raise TimeoutError(f"locator did not become visible within {timeout}ms")

    class _LandingPage:
        url = "https://labs.google/fx/tools/flow"

        def locator(self, selector):
            if selector == "button:has-text('Try Google Flow')":
                return _LandingLocator(True)
            return _LandingLocator(False)

        def screenshot(self, path=None, full_page=None):
            Path(path).write_bytes(b"")

        def content(self):
            return "<html></html>"

        def title(self):
            return "Google Flow"

    flow_page = FlowPage(page=_LandingPage(), screenshots_dir=tmp_path / "shots", downloads_dir=tmp_path / "dl")

    with pytest.raises(UserActionRequiredError):
        flow_page.check_auth_and_security()


# ---------------------------------------------------------------------------
# 11. Bounded remote verification (max 2 attempts), SCHEDULE_RESUME_REQUIRED
# ---------------------------------------------------------------------------

def test_youtube_bounded_remote_verification_max_two_attempts(tmp_path):
    from automation.publishing.youtube_studio_publisher import YouTubeStudioPublisher
    from automation.publishing.config import PublishingConfig

    video = _write_video(tmp_path, "REEL-2026-0013", content=b"real bytes" * 100)
    sha = hashlib.sha256(video.read_bytes()).hexdigest()

    rec = PublishRecord(
        publish_id="PUB-REEL-2026-0013-YOUTUBE", batch_id="2026-08-25", reel_id="REEL-2026-0013",
        platform=Platform.YOUTUBE, video_file=video, video_sha256=sha,
        title="A Real Title", description="A real caption.", hashtags=[],
        scheduled_at_local="2026-08-25 19:30:00", scheduled_at_utc="2026-08-25 16:30:00",
        remote_id="yt_existing_id", remote_url="https://youtube.com/shorts/yt_existing_id",
        upload_started=True, remote_draft_exists=True
    )

    publisher = YouTubeStudioPublisher.__new__(YouTubeStudioPublisher)
    publisher.config = PublishingConfig()
    publisher.repo = MagicMock()
    publisher.repo.get_publish_record.return_value = None
    publisher.repo.merge_with_existing.side_effect = lambda r: r

    mock_observer = MagicMock()
    mock_observer.is_logged_in.return_value = True
    mock_observer.verify_logged_in_channel.return_value = (True, "@BuiIdVerse", "ok")
    mock_observer.open_exact_remote_video.return_value = True
    mock_observer.enter_existing_draft_wizard.return_value = True
    mock_observer.advance_wizard_to_visibility.return_value = (True, "ok")
    mock_observer.find_and_expand_schedule_card.return_value = True
    mock_observer.set_schedule_datetime.return_value = True
    mock_observer.click_schedule_and_verify.return_value = (True, "ref")
    mock_observer.verify_remote_scheduled_status.return_value = (False, "REMOTE_STILL_DRAFT")

    fake_ctx = MagicMock()
    fake_ctx.pages = []
    fake_page = MagicMock()
    fake_page.url = "https://studio.youtube.com/"
    fake_ctx.new_page.return_value = fake_page

    class _CM:
        def __enter__(self):
            return (MagicMock(), fake_ctx)

        def __exit__(self, *a):
            return False

    publisher.browser_mgr = MagicMock()
    publisher.browser_mgr.connect.return_value = _CM()

    with patch("automation.publishing.youtube_studio_publisher.YouTubeStudioUIObserver", return_value=mock_observer), \
         patch("automation.publishing.youtube_studio_publisher.time.sleep", return_value=None):
        result = publisher.upload_and_schedule(rec)

    # Bounded, not unbounded -- which is what this test is for. The bound itself grew
    # deliberately when verification was made patient (2026-08-19), so it is read from the
    # source: one pre-resume check plus one per backoff step.
    from automation.publishing.youtube_studio_publisher import VERIFY_BACKOFF_SECONDS

    assert mock_observer.verify_remote_scheduled_status.call_count == 1 + len(VERIFY_BACKOFF_SECONDS)
    assert result.status == PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
    # Remote evidence must be preserved, never falsely marked SCHEDULED.
    assert result.remote_id == "yt_existing_id"


# ---------------------------------------------------------------------------
# 12. Resume does not regenerate real reels / does not re-spend Flow credits
# ---------------------------------------------------------------------------

def test_resume_does_not_regenerate_existing_real_inventory(tmp_path):
    repo = StateRepository(tmp_path)
    for i in range(11, 25):
        reel_id = f"REEL-2026-{i:04d}"
        video = _write_video(tmp_path, reel_id, content=(reel_id.encode() * 100))
        state = _make_state(reel_id, video_path=str(video), video_sha256=hashlib.sha256(video.read_bytes()).hexdigest())
        repo.save_reel_state(state)

    mock_flow = MagicMock()
    orchestrator = WeeklyOrchestrator(base_dir=tmp_path, vault_path=tmp_path / "vault", dry_run=False, flow_provider=mock_flow)

    available = orchestrator._scan_v3_inventory()
    assert len(available) == 14

    mock_flow.generate_single_video.assert_not_called()
