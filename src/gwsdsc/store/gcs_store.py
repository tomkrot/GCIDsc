"""Google Cloud Storage–based versioned artifact store.

Uses GCS object versioning or timestamped prefixes to maintain an
append-only history of tenant snapshots.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gwsdsc.config import StoreConfig
from gwsdsc.store.base import BaseStore

logger = logging.getLogger(__name__)


class GCSStore(BaseStore):
    """Persist snapshots to a GCS bucket with object versioning."""

    def __init__(self, config: StoreConfig) -> None:
        self.config = config
        if not config.gcs_bucket:
            raise ValueError("StoreConfig.gcs_bucket is required for GCS store")
        self.bucket_name = config.gcs_bucket
        self.prefix = config.gcs_prefix.rstrip("/") + "/"
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client()
        return self._client

    @property
    def bucket(self):
        return self.client.bucket(self.bucket_name)

    def commit(self, snapshot_dir: Path, message: str | None = None) -> str:
        """Upload all files in snapshot_dir to GCS under a timestamped prefix."""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        version_prefix = f"{self.prefix}{timestamp}/"

        count = 0
        for file_path in snapshot_dir.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(snapshot_dir)
                blob_name = f"{version_prefix}{relative}"
                blob = self.bucket.blob(blob_name)
                blob.upload_from_filename(str(file_path))
                count += 1

        # Write a version marker
        marker = self.bucket.blob(f"{version_prefix}_version.json")
        marker.upload_from_string(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "message": message or f"Export {timestamp}",
                    "file_count": count,
                }
            )
        )

        # Update "latest" pointer
        latest_blob = self.bucket.blob(f"{self.prefix}latest.json")
        latest_blob.upload_from_string(
            json.dumps({"latest_version": timestamp})
        )

        logger.info(
            "Uploaded %d files to gs://%s/%s", count, self.bucket_name, version_prefix
        )
        return timestamp

    def list_versions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List available snapshot versions by scanning GCS prefixes."""
        versions: list[dict[str, Any]] = []
        blobs = self.client.list_blobs(
            self.bucket_name,
            prefix=self.prefix,
            delimiter="/",
        )
        # Consume the iterator to populate prefixes
        list(blobs)

        for prefix in sorted(blobs.prefixes, reverse=True)[:limit]:
            # Each prefix is like "exports/2025-03-09T000000Z/"
            version_name = prefix.rstrip("/").split("/")[-1]
            marker_blob = self.bucket.blob(f"{prefix}_version.json")
            meta: dict[str, Any] = {"version": version_name}
            if marker_blob.exists():
                data = json.loads(marker_blob.download_as_text())
                meta.update(data)
            versions.append(meta)

        return versions

    def checkout(self, version: str, target_dir: Path) -> Path:
        """Download a specific version from GCS to a local directory."""
        version_prefix = f"{self.prefix}{version}/"
        target_dir.mkdir(parents=True, exist_ok=True)

        blobs = self.client.list_blobs(self.bucket_name, prefix=version_prefix)
        count = 0
        for blob in blobs:
            relative = blob.name[len(version_prefix):]
            if not relative or relative.startswith("_"):
                continue
            local_path = target_dir / relative
            local_path.parent.mkdir(parents=True, exist_ok=True)
            blob.download_to_filename(str(local_path))
            count += 1

        logger.info("Downloaded %d files from gs://%s/%s", count, self.bucket_name, version_prefix)
        return target_dir
