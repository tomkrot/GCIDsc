"""Cloud Identity — Inbound OIDC SSO Profiles.

Manages OpenID Connect SSO profiles for authentication from external IdPs.

API Reference:
  https://cloud.google.com/identity/docs/reference/rest/v1/inboundOidcSsoProfiles
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class CiOidcSsoProfilesResource(BaseResource):
    NAME = "ci_oidc_sso_profiles"
    API_SERVICE = "cloudidentity"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/cloud-identity.inboundsso",
        "https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Cloud Identity OIDC SSO profiles"
    STRIP_FIELDS = []
    KEY_FIELDS = ["name"]

    def export_all(self) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []
        request = self.service.inboundOidcSsoProfiles().list(
            pageSize=100,
            filter=f"customer==\"customers/{self.customer_id}\"",
        )
        while request is not None:
            response = request.execute()
            profiles.extend(response.get("inboundOidcSsoProfiles", []))
            page_token = response.get("nextPageToken")
            if page_token:
                request = self.service.inboundOidcSsoProfiles().list(
                    pageSize=100,
                    filter=f"customer==\"customers/{self.customer_id}\"",
                    pageToken=page_token,
                )
            else:
                request = None

        logger.info("Exported %d OIDC SSO profiles", len(profiles))
        return profiles

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("name", item.get("displayName", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {k: v for k, v in desired.items() if k not in ("name", *self.STRIP_FIELDS)}

        if existing and existing.get("name"):
            return (
                self.service.inboundOidcSsoProfiles()
                .patch(name=existing["name"], body=body, updateMask="*")
                .execute()
            )
        else:
            return (
                self.service.inboundOidcSsoProfiles()
                .create(body=body)
                .execute()
            )

    def delete_one(self, existing: dict[str, Any]) -> None:
        if existing.get("name"):
            self.service.inboundOidcSsoProfiles().delete(
                name=existing["name"]
            ).execute()
