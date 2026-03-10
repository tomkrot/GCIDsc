"""Alert Center API — alert rules, active alerts, and feedback.

Exports the Alert Center configuration: system-defined alert rules and
their notification settings, plus a snapshot of active alerts.

API Reference:
  https://developers.google.com/workspace/alert-center/reference/rest
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class AlertCenterResource(BaseResource):
    NAME = "alert_center"
    API_SERVICE = "alertcenter"
    API_VERSION = "v1beta1"
    SCOPES = [
        "https://www.googleapis.com/auth/apps.alerts",
    ]
    IMPORTABLE = False
    DESCRIPTION = "Alert Center — system-defined alert rules, active alerts, and notification config"
    STRIP_FIELDS = []
    KEY_FIELDS = ["alertId"]

    def export_all(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        # Export alert center settings
        try:
            settings = self.service.v1beta1().getSettings().execute()
            settings["_resourceType"] = "settings"
            all_items.append(settings)
        except Exception as exc:
            logger.debug("Cannot fetch Alert Center settings: %s", exc)

        # Export active alerts (snapshot for audit/drift)
        alerts = self._list_alerts()
        for alert in alerts:
            alert["_resourceType"] = "alert"
        all_items.extend(alerts)

        logger.info("Exported %d Alert Center items", len(all_items))
        return all_items

    def get_key(self, item: dict[str, Any]) -> str:
        if item.get("_resourceType") == "settings":
            return "_alert_center_settings"
        return item.get("alertId", item.get("type", ""))

    def _list_alerts(self) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        try:
            request = self.service.alerts().list(pageSize=100)
            while request is not None:
                response = request.execute()
                alerts.extend(response.get("alerts", []))
                page_token = response.get("nextPageToken")
                request = (
                    self.service.alerts().list(pageSize=100, pageToken=page_token)
                    if page_token else None
                )
        except Exception as exc:
            logger.debug("Cannot list alerts: %s", exc)
        return alerts
