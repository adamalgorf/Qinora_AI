# AWS migration runbook

Steps for cutting QInora over from Render/Supabase to AWS (Terraform in
`infra/aws/`). The steps below touch billing, IAM trust, and production data
- run them yourself rather than delegating them, for the same reason
`render.yaml`'s `DATABASE_URL`/`OPENAI_API_KEY` were always filled in by hand
rather than committed.

## 1. Account and access

1. Create the AWS account (or use the one you just created) and enable MFA on
   the root user.
2. Create an IAM user (or role, if you use SSO) with permissions to run
   Terraform - `AdministratorAccess` is the fast path for a first cutover;
   scope it down once the infra is stable.
3. Set up an OIDC identity provider + IAM role for GitHub Actions
   (`token.actions.githubusercontent.com`, trust policy restricted to this
   repo's `main` branch) so `.github/workflows/deploy-aws.yml` can assume it
   without long-lived access keys. AWS's own guide:
   "Configuring OpenID Connect in Amazon Web Services" in the GitHub Actions
   docs covers the exact trust policy JSON.
4. In the repo's GitHub Actions settings, add these as **variables** (not
   secrets - they're not sensitive, just identifiers) once step 2 below has
   produced them: `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`,
   `BACKEND_ECR_REPOSITORY_URL`, `FRONTEND_ECR_REPOSITORY_URL`,
   `BACKEND_API_URL`, `BACKEND_APPRUNNER_SERVICE_ARN`,
   `FRONTEND_APPRUNNER_SERVICE_ARN`.

## 2. Provision the infrastructure

```bash
cd infra/aws
terraform init
terraform apply \
  -var="db_password=<choose one, save it in a password manager>" \
  -var="openai_api_key=<from your OpenAI account>" \
  -var="email_webhook_secret=<generate, e.g. openssl rand -hex 32>" \
  -var="auth_token_secret=<generate, e.g. openssl rand -hex 32>"
```

This is a **billed** step - review the plan Terraform prints before typing
`yes`. It creates: a small VPC, an RDS Postgres instance, two ECR repos, two
App Runner services, an ECS Fargate cluster + 3 worker task definitions, and
3 EventBridge Scheduler rules. The App Runner services will fail to start
until step 3 pushes real images - that's expected on the first apply.

Note the outputs (`backend_ecr_repository_url`, `frontend_ecr_repository_url`,
`rds_endpoint`, `backend_url`, `frontend_url`) - you'll need them for the
GitHub Actions variables above and for step 4.

## 3. First image push (manual, before CI takes over)

```bash
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com

docker build -t <backend_ecr_repository_url>:latest backend/
docker push <backend_ecr_repository_url>:latest

docker build -f frontend/Dockerfile --build-arg VITE_API_URL=<backend_url> -t <frontend_ecr_repository_url>:latest .
docker push <frontend_ecr_repository_url>:latest
```

Then, in the AWS Console (App Runner), manually trigger a deployment for both
services once, or re-run `terraform apply` (it will notice the services exist
and just confirm no drift). After this, `deploy-aws.yml` handles every future
push to `main`.

## 4. Apply the schema to RDS

```bash
cd backend
QINORA_PERSISTENCE=postgres \
DATABASE_URL="postgres://qinora_admin:<db_password>@<rds_endpoint>/qinora?sslmode=require" \
python -m qinora.infrastructure.migrations
```

Confirms the 9 migrations apply cleanly before any real data is involved.

## 5. Data cutover (touches production data - take a fresh Supabase backup first)

```bash
pg_dump "<current Supabase DATABASE_URL>" --format=custom --file=qinora.dump
pg_restore --dbname "postgres://qinora_admin:<db_password>@<rds_endpoint>/qinora?sslmode=require" qinora.dump
```

Do this during a short maintenance window - inbound emails/webhooks landing
between the dump and the DNS/traffic cutover (step 7) would be missed.

## 6. Smoke test

Hit `<backend_url>/health`, `<backend_url>/ready`, `POST <backend_url>/demo/flow`,
and load `<frontend_url>` end to end before touching DNS. Check the
CloudWatch log group `/ecs/qinora-workers` after a few minutes to confirm the
three scheduled worker tasks are running successfully.

## 7. DNS cutover - app.qinora.se

The app is meant to live at the `app.qinora.se` subdomain, not the bare
domain. `serverHold` is a registry-level flag on the whole `qinora.se` zone,
so it blocks every subdomain too, including `app.qinora.se` - this still
needs the earlier GoDaddy/.SE issue resolved first. Once it resolves:

1. In the App Runner console, add `app.qinora.se` as a custom domain on the
   **frontend** service.
2. App Runner will give you a CNAME/validation record - add it in GoDaddy's
   DNS panel under the `app` subdomain (no need to move DNS management off
   GoDaddy, and no change needed to the bare `qinora.se` record itself).
3. Wait for the custom domain's status to flip to "Active" before relying on
   it.
4. Update `CORS_ALLOWED_ORIGINS` (infra/aws/apprunner.tf currently points it
   at the frontend's default `*.awsapprunner.com` URL) to `https://app.qinora.se`
   once the custom domain is active, and re-apply.

## 8. Decommission Render

Only after the above is verified working end-to-end: delete the Render
services, remove `render.yaml`, and delete
`.github/workflows/keep-alive.yml` (it exists purely to dodge Render's
free-tier cold starts and has no equivalent need on App Runner).
