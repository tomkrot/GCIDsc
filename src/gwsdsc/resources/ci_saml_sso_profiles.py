"""Cloud Identity — Inbound SAML SSO Profiles.

Manages SAML-based SSO profiles that define how external Identity Providers
(IdPs) authenticate into the Google Workspace tenant.  Each profile
contains IdP entity ID, SSO URL, signing certificates, and SP configuration.

API Reference:
  https://cloud.google.com/identity/docs/reference/rest/v1/inboundSamlSsoProfiles
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class CiSamlSsoProfilesResource(BaseResource):
    NAME = "ci_saml_sso_profiles"
    API_SERVICE = "cloudidentity"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/cloud-identity.inboundsso",
        "https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Cloud Identity SAML SSO profiles (IdP configuration)"
    STRIP_FIELDS = []
    KEY_FIELDS = ["name"]

    def export_all(self) -> list[dict[str, Any]]:
        profiles: list[dict[str, Any]] = []
        request = self.service.inboundSamlSsoProfiles().list(
            pageSize=100,
            filter=f"customer==\"customers/{self.customer_id}\"",
        )
        while request is not None:
            response = request.execute()
            profiles.extend(response.get("inboundSamlSsoProfiles", []))
            page_token = response.get("nextPageToken")
            if page_token:
                request = self.service.inboundSamlSsoProfiles().list(
                    pageSize=100,
                    filter=f"customer==\"customers/{self.customer_id}\"",
                    pageToken=page_token,
                )
            else:
                request = None

        # Also fetch IdP credentials for each profile
        for profile in profiles:
            profile_name = profile.get("name", "")
            if profile_name:
                try:
                    creds_resp = (
                        self.service.inboundSamlSsoProfiles()
                        .idpCredentials()
                        .list(parent=profile_name)
                        .execute()
                    )
                    profile["_idpCredentials"] = creds_resp.get("idpCredentials", [])
                except Exception as exc:
                    logger.debug("Cannot fetch IdP creds for %s: %s", profile_name, exc)

        logger.info("Exported %d SAML SSO profiles", len(profiles))
        return profiles

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("name", item.get("displayName", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        idp_creds = desired.pop("_idpCredentials", [])
        body = {k: v for k, v in desired.items() if k not in ("name", *self.STRIP_FIELDS)}

        if existing and existing.get("name"):
            result = (
                self.service.inboundSamlSsoProfiles()
                .patch(name=existing["name"], body=body, updateMask="*")
                .execute()
            )
        else:
            result = (
                self.service.inboundSamlSsoProfiles()
                .create(body=body)
                .execute()
            )

        # Re-add IdP credentials if provided
        profile_name = result.get("name") or (existing or {}).get("name")
        if profile_name and idp_creds:
            for cred in idp_creds:
                try:
                    self.service.inboundSamlSsoProfiles().idpCredentials().add(
                        parent=profile_name, body=cred
                    ).execute()
                except Exception as exc:
                    logger.warning("Cannot add IdP credential to %s: %s", profile_name, exc)

        return result

    def delete_one(self, existing: dict[str, Any]) -> None:
        if existing.get("name"):
            self.service.inboundSamlSsoProfiles().delete(
                name=existing["name"]
            ).execute()
