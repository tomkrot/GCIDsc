"""Google Vault — Retention Rules & Legal Holds.

Exports Vault matters, retention rules (default + custom), and legal holds.
These are compliance-critical: incorrect retention settings can cause
irreversible data loss.

API Reference:
  https://developers.google.com/workspace/vault/reference/rest
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class VaultRetentionResource(BaseResource):
    NAME = "vault_retention"
    API_SERVICE = "vault"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/ediscovery",
        "https://www.googleapis.com/auth/ediscovery.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Google Vault matters, retention rules, and legal holds"
    STRIP_FIELDS = []
    KEY_FIELDS = ["matterId", "name"]

    def export_all(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []

        # Export all matters and their holds
        matters = self._list_matters()
        for matter in matters:
            matter["_resourceType"] = "matter"
            all_items.append(matter)

            matter_id = matter.get("matterId", "")
            if matter_id:
                holds = self._list_holds(matter_id)
                for hold in holds:
                    hold["_resourceType"] = "hold"
                    hold["_matterId"] = matter_id
                    hold["_matterName"] = matter.get("name", "")
                all_items.extend(holds)

        logger.info(
            "Exported %d Vault items (%d matters + holds)",
            len(all_items),
            len(matters),
        )
        return all_items

    def get_key(self, item: dict[str, Any]) -> str:
        rtype = item.get("_resourceType", "")
        if rtype == "matter":
            return f"matter:{item.get('matterId', item.get('name', ''))}"
        elif rtype == "hold":
            return f"hold:{item.get('_matterId', '')}:{item.get('holdId', item.get('name', ''))}"
        return item.get("name", item.get("matterId", ""))

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        rtype = desired.get("_resourceType", "")

        if rtype == "matter":
            body = {
                k: v for k, v in desired.items()
                if not k.startswith("_") and k not in ("matterId",)
            }
            if existing:
                return self.service.matters().update(
                    matterId=existing["matterId"], body=body
                ).execute()
            else:
                return self.service.matters().create(body=body).execute()

        elif rtype == "hold":
            matter_id = desired.get("_matterId", "")
            body = {
                k: v for k, v in desired.items()
                if not k.startswith("_") and k not in ("holdId",)
            }
            if existing:
                return self.service.matters().holds().update(
                    matterId=matter_id, holdId=existing["holdId"], body=body
                ).execute()
            else:
                return self.service.matters().holds().create(
                    matterId=matter_id, body=body
                ).execute()

        return None

    def _list_matters(self) -> list[dict[str, Any]]:
        matters: list[dict[str, Any]] = []
        request = self.service.matters().list(state="OPEN", pageSize=100)
        while request is not None:
            response = request.execute()
            matters.extend(response.get("matters", []))
            page_token = response.get("nextPageToken")
            request = (
                self.service.matters().list(state="OPEN", pageSize=100, pageToken=page_token)
                if page_token else None
            )
        # Also include closed matters for complete audit trail
        request = self.service.matters().list(state="CLOSED", pageSize=100)
        while request is not None:
            response = request.execute()
            matters.extend(response.get("matters", []))
            page_token = response.get("nextPageToken")
            request = (
                self.service.matters().list(state="CLOSED", pageSize=100, pageToken=page_token)
                if page_token else None
            )
        return matters

    def _list_holds(self, matter_id: str) -> list[dict[str, Any]]:
        holds: list[dict[str, Any]] = []
        try:
            request = self.service.matters().holds().list(matterId=matter_id, pageSize=100)
            while request is not None:
                response = request.execute()
                holds.extend(response.get("holds", []))
                page_token = response.get("nextPageToken")
                request = (
                    self.service.matters().holds().list(
                        matterId=matter_id, pageSize=100, pageToken=page_token
                    ) if page_token else None
                )
        except Exception as exc:
            logger.debug("Cannot list holds for matter %s: %s", matter_id, exc)
        return holds
