"""Cloud Identity — Inbound SSO Assignments.

Manages assignments of SSO profiles (SAML or OIDC) to OrgUnits or Groups.
These determine which SSO profile is used when users in a given OU or group
authenticate.

API Reference:
  https://cloud.google.com/identity/docs/reference/rest/v1/inboundSsoAssignments
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class CiSsoAssignmentsResource(BaseResource):
    NAME = "ci_sso_assignments"
    API_SERVICE = "cloudidentity"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/cloud-identity.inboundsso",
        "https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Cloud Identity SSO profile-to-OU/Group assignments"
    STRIP_FIELDS = []
    KEY_FIELDS = ["name"]

    def export_all(self) -> list[dict[str, Any]]:
        assignments: list[dict[str, Any]] = []
        request = self.service.inboundSsoAssignments().list(
            pageSize=100,
            filter=f"customer==\"customers/{self.customer_id}\"",
        )
        while request is not None:
            response = request.execute()
            assignments.extend(response.get("inboundSsoAssignments", []))
            page_token = response.get("nextPageToken")
            if page_token:
                request = self.service.inboundSsoAssignments().list(
                    pageSize=100,
                    filter=f"customer==\"customers/{self.customer_id}\"",
                    pageToken=page_token,
                )
            else:
                request = None

        logger.info("Exported %d SSO assignments", len(assignments))
        return assignments

    def get_key(self, item: dict[str, Any]) -> str:
        # Unique by target (OU or group) + profile combination
        target_group = item.get("targetGroup", "")
        target_org = item.get("targetOrgUnit", "")
        return item.get("name", f"{target_group or target_org}:{item.get('ssoProfile', '')}")

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {k: v for k, v in desired.items() if k not in ("name", *self.STRIP_FIELDS)}

        if existing and existing.get("name"):
            return (
                self.service.inboundSsoAssignments()
                .patch(name=existing["name"], body=body, updateMask="*")
                .execute()
            )
        else:
            return (
                self.service.inboundSsoAssignments()
                .create(body=body)
                .execute()
            )

    def delete_one(self, existing: dict[str, Any]) -> None:
        if existing.get("name"):
            self.service.inboundSsoAssignments().delete(
                name=existing["name"]
            ).execute()
