"""Customer (tenant) resource — top-level account settings."""

from __future__ import annotations

from typing import Any

from gwsdsc.resources.base import BaseResource


class CustomerResource(BaseResource):
    NAME = "customer"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.customer",
        "https://www.googleapis.com/auth/admin.directory.customer.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Customer / tenant-level settings"
    STRIP_FIELDS = ["etag", "kind", "customerCreationTime"]
    KEY_FIELDS = ["id"]

    def export_all(self) -> list[dict[str, Any]]:
        result = self.service.customers().get(customerKey=self.customer_id).execute()
        return [result]

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("id", "customer")

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {
            k: v
            for k, v in desired.items()
            if k not in ("id", "customerDomain", "alternateEmail", *self.STRIP_FIELDS)
        }
        if not body:
            return None
        return (
            self.service.customers()
            .update(customerKey=self.customer_id, body=body)
            .execute()
        )
