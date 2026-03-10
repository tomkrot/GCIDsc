"""Mobile Devices resource module (read-only inventory)."""

from __future__ import annotations

from typing import Any

from gwsdsc.resources.base import BaseResource


class MobileDevicesResource(BaseResource):
    NAME = "mobile_devices"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.device.mobile",
        "https://www.googleapis.com/auth/admin.directory.device.mobile.readonly",
    ]
    IMPORTABLE = False
    DESCRIPTION = "Mobile device inventory (read-only)"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        request = self.service.mobiledevices().list(
            customerId=self.customer_id, maxResults=100
        )
        while request is not None:
            response = request.execute()
            devices.extend(response.get("mobiledevices", []))
            request = self.service.mobiledevices().list_next(request, response)
        return devices

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("resourceId", item.get("serialNumber", ""))
