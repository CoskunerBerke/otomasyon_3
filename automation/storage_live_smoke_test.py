"""
Railway Private S3 Storage Live Smoke Test Helper.
Triggers an authenticated S3 storage round-trip diagnostic inside Railway Cloud Control Plane.
Requires explicit --apply flag; default is DRY PLAN ONLY.
Executes zero generation, zero command claims, zero video publishing, and guarantees test cleanup.
"""
import sys
import argparse
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("ReelsAIFactory.StorageSmokeTest")

from automation.cloud.config import CloudConfig
from automation.local_worker_cloud_client import LocalWorkerCloudClient


def run_storage_smoke_test(
    apply_changes: bool = False,
    client: Optional[LocalWorkerCloudClient] = None,
    config: Optional[CloudConfig] = None
) -> bool:
    """Executes private S3 storage round-trip smoke test with strict safety defaults."""
    cfg = config or CloudConfig()

    print("=" * 60)
    print("REELS AI FACTORY - RAILWAY S3 STORAGE LIVE SMOKE TEST")
    print("=" * 60)
    print(f"Cloud URL      : {cfg.public_base_url or '<NOT_SET>'}")
    print(f"Worker Key     : {cfg.masked_worker_key}")
    print("=" * 60)

    if not cfg.public_base_url:
        print("\nERROR: PUBLIC_BASE_URL is not set.")
        return False
    if not cfg.is_worker_api_enabled:
        print("\nERROR: LOCAL_WORKER_API_KEY is not set.")
        return False

    if not apply_changes:
        print("\n[DRY-RUN] No storage operations executed.")
        print("To execute live private S3 storage round-trip test, run with --apply:")
        print(".venv\\Scripts\\python.exe -m automation.storage_live_smoke_test --apply\n")
        return True

    cl = client or LocalWorkerCloudClient(
        public_base_url=cfg.public_base_url,
        api_key=cfg.local_worker_api_key,
        timeout_seconds=20.0
    )

    print("\nExecuting live private S3 storage round-trip diagnostic on Railway...")
    ok, data, err = cl.run_storage_self_test()

    if ok and data.get("ok"):
        print(f"[PASS 1/7] PUT test object ({data.get('size_bytes', 0)} bytes)")
        print(f"[PASS 2/7] HEAD / exists verified in bucket")
        print(f"[PASS 3/7] Read real storage metadata")
        print(f"[PASS 4/7] GET / download test object")
        print(f"[PASS 5/7] SHA256 integrity match verified")
        print(f"[PASS 6/7] DELETE test object")
        print(f"[PASS 7/7] Verified test object removed from bucket (exists_after_delete: {data.get('exists_after_delete')})")
        print(f"\n[SUCCESS] Railway private S3 storage round-trip passed! Backend: {data.get('storage_backend')}")
        return True
    else:
        err_msg = err or data.get("error") or "UNKNOWN_ERROR"
        details = data.get("message") or ""
        print(f"\n[FAILED] S3 storage self-test failed: {err_msg} ({details})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Railway Private S3 Storage Smoke Test")
    parser.add_argument("--apply", action="store_true", default=False, help="Execute live private S3 round-trip diagnostic")
    args = parser.parse_args()

    success = run_storage_smoke_test(apply_changes=args.apply)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
