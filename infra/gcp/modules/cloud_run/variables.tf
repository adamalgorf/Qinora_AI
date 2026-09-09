variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "image" {
  type        = string
  description = "Full container image reference, e.g. europe-north2-docker.pkg.dev/PROJECT/qinora-backend/api:latest"
}

variable "service_account_email" {
  type = string
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 4
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "1Gi"
}

variable "container_port" {
  type        = number
  default     = 8000
  description = "Must match the port the container listens on (see backend/Dockerfile)"
}

variable "vpc_connector_id" {
  type        = string
  default     = null
  description = "Serverless VPC Access connector ID (see modules/network). Leave null to run without private networking - fine as long as DATABASE_URL points at a publicly reachable Postgres."
}

variable "env_vars" {
  type        = map(string)
  description = "Plain, non-secret environment variables"
  default     = {}
}

variable "secret_env_vars" {
  type = map(object({
    secret_id = string
    version   = optional(string, "latest")
  }))
  description = "Environment variables sourced from Secret Manager, keyed by env var name"
  default     = {}
}

variable "labels" {
  type    = map(string)
  default = {}
}
