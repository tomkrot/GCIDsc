"""Diff Engine — semantic comparison between two configuration snapshots.

Produces a structured diff that identifies added, removed, and modified
resources between a *baseline* and a *target* snapshot.  The diff is
resource-aware: items are matched by their canonical key (e.g.
``primaryEmail`` for users) rather than list position.

Usage::

    from gwsdsc.engine.diff_engine import DiffEngine

    diff = DiffEngine.compare(
        baseline_dir="artifacts/2025-03-01T000000Z",
        target_dir="artifacts/2025-03-09T000000Z",
    )
    # diff is a DiffResult
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deepdiff import DeepDiff

from gwsdsc.resources import REGISTRY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes for structured diff output
# ---------------------------------------------------------------------------


@dataclass
class ItemChange:
    """A single changed item within a resource."""

    key: str
    change_type: str  # "added", "removed", "modified"
    details: dict[str, Any] = field(default_factory=dict)
    baseline_value: dict[str, Any] | None = None
    target_value: dict[str, Any] | None = None


@dataclass
class ResourceDiff:
    """Diff result for one resource type."""

    resource_name: str
    added: list[ItemChange] = field(default_factory=list)
    removed: list[ItemChange] = field(default_factory=list)
    modified: list[ItemChange] = field(default_factory=list)
    baseline_count: int = 0
    target_count: int = 0

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0


@dataclass
class DiffResult:
    """Complete diff between two snapshots."""

    baseline_path: str
    target_path: str
    baseline_metadata: dict[str, Any] = field(default_factory=dict)
    target_metadata: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, ResourceDiff] = field(default_factory=dict)

    @property
    def total_changes(self) -> int:
        return sum(r.total_changes for r in self.resources.values())

    @property
    def has_changes(self) -> bool:
        return self.total_changes > 0

    @property
    def summary(self) -> dict[str, Any]:
        """Human-readable summary dict."""
        return {
            "baseline": self.baseline_path,
            "target": self.target_path,
            "total_changes": self.total_changes,
            "resources": {
                name: {
                    "added": len(rd.added),
                    "removed": len(rd.removed),
                    "modified": len(rd.modified),
                    "baseline_count": rd.baseline_count,
                    "target_count": rd.target_count,
                }
                for name, rd in self.resources.items()
                if rd.has_changes
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialise the full diff to JSON."""
        return json.dumps(self._as_dict(), indent=indent, default=str)

    def _as_dict(self) -> dict[str, Any]:
        return {
            "baseline": self.baseline_path,
            "target": self.target_path,
            "baseline_metadata": self.baseline_metadata,
            "target_metadata": self.target_metadata,
            "total_changes": self.total_changes,
            "resources": {
                name: {
                    "added": [vars(c) for c in rd.added],
                    "removed": [vars(c) for c in rd.removed],
                    "modified": [vars(c) for c in rd.modified],
                    "baseline_count": rd.baseline_count,
                    "target_count": rd.target_count,
                }
                for name, rd in self.resources.items()
            },
        }


# ---------------------------------------------------------------------------
# Diff Engine
# ---------------------------------------------------------------------------


class DiffEngine:
    """Compare two snapshot directories and produce a structured diff."""

    @staticmethod
    def compare(
        baseline_dir: str | Path,
        target_dir: str | Path,
        resource_names: list[str] | None = None,
    ) -> DiffResult:
        """Compare *baseline* and *target* snapshot directories.

        Parameters
        ----------
        baseline_dir, target_dir
            Paths to snapshot directories (each containing ``<resource>.json`` files).
        resource_names
            Limit comparison to these resources. ``None`` compares all found.
        """
        baseline = Path(baseline_dir).resolve()
        target = Path(target_dir).resolve()

        result = DiffResult(
            baseline_path=str(baseline),
            target_path=str(target),
        )

        # Load metadata if available
        for meta_name in ("_metadata.json",):
            bp = baseline / meta_name
            tp = target / meta_name
            if bp.exists():
                result.baseline_metadata = json.loads(bp.read_text())
            if tp.exists():
                result.target_metadata = json.loads(tp.read_text())

        # Discover resources to compare
        baseline_files = {p.stem for p in baseline.glob("*.json") if not p.stem.startswith("_")}
        target_files = {p.stem for p in target.glob("*.json") if not p.stem.startswith("_")}
        all_resources = baseline_files | target_files

        if resource_names:
            all_resources = all_resources & set(resource_names)

        for resource_name in sorted(all_resources):
            b_items = _load_resource(baseline / f"{resource_name}.json")
            t_items = _load_resource(target / f"{resource_name}.json")

            rd = _diff_resource(resource_name, b_items, t_items)
            result.resources[resource_name] = rd

            if rd.has_changes:
                logger.info(
                    "  %s: +%d -%d ~%d",
                    resource_name,
                    len(rd.added),
                    len(rd.removed),
                    len(rd.modified),
                )

        logger.info(
            "Diff complete: %d total changes across %d resources",
            result.total_changes,
            len(result.resources),
        )
        return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _load_resource(path: Path) -> list[dict[str, Any]]:
    """Load a resource JSON file, returning an empty list if missing."""
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "_error" in data:
        return []
    return [data]


def _get_key_func(resource_name: str):
    """Get the key-extraction function for a resource.

    If we have a registered resource class, use its ``get_key`` method.
    Otherwise fall back to a generic approach.
    """
    cls = REGISTRY.get(resource_name)
    if cls:
        # Create a minimal instance just for get_key (doesn't need real creds)
        from gwsdsc.config import CredentialsConfig

        dummy_creds = CredentialsConfig(type="adc")
        instance = cls(credentials_config=dummy_creds)
        return instance.get_key
    # Generic fallback: use "id" or "name" or "email"
    def _generic_key(item: dict[str, Any]) -> str:
        for field in ("primaryEmail", "email", "orgUnitPath", "domainName", "id", "name"):
            if field in item:
                return str(item[field])
        return json.dumps(item, sort_keys=True)[:120]

    return _generic_key


def _diff_resource(
    resource_name: str,
    baseline: list[dict[str, Any]],
    target: list[dict[str, Any]],
) -> ResourceDiff:
    """Compute the diff for a single resource type."""
    key_func = _get_key_func(resource_name)

    b_map: dict[str, dict[str, Any]] = {}
    for item in baseline:
        try:
            b_map[key_func(item)] = item
        except Exception:
            pass

    t_map: dict[str, dict[str, Any]] = {}
    for item in target:
        try:
            t_map[key_func(item)] = item
        except Exception:
            pass

    rd = ResourceDiff(
        resource_name=resource_name,
        baseline_count=len(baseline),
        target_count=len(target),
    )

    # Added (in target but not baseline)
    for key in sorted(set(t_map) - set(b_map)):
        rd.added.append(
            ItemChange(key=key, change_type="added", target_value=t_map[key])
        )

    # Removed (in baseline but not target)
    for key in sorted(set(b_map) - set(t_map)):
        rd.removed.append(
            ItemChange(key=key, change_type="removed", baseline_value=b_map[key])
        )

    # Modified (in both, but different)
    for key in sorted(set(b_map) & set(t_map)):
        b_item = b_map[key]
        t_item = t_map[key]

        # Use DeepDiff for semantic comparison
        dd = DeepDiff(
            b_item,
            t_item,
            ignore_order=True,
            exclude_paths={"root['etag']", "root['kind']"},
            verbose_level=2,
        )
        if dd:
            rd.modified.append(
                ItemChange(
                    key=key,
                    change_type="modified",
                    details=json.loads(dd.to_json()),
                    baseline_value=b_item,
                    target_value=t_item,
                )
            )

    return rd
