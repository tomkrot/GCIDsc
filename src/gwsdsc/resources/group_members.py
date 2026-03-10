"""Group Members resource module."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class GroupMembersResource(BaseResource):
    NAME = "group_members"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.group.member",
        "https://www.googleapis.com/auth/admin.directory.group.member.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Group membership"
    STRIP_FIELDS = ["etag", "kind"]
    KEY_FIELDS = ["email", "_groupEmail"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export members for every group in the tenant."""
        # First list all groups
        groups: list[str] = []
        request = self.service.groups().list(
            customer=self.customer_id, maxResults=200
        )
        while request is not None:
            response = request.execute()
            groups.extend(g["email"] for g in response.get("groups", []))
            request = self.service.groups().list_next(request, response)

        # Then export members per group
        all_members: list[dict[str, Any]] = []
        for group_email in groups:
            try:
                members = self._list_members(group_email)
                for m in members:
                    m["_groupEmail"] = group_email
                all_members.extend(members)
            except Exception as exc:
                logger.warning("Cannot list members of %s: %s", group_email, exc)

        logger.info("Exported %d memberships across %d groups", len(all_members), len(groups))
        return all_members

    def get_key(self, item: dict[str, Any]) -> str:
        return f"{item.get('_groupEmail', '')}:{item.get('email', item.get('id', ''))}"

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        group_email = desired.pop("_groupEmail", None)
        if not group_email:
            raise ValueError("_groupEmail is required for group_members import")

        body = {k: v for k, v in desired.items() if k not in ("id", *self.STRIP_FIELDS)}

        if existing:
            return (
                self.service.members()
                .update(groupKey=group_email, memberKey=existing["email"], body=body)
                .execute()
            )
        else:
            return (
                self.service.members()
                .insert(groupKey=group_email, body=body)
                .execute()
            )

    def delete_one(self, existing: dict[str, Any]) -> None:
        group_email = existing.get("_groupEmail")
        member_email = existing.get("email", existing.get("id"))
        if group_email and member_email:
            self.service.members().delete(
                groupKey=group_email, memberKey=member_email
            ).execute()

    def _list_members(self, group_email: str) -> list[dict[str, Any]]:
        members: list[dict[str, Any]] = []
        request = self.service.members().list(groupKey=group_email, maxResults=200)
        while request is not None:
            response = request.execute()
            members.extend(response.get("members", []))
            request = self.service.members().list_next(request, response)
        return members
