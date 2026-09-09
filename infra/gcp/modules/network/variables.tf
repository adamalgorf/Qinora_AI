variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type        = string
  description = "Base name for network resources"
}

variable "labels" {
  type    = map(string)
  default = {}
}
