variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "tier" {
  type        = string
  description = "Cloud SQL machine tier, e.g. db-f1-micro (shared-core, dev-friendly)"
  default     = "db-f1-micro"
}

variable "database_version" {
  type    = string
  default = "POSTGRES_16"
}

variable "disk_size_gb" {
  type    = number
  default = 10
}

variable "db_name" {
  type = string
}

variable "db_user" {
  type = string
}

variable "network_id" {
  type        = string
  description = "Self link / id of the VPC to attach the private IP to"
}

variable "private_vpc_connection" {
  type        = string
  description = "Forces Terraform to wait for the private services peering before creating the instance"
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "labels" {
  type    = map(string)
  default = {}
}
