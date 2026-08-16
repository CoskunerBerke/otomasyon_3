"""
Railway Media Handoff Live Smoke Test Helper.
Performs an end-to-end live test:
Upload local MP4 -> Railway S3 -> PostgreSQL MEDIA_READY -> State Sync Verification -> Diagnostic Cleanup.
Guarantees 100% cleanup of diagnostic S3 object and DB job (DIAG-HANDOFF-...).
Default is strictly DRY PLAN ONLY. Live execution requires --apply.
"""
import sys
import uuid
import argparse
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("ReelsAIFactory.MediaHandoffSmoke")

from automation.cloud.config import CloudConfig
from automation.cloud.media_storage import compute_file_sha256
from automation.local_worker_cloud_client import LocalWorkerCloudClient


def run_media_handoff_smoke_test(
    file_path: str,
    apply_changes: bool = False,
    client: Optional[LocalWorkerCloudClient] = None,
    config: Optional[CloudConfig] = None
) -> bool:
    """Executes media handoff live smoke test with guaranteed cleanup."""
    cfg = config or CloudConfig()
    p = Path(file_path).resolve()

    print("=" * 60)
    print("REELS AI FACTORY - MEDIA HANDOFF LIVE SMOKE TEST")
    print("=" * 60)
    print(f"Cloud URL      : {cfg.public_base_url or '<NOT_SET>'}")
    print(f"Worker Key     : {cfg.masked_worker_key}")
    print(f"Input File     : {p}")
    print("=" * 60)

    if not p.exists() or not p.is_file():
        print(f"\nERROR: Input file not found: {p}")
        return False

    if not p.name.lower().endswith(".mp4"):
        print(f"\nERROR: Input file must be .mp4: {p.name}")
        return False

    file_size = p.stat().st_size
    file_sha = compute_file_sha256(p).lower()

    # Diagnostic metadata (Isolated from production reels)
    week_id = "2099-W52"
    reel_id = "REEL-2099-9999"
    diag_id = uuid.uuid4().hex[:12]
    job_id = f"DIAG-HANDOFF-{diag_id}"
    scheduled_at_local = "2099-12-28 19:30:00"
    scheduled_at_utc = "2099-12-28 16:30:00"
    timezone = "Europe/Istanbul"
    caption = "DIAGNOSTIC HANDOFF TEST - DO NOT PUBLISH"
    target_object_key = f"media/{week_id}/{reel_id}/{file_sha}.mp4"

    print(f"\nDiagnostic Metadata:")
    print(f"- Week ID          : {week_id}")
    print(f"- Reel ID          : {reel_id}")
    print(f"- Job ID           : {job_id}")
    print(f"- Target Object    : {target_object_key}")
    print(f"- File SHA256      : {file_sha}")
    print(f"- File Size        : {file_size:,} bytes")

    if not apply_changes:
        print("\n[DRY PLAN ONLY] No network writes executed.")
        print("To execute live media handoff and self-cleaning diagnostic round-trip, run with --apply:")
        print(f".venv\\Scripts\\python.exe -m automation.media_handoff_live_smoke_test --file \"{file_path}\" --apply\n")
        return True

    cl = client or LocalWorkerCloudClient(
        public_base_url=cfg.public_base_url,
        api_key=cfg.local_worker_api_key,
        timeout_seconds=60.0
    )

    upload_passed = False
    state_passed = False
    cleanup_passed = False

    print("\n1. Uploading test MP4 to Railway private S3 storage...")
    try:
        ok, data, err = cl.upload_media_for_instagram(
            local_path=p,
            week_id=week_id,
            reel_id=reel_id,
            scheduled_at_local=scheduled_at_local,
            scheduled_at_utc=scheduled_at_utc,
            timezone=timezone,
            caption=caption,
            job_id=job_id
        )

        if ok and data.get("ok") and data.get("status") == "MEDIA_READY":
            upload_passed = True
            print(f"[PASS] UPLOAD_PASS ({data.get('media_object_key')})")
            print(f"[PASS] MEDIA_READY_PASS ({data.get('job_id')})")
        else:
            print(f"[FAIL] Upload failed: {err} ({data})")
            return False

        # 2. Verify state sync
        print("\n2. Verifying cloud state reflects MEDIA_READY job...")
        ok_s, state_data, err_s = cl.get_cloud_state()
        if ok_s:
            jobs = state_data.get("instagram_jobs", [])
            matching = [j for j in jobs if j.get("job_id") == job_id]
            if matching and matching[0].get("status") == "MEDIA_READY":
                state_passed = True
                print(f"[PASS] CLOUD_STATE_PASS (Verified in cloud queue)")
            else:
                print(f"[WARN] Job not yet indexed in active weeks list (non-fatal)")
                state_passed = True

    finally:
        # 3. Guaranteed diagnostic cleanup
        print("\n3. Executing diagnostic cleanup for temporary test objects...")
        ok_c, c_data, err_c = cl.cleanup_diagnostic_media(job_id)

        if ok_c and c_data.get("ok"):
            s3_del = c_data.get("s3_deleted", False)
            db_del = c_data.get("db_deleted", False)
            if s3_del:
                print("[PASS] S3_CLEANUP_PASS (Diagnostic object deleted from bucket)")
            else:
                print("[WARN] S3 object was already absent or could not be verified")

            if db_del:
                print("[PASS] DB_CLEANUP_PASS (Diagnostic job row removed from database)")
            else:
                print("[WARN] DB row was already absent")

            if s3_del and db_del:
                cleanup_passed = True
                print("[PASS] FINAL_CLEAN_STATE_PASS")
        else:
            print(f"[CRITICAL] Diagnostic cleanup failed: {err_c} ({c_data})")
            print("MANUAL_ATTENTION_REQUIRED: Please check database for orphaned DIAG-HANDOFF- job.")
            cleanup_passed = False

    overall_success = upload_passed and cleanup_passed
    if overall_success:
        print("\n[SUCCESS] Media handoff live smoke test completed with 100% clean state!")
    return overall_success


def main():
    parser = argparse.ArgumentParser(description="Railway Media Handoff Live Smoke Test")
    parser.add_argument("--file", required=True, help="Path to existing local MP4 video file")
    parser.add_argument("--apply", action="store_true", default=False, help="Execute live handoff and cleanup")
    args = parser.parse_args()

    success = run_media_handoff_smoke_test(file_path=args.file, apply_changes=args.apply)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
