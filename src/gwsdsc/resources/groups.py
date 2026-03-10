"""Groups resource module — groups and group settings."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class GroupsResource(BaseResource):
    NAME = "groups"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.group",
        "https://www.googleapis.com/auth/admin.directory.group.readonly",
        "https://www.googleapis.com/auth/apps.groups.settings",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Groups and group settings"
    STRIP_FIELDS = ["etag", "kind", "nonEditableAliases"]
    KEY_FIELDS = ["email"]

    def export_all(self) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        request = self.service.groups().list(
            customer=self.customer_id, maxResults=200
        )

        while request is not None:
            response = request.execute()
            for group in response.get("groups", []):
                # Optionally fetch group settings via Groups Settings API
                if self.options.get("include_settings", True):
                    group["_settings"] = self._fetch_settings(group["email"])
                groups.append(group)
            request = self.service.groups().list_next(request, response)

        logger.info("Exported %d groups", len(groups))
        return groups

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("email", item.get("id", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        settings = desired.pop("_settings", None)
        body = {
            k: v
            for k, v in desired.items()
            if k not in ("id", "directMembersCount", *self.STRIP_FIELDS)
        }

        if existing:
            result = (
                self.service.groups()
                .update(groupKey=existing["email"], body=body)
                .execute()
            )
        else:
            result = self.service.groups().insert(body=body).execute()

        # Apply group settings if provided
        if settings:
            self._apply_settings(desired["email"], settings)

        return result

    def delete_one(self, existing: dict[str, Any]) -> None:
        self.service.groups().delete(groupKey=existing["email"]).execute()

    def _fetch_settings(self, group_email: str) -> dict[str, Any]:
        """Fetch settings via the Groups Settings API."""
        try:
            from gwsdsc.auth import build_service

            svc = build_service(
                config=self.credentials_config,
                api_service="groupssettings",
                api_version="v1",
                scopes=["https://www.googleapis.com/auth/apps.groups.settings"],
            )
            return svc.groups().get(groupUniqueId=group_email, alt="json").execute()
        except Exception as exc:
            logger.warning("Could not fetch settings for %s: %s", group_email, exc)
            return {}

    def _apply_settings(self, group_email: str, settings: dict[str, Any]) -> None:
        """Update settings via the Groups Settings API."""
        try:
            from gwsdsc.auth import build_service

            svc = build_service(
                config=self.credentials_config,
                api_service="groupssettings",
                api_version="v1",
                scopes=["https://www.googleapis.com/auth/apps.groups.settings"],
            )
            clean = {
                k: v
                for k, v in settings.items()
                if k not in ("email", "name", "description", "kind")
            }
            svc.groups().update(groupUniqueId=group_email, body=clean).execute()
        except Exception as exc:
            logger.warning("Could not apply settings for %s: %s", group_email, exc)
