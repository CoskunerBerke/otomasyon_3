"""
Pre-Publish Hard Gate for live YouTube/TikTok/Instagram delivery.

Consolidates the Reel ID invariant and the full production-eligibility checklist into a
single call site every live publishing path must pass through BEFORE any file reaches a
platform. Failure occurs before upload -- never after.
"""
import hashlib
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

from .eligibility import is_live_production_eligible, HARD_EXCLUDED_REEL_IDS

logger = logging.getLogger("ReelsAIFactory.PrePublishGate")

# Fallback metadata strings that must never reach a live platform. If title/caption still
# looks like this, it means the generic fallback path was used instead of real ReelConceptPlan
# metadata -- block rather than publish something that was already an incident once.
PLACEHOLDER_TITLE_MARKERS = ("architectural marvel",)


def verify_reel_id_invariant(
    slot_reel_id: str,
    state_reel_id: str,
    publish_record_reel_id: str,
    video_path: Path
) -> Tuple[bool, str]:
    """
    Hard invariant: slot reel ID == state reel ID == PublishRecord reel ID == the reel ID
    encoded in the resolved video filename. Never "best guess" the file.
    """
    ids = {slot_reel_id, state_reel_id, publish_record_reel_id}
    if len(ids) != 1 or not slot_reel_id:
        return False, "REEL_ID_MEDIA_MISMATCH"

    if slot_reel_id not in Path(video_path).name:
        return False, "REEL_ID_MEDIA_MISMATCH"

    return True, "OK"


def is_placeholder_metadata(title: str, caption: str) -> bool:
    """Detects the known generic live-fallback metadata that caused the REEL-2026-0001 incident."""
    combined = f"{title or ''} {caption or ''}".strip().lower()
    if not combined:
        return True
    return any(marker in combined for marker in PLACEHOLDER_TITLE_MARKERS)


def run_pre_publish_hard_gate(
    reel_state: Any,
    slot: Any,
    publish_record: Any,
    video_path: Path,
    already_platform_success: bool = False
) -> Tuple[bool, str]:
    """
    Runs the full pre-publish checklist. Returns (True, "OK") only if every check passes.
    Must be called immediately before handing a file to a YouTube/TikTok/Instagram publisher.
    """
    video_path = Path(video_path)
    reel_id = getattr(reel_state, "reel_id", None)

    # 12. Platform has not already successfully processed this Reel.
    if already_platform_success:
        return False, "ALREADY_PUBLISHED_SKIP"

    # 1-9: production provenance, pipeline_version, content_mode, QC, mock/test/diagnostic
    # exclusion, and REEL-2026-0010 exclusion (all enforced inside is_live_production_eligible).
    ok, reason = is_live_production_eligible(reel_state, video_path)
    if not ok:
        return False, f"PRE_PUBLISH_GATE_FAILED: {reason}"

    # 3. Reel ID invariant across slot / state / PublishRecord / filename.
    ok, reason = verify_reel_id_invariant(
        slot_reel_id=getattr(slot, "reel_id", None),
        state_reel_id=reel_id,
        publish_record_reel_id=getattr(publish_record, "reel_id", None),
        video_path=video_path
    )
    if not ok:
        return False, reason

    # 10. Metadata is not placeholder/generic.
    if is_placeholder_metadata(getattr(publish_record, "title", ""), getattr(publish_record, "description", "")):
        return False, "PLACEHOLDER_METADATA_REJECTED"

    # 11. Scheduled datetime matches the slot exactly.
    if getattr(publish_record, "scheduled_at_local", None) != getattr(slot, "scheduled_at_local", None):
        return False, "SCHEDULE_DATETIME_SLOT_MISMATCH"

    # 13. SHA belongs to this exact Reel (redundant with is_live_production_eligible's check,
    # but re-verified here against the PublishRecord specifically, which is the thing that
    # actually gets uploaded).
    record_sha = getattr(publish_record, "video_sha256", None)
    if record_sha:
        actual_sha = hashlib.sha256(video_path.read_bytes()).hexdigest()
        if actual_sha != record_sha:
            return False, "REEL_ID_MEDIA_MISMATCH"

    return True, "OK"
