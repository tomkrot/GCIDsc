"""ChromeOS Management Telemetry — device fleet health data."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class ChromeOSTelemetryResource(BaseResource):
    NAME = "chromeos_telemetry"
    API_SERVICE = "chromemanagement"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/chrome.management.telemetry.readonly",
    ]
    IMPORTABLE = False
    DESCRIPTION = "ChromeOS device telemetry — fleet health, hardware, and OS inventory"
    STRIP_FIELDS = []

    def export_all(self) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        max_devices = self.options.get("max_devices", 2000)
        parent = f"customers/{self.customer_id}"

        try:
            request = self.service.customers().telemetry().devices().list(
                parent=parent, pageSize=100,
                readMask="name,serialNumber,orgUnitId,deviceId,osVersion,model,hardwareInfo",
            )
            while request is not None and len(devices) < max_devices:
                response = request.execute()
                devices.extend(response.get("devices", []))
                page_token = response.get("nextPageToken")
                request = (
                    self.service.customers().telemetry().devices().list(
                        parent=parent, pageSize=100, pageToken=page_token,
                        readMask="name,serialNumber,orgUnitId,deviceId,osVersion,model,hardwareInfo",
                    ) if page_token else None
                )
        except Exception as exc:
            logger.debug("Cannot list ChromeOS telemetry: %s", exc)

        logger.info("Exported %d ChromeOS telemetry devices", len(devices))
        return devices

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("name", item.get("serialNumber", item.get("deviceId", "")))
