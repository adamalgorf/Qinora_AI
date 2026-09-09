output "backend_url" {
  description = "Direct Cloud Run URL (bypasses the load balancer / Cloud Armor)"
  value       = module.cloud_run.url
}

output "load_balancer_ip" {
  description = "Point app.qinora.se's DNS A record at this IP"
  value       = module.load_balancer.lb_ip_address
}

output "frontend_bucket_name" {
  value = module.gcs_site.bucket_name
}

output "cloud_sql_instance_connection_name" {
  value = module.cloud_sql.instance_connection_name
}

output "cloud_sql_private_ip" {
  value = module.cloud_sql.private_ip_address
}

output "artifact_registry_repository_url" {
  value = module.artifact_registry.repository_url
}

output "artifact_registry_repository_id" {
  description = "GitHub repo var GCP_ARTIFACT_REPOSITORY"
  value       = module.artifact_registry.repository_id
}

output "cloud_run_service_name" {
  description = "GitHub repo var GCP_SERVICE"
  value       = module.cloud_run.service_name
}

output "workload_identity_provider" {
  description = "Pass to google-github-actions/auth as workload_identity_provider (GitHub repo var GCP_WORKLOAD_IDENTITY_PROVIDER)"
  value       = module.iam.workload_identity_provider
}

output "github_actions_service_account_email" {
  description = "Pass to google-github-actions/auth as service_account (GitHub repo var GCP_SERVICE_ACCOUNT)"
  value       = module.iam.github_actions_service_account_email
}
