"""
Idempotency and duplicate upload prevention manager.
Computes video SHA256 fingerprints and validates platform publication states.
"""
import hashlib
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from .models import Platform, PlatformPublicationStatus, PublishRecord

class IdempotencyManager:
    """Guarantees that no Reel is scheduled or uploaded more than once per platform."""

    @staticmethod
    def compute_file_sha256(file_path: Path) -> str:
        """Compute SHA256 checksum of video file."""
        if not file_path.exists():
            return ""
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    # Alias for convenience
    compute_sha256 = compute_file_sha256

    @staticmethod
    def should_skip_platform(
        reel_id: str,
        platform: Platform,
        existing_records: Dict[str, PublishRecord]
    ) -> Tuple[bool, str]:
        """
        Check if a reel has already been successfully scheduled/published on the platform.
        Returns: `(should_skip: bool, reason: str)`
        """
        key = f"{reel_id}_{platform.value}"
        rec = existing_records.get(key)
        if not rec:
            return False, "New publication record"

        # Dry-run records and records without verified remote IDs NEVER block live upload
        if rec.dry_run or rec.status in (PlatformPublicationStatus.METADATA_READY, PlatformPublicationStatus.DRY_RUN):
            return False, f"Eligible for live upload (Dry-run/Metadata record: {rec.status.value})"

        if not rec.remote_id and rec.status not in (PlatformPublicationStatus.SCHEDULED, PlatformPublicationStatus.PUBLISHED):
            return False, f"Eligible for upload/retry (Current status: {rec.status.value})"

        if rec.status in (PlatformPublicationStatus.SCHEDULED, PlatformPublicationStatus.PUBLISHED) and rec.remote_id:
            remote_ref = rec.remote_id or rec.remote_url or "Verified Remote"
            return True, f"Already {rec.status.value} on {platform.value} (Remote: {remote_ref})"

        if rec.status == PlatformPublicationStatus.SKIPPED:
            return True, f"Previously skipped on {platform.value}"

        return False, f"Eligible for upload/retry (Current status: {rec.status.value})"
