variable "project_id" {
  type = string
}

variable "name_prefix" {
  type = string
}

variable "database_url" {
  type      = string
  sensitive = true
}

variable "labels" {
  type    = map(string)
  default = {}
}
