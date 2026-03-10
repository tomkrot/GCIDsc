"""Admin Roles resource module."""

from __future__ import annotations

from typing import Any

from gwsdsc.resources.base import BaseResource


class RolesResource(BaseResource):
    NAME = "roles"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.rolemanagement",
        "https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Admin roles"
    STRIP_FIELDS = ["etag", "kind"]
    KEY_FIELDS = ["roleId"]

    def export_all(self) -> list[dict[str, Any]]:
        response = self.service.roles().list(customer=self.customer_id).execute()
        return response.get("items", [])

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("roleName", item.get("roleId", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {k: v for k, v in desired.items() if k not in ("roleId", *self.STRIP_FIELDS)}
        if existing:
            return (
                self.service.roles()
                .update(customer=self.customer_id, roleId=existing["roleId"], body=body)
                .execute()
            )
        else:
            return (
                self.service.roles()
                .insert(customer=self.customer_id, body=body)
                .execute()
            )
