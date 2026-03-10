"""Custom User Schemas resource module."""

from __future__ import annotations

from typing import Any

from gwsdsc.resources.base import BaseResource


class SchemasResource(BaseResource):
    NAME = "schemas"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.userschema",
        "https://www.googleapis.com/auth/admin.directory.userschema.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Custom user schemas"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        response = self.service.schemas().list(customerId=self.customer_id).execute()
        return response.get("schemas", [])

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("schemaName", item.get("schemaId", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {k: v for k, v in desired.items() if k not in ("schemaId", *self.STRIP_FIELDS)}
        if existing:
            return (
                self.service.schemas()
                .update(customerId=self.customer_id, schemaKey=existing["schemaId"], body=body)
                .execute()
            )
        else:
            return (
                self.service.schemas()
                .insert(customerId=self.customer_id, body=body)
                .execute()
            )
