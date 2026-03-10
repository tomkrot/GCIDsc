"""Chrome Policies resource module — Chrome Policy API."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class ChromePoliciesResource(BaseResource):
    NAME = "chrome_policies"
    API_SERVICE = "chromepolicy"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/chrome.management.policy",
        "https://www.googleapis.com/auth/chrome.management.policy.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Chrome browser and ChromeOS policies"
    STRIP_FIELDS = []

    # Well-known policy schema namespaces to export
    POLICY_NAMESPACES = [
        "chrome.users",
        "chrome.users.apps",
        "chrome.devices",
        "chrome.devices.kiosk",
        "chrome.devices.managedguest",
        "chrome.printers",
        "chrome.networks.wifi",
        "chrome.networks.ethernet",
        "chrome.networks.vpn",
        "chrome.networks.certificates",
    ]

    def export_all(self) -> list[dict[str, Any]]:
        """Export resolved policies for all OUs × all namespaces."""
        policies: list[dict[str, Any]] = []

        # Fetch OUs to iterate
        ou_paths = self._get_ou_paths()

        for ou_path in ou_paths:
            for ns in self.POLICY_NAMESPACES:
                try:
                    resolved = self._resolve_policies(ou_path, ns)
                    for pol in resolved:
                        pol["_orgUnitPath"] = ou_path
                        pol["_namespace"] = ns
                    policies.extend(resolved)
                except Exception as exc:
                    logger.debug("No policies for %s @ %s: %s", ns, ou_path, exc)

        logger.info("Exported %d chrome policy entries", len(policies))
        return policies

    def get_key(self, item: dict[str, Any]) -> str:
        schema = item.get("value", {}).get("policySchema", "unknown")
        ou = item.get("_orgUnitPath", "/")
        return f"{ou}:{schema}"

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Apply a policy to the specified OU."""
        ou_id = self._ou_path_to_id(desired.get("_orgUnitPath", "/"))
        if not ou_id:
            logger.warning("Cannot resolve OU for policy import")
            return None

        body = {
            "requests": [
                {
                    "policyTargetKey": {
                        "targetResource": f"orgunits/{ou_id}",
                    },
                    "policyValue": desired.get("value", {}),
                    "updateMask": "*",
                }
            ]
        }
        return (
            self.service.customers()
            .policies()
            .orgunits()
            .batchModify(customer=f"customers/{self.customer_id}", body=body)
            .execute()
        )

    def _get_ou_paths(self) -> list[str]:
        """Return all OU paths from Directory API."""
        from gwsdsc.auth import build_service

        dir_svc = build_service(
            self.credentials_config,
            "admin",
            "directory_v1",
            ["https://www.googleapis.com/auth/admin.directory.orgunit.readonly"],
        )
        resp = dir_svc.orgunits().list(customerId=self.customer_id, type="all").execute()
        paths = ["/"] + [ou["orgUnitPath"] for ou in resp.get("organizationUnits", [])]
        return paths

    def _resolve_policies(self, ou_path: str, namespace: str) -> list[dict[str, Any]]:
        """Resolve policies for a given OU and namespace."""
        ou_id = self._ou_path_to_id(ou_path)
        target_resource = f"orgunits/{ou_id}" if ou_id else "orgunits/"

        body = {
            "policyTargetKey": {"targetResource": target_resource},
            "policySchemaFilter": f"{namespace}.*",
        }
        response = (
            self.service.customers()
            .policies()
            .resolve(customer=f"customers/{self.customer_id}", body=body)
            .execute()
        )
        return response.get("resolvedPolicies", [])

    def _ou_path_to_id(self, ou_path: str) -> str | None:
        """Convert an OU path to its ID (needed by Chrome Policy API)."""
        if ou_path == "/":
            return ""
        from gwsdsc.auth import build_service

        dir_svc = build_service(
            self.credentials_config,
            "admin",
            "directory_v1",
            ["https://www.googleapis.com/auth/admin.directory.orgunit.readonly"],
        )
        try:
            ou = dir_svc.orgunits().get(
                customerId=self.customer_id, orgUnitPath=[ou_path.lstrip("/")]
            ).execute()
            return ou.get("orgUnitId", "").replace("id:", "")
        except Exception:
            return None
