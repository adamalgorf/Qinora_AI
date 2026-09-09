variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type        = string
  description = "Full resource name for the job, e.g. qinora-outbound-mailer"
}

variable "image" {
  type = string
}

variable "args" {
  type        = list(string)
  description = "Full container command (backend/Dockerfile has no ENTRYPOINT), e.g. [\"python\", \"-m\", \"qinora.workers.outbound_mailer\"]"
}

variable "service_account_email" {
  type        = string
  description = "Identity the job's container runs as"
}

variable "schedule" {
  type        = string
  description = "Cron expression, e.g. \"* * * * *\". Cloud Scheduler's minimum granularity is 1 minute."
}

variable "timeout_seconds" {
  type    = number
  default = 300
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "vpc_connector_id" {
  type    = string
  default = null
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

variable "secret_env_vars" {
  type = map(object({
    secret_id = string
    version   = optional(string, "latest")
  }))
  default = {}
}

variable "labels" {
  type    = map(string)
  default = {}
}
