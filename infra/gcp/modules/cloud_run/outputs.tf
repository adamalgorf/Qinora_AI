output "service_name" {
  value = google_cloud_run_v2_service.api.name
}

output "url" {
  value = google_cloud_run_v2_service.api.uri
}

output "latest_ready_revision" {
  value = google_cloud_run_v2_service.api.latest_ready_revision
}
