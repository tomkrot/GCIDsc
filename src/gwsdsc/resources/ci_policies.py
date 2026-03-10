"""Cloud Identity Policy API resource module.

Exports the full set of admin-configurable policies from the Cloud Identity
Policy API.  These cover hundreds of Workspace settings grouped into
categories such as:

  * Security (2SV, session controls, password policies)
  * API controls (third-party app access, DWD)
  * Gmail (routing, compliance, spam filters)
  * Drive (sharing, DLP, external access)
  * Calendar (sharing defaults, resource booking)
  * Groups (creation, external membership)
  * Chat, Meet, Sites, Vault, Marketplace …
  * Data protection rules & DLP

The Policy API returns policies as Setting objects scoped to OrgUnits
or Groups via a PolicyQuery.  This module exports *all* admin-configured
policies (not system defaults) so they can be versioned, diffed, and
re-applied to another tenant.

API Reference:
  https://cloud.google.com/identity/docs/reference/rest/v1/policies
"""

from __future__ import annotations

import logging
from typing import Any

from gwsdsc.resources.base import BaseResource

logger = logging.getLogger(__name__)

# Complete list of setting type families surfaced by the Policy API (GA Feb 2025).
# See https://docs.cloud.google.com/identity/docs/concepts/supported-policy-api-settings
_SETTING_TYPE_FAMILIES = [
    # ── Security ──────────────────────────────────────────────────
    "security",
    "security.sign_in",
    "security.session_controls",
    "security.password_management",
    "security.super_admin_account_recovery",
    "security.user_account_recovery",
    "security.less_secure_apps",
    "security.advanced_protection_program",
    "security.login_challenges",
    # ── API Controls ──────────────────────────────────────────────
    "api_controls",
    "api_controls.unconfigured_third_party_apps",
    "api_controls.third_party_apps_access",
    "api_controls.domain_wide_delegation",
    "api_controls.apps_access_settings",
    "api_controls.apps_internal",
    "api_controls.apps_trusted",
    "api_controls.apps_limited",
    "api_controls.apps_blocked",
    # ── Gmail ─────────────────────────────────────────────────────
    "gmail",
    "gmail.compliance",
    "gmail.routing",
    "gmail.spam_filter",
    "gmail.email_authentication",
    "gmail.end_user_access",
    "gmail.confidential_mode",
    "gmail.enhanced_pre_delivery_scanning",
    "gmail.spoofing_authentication",
    "gmail.links_and_external_images",
    "gmail.attachments",
    "gmail.pop_imap_access",
    "gmail.mail_delegation",
    "gmail.per_user_outbound_gateway",
    "gmail.name_format",
    # ── Drive ─────────────────────────────────────────────────────
    "drive",
    "drive.sharing",
    "drive.sharing_external",
    "drive.data_protection",
    "drive.features",
    "drive.transfer_ownership",
    "drive.shared_drives",
    "drive.drive_sdk",
    "drive.drive_for_desktop",
    # ── Calendar ──────────────────────────────────────────────────
    "calendar",
    "calendar.sharing",
    "calendar.general",
    "calendar.external_invitations",
    # ── Groups ────────────────────────────────────────────────────
    "groups",
    "groups.sharing",
    "groups.creation",
    # ── Chat ──────────────────────────────────────────────────────
    "chat",
    "chat.spaces",
    "chat.history",
    "chat.external",
    "chat.apps",
    "chat.space_history",
    "chat.read_status",
    # ── Meet ──────────────────────────────────────────────────────
    "meet",
    "meet.safety",
    "meet.video",
    "meet.recording",
    # ── Sites ─────────────────────────────────────────────────────
    "sites",
    "sites.creation",
    # ── Vault ─────────────────────────────────────────────────────
    "vault",
    # ── Marketplace ───────────────────────────────────────────────
    "workspace_marketplace",
    "workspace_marketplace.apps_allowlist",
    # ── Data Protection / DLP ─────────────────────────────────────
    "data_protection",
    "data_protection.rule",
    "data_protection.detector",
    # ── Services & Apps ───────────────────────────────────────────
    "directory",
    "classroom",
    "classroom.guardian",
    "classroom.roster_import",
    "takeout",
    "user_takeout",
    "alerts",
    "alerts.system_defined",
    "currents",
    "keep",
    "appsheet",
    # ── Service Status (per-app on/off per OU) ────────────────────
    "service_status",
]


class CiPoliciesResource(BaseResource):
    """Cloud Identity Policy API — admin-configurable tenant policies."""

    NAME = "ci_policies"
    API_SERVICE = "cloudidentity"
    API_VERSION = "v1"
    SCOPES = [
        "https://www.googleapis.com/auth/cloud-identity",
        "https://www.googleapis.com/auth/cloud-identity.policies",
        "https://www.googleapis.com/auth/cloud-identity.policies.readonly",
    ]
    IMPORTABLE = True
    DESCRIPTION = "Cloud Identity policies (security, API controls, Gmail, Drive, Calendar, Groups, DLP, etc.)"
    STRIP_FIELDS = []
    KEY_FIELDS = ["name"]

    def export_all(self) -> list[dict[str, Any]]:
        """Export all admin-configured policies via the Policy API.

        Uses ``policies.list()`` with a filter to retrieve policies scoped
        to every setting type family.
        """
        all_policies: list[dict[str, Any]] = []
        customer_ref = f"customers/{self.customer_id}"

        # The Policy API supports listing policies with a setting type filter
        families_to_export = self.options.get("setting_families", _SETTING_TYPE_FAMILIES)

        for family in families_to_export:
            try:
                policies = self._list_policies_for_family(customer_ref, family)
                for policy in policies:
                    policy["_settingFamily"] = family
                all_policies.extend(policies)
            except Exception as exc:
                logger.debug("No policies for family '%s': %s", family, exc)

        logger.info("Exported %d Cloud Identity policies", len(all_policies))
        return all_policies

    def get_key(self, item: dict[str, Any]) -> str:
        return item.get("name", f"{item.get('_settingFamily', '')}:{item.get('setting', {}).get('type', '')}")

    def import_one(
        self, desired: dict[str, Any], existing: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Create or update a policy.

        Uses ``policies.patch()`` if the policy exists, or
        ``policies.create()`` for new ones.
        """
        customer_ref = f"customers/{self.customer_id}"
        body = {
            k: v
            for k, v in desired.items()
            if k not in ("name", "_settingFamily", *self.STRIP_FIELDS)
        }

        if existing and existing.get("name"):
            # Patch existing policy
            return (
                self.service.policies()
                .patch(name=existing["name"], body=body, updateMask="*")
                .execute()
            )
        else:
            # Create new policy
            return (
                self.service.policies()
                .create(parent=customer_ref, body=body)
                .execute()
            )

    def delete_one(self, existing: dict[str, Any]) -> None:
        if existing.get("name"):
            self.service.policies().delete(name=existing["name"]).execute()

    # ------------------------------------------------------------------

    def _list_policies_for_family(
        self, customer_ref: str, family: str
    ) -> list[dict[str, Any]]:
        """List policies for a specific setting type family."""
        policies: list[dict[str, Any]] = []
        filter_str = f"setting.type='{family}'"

        request = self.service.policies().list(
            parent=customer_ref,
            filter=filter_str,
            pageSize=100,
        )
        while request is not None:
            response = request.execute()
            policies.extend(response.get("policies", []))
            page_token = response.get("nextPageToken")
            if page_token:
                request = self.service.policies().list(
                    parent=customer_ref,
                    filter=filter_str,
                    pageSize=100,
                    pageToken=page_token,
                )
            else:
                request = None

        return policies
