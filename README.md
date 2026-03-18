# Deployment Guide — Google Cloud Pipeline

> Quick-reference guide for deploying the Cloud Build pipelines and
> Terraform infrastructure in this directory.  For the full end-to-end
> walkthrough including Google Workspace preparation, see
> [`docs/implementation-google-cloud.md`](../../docs/implementation-google-cloud.md).

---

## Contents of This Directory

```
pipelines/google-cloud/
├── README.md                      ← you are here
├── cloudbuild-export.yaml         ← Cloud Build: nightly export pipeline
├── cloudbuild-apply.yaml          ← Cloud Build: manual apply pipeline (approval-gated)
└── terraform/
    ├── main.tf                    ← All GCP resources (buckets, triggers, scheduler, IAM)
    ├── variables.tf               ← Input variables
    └── outputs.tf                 ← Output values (bucket names, trigger IDs, etc.)
```

---

## Architecture

```
Cloud Scheduler (cron)
       │
       ▼
Cloud Build Trigger ("gwsdsc-export")
       │
       ├── 1. pip install gwsdsc
       ├── 2. Read SA key from Secret Manager
       ├── 3. Generate tenant.yaml
       ├── 4. gwsdsc export → JSON artifacts
       ├── 5. gsutil rsync → GCS versioned bucket
       ├── 6. gwsdsc diff → HTML drift report → GCS reports bucket
       └── 7. git commit + tag → Source repository

Cloud Build Trigger ("gwsdsc-apply")  ← manual, approval required
       │
       ├── 1. pip install gwsdsc
       ├── 2. Read SA key from Secret Manager
       ├── 3. Download snapshot from GCS
       ├── 4. gwsdsc apply --plan (dry-run)
       └── 5. gwsdsc apply --confirm (if _CONFIRM=true)
```

---

## How the Pipeline Installs gwsdsc

The gwsdsc package is not published to PyPI — it lives in the Git repository.  Cloud Build accesses it through the source repository connection.

When a Cloud Build trigger fires, Cloud Build clones the linked repository (GitHub or Cloud Source Repos) into the `/workspace` directory inside the build container:

```
/workspace/                         ← Cloud Build workspace
    ├── pyproject.toml               ← pip reads this
    ├── src/gwsdsc/                  ← the Python package source
    ├── pipelines/
    ├── config/
    └── ...
```

Each step that runs `pip install -e ".[dev]"` does the following:

1. Reads `pyproject.toml` in `/workspace`
2. Downloads dependencies (google-api-python-client, tenacity, etc.) from **PyPI**
3. Installs the `gwsdsc` package from the local source code
4. Registers the `gwsdsc` command in the container's PATH

Because Cloud Build steps run in separate Docker containers, the install must be repeated in each step that calls `gwsdsc`.  The `/workspace` directory is shared across steps (it's a mounted volume), but the Python installation inside each container is isolated.

---

## Prerequisites

Before deploying, you must have completed:

1. **Google Workspace service account** with domain-wide delegation and all required OAuth scopes (see [`docs/authentication.md`](../../docs/authentication.md))
2. **GCP project** with billing enabled
3. **SA key JSON file** on your local machine (will be uploaded to Secret Manager, then deleted)
4. **Terraform** 1.5+ installed locally
5. **gcloud CLI** authenticated (`gcloud auth login`)

---

## Step-by-Step Deployment

### 1. Enable Required APIs

```bash
gcloud config set project YOUR_PROJECT_ID

gcloud services enable \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  admin.googleapis.com \
  groupssettings.googleapis.com \
  chromepolicy.googleapis.com \
  gmail.googleapis.com \
  cloudidentity.googleapis.com \
  accesscontextmanager.googleapis.com \
  vault.googleapis.com \
  alertcenter.googleapis.com \
  licensing.googleapis.com \
  chromemanagement.googleapis.com
```

### 2. Create Terraform Variables File

```bash
cd pipelines/google-cloud/terraform

cat > terraform.tfvars << 'EOF'
project_id          = "your-gcp-project-id"
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

For Cloud Source Repositories instead of GitHub:

```hcl
source_repo_url  = "https://source.developers.google.com/p/YOUR_PROJECT/r/gwsdsc-config"
source_repo_type = "CLOUD_SOURCE_REPOSITORIES"
```

### 3. Run Terraform

```bash
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

This creates all resources in one step:

| Resource | Purpose |
|---|---|
| **GCS bucket** (`artifacts`) | Versioned snapshot storage (90 versions, 365-day max age) |
| **GCS bucket** (`reports`) | HTML drift reports (90-day retention) |
| **Secret Manager secret** | Container for the SA key (empty — you upload the value next) |
| **Service Account** (`gwsdsc-cloudbuild`) | Cloud Build pipeline identity |
| **Cloud Build trigger** (`gwsdsc-export`) | Export pipeline — triggered by Scheduler |
| **Cloud Build trigger** (`gwsdsc-apply`) | Apply pipeline — manual, approval required |
| **Cloud Scheduler job** | Fires the export trigger at 02:00 UTC daily |
| **IAM bindings** | Storage, Secret Manager, logging, and Scheduler→Build permissions |

### 4. Upload the SA Key to Secret Manager

```bash
gcloud secrets versions add gwsdsc-sa-key \
  --data-file=path/to/sa-key.json \
  --project=YOUR_PROJECT_ID
```

Verify:

```bash
gcloud secrets versions list gwsdsc-sa-key
```

Then **delete the local key file** — it's now in Secret Manager.

### 5. Connect the Source Repository

**GitHub:** Go to **Cloud Build → Triggers** in the GCP Console. If prompted, install the Cloud Build GitHub App on your repository.

**Cloud Source Repositories:**

```bash
gcloud source repos create gwsdsc-config
cd /path/to/GoogleWorkspaceDsc
git remote add google https://source.developers.google.com/p/YOUR_PROJECT/r/gwsdsc-config
git push google main
```

### 6. Test the Export Trigger

```bash
gcloud builds triggers run gwsdsc-export \
  --region=europe-west1 \
  --branch=main
```

Monitor the build:

```bash
gcloud builds log --stream $(gcloud builds list --limit=1 --format="value(id)")
```

### 7. Verify Outputs

```bash
# List snapshots in GCS
gsutil ls gs://gwsdsc-artifacts-yourdomain/exports/

# Check the latest pointer
gsutil cat gs://gwsdsc-artifacts-yourdomain/exports/latest.json

# View a resource export
gsutil cat gs://gwsdsc-artifacts-yourdomain/exports/2025-03-09T020000Z/users.json | python3 -m json.tool | head 20
```

---

## Cloud Build Substitutions Reference

Both pipelines accept substitution variables.  Terraform sets these via the trigger definition, but they can also be overridden when running manually.

### Export Pipeline (`cloudbuild-export.yaml`)

| Variable | Default | Description |
|---|---|---|
| `_GWS_CUSTOMER_ID` | `my_customer` | Google Workspace Customer ID |
| `_GWS_PRIMARY_DOMAIN` | `example.com` | Primary domain |
| `_GWS_TENANT_NAME` | `My Organisation` | Display name for reports |
| `_GWS_DELEGATED_ADMIN` | `admin@example.com` | Super Admin for domain-wide delegation |
| `_SA_KEY_SECRET` | `gwsdsc-sa-key` | Secret Manager secret name |
| `_ARTIFACT_BUCKET` | `gwsdsc-artifacts` | GCS bucket for snapshots |
| `_ARTIFACT_REPO` | `gwsdsc-config` | Source repository name |

### Apply Pipeline (`cloudbuild-apply.yaml`)

All of the above, plus:

| Variable | Default | Description |
|---|---|---|
| `_APPLY_VERSION` | (empty) | Snapshot timestamp to apply.  Empty = latest. |
| `_CONFIRM` | `false` | Set to `true` to actually apply changes.  `false` = dry-run only. |

**Manual trigger with overrides:**

```bash
# Dry-run (plan only)
gcloud builds triggers run gwsdsc-apply \
  --region=europe-west1 \
  --branch=main \
  --substitutions=_APPLY_VERSION="2025-03-09T020000Z"

# Apply for real (requires approval if configured)
gcloud builds triggers run gwsdsc-apply \
  --region=europe-west1 \
  --branch=main \
  --substitutions=_APPLY_VERSION="2025-03-09T020000Z",_CONFIRM="true"
```

---

## Customisation

### Change the Export Schedule

Edit `export_schedule` in `terraform.tfvars` and re-apply, or update directly:

```bash
gcloud scheduler jobs update http gwsdsc-nightly-export \
  --schedule="0 6 * * 1-5" \
  --location=europe-west1
```

### Increase Build Timeout

Edit the `timeout` field at the top of `cloudbuild-export.yaml`:

```yaml
timeout: "3600s"   # 60 minutes for large tenants
```

### Export Specific Resources

Modify the `gwsdsc export` command in step 4 of `cloudbuild-export.yaml`:

```bash
gwsdsc export \
  --config /workspace/config/tenant.yaml \
  --output /workspace/artifacts/$${TIMESTAMP} \
  --resources users,groups,ci_policies,context_aware_access
```

### Exclude Resources

Add `exclude_resources` to the generated `tenant.yaml` in step 3:

```yaml
exclude_resources:
  - app_access
  - ci_devices
  - chromeos_telemetry
```

### Change the GCS Region or Retention

Edit `terraform.tfvars`:

```hcl
region                    = "us-central1"
artifact_versions_to_keep = 180
artifact_max_age_days     = 730
```

Then: `terraform apply`.

---

## Outputs After Deployment

After a successful export run, the following artifacts exist:

| Artifact | Location | Description |
|---|---|---|
| Snapshot | `gs://<bucket>/exports/<timestamp>/` | JSON files per resource module |
| Latest pointer | `gs://<bucket>/exports/latest.json` | `{"latest_version": "<timestamp>"}` |
| Drift report (HTML) | `gs://<bucket>-reports/drift-report-<timestamp>.html` | Human-readable drift report |
| Diff result (JSON) | `gs://<bucket>-reports/diff-result-<timestamp>.json` | Machine-readable diff |
| Git commit | Source repo | `gwsdsc export <timestamp>` with tag `export/<timestamp>` |

---

## Terraform Resources Reference

After `terraform apply`, these resources exist in your GCP project:

| Terraform Resource | GCP Resource | Name |
|---|---|---|
| `google_storage_bucket.artifacts` | GCS Bucket | `<artifact_bucket_name>` |
| `google_storage_bucket.reports` | GCS Bucket | `<artifact_bucket_name>-reports` |
| `google_secret_manager_secret.sa_key` | Secret | `gwsdsc-sa-key` |
| `google_service_account.cloudbuild_sa` | Service Account | `gwsdsc-cloudbuild@<project>.iam.gserviceaccount.com` |
| `google_cloudbuild_trigger.export` | Cloud Build Trigger | `gwsdsc-export` |
| `google_cloudbuild_trigger.apply` | Cloud Build Trigger | `gwsdsc-apply` (approval required) |
| `google_cloud_scheduler_job.nightly_export` | Cloud Scheduler Job | `gwsdsc-nightly-export` |

### Destroying the Infrastructure

To tear down everything Terraform created:

```bash
cd pipelines/google-cloud/terraform
terraform destroy
```

This does **not** delete the Secret Manager secret versions (data protection) or the GCS bucket contents.  To fully clean up:

```bash
gcloud secrets delete gwsdsc-sa-key --quiet
gsutil -m rm -r gs://gwsdsc-artifacts-yourdomain/
gsutil -m rm -r gs://gwsdsc-artifacts-yourdomain-reports/
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Build fails at step 2 (get-secret) | Secret has no versions, or Cloud Build SA lacks `secretAccessor` role | Upload the key: `gcloud secrets versions add gwsdsc-sa-key --data-file=key.json` |
| `403 Not Authorized` from Google Admin APIs | DWD misconfigured or scopes incomplete | Verify Client ID + scopes in Admin Console → API controls → Domain-Wide Delegation |
| Cloud Scheduler returns `PERMISSION_DENIED` | Cloud Build SA lacks `cloudbuild.builds.editor` role | Re-run `terraform apply` or add the role manually |
| Build fails at step 1 (pip install) | Network issue or Python image changed | Try `python:3.12` instead of `python:3.12-slim` |
| Diff says "No previous export" | First run — nothing to compare yet | Expected.  The second run will produce a diff. |
| Apply trigger doesn't need approval | `approval_required` not set | Verify in Console: **Cloud Build → Triggers → gwsdsc-apply → Edit → Approval** |
| GCS bucket name conflict | Bucket name is globally unique | Change `artifact_bucket_name` in `terraform.tfvars` |
| Terraform state conflict | Multiple operators | Use a GCS backend: add `backend "gcs" { bucket = "..." }` to `main.tf` |

---

## Cost Estimate

For a typical tenant (500 users, nightly exports):

| Resource | Monthly Cost |
|---|---|
| Cloud Build | < $1 |
| Cloud Scheduler | Free tier (3 jobs/month) |
| Secret Manager | < $0.10 |
| GCS storage | $0.50–$5 |
| **Total** | **< $7/month** |

---

## Related Documentation

- **Full implementation guide**: [`docs/implementation-google-cloud.md`](../../docs/implementation-google-cloud.md)
- **Authentication & scopes**: [`docs/authentication.md`](../../docs/authentication.md)
- **Adding resources**: [`docs/extending-resources.md`](../../docs/extending-resources.md)
- **API coverage**: [`docs/api-gap-analysis.md`](../../docs/api-gap-analysis.md)
