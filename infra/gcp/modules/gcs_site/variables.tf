variable "project_id" {
  type = string
}

variable "name" {
  type = string
}

variable "location" {
  type        = string
  description = "GCS bucket location (can be a multi-region like EU, or a single region)"
  default     = "EU"
}

variable "labels" {
  type    = map(string)
  default = {}
}
