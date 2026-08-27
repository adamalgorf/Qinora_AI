variable "aws_region" {
  description = "AWS region. Stockholm is the closest region to Sweden."
  type        = string
  default     = "eu-north-1"
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
