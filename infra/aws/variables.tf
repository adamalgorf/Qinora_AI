variable "aws_region" {
  description = "AWS region. eu-north-1 (Stockholm) is closest to Sweden but does not support App Runner - eu-central-1 (Frankfurt) is the nearest region that does."
  type        = string
  default     = "eu-central-1"
}

variable "project_name" {
  type    = string
  default = "qinora"
}

variable "db_password" {
  description = "Master password for the RDS instance. Pass via TF_VAR_db_password, never commit it."
  type        = string
  sensitive   = true
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

variable "postgres_tenant_id" {
  type    = string
  default = "00000000-0000-0000-0000-000000000001"
}

variable "backend_image_tag" {
  description = "Tag to deploy for the backend ECR image. Bump this (or let CI pass a new one) to trigger a new App Runner deployment."
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  type    = string
  default = "latest"
}

# --- Outlook / Microsoft 365 intake bridge (qinora.workers.outlook_bridge) ---
# Either outlook_client_secret (application auth, Sandahls admin consent) or
# outlook_refresh_token (delegated auth via `python -m
# qinora.workers.outlook_bridge login`) must be non-empty for the bridge to
# start; leave both empty to deploy without the bridge scheduled at all.

variable "outlook_tenant_id" {
  description = "Entra ID tenant of the Sandahls mailboxes (GUID or sandahls.com)."
  type        = string
  default     = ""
}

variable "outlook_client_id" {
  description = "Application (client) ID of the QiNora app registration."
  type        = string
  default     = ""
}

variable "outlook_client_secret" {
  description = "Client secret for application (client-credentials) auth. Pass via TF_VAR_outlook_client_secret."
  type        = string
  sensitive   = true
  default     = ""
}

variable "outlook_refresh_token" {
  description = "Delegated refresh token for one mailbox, printed by the `login` helper. Pass via TF_VAR_outlook_refresh_token."
  type        = string
  sensitive   = true
  default     = ""
}

variable "outlook_mailboxes" {
  description = "Comma-separated mailboxes the bridge watches (application auth only)."
  type        = string
  default     = "test.spedition@sandahls.com,qinora.ai@sandahls.com"
}

variable "outlook_send_mailbox" {
  description = "Mailbox new outbound mail (carrier RFQs, unthreaded quotes) is sent from."
  type        = string
  default     = "test.spedition@sandahls.com"
}

variable "outlook_sender_name" {
  type    = string
  default = "Sandahls"
}
