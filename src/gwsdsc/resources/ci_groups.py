"""Cloud Identity — Groups (security groups, dynamic groups, labels).

The Cloud Identity Groups API provides a superset of the Admin SDK Groups API,
including support for:
  * Security group labels
  * Dynamic group memberships (query-based)
  * Membership expiry
  * Transitive membership queries

This module exports the Cloud Identity–specific group metadata and security
settings.  Use alongside the Admin SDK ``groups`` module for a complete
picture — or use this one alone if you prefer the CI API.

API Reference:
  https://cloud.google.com/identity/docs/reference/rest/v1/groups
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class CiGroupsResource(BaseResource):
    NAME = "ci_groups"
    API_SERVICE = "cloudidentity"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/cloud-identity.groups",
        "https://www.googleapis.com/auth/cloud-identity.groups.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Cloud Identity groups (security labels, dynamic memberships)"
    STRIP_FIELDS = []
    KEY_FIELDS = ["groupKey"]

    def export_all(self) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        parent = f"customers/{self.customer_id}"

        request = self.service.groups().list(parent=parent, pageSize=200)
        while request is not None:
            response = request.execute()
            page_groups = response.get("groups", [])

            for group in page_groups:
                # Fetch security settings
                group_name = group.get("name", "")
                if group_name:
                    try:
                        sec = (
                            self.service.groups()
                            .getSecuritySettings(name=f"{group_name}/securitySettings")
                            .execute()
                        )
                        group["_securitySettings"] = sec
                    except Exception:
                        pass

                groups.append(group)

            page_token = response.get("nextPageToken")
            if page_token:
                request = self.service.groups().list(
                    parent=parent, pageSize=200, pageToken=page_token
                )
            else:
                request = None

        logger.info("Exported %d Cloud Identity groups", len(groups))
        return groups

    def get_key(self, item: dict[str, Any]) -> str:
        gk = item.get("groupKey", {})
        if isinstance(gk, dict):
            return gk.get("id", item.get("name", ""))
        return str(gk) or item.get("name", "")

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        sec_settings = desired.pop("_securitySettings", None)
        body = {k: v for k, v in desired.items() if k not in ("name", *self.STRIP_FIELDS)}

        if existing and existing.get("name"):
            result = (
                self.service.groups()
                .patch(name=existing["name"], body=body, updateMask="*")
                .execute()
            )
        else:
            result = self.service.groups().create(body=body).execute()

        # Apply security settings
        group_name = (result or {}).get("name") or (existing or {}).get("name")
        if group_name and sec_settings:
            try:
                self.service.groups().updateSecuritySettings(
                    name=f"{group_name}/securitySettings",
                    body=sec_settings,
                    updateMask="*",
                ).execute()
            except Exception as exc:
                logger.warning("Cannot apply security settings for %s: %s", group_name, exc)

        return result

    def delete_one(self, existing: dict[str, Any]) -> None:
        if existing.get("name"):
            self.service.groups().delete(name=existing["name"]).execute()
