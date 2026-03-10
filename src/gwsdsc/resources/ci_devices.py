"""Cloud Identity — Devices (Endpoint Management).

Exports the device inventory and device-user bindings from the Cloud Identity
Devices API.  This provides richer device management data than the Admin SDK
``mobiledevices`` endpoint, including company-owned devices, BYO devices,
device states, and client states (MDM compliance).

API Reference:
  https://cloud.google.com/identity/docs/reference/rest/v1/devices
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class CiDevicesResource(BaseResource):
    NAME = "ci_devices"
    API_SERVICE = "cloudidentity"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/cloud-identity.devices",
        "https://www.googleapis.com/auth/cloud-identity.devices.readonly",
    ]
    IMPORTABLE = False  # device inventory is read-only
    DESCRIPTION = "Cloud Identity devices and endpoint management state"
    STRIP_FIELDS = []
    KEY_FIELDS = ["name"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export all devices and optionally their device-user bindings."""
        devices: list[dict[str, Any]] = []
        include_device_users = self.options.get("include_device_users", True)

        customer_ref = f"customers/{self.customer_id}"
        request = self.service.devices().list(
            customer=customer_ref,
            pageSize=100,
        )
        while request is not None:
            response = request.execute()
            page_devices = response.get("devices", [])

            for device in page_devices:
                if include_device_users and device.get("name"):
                    device["_deviceUsers"] = self._list_device_users(device["name"])
                devices.append(device)

            page_token = response.get("nextPageToken")
            if page_token:
                request = self.service.devices().list(
                    customer=customer_ref,
                    pageSize=100,
                    pageToken=page_token,
                )
            else:
                request = None

        logger.info("Exported %d Cloud Identity devices", len(devices))
        return devices

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("name", item.get("serialNumber", item.get("deviceId", "")))

    def _list_device_users(self, device_name: str) -> list[dict[str, Any]]:
        """List device-user bindings for a device."""
        device_users: list[dict[str, Any]] = []
        try:
            request = self.service.devices().deviceUsers().list(parent=device_name)
            while request is not None:
                response = request.execute()
                device_users.extend(response.get("deviceUsers", []))
                page_token = response.get("nextPageToken")
                if page_token:
                    request = self.service.devices().deviceUsers().list(
                        parent=device_name, pageToken=page_token
                    )
                else:
                    request = None
        except Exception as exc:
            logger.debug("Cannot list device users for %s: %s", device_name, exc)
        return device_users
