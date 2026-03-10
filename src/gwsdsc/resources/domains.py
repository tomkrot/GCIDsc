"""Domains resource module."""

from __future__ import annotations

from typing import Any

from gwsdsc.resources.base import BaseResource


class DomainsResource(BaseResource):
    NAME = "domains"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.domain",
        "https://www.googleapis.com/auth/admin.directory.domain.readonly",
    ]
    IMPORTABLE = False
    DESCRIPTION = "Verified domains (read-only — cannot programmatically verify)"
    STRIP_FIELDS = ["etag", "kind"]

    def export_all(self) -> list[dict[str, Any]]:
        response = self.service.domains().list(customer=self.customer_id).execute()
        return response.get("domains", [])

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("domainName", "")
