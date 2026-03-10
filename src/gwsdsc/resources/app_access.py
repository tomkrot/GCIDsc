"""App Access / Third-party tokens resource module (read-only audit)."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class AppAccessResource(BaseResource):
    NAME = "app_access"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.user.security",
    ]
    IMPORTABLE = False
    DESCRIPTION = "Third-party app tokens granted by users (read-only audit)"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export all third-party tokens across all users.

        Note: This iterates users and fetches tokens per-user.
        For large tenants consider limiting via options.max_users.
        """
        max_users = self.options.get("max_users", 1000)
        tokens: list[dict[str, Any]] = []

        request = self.service.users().list(
            customer=self.customer_id, maxResults=min(max_users, 500), projection="basic"
        )
        user_count = 0

        while request is not None and user_count < max_users:
            response = request.execute()
            for user in response.get("users", []):
                user_count += 1
                if user_count > max_users:
                    break
                try:
                    tok_response = (
                        self.service.tokens()
                        .list(userKey=user["primaryEmail"])
                        .execute()
                    )
                    for tok in tok_response.get("items", []):
                        tok["_userEmail"] = user["primaryEmail"]
                        tokens.append(tok)
                except Exception:
                    pass  # User may have no tokens or insufficient permissions
            request = self.service.users().list_next(request, response)

        logger.info("Exported %d third-party tokens from %d users", len(tokens), user_count)
        return tokens

    def get_key(self, item: dict[str, Any]) -> str:
        return f"{item.get('_userEmail', '')}:{item.get('clientId', '')}"
