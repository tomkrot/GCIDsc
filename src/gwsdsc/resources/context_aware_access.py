"""Context-Aware Access — Access Context Manager API.

Exports access policies, access levels (BeyondCorp zero-trust conditions),
and VPC Service Perimeters.  These define the device posture, IP range, OS,
and geo-location conditions under which users can reach Workspace applications.

API Reference:
  https://docs.cloud.google.com/access-context-manager/docs/reference/rest
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class ContextAwareAccessResource(BaseResource):
    NAME = "context_aware_access"
    API_SERVICE = "accesscontextmanager"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/cloud-platform",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Context-Aware Access — access levels, policies, and service perimeters (BeyondCorp)"
    STRIP_FIELDS = ["etag"]
    KEY_FIELDS = ["name"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export all access policies, their access levels, and service perimeters."""
        all_items: list[dict[str, Any]] = []

        # List access policies
        policies = self._list_access_policies()
        for policy in policies:
            policy["_resourceType"] = "accessPolicy"
            all_items.append(policy)

            policy_name = policy.get("name", "")
            if not policy_name:
                continue

            # Access levels within each policy
            for level in self._list_access_levels(policy_name):
                level["_resourceType"] = "accessLevel"
                level["_policyName"] = policy_name
                all_items.append(level)

            # Service perimeters
            for perimeter in self._list_service_perimeters(policy_name):
                perimeter["_resourceType"] = "servicePerimeter"
                perimeter["_policyName"] = policy_name
                all_items.append(perimeter)

        logger.info(
            "Exported %d context-aware access items (policies + levels + perimeters)",
            len(all_items),
        )
        return all_items

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("name", item.get("title", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        rtype = desired.get("_resourceType", "")
        body = {
            k: v
            for k, v in desired.items()
            if not k.startswith("_") and k not in self.STRIP_FIELDS
        }

        if rtype == "accessLevel":
            policy_name = desired.get("_policyName", "")
            if existing:
                return (
                    self.service.accessPolicies()
                    .accessLevels()
                    .patch(name=existing["name"], body=body, updateMask="*")
                    .execute()
                )
            else:
                return (
                    self.service.accessPolicies()
                    .accessLevels()
                    .create(parent=policy_name, body=body)
                    .execute()
                )
        elif rtype == "servicePerimeter":
            policy_name = desired.get("_policyName", "")
            if existing:
                return (
                    self.service.accessPolicies()
                    .servicePerimeters()
                    .patch(name=existing["name"], body=body, updateMask="*")
                    .execute()
                )
            else:
                return (
                    self.service.accessPolicies()
                    .servicePerimeters()
                    .create(parent=policy_name, body=body)
                    .execute()
                )
        return None

    def _list_access_policies(self) -> list[dict[str, Any]]:
        policies: list[dict[str, Any]] = []
        request = self.service.accessPolicies().list(parent=f"organizations/{self.customer_id}")
        while request is not None:
            response = request.execute()
            policies.extend(response.get("accessPolicies", []))
            page_token = response.get("nextPageToken")
            request = (
                self.service.accessPolicies().list(
                    parent=f"organizations/{self.customer_id}", pageToken=page_token
                )
                if page_token
                else None
            )
        return policies

    def _list_access_levels(self, policy_name: str) -> list[dict[str, Any]]:
        levels: list[dict[str, Any]] = []
        try:
            request = self.service.accessPolicies().accessLevels().list(parent=policy_name)
            while request is not None:
                response = request.execute()
                levels.extend(response.get("accessLevels", []))
                page_token = response.get("nextPageToken")
                request = (
                    self.service.accessPolicies()
                    .accessLevels()
                    .list(parent=policy_name, pageToken=page_token)
                    if page_token
                    else None
                )
        except Exception as exc:
            logger.debug("Cannot list access levels for %s: %s", policy_name, exc)
        return levels

    def _list_service_perimeters(self, policy_name: str) -> list[dict[str, Any]]:
        perimeters: list[dict[str, Any]] = []
        try:
            request = self.service.accessPolicies().servicePerimeters().list(parent=policy_name)
            while request is not None:
                response = request.execute()
                perimeters.extend(response.get("servicePerimeters", []))
                page_token = response.get("nextPageToken")
                request = (
                    self.service.accessPolicies()
                    .servicePerimeters()
                    .list(parent=policy_name, pageToken=page_token)
                    if page_token
                    else None
                )
        except Exception as exc:
            logger.debug("Cannot list service perimeters for %s: %s", policy_name, exc)
        return perimeters
