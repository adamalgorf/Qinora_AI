terraform {
  required_version = ">= 1.9.0"

  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }

  # Terraform's backend block can't reference variables, so the bucket name
  # is filled in via -backend-config at init time. See README.md.
  backend "gcs" {
    prefix = "qinora/dev"
  }
}
