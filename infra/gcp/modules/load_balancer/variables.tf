variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "domain_name" {
  type        = string
  description = "Domain the managed SSL certificate will be issued for, e.g. app.qinora.com"
}

variable "cloud_run_service_name" {
  type = string
}

variable "backend_bucket_id" {
  type = string
}

variable "labels" {
  type    = map(string)
  default = {}
}
