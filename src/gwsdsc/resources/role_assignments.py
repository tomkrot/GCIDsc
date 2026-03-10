"""Role Assignments resource module."""

from __future__ import annotations

from typing import Any

from gwsdsc.resources.base import BaseResource


class RoleAssignmentsResource(BaseResource):
    NAME = "role_assignments"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.rolemanagement",
        "https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Role-to-user assignments"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        assignments: list[dict[str, Any]] = []
        request = self.service.roleAssignments().list(
            customer=self.customer_id, maxResults=200
        )
        while request is not None:
            response = request.execute()
            assignments.extend(response.get("items", []))
            request = self.service.roleAssignments().list_next(request, response)
        return assignments

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("roleAssignmentId", f"{item.get('roleId')}:{item.get('assignedTo')}")

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        if existing:
            return None  # Role assignments are immutable; delete + recreate
        body = {k: v for k, v in desired.items() if k not in ("roleAssignmentId", *self.STRIP_FIELDS)}
        return (
            self.service.roleAssignments()
            .insert(customer=self.customer_id, body=body)
            .execute()
        )

    def delete_one(self, existing: dict[str, Any]) -> None:
        self.service.roleAssignments().delete(
            customer=self.customer_id,
            roleAssignmentId=existing["roleAssignmentId"],
        ).execute()
