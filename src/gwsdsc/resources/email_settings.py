"""Email Settings resource module — Gmail routing, compliance rules."""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)


class EmailSettingsResource(BaseResource):
    NAME = "email_settings"
    API_SERVICE = "gmail"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://www.googleapis.com/auth/gmail.settings.sharing",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Gmail routing, compliance, and transport rules"
    STRIP_FIELDS = ["kind"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export Gmail settings for domain-level and per-user settings.

        Domain-level settings (send-as, forwarding, IMAP/POP) are fetched
        per-user for designated admin / template users only, unless
        options.all_users is True.
        """
        settings: list[dict[str, Any]] = []
        target_users = self.options.get("target_users", [])

        if not target_users:
            logger.info("email_settings: no target_users specified, exporting domain-level only")
            return settings

        for user_email in target_users:
            try:
                # Fetch send-as, forwarding, IMAP, POP
                user_settings: dict[str, Any] = {"_userEmail": user_email}

                sas = self.service.users().settings().sendAs().list(userId=user_email).execute()
                user_settings["sendAs"] = sas.get("sendAs", [])

                filters = self.service.users().settings().filters().list(userId=user_email).execute()
                user_settings["filters"] = filters.get("filter", [])

                fwd = self.service.users().settings().getAutoForwarding(userId=user_email).execute()
                user_settings["autoForwarding"] = fwd

                imap = self.service.users().settings().getImap(userId=user_email).execute()
                user_settings["imap"] = imap

                pop = self.service.users().settings().getPop(userId=user_email).execute()
                user_settings["pop"] = pop

                vacation = self.service.users().settings().getVacation(userId=user_email).execute()
                user_settings["vacation"] = vacation

                settings.append(user_settings)
            except Exception as exc:
                logger.warning("Cannot export email settings for %s: %s", user_email, exc)

        logger.info("Exported email settings for %d users", len(settings))
        return settings

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("_userEmail", "")

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        user_email = desired.get("_userEmail")
        if not user_email:
            return None

        results: dict[str, Any] = {"_userEmail": user_email}

        if "autoForwarding" in desired:
            results["autoForwarding"] = (
                self.service.users()
                .settings()
                .updateAutoForwarding(userId=user_email, body=desired["autoForwarding"])
                .execute()
            )

        if "imap" in desired:
            results["imap"] = (
                self.service.users()
                .settings()
                .updateImap(userId=user_email, body=desired["imap"])
                .execute()
            )

        if "pop" in desired:
            results["pop"] = (
                self.service.users()
                .settings()
                .updatePop(userId=user_email, body=desired["pop"])
                .execute()
            )

        return results
