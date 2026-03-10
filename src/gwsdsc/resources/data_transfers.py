"""Data Transfer API — transfer records and supported applications."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class DataTransfersResource(BaseResource):
    NAME = "data_transfers"
    API_SERVICE = "admin"
    API_VERSION = "datatransfer_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.datatransfer",
        "https://www.googleapis.com/auth/admin.datatransfer.readonly",
    ]
    IMPORTABLE = False
    DESCRIPTION = "Data Transfer — transfer-capable apps and transfer records (audit)"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        # Export supported applications
        try:
            apps_resp = self.service.applications().list(customerId=self.customer_id).execute()
            for app in apps_resp.get("applications", []):
                app["_resourceType"] = "transferableApp"
            all_items.extend(apps_resp.get("applications", []))
        except Exception as exc:
            logger.debug("Cannot list transferable apps: %s", exc)

        # Export recent transfer records
        max_transfers = self.options.get("max_transfers", 500)
        try:
            request = self.service.transfers().list(customerId=self.customer_id, maxResults=100)
            count = 0
            while request is not None and count < max_transfers:
                response = request.execute()
                transfers = response.get("dataTransfers", [])
                for t in transfers:
                    t["_resourceType"] = "transfer"
                all_items.extend(transfers)
                count += len(transfers)
                page_token = response.get("nextPageToken")
                request = (
                    self.service.transfers().list(
                        customerId=self.customer_id, maxResults=100, pageToken=page_token
                    ) if page_token else None
                )
        except Exception as exc:
            logger.debug("Cannot list data transfers: %s", exc)

        logger.info("Exported %d data transfer items", len(all_items))
        return all_items

    def get_key(self, item: dict[str, Any]) -> str:
        if item.get("_resourceType") == "transferableApp":
            return f"app:{item.get('id', item.get('name', ''))}"
        return f"transfer:{item.get('id', '')}"
