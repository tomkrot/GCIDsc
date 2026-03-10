"""Security settings resource — 2SV enforcement, session controls, etc."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class SecurityResource(BaseResource):
    NAME = "security"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.user.security",
        "https://www.googleapis.com/auth/admin.directory.user.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Security posture (2SV enrollment stats, per-OU enforcement)"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export 2SV enrollment status across all users (summary + detail).

        Produces a summary record plus per-user 2SV status for auditing.
        """
        users_2sv: list[dict[str, Any]] = []
        enrolled = 0
        enforced = 0
        total = 0

        request = self.service.users().list(
            customer=self.customer_id,
            maxResults=500,
            projection="basic",
        )

        while request is not None:
            response = request.execute()
            for user in response.get("users", []):
                total += 1
                status = {
                    "primaryEmail": user["primaryEmail"],
                    "isEnrolledIn2Sv": user.get("isEnrolledIn2Sv", False),
                    "isEnforcedIn2Sv": user.get("isEnforcedIn2Sv", False),
                    "orgUnitPath": user.get("orgUnitPath", "/"),
                }
                if status["isEnrolledIn2Sv"]:
                    enrolled += 1
                if status["isEnforcedIn2Sv"]:
                    enforced += 1
                users_2sv.append(status)
            request = self.service.users().list_next(request, response)

        # Prepend a summary record
        summary = {
            "_type": "summary",
            "totalUsers": total,
            "enrolledIn2Sv": enrolled,
            "enforcedIn2Sv": enforced,
            "enrollmentRate": round(enrolled / max(total, 1) * 100, 1),
        }

        logger.info(
            "Security export: %d users, 2SV enrolled=%d (%.1f%%), enforced=%d",
            total, enrolled, summary["enrollmentRate"], enforced,
        )
        return [summary] + users_2sv

    def get_key(self, item: dict[str, Any]) -> str:
        if item.get("_type") == "summary":
            return "_security_summary"
        return item.get("primaryEmail", "")

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        # 2SV can't be directly toggled via API — this is a reporting resource
        # Enforcement is set per-OU via Admin console or Chrome Policy API
        if desired.get("_type") == "summary":
            return None
        logger.info(
            "Security import: 2SV enforcement is managed via OU policies, not individual user API calls."
        )
        return None
