"""Chrome Printer Management — CUPS printers and print servers."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class ChromePrintersResource(BaseResource):
    NAME = "chrome_printers"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.chrome.printers",
        "https://www.googleapis.com/auth/admin.chrome.printers.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Chrome printer management — CUPS printers and print server fleet"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        printers: list[dict[str, Any]] = []
        parent = f"customers/{self.customer_id}"

        try:
            request = self.service.customers().chrome().printers().list(
                parent=parent, pageSize=100,
            )
            while request is not None:
                response = request.execute()
                printers.extend(response.get("printers", []))
                page_token = response.get("nextPageToken")
                request = (
                    self.service.customers().chrome().printers().list(
                        parent=parent, pageSize=100, pageToken=page_token,
                    ) if page_token else None
                )
        except Exception as exc:
            logger.debug("Cannot list Chrome printers: %s", exc)

        logger.info("Exported %d Chrome printers", len(printers))
        return printers

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("id", item.get("name", item.get("displayName", "")))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        parent = f"customers/{self.customer_id}"
        body = {k: v for k, v in desired.items() if k not in ("id", *self.STRIP_FIELDS)}

        if existing:
            return (
                self.service.customers().chrome().printers()
                .patch(name=existing["name"], body=body, updateMask="*")
                .execute()
            )
        else:
            return (
                self.service.customers().chrome().printers()
                .create(parent=parent, body=body)
                .execute()
            )

    def delete_one(self, existing: dict[str, Any]) -> None:
        self.service.customers().chrome().printers().delete(
            name=existing["name"]
        ).execute()
