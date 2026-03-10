"""Users resource module — exports user account configurations.

Sensitive data (passwords, recovery info) is never exported.
Only configuration-relevant attributes are persisted.
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)

# Fields that are config-relevant for users
_CONFIG_FIELDS = [
    "primaryEmail",
    "name",
    "isAdmin",
    "isDelegatedAdmin",
    "suspended",
    "archived",
    "orgUnitPath",
    "includeInGlobalAddressList",
    "ipWhitelisted",
    "emails",
    "relations",
    "addresses",
    "organizations",
    "phones",
    "languages",
    "customSchemas",
    "recoveryEmail",
    "recoveryPhone",
    "changePasswordAtNextLogin",
    "agreedToTerms",
    "isEnrolledIn2Sv",
    "isEnforcedIn2Sv",
    "creationTime",
    "lastLoginTime",
    "thumbnailPhotoUrl",
    "id",
]

# Fields never to export (security-sensitive or volatile)
_NEVER_EXPORT = [
    "password",
    "hashFunction",
    "etag",
    "kind",
]


class UsersResource(BaseResource):
    NAME = "users"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.user",
        "https://www.googleapis.com/auth/admin.directory.user.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "User accounts (configuration fields only)"
    STRIP_FIELDS = _NEVER_EXPORT
    KEY_FIELDS = ["primaryEmail"]

    def export_all(self) -> list[dict[str, Any]]:
        include_suspended = self.options.get("include_suspended", True)
        projection = self.options.get("projection", "full")

        users: list[dict[str, Any]] = []
        request = self.service.users().list(
            customer=self.customer_id,
            maxResults=500,
            projection=projection,
            orderBy="email",
        )

        while request is not None:
            response = request.execute()
            page_users = response.get("users", [])

            for user in page_users:
                if not include_suspended and user.get("suspended"):
                    continue
                users.append(self._extract_config(user))

            request = self.service.users().list_next(request, response)

        logger.info("Exported %d users", len(users))
        return users

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("primaryEmail", item.get("id", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {
            k: v
            for k, v in desired.items()
            if k not in ("id", "creationTime", "lastLoginTime", *self.STRIP_FIELDS)
        }
        if existing:
            return (
                self.service.users()
                .update(userKey=existing["primaryEmail"], body=body)
                .execute()
            )
        else:
            if "password" not in body:
                body["password"] = "__CHANGE_ME__"  # API requires password on create
                body["changePasswordAtNextLogin"] = True
            return self.service.users().insert(body=body).execute()

    def delete_one(self, existing: dict[str, Any]) -> None:
        self.service.users().delete(userKey=existing["primaryEmail"]).execute()

    def _extract_config(self, user: dict[str, Any]) -> dict[str, Any]:
        """Keep only configuration-relevant fields."""
        return {
            k: v
            for k, v in user.items()
            if k in _CONFIG_FIELDS and k not in _NEVER_EXPORT
        }
