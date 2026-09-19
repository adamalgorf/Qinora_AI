# Qinora AI / QiNora TMS

Workflow-first Transport Management System for 4PL operators and freight forwarders. Qinora reads
incoming customer and carrier email, turns it into structured transport cases, sources carrier
prices, quotes the customer and follows the order through booking, delivery and invoice audit.

Production runs at **app.qinora.se** (Google Cloud, region `europe-north2`).

## How it works

The core product is a deterministic order-to-cash workflow with clean architecture boundaries.
AI is used only for narrow tasks (parsing free-text requests, reading carrier offers, interpreting
customer replies, analysing RFQs) and sits behind ports, so it can be swapped for a stub. Three
named agents do that work:

| Agent | Key | Job |
| --- | --- | --- |
| **Nora** | `request_parsing_agent` | Parses new inbound RFQ emails into a transport request |
| **Quinn** | `carrier_offer_agent` | Reads carrier replies to freight requests |
| **Orion** | `quote_response_agent` | Interprets the customer's reply to a quote |

A separate RFQ-analysis graph (`POST /rfq/analyze`) uses the same OpenAI client. Each agent can be
enabled/disabled, switched between manual / assisted / guarded-auto mode and given
a minimum confidence threshold from the **Automationer** page.

Typical email flow:

1. A mailbox bridge forwards inbound mail to `POST /webhooks/email` (HMAC-signed, idempotent).
2. Nora parses it into a case. Missing data creates a clarification request; unknown carriers'
   prices are sourced through automatic carrier RFQs (`sourcing` status).
3. A quote is created, sent to the customer (queued in the outbound queue) and Orion handles the reply
   (accepted / revised / rejected). Unknown senders who confirm an order are registered as customers.
4. Accepted quotes become shipments, which follow the shipment status machine to delivery and an
   invoice audit.

See [docs/architecture.md](docs/architecture.md) for layers and the dependency rule.

## Stack

- **Backend:** Python 3.12+, FastAPI, Pydantic v2, uvicorn. Persistence is raw SQL through psycopg 3
  (Postgres) with a parallel SQLite adapter for local dev, and plain numbered `.sql` migrations (no
  ORM). Passwords are hashed with bcrypt, quote PDFs are rendered in-process.
- **AI:** OpenAI API (`gpt-4o-mini` by default) for the agents, behind ports with a deterministic
  `stub` provider for local dev and tests. No Vertex AI/Bedrock and no agent framework.
- **Frontend:** TypeScript, React 19, Vite 7, Tailwind CSS 4, shadcn/Radix components, React Query,
  React Router 7, lucide icons. Font is Inter; colors are semantic HSL tokens in
  `frontend/src/app/styles.css`. Built with Node 24 in CI/Docker.
- **Mail:** Microsoft 365 / Outlook through Microsoft Graph (`workers/outlook_bridge.py`). The Gmail
  Apps Script bridge in `integrations/gmail-intake-bridge/` is legacy.
- **Production (Google Cloud only):** Cloud Run (API and worker jobs), Cloud SQL Postgres, Secret
  Manager, Artifact Registry, GCS + Cloud CDN for the static frontend, an external HTTPS load balancer
  with Cloud Armor, Cloud Scheduler, all defined in Terraform in `infra/gcp/`. CI/CD is GitHub Actions
  with Workload Identity Federation.
- **Local containers:** Docker Compose, with Nginx serving the frontend build.
- **Tests/lint:** pytest (with pytest-asyncio), ruff, `tsc` typecheck.

## Repository layout

```text
backend/            FastAPI app, workers, migrations, tests
  src/qinora/domain          pure business rules
  src/qinora/application     use cases and ports
  src/qinora/infrastructure  SQLite/Postgres, LLM adapters, PDF, settings
  src/qinora/interfaces/http routers, auth, container (composition root)
  src/qinora/workers         one-shot job entrypoints
  migrations/                numbered .sql migrations
frontend/           React operator UI (feature slices under src/features)
integrations/       mailbox bridges (Outlook/Microsoft 365, Gmail Apps Script)
infra/gcp/          Terraform for production
docs/               architecture notes
docker-compose.yml  local full stack
```

## Frontend pages

Overview, Inbox (Inkorg), Cases (Ärenden, incl. case detail), Quotes (Offerter, with quote detail and
PDF download), Automations (Automationer), Documents (Dokument), Customers (Kunder, with manual
create and CSV import), Analytics, Carriers (Transportörer) and Settings (profile). A login screen is
shown when the backend requires authentication.

## Run locally

### Backend

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn qinora.interfaces.http.app:app --reload
```

By default the API uses SQLite at `data/qinora.dev.sqlite3` (override with `QINORA_SQLITE_PATH`) and
the stub LLM provider, so it runs with no external services.

### Frontend

```powershell
npm install
npm.cmd run dev:web
```

The Vite dev server (http://localhost:5173) proxies `/api` to `http://127.0.0.1:8000`.

### Full stack with Docker

```powershell
docker compose up --build
```

The frontend is served at http://127.0.0.1:8080 (proxying `/api` to the backend) and the backend at
http://127.0.0.1:8000. `tracking-simulator` and `stale-request-escalator` run as looping services next
to it. For local Postgres:

```powershell
docker compose --profile postgres up --build
```

then set `QINORA_PERSISTENCE=postgres` and apply the migrations against that database.

To run the Outlook bridges too, fill in the `OUTLOOK_*` values in `.env` and use
`docker compose --profile outlook up`. See
[integrations/outlook-intake-bridge/README.md](integrations/outlook-intake-bridge/README.md).

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `QINORA_PERSISTENCE` | `sqlite` or `postgres` | `sqlite` |
| `DATABASE_URL` | Postgres connection string (required for `postgres`) | – |
| `QINORA_POSTGRES_TENANT_ID` | Tenant id used for tenant-scoped rows | fixed dev UUID |
| `QINORA_SQLITE_PATH` | SQLite file path | `data/qinora.dev.sqlite3` |
| `QINORA_AUTH_TOKEN_SECRET` | Signing secret for Bearer tokens – **set in production** | `dev-auth-secret` |
| `QINORA_REQUIRE_AUTH` | Force login on/off | on with Postgres, off with SQLite |
| `EMAIL_WEBHOOK_SECRET` | HMAC secret shared with the mailbox bridges – **set in production** | `dev-secret` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated allowed origins | `*` |
| `LLM_PROVIDER` | `stub` or `openai` | `stub` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Used when `LLM_PROVIDER=openai` | – / `gpt-4o-mini` |
| `QINORA_DEFAULT_MARKUP_PERCENT` | Default markup on carrier price | `10` |
| `QINORA_CUSTOMER_MAILBOX` / `QINORA_CARRIER_MAILBOX` | Sender mailboxes for customer / carrier mail | – |

## Database and migrations

Migrations live in `backend/migrations/` (`0001_initial.sql` … currently up to `0015`) and are
applied in order:

```powershell
cd backend
$env:DATABASE_URL="postgres://postgres:postgres@localhost:5432/qinora"
python -m qinora.infrastructure.migrations
```

In production a Cloud Run migration job runs them; it is re-run whenever a new file is added.

## Authentication and users

Login is per-user with roles (`shipper`, `carrier`, `4pl_tower`, `admin`, `superadmin`). Endpoints: `POST /auth/login`,
`GET /auth/me`, `POST /auth/change-password`, and user management under `/users` (admin only).
`POST /auth/dev-token` issues a local dev token and is for development only.

The first account cannot be created through the API (creating users needs a logged-in admin), so
bootstrap it from the CLI:

```powershell
cd backend
python -m qinora.infrastructure.bootstrap_admin --email you@example.com --full-name "Name" --password "<password>" --role admin
```

## Workers

Workers are one-shot entrypoints (`python -m qinora.workers.<name>`), run on a schedule in
production (Cloud Run Jobs + Cloud Scheduler) and in a loop in Docker Compose.

| Worker | Job |
| --- | --- |
| `outlook_bridge` | Forwards unread Outlook mail to `/webhooks/email`, sends queued outbound mail through Microsoft Graph and acks it back. **This is the real mail sender.** |
| `carrier_rfq_collector` | Sweeps sent carrier RFQs for replies (also triggered by the Outlook bridge on every pass via `/outbound/collect-carrier-rfqs`) |
| `tracking_simulator` | Advances in-transit shipments and creates invoice audits |
| `stale_request_escalator` | Escalates stale clarification requests into Control Tower tasks |
| `outbound_mailer` | **Test double only.** Marks queued mail as sent without delivering it. Never run it against real data next to the Outlook bridge |

> `docker-compose.yml` deliberately does not include `outbound_mailer`: running it next to the
> Outlook bridge silently swallows real customer emails. Note that `infra/gcp/main.tf` still defines a
> scheduled `outbound_mailer` job – see the comment in
> `backend/src/qinora/interfaces/http/routers/outbound.py` before keeping it enabled.

## API overview

Interactive docs are served by FastAPI at `/docs`. Main route groups:

- **Health / auth:** `/health`, `/ready`, `/auth/*`, `/users`
- **Work:** `/inbox/pending`, `/inbox/{id}`, `/requests` (incl. `/requests/parse`), `/cases`,
  `/cases/{id}`, `/cases/{id}/notes`, `/tasks`, `/search`
- **Quotes:** `/quotes`, `/quotes/{id}`, `/quotes/{id}/pdf`, `/quotes/{id}/send`,
  `/quotes/{id}/reply`, `/quotes/{id}/accept`
- **Shipments / invoices:** `/shipments`, `/shipments/{id}/status`, `/shipments/{id}/override`,
  `/shipments/{id}/timeline`, `/shipments/{id}/invoice`, `/invoices`
- **CRM:** `/contacts`, `/contacts/{id}`, `/contacts/import`
- **Carriers / pricing:** `/carriers`, `/carriers/intelligence`, `/rate-profiles`
- **Documents:** `/documents`, `/documents/{id}`, `/documents/{id}/content`
- **Automation / analytics:** `/automations`, `/agents/configs`, `/agents/{key}/config`,
  `/agents/logs`, `/analytics/summary`, `/dashboard/summary`
- **Email plumbing (HMAC-signed):** `/webhooks/email`, `/outbound/next-queued`,
  `/outbound/{queue}/{id}/ack`, `/outbound/{queue}/{id}/fail`, `/outbound/collect-carrier-rfqs`,
  `/emails/outbound`

`POST /demo/flow` still exists as a backend smoke-test endpoint that runs a request-to-invoice
scenario; it is no longer exposed in the UI.

## Verify

```powershell
cd backend
python -m ruff check .
python -m pytest

cd ..
npm.cmd run typecheck
npm.cmd run build
```

The same checks run in GitHub Actions (`ci.yml`).

## Deployment

Every push to `main` runs `.github/workflows/deploy-gcp.yml`:

1. Lint and test the backend.
2. Build the backend image, push it to Artifact Registry and deploy it to Cloud Run with 0% traffic.
3. Health-check the candidate revision, then promote it to 100% (automatic rollback on failure).
4. Build the frontend with `VITE_API_URL=/api`, sync it to the GCS bucket, set no-cache on
   `index.html` and invalidate the CDN.

The load balancer routes `/api/*` to Cloud Run and everything else to the static site. Infrastructure
is described in [infra/gcp/README.md](infra/gcp/README.md).
