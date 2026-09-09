output "database_url_secret_id" {
  value = google_secret_manager_secret.database_url.secret_id
}

output "database_url_secret_name" {
  value = google_secret_manager_secret.database_url.name
}
