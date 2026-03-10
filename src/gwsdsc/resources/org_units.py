"""Organizational Units resource module."""

from __future__ import annotations

from typing import Any

from gwsdsc.resources.base import BaseResource


class OrgUnitsResource(BaseResource):
    NAME = "org_units"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.orgunit",
        "https://www.googleapis.com/auth/admin.directory.orgunit.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Organizational units"
    STRIP_FIELDS = ["etag", "kind"]
    KEY_FIELDS = ["orgUnitPath"]

    def export_all(self) -> list[dict[str, Any]]:
        response = (
            self.service.orgunits()
            .list(customerId=self.customer_id, type="all")
            .execute()
        )
        return response.get("organizationUnits", [])

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("orgUnitPath", item.get("orgUnitId", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {
            k: v
            for k, v in desired.items()
            if k not in ("orgUnitId", *self.STRIP_FIELDS)
        }
        if existing:
            # Update
            org_unit_path = existing["orgUnitPath"].lstrip("/")
            return (
                self.service.orgunits()
                .update(
                    customerId=self.customer_id,
                    orgUnitPath=[org_unit_path],
                    body=body,
                )
                .execute()
            )
        else:
            # Create
            return (
                self.service.orgunits()
                .insert(customerId=self.customer_id, body=body)
                .execute()
            )

    def delete_one(self, existing: dict[str, Any]) -> None:
        org_unit_path = existing["orgUnitPath"].lstrip("/")
        self.service.orgunits().delete(
            customerId=self.customer_id, orgUnitPath=[org_unit_path]
        ).execute()
