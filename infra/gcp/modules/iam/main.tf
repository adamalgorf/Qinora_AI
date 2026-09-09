# --- Cloud Run runtime service account -------------------------------------

resource "google_service_account" "cloud_run" {
  project      = var.project_id
  account_id   = "${var.name}-run-sa"
  display_name = "${var.name} Cloud Run runtime"
}

resource "google_project_iam_member" "cloud_run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

# Grant secret access per-secret rather than project-wide.
resource "google_secret_manager_secret_iam_member" "cloud_run_secret_access" {
  for_each  = toset(var.secret_ids)
  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

# --- GitHub Actions deploy identity (Workload Identity Federation) ---------
# No long-lived key is created; GitHub Actions exchanges its OIDC token for
# short-lived credentials scoped to this service account.

resource "google_service_account" "github_actions" {
  project      = var.project_id
  account_id   = "${var.name}-gha-deploy"
  display_name = "${var.name} GitHub Actions deployer"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "${var.name}-github-pool"
  display_name              = "${var.name} GitHub pool"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "${var.name}-github-provider"
  display_name                       = "${var.name} GitHub provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  # Restrict to this repo only.
  attribute_condition = "assertion.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

resource "google_project_iam_member" "github_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_project_iam_member" "github_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

# Lets the GitHub Actions SA deploy new revisions running as the Cloud Run SA.
resource "google_service_account_iam_member" "github_actas_cloud_run_sa" {
  service_account_id = google_service_account.cloud_run.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions.email}"
}
