# ---------------------------------------------------------------------------
# GoogleWorkspaceDsc — Terraform Variables
# ---------------------------------------------------------------------------

variable "project_id" {
  description = "Google Cloud project ID"
  type        = string
}

variable "region" {
  description = "Google Cloud region"
  type        = string
  default     = "europe-west1"
}

# --- Google Workspace tenant ---

variable "gws_customer_id" {
  description = "Google Workspace customer ID (or 'my_customer')"
  type        = string
  default     = "my_customer"
}

variable "gws_primary_domain" {
  description = "Primary domain of the Google Workspace tenant"
  type        = string
}

variable "gws_tenant_name" {
  description = "Human-readable tenant name (used in reports)"
  type        = string
}

variable "gws_delegated_admin" {
  description = "Email of the admin account for domain-wide delegation"
  type        = string
}

# --- Storage ---

variable "artifact_bucket_name" {
  description = "Name for the GCS artifacts bucket"
  type        = string
  default     = "gwsdsc-artifacts"
}

variable "artifact_versions_to_keep" {
  description = "Number of object versions to retain in the artifacts bucket"
  type        = number
  default     = 90
}

variable "artifact_max_age_days" {
  description = "Maximum age (days) for artifact objects before deletion"
  type        = number
  default     = 365
}

# --- Secret Manager ---

variable "secret_name" {
  description = "Secret Manager secret name for the service account key"
  type        = string
  default     = "gwsdsc-sa-key"
}

# --- Source Repository ---

variable "source_repo_url" {
  description = "Git repository URL (GitHub or Cloud Source Repositories)"
  type        = string
}

variable "source_repo_type" {
  description = "Repository type: GITHUB or CLOUD_SOURCE_REPOSITORIES"
  type        = string
  default     = "GITHUB"

  validation {
    condition     = contains(["GITHUB", "CLOUD_SOURCE_REPOSITORIES"], var.source_repo_type)
    error_message = "Must be GITHUB or CLOUD_SOURCE_REPOSITORIES."
  }
}

# --- Scheduling ---

variable "export_schedule" {
  description = "Cron schedule for nightly exports (Cloud Scheduler format)"
  type        = string
  default     = "0 2 * * *"   # 02:00 UTC daily
}
