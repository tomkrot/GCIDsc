"""Resource module registry — 31 modules across 11 Google APIs."""

from __future__ import annotations
from typing import TYPE_CHECKING

from gwsdsc.resources.admin_settings_legacy import AdminSettingsLegacyResource
from gwsdsc.resources.alert_center import AlertCenterResource
from gwsdsc.resources.app_access import AppAccessResource
from gwsdsc.resources.calendar_resources import CalendarResourcesResource
from gwsdsc.resources.chrome_browsers import ChromeBrowsersResource
from gwsdsc.resources.chrome_policies import ChromePoliciesResource
from gwsdsc.resources.chrome_printers import ChromePrintersResource
from gwsdsc.resources.chromeos_telemetry import ChromeOSTelemetryResource
from gwsdsc.resources.ci_devices import CiDevicesResource
from gwsdsc.resources.ci_groups import CiGroupsResource
from gwsdsc.resources.ci_oidc_sso_profiles import CiOidcSsoProfilesResource
from gwsdsc.resources.ci_policies import CiPoliciesResource
from gwsdsc.resources.ci_saml_sso_profiles import CiSamlSsoProfilesResource
from gwsdsc.resources.ci_sso_assignments import CiSsoAssignmentsResource
from gwsdsc.resources.ci_user_invitations import CiUserInvitationsResource
from gwsdsc.resources.contact_delegation import ContactDelegationResource
from gwsdsc.resources.context_aware_access import ContextAwareAccessResource
from gwsdsc.resources.customer import CustomerResource
from gwsdsc.resources.data_transfers import DataTransfersResource
from gwsdsc.resources.domains import DomainsResource
from gwsdsc.resources.email_settings import EmailSettingsResource
from gwsdsc.resources.group_members import GroupMembersResource
from gwsdsc.resources.groups import GroupsResource
from gwsdsc.resources.license_assignments import LicenseAssignmentsResource
from gwsdsc.resources.mobile_devices import MobileDevicesResource
from gwsdsc.resources.org_units import OrgUnitsResource
from gwsdsc.resources.role_assignments import RoleAssignmentsResource
from gwsdsc.resources.roles import RolesResource
from gwsdsc.resources.schemas import SchemasResource
from gwsdsc.resources.security import SecurityResource
from gwsdsc.resources.users import UsersResource
from gwsdsc.resources.vault_retention import VaultRetentionResource

if TYPE_CHECKING:
    from gwsdsc.resources.base import BaseResource

REGISTRY: dict[str, type[BaseResource]] = {
    cls.NAME: cls  # type: ignore[attr-defined]
    for cls in [
        AdminSettingsLegacyResource, AlertCenterResource, AppAccessResource,
        CalendarResourcesResource, ChromeBrowsersResource, ChromePoliciesResource,
        ChromePrintersResource, ChromeOSTelemetryResource, CiDevicesResource,
        CiGroupsResource, CiOidcSsoProfilesResource, CiPoliciesResource,
        CiSamlSsoProfilesResource, CiSsoAssignmentsResource, CiUserInvitationsResource,
        ContactDelegationResource, ContextAwareAccessResource, CustomerResource,
        DataTransfersResource, DomainsResource, EmailSettingsResource,
        GroupMembersResource, GroupsResource, LicenseAssignmentsResource,
        MobileDevicesResource, OrgUnitsResource, RoleAssignmentsResource,
        RolesResource, SchemasResource, SecurityResource, UsersResource,
        VaultRetentionResource,
    ]
}

ALL_RESOURCE_NAMES = sorted(REGISTRY.keys())

def get_resource_class(name: str) -> type[BaseResource]:
    if name not in REGISTRY:
        raise KeyError(f"Unknown resource '{name}'. Available: {', '.join(ALL_RESOURCE_NAMES)}")
    return REGISTRY[name]
