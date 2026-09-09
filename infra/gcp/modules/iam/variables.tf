variable "project_id" {
  type = string
}

variable "name" {
  type = string
}

variable "github_repo" {
  type        = string
  description = "GitHub repo in owner/name form, e.g. adamalgorf/Qinora_AI"
}

variable "secret_ids" {
  type        = list(string)
  description = "Secret Manager secret IDs the Cloud Run service account may read"
}
