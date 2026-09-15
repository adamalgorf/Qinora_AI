provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  labels = { app = var.name }
}

resource "google_project_service" "required" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "sqladmin.googleapis.com",
    "compute.googleapis.com",
    "vpcaccess.googleapis.com",
    "servicenetworking.googleapis.com",
    "cloudscheduler.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# --- Networking + Cloud SQL --------------------------------------------------
# Private-IP Postgres, reachable from Cloud Run over a Serverless VPC Access
# connector. See modules/network and modules/cloud_sql.

module "network" {
  source = "./modules/network"

  project_id = var.project_id
  region     = var.region
  name       = var.name
  labels     = local.labels

  depends_on = [google_project_service.required]
}

module "cloud_sql" {
  source = "./modules/cloud_sql"

  project_id             = var.project_id
  region                 = var.region
  name                   = var.name
  tier                   = var.db_tier
  disk_size_gb           = var.db_disk_size_gb
  db_name                = var.db_name
  db_user                = var.db_user
  deletion_protection    = var.db_deletion_protection
  network_id             = module.network.network_id
  private_vpc_connection = module.network.private_vpc_connection
  labels                 = local.labels
}

locals {
  # var.database_url overrides this if you want to point at an external
  # Postgres instead of the Cloud SQL instance provisioned above.
  database_url = coalesce(var.database_url, "postgresql://${module.cloud_sql.db_user}:${module.cloud_sql.db_password}@${module.cloud_sql.private_ip_address}:5432/${module.cloud_sql.db_name}")
}

# --- Artifact Registry --------------------------------------------------------

module "artifact_registry" {
  source     = "./modules/artifact_registry"
  project_id = var.project_id
  region     = var.region
  name       = var.name
  labels     = local.labels

  depends_on = [google_project_service.required]
}

# --- Secrets ------------------------------------------------------------------
# database-url goes through modules/secrets; the rest of the backend's secret
# contract (see backend/.env.example and
# backend/src/qinora/infrastructure/settings.py) is small enough to declare
# directly here rather than growing that module's interface.

module "secrets" {
  source       = "./modules/secrets"
  project_id   = var.project_id
  name_prefix  = var.name
  database_url = local.database_url
  labels       = local.labels

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "openai_api_key" {
  project   = var.project_id
  secret_id = "${var.name}-openai-api-key"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "openai_api_key" {
  secret      = google_secret_manager_secret.openai_api_key.id
  secret_data = var.openai_api_key
}

resource "google_secret_manager_secret" "email_webhook_secret" {
  project   = var.project_id
  secret_id = "${var.name}-email-webhook-secret"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "email_webhook_secret" {
  secret      = google_secret_manager_secret.email_webhook_secret.id
  secret_data = var.email_webhook_secret
}

resource "google_secret_manager_secret" "auth_token_secret" {
  project   = var.project_id
  secret_id = "${var.name}-auth-token-secret"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "auth_token_secret" {
  secret      = google_secret_manager_secret.auth_token_secret.id
  secret_data = var.auth_token_secret
}

resource "google_secret_manager_secret" "app_password" {
  project   = var.project_id
  secret_id = "${var.name}-app-password"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "app_password" {
  secret      = google_secret_manager_secret.app_password.id
  secret_data = var.app_password
}

# Blank until you set outlook_client_secret/outlook_refresh_token - the
# outlook-bridge job will fail (harmlessly, no monitoring/alerting wired up
# per scope) until one of them is populated. See README.md.

resource "google_secret_manager_secret" "outlook_client_secret" {
  project   = var.project_id
  secret_id = "${var.name}-outlook-client-secret"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "outlook_client_secret" {
  secret      = google_secret_manager_secret.outlook_client_secret.id
  secret_data = var.outlook_client_secret
}

resource "google_secret_manager_secret" "outlook_refresh_token" {
  project   = var.project_id
  secret_id = "${var.name}-outlook-refresh-token"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "outlook_refresh_token" {
  secret      = google_secret_manager_secret.outlook_refresh_token.id
  secret_data = var.outlook_refresh_token
}

# --- IAM + Workload Identity Federation ---------------------------------------
# See modules/iam/main.tf: Cloud Run runtime service account, GitHub Actions
# deploy service account, and the workload identity pool/provider that lets
# GitHub Actions impersonate it via OIDC - no service account key involved.

module "iam" {
  source      = "./modules/iam"
  project_id  = var.project_id
  name        = var.name
  github_repo = var.github_repo

  secret_ids = [
    module.secrets.database_url_secret_id,
    google_secret_manager_secret.openai_api_key.secret_id,
    google_secret_manager_secret.email_webhook_secret.secret_id,
    google_secret_manager_secret.auth_token_secret.secret_id,
    google_secret_manager_secret.app_password.secret_id,
    google_secret_manager_secret.outlook_client_secret.secret_id,
    google_secret_manager_secret.outlook_refresh_token.secret_id,
  ]

  depends_on = [google_project_service.required]
}

# --- Cloud Run -----------------------------------------------------------

module "cloud_run" {
  source = "./modules/cloud_run"

  project_id            = var.project_id
  region                = var.region
  name                  = var.name
  image                 = "${var.region}-docker.pkg.dev/${var.project_id}/${module.artifact_registry.repository_id}/api:${var.backend_image_tag}"
  service_account_email = module.iam.cloud_run_service_account_email
  min_instances         = var.cloud_run_min_instances
  max_instances         = var.cloud_run_max_instances
  cpu                   = var.cloud_run_cpu
  memory                = var.cloud_run_memory
  vpc_connector_id      = module.network.vpc_connector_id
  labels                = local.labels

  env_vars = {
    QINORA_PERSISTENCE        = "postgres"
    QINORA_POSTGRES_TENANT_ID = var.postgres_tenant_id
    LLM_PROVIDER              = "openai"
    OPENAI_MODEL              = var.openai_model
    CORS_ALLOWED_ORIGINS      = var.cors_allowed_origins
  }

  secret_env_vars = {
    DATABASE_URL             = { secret_id = module.secrets.database_url_secret_id }
    OPENAI_API_KEY           = { secret_id = google_secret_manager_secret.openai_api_key.secret_id }
    EMAIL_WEBHOOK_SECRET     = { secret_id = google_secret_manager_secret.email_webhook_secret.secret_id }
    QINORA_AUTH_TOKEN_SECRET = { secret_id = google_secret_manager_secret.auth_token_secret.secret_id }
    QINORA_APP_PASSWORD      = { secret_id = google_secret_manager_secret.app_password.secret_id }
  }

  # secret_env_vars above only names the parent secret - Cloud Run resolves
  # "latest" at creation time, so it also needs the *version* resources to
  # exist first, which referencing only the secret's id doesn't guarantee.
  depends_on = [
    module.secrets,
    google_secret_manager_secret_version.openai_api_key,
    google_secret_manager_secret_version.email_webhook_secret,
    google_secret_manager_secret_version.auth_token_secret,
    google_secret_manager_secret_version.app_password,
  ]
}

# --- Frontend static site + external HTTPS load balancer ---------------------
# Routes app.qinora.se: /api/* to Cloud Run, everything else to the GCS
# bucket serving the React build. See modules/gcs_site and
# modules/load_balancer.

module "gcs_site" {
  source = "./modules/gcs_site"

  project_id = var.project_id
  name       = var.name
  location   = "EU"
  labels     = local.labels
}

# Scoped to just this bucket (not project-wide) - CI needs storage.admin
# here specifically because storage.objectAdmin alone lacks buckets.get,
# which `gcloud storage rsync` needs to list the bucket before syncing.
resource "google_storage_bucket_iam_member" "github_actions_frontend_deploy" {
  bucket = module.gcs_site.bucket_name
  role   = "roles/storage.admin"
  member = "serviceAccount:${module.iam.github_actions_service_account_email}"
}

module "load_balancer" {
  source = "./modules/load_balancer"

  project_id             = var.project_id
  region                 = var.region
  name                   = var.name
  domain_name            = var.domain_name
  cloud_run_service_name = module.cloud_run.service_name
  backend_bucket_id      = module.gcs_site.backend_bucket_id
  labels                 = local.labels
}

# --- Background workers (Cloud Run Jobs + Cloud Scheduler) --------------------
# GCP equivalent of infra/aws/ecs_workers.tf's ECS scheduled tasks. Each job
# runs the same backend image as the API, with the entrypoint overridden to
# one workers/*.py batch pass. Cloud Scheduler's minimum granularity is 1
# minute, so outbound-mailer moves from docker-compose's 30s poll to 60s -
# a small latency increase for sending already-queued emails, not a
# functional change.

locals {
  worker_image = "${var.region}-docker.pkg.dev/${var.project_id}/${module.artifact_registry.repository_id}/api:${var.backend_image_tag}"

  worker_env_vars = {
    QINORA_PERSISTENCE        = "postgres"
    QINORA_POSTGRES_TENANT_ID = var.postgres_tenant_id
  }

  worker_secret_env_vars = {
    DATABASE_URL = { secret_id = module.secrets.database_url_secret_id }
  }
}

module "outbound_mailer" {
  source = "./modules/scheduled_job"

  project_id            = var.project_id
  region                = var.region
  scheduler_region      = var.scheduler_region
  name                  = "${var.name}-outbound-mailer"
  image                 = local.worker_image
  args                  = ["python", "-m", "qinora.workers.outbound_mailer"]
  service_account_email = module.iam.cloud_run_service_account_email
  vpc_connector_id      = module.network.vpc_connector_id
  schedule              = "* * * * *" # every minute (was 30s in docker-compose)
  env_vars              = local.worker_env_vars
  secret_env_vars       = local.worker_secret_env_vars
  labels                = local.labels

  depends_on = [module.secrets]
}

module "tracking_simulator" {
  source = "./modules/scheduled_job"

  project_id            = var.project_id
  region                = var.region
  scheduler_region      = var.scheduler_region
  name                  = "${var.name}-tracking-simulator"
  image                 = local.worker_image
  args                  = ["python", "-m", "qinora.workers.tracking_simulator"]
  service_account_email = module.iam.cloud_run_service_account_email
  vpc_connector_id      = module.network.vpc_connector_id
  schedule              = "* * * * *" # every minute (matches docker-compose's 60s)
  env_vars              = local.worker_env_vars
  secret_env_vars       = local.worker_secret_env_vars
  labels                = local.labels

  depends_on = [module.secrets]
}

module "stale_request_escalator" {
  source = "./modules/scheduled_job"

  project_id            = var.project_id
  region                = var.region
  scheduler_region      = var.scheduler_region
  name                  = "${var.name}-stale-request-escalator"
  image                 = local.worker_image
  args                  = ["python", "-m", "qinora.workers.stale_request_escalator"]
  service_account_email = module.iam.cloud_run_service_account_email
  vpc_connector_id      = module.network.vpc_connector_id
  schedule              = "*/5 * * * *" # matches docker-compose's 300s
  env_vars              = local.worker_env_vars
  secret_env_vars       = local.worker_secret_env_vars
  labels                = local.labels

  depends_on = [module.secrets]
}

module "outlook_bridge" {
  source = "./modules/scheduled_job"

  project_id            = var.project_id
  region                = var.region
  scheduler_region      = var.scheduler_region
  name                  = "${var.name}-outlook-bridge"
  image                 = local.worker_image
  args                  = ["python", "-m", "qinora.workers.outlook_bridge"]
  service_account_email = module.iam.cloud_run_service_account_email
  vpc_connector_id      = module.network.vpc_connector_id
  schedule              = "* * * * *" # every minute (matches docker-compose's 60s)

  env_vars = merge(local.worker_env_vars, {
    QINORA_API_BASE_URL  = module.cloud_run.url
    OUTLOOK_TENANT_ID    = var.outlook_tenant_id
    OUTLOOK_CLIENT_ID    = var.outlook_client_id
    OUTLOOK_MAILBOXES    = var.outlook_mailboxes
    OUTLOOK_SEND_MAILBOX = var.outlook_send_mailbox
    OUTLOOK_SENDER_NAME  = var.outlook_sender_name
  })

  secret_env_vars = merge(local.worker_secret_env_vars, {
    OUTLOOK_CLIENT_SECRET = { secret_id = google_secret_manager_secret.outlook_client_secret.secret_id }
    OUTLOOK_REFRESH_TOKEN = { secret_id = google_secret_manager_secret.outlook_refresh_token.secret_id }
  })

  labels = local.labels

  depends_on = [
    module.secrets,
    google_secret_manager_secret_version.outlook_client_secret,
    google_secret_manager_secret_version.outlook_refresh_token,
  ]
}
