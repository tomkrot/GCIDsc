# Deployment Guide — Azure DevOps Pipeline

> Quick-reference guide for deploying the `azure-pipelines.yml` in this
> directory.  For the full end-to-end walkthrough including Google Workspace
> preparation, see [`docs/implementation-azure-devops.md`](../../docs/implementation-azure-devops.md).

---

## Contents of This Directory

```
pipelines/azure-devops/
├── README.md                  ← you are here
└── azure-pipelines.yml        ← the pipeline definition (4 stages)
```

---

## Pipeline Stages

| Stage | Trigger | What It Does |
|---|---|---|
| **1 — Export** | Cron (02:00 UTC nightly) or CI on `main` | Installs gwsdsc, reads SA key from Azure Key Vault, exports all 32 resource modules, publishes JSON as a pipeline artifact |
| **2 — Diff** | Automatic (after Export) | Compares the new snapshot against the previous Git-tagged snapshot, generates an HTML drift report, publishes it as a pipeline artifact |
| **3 — Commit** | Automatic (after Diff) | Commits the snapshot to the Git repository under `artifacts/<timestamp>/`, writes a `latest.json` pointer, pushes with a tag `export/<timestamp>` |
| **4 — Apply** | Manual trigger only + environment approval gate | Runs `gwsdsc apply --plan` (dry-run), then `gwsdsc apply --confirm` after human approval.  Only executes when the pipeline is started manually. |

---

## Prerequisites

Before creating the pipeline, you must have completed:

1. **Google Workspace service account** with domain-wide delegation and all required OAuth scopes (see [`docs/authentication.md`](../../docs/authentication.md))
2. **Azure Key Vault** with the SA key uploaded as a base64-encoded secret named `gwsdsc-sa-key`
3. **Azure DevOps project** with the GoogleWorkspaceDsc code pushed to a repository

### Agent Requirements

The pipeline runs on **both Linux and Windows** agents.  All script steps use `pwsh:` (PowerShell Core).

| Hosted Agent | Self-Hosted Agent (Windows) | Self-Hosted Agent (Linux) |
|---|---|---|
| `ubuntu-latest` or `windows-latest` — ready out of the box | Python 3.10+, Git, PowerShell Core 7+ | Python 3.10+, Git |

---

## Step-by-Step Deployment

### 1. Create the Variable Group

Go to **Pipelines → Library → + Variable group** and name it `gwsdsc`.

**Link to Azure Key Vault:**

1. Toggle **Link secrets from an Azure key vault as variables**.
2. Select your subscription and Key Vault.
3. Add the secret `gwsdsc-sa-key`.

**Add plain-text variables:**

| Variable | Example Value |
|---|---|
| `GWS_TENANT_NAME` | `My Organisation` |
| `GWS_CUSTOMER_ID` | `C01abc2de` or `my_customer` |
| `GWS_PRIMARY_DOMAIN` | `yourdomain.com` |
| `GWS_DELEGATED_ADMIN` | `admin@yourdomain.com` |
| `AZURE_VAULT_URL` | `https://kv-gwsdsc.vault.azure.net` |

Click **Save**.

### 2. Create the Pipeline

1. Go to **Pipelines → New pipeline**.
2. Select your repository (Azure Repos or GitHub).
3. Choose **Existing Azure Pipelines YAML file**.
4. Set path to `/pipelines/azure-devops/azure-pipelines.yml`.
5. Click **Save** (or **Run** to test immediately).

### 3. Grant Variable Group Access

1. Go to **Pipelines → Library → gwsdsc**.
2. Click **Pipeline permissions → + → select your pipeline**.

### 4. Create the Approval Environment

The Apply stage targets the `gws-production` environment with an approval gate.

1. Go to **Pipelines → Environments → New environment**.
2. Name it `gws-production`, resource type **None**.
3. Click the environment → **⋮** → **Approvals and checks**.
4. Add **Approvals** → select your approvers.

### 5. Configure Git Push Permissions

The Commit stage pushes to the repository.  The pipeline's build service identity needs write access.

1. Go to **Project Settings → Repositories → your repo → Security**.
2. Find the `<ProjectName> Build Service` identity.
3. Grant **Contribute** and **Create Tag** = Allow.

### 6. Select the Agent Pool

The pipeline has a parameter `agentPool` with three options:

| Value | When to Use |
|---|---|
| `ubuntu-latest` | Default — Microsoft-hosted Linux agent |
| `windows-latest` | Microsoft-hosted Windows agent |
| `Default` | Self-hosted pool (change this to your pool name) |

To change the default, either edit the YAML or select the value when running the pipeline manually.

For a self-hosted Windows agent, edit line 24 and add your pool name:

```yaml
values:
  - ubuntu-latest
  - windows-latest
  - Default
  - MyWindowsPool     # ← add your self-hosted pool name
```

---

## Customisation

### Change the Schedule

Edit the `schedules:` block (line 38):

```yaml
schedules:
  - cron: "0 6 * * 1-5"          # Weekdays at 06:00 UTC
    displayName: "Weekday morning export"
    branches:
      include:
        - main
    always: true
```

### Export Specific Resources Only

Override the `resources` list in the generated `tenant.yaml` (line 93):

```yaml
resources:
  - users
  - groups
  - ci_policies
  - context_aware_access
```

### Exclude Slow Resources

Add entries to `exclude_resources` in the generated config:

```yaml
exclude_resources:
  - app_access
  - ci_devices
  - chromeos_telemetry
```

### Increase Timeout for Large Tenants

The default Azure DevOps job timeout is 60 minutes.  For tenants with 10,000+ users, add a `timeoutInMinutes` to the Export job:

```yaml
- job: ExportJob
  displayName: "Run gwsdsc export"
  timeoutInMinutes: 120
  steps:
    ...
```

---

## Outputs

After a successful run, the pipeline produces:

| Artifact | Location | Description |
|---|---|---|
| `gws-snapshot` | Pipeline artifacts → `gws-snapshot` | JSON files for every exported resource module |
| `drift-report` | Pipeline artifacts → `drift-report` | HTML drift report (from 2nd run onwards) |
| Git commit | Repository `artifacts/<timestamp>/` | Versioned snapshot committed with tag `export/<timestamp>` |
| `latest.json` | Repository `artifacts/latest.json` | Pointer to the most recent snapshot directory |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: gwsdsc` | pip install failed | Check the install step log for network errors or Python version issues |
| `SecretNotFound` / Key Vault 403 | Variable group not linked to vault, or SP lacks `Key Vault Secrets User` role | Re-link the variable group; verify SP RBAC on the vault |
| `403 Not Authorized` from Google | DWD misconfigured | Verify Client ID in Admin Console matches SA's numeric Unique ID; check scopes |
| Git push fails | Build service lacks repo permissions | Grant Contribute + Create Tag to the build service identity |
| Diff stage shows "No previous export" | First run has nothing to compare against | Expected on first run — second run will diff successfully |
| Apply stage doesn't run | Pipeline was triggered by schedule, not manually | Apply only runs on `Manual` trigger reason |
| Pipeline times out | Tenant is very large | Add `timeoutInMinutes: 120` to the job; exclude slow resources |

---

## Related Documentation

- **Full implementation guide**: [`docs/implementation-azure-devops.md`](../../docs/implementation-azure-devops.md)
- **Authentication & scopes**: [`docs/authentication.md`](../../docs/authentication.md)
- **Adding resources**: [`docs/extending-resources.md`](../../docs/extending-resources.md)
- **API coverage**: [`docs/api-gap-analysis.md`](../../docs/api-gap-analysis.md)
