"""Export Engine — orchestrates a full or partial tenant export.

Usage::

    from gwsdsc.config import load_tenant_config
    from gwsdsc.engine.export_engine import ExportEngine

    cfg = load_tenant_config("config/tenant.yaml")
    engine = ExportEngine(cfg)
    snapshot = engine.run()
    # snapshot is a dict: { "metadata": {...}, "resources": { "users": [...], ... } }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gwsdsc.config import TenantConfig, load_resource_catalogue
from gwsdsc.resources import ALL_RESOURCE_NAMES, REGISTRY

logger = logging.getLogger(__name__)


class ExportEngine:
    """Fetches configuration from a Google Workspace tenant and writes
    versioned JSON artifacts to the configured store."""

    def __init__(self, config: TenantConfig) -> None:
        self.config = config
        self.catalogue = load_resource_catalogue()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        resource_names: list[str] | None = None,
        output_dir: str | Path | None = None,
    ) -> dict[str, Any]:
        """Execute the export and return the snapshot dict.

        Parameters
        ----------
        resource_names
            Specific resources to export. ``None`` or ``["all"]`` means
            everything minus ``config.exclude_resources``.
        output_dir
            Directory to write JSON artifacts. Defaults to
            ``<store.path>/<timestamp>/``.
        """
        names = self._resolve_names(resource_names)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        out = Path(output_dir) if output_dir else Path(self.config.store.path) / timestamp
        out.mkdir(parents=True, exist_ok=True)

        logger.info("Starting export: resources=%s, output=%s", names, out)

        snapshot: dict[str, Any] = {
            "metadata": {
                "tenant_name": self.config.tenant_name,
                "primary_domain": self.config.primary_domain,
                "customer_id": self.config.customer_id,
                "exported_at": timestamp,
                "resources_exported": names,
                "gwsdsc_version": "0.1.0",
            },
            "resources": {},
        }

        errors: dict[str, str] = {}

        for name in names:
            logger.info("Exporting resource: %s", name)
            try:
                cls = REGISTRY[name]
                options = self.config.export_options.get(name, {})
                resource = cls(
                    credentials_config=self.config.credentials,
                    customer_id=self.config.customer_id,
                    options=options,
                )
                items = resource.export_cleaned()
                snapshot["resources"][name] = items

                # Write individual resource file
                resource_file = out / f"{name}.json"
                resource_file.write_text(
                    json.dumps(items, indent=2, default=str, ensure_ascii=False)
                )
                logger.info("  %s: %d items exported", name, len(items))

            except Exception as exc:
                msg = f"Failed to export {name}: {exc}"
                logger.error(msg)
                errors[name] = str(exc)
                snapshot["resources"][name] = {"_error": str(exc)}

        # Write metadata
        (out / "_metadata.json").write_text(
            json.dumps(snapshot["metadata"], indent=2)
        )

        # Write error summary if any
        if errors:
            snapshot["metadata"]["errors"] = errors
            (out / "_errors.json").write_text(json.dumps(errors, indent=2))

        # Write combined snapshot
        (out / "_snapshot.json").write_text(
            json.dumps(snapshot, indent=2, default=str, ensure_ascii=False)
        )

        # Maintain a "latest" pointer (cross-platform — no symlinks)
        _write_latest_pointer(Path(self.config.store.path), out)

        logger.info(
            "Export complete: %d resources, %d errors, output=%s",
            len(names) - len(errors),
            len(errors),
            out,
        )
        return snapshot

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_names(self, resource_names: list[str] | None) -> list[str]:
        """Turn user input into a concrete list of resource names."""
        cfg_names = resource_names or self.config.resources
        if "all" in cfg_names:
            names = list(ALL_RESOURCE_NAMES)
        else:
            names = [n for n in cfg_names if n in REGISTRY]

        excluded = set(self.config.exclude_resources)
        names = [n for n in names if n not in excluded]
        return sorted(names)


# ---------------------------------------------------------------------------
# Cross-platform "latest" pointer (replaces symlinks)
# ---------------------------------------------------------------------------


def _write_latest_pointer(store_path: Path, snapshot_dir: Path) -> None:
    """Write a ``latest.json`` pointer file instead of a symlink.

    Symlinks require Developer Mode or admin privileges on Windows and
    behave inconsistently in Git across platforms.  A JSON pointer is
    universally portable.
    """
    pointer = store_path / "latest.json"
    pointer.write_text(json.dumps({
        "path": str(snapshot_dir.resolve()),
        "name": snapshot_dir.name,
    }, indent=2))


def resolve_latest(store_path: str | Path) -> Path | None:
    """Resolve the latest snapshot directory from the ``latest.json`` pointer.

    Returns ``None`` if no pointer exists or the target directory is missing.
    """
    pointer = Path(store_path) / "latest.json"
    if not pointer.exists():
        return None
    try:
        data = json.loads(pointer.read_text())
        target = Path(data["path"])
        if target.is_dir():
            return target
    except (json.JSONDecodeError, KeyError):
        pass
    return None
