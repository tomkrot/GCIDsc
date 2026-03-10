# ---------------------------------------------------------------------------
# GoogleWorkspaceDsc — Terraform: Google Cloud Infrastructure
# ---------------------------------------------------------------------------
# Creates:
#   • GCS bucket for artifacts (versioned)
#   • GCS bucket for reports
#   • Secret Manager secret for service account key
#   • Cloud Build triggers (export + apply)
#   • Cloud Scheduler job for nightly exports
#   • Service account for Cloud Build
#   • IAM bindings
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  # Optional: store state in GCS
  # backend "gcs" {
  #   bucket = "your-terraform-state-bucket"
  #   prefix = "gwsdsc"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# Enable required APIs
# ---------------------------------------------------------------------------

resource "google_project_service" "apis" {
  for_each = toset([
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
    "admin.googleapis.com",
    "groupssettings.googleapis.com",
    "chromepolicy.googleapis.com",
    "gmail.googleapis.com",
    "cloudidentity.googleapis.com",
    "accesscontextmanager.googleapis.com",
    "vault.googleapis.com",
    "alertcenter.googleapis.com",
    "licensing.googleapis.com",
    "chromemanagement.googleapis.com",
  ])

  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# GCS Bucket — Artifacts (versioned)
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "artifacts" {
  name                        = var.artifact_bucket_name
  location                    = var.region
  force_destroy               = false
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      num_newer_versions = var.artifact_versions_to_keep
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = var.artifact_max_age_days
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    managed-by = "gwsdsc"
    purpose    = "tenant-config-artifacts"
  }
}

# ---------------------------------------------------------------------------
# GCS Bucket — Reports
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "reports" {
  name                        = "${var.artifact_bucket_name}-reports"
  location                    = var.region
  force_destroy               = true
  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    managed-by = "gwsdsc"
    purpose    = "drift-reports"
  }
}

# ---------------------------------------------------------------------------
# Secret Manager — Service Account Key
# ---------------------------------------------------------------------------

resource "google_secret_manager_secret" "sa_key" {
  secret_id = var.secret_name

  replication {
    auto {}
  }

  labels = {
    managed-by = "gwsdsc"
  }

  depends_on = [google_project_service.apis["secretmanager.googleapis.com"]]
}

# NOTE: The actual secret version (key JSON) must be created manually or via
# a separate process:
#   gcloud secrets versions add gwsdsc-sa-key --data-file=sa-key.json

# ---------------------------------------------------------------------------
# Service Account for Cloud Build
# ---------------------------------------------------------------------------

resource "google_service_account" "cloudbuild_sa" {
  account_id   = "gwsdsc-cloudbuild"
  display_name = "GoogleWorkspaceDsc Cloud Build SA"
  description  = "Service account for gwsdsc Cloud Build pipelines"
}

# Grant Cloud Build SA access to artifacts bucket
resource "google_storage_bucket_iam_member" "cb_artifacts" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloudbuild_sa.email}"
}

resource "google_storage_bucket_iam_member" "cb_reports" {
  bucket = google_storage_bucket.reports.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.cloudbuild_sa.email}"
}

# Grant Cloud Build SA access to Secret Manager
resource "google_secret_manager_secret_iam_member" "cb_secret_access" {
  secret_id = google_secret_manager_secret.sa_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudbuild_sa.email}"
}

# Grant Cloud Build SA ability to write logs
resource "google_project_iam_member" "cb_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudbuild_sa.email}"
}

# ---------------------------------------------------------------------------
# Cloud Build Triggers
# ---------------------------------------------------------------------------

resource "google_cloudbuild_trigger" "export" {
  name        = "gwsdsc-export"
  description = "GoogleWorkspaceDsc — nightly export"
  location    = var.region

  service_account = google_service_account.cloudbuild_sa.id

  source_to_build {
    uri       = var.source_repo_url
    ref       = "refs/heads/main"
    repo_type = var.source_repo_type   # "GITHUB" or "CLOUD_SOURCE_REPOSITORIES"
  }

  git_file_source {
    path      = "pipelines/google-cloud/cloudbuild-export.yaml"
    uri       = var.source_repo_url
    revision  = "refs/heads/main"
    repo_type = var.source_repo_type
  }

  substitutions = {
    _GWS_CUSTOMER_ID     = var.gws_customer_id
    _GWS_PRIMARY_DOMAIN  = var.gws_primary_domain
    _GWS_TENANT_NAME     = var.gws_tenant_name
    _GWS_DELEGATED_ADMIN = var.gws_delegated_admin
    _SA_KEY_SECRET       = var.secret_name
    _ARTIFACT_BUCKET     = google_storage_bucket.artifacts.name
  }

  depends_on = [google_project_service.apis["cloudbuild.googleapis.com"]]
}

resource "google_cloudbuild_trigger" "apply" {
  name        = "gwsdsc-apply"
  description = "GoogleWorkspaceDsc — manual apply (requires confirmation)"
  location    = var.region

  service_account = google_service_account.cloudbuild_sa.id

  source_to_build {
    uri       = var.source_repo_url
    ref       = "refs/heads/main"
    repo_type = var.source_repo_type
  }

  git_file_source {
    path      = "pipelines/google-cloud/cloudbuild-apply.yaml"
    uri       = var.source_repo_url
    revision  = "refs/heads/main"
    repo_type = var.source_repo_type
  }

  substitutions = {
    _GWS_CUSTOMER_ID     = var.gws_customer_id
    _GWS_PRIMARY_DOMAIN  = var.gws_primary_domain
    _GWS_TENANT_NAME     = var.gws_tenant_name
    _GWS_DELEGATED_ADMIN = var.gws_delegated_admin
    _SA_KEY_SECRET       = var.secret_name
    _ARTIFACT_BUCKET     = google_storage_bucket.artifacts.name
    _CONFIRM             = "false"
  }

  # Require manual approval (configure in Cloud Build settings)
  approval_config {
    approval_required = true
  }

  depends_on = [google_project_service.apis["cloudbuild.googleapis.com"]]
}

# ---------------------------------------------------------------------------
# Cloud Scheduler — Nightly Export Trigger
# ---------------------------------------------------------------------------

resource "google_cloud_scheduler_job" "nightly_export" {
  name        = "gwsdsc-nightly-export"
  description = "Trigger gwsdsc export every night at 02:00 UTC"
  schedule    = var.export_schedule
  time_zone   = "UTC"
  region      = var.region

  http_target {
    http_method = "POST"
    uri         = "https://cloudbuild.googleapis.com/v1/projects/${var.project_id}/locations/${var.region}/triggers/${google_cloudbuild_trigger.export.trigger_id}:run"

    body = base64encode(jsonencode({
      projectId = var.project_id
      triggerId = google_cloudbuild_trigger.export.trigger_id
      source = {
        branchName = "main"
      }
    }))

    oauth_token {
      service_account_email = google_service_account.cloudbuild_sa.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [google_project_service.apis["cloudscheduler.googleapis.com"]]
}

# Grant Scheduler SA permission to trigger Cloud Build
resource "google_project_iam_member" "scheduler_cb_trigger" {
  project = var.project_id
  role    = "roles/cloudbuild.builds.editor"
  member  = "serviceAccount:${google_service_account.cloudbuild_sa.email}"
}
