"""
Media Storage Abstraction for Cloud Control Plane and Workers.
Provides vendor-independent object storage (Local Development Storage and S3-Compatible Storage).
Implements real S3 operations using boto3 for Railway Storage Bucket with private ACLs and region support.
"""
import os
import shutil
import hashlib
import logging
import datetime
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger("ReelsAIFactory.MediaStorage")

from .config import CloudConfig, mask_secret


def compute_file_sha256(path: Path) -> str:
    """Computes SHA256 digest of a local file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class MediaStorageInterface(ABC):
    """Abstract interface for object storage."""

    @abstractmethod
    def put_file(self, local_path: Path, object_key: str, content_type: str = "video/mp4") -> str:
        pass

    @abstractmethod
    def get_file(self, object_key: str, target_path: Path) -> bool:
        pass

    @abstractmethod
    def delete_file(self, object_key: str) -> bool:
        pass

    @abstractmethod
    def exists(self, object_key: str) -> bool:
        pass

    @abstractmethod
    def get_metadata(self, object_key: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        pass

    @abstractmethod
    def cleanup_expired_objects(self, retention_days: int = 7, enable_cleanup: bool = False) -> Dict[str, Any]:
        pass


class LocalMediaStorageAdapter(MediaStorageInterface):
    """Local filesystem adapter simulating cloud object storage for development."""

    def __init__(self, root_dir: Optional[Path] = None):
        self.root_dir = (root_dir or Path("workspace/cloud_media_storage")).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, object_key: str) -> Path:
        clean_key = object_key.lstrip("/").replace("\\", "/")
        return self.root_dir / clean_key

    def is_ready(self) -> bool:
        return self.root_dir.exists()

    def put_file(self, local_path: Path, object_key: str, content_type: str = "video/mp4") -> str:
        if not local_path.exists():
            raise FileNotFoundError(f"Local file does not exist: {local_path}")
        target = self._get_path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, target)
        logger.info(f"[STORAGE] Stored local object '{object_key}' ({target.stat().st_size} bytes)")
        return object_key

    def get_file(self, object_key: str, target_path: Path) -> bool:
        src = self._get_path(object_key)
        if not src.exists():
            return False
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target_path)
        return True

    def delete_file(self, object_key: str) -> bool:
        p = self._get_path(object_key)
        if p.exists():
            p.unlink()
            return True
        return False

    def exists(self, object_key: str) -> bool:
        return self._get_path(object_key).exists()

    def get_metadata(self, object_key: str) -> Dict[str, Any]:
        p = self._get_path(object_key)
        if not p.exists():
            return {}
        return {
            "object_key": object_key,
            "size_bytes": p.stat().st_size,
            "sha256": compute_file_sha256(p),
            "content_type": "video/mp4"
        }

    def cleanup_expired_objects(self, retention_days: int = 7, enable_cleanup: bool = False) -> Dict[str, Any]:
        """Identifies and optionally deletes objects older than retention_days."""
        cutoff = datetime.datetime.now() - datetime.timedelta(days=retention_days)
        candidates = []
        deleted = []

        for p in self.root_dir.glob("**/*"):
            if p.is_file():
                mtime = datetime.datetime.fromtimestamp(p.stat().st_mtime)
                if mtime < cutoff:
                    candidates.append(str(p.relative_to(self.root_dir)))
                    if enable_cleanup:
                        try:
                            p.unlink()
                            deleted.append(str(p.relative_to(self.root_dir)))
                        except Exception as e:
                            logger.error(f"[STORAGE CLEANUP] Failed to delete {p}: {e}")

        return {
            "retention_days": retention_days,
            "enable_cleanup": enable_cleanup,
            "candidate_count": len(candidates),
            "cleaned_count": len(deleted),
            "candidates": candidates
        }


class S3MediaStorageAdapter(MediaStorageInterface):
    """Real S3-compatible storage adapter for Railway Storage Bucket, AWS S3, Cloudflare R2."""

    def __init__(
        self,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "auto",
        s3_client: Optional[Any] = None
    ):
        self.endpoint_url = endpoint_url.strip()
        self.bucket = bucket.strip()
        self.access_key = access_key.strip()
        self.secret_key = secret_key.strip()
        self.region = region.strip() if region else "auto"
        self._custom_client = s3_client

    def is_ready(self) -> bool:
        return bool(self.endpoint_url and self.bucket and self.access_key and self.secret_key)

    def _get_client(self):
        """Constructs or returns boto3 S3 client."""
        if self._custom_client is not None:
            return self._custom_client

        if not self.is_ready():
            raise RuntimeError("S3MediaStorageAdapter credentials not fully configured.")

        try:
            import boto3
            from botocore.config import Config
        except ImportError:
            raise RuntimeError("boto3 package is required for S3MediaStorageAdapter.")

        cfg = Config(
            signature_version="s3v4",
            s3={"addressing_style": "auto"}
        )
        
        region_name = self.region if self.region and self.region.lower() != "auto" else None

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=region_name,
            config=cfg
        )

    def _clean_key(self, object_key: str) -> str:
        return object_key.lstrip("/").replace("\\", "/")

    def put_file(self, local_path: Path, object_key: str, content_type: str = "video/mp4") -> str:
        if not local_path.exists():
            raise FileNotFoundError(f"Local file does not exist: {local_path}")
        clean_key = self._clean_key(object_key)
        client = self._get_client()

        logger.info(f"[S3 STORAGE] Uploading '{clean_key}' to bucket '{self.bucket}' ({local_path.stat().st_size} bytes)")
        client.upload_file(
            Filename=str(local_path),
            Bucket=self.bucket,
            Key=clean_key,
            ExtraArgs={"ContentType": content_type}
        )
        return clean_key

    def get_file(self, object_key: str, target_path: Path) -> bool:
        clean_key = self._clean_key(object_key)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        client = self._get_client()

        try:
            logger.info(f"[S3 STORAGE] Downloading '{clean_key}' from bucket '{self.bucket}' to '{target_path}'")
            client.download_file(
                Bucket=self.bucket,
                Key=clean_key,
                Filename=str(target_path)
            )
            return target_path.exists()
        except Exception as e:
            logger.error(f"[S3 STORAGE] Failed to download '{clean_key}': {e}")
            return False

    def delete_file(self, object_key: str) -> bool:
        clean_key = self._clean_key(object_key)
        client = self._get_client()
        try:
            logger.info(f"[S3 STORAGE] Deleting '{clean_key}' from bucket '{self.bucket}'")
            client.delete_object(Bucket=self.bucket, Key=clean_key)
            return True
        except Exception as e:
            logger.error(f"[S3 STORAGE] Failed to delete '{clean_key}': {e}")
            return False

    def exists(self, object_key: str) -> bool:
        clean_key = self._clean_key(object_key)
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket, Key=clean_key)
            return True
        except Exception:
            return False

    def get_metadata(self, object_key: str) -> Dict[str, Any]:
        clean_key = self._clean_key(object_key)
        client = self._get_client()
        try:
            resp = client.head_object(Bucket=self.bucket, Key=clean_key)
            etag = resp.get("ETag", "").strip('"')
            return {
                "object_key": clean_key,
                "bucket": self.bucket,
                "size_bytes": resp.get("ContentLength", 0),
                "content_type": resp.get("ContentType", "video/mp4"),
                "etag": etag,
                "last_modified": str(resp.get("LastModified", ""))
            }
        except Exception as e:
            logger.warning(f"[S3 STORAGE] Could not fetch metadata for '{clean_key}': {e}")
            return {}

    def cleanup_expired_objects(self, retention_days: int = 7, enable_cleanup: bool = False) -> Dict[str, Any]:
        """Identifies expired objects in S3 bucket. Deletion only executed if enable_cleanup=True."""
        client = self._get_client()
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=retention_days)
        candidates = []
        cleaned = []

        try:
            paginator = client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket):
                for obj in page.get("Contents", []):
                    last_mod = obj.get("LastModified")
                    if last_mod and last_mod < cutoff:
                        k = obj.get("Key")
                        candidates.append(k)
                        if enable_cleanup and k:
                            try:
                                client.delete_object(Bucket=self.bucket, Key=k)
                                cleaned.append(k)
                            except Exception as del_err:
                                logger.error(f"[S3 STORAGE CLEANUP] Failed to delete '{k}': {del_err}")
        except Exception as e:
            logger.error(f"[S3 STORAGE CLEANUP] Error scanning bucket '{self.bucket}': {e}")

        return {
            "retention_days": retention_days,
            "enable_cleanup": enable_cleanup,
            "candidate_count": len(candidates),
            "cleaned_count": len(cleaned),
            "candidates": candidates
        }


def get_media_storage(config: CloudConfig) -> MediaStorageInterface:
    """Factory helper returning the configured media storage adapter."""
    if config.media_storage_backend == "s3" and config.s3_bucket:
        return S3MediaStorageAdapter(
            endpoint_url=config.s3_endpoint_url,
            bucket=config.s3_bucket,
            access_key=config.s3_access_key_id,
            secret_key=config.s3_secret_access_key,
            region=config.s3_region
        )
    return LocalMediaStorageAdapter(config.base_dir / "workspace" / "cloud_media_storage")
