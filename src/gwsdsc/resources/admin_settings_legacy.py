"""Admin Settings API (Legacy) — SMTP gateway, email routing, domain settings.

The legacy Admin Settings API (GData/Atom-based) exposes settings not yet
fully available in the Cloud Identity Policy API, including outbound email
gateway, domain-level email routing, and legacy SSO configuration.

Note: This API uses XML over HTTP, not JSON.  We convert to dicts for
consistency with the rest of the framework.

API Reference:
  https://developers.google.com/workspace/admin/admin-settings
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)

_GD_NAMESPACE = "http://schemas.google.com/apps/2006"
_SETTINGS_FEEDS = [
    ("general/defaultLanguage", "defaultLanguage"),
    ("general/organizationName", "organizationName"),
    ("general/currentNumberOfUsers", "currentNumberOfUsers"),
    ("general/maximumNumberOfUsers", "maximumNumberOfUsers"),
    ("accountInformation/supportPIN", "supportPIN"),
    ("accountInformation/edition", "edition"),
    ("accountInformation/customerPIN", "customerPIN"),
    ("email/gateway", "emailGateway"),
    ("email/routing", "emailRouting"),
]


class AdminSettingsLegacyResource(BaseResource):
    NAME = "admin_settings_legacy"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = [
        "https://apps-apis.google.com/a/feeds/domain/",
        "https://www.googleapis.com/auth/admin.directory.domain",
    ]
    IMPORTABLE = False  # Read-only audit — use CI Policy API for writes
    DESCRIPTION = "Legacy Admin Settings — SMTP gateway, email routing, domain info"
    STRIP_FIELDS = []
    KEY_FIELDS = ["_settingName"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export legacy settings by fetching each feed endpoint.

        Note: This module attempts the legacy GData API. If the domain
        has migrated fully to the newer APIs, some feeds may return 404.
        We capture what we can and skip the rest.
        """
        all_settings: list[dict[str, Any]] = []
        primary_domain = self.options.get("primary_domain", "")

        if not primary_domain:
            logger.warning("admin_settings_legacy: primary_domain option required, skipping")
            return all_settings

        for feed_path, setting_name in _SETTINGS_FEEDS:
            try:
                url = f"https://apps-apis.google.com/a/feeds/domain/2.0/{primary_domain}/{feed_path}"
                # Use the underlying http from the service to make raw requests
                http = self.service._http
                response, content = http.request(url, method="GET")

                if response.status == 200:
                    parsed = self._parse_xml_to_dict(content.decode("utf-8"))
                    parsed["_settingName"] = setting_name
                    parsed["_feedPath"] = feed_path
                    all_settings.append(parsed)
                else:
                    logger.debug("Legacy setting %s returned HTTP %s", setting_name, response.status)
            except Exception as exc:
                logger.debug("Cannot fetch legacy setting %s: %s", setting_name, exc)

        logger.info("Exported %d legacy admin settings", len(all_settings))
        return all_settings

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("_settingName", "")

    def _parse_xml_to_dict(self, xml_content: str) -> dict[str, Any]:
        """Parse GData XML response into a simple dict."""
        result: dict[str, Any] = {}
        try:
            root = ET.fromstring(xml_content)
            for prop in root.iter(f"{{{_GD_NAMESPACE}}}property"):
                name = prop.get("name", "")
                value = prop.get("value", "")
                if name:
                    result[name] = value
        except ET.ParseError:
            result["_rawXml"] = xml_content[:2000]
        return result
