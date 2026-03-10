# ---------------------------------------------------------------------------
# GoogleWorkspaceDsc — Terraform Outputs
# ---------------------------------------------------------------------------

output "artifact_bucket" {
  description = "GCS bucket for configuration artifacts"
  value       = google_storage_bucket.artifacts.name
}

output "reports_bucket" {
  description = "GCS bucket for drift reports"
  value       = google_storage_bucket.reports.name
}

output "cloudbuild_sa_email" {
  description = "Service account email used by Cloud Build"
  value       = google_service_account.cloudbuild_sa.email
}

output "export_trigger_id" {
  description = "Cloud Build trigger ID for exports"
  value       = google_cloudbuild_trigger.export.trigger_id
}

output "apply_trigger_id" {
  description = "Cloud Build trigger ID for apply (requires approval)"
  value       = google_cloudbuild_trigger.apply.trigger_id
}

output "scheduler_job_name" {
  description = "Cloud Scheduler job name for nightly exports"
  value       = google_cloud_scheduler_job.nightly_export.name
}

output "secret_id" {
  description = "Secret Manager secret ID for the SA key"
  value       = google_secret_manager_secret.sa_key.secret_id
}

output "next_steps" {
  description = "Post-apply instructions"
  value       = <<-EOT

    ╔══════════════════════════════════════════════════════════════╗
    ║                    Next Steps                               ║
    ╠══════════════════════════════════════════════════════════════╣
    ║                                                              ║
    ║  1. Upload your service account key to Secret Manager:       ║
    ║     gcloud secrets versions add ${var.secret_name} \         ║
    ║       --data-file=path/to/sa-key.json                        ║
    ║                                                              ║
    ║  2. Configure domain-wide delegation in Google Admin Console ║
    ║     for the service account with required OAuth scopes.      ║
    ║     See docs/authentication.md for the scope list.           ║
    ║                                                              ║
    ║  3. Test manually:                                           ║
    ║     gcloud builds triggers run gwsdsc-export \               ║
    ║       --region=${var.region}                                  ║
    ║                                                              ║
    ║  4. The nightly schedule will start at ${var.export_schedule} ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
  EOT
}
