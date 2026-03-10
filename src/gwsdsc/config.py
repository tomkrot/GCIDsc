"""Configuration loader and validation for GoogleWorkspaceDsc."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Tenant configuration
# ---------------------------------------------------------------------------

class CredentialsConfig(BaseModel):
    """How we authenticate to Google APIs.

    Secrets (service account keys) can be retrieved at runtime from:
      * ``file`` — plain file path (legacy, not recommended for CI/CD)
      * ``env`` — environment variable containing base64/raw JSON
      * ``google_secret_manager`` — Google Cloud Secret Manager
      * ``azure_key_vault`` — Azure Key Vault
    """

    type: Literal["service_account", "oauth", "adc"] = "service_account"
    delegated_admin_email: str | None = None
    scopes: list[str] = Field(default_factory=list)

    # --- Secret backend selection ---
    secret_backend: Literal["file", "env", "google_secret_manager", "azure_key_vault"] = "file"

    # file backend (legacy)
    service_account_key_path: str | None = None

    # env backend
    secret_env: str | None = Field(None, description="Env var name holding base64/raw JSON key")

    # Google Secret Manager backend
    secret_ref: str | None = Field(
        None,
        description=(
            "Full resource name (projects/<p>/secrets/<s>/versions/<v>) "
            "or just the secret name"
        ),
    )
    google_project_id: str | None = None
    secret_version: str = "latest"

    # Azure Key Vault backend
    azure_vault_url: str | None = Field(None, description="e.g. https://my-vault.vault.azure.net")
    azure_secret_name: str | None = None
    azure_secret_version: str | None = None
    azure_tenant_id: str | None = None
    azure_client_id: str | None = None
    azure_client_secret_env: str | None = Field(
        None, description="Env var name holding the Azure SP client secret"
    )

    @field_validator("service_account_key_path", mode="before")
    @classmethod
    def expand_env(cls, v: str | None) -> str | None:
        if v and v.startswith("$"):
            return os.environ.get(v.lstrip("$"), v)
        return v

    def resolve_key_info(self) -> dict:
        """Resolve the service account key to an in-memory dict.

        No temporary files are created — the key material stays in memory
        and is passed directly to ``from_service_account_info()``.
        """
        from gwsdsc.secrets import resolve_credentials

        return resolve_credentials(self.model_dump())


class StoreConfig(BaseModel):
    """Where exported artifacts are persisted."""

    type: Literal["git", "gcs", "local"] = "local"
    path: str = "artifacts"
    # Git options
    git_remote: str | None = None
    git_branch: str = "main"
    git_commit_message_template: str = "gwsdsc export {timestamp}"
    # GCS options
    gcs_bucket: str | None = None
    gcs_prefix: str = "exports/"


class TenantConfig(BaseModel):
    """Top-level tenant configuration."""

    tenant_name: str
    customer_id: str = "my_customer"
    primary_domain: str
    credentials: CredentialsConfig
    store: StoreConfig = StoreConfig()
    resources: list[str] = Field(
        default_factory=lambda: ["all"],
        description="Resource modules to export. Use 'all' for everything.",
    )
    exclude_resources: list[str] = Field(
        default_factory=list,
        description="Resource modules to skip even when 'all' is selected.",
    )
    export_options: dict = Field(
        default_factory=dict,
        description="Per-resource overrides, e.g. users.include_suspended: false",
    )


# ---------------------------------------------------------------------------
# Resource catalogue configuration
# ---------------------------------------------------------------------------

class ResourceEntry(BaseModel):
    """Metadata for a single resource module."""

    name: str
    enabled: bool = True
    importable: bool = True
    api_service: str = "admin"
    api_version: str = "directory_v1"
    scopes: list[str] = Field(default_factory=list)
    description: str = ""


class ResourceCatalogue(BaseModel):
    resources: list[ResourceEntry] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_tenant_config(path: str | Path) -> TenantConfig:
    """Load and validate a tenant.yaml file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Tenant config not found: {p}")
    with p.open() as fh:
        raw = yaml.safe_load(fh)
    return TenantConfig(**raw)


def load_resource_catalogue(path: str | Path | None = None) -> ResourceCatalogue:
    """Load the resource catalogue or return built-in defaults."""
    if path and Path(path).exists():
        with open(path) as fh:
            raw = yaml.safe_load(fh)
        return ResourceCatalogue(**raw)
    return _builtin_catalogue()


def _builtin_catalogue() -> ResourceCatalogue:
    """Hard-coded catalogue of all built-in resource modules."""
    entries = [
        ResourceEntry(
            name="customer",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.customer.readonly"],
            description="Customer / tenant-level settings",
        ),
        ResourceEntry(
            name="org_units",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.orgunit"],
            description="Organizational units",
        ),
        ResourceEntry(
            name="users",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.user.readonly"],
            description="User accounts (config-relevant fields only, not passwords)",
        ),
        ResourceEntry(
            name="groups",
            api_service="admin",
            api_version="directory_v1",
            scopes=[
                "https://www.googleapis.com/auth/admin.directory.group.readonly",
                "https://www.googleapis.com/auth/apps.groups.settings",
            ],
            description="Groups and group settings",
        ),
        ResourceEntry(
            name="group_members",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.group.member.readonly"],
            description="Group membership",
        ),
        ResourceEntry(
            name="roles",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly"],
            description="Admin roles",
        ),
        ResourceEntry(
            name="role_assignments",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly"],
            description="Role-to-user assignments",
        ),
        ResourceEntry(
            name="domains",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.domain.readonly"],
            importable=False,
            description="Verified domains",
        ),
        ResourceEntry(
            name="schemas",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.userschema"],
            description="Custom user schemas",
        ),
        ResourceEntry(
            name="app_access",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.user.security"],
            importable=False,
            description="Third-party app tokens (read-only audit)",
        ),
        ResourceEntry(
            name="chrome_policies",
            api_service="chromepolicy",
            api_version="v1",
            scopes=["https://www.googleapis.com/auth/chrome.management.policy"],
            description="Chrome browser and OS policies",
        ),
        ResourceEntry(
            name="email_settings",
            api_service="gmail",
            api_version="v1",
            scopes=["https://www.googleapis.com/auth/gmail.settings.basic"],
            description="Gmail routing, compliance, transport rules",
        ),
        ResourceEntry(
            name="security",
            api_service="admin",
            api_version="directory_v1",
            scopes=[
                "https://www.googleapis.com/auth/admin.directory.user.security",
            ],
            description="Security settings (2SV enforcement, session controls)",
        ),
        ResourceEntry(
            name="calendar_resources",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.resource.calendar"],
            description="Calendar resources (rooms, equipment)",
        ),
        ResourceEntry(
            name="mobile_devices",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://www.googleapis.com/auth/admin.directory.device.mobile.readonly"],
            importable=False,
            description="Mobile device inventory (read-only)",
        ),
        # ---- Cloud Identity API resources ----
        ResourceEntry(
            name="ci_policies",
            api_service="cloudidentity",
            api_version="v1",
            scopes=[
                "https://www.googleapis.com/auth/cloud-identity.policies",
                "https://www.googleapis.com/auth/cloud-identity.policies.readonly",
            ],
            description="Cloud Identity policies (security, API controls, Gmail, Drive, Calendar, DLP, etc.)",
        ),
        ResourceEntry(
            name="ci_saml_sso_profiles",
            api_service="cloudidentity",
            api_version="v1",
            scopes=[
                "https://www.googleapis.com/auth/cloud-identity.inboundsso",
                "https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly",
            ],
            description="SAML SSO profiles (IdP configuration, certificates)",
        ),
        ResourceEntry(
            name="ci_oidc_sso_profiles",
            api_service="cloudidentity",
            api_version="v1",
            scopes=[
                "https://www.googleapis.com/auth/cloud-identity.inboundsso",
                "https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly",
            ],
            description="OIDC SSO profiles",
        ),
        ResourceEntry(
            name="ci_sso_assignments",
            api_service="cloudidentity",
            api_version="v1",
            scopes=[
                "https://www.googleapis.com/auth/cloud-identity.inboundsso",
                "https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly",
            ],
            description="SSO profile assignments to OUs and groups",
        ),
        ResourceEntry(
            name="ci_devices",
            api_service="cloudidentity",
            api_version="v1",
            scopes=[
                "https://www.googleapis.com/auth/cloud-identity.devices",
                "https://www.googleapis.com/auth/cloud-identity.devices.readonly",
            ],
            importable=False,
            description="Cloud Identity device inventory and endpoint state",
        ),
        ResourceEntry(
            name="ci_groups",
            api_service="cloudidentity",
            api_version="v1",
            scopes=[
                "https://www.googleapis.com/auth/cloud-identity.groups",
                "https://www.googleapis.com/auth/cloud-identity.groups.readonly",
            ],
            description="Cloud Identity groups (security labels, dynamic memberships)",
        ),
        ResourceEntry(
            name="ci_user_invitations",
            api_service="cloudidentity",
            api_version="v1",
            scopes=["https://www.googleapis.com/auth/cloud-identity"],
            importable=False,
            description="Cloud Identity user invitations (unmanaged account cleanup)",
        ),
        # ---- Access Context Manager ----
        ResourceEntry(
            name="context_aware_access",
            api_service="accesscontextmanager",
            api_version="v1",
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            description="Context-Aware Access — access levels, service perimeters (BeyondCorp)",
        ),
        # ---- Google Vault ----
        ResourceEntry(
            name="vault_retention",
            api_service="vault",
            api_version="v1",
            scopes=[
                "https://www.googleapis.com/auth/ediscovery",
                "https://www.googleapis.com/auth/ediscovery.readonly",
            ],
            description="Google Vault matters, retention rules, and legal holds",
        ),
        # ---- Chrome Enterprise Core ----
        ResourceEntry(
            name="chrome_browsers",
            api_service="admin",
            api_version="directory_v1",
            scopes=[
                "https://www.googleapis.com/auth/admin.directory.device.chromebrowsers",
                "https://www.googleapis.com/auth/admin.directory.device.chromebrowsers.readonly",
            ],
            importable=False,
            description="Chrome Enterprise Core — enrolled browsers, extensions, enrollment tokens",
        ),
        ResourceEntry(
            name="chrome_printers",
            api_service="admin",
            api_version="directory_v1",
            scopes=[
                "https://www.googleapis.com/auth/admin.chrome.printers",
                "https://www.googleapis.com/auth/admin.chrome.printers.readonly",
            ],
            description="Chrome printer management — CUPS printers and print servers",
        ),
        ResourceEntry(
            name="chromeos_telemetry",
            api_service="chromemanagement",
            api_version="v1",
            scopes=["https://www.googleapis.com/auth/chrome.management.telemetry.readonly"],
            importable=False,
            description="ChromeOS device telemetry — fleet health and hardware inventory",
        ),
        # ---- Alert Center ----
        ResourceEntry(
            name="alert_center",
            api_service="alertcenter",
            api_version="v1beta1",
            scopes=["https://www.googleapis.com/auth/apps.alerts"],
            importable=False,
            description="Alert Center — alert rules, active alerts, notification config",
        ),
        # ---- Enterprise License Manager ----
        ResourceEntry(
            name="license_assignments",
            api_service="licensing",
            api_version="v1",
            scopes=[
                "https://www.googleapis.com/auth/apps.licensing",
                "https://www.googleapis.com/auth/apps.licensing.readonly",
            ],
            description="Enterprise license assignments (SKU-to-user mappings)",
        ),
        # ---- Legacy Admin Settings ----
        ResourceEntry(
            name="admin_settings_legacy",
            api_service="admin",
            api_version="directory_v1",
            scopes=["https://apps-apis.google.com/a/feeds/domain/"],
            importable=False,
            description="Legacy Admin Settings — SMTP gateway, email routing, domain info",
        ),
        # ---- Contact Delegation ----
        ResourceEntry(
            name="contact_delegation",
            api_service="admin",
            api_version="directory_v1",
            scopes=[
                "https://www.googleapis.com/auth/admin.contact.delegation",
                "https://www.googleapis.com/auth/admin.contact.delegation.readonly",
            ],
            description="Contact delegation — cross-account contact access grants",
        ),
        # ---- Data Transfer ----
        ResourceEntry(
            name="data_transfers",
            api_service="admin",
            api_version="datatransfer_v1",
            scopes=[
                "https://www.googleapis.com/auth/admin.datatransfer",
                "https://www.googleapis.com/auth/admin.datatransfer.readonly",
            ],
            importable=False,
            description="Data Transfer — transferable apps and transfer records (audit)",
        ),
    ]
    return ResourceCatalogue(resources=entries)
