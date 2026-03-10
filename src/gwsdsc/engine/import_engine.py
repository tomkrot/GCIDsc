"""Import Engine — applies desired-state configuration to a target tenant.

Supports two modes:
  * **plan** (dry-run) — shows what *would* change without modifying anything.
  * **apply** — creates, updates, or optionally deletes resources to converge
    the target tenant to the desired state.

Usage::

    from gwsdsc.engine.import_engine import ImportEngine, ImportMode

    engine = ImportEngine(target_config)
    plan = engine.run(source_dir="artifacts/latest", mode=ImportMode.PLAN)
    # Inspect plan, then:
    result = engine.run(source_dir="artifacts/latest", mode=ImportMode.APPLY)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from gwsdsc.config import TenantConfig, load_resource_catalogue
from gwsdsc.resources import REGISTRY

logger = logging.getLogger(__name__)


class ImportMode(str, Enum):
    PLAN = "plan"
    APPLY = "apply"


@dataclass
class ImportAction:
    """A single planned or executed action."""

    resource_name: str
    key: str
    action: str  # "create", "update", "delete", "skip", "error"
    details: str = ""
    desired: dict[str, Any] | None = None
    existing: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


@dataclass
class ImportResult:
    """Results of an import run."""

    mode: str
    source_dir: str
    actions: list[ImportAction] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for a in self.actions:
            counts[a.action] = counts.get(a.action, 0) + 1
        return counts

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {
                "mode": self.mode,
                "source_dir": self.source_dir,
                "summary": self.summary,
                "actions": [vars(a) for a in self.actions],
            },
            indent=indent,
            default=str,
        )


class ImportEngine:
    """Converge a target tenant toward a desired-state snapshot."""

    # Import order matters (dependencies first)
    IMPORT_ORDER = [
        # Tenant foundation
        "customer",
        "domains",
        "org_units",
        "schemas",
        # Context-Aware Access (before SSO — access levels may be referenced)
        "context_aware_access",
        # Cloud Identity SSO must be configured before user imports
        "ci_saml_sso_profiles",
        "ci_oidc_sso_profiles",
        "ci_sso_assignments",
        # Cloud Identity policies (security, API controls, DLP, app settings)
        "ci_policies",
        "ci_groups",
        # Core Admin SDK resources
        "users",
        "license_assignments",
        "groups",
        "group_members",
        "roles",
        "role_assignments",
        "contact_delegation",
        # Application settings
        "chrome_policies",
        "chrome_printers",
        "email_settings",
        "security",
        "calendar_resources",
        # Compliance
        "vault_retention",
    ]

    def __init__(
        self,
        config: TenantConfig,
        allow_delete: bool = False,
    ) -> None:
        self.config = config
        self.allow_delete = allow_delete
        self.catalogue = load_resource_catalogue()

    def run(
        self,
        source_dir: str | Path,
        mode: ImportMode = ImportMode.PLAN,
        resource_names: list[str] | None = None,
    ) -> ImportResult:
        """Run the import.

        Parameters
        ----------
        source_dir
            Path to a snapshot directory containing ``<resource>.json`` files.
        mode
            ``PLAN`` for dry-run, ``APPLY`` to make changes.
        resource_names
            Limit to specific resources. ``None`` imports everything available.
        """
        source = Path(source_dir).resolve()
        result = ImportResult(mode=mode.value, source_dir=str(source))

        names = self._resolve_names(resource_names, source)
        logger.info("Import %s: resources=%s, source=%s", mode.value, names, source)

        for name in names:
            actions = self._process_resource(name, source, mode)
            result.actions.extend(actions)

        logger.info(
            "Import %s complete: %s",
            mode.value,
            result.summary,
        )
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_names(
        self, resource_names: list[str] | None, source: Path
    ) -> list[str]:
        available = {p.stem for p in source.glob("*.json") if not p.stem.startswith("_")}
        importable = {
            n for n, cls in REGISTRY.items() if cls.IMPORTABLE  # type: ignore[attr-defined]
        }
        candidates = available & importable

        if resource_names:
            candidates = candidates & set(resource_names)

        # Sort by import order
        ordered = [n for n in self.IMPORT_ORDER if n in candidates]
        # Add anything not in the explicit order
        ordered += sorted(candidates - set(ordered))
        return ordered

    def _process_resource(
        self,
        resource_name: str,
        source: Path,
        mode: ImportMode,
    ) -> list[ImportAction]:
        """Plan or apply changes for a single resource."""
        actions: list[ImportAction] = []
        cls = REGISTRY[resource_name]

        # Load desired state from artifact
        desired_path = source / f"{resource_name}.json"
        if not desired_path.exists():
            return actions
        desired_items = json.loads(desired_path.read_text())
        if not isinstance(desired_items, list):
            return actions

        # Build resource instance for the TARGET tenant
        options = self.config.export_options.get(resource_name, {})
        resource = cls(
            credentials_config=self.config.credentials,
            customer_id=self.config.customer_id,
            options=options,
        )

        # Fetch current state from target
        try:
            existing_items = resource.export_cleaned()
        except Exception as exc:
            logger.warning("Cannot fetch existing %s: %s", resource_name, exc)
            existing_items = []

        # Build key-based maps
        existing_map = {resource.get_key(item): item for item in existing_items}
        desired_map = {resource.get_key(item): item for item in desired_items}

        # Create or Update
        for key, desired_item in desired_map.items():
            existing_item = existing_map.get(key)

            if existing_item is None:
                action = ImportAction(
                    resource_name=resource_name,
                    key=key,
                    action="create",
                    desired=desired_item,
                )
                if mode == ImportMode.APPLY:
                    try:
                        action.result = resource.import_one(desired_item, None)
                    except Exception as exc:
                        action.action = "error"
                        action.details = str(exc)
                actions.append(action)
            else:
                # Check if update needed (quick check)
                from deepdiff import DeepDiff

                dd = DeepDiff(
                    existing_item,
                    desired_item,
                    ignore_order=True,
                    exclude_paths=set(
                        f"root['{f}']" for f in resource.STRIP_FIELDS
                    ),
                )
                if dd:
                    action = ImportAction(
                        resource_name=resource_name,
                        key=key,
                        action="update",
                        desired=desired_item,
                        existing=existing_item,
                        details=str(dd),
                    )
                    if mode == ImportMode.APPLY:
                        try:
                            action.result = resource.import_one(
                                desired_item, existing_item
                            )
                        except Exception as exc:
                            action.action = "error"
                            action.details = str(exc)
                    actions.append(action)

        # Delete (items in existing but not desired)
        if self.allow_delete:
            for key in set(existing_map) - set(desired_map):
                action = ImportAction(
                    resource_name=resource_name,
                    key=key,
                    action="delete",
                    existing=existing_map[key],
                )
                if mode == ImportMode.APPLY:
                    try:
                        resource.delete_one(existing_map[key])
                    except NotImplementedError:
                        action.action = "skip"
                        action.details = "delete not supported for this resource"
                    except Exception as exc:
                        action.action = "error"
                        action.details = str(exc)
                actions.append(action)

        return actions
