# Implementation Guide — Google Cloud Platform

> Step-by-step instructions for deploying GoogleWorkspaceDsc entirely
> within the **Google Cloud** ecosystem using **Cloud Build**,
> **Cloud Scheduler**, **Secret Manager**, and **Terraform**.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Prerequisites](#2-prerequisites)
3. [Phase 1 — Google Workspace Preparation](#3-phase-1--google-workspace-preparation)
4. [Phase 2 — Google Cloud Infrastructure (Terraform)](#4-phase-2--google-cloud-infrastructure-terraform)
5. [Phase 3 — Secret Manager & Credential Setup](#5-phase-3--secret-manager--credential-setup)
6. [Phase 4 — Repository Setup](#6-phase-4--repository-setup)
7. [Phase 5 — First Export & Validation](#7-phase-5--first-export--validation)
8. [Phase 6 — Enable Scheduling & Drift Reporting](#8-phase-6--enable-scheduling--drift-reporting)
9. [Phase 7 — Tenant Cloning (Apply)](#9-phase-7--tenant-cloning-apply)
10. [Operational Procedures](#10-operational-procedures)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Architecture Overview

```
┌───────────────────────────────────────────────────────────────────┐
│                      Google Cloud Project                          │
│                                                                     │
│   ┌──────────────┐     ┌────────────────┐    ┌────────────────┐   │
│   │ Cloud         │────►│  Cloud Build    │───►│ GCS Bucket     │   │
│   │ Scheduler     │     │  (export /      │    │ (versioned     │   │
│   │ (cron 02:00)  │     │   apply)        │    │  artifacts)    │   │
│   └──────────────┘     └───────┬─────────┘    └────────────────┘   │
│                                 │                                    │
│                       ┌─────────▼──────────┐  ┌────────────────┐   │
│                       │  Secret Manager     │  │ Cloud Source    │   │
│                       │  (SA key JSON)      │  │ Repos / GitHub  │   │
│                       └─────────┬──────────┘  │ (code + config) │   │
│                                 │              └────────────────┘   │
│                                 │                                    │
│   ┌─────────────────────────────┼──────────────────────────────┐   │
│   │   Cloud Build Service Account                               │   │
│   │   (IAM bindings: storage, secrets, scheduler)               │   │
│   └─────────────────────────────┼──────────────────────────────┘   │
└─────────────────────────────────┼──────────────────────────────────┘
                                  │ service account
                                  │ w/ domain-wide delegation
                       ┌──────────▼──────────┐
                       │ Google Workspace     │
                       │ Tenant               │
                       │ (Admin SDK, CI API,  │
                       │  Chrome Policy, …)   │
                       └─────────────────────┘
```

Everything runs within Google Cloud. Cloud Scheduler fires a nightly Cloud Build job that reads the SA key from Secret Manager, exports all 21 resource modules, uploads the artifacts to a versioned GCS bucket, diffs against the previous snapshot, and writes an HTML drift report to a separate reports bucket. A second Cloud Build trigger (with manual approval required) handles applying a snapshot to a target tenant.

The full infrastructure is defined in Terraform for reproducibility.

---

## 2. Prerequisites

### 2.1 Google Workspace / Cloud Identity

| Requirement | Detail |
|---|---|
| Google Workspace edition | Business Starter or above, **or** Cloud Identity Free / Premium |
| Super Admin account | Needed for domain-wide delegation and as the delegated admin identity |
| Customer ID | Your Workspace Customer ID (e.g. `C01abc2de`), visible in **Admin Console → Account → Account settings** |
| Primary domain | The primary domain of your tenant (e.g. `yourdomain.com`) |

### 2.2 Google Cloud

| Requirement | Detail |
|---|---|
| Google Cloud account | With billing enabled |
| IAM permissions | `Owner` or `Editor` on the GCP project (for initial setup; can be scoped down afterwards) |
| gcloud CLI | Authenticated locally (`gcloud auth login`) |
| Terraform | v1.5 or later (for automated infrastructure provisioning) |
| GitHub (optional) | If using GitHub instead of Cloud Source Repositories as the code host |

### 2.3 Local Machine

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.10+ | Running gwsdsc locally for testing |
| Git | 2.30+ | Repository management |
| gcloud CLI | latest | GCP project and API management |
| Terraform | 1.5+ | Infrastructure provisioning |

---

## 3. Phase 1 — Google Workspace Preparation

### 3.1 Create (or Select) a GCP Project

```bash
gcloud auth login

# Create a dedicated project
gcloud projects create gwsdsc-automation \
  --name="GoogleWorkspaceDsc Automation" \
  --organization=YOUR_ORG_ID

gcloud config set project gwsdsc-automation

# Enable billing (required for Cloud Build, Scheduler, etc.)
gcloud billing projects link gwsdsc-automation \
  --billing-account=YOUR_BILLING_ACCOUNT_ID
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
  chromemanagement.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  sourcerepo.googleapis.com
```

### 3.3 Create the Workspace Service Account

This is the service account that will access Google Workspace APIs via domain-wide delegation. It is separate from the Cloud Build service account.

```bash
gcloud iam service-accounts create gwsdsc-exporter \
  --display-name="GoogleWorkspaceDsc Exporter" \
  --description="Reads/writes GWS tenant configuration via Admin SDK and CI API"

SA_EMAIL="gwsdsc-exporter@gwsdsc-automation.iam.gserviceaccount.com"

# Create a JSON key (will be uploaded to Secret Manager)
gcloud iam service-accounts keys create sa-key.json \
  --iam-account=$SA_EMAIL
```

### 3.4 Configure Domain-Wide Delegation

1. Open the [GCP Console → IAM → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts).
2. Click `gwsdsc-exporter` → copy the **Unique ID** (numeric Client ID).
3. Open the [Google Admin Console](https://admin.google.com) as a Super Admin.
4. Navigate to **Security → Access and data control → API controls**.
5. Click **Manage Domain-Wide Delegation** → **Add new**.
6. Paste the Client ID.
7. Add the following OAuth scopes (comma-separated, all on one line):

```
https://www.googleapis.com/auth/admin.directory.customer,https://www.googleapis.com/auth/admin.directory.customer.readonly,https://www.googleapis.com/auth/admin.directory.domain.readonly,https://www.googleapis.com/auth/admin.directory.group,https://www.googleapis.com/auth/admin.directory.group.readonly,https://www.googleapis.com/auth/admin.directory.group.member,https://www.googleapis.com/auth/admin.directory.group.member.readonly,https://www.googleapis.com/auth/admin.directory.orgunit,https://www.googleapis.com/auth/admin.directory.orgunit.readonly,https://www.googleapis.com/auth/admin.directory.rolemanagement,https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly,https://www.googleapis.com/auth/admin.directory.user,https://www.googleapis.com/auth/admin.directory.user.readonly,https://www.googleapis.com/auth/admin.directory.user.security,https://www.googleapis.com/auth/admin.directory.userschema,https://www.googleapis.com/auth/admin.directory.userschema.readonly,https://www.googleapis.com/auth/admin.directory.resource.calendar,https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly,https://www.googleapis.com/auth/admin.directory.device.mobile.readonly,https://www.googleapis.com/auth/admin.directory.device.chromebrowsers,https://www.googleapis.com/auth/admin.directory.device.chromebrowsers.readonly,https://www.googleapis.com/auth/admin.chrome.printers,https://www.googleapis.com/auth/admin.chrome.printers.readonly,https://www.googleapis.com/auth/admin.contact.delegation,https://www.googleapis.com/auth/admin.contact.delegation.readonly,https://www.googleapis.com/auth/admin.datatransfer,https://www.googleapis.com/auth/admin.datatransfer.readonly,https://www.googleapis.com/auth/apps.groups.settings,https://www.googleapis.com/auth/chrome.management.policy,https://www.googleapis.com/auth/chrome.management.policy.readonly,https://www.googleapis.com/auth/chrome.management.telemetry.readonly,https://www.googleapis.com/auth/gmail.settings.basic,https://www.googleapis.com/auth/gmail.settings.sharing,https://www.googleapis.com/auth/cloud-identity,https://www.googleapis.com/auth/cloud-identity.policies,https://www.googleapis.com/auth/cloud-identity.policies.readonly,https://www.googleapis.com/auth/cloud-identity.inboundsso,https://www.googleapis.com/auth/cloud-identity.inboundsso.readonly,https://www.googleapis.com/auth/cloud-identity.devices,https://www.googleapis.com/auth/cloud-identity.devices.readonly,https://www.googleapis.com/auth/cloud-identity.groups,https://www.googleapis.com/auth/cloud-identity.groups.readonly,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/ediscovery,https://www.googleapis.com/auth/ediscovery.readonly,https://www.googleapis.com/auth/apps.alerts,https://www.googleapis.com/auth/apps.licensing,https://apps-apis.google.com/a/feeds/domain/
```

8. Click **Authorize**.

### 3.5 Local Smoke Test

Verify the SA works before moving on:

```bash
cd GoogleWorkspaceDsc
pip install -e .

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

gwsdsc export --config /tmp/test-tenant.yaml

# Verify output
ls /tmp/gwsdsc-test/*/
cat /tmp/gwsdsc-test/*/customer.json
```

If this succeeds, the Google Workspace side is ready.

---

## 4. Phase 2 — Google Cloud Infrastructure (Terraform)

The included Terraform configuration provisions all required GCP resources in one step.

### 4.1 Create a Terraform Variables File

```bash
cd GoogleWorkspaceDsc/pipelines/google-cloud/terraform

cat > terraform.tfvars << EOF
project_id          = "gwsdsc-automation"
region              = "europe-west1"

gws_customer_id     = "my_customer"
gws_primary_domain  = "yourdomain.com"
gws_tenant_name     = "My Organisation"
gws_delegated_admin = "admin@yourdomain.com"

artifact_bucket_name = "gwsdsc-artifacts-yourdomain"
secret_name          = "gwsdsc-sa-key"

source_repo_url      = "https://github.com/your-org/GoogleWorkspaceDsc"
source_repo_type     = "GITHUB"

export_schedule      = "0 2 * * *"
EOF
```

If using Cloud Source Repositories instead of GitHub, set:

```hcl
source_repo_url  = "https://source.developers.google.com/p/gwsdsc-automation/r/gwsdsc-config"
source_repo_type = "CLOUD_SOURCE_REPOSITORIES"
```

### 4.2 Run Terraform

```bash
terraform init
terraform plan -out=tfplan
```

Review the plan carefully. It will create the following resources:

| Resource | Purpose |
|---|---|
| `google_storage_bucket.artifacts` | Versioned GCS bucket for configuration snapshots |
| `google_storage_bucket.reports` | GCS bucket for HTML drift reports (90-day retention) |
| `google_secret_manager_secret.sa_key` | Secret Manager secret (empty — you upload the value next) |
| `google_service_account.cloudbuild_sa` | Service account for Cloud Build pipelines |
| `google_cloudbuild_trigger.export` | Cloud Build trigger: export pipeline |
| `google_cloudbuild_trigger.apply` | Cloud Build trigger: apply pipeline (approval required) |
| `google_cloud_scheduler_job.nightly_export` | Cloud Scheduler cron job: triggers export at 02:00 UTC |
| IAM bindings | Storage access, Secret Manager access, logging, and Scheduler-to-Build permissions |

```bash
terraform apply tfplan
```

Note the outputs — you will need the bucket names and trigger IDs.

### 4.3 What Terraform Creates (Summary)

```
┌────────────────────────────────┐
│  google_storage_bucket         │
│  "gwsdsc-artifacts-yourdomain" │
│  (versioning=true,             │
│   90 versions retained,        │
│   365-day max age)             │
└────────────────────────────────┘

┌────────────────────────────────┐
│  google_secret_manager_secret  │
│  "gwsdsc-sa-key"               │
│  (value uploaded manually)     │
└────────────────────────────────┘

┌────────────────────────────────┐
│  google_cloudbuild_trigger     │
│  "gwsdsc-export"               │
│  (triggered by Scheduler)      │
├────────────────────────────────┤
│  "gwsdsc-apply"                │
│  (manual, approval_required)   │
└────────────────────────────────┘

┌────────────────────────────────┐
│  google_cloud_scheduler_job    │
│  "gwsdsc-nightly-export"       │
│  (cron: 0 2 * * *)            │
└────────────────────────────────┘
```

---

## 5. Phase 3 — Secret Manager & Credential Setup

### 5.1 Upload the SA Key to Secret Manager

Terraform created the secret resource but not its value. Upload the key now:

```bash
gcloud secrets versions add gwsdsc-sa-key \
  --data-file=sa-key.json \
  --project=gwsdsc-automation
```

Verify it was stored:

```bash
gcloud secrets versions list gwsdsc-sa-key --project=gwsdsc-automation
```

### 5.2 Grant the Cloud Build SA Access to Secret Manager

Terraform already created the IAM binding, but verify it:

```bash
gcloud secrets get-iam-policy gwsdsc-sa-key --project=gwsdsc-automation
```

The Cloud Build service account (`gwsdsc-cloudbuild@gwsdsc-automation.iam.gserviceaccount.com`) should have `roles/secretmanager.secretAccessor`.

### 5.3 Delete the Local Key File

```bash
shred -u sa-key.json
```

### 5.4 Verify Runtime Secret Access

Test that Cloud Build can read the secret:

```bash
gcloud builds submit --no-source \
  --project=gwsdsc-automation \
  --config=- << 'EOF'
steps:
  - name: "gcr.io/cloud-builders/gcloud"
    args:
      - "secrets"
      - "versions"
      - "access"
      - "latest"
      - "--secret=gwsdsc-sa-key"
EOF
```

If the build succeeds without errors, secret access is working.

---

## 6. Phase 4 — Repository Setup

### 6.1 Option A — GitHub

If you are using GitHub:

1. Push the GoogleWorkspaceDsc code to a GitHub repository.
2. In the GCP Console, go to **Cloud Build → Triggers** and connect your GitHub repository (this creates a Cloud Build GitHub App connection).
3. The Terraform triggers reference `source_repo_url` pointing to your GitHub repo.

### 6.2 Option B — Cloud Source Repositories

If you prefer keeping everything inside Google Cloud:

```bash
# Create the repository
gcloud source repos create gwsdsc-config --project=gwsdsc-automation

# Add as remote and push
cd GoogleWorkspaceDsc
git remote add google \
  https://source.developers.google.com/p/gwsdsc-automation/r/gwsdsc-config
git push google main
```

### 6.3 Verify Repository Content

Whichever option you chose, confirm the following files are present:

```
pipelines/google-cloud/cloudbuild-export.yaml
pipelines/google-cloud/cloudbuild-apply.yaml
src/gwsdsc/
config/tenant.yaml.example
pyproject.toml
```

---

## 7. Phase 5 — First Export & Validation

### 7.1 Trigger the Export Manually

```bash
gcloud builds triggers run gwsdsc-export \
  --region=europe-west1 \
  --project=gwsdsc-automation \
  --branch=main
```

Or from the Console: **Cloud Build → Triggers → gwsdsc-export → Run**.

### 7.2 Monitor the Build

```bash
# Watch the build log
gcloud builds log --stream $(gcloud builds list --limit=1 --format="value(id)")
```

Or view the log in the Cloud Build Console. The build goes through the following steps:

1. **install** — installs the gwsdsc Python package
2. **get-secret** — retrieves the SA key from Secret Manager
3. **gen-config** — generates `tenant.yaml` with the correct substitution variables
4. **export** — runs `gwsdsc export` and writes JSON artifacts to the workspace
5. **upload** — syncs artifacts to the GCS bucket
6. **diff** — compares against the previous snapshot (skipped on first run)
7. **git-commit** — commits the snapshot to the source repo

### 7.3 Verify the GCS Artifacts

```bash
# List the exported snapshots
gsutil ls gs://gwsdsc-artifacts-yourdomain/exports/

# Inspect a specific resource
gsutil cat gs://gwsdsc-artifacts-yourdomain/exports/2025-03-09T020000Z/users.json | python3 -m json.tool | head -40
```

### 7.4 Verify the Latest Pointer

```bash
gsutil cat gs://gwsdsc-artifacts-yourdomain/exports/latest.json
# Should show: {"latest_version": "2025-03-09T020000Z"}
```

---

## 8. Phase 6 — Enable Scheduling & Drift Reporting

### 8.1 Verify Cloud Scheduler

Terraform already created the scheduler job. Confirm:

```bash
gcloud scheduler jobs describe gwsdsc-nightly-export \
  --location=europe-west1 \
  --project=gwsdsc-automation
```

The job runs at `0 2 * * *` (02:00 UTC daily). To change the schedule:

```bash
gcloud scheduler jobs update http gwsdsc-nightly-export \
  --schedule="0 3 * * *" \
  --location=europe-west1
```

### 8.2 Trigger a Manual Second Export

To generate the first drift report, run the export again (or wait for the next scheduled run):

```bash
gcloud builds triggers run gwsdsc-export \
  --region=europe-west1 \
  --branch=main
```

After this second run, the `diff` step will compare the two snapshots and produce a drift report.

### 8.3 View Drift Reports

```bash
# List reports
gsutil ls gs://gwsdsc-artifacts-yourdomain-reports/

# Download the latest HTML report
gsutil cp gs://gwsdsc-artifacts-yourdomain-reports/drift-report-*.html /tmp/
open /tmp/drift-report-*.html
```

### 8.4 Optional: Set Up Notifications

To receive notifications when drift is detected or when builds fail, use Cloud Build notifications:

```bash
# Example: send to a Pub/Sub topic
gcloud builds triggers update gwsdsc-export \
  --region=europe-west1 \
  --include-build-logs=INCLUDE_BUILD_LOGS_WITH_STATUS
```

Then subscribe to the `cloud-builds` Pub/Sub topic to route to email, Slack, or a Cloud Function.

---

## 9. Phase 7 — Tenant Cloning (Apply)

### 9.1 Prepare the Target Tenant

Repeat [Phase 1](#3-phase-1--google-workspace-preparation) for the target tenant:

1. Create a new GCP project for the target tenant.
2. Create a new service account with domain-wide delegation on the target domain.
3. Upload the target SA key to a new Secret Manager secret (e.g. `gwsdsc-sa-key-target`).

### 9.2 Dry-Run Plan

Trigger the apply trigger with `_CONFIRM=false` (the default):

```bash
gcloud builds triggers run gwsdsc-apply \
  --region=europe-west1 \
  --project=gwsdsc-automation \
  --branch=main \
  --substitutions=_APPLY_VERSION="2025-03-09T020000Z",_CONFIRM="false"
```

Review the build log. The `plan` step shows every resource that would be created, updated, or deleted in the target tenant.

### 9.3 Apply with Approval

The `gwsdsc-apply` trigger has `approval_required = true` in Terraform. When you trigger it with `_CONFIRM=true`:

1. The build enters a **pending approval** state.
2. Navigate to **Cloud Build → Builds** → click the pending build → **Approve**.
3. After approval, the build continues and applies the changes.

```bash
gcloud builds triggers run gwsdsc-apply \
  --region=europe-west1 \
  --branch=main \
  --substitutions=_APPLY_VERSION="2025-03-09T020000Z",_CONFIRM="true"
```

### 9.4 Selective Apply

To apply only specific resources (e.g. just groups and org units during an initial migration):

Edit the `cloudbuild-apply.yaml` to pass `--resources` to the gwsdsc CLI, or create a separate trigger with custom substitutions.

---

## 10. Operational Procedures

### 10.1 Key Rotation

```bash
# 1. Create a new key
gcloud iam service-accounts keys create new-sa-key.json \
  --iam-account=gwsdsc-exporter@gwsdsc-automation.iam.gserviceaccount.com

# 2. Upload new version to Secret Manager
gcloud secrets versions add gwsdsc-sa-key --data-file=new-sa-key.json

# 3. Verify the new key works (trigger a test export)
gcloud builds triggers run gwsdsc-export --region=europe-west1 --branch=main

# 4. Disable the old key version in Secret Manager
gcloud secrets versions disable OLD_VERSION_NUMBER --secret=gwsdsc-sa-key

# 5. Delete old key from GCP IAM
gcloud iam service-accounts keys list --iam-account=$SA_EMAIL
gcloud iam service-accounts keys delete OLD_KEY_ID --iam-account=$SA_EMAIL

# 6. Clean up local file
shred -u new-sa-key.json
```

### 10.2 Comparing Specific Snapshots Locally

```bash
# Download two snapshots
mkdir -p /tmp/snapshot-a /tmp/snapshot-b
gsutil -m rsync -r gs://gwsdsc-artifacts-yourdomain/exports/2025-03-01T020000Z/ /tmp/snapshot-a/
gsutil -m rsync -r gs://gwsdsc-artifacts-yourdomain/exports/2025-03-09T020000Z/ /tmp/snapshot-b/

# Run diff locally
gwsdsc diff \
  --baseline /tmp/snapshot-a \
  --target /tmp/snapshot-b \
  --report html \
  --output /tmp/my-comparison.html
```

### 10.3 Adjusting Retention

The artifact bucket is configured with two lifecycle rules (set in Terraform):

| Rule | Default | Purpose |
|---|---|---|
| `artifact_versions_to_keep` | 90 | Number of GCS object versions before the oldest is deleted |
| `artifact_max_age_days` | 365 | Maximum age of any object |

To change them, update `terraform.tfvars` and re-apply:

```bash
cd pipelines/google-cloud/terraform
terraform apply -var="artifact_versions_to_keep=180" -var="artifact_max_age_days=730"
```

### 10.4 Cost Estimation

For a typical tenant (500 users, nightly exports), expect approximately:

| Resource | Estimated Monthly Cost |
|---|---|
| Cloud Build | Less than $1 (a few minutes of build time per day) |
| Cloud Scheduler | Free tier (up to 3 jobs free per month) |
| Secret Manager | Less than $0.10 (one secret, one active version) |
| GCS storage | $0.50–$5 depending on snapshot size and retention |
| **Total** | **Less than $7 per month** |

---

## 11. Troubleshooting

### "403 Not Authorized to access this resource" from Google Admin APIs

The most common cause is a mismatch in domain-wide delegation. Confirm all three of these are correct: the service account's numeric Client ID is entered in the Admin Console, the OAuth scopes are complete and contain no extra whitespace, and the delegated admin email is a Super Admin that is not suspended.

### "Secret version not found"

```bash
gcloud secrets versions list gwsdsc-sa-key --project=gwsdsc-automation
```

Make sure the secret has at least one `ENABLED` version. If the Terraform secret was created but you forgot to upload the key value, the list will be empty.

### Cloud Build Cannot Access the Source Repository

If using GitHub, ensure the Cloud Build GitHub App is installed on the repository and has permissions. For Cloud Source Repositories, verify the Cloud Build SA has `roles/source.reader`.

### Cloud Scheduler Returns 403

The Cloud Build SA needs `roles/cloudbuild.builds.editor` to trigger builds. Terraform creates this binding, but if it was removed:

```bash
gcloud projects add-iam-policy-binding gwsdsc-automation \
  --member="serviceAccount:gwsdsc-cloudbuild@gwsdsc-automation.iam.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.editor"
```

### Export Succeeds but Diff Shows No Previous Snapshot

On the first run, there is no previous snapshot to compare against. The diff step gracefully skips. After the second successful export, diffs will work automatically.

### Build Exceeds Timeout

The default timeout in `cloudbuild-export.yaml` is 1 800 seconds (30 minutes). For very large tenants, increase it:

```yaml
timeout: "3600s"   # 60 minutes
```

Or exclude slow resources:

```yaml
# In the gen-config step, add:
exclude_resources:
  - app_access
  - ci_devices
  - mobile_devices
```

### Terraform State Conflicts

If multiple people run Terraform, use a GCS backend for remote state:

```hcl
terraform {
  backend "gcs" {
    bucket = "your-terraform-state-bucket"
    prefix = "gwsdsc"
  }
}
```

---

*Last updated: March 2026 — GoogleWorkspaceDsc v0.1.0*
