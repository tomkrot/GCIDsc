"""Calendar Resources (rooms, equipment) resource module."""

from __future__ import annotations

from typing import Any

from gwsdsc.resources.base import BaseResource


class CalendarResourcesResource(BaseResource):
    NAME = "calendar_resources"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.resource.calendar",
        "https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Calendar resources (rooms, equipment)"
    STRIP_FIELDS = ["etags", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        request = self.service.resources().calendars().list(
            customer=self.customer_id, maxResults=500
        )
        while request is not None:
            response = request.execute()
            resources.extend(response.get("items", []))
            request = self.service.resources().calendars().list_next(request, response)
        return resources

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("resourceEmail", item.get("resourceId", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {k: v for k, v in desired.items() if k not in self.STRIP_FIELDS}
        if existing:
            return (
                self.service.resources()
                .calendars()
                .update(
                    customer=self.customer_id,
                    calendarResourceId=existing["resourceId"],
                    body=body,
                )
                .execute()
            )
        else:
            return (
                self.service.resources()
                .calendars()
                .insert(customer=self.customer_id, body=body)
                .execute()
            )

    def delete_one(self, existing: dict[str, Any]) -> None:
        self.service.resources().calendars().delete(
            customer=self.customer_id,
            calendarResourceId=existing["resourceId"],
        ).execute()
