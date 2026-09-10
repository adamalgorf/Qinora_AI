# Qinora on GCP — Terraform

Terraform for running Qinora on Google Cloud: Cloud Run (FastAPI), Cloud SQL
(Postgres, private IP), a GCS + Cloud CDN static site for the React build,
and an external HTTPS load balancer with Cloud Armor routing `/api/*` to
Cloud Run and everything else to the static site, fronting **app.qinora.se**.

This design was consolidated from two Claude sessions working on this repo
in parallel — see git history / session notes if the "why" behind a specific
choice (e.g. secrets declared inline in `main.tf` rather than a generic
`modules/secrets` map) looks surprising.

This lives alongside `infra/aws/`, which has a real, previously-applied
deployment (`terraform.tfstate` present). **Do not delete `infra/aws/`**
until this GCP stack is live and verified — and when you do, `terraform
destroy` it first so you don't leave billed AWS resources running with no
IaC tracking them.

## Corrections from the original spec

- **Region**: `eu-north1` is AWS's Stockholm code. GCP's equivalent is
  **`europe-north2`** (Stockholm); `europe-north1` is Finland.
- **Cloud SQL tier**: there's no `db-e2-micro` Cloud SQL tier (`e2-micro` is a
  Compute Engine machine type). The shared-core, dev-friendly Cloud SQL tier
  is **`db-f1-micro`**, used here.
- **Cloud Run scaling**: Cloud Run instance counts are whole numbers, so
  "0.25–4 instances" is interpreted as **min 0 (scale-to-zero), max 4**.
- **LLM provider**: the original spec assumed Vertex AI, but
  `backend/src/qinora/infrastructure/llm/` only has OpenAI and stub
  implementations — no Vertex AI integration exists in the codebase. This
  stack wires up **OpenAI** (`LLM_PROVIDER=openai`, `OPENAI_API_KEY` secret)
  to match the real code. Building a Vertex AI backend would be a separate
  application-code task, not an infra one.

## Layout

```
infra/gcp/
  backend.tf              # GCS remote state backend
  variables.tf
  main.tf                 # wires modules together, enables required APIs
  outputs.tf
  terraform.tfvars.example
  modules/
    network/              # VPC, private services access, Serverless VPC connector
    cloud_sql/             # Postgres, private IP only
    secrets/               # Secret Manager (DATABASE_URL only - see main.tf)
    artifact_registry/     # Docker repo for backend images
    iam/                   # Cloud Run SA + GitHub Actions SA via Workload Identity Federation
    cloud_run/              # FastAPI service
    gcs_site/               # React static site bucket + CDN backend bucket
    load_balancer/          # External HTTPS LB, URL map, Cloud Armor, managed cert
    scheduled_job/          # Cloud Run Job + Cloud Scheduler, one instance per background worker
```

`OPENAI_API_KEY`, `EMAIL_WEBHOOK_SECRET`, and `QINORA_AUTH_TOKEN_SECRET` are
declared directly as `google_secret_manager_secret` resources in root
`main.tf` rather than through `modules/secrets`, since growing that module's
interface for 3 more call sites wasn't worth it. `DATABASE_URL` goes through
the module since it's derived (see below), not passed straight from a
variable.

## Background workers

Your docker-compose runs 4 background workers as `while true; do python -m
qinora.workers.X; sleep N; done` loops. The GCP equivalent of AWS's ECS
scheduled tasks (`infra/aws/ecs_workers.tf`) is **Cloud Run Jobs + Cloud
Scheduler** (`modules/scheduled_job`, instantiated once per worker in
`main.tf`): each job runs the same backend image with its entrypoint
overridden to one `workers/*.py` batch pass, triggered on a cron schedule.

Cloud Scheduler's minimum granularity is 1 minute, so `outbound-mailer`
moves from a 30s poll to 60s — already-queued emails go out up to 30s later
than before, not a functional change. `tracking-simulator` and
`outlook-bridge` (60s) and `stale-request-escalator` (5 min) keep their
existing cadence exactly.

`outlook-bridge` needs `outlook_tenant_id`/`outlook_client_id` plus either
`outlook_client_secret` (application auth) or `outlook_refresh_token`
(delegated auth, from `python -m qinora.workers.outlook_bridge login`) — see
`integrations/outlook-intake-bridge/README.md`. Leave them at their
`"not-configured"` default (Secret Manager rejects an empty payload, so a
real blank isn't an option) to deploy anyway; the job will just fail on
each run (harmlessly — no monitoring/alerting is wired up, per scope) until
you fill them in, which needs no infra change, just updating the secret
values and letting the next scheduled run pick them up.

## Prerequisites

1. A GCP project with billing enabled.
2. `gcloud` and `terraform` (>= 1.9) installed and authenticated:
   ```bash
   gcloud auth application-default login
   gcloud config set project <your-project-id>
   ```
3. A GCS bucket for Terraform state (create once, outside Terraform):
   ```bash
   gcloud storage buckets create gs://<your-project-id>-tfstate \
     --location=EU --uniform-bucket-level-access
   gcloud storage buckets update gs://<your-project-id>-tfstate --versioning
   ```
4. Control over `qinora.se`'s DNS, to point `app.qinora.se` at the load
   balancer's IP once it's created (needed for the managed SSL certificate
   to provision).
5. An OpenAI API key.

## First-time setup

Cloud Run needs an image to exist in Artifact Registry *before* it can be
created, but Artifact Registry doesn't exist until Terraform creates it —
so the very first apply is two steps:

```bash
cd infra/gcp
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: project_id, domain_name, etc.

export TF_VAR_openai_api_key="sk-..."
export TF_VAR_email_webhook_secret="$(openssl rand -hex 32)"
export TF_VAR_auth_token_secret="$(openssl rand -hex 32)"
# Optional - see "Background workers" below. Safe to leave unset for now.
# export TF_VAR_outlook_client_secret="..."
# export TF_VAR_outlook_refresh_token="..."

terraform init -backend-config="bucket=<your-project-id>-tfstate"

# Step 1: create everything except Cloud Run (which needs a real image).
terraform apply -target=module.artifact_registry

# Push a bootstrap image so Cloud Run has something to point at.
gcloud auth configure-docker europe-north2-docker.pkg.dev
docker build -t europe-north2-docker.pkg.dev/<project-id>/qinora-backend/api:bootstrap ./backend
docker push europe-north2-docker.pkg.dev/<project-id>/qinora-backend/api:bootstrap

# Step 2: everything else, including Cloud Run.
terraform apply
```

After `apply`, point `app.qinora.se`'s DNS A record at the `load_balancer_ip`
output. The Google-managed SSL certificate stays in `PROVISIONING` until DNS
resolves correctly; this can take up to ~60 minutes.

Run database migrations against the new Cloud SQL instance once (see
`backend/migrations` / `backend/src/qinora/infrastructure/migrations.py`) —
either from a one-off Cloud Run job with the VPC connector attached, or via
`cloud-sql-proxy` from your machine using the `cloud_sql_instance_connection_name`
output.

## Deploying the frontend

The static site bucket has no CI wiring here since none was requested;
build and sync the React app from your GitHub Actions workflow, e.g.:

```bash
gcloud storage rsync ./frontend/dist gs://<frontend_bucket_name> --delete-unmatched-destination-objects
# Long-cache hashed assets, short/no-cache the HTML entry point:
gcloud storage objects update "gs://<frontend_bucket_name>/**" --cache-control="public,max-age=31536000,immutable"
gcloud storage objects update "gs://<frontend_bucket_name>/index.html" --cache-control="no-cache"
```

## Deploying the backend from GitHub Actions

`.github/workflows/deploy-gcp.yml` already exists and is design-agnostic —
it does a 0%-traffic canary deploy, health-checks `/ready`, promotes on
success, and rolls back on failure. It expects these **GitHub repo
variables** (Settings → Secrets and variables → Actions → Variables), which
map directly to this stack's outputs:

| GitHub variable               | Terraform output                       |
| ------------------------------ | --------------------------------------- |
| `GCP_PROJECT_ID`               | `var.project_id`                        |
| `GCP_REGION`                   | `var.region`                            |
| `GCP_ARTIFACT_REPOSITORY`      | `artifact_registry_repository_id`       |
| `GCP_SERVICE`                  | `cloud_run_service_name`                |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `workload_identity_provider`          |
| `GCP_SERVICE_ACCOUNT`          | `github_actions_service_account_email`  |

No long-lived service account key is created or needed — GitHub Actions
authenticates via Workload Identity Federation (OIDC), scoped to this repo
only.

## IAM summary

- **Cloud Run runtime SA**: `roles/cloudsql.client` and
  `roles/secretmanager.secretAccessor` scoped to only its 4 secrets — not
  project-wide. No Vertex AI role (unused — see "Corrections" above).
- **GitHub Actions deploy SA**: `roles/artifactregistry.writer`,
  `roles/run.developer`, and `roles/iam.serviceAccountUser` on the Cloud Run
  SA (needed to deploy revisions running as it). Bound to this repo only via
  Workload Identity Federation's `attribute_condition`.

## What's intentionally not here

Per the original scope: no monitoring/alerting stack and no multi-environment
(staging/prod) split — this is one environment in one region.
