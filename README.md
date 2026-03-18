# GoogleWorkspaceDsc — Configuration as Code for Google Workspace

> A Desired State Configuration (DSC) framework for **Google Workspace / Cloud Identity** tenants.
> Inspired by [Microsoft365DscWorkshop](https://github.com/dsccommunity/Microsoft365DscWorkshop).

---

## Overview

**GoogleWorkspaceDsc** exports, versions, diffs, and re-applies the full
configuration surface of a Google Workspace (or Cloud Identity) tenant.
It treats tenant settings as *code*, enabling:

| Capability | Description |
|---|---|
| **Scheduled Export** | Nightly / on-demand snapshot of every configuration resource |
| **Versioned Artifacts** | Each export is a Git commit; every change is traceable |
| **Differential Analysis** | Semantic diff between any two snapshots (human-readable + JSON) |
| **Drift Reporting** | HTML / Markdown reports highlighting configuration drift |
| **Tenant Cloning** | Re-create (or converge) a tenant from exported configuration data |
| **CI/CD Pipelines** | Ready-made pipelines for **Azure DevOps** *and* **Google Cloud Build** |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Google Workspace Tenant                    │
│  (Admin SDK · Groups Settings · Gmail · Calendar · Chrome …) │
└───────────────────────────┬─────────────────────────────────┘
                            │  REST / gRPC
                ┌───────────▼────────────┐
                │   gwsdsc  Export Engine │
                │   (Python – Resource    │
                │    Modules per API)     │
                └───────────┬────────────┘
                            │  JSON / YAML artifacts
              ┌─────────────▼──────────────┐
              │   Versioned Artifact Store  │
              │   (Git repo  or  GCS bucket │
              │    with object versioning)  │
              └─────────────┬──────────────┘
                            │
           ┌────────────────┼────────────────┐
           ▼                ▼                ▼
    ┌────────────┐   ┌────────────┐   ┌────────────┐
    │  Diff /    │   │  Drift     │   │  Import /  │
    │  Compare   │   │  Report    │   │  Apply     │
    └────────────┘   └────────────┘   └────────────┘
```

### Pipeline Options

| Option | Stack | Scheduling | Agent OS |
|---|---|---|---|
| **A — Azure DevOps** | Azure Pipelines + Git (Azure Repos / GitHub) | Cron trigger in YAML pipeline | **Linux or Windows** (PowerShell Core) |
| **B — Google Cloud** | Cloud Build + Cloud Scheduler + GCS / Cloud Source Repos | Cloud Scheduler → Cloud Build trigger | Linux (Cloud Build workers) |

---

## Security & Robustness

**In-memory credential handling** — Service account keys are never written
to temporary files.  All secret backends (Google Secret Manager, Azure Key
Vault, environment variable) resolve to an in-memory ``dict`` that is
passed directly to ``google.oauth2.service_account.Credentials.from_service_account_info()``.
No residual key material is left on disk.

**Automatic API retry** — All Google API calls use exponential backoff via
``tenacity`` to handle HTTP 429 (rate limit) and 5xx (transient) errors.
Each resource module's ``_call_api()`` helper and the API discovery
``build()`` step are both wrapped in retry logic with up to 5 attempts and
2–60 second waits.

**Dynamic service resolution** — The API service/version mapping is inferred
from the Resource Catalogue at runtime rather than maintained as a hardcoded
dictionary.  Adding a new resource module automatically makes it discoverable
without touching the auth layer.

---

## Supported Resource Modules

Each module maps to one or more Google API endpoints.

| Module | API | Export | Import | Diff |
|---|---|---|---|---|
| **Admin SDK (Directory API)** | | | | |
| `customer` | Customers | ✅ | ✅ | ✅ |
| `org_units` | OrgUnits | ✅ | ✅ | ✅ |
| `users` | Users | ✅ | ✅ | ✅ |
| `groups` | Groups + Groups Settings | ✅ | ✅ | ✅ |
| `group_members` | Members | ✅ | ✅ | ✅ |
| `roles` | Roles | ✅ | ✅ | ✅ |
| `role_assignments` | RoleAssignments | ✅ | ✅ | ✅ |
| `domains` | Domains | ✅ | ⚠️ | ✅ |
| `schemas` | Schemas | ✅ | ✅ | ✅ |
| `app_access` | 3rd-party app tokens | ✅ | ❌ | ✅ |
| `email_settings` | Gmail Routing/Compliance | ✅ | ✅ | ✅ |
| `security` | 2SV posture | ✅ | ✅ | ✅ |
| `calendar_resources` | Calendar rooms/equipment | ✅ | ✅ | ✅ |
| `mobile_devices` | MobileDevices | ✅ | ❌ | ✅ |
| **Chrome Enterprise** | | | | |
| `chrome_policies` | Chrome Policy API (per-OU) | ✅ | ✅ | ✅ |
| `chrome_browsers` | CBCM enrolled browsers/extensions/tokens | ✅ | ❌ | ✅ |
| `chrome_printers` | CUPS printers/print servers | ✅ | ✅ | ✅ |
| `chromeos_telemetry` | ChromeOS fleet health/hardware | ✅ | ❌ | ✅ |
| **Cloud Identity** | | | | |
| `ci_policies` | Policy API (90+ setting families: security, DLP, API controls, Gmail, Drive, Calendar, Chat, Meet, Classroom, etc.) | ✅ | ✅ | ✅ |
| `ci_saml_sso_profiles` | SAML SSO profiles + IdP certs | ✅ | ✅ | ✅ |
| `ci_oidc_sso_profiles` | OIDC SSO profiles | ✅ | ✅ | ✅ |
| `ci_sso_assignments` | SSO profile-to-OU/Group bindings | ✅ | ✅ | ✅ |
| `ci_devices` | Devices + DeviceUsers | ✅ | ❌ | ✅ |
| `ci_groups` | Security groups, dynamic memberships | ✅ | ✅ | ✅ |
| `ci_user_invitations` | Unmanaged account invitations | ✅ | ❌ | ✅ |
| **Access Context Manager** | | | | |
| `context_aware_access` | Access levels + service perimeters (BeyondCorp) | ✅ | ✅ | ✅ |
| **Google Vault** | | | | |
| `vault_retention` | Matters, retention rules, legal holds | ✅ | ✅ | ✅ |
| **Alert Center** | | | | |
| `alert_center` | Alert rules, active alerts, notification config | ✅ | ❌ | ✅ |
| **License Manager** | | | | |
| `license_assignments` | SKU-to-user license assignments | ✅ | ✅ | ✅ |
| **Legacy / Other** | | | | |
| `admin_settings_legacy` | SMTP gateway, email routing, domain info | ✅ | ❌ | ✅ |
| `contact_delegation` | Cross-account contact access | ✅ | ✅ | ✅ |
| `data_transfers` | Transferable apps, transfer records | ✅ | ❌ | ✅ |

> ⚠️ = Partial (verify-only for verified domains)
> ❌ = Read-only / not applicable for import

---

## Quick Start

### 1. Prerequisites

```bash
# Python 3.10+
pip install -e ".[dev]"

# Google Cloud service account with domain-wide delegation
# See docs/authentication.md for full setup
```

### 2. Configure

```bash
cp config/tenant.yaml.example  config/tenant.yaml
cp config/resources.yaml.example  config/resources.yaml
# Edit tenant.yaml with your domain, customer ID, and credentials path
```

### 3. Export

```bash
# Full export to ./artifacts/
gwsdsc export --config config/tenant.yaml

# Export specific resources only
gwsdsc export --config config/tenant.yaml --resources users,groups,org_units
```

### 4. Diff

```bash
# Compare two snapshots (Git tags, commit SHAs, or directories)
gwsdsc diff --baseline artifacts/2025-03-01 --target artifacts/2025-03-09

# Generate HTML drift report
gwsdsc diff --baseline v1.0 --target v1.1 --report html --output drift-report.html
```

### 5. Apply / Import

```bash
# Dry-run (plan)
gwsdsc apply --config config/tenant.yaml --source artifacts/latest --plan

# Apply to target tenant
gwsdsc apply --config config/tenant.yaml --source artifacts/latest --confirm
```

---

## Pipeline Setup

### Option A — Azure DevOps

```bash
# Copy pipeline definitions into your Azure DevOps repo
cp -r pipelines/azure-devops/* .

# The main pipeline (azure-pipelines.yml) provides:
#   • Scheduled nightly export (cron)
#   • Artifact commit + push
#   • Diff against previous export
#   • Drift report published as pipeline artifact
#   • Manual approval gate before apply
```

See [pipelines/azure-devops/README.md](pipelines/azure-devops/README.md).

### Option B — Google Cloud Native

```bash
# Deploy with Terraform
cd pipelines/google-cloud/terraform
terraform init
terraform apply

# This creates:
#   • Cloud Source Repository (or connects to GitHub)
#   • Cloud Build triggers (export + apply)
#   • Cloud Scheduler job for nightly export
#   • Secret Manager entries for service account keys
#   • GCS bucket for reports
```

See [pipelines/google-cloud/README.md](pipelines/google-cloud/README.md).

---

## Project Structure

```
GoogleWorkspaceDsc/
├── README.md
├── pyproject.toml
├── Makefile
├── src/
│   └── gwsdsc/
│       ├── __init__.py
│       ├── cli.py                  # CLI entry point (Typer)
│       ├── auth.py                 # Service-account auth helpers
│       ├── config.py               # YAML config loader + validation
│       ├── secrets.py              # Azure Key Vault / GCP Secret Manager
│       ├── engine/
│       │   ├── export_engine.py    # Export orchestrator
│       │   ├── import_engine.py    # Import / Apply orchestrator
│       │   ├── diff_engine.py      # Semantic diff
│       │   └── report_engine.py    # HTML / Markdown reporting
│       ├── resources/
│       │   ├── base.py             # Abstract base resource
│       │   ├── customer.py
│       │   ├── org_units.py
│       │   ├── users.py
│       │   ├── groups.py
│       │   ├── group_members.py
│       │   ├── roles.py
│       │   ├── role_assignments.py
│       │   ├── domains.py
│       │   ├── schemas.py
│       │   ├── app_access.py
│       │   ├── chrome_policies.py
│       │   ├── email_settings.py
│       │   ├── security.py
│       │   ├── calendar_resources.py
│       │   ├── mobile_devices.py
│       │   ├── ci_policies.py       # Cloud Identity Policy API
│       │   ├── ci_saml_sso_profiles.py  # SAML SSO profiles
│       │   ├── ci_oidc_sso_profiles.py  # OIDC SSO profiles
│       │   ├── ci_sso_assignments.py    # SSO → OU/Group assignments
│       │   ├── ci_devices.py        # CI device inventory
│       │   └── ci_groups.py         # CI groups (security, dynamic)
│       │   ├── ci_user_invitations.py   # Unmanaged account invitations
│       │   ├── context_aware_access.py  # BeyondCorp access levels
│       │   ├── vault_retention.py   # Vault matters, retention, holds
│       │   ├── chrome_browsers.py   # CBCM enrolled browsers
│       │   ├── chrome_printers.py   # CUPS printer fleet
│       │   ├── chromeos_telemetry.py    # ChromeOS device health
│       │   ├── alert_center.py      # Alert rules and config
│       │   ├── license_assignments.py   # SKU-to-user licenses
│       │   ├── admin_settings_legacy.py # SMTP gateway, email routing
│       │   ├── contact_delegation.py    # Cross-account contacts
│       │   └── data_transfers.py    # Transfer records (audit)
│       └── store/
│           ├── base.py             # Abstract store interface
│           ├── git_store.py        # Git-based versioned storage
│           └── gcs_store.py        # GCS versioned bucket storage
├── pipelines/
│   ├── azure-devops/
│   │   └── azure-pipelines.yml
│   └── google-cloud/
│       ├── cloudbuild-export.yaml
│       ├── cloudbuild-apply.yaml
│       └── terraform/
│           ├── main.tf
│           ├── variables.tf
│           └── outputs.tf
├── config/
│   ├── tenant.yaml.example
│   └── resources.yaml.example
├── tests/
│   ├── conftest.py
│   ├── test_diff_engine.py
│   ├── test_resources.py
│   └── test_secrets.py
└── docs/
    ├── authentication.md
    ├── extending-resources.md
    ├── api-gap-analysis.md
    ├── implementation-azure-devops.md
    └── implementation-google-cloud.md
```

---

## Extending

To add a new resource module, subclass `BaseResource`:

```python
from gwsdsc.resources.base import BaseResource

class MyNewResource(BaseResource):
    NAME = "my_resource"
    API_SERVICE = "admin"
    API_VERSION = "directory_v1"
    SCOPES = ["https://www.googleapis.com/auth/admin.directory..."]
    IMPORTABLE = True

    def export_all(self) -> list[dict]:
        """Fetch all instances from the API."""
        ...

    def import_one(self, desired: dict, existing: dict | None) -> None:
        """Create or update a single instance."""
        ...
```

Then register it in `src/gwsdsc/resources/__init__.py`.

---

## License

MIT — see [LICENSE](LICENSE).
