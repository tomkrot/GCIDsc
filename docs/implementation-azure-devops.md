# Implementation Guide — Azure DevOps

> Step-by-step instructions for deploying GoogleWorkspaceDsc with
> **Azure DevOps Pipelines**, **Azure Repos** (or GitHub), and
> **Azure Key Vault** for secret management.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Phase 1 — Google Workspace Preparation](#3-phase-1--google-workspace-preparation)
4. [Phase 2 — Azure Infrastructure Setup](#4-phase-2--azure-infrastructure-setup)
5. [Phase 3 — Repository & Code Setup](#5-phase-3--repository--code-setup)
6. [Phase 4 — Azure DevOps Pipeline Configuration](#6-phase-4--azure-devops-pipeline-configuration)
7. [Phase 5 — First Export & Validation](#7-phase-5--first-export--validation)
8. [Phase 6 — Enable Scheduling & Drift Reporting](#8-phase-6--enable-scheduling--drift-reporting)
9. [Phase 7 — Tenant Cloning (Apply)](#9-phase-7--tenant-cloning-apply)
10. [Operational Procedures](#10-operational-procedures)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     Azure DevOps Organisation                     │
│                                                                    │
│  ┌─────────────┐    ┌────────────────┐    ┌──────────────────┐   │
│  │ Azure Repos  │    │  Azure Pipeline │    │  Pipeline        │   │
│  │ (Git repo    │◄───│  (YAML, cron   │───►│  Artifacts       │   │
│  │  w/ config   │    │   scheduled)   │    │  (drift reports) │   │
│  │  + artifacts)│    └───────┬────────┘    └──────────────────┘   │
│  └─────────────┘            │                                      │
│                              │ reads secret at runtime              │
│                    ┌─────────▼─────────┐                           │
│                    │  Azure Key Vault   │                           │
│                    │  (SA key JSON)     │                           │
│                    └─────────┬─────────┘                           │
└──────────────────────────────┼──────────────────────────────────────┘
                               │ service account
                               │ w/ domain-wide delegation
                    ┌──────────▼──────────┐
                    │ Google Workspace     │
                    │ Tenant               │
                    │ (Admin SDK, CI API,  │
                    │  Chrome Policy, …)   │
                    └─────────────────────┘
```

The nightly cycle runs as follows: Cloud Scheduler (cron in the YAML pipeline) triggers a build. The pipeline reads the Google service account key from Azure Key Vault, exports all 21 resource modules via the Google APIs, commits the JSON artifacts to Git, diffs against the previous snapshot, and publishes an HTML drift report. Applying changes to a target tenant is a separate, manually-triggered stage with an approval gate.

---

## 2. Prerequisites

Before you begin, confirm you have the following accounts and permissions.

### 2.1 Google Workspace / Cloud Identity

| Requirement | Detail |
|---|---|
| Google Workspace edition | Business Starter or above (any paid edition), **or** Cloud Identity Free / Premium |
| Super Admin account | An account with the Super Admin role — needed to configure domain-wide delegation and to act as the delegated admin for API calls |
| Google Cloud project | A GCP project linked to the same organisation (for enabling APIs and creating the service account) |
| Cloud Identity API enabled | Required for `ci_policies`, `ci_saml_sso_profiles`, `ci_sso_assignments`, `ci_devices`, `ci_groups` |
| Chrome Policy API enabled | Required for `chrome_policies` |

### 2.2 Azure

| Requirement | Detail |
|---|---|
| Azure subscription | Any subscription where you can create Key Vault resources |
| Azure DevOps organisation | With permissions to create Projects, Pipelines, and Service Connections |
| Azure Key Vault | You will create one (or use an existing one) to store the Google SA key |
| Azure CLI installed locally | `az` version 2.50 or later |

### 2.3 Local Machine

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Running gwsdsc locally for testing |
| Git | 2.30+ | Repository management |
| gcloud CLI | latest | Google Cloud project setup |
| az CLI | 2.50+ | Azure resource setup |
| Terraform (optional) | 1.5+ | If you want to IaC the Azure resources too |

---

## 3. Phase 1 — Google Workspace Preparation

These steps are identical regardless of whether you use Azure DevOps or Google Cloud for your pipeline. They configure the Google side of the integration.

### 3.1 Create a Google Cloud Project

```bash
# Authenticate
gcloud auth login

# Create project (or use an existing one)
gcloud projects create gwsdsc-automation \
  --name="GoogleWorkspaceDsc Automation" \
  --organization=YOUR_ORG_ID

gcloud config set project gwsdsc-automation
```

### 3.2 Enable Required APIs

```bash
gcloud services enable \
  admin.googleapis.com \
  groupssettings.googleapis.com \
  chromepolicy.googleapis.com \
  gmail.googleapis.com \
  calendar-json.googleapis.com \
  cloudidentity.googleapis.com \
  accesscontextmanager.googleapis.com \
  vault.googleapis.com \
  alertcenter.googleapis.com \
  licensing.googleapis.com \
  chromemanagement.googleapis.com
```

### 3.3 Create a Service Account

```bash
# Create the SA
gcloud iam service-accounts create gwsdsc-exporter \
  --display-name="GoogleWorkspaceDsc Exporter" \
  --description="Exports and applies GWS tenant configuration"

# Note the full email — you will need it below
SA_EMAIL="gwsdsc-exporter@gwsdsc-automation.iam.gserviceaccount.com"

# Create and download a JSON key
gcloud iam service-accounts keys create sa-key.json \
  --iam-account=$SA_EMAIL
```

The file `sa-key.json` now exists on your local disk. You will upload it to Azure Key Vault in Phase 2. **Do not commit it to Git.**

### 3.4 Configure Domain-Wide Delegation

1. Open the [Google Cloud Console → IAM → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts).
2. Click the service account `gwsdsc-exporter`.
3. Copy the **Unique ID** (numeric Client ID, e.g. `1123456789012345`).
4. Open the [Google Admin Console](https://admin.google.com).
5. Navigate to **Security → Access and data control → API controls**.
6. Click **Manage Domain-Wide Delegation** → **Add new**.
7. Paste the Client ID.
8. In the **OAuth scopes** field, paste the following (all on one line, comma-separated):

```
https://www.googleapis.com/auth/admin.directory.customer,https://www.googleapis.com/auth/admin.directory.customer.readonly,https://www.googleapis.com/auth/admin.directory.domain.readonly,https://www.googleapis.com/auth/admin.directory.group,https://www.googleapis.com/auth/admin.directory.group.readonly,https://www.googleapis.com/auth/admin.directory.group.member,https://www.googleapis.com/auth/admin.directory.group.member.readonly,https://www.googleapis.com/auth/admin.directory.orgunit,https://www.googleapis.com/auth/admin.directory.orgunit.readonly,https://www.googleapis.com/auth/admin.directory.rolemanagement,https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly,https://www.googleapis.com/auth/admin.directory.user,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/admin.directory.user.security,https://www.googleapis.com/auth/admin.directory.userschema,https://www.googleapis.com/auth/admin.directory.userschema.readonly,https://www.googleapis.com/auth/admin.directory.resource.calendar,https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly,https://www.googleapis.com/auth/admin.directory.device.mobile.readonly,https://www.googleapis.com/auth/admin.directory.device.chromebrowsers,https://www.googleapis.com/auth/admin.directory.device.chromebrowsers.readonly,https://www.googleapis.com/auth/admin.chrome.printers,https://www.googleapis.com/auth/admin.chrome.printers.readonly,https://www.googleapis.com/auth/admin.contact.delegation,https://www.googleapis.com/auth/admin.contact.delegation.readonly,https://www.googleapis.com/auth/admin.datatransfer,https://www.googleapis.com/auth/admin.datatransfer.readonly,https://www.googleapis.com/auth/apps.groups.settings,https://www.googleapis.com/auth/chrome.management.policy,https://www.googleapis.com/auth/chrome.management.policy.readonly,https://www.googleapis.com/auth/chrome.management.telemetry.readonly,https://www.googleapis.com/auth/gmail.settings.basic,https://www.googleapis.com/auth/gmail.settings.sharing,https://www.googleapis.com/auth/cloud-identity,https://www.googleapis.com/auth/cloud-identity.policies,https://www.googleapis.com/auth/cloud-identity.policies.readonly,https://www.googleapis.com/auth/cloud-identity.inboundsso,https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly,https://www.googleapis.com/auth/cloud-identity.devices,https://www.googleapis.com/auth/cloud-identity.devices.readonly,https://www.googleapis.com/auth/cloud-identity.groups,https://www.googleapis.com/auth/cloud-identity.groups.readonly,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/ediscovery,https://www.googleapis.com/auth/ediscovery.readonly,https://www.googleapis.com/auth/apps.alerts,https://www.googleapis.com/auth/apps.licensing,https://apps-apis.google.com/a/feeds/domain/
```

9. Click **Authorize**.

### 3.5 Identify Your Customer ID

You need the Google Workspace Customer ID (not the GCP project ID).

```bash
# Option A: Admin Console → Account → Account settings → Customer ID
# Option B: Using gcloud (if Directory API is enabled)
# It looks like "C01abc2de" — or use "my_customer" as shorthand
```

### 3.6 Identify the Delegated Admin Email

Choose a Super Admin account that the service account will impersonate, for example `admin@yourdomain.com`. This account must remain active (not suspended) and must have the Super Admin role.

### 3.7 Local Smoke Test

Before wiring up Azure, verify the SA key works locally:

```bash
# Install gwsdsc locally
cd GoogleWorkspaceDsc
pip install -e .

# Create a minimal test config
cat > /tmp/test-tenant.yaml << EOF
tenant_name: "Smoke Test"
customer_id: "my_customer"
primary_domain: "yourdomain.com"
credentials:
  type: service_account
  secret_backend: file
  service_account_key_path: "$(pwd)/sa-key.json"
  delegated_admin_email: "admin@yourdomain.com"
store:
  type: local
  path: /tmp/gwsdsc-test
resources:
  - customer
  - org_units
EOF

# Run a minimal export
gwsdsc export --config /tmp/test-tenant.yaml
```

If this produces JSON files under `/tmp/gwsdsc-test/`, the Google side is working correctly.

---

## 4. Phase 2 — Azure Infrastructure Setup

### 4.1 Create a Resource Group

```bash
az login
az account set --subscription "Your Subscription Name"

az group create \
  --name rg-gwsdsc \
  --location westeurope
```

### 4.2 Create an Azure Key Vault

```bash
az keyvault create \
  --name kv-gwsdsc \
  --resource-group rg-gwsdsc \
  --location westeurope \
  --sku standard \
  --enable-rbac-authorization true
```

### 4.3 Upload the Google SA Key to Key Vault

The service account key JSON must be stored as a Key Vault secret. Since Key Vault secrets are plain strings, base64-encode the JSON first (gwsdsc auto-detects and decodes base64 at runtime).

```bash
# Encode the key
BASE64_KEY=$(base64 -w0 sa-key.json)

# Store in Key Vault
az keyvault secret set \
  --vault-name kv-gwsdsc \
  --name gwsdsc-sa-key \
  --value "$BASE64_KEY"

# Verify
az keyvault secret show \
  --vault-name kv-gwsdsc \
  --name gwsdsc-sa-key \
  --query "id" -o tsv
```

### 4.4 Create an Azure AD App Registration (Service Principal)

The Azure DevOps pipeline needs a Service Principal to access Key Vault at runtime.

```bash
# Create the SP
az ad sp create-for-rbac \
  --name "sp-gwsdsc-pipeline" \
  --role "Key Vault Secrets User" \
  --scopes "/subscriptions/YOUR_SUB_ID/resourceGroups/rg-gwsdsc/providers/Microsoft.KeyVault/vaults/kv-gwsdsc"
```

Save the output — you will need `appId`, `password`, and `tenant` for the Azure DevOps service connection.

```json
{
  "appId": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "displayName": "sp-gwsdsc-pipeline",
  "password": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

### 4.5 Delete the Local Key File

Now that the key is safely in Key Vault, remove it from your local machine:

```bash
shred -u sa-key.json   # Linux
# or: rm -P sa-key.json  # macOS
```

---

## 5. Phase 3 — Repository & Code Setup

### 5.1 Create the Azure DevOps Project

1. Go to [dev.azure.com](https://dev.azure.com) → your organisation.
2. **New project** → name it `GoogleWorkspaceDsc`.
3. Under **Repos**, initialise with a README or import from GitHub.

### 5.2 Push the Framework Code

```bash
cd GoogleWorkspaceDsc

# Add Azure Repos as remote (or GitHub)
git init
git remote add origin https://dev.azure.com/YOUR_ORG/GoogleWorkspaceDsc/_git/GoogleWorkspaceDsc

git add .
git commit -m "Initial commit — GoogleWorkspaceDsc framework"
git push -u origin main
```

### 5.3 Verify Repository Structure

After pushing, your repo should contain at minimum:

```
├── src/gwsdsc/          # Python framework
├── pipelines/azure-devops/azure-pipelines.yml
├── config/tenant.yaml.example
├── pyproject.toml
├── Makefile
└── README.md
```

---

## 6. Phase 4 — Azure DevOps Pipeline Configuration

### 6.1 Create a Variable Group Linked to Key Vault

1. In Azure DevOps, go to **Pipelines → Library**.
2. Click **+ Variable group** → name it `gwsdsc`.
3. Toggle **Link secrets from an Azure key vault as variables**.
4. Select the Azure subscription and the Key Vault `kv-gwsdsc`.
5. Click **+ Add** and select the secret `gwsdsc-sa-key`.
6. Also add the following **plain-text** variables:

| Variable | Value | Secret? |
|---|---|---|
| `GWS_TENANT_NAME` | `My Organisation` | No |
| `GWS_CUSTOMER_ID` | `C01abc2de` (or `my_customer`) | No |
| `GWS_PRIMARY_DOMAIN` | `yourdomain.com` | No |
| `GWS_DELEGATED_ADMIN` | `admin@yourdomain.com` | No |
| `AZURE_VAULT_URL` | `https://kv-gwsdsc.vault.azure.net` | No |

7. Click **Save**.

### 6.2 Create a Service Connection

1. Go to **Project Settings → Service connections**.
2. Click **New service connection → Azure Resource Manager**.
3. Choose **Service principal (manual)**.
4. Enter the `appId`, `password`, `tenant`, and subscription details from Phase 2.4.
5. Name it `azure-gwsdsc` and click **Verify and save**.

### 6.3 Create the Pipeline

1. Go to **Pipelines → New pipeline**.
2. Select your repository (Azure Repos Git or GitHub).
3. Choose **Existing Azure Pipelines YAML file**.
4. Set the path to `/pipelines/azure-devops/azure-pipelines.yml`.
5. Click **Run** (or **Save** first to review).

### 6.4 Configure the Approval Gate (Environment)

The Apply stage uses a **deployment environment** with approval gates so that configuration changes are never applied without human review.

1. Go to **Pipelines → Environments**.
2. Click **New environment** → name it `gws-production`.
3. Click the environment → **⋮** (more) → **Approvals and checks**.
4. Add an **Approvals** check.
5. Add one or more approvers (yourself, your team lead, etc.).
6. Optionally add a **Business hours** check if you only want applies during working hours.

### 6.5 Grant Pipeline Permissions

The pipeline needs permission to access the variable group:

1. Go to **Pipelines → Library → gwsdsc** (your variable group).
2. Click **Pipeline permissions**.
3. Click **+** and add your pipeline.

---

## 7. Phase 5 — First Export & Validation

### 7.1 Trigger a Manual Run

1. Go to **Pipelines** → click your pipeline → **Run pipeline**.
2. Select branch `main`.
3. Click **Run**.
4. Watch the **Export** stage. It should complete in 2–10 minutes depending on tenant size.

### 7.2 Verify the Artifacts

After the Export stage completes:

1. Click the completed run → **Published artifacts** → `gws-snapshot`.
2. You should see files like `users.json`, `groups.json`, `org_units.json`, `ci_policies.json`, etc.
3. Download and inspect a few to confirm they contain real data.

### 7.3 Verify the Git Commit

After the Commit stage completes:

1. Go to **Repos → Commits**.
2. You should see a commit like `gwsdsc export 2025-03-09T020000Z`.
3. A tag `export/2025-03-09T020000Z` should exist under **Tags**.

### 7.4 Check the Drift Report

For the first run there will be no previous snapshot, so the Diff stage will skip. After the second run, the drift report will appear under the `drift-report` pipeline artifact.

---

## 8. Phase 6 — Enable Scheduling & Drift Reporting

### 8.1 Cron Schedule

The pipeline YAML already includes a cron schedule (`0 2 * * *` — 02:00 UTC nightly). Azure DevOps will automatically trigger scheduled runs once the pipeline has been run at least once.

To change the schedule, edit the `schedules` section in `azure-pipelines.yml`:

```yaml
schedules:
  - cron: "0 2 * * *"           # Every night at 02:00 UTC
    displayName: "Nightly export"
    branches:
      include:
        - main
    always: true                 # Run even if no code changes
```

### 8.2 Drift Report Distribution

After the second scheduled run, an HTML drift report is published as a pipeline artifact. To distribute it automatically you can add a step that sends it via email, uploads it to SharePoint, or posts a summary to a Teams channel using the Azure DevOps REST API or a webhook.

### 8.3 Monitoring Pipeline Health

Set up pipeline notifications in **Project Settings → Notifications**. Create a rule that alerts your team when a scheduled run fails.

---

## 9. Phase 7 — Tenant Cloning (Apply)

To replicate the exported configuration into a **different** Google Workspace tenant (e.g. a staging environment or a disaster recovery tenant):

### 9.1 Prepare the Target Tenant

1. Repeat [Phase 1](#3-phase-1--google-workspace-preparation) for the target tenant (new GCP project, new SA, new DWD).
2. Upload the target tenant's SA key to a separate Key Vault secret, e.g. `gwsdsc-sa-key-target`.

### 9.2 Create a Target Tenant Config

Create a second tenant config file (`config/tenant-target.yaml`) pointing to the target tenant's credentials and customer ID.

### 9.3 Run the Apply Stage

1. Trigger a **manual** pipeline run.
2. The Apply stage runs with `--plan` first (dry-run) showing what would change.
3. An approver reviews the plan in the pipeline log.
4. After approval, the `--confirm` step executes the actual changes.

Important: the Apply stage only runs on `Manual` triggers (not scheduled runs). This is enforced by the pipeline condition `eq(variables['Build.Reason'], 'Manual')`.

---

## 10. Operational Procedures

### 10.1 Key Rotation

Rotate the Google SA key periodically:

```bash
# Create new key
gcloud iam service-accounts keys create new-sa-key.json \
  --iam-account=$SA_EMAIL

# Upload to Key Vault (creates a new version)
az keyvault secret set \
  --vault-name kv-gwsdsc \
  --name gwsdsc-sa-key \
  --value "$(base64 -w0 new-sa-key.json)"

# Delete old key from GCP (after confirming the new one works)
gcloud iam service-accounts keys list --iam-account=$SA_EMAIL
gcloud iam service-accounts keys delete OLD_KEY_ID --iam-account=$SA_EMAIL

# Clean up
shred -u new-sa-key.json
```

### 10.2 Comparing Specific Snapshots

```bash
# Locally
gwsdsc diff \
  --baseline artifacts/2025-03-01T020000Z \
  --target   artifacts/2025-03-09T020000Z \
  --report html \
  --output my-comparison.html
```

### 10.3 Exporting Specific Resources Only

```bash
gwsdsc export --config config/tenant.yaml --resources ci_policies,ci_saml_sso_profiles,users
```

### 10.4 Adding New Resources

1. Follow the guide in `docs/extending-resources.md`.
2. Register your module in `src/gwsdsc/resources/__init__.py`.
3. Push to `main` — the next scheduled run will include it automatically.

---

## 11. Troubleshooting

### "403 Not Authorized" from Google APIs

This almost always means domain-wide delegation is misconfigured. Verify the Client ID in the Admin Console matches the service account's numeric Unique ID (not the email). Also ensure the delegated admin email is a Super Admin and not suspended.

### "SecretNotFound" from Azure Key Vault

Check that the variable group is linked to the correct Key Vault and that the secret name matches exactly (`gwsdsc-sa-key`). Also confirm the Service Principal has the `Key Vault Secrets User` role on the vault.

### Pipeline Cannot Push to Git

The Commit stage uses `persistCredentials: true` on the checkout step. If pushes fail, ensure the pipeline's build service identity has `Contribute` and `Create Tag` permissions on the repository (Repos → Security).

### "No module named gwsdsc"

Ensure `pip install -e ".[azure]"` ran successfully in the Install step. Check the pipeline log for pip errors (network issues, Python version mismatch).

### Export Takes Too Long

Large tenants (10 000+ users) may exceed the default 60-minute pipeline timeout. Either increase the timeout in the YAML (`timeoutInMinutes: 120`) or exclude slow resources like `app_access` and `ci_devices` via `exclude_resources` in the config.

---

*Last updated: March 2026 — GoogleWorkspaceDsc v0.1.0*
