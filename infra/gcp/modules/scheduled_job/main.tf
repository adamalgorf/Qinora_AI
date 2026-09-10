# Each backend/src/qinora/workers/*.py entrypoint runs one batch pass and
# exits (see docker-compose.yml's `while true; do python -m ...; sleep N;
# done` loops) - Cloud Run Jobs + Cloud Scheduler is the run-to-completion
# GCP equivalent, replacing the sleep loop with a cron schedule.

resource "google_cloud_run_v2_job" "job" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  deletion_protection = false
  labels              = var.labels

  template {
    template {
      service_account = var.service_account_email
      timeout         = "${var.timeout_seconds}s"
      max_retries     = 1

      dynamic "vpc_access" {
        for_each = var.vpc_connector_id != null ? [var.vpc_connector_id] : []
        content {
          connector = vpc_access.value
          egress    = "PRIVATE_RANGES_ONLY"
        }
      }

      containers {
        image = var.image
        # backend/Dockerfile has no ENTRYPOINT, only a CMD, so the full
        # invocation (including the interpreter) must be set here.
        command = var.args

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }

        dynamic "env" {
          for_each = var.env_vars
          content {
            name  = env.key
            value = env.value
          }
        }

        dynamic "env" {
          for_each = var.secret_env_vars
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value.secret_id
                version = env.value.version
              }
            }
          }
        }
      }
    }
  }
}

# Dedicated identity for Cloud Scheduler to invoke this one job - narrower
# than granting it broadly on the runtime service account.
resource "google_service_account" "invoker" {
  project = var.project_id
  # GCP service account IDs are capped at 30 chars - truncate rather than
  # error on longer worker names (e.g. qinora-stale-request-escalator).
  account_id   = substr("${var.name}-inv", 0, 30)
  display_name = "Cloud Scheduler invoker for ${var.name}"
}

resource "google_cloud_run_v2_job_iam_member" "invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.job.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.invoker.email}"
}

resource "google_cloud_scheduler_job" "trigger" {
  project  = var.project_id
  region   = var.scheduler_region
  name     = "${var.name}-trigger"
  schedule = var.schedule

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.job.name}:run"

    oauth_token {
      service_account_email = google_service_account.invoker.email
    }
  }

  retry_config {
    retry_count = 1
  }
}
