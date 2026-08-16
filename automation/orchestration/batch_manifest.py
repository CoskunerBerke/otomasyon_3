"""
Batch Manifest & Progress models for the simplified, deterministic weekly pipeline
(automation/simple_weekly_pipeline.py).

manifest.json is the IMMUTABLE content plan for a week once status == "LOCKED": which
14 Reel IDs exist, which video belongs to which, and what metadata/schedule slot it has.
progress.json is the MUTABLE per-platform publishing status, kept in a separate file so a
platform failure can never touch the content plan.

Both live under workspace/batches/<week_id>/ (gitignored, local machine state only), using
the same atomic temp-file-then-replace write pattern as StateRepository.
"""
import json
import logging
import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ReelsAIFactory.BatchManifest")


def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class BatchReel:
    """One immutable-once-locked content entry: exactly one Reel ID, one video, one slot."""
    index: int
    reel_id: str
    scheduled_at_local: str
    scheduled_at_utc: str
    topic_key: str = ""
    title: str = ""
    caption: str = ""
    hashtags: List[str] = field(default_factory=list)
    pipeline_version: int = 3
    content_mode: str = "silent_global_step_by_step"
    video_path: Optional[str] = None
    video_sha256: Optional[str] = None
    # NOT_STARTED | COMPLETE | FAILED -- Phase 1 (GENERATE) outcome for this Reel only.
    generation_status: str = "NOT_STARTED"
    generation_error: Optional[str] = None
    # Raw ReelConceptPlan selector fields, persisted so the *exact same* plan (same
    # prompt, same segments) can be deterministically rebuilt via
    # PromptEngine.build_concept_plan() on a later, separate process run -- metadata
    # decided at manifest-creation time must never drift at actual generation time.
    concept_id_slug: str = ""
    environment: str = ""
    architecture: str = ""
    transformation: str = ""
    camera_style: str = ""
    lighting: str = ""
    materials: str = ""
    reveal: str = ""
    diversity_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "reel_id": self.reel_id,
            "scheduled_at_local": self.scheduled_at_local,
            "scheduled_at_utc": self.scheduled_at_utc,
            "topic_key": self.topic_key,
            "title": self.title,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "pipeline_version": self.pipeline_version,
            "content_mode": self.content_mode,
            "video_path": self.video_path,
            "video_sha256": self.video_sha256,
            "generation_status": self.generation_status,
            "generation_error": self.generation_error,
            "concept_id_slug": self.concept_id_slug,
            "environment": self.environment,
            "architecture": self.architecture,
            "transformation": self.transformation,
            "camera_style": self.camera_style,
            "lighting": self.lighting,
            "materials": self.materials,
            "reveal": self.reveal,
            "diversity_score": self.diversity_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchReel":
        return cls(
            index=data.get("index", 0),
            reel_id=data.get("reel_id", ""),
            scheduled_at_local=data.get("scheduled_at_local", ""),
            scheduled_at_utc=data.get("scheduled_at_utc", ""),
            topic_key=data.get("topic_key", ""),
            title=data.get("title", ""),
            caption=data.get("caption", ""),
            hashtags=data.get("hashtags", []),
            pipeline_version=data.get("pipeline_version", 3),
            content_mode=data.get("content_mode", "silent_global_step_by_step"),
            video_path=data.get("video_path"),
            video_sha256=data.get("video_sha256"),
            generation_status=data.get("generation_status", "NOT_STARTED"),
            generation_error=data.get("generation_error"),
            concept_id_slug=data.get("concept_id_slug", ""),
            environment=data.get("environment", ""),
            architecture=data.get("architecture", ""),
            transformation=data.get("transformation", ""),
            camera_style=data.get("camera_style", ""),
            lighting=data.get("lighting", ""),
            materials=data.get("materials", ""),
            reveal=data.get("reveal", ""),
            diversity_score=data.get("diversity_score", 0.0),
        )


@dataclass
class BatchManifest:
    """The week's immutable-once-locked production plan."""
    week_id: str
    start_date: str
    timezone: str = "Europe/Istanbul"
    target_reels: int = 14
    # DRAFT -> LOCKED. Only these two values exist. Publishing phases refuse to run
    # against anything other than LOCKED.
    status: str = "DRAFT"
    reels: List[BatchReel] = field(default_factory=list)
    created_at: str = field(default_factory=_now_str)
    updated_at: str = field(default_factory=_now_str)
    locked_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "week_id": self.week_id,
            "start_date": self.start_date,
            "timezone": self.timezone,
            "target_reels": self.target_reels,
            "status": self.status,
            "reels": [r.to_dict() for r in self.reels],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "locked_at": self.locked_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchManifest":
        return cls(
            week_id=data.get("week_id", ""),
            start_date=data.get("start_date", ""),
            timezone=data.get("timezone", "Europe/Istanbul"),
            target_reels=data.get("target_reels", 14),
            status=data.get("status", "DRAFT"),
            reels=[BatchReel.from_dict(r) for r in data.get("reels", [])],
            created_at=data.get("created_at", _now_str()),
            updated_at=data.get("updated_at", _now_str()),
            locked_at=data.get("locked_at"),
        )

    def reel_ids(self) -> List[str]:
        return [r.reel_id for r in self.reels]

    def get_reel(self, reel_id: str) -> Optional[BatchReel]:
        for r in self.reels:
            if r.reel_id == reel_id:
                return r
        return None


def default_progress_entry() -> Dict[str, Any]:
    """The starting per-platform status skeleton for a single Reel ID."""
    return {
        "youtube": {"status": "PENDING", "remote_id": None, "url": None, "error": None},
        "tiktok": {"status": "PENDING", "remote_id": None, "url": None, "error": None},
        "instagram": {"status": "PENDING", "remote_media_id": None, "error": None},
    }


class BatchRepository:
    """Atomic reader/writer for workspace/batches/<week_id>/{manifest,progress}.json."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = (base_dir or Path(".").resolve())
        self.batches_dir = self.base_dir / "workspace" / "batches"

    def batch_dir(self, week_id: str) -> Path:
        return self.batches_dir / week_id

    def manifest_path(self, week_id: str) -> Path:
        return self.batch_dir(week_id) / "manifest.json"

    def progress_path(self, week_id: str) -> Path:
        return self.batch_dir(week_id) / "progress.json"

    def _atomic_write_json(self, target_path: Path, data: Dict[str, Any]) -> bool:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                import os
                os.fsync(f.fileno())
            tmp_path.replace(target_path)
            return True
        except Exception as e:
            logger.error(f"[BATCH REPO] Atomic write failed for {target_path.name}: {e}")
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return False

    # -- manifest --------------------------------------------------------

    def load_manifest(self, week_id: str) -> Optional[BatchManifest]:
        path = self.manifest_path(week_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return BatchManifest.from_dict(json.load(f))
        except Exception as e:
            logger.error(f"[BATCH REPO] Error loading manifest {week_id}: {e}")
            return None

    def save_manifest(self, manifest: BatchManifest) -> bool:
        manifest.updated_at = _now_str()
        return self._atomic_write_json(self.manifest_path(manifest.week_id), manifest.to_dict())

    # -- progress ----------------------------------------------------------

    def load_progress(self, week_id: str) -> Dict[str, Any]:
        path = self.progress_path(week_id)
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[BATCH REPO] Error loading progress {week_id}: {e}")
            return {}

    def save_progress(self, week_id: str, progress: Dict[str, Any]) -> bool:
        return self._atomic_write_json(self.progress_path(week_id), progress)

    def ensure_progress_entries(self, week_id: str, reel_ids: List[str]) -> Dict[str, Any]:
        """Loads progress.json, adds a PENDING skeleton for any missing reel_id, saves, returns it."""
        progress = self.load_progress(week_id)
        changed = False
        for reel_id in reel_ids:
            if reel_id not in progress:
                progress[reel_id] = default_progress_entry()
                changed = True
        if changed:
            self.save_progress(week_id, progress)
        return progress

    def update_platform_status(
        self,
        week_id: str,
        reel_id: str,
        platform: str,
        status: str,
        **fields: Any
    ) -> bool:
        """Atomically updates one platform's status (and any extra fields) for one Reel."""
        progress = self.load_progress(week_id)
        if reel_id not in progress:
            progress[reel_id] = default_progress_entry()
        progress[reel_id].setdefault(platform, {})
        progress[reel_id][platform]["status"] = status
        for k, v in fields.items():
            progress[reel_id][platform][k] = v
        return self.save_progress(week_id, progress)
