variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "labels" {
  type    = map(string)
  default = {}
}
