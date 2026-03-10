"""Enterprise License Manager — SKU-to-user license assignments."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)

# Known Google Workspace product IDs
_PRODUCT_IDS = [
    "Google-Apps",               # Google Workspace
    "101031",                    # Google Workspace Enterprise
    "101034",                    # Google Workspace for Education
    "Google-Chrome-Device-Management",
    "Google-Vault",
    "101037",                    # Google Workspace Additional Storage
]


class LicenseAssignmentsResource(BaseResource):
    NAME = "license_assignments"
    API_SERVICE = "licensing"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/apps.licensing",
        "https://www.googleapis.com/auth/apps.licensing.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Enterprise license assignments (SKU-to-user mappings)"
    STRIP_FIELDS = ["etags", "kind"]
    KEY_FIELDS = ["productId", "skuId", "userId"]

    def export_all(self) -> list[dict[str, Any]]:
        assignments: list[dict[str, Any]] = []
        product_ids = self.options.get("product_ids", _PRODUCT_IDS)

        for product_id in product_ids:
            try:
                request = self.service.licenseAssignments().listForProduct(
                    productId=product_id, customerId=self.customer_id, maxResults=1000
                )
                while request is not None:
                    response = request.execute()
                    assignments.extend(response.get("items", []))
                    page_token = response.get("nextPageToken")
                    request = (
                        self.service.licenseAssignments().listForProduct(
                            productId=product_id, customerId=self.customer_id,
                            maxResults=1000, pageToken=page_token,
                        ) if page_token else None
                    )
            except Exception as exc:
                logger.debug("Cannot list licenses for product %s: %s", product_id, exc)

        logger.info("Exported %d license assignments", len(assignments))
        return assignments

    def get_key(self, item: dict[str, Any]) -> str:
        return f"{item.get('productId', '')}:{item.get('skuId', '')}:{item.get('userId', '')}"

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = {
            "userId": desired.get("userId"),
            "skuId": desired.get("skuId"),
            "productId": desired.get("productId"),
        }
        if existing:
            return None  # License reassignment is done via delete + create
        return (
            self.service.licenseAssignments()
            .insert(productId=desired["productId"], skuId=desired["skuId"], body=body)
            .execute()
        )
