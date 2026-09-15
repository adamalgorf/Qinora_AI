variable "project_id" {
  type        = string
  description = "GCP project ID, e.g. qinora-prod"
}

variable "region" {
  type        = string
  default     = "europe-north2"
  description = "europe-north2 (Stockholm) - eu-north1/europe-north1 are not the same region (Finland)"
}

variable "scheduler_region" {
  type        = string
  default     = "europe-west1"
  description = "Region for Cloud Scheduler triggers - it doesn't support europe-north2, so this is a separate, valid region (see modules/scheduled_job)."
}

variable "name" {
  type    = string
  default = "qinora"
}

variable "github_repo" {
  type        = string
  default     = "adamalgorf/Qinora_AI"
  description = "GitHub repo in owner/name form - restricts which repo can assume the deploy identity"
}

variable "database_url" {
  description = "Full Postgres connection string. Leave null to use the Cloud SQL instance provisioned by modules/cloud_sql; set to point at an external Postgres instead. Pass via TF_VAR_database_url, never commit it."
  type        = string
  sensitive   = true
  default     = null
}

variable "domain_name" {
  type        = string
  description = "Domain the load balancer's managed SSL certificate is issued for, e.g. app.qinora.se. Point its DNS A record at the load_balancer_ip output."
}

variable "db_tier" {
  type        = string
  description = "Cloud SQL machine tier. db-f1-micro is the shared-core, dev-friendly tier (GCP has no db-e2-micro tier)."
  default     = "db-f1-micro"
}

variable "db_disk_size_gb" {
  type    = number
  default = 10
}

variable "db_name" {
  type    = string
  default = "qinora"
}

variable "db_user" {
  type    = string
  default = "qinora_app"
}

variable "db_deletion_protection" {
  type    = bool
  default = true
}

variable "cors_allowed_origins" {
  type    = string
  default = "*"
}

variable "cloud_run_min_instances" {
  type        = number
  description = "Cloud Run instance counts are whole numbers; 0 allows scale-to-zero"
  default     = 0
}

variable "cloud_run_max_instances" {
  type    = number
  default = 4
}

variable "cloud_run_cpu" {
  type    = string
  default = "1"
}

variable "cloud_run_memory" {
  type    = string
  default = "1Gi"
}

variable "openai_api_key" {
  type      = string
  sensitive = true
}

variable "openai_model" {
  type    = string
  default = "gpt-4o-mini"
}

variable "email_webhook_secret" {
  type      = string
  sensitive = true
}

variable "auth_token_secret" {
  type      = string
  sensitive = true
}

# When set, gates the app behind /auth/login instead of the unauthenticated
# /auth/dev-token auto-login path (see backend/src/qinora/interfaces/http
# /routers/auth.py) - required for any environment reachable by the public
# internet.
variable "app_password" {
  type      = string
  sensitive = true
}

variable "postgres_tenant_id" {
  type    = string
  default = "00000000-0000-0000-0000-000000000001"
}

variable "outlook_tenant_id" {
  type    = string
  default = ""
}

variable "outlook_client_id" {
  type    = string
  default = ""
}

variable "outlook_client_secret" {
  description = "Leave as the placeholder if using OUTLOOK_REFRESH_TOKEN (delegated auth) instead - Secret Manager rejects an empty payload, so a real blank isn't an option."
  type        = string
  sensitive   = true
  default     = "not-configured"
}

variable "outlook_refresh_token" {
  description = "Leave as the placeholder if using OUTLOOK_CLIENT_SECRET (application auth) instead - Secret Manager rejects an empty payload, so a real blank isn't an option."
  type        = string
  sensitive   = true
  default     = "not-configured"
}

variable "outlook_mailboxes" {
  type    = string
  default = ""
}

variable "outlook_send_mailbox" {
  type    = string
  default = ""
}

variable "outlook_sender_name" {
  type    = string
  default = ""
}

variable "backend_image_tag" {
  description = "Image tag to deploy on `terraform apply`. CI deploys new SHA-tagged images directly via `gcloud run deploy` (see .github/workflows/deploy-gcp.yml) and Terraform ignores drift on this field (see modules/cloud_run/main.tf) - this only matters for the very first apply, before any image has been pushed. Push a placeholder image at this tag first (see infra/gcp README/setup instructions)."
  type        = string
  default     = "bootstrap"
}
