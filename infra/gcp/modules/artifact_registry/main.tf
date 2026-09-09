resource "google_artifact_registry_repository" "backend" {
  project       = var.project_id
  location      = var.region
  repository_id = "${var.name}-backend"
  format        = "DOCKER"
  description   = "Docker images for the ${var.name} FastAPI backend"
  labels        = var.labels

  cleanup_policies {
    id     = "keep-recent-30"
    action = "KEEP"
    most_recent_versions {
      keep_count = 30
    }
  }
}
