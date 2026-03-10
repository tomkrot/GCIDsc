"""Cloud Identity — User Invitations (unmanaged account cleanup)."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class CiUserInvitationsResource(BaseResource):
    NAME = "ci_user_invitations"
    API_SERVICE = "cloudidentity"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/cloud-identity",
    ]
    IMPORTABLE = False
    DESCRIPTION = "Cloud Identity user invitations — unmanaged accounts pending conversion"
    STRIP_FIELDS = []

    def export_all(self) -> list[dict[str, Any]]:
        invitations: list[dict[str, Any]] = []
        parent = f"customers/{self.customer_id}"

        try:
            request = self.service.customers().userinvitations().list(
                parent=parent, pageSize=100,
            )
            while request is not None:
                response = request.execute()
                invitations.extend(response.get("userInvitations", []))
                page_token = response.get("nextPageToken")
                request = (
                    self.service.customers().userinvitations().list(
                        parent=parent, pageSize=100, pageToken=page_token,
                    ) if page_token else None
                )
        except Exception as exc:
            logger.debug("Cannot list user invitations: %s", exc)

        logger.info("Exported %d user invitations", len(invitations))
        return invitations

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("name", item.get("email", ""))
