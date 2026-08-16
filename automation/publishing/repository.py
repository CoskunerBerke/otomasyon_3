"""
Obsidian Publishing Repository.
Manages 13_PUBLISHING/, PUBLISHING_QUEUE.md, PUB-BATCH notes, PUB-REEL record notes,
and synchronizes Publishing Metadata into Reel notes.
Guarantees remote ID preservation, merge rules, and pre-upload atomic reloads.
"""
import re
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from .models import Platform, PlatformPublicationStatus, PublishRecord, PublishingBatch

logger = logging.getLogger("ReelsAIFactory.PublishingRepository")

class PublishingRepository:
    """Handles all Obsidian I/O operations for the publishing subsystem."""

    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path).resolve()
        self.publishing_dir = self.vault_path / "13_PUBLISHING"
        self.queue_file = self.publishing_dir / "PUBLISHING_QUEUE.md"
        self._ensure_folders()

    def _ensure_folders(self) -> None:
        try:
            self.publishing_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to create 13_PUBLISHING directory: {e}")

    def _safe_write(self, target_file: Path, content: str) -> None:
        """Atomic write with temporary file and retry."""
        try:
            target_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = target_file.with_suffix(".tmp")
            for _ in range(3):
                try:
                    tmp_file.write_text(content, encoding="utf-8")
                    tmp_file.replace(target_file)
                    return
                except PermissionError:
                    import time
                    time.sleep(0.1)
                except Exception:
                    if tmp_file.exists():
                        tmp_file.unlink(missing_ok=True)
                    raise

            target_file.write_text(content, encoding="utf-8")
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Publishing write failed for {target_file.name}: {e}")

    def get_publish_record(self, reel_id: str, platform: Platform) -> Optional[PublishRecord]:
        """Load a specific PublishRecord directly from disk if it exists."""
        self._ensure_folders()
        platform_str = platform.value.upper()
        rec_filename = f"PUB-{reel_id}-{platform_str}.md"
        rec_file = self.publishing_dir / rec_filename
        if not rec_file.exists():
            return None

        try:
            content = rec_file.read_text(encoding="utf-8")
            fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
            if not fm_match:
                return None

            fm_text = fm_match.group(1)
            data: Dict[str, Any] = {}
            for line in fm_text.splitlines():
                if ":" in line and not line.startswith("  -"):
                    k, v = line.split(":", 1)
                    data[k.strip()] = v.strip().strip('"').strip("'")

            is_dry_run = str(data.get("dry_run", "false")).lower() == "true"
            upload_started = str(data.get("upload_started", "false")).lower() == "true"
            remote_draft_exists = str(data.get("remote_draft_exists", "false")).lower() == "true"

            return PublishRecord(
                publish_id=data.get("publish_id", rec_file.stem),
                batch_id=data.get("batch_id", ""),
                reel_id=data.get("reel_id", reel_id),
                platform=platform,
                video_file=Path(data.get("video_file", "")),
                video_sha256=data.get("video_sha256", ""),
                title="",
                description="",
                hashtags=[],
                scheduled_at_local=data.get("scheduled_at_local", ""),
                scheduled_at_utc=data.get("scheduled_at_utc", ""),
                account_handle=data.get("account_handle", ""),
                timezone=data.get("timezone", "Europe/Istanbul"),
                status=PlatformPublicationStatus(data.get("status", "PENDING")),
                remote_id=data.get("remote_id") or None,
                remote_url=data.get("remote_url") or None,
                upload_started=upload_started,
                remote_draft_exists=remote_draft_exists,
                dry_run=is_dry_run,
                attempt_count=int(data.get("attempt_count", 0)),
                last_error=data.get("last_error") or None,
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                schedule_verified=str(data.get("schedule_verified", "false")).lower() == "true",
                verified_schedule_date=data.get("verified_schedule_date") or None,
                verified_schedule_time=data.get("verified_schedule_time") or None,
                verified_remote_status=data.get("verified_remote_status") or None,
                verified_at=data.get("verified_at") or None
            )
        except Exception as e:
            logger.warning(f"Error reading publish record {rec_filename}: {e}")
            return None

    def merge_with_existing(self, new_record: PublishRecord) -> PublishRecord:
        """
        Merge new_record with any existing record on disk.
        Existing remote_id, remote_url, upload_started, and resume states ALWAYS WIN.
        """
        existing = self.get_publish_record(new_record.reel_id, new_record.platform)
        if not existing:
            return new_record

        # Preserve remote evidence only for live runs (dry-run stays clean)
        if not new_record.dry_run:
            if existing.remote_id and not new_record.remote_id:
                new_record.remote_id = existing.remote_id
                logger.info(f"[{new_record.reel_id}] Merged existing remote_id: {existing.remote_id}")

            if existing.remote_url and not new_record.remote_url:
                new_record.remote_url = existing.remote_url

            if existing.upload_started:
                new_record.upload_started = True

            if existing.remote_draft_exists:
                new_record.remote_draft_exists = True

            # Preserve resume/scheduled status if new_record is generic PENDING
            if new_record.status == PlatformPublicationStatus.PENDING:
                if existing.status in (
                    PlatformPublicationStatus.UPLOADED_DRAFT,
                    PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED,
                ):
                    new_record.status = existing.status
                    logger.info(f"[{new_record.reel_id}] Preserved status from disk: {existing.status.value}")
                elif existing.status == PlatformPublicationStatus.SCHEDULED:
                    # SCHEDULED only preserved if schedule_verified is True
                    if getattr(existing, 'schedule_verified', False):
                        new_record.status = existing.status
                        new_record.schedule_verified = existing.schedule_verified
                        new_record.verified_schedule_date = existing.verified_schedule_date
                        new_record.verified_schedule_time = existing.verified_schedule_time
                        new_record.verified_remote_status = existing.verified_remote_status
                        new_record.verified_at = existing.verified_at
                        logger.info(f"[{new_record.reel_id}] Preserved verified SCHEDULED status from disk.")
                    else:
                        new_record.status = PlatformPublicationStatus.SCHEDULE_RESUME_REQUIRED
                        logger.warning(f"[{new_record.reel_id}] SCHEDULED without verification evidence → normalized to SCHEDULE_RESUME_REQUIRED")
                elif existing.status == PlatformPublicationStatus.PUBLISHED:
                    new_record.status = existing.status
                    logger.info(f"[{new_record.reel_id}] Preserved status from disk: {existing.status.value}")

        return new_record

    def save_publish_record(self, record: PublishRecord) -> Path:
        """Create or update 13_PUBLISHING/PUB-<REEL_ID>-<PLATFORM>.md."""
        self._ensure_folders()
        platform_str = record.platform.value.upper()
        rec_filename = f"PUB-{record.reel_id}-{platform_str}.md"
        rec_file = self.publishing_dir / rec_filename

        tags_str = f"""tags:
  - publishing
  - {record.platform.value}
  - {record.status.value.lower()}"""

        content = f"""---
node_type: publish_record
publish_id: {record.publish_id}
batch_id: {record.batch_id}
reel_id: {record.reel_id}
platform: {record.platform.value}
account_handle: "{record.account_handle}"
status: {record.status.value}
scheduled_at_local: {record.scheduled_at_local}
scheduled_at_utc: {record.scheduled_at_utc}
timezone: {record.timezone}
remote_id: "{record.remote_id or ''}"
remote_url: "{record.remote_url or ''}"
upload_started: {str(record.upload_started).lower()}
remote_draft_exists: {str(record.remote_draft_exists).lower()}
dry_run: {str(record.dry_run).lower()}
video_sha256: "{record.video_sha256}"
ai_generated: {str(record.ai_generated).lower()}
synthetic_media_disclosed: {str(record.synthetic_media_disclosed).lower()}
schedule_verified: {str(record.schedule_verified).lower()}
verified_schedule_date: "{record.verified_schedule_date or ''}"
verified_schedule_time: "{record.verified_schedule_time or ''}"
verified_remote_status: "{record.verified_remote_status or ''}"
verified_at: "{record.verified_at or ''}"
attempt_count: {record.attempt_count}
last_error: "{record.last_error or ''}"
created_at: {record.created_at}
updated_at: {record.updated_at}
{tags_str}
---

# 📢 {record.platform.value.upper()} Publishing Record

- **Reel:** [[{record.reel_id}]]
- **Batch:** [[{record.batch_id}]]
- **Published / Scheduled by:** [[PUBLISH_AGENT]]
- **Platform:** {record.platform.value.title()}
- **Target Account:** `{record.account_handle or 'Default'}`
- **Status:** `{record.status.value}`
- **Scheduled Time:** `{record.scheduled_at_local}` ({record.timezone})
- **Remote ID:** `{record.remote_id or 'None'}`
- **Remote URL:** {record.remote_url or 'None'}
- **Dry Run:** {record.dry_run}

---

## 📝 Publication Content
- **Title / Caption:** {record.title}
- **Description:** {record.description}
- **Hashtags:** `{' '.join(record.hashtags)}`

---

## 🔒 Verification & Safety
- **Video File:** `{record.video_file}`
- **SHA256 Fingerprint:** `{record.video_sha256}`
- **AI Content Disclosed:** {record.synthetic_media_disclosed}
- **Attempt Count:** {record.attempt_count}
- **Last Error:** {record.last_error or 'None'}

---

## 🌐 Graph Connections
- [[{record.reel_id}]]
- [[PUBLISH_AGENT]]
- [[{record.batch_id}]]
- [[PUBLISHING_QUEUE]]
- [[AGENT_CONTROL_CENTER]]
"""
        self._safe_write(rec_file, content)
        return rec_file

    def save_batch_note(self, batch: PublishingBatch) -> Path:
        """Create 13_PUBLISHING/PUB-BATCH-<TIMESTAMP>.md."""
        self._ensure_folders()
        batch_filename = f"{batch.batch_id}.md"
        batch_file = self.publishing_dir / batch_filename

        reels_links = "\n".join(f"- [[{r}]]" for r in batch.requested_reels)
        record_links = "\n".join(f"- [[PUB-{rec.reel_id}-{rec.platform.value.upper()}]]" for rec in batch.records)

        yt_success = sum(1 for r in batch.records if r.platform == Platform.YOUTUBE and r.status in (PlatformPublicationStatus.SCHEDULED, PlatformPublicationStatus.PUBLISHED))
        tt_success = sum(1 for r in batch.records if r.platform == Platform.TIKTOK and r.status in (PlatformPublicationStatus.SCHEDULED, PlatformPublicationStatus.PUBLISHED))
        failed_count = sum(1 for r in batch.records if r.status == PlatformPublicationStatus.FAILED)

        content = f"""---
node_type: publishing_batch
batch_id: {batch.batch_id}
status: {batch.status}
start_date: "{batch.start_date or ''}"
timezone: {batch.timezone}
requested_reels: {len(batch.requested_reels)}
youtube_scheduled: {yt_success}
tiktok_scheduled: {tt_success}
failed_count: {failed_count}
started_at: {batch.started_at}
finished_at: "{batch.finished_at or ''}"
tags:
  - publishing-batch
  - automation
---

# 📦 PUBLISHING BATCH: {batch.batch_id}

- **Orchestrated by:** [[PUBLISH_AGENT]]
- **Status:** `{batch.status}`
- **Start Date:** {batch.start_date or 'Immediate'}
- **Timezone:** {batch.timezone}
- **Daily Slots:** {', '.join(batch.slots)}

---

## 🎯 Target Reels
{reels_links or '- None'}

---

## 📢 Generated Publishing Records
{record_links or '- None'}

---

## 📊 Summary
- **YouTube Scheduled:** {yt_success} / {len(batch.requested_reels)}
- **TikTok Scheduled:** {tt_success} / {len(batch.requested_reels)}
- **Failed Records:** {failed_count}

---

## 🌐 Graph Connections
- [[PUBLISH_AGENT]]
- [[PUBLISHING_QUEUE]]
- [[AGENT_CONTROL_CENTER]]
"""
        self._safe_write(batch_file, content)
        return batch_file

    def update_publishing_queue(self, records: List[PublishRecord]) -> Path:
        """Create or update 13_PUBLISHING/PUBLISHING_QUEUE.md."""
        self._ensure_folders()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        grouped: Dict[str, Dict[Platform, PublishRecord]] = {}
        for r in records:
            if r.reel_id not in grouped:
                grouped[r.reel_id] = {}
            grouped[r.reel_id][r.platform] = r

        rows = []
        for reel_id, plats in grouped.items():
            yt_rec = plats.get(Platform.YOUTUBE)
            tt_rec = plats.get(Platform.TIKTOK)

            yt_status = f"{yt_rec.status.value} ({yt_rec.scheduled_at_local.split('T')[-1][:5]})" if yt_rec else "NOT QUEUED"
            tt_status = f"{tt_rec.status.value} ({tt_rec.scheduled_at_local.split('T')[-1][:5]})" if tt_rec else "NOT QUEUED"

            rows.append(f"| [[{reel_id}]] | {yt_status} | {tt_status} |")

        table_str = "\n".join(rows) if rows else "| None | - | - |"

        content = f"""---
node_type: publishing_queue
title: Live Publishing Queue
tags:
  - publishing
  - queue
---

# 📺 REELS AI FACTORY — LIVE PUBLISHING QUEUE

Last Updated: `{now_str}` | Supervisor: [[PUBLISH_AGENT]] | Dashboard: [[AGENT_CONTROL_CENTER]]

---

## 📊 Scheduled & Active Publications

| Reel ID | YouTube Shorts (@BuiIdVerse) | TikTok Studio (@kitchenverse360) |
| :--- | :--- | :--- |
{table_str}

---

## 🧭 İlgili Bağlantılar
- [[PUBLISH_AGENT]]
- [[AGENT_CONTROL_CENTER]]
- [[00_AGENTS/AGENT_ARCHITECTURE]]
"""
        self._safe_write(self.queue_file, content)
        return self.queue_file

    def load_all_records(self) -> Dict[str, PublishRecord]:
        """Scan 13_PUBLISHING/ and parse existing PublishRecord files."""
        records: Dict[str, PublishRecord] = {}
        if not self.publishing_dir.exists():
            return records

        for file_path in self.publishing_dir.glob("PUB-REEL-*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
                fm_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
                if not fm_match:
                    continue

                fm_text = fm_match.group(1)
                data: Dict[str, Any] = {}
                for line in fm_text.splitlines():
                    if ":" in line and not line.startswith("  -"):
                        k, v = line.split(":", 1)
                        data[k.strip()] = v.strip().strip('"').strip("'")

                reel_id = data.get("reel_id", "")
                plat_str = data.get("platform", "youtube").lower()
                plat = Platform.YOUTUBE if plat_str == "youtube" else Platform.TIKTOK
                is_dry_run = str(data.get("dry_run", "false")).lower() == "true"
                upload_started = str(data.get("upload_started", "false")).lower() == "true"
                remote_draft_exists = str(data.get("remote_draft_exists", "false")).lower() == "true"

                rec = PublishRecord(
                    publish_id=data.get("publish_id", file_path.stem),
                    batch_id=data.get("batch_id", ""),
                    reel_id=reel_id,
                    platform=plat,
                    video_file=Path(data.get("video_file", "")),
                    video_sha256=data.get("video_sha256", ""),
                    title="",
                    description="",
                    hashtags=[],
                    scheduled_at_local=data.get("scheduled_at_local", ""),
                    scheduled_at_utc=data.get("scheduled_at_utc", ""),
                    account_handle=data.get("account_handle", "@BuiIdVerse" if plat == Platform.YOUTUBE else "@kitchenverse360"),
                    timezone=data.get("timezone", "Europe/Istanbul"),
                    status=PlatformPublicationStatus(data.get("status", "PENDING")),
                    remote_id=data.get("remote_id") or None,
                    remote_url=data.get("remote_url") or None,
                    upload_started=upload_started,
                    remote_draft_exists=remote_draft_exists,
                    dry_run=is_dry_run,
                    attempt_count=int(data.get("attempt_count", 0)),
                    last_error=data.get("last_error") or None,
                    created_at=data.get("created_at", ""),
                    updated_at=data.get("updated_at", ""),
                    schedule_verified=str(data.get("schedule_verified", "false")).lower() == "true",
                    verified_schedule_date=data.get("verified_schedule_date") or None,
                    verified_schedule_time=data.get("verified_schedule_time") or None,
                    verified_remote_status=data.get("verified_remote_status") or None,
                    verified_at=data.get("verified_at") or None
                )
                key = f"{reel_id}_{plat.value}"
                records[key] = rec
            except Exception as e:
                logger.warning(f"Failed to parse publish record from {file_path.name}: {e}")

        return records

    def sanitize_existing_dry_run_records(self) -> int:
        """
        Scan 13_PUBLISHING/ and safely normalize any dry-run/mock records.
        """
        records = self.load_all_records()
        cleaned_count = 0
        for key, rec in records.items():
            if rec.dry_run or rec.status == PlatformPublicationStatus.METADATA_READY or (rec.remote_id and "mock" in rec.remote_id.lower()):
                rec.mark_dry_run()
                self.save_publish_record(rec)
                cleaned_count += 1

        if cleaned_count > 0:
            self.update_publishing_queue(list(records.values()))
        return cleaned_count

    def update_reel_publishing_metadata(
        self,
        reel_id: str,
        yt_title: str,
        yt_desc: str,
        yt_tags: List[str],
        tt_caption: str,
        tt_tags: List[str]
    ) -> None:
        """Inject or update ## Publishing Metadata section in the Reel's note."""
        target_note = None
        for folder in ["05_READY", "04_PRODUCTION", "03_SCRIPTS"]:
            p = self.vault_path / folder / f"{reel_id}.md"
            if p.exists():
                target_note = p
                break

        if not target_note:
            return

        content = target_note.read_text(encoding="utf-8")
        pub_meta_block = f"""
---

# Publishing Metadata

### YouTube Shorts
- **Title:** {yt_title}
- **Description:** {yt_desc}
- **Hashtags:** `{' '.join(yt_tags)}`

### TikTok Studio
- **Caption:** {tt_caption}
- **Hashtags:** `{' '.join(tt_tags)}`

---
"""
        if "# Publishing Metadata" not in content:
            if "# Agent Graph" in content:
                content = content.replace("# Agent Graph", pub_meta_block + "\n# Agent Graph")
            else:
                content += "\n" + pub_meta_block

        yt_pub_link = f"- [[PUB-{reel_id}-YOUTUBE]]"
        tt_pub_link = f"- [[PUB-{reel_id}-TIKTOK]]"
        if yt_pub_link not in content:
            content += f"\n- **Publishing Records:**\n  {yt_pub_link}\n  {tt_pub_link}\n"

        self._safe_write(target_note, content)
