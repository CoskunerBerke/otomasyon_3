"""
Manual CLI Helper for Reels AI Factory Media Handoff.
Default execution is strictly DRY PLAN ONLY (0 network writes).
Live upload requires explicit --apply flag.
"""
import sys
import argparse
import logging
from pathlib import Path

logger = logging.getLogger("ReelsAIFactory.MediaHandoffCLI")

from automation.cloud.config import CloudConfig
from automation.cloud.media_storage import compute_file_sha256
from automation.media_handoff import handoff_reel_to_cloud


def main():
    parser = argparse.ArgumentParser(description="Reels AI Factory - Local Media Handoff CLI")
    parser.add_argument("--file", required=True, help="Path to local MP4 video file")
    parser.add_argument("--week-id", required=True, help="Target week ID (e.g. 2026-W34)")
    parser.add_argument("--reel-id", required=True, help="Target reel ID (e.g. REEL-2026-0011)")
    parser.add_argument("--scheduled-at-local", required=True, help="Scheduled local time (e.g. '2026-08-17 19:30:00')")
    parser.add_argument("--scheduled-at-utc", required=True, help="Scheduled UTC time (e.g. '2026-08-17 16:30:00')")
    parser.add_argument("--timezone", default="Europe/Istanbul", help="Timezone string")
    parser.add_argument("--caption", default="", help="Instagram caption")
    parser.add_argument("--job-id", default=None, help="Optional custom job ID")
    parser.add_argument("--apply", action="store_true", default=False, help="Execute live media handoff")

    args = parser.parse_args()
    config = CloudConfig()

    p = Path(args.file).resolve()
    if not p.exists():
        print(f"ERROR: File not found: {p}")
        sys.exit(1)

    if not p.name.lower().endswith(".mp4"):
        print(f"ERROR: File must be .mp4: {p.name}")
        sys.exit(1)

    file_size = p.stat().st_size
    file_sha = compute_file_sha256(p).lower()
    planned_job_id = args.job_id or f"JOB-{args.week_id}-{args.reel_id}"
    planned_object_key = f"media/{args.week_id}/{args.reel_id}/{file_sha}.mp4"

    print("=" * 60)
    print("REELS AI FACTORY - MEDIA HANDOFF TO RAILWAY")
    print("=" * 60)
    print(f"Local File       : {p}")
    print(f"File Size        : {file_size:,} bytes")
    print(f"SHA256           : {file_sha}")
    print(f"Week ID          : {args.week_id}")
    print(f"Reel ID          : {args.reel_id}")
    print(f"Planned Job ID   : {planned_job_id}")
    print(f"Target Key       : {planned_object_key}")
    print(f"Scheduled Local  : {args.scheduled_at_local} ({args.timezone})")
    print(f"Cloud Target URL : {config.public_base_url or '<NOT_SET>'}")
    print("=" * 60)

    if not args.apply:
        print("\n[DRY PLAN ONLY] No network writes executed.")
        print("To execute live handoff to Railway S3 and register Instagram job, run with --apply:")
        print(f".venv\\Scripts\\python.exe -m automation.media_handoff_cli --file \"{args.file}\" --week-id {args.week_id} --reel-id {args.reel_id} --scheduled-at-local \"{args.scheduled_at_local}\" --scheduled-at-utc \"{args.scheduled_at_utc}\" --apply\n")
        sys.exit(0)

    print("\n[LIVE HANDOFF REQUESTED] Uploading to Railway private S3...")
    ok, data, err = handoff_reel_to_cloud(
        local_path=p,
        week_id=args.week_id,
        reel_id=args.reel_id,
        scheduled_at_local=args.scheduled_at_local,
        scheduled_at_utc=args.scheduled_at_utc,
        timezone=args.timezone,
        caption=args.caption,
        job_id=args.job_id,
        config=config
    )

    if ok:
        print(f"[PASS] Media uploaded and verified in S3: {data.get('media_object_key')}")
        print(f"[PASS] Instagram job registered as MEDIA_READY: {data.get('job_id')}")
        print(f"[SUCCESS] Media handoff completed successfully! (Idempotent: {data.get('idempotent')})")
        sys.exit(0)
    else:
        print(f"[FAILED] Media handoff failed: {err}")
        sys.exit(1)


if __name__ == "__main__":
    main()
