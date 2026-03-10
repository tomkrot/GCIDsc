"""Contact Delegation API — cross-account contact access grants."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class ContactDelegationResource(BaseResource):
    NAME = "contact_delegation"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.contact.delegation",
        "https://www.googleapis.com/auth/admin.contact.delegation.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Contact delegation — cross-account contact access grants"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export contact delegations across all users.

        Iterates users and fetches their contact delegates.
        Limited by options.max_users (default 1000).
        """
        delegations: list[dict[str, Any]] = []
        max_users = self.options.get("max_users", 1000)
        user_count = 0

        request = self.service.users().list(
            customer=self.customer_id, maxResults=min(max_users, 500), projection="basic"
        )
        while request is not None and user_count < max_users:
            response = request.execute()
            for user in response.get("users", []):
                user_count += 1
                if user_count > max_users:
                    break
                email = user.get("primaryEmail", "")
                try:
                    delegates = self._list_delegates(email)
                    for d in delegates:
                        d["_delegatorEmail"] = email
                    delegations.extend(delegates)
                except Exception:
                    pass
            request = self.service.users().list_next(request, response)

        logger.info("Exported %d contact delegations from %d users", len(delegations), user_count)
        return delegations

    def get_key(self, item: dict[str, Any]) -> str:
        return f"{item.get('_delegatorEmail', '')}:{item.get('delegateEmail', '')}"

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        delegator = desired.get("_delegatorEmail")
        delegate = desired.get("delegateEmail")
        if not delegator or not delegate:
            return None
        if existing:
            return None  # Delegation is binary — exists or not
        try:
            return self.service.users().contacts().delegates().create(
                parent=delegator, body={"delegateEmail": delegate}
            ).execute()
        except Exception as exc:
            logger.debug("Cannot create contact delegation %s → %s: %s", delegator, delegate, exc)
            return None

    def _list_delegates(self, user_email: str) -> list[dict[str, Any]]:
        try:
            resp = self.service.users().contacts().delegates().list(parent=user_email).execute()
            return resp.get("delegates", [])
        except Exception:
            return []
