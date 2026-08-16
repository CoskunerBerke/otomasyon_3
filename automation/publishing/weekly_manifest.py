"""
Weekly Schedule Manifest Generator and Obsidian Dashboard Synchronizer.
Manages weekly publishing plans (7 days x 2 daily slots = 14 videos) and live dashboards.
"""
import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .models import PublishBatch, PublishRecord, Platform, PlatformPublicationStatus
from .config import PublishingConfig

logger = logging.getLogger("ReelsAIFactory.WeeklyManifest")

class WeeklyManifestManager:
    """Manages weekly_schedule.json and Obsidian WEEKLY_PUBLISHING_DASHBOARD.md."""

    @staticmethod
    def generate_manifest_dict(
        batch: PublishBatch,
        config: PublishingConfig
    ) -> Dict[str, Any]:
        """Generate structured weekly manifest dictionary for export."""
        slots = []
        for i, (reel_id, local_dt, utc_dt) in enumerate(batch.schedule_slots, start=1):
            yt_rec = next((r for r in batch.records if r.reel_id == reel_id and r.platform == Platform.YOUTUBE), None)
            tt_rec = next((r for r in batch.records if r.reel_id == reel_id and r.platform == Platform.TIKTOK), None)

            slot_item = {
                "slot_number": i,
                "reel_id": reel_id,
                "scheduled_at_local": local_dt,
                "scheduled_at_utc": utc_dt,
                "youtube": {
                    "title": yt_rec.title if yt_rec else "",
                    "description": yt_rec.description if yt_rec else "",
                    "hashtags": yt_rec.hashtags if yt_rec else [],
                    "status": yt_rec.status.value if yt_rec else "UNASSIGNED",
                    "remote_url": yt_rec.remote_url if yt_rec else None
                },
                "tiktok": {
                    "caption": tt_rec.description if tt_rec else "",
                    "hashtags": tt_rec.hashtags if tt_rec else [],
                    "status": tt_rec.status.value if tt_rec else "UNASSIGNED",
                    "remote_url": tt_rec.remote_url if tt_rec else None
                }
            }
            slots.append(slot_item)

        manifest = {
            "batch_id": batch.batch_id,
            "created_at": batch.created_at,
            "start_date": config.schedule_start_date,
            "timezone": config.timezone,
            "daily_slots": config.daily_slots,
            "total_slots": len(slots),
            "youtube_target": config.youtube_expected_handle,
            "tiktok_target": config.tiktok_expected_username,
            "slots": slots
        }
        return manifest

    @staticmethod
    def write_manifest_files(
        vault_path: Path,
        batch: PublishBatch,
        config: PublishingConfig
    ) -> Tuple[Path, Path]:
        """Write weekly_schedule.json and 13_PUBLISHING/WEEKLY_PUBLISHING_DASHBOARD.md."""
        publishing_dir = vault_path / "13_PUBLISHING"
        publishing_dir.mkdir(parents=True, exist_ok=True)

        manifest_data = WeeklyManifestManager.generate_manifest_dict(batch, config)

        # 1. Write weekly_schedule.json
        json_path = publishing_dir / "weekly_schedule.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

        # 2. Render Markdown Dashboard
        md_path = publishing_dir / "WEEKLY_PUBLISHING_DASHBOARD.md"

        yt_scheduled_count = sum(1 for r in batch.records if r.platform == Platform.YOUTUBE and r.status == PlatformPublicationStatus.SCHEDULED)
        tt_scheduled_count = sum(1 for r in batch.records if r.platform == Platform.TIKTOK and r.status == PlatformPublicationStatus.SCHEDULED)
        total_reels = len(batch.requested_reels)

        rows = []
        for slot in manifest_data["slots"]:
            s_num = slot["slot_number"]
            r_id = slot["reel_id"]
            s_time = slot["scheduled_at_local"].replace("T", " ")[:16]
            yt_st = slot["youtube"]["status"]
            tt_st = slot["tiktok"]["status"]
            yt_title = slot["youtube"]["title"][:35] + "..." if len(slot["youtube"]["title"]) > 35 else slot["youtube"]["title"]

            yt_icon = "🟢" if yt_st == "SCHEDULED" else ("🟡" if "READY" in yt_st or "DRY" in yt_st else "🔴")
            tt_icon = "🟢" if tt_st == "SCHEDULED" else ("🟡" if "READY" in tt_st or "DRY" in tt_st else "🔴")

            rows.append(f"| {s_num:02d} | [[05_READY/{r_id}\\|{r_id}]] | {s_time} | {yt_title} | {yt_icon} {yt_st} | {tt_icon} {tt_st} |")

        table_content = "\n".join(rows)

        content = f"""---
title: Weekly Publishing Dashboard
batch_id: {batch.batch_id}
start_date: {config.schedule_start_date}
timezone: {config.timezone}
total_reels: {total_reels}
youtube_target: "{config.youtube_expected_handle}"
tiktok_target: "{config.tiktok_expected_username}"
---

# 📅 WEEKLY PUBLISHING DASHBOARD — 7 DAY SCHEDULE
> **Batch ID:** `{batch.batch_id}`  
> **Schedule Range:** `{config.schedule_start_date}` — 7 Days (14 Slots: `19:30` & `22:00` {config.timezone})  
> **YouTube Channel:** `{config.youtube_expected_handle}` (`{config.youtube_expected_channel_id or 'UCahsmsqzTCtwTDDtvCurtBA'}`)  
> **TikTok Account:** `{config.tiktok_expected_username}`  

---

### 📊 Publishing Summary
* **Total Videos in Batch:** `{total_reels} / 14`
* **YouTube Shorts Scheduled:** `{yt_scheduled_count} / {total_reels}`
* **TikTok Studio Scheduled:** `{tt_scheduled_count} / {total_reels}`
* **Batch Status:** `{batch.status}`

---

### 🗓️ 14-Slot Publishing Matrix

| Slot | Reel ID | Scheduled Date / Time | Concept Title | YouTube Status | TikTok Status |
| :---: | :--- | :--- | :--- | :--- | :--- |
{table_content}

---
*Generated by Reels AI Factory Weekly Publishing Agent V1.*
"""
        md_path.write_text(content, encoding="utf-8")
        logger.info(f"Updated Weekly Dashboard: {md_path.name}")
        return json_path, md_path
