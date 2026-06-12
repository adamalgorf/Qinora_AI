# Qinora AI / QiNora TMS

AI-driven Transport Management System for 4PL operators and freight forwarders.

## Stack

- Backend: Python, FastAPI, Pydantic v2, clean architecture
- Frontend: TypeScript, React, Vite, React Query
- UI: shadcn-style local components with Tailwind CSS v4
- Tests: pytest, ruff, TypeScript build

## Run Backend

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn qinora.interfaces.http.app:app --reload
```

## Database

The first Postgres/Supabase migration lives in:

```text
backend/migrations/0001_initial.sql
```

It defines the tenant-scoped core schema, operational indexes, shipment status trigger, webhook
idempotency table and RLS enablement. The current API uses a seed adapter while the Postgres
repository adapter is wired in.

For local development, the API also boots a SQLite adapter at `data/qinora.dev.sqlite3` by
default. Override it with `QINORA_SQLITE_PATH`.

Set `QINORA_AUTH_TOKEN_SECRET` for signed Bearer tokens. The development UI can issue a local
dev token through `POST /auth/dev-token`; production auth can replace that endpoint without
changing the RBAC use cases.

Set `QINORA_PERSISTENCE=postgres` with `DATABASE_URL` to run the API against Postgres. Apply
migrations first:

```powershell
cd backend
$env:DATABASE_URL="postgres://postgres:postgres@localhost:5432/qinora"
python -m qinora.infrastructure.migrations
```

## Run Frontend

```powershell
npm install
npm.cmd run dev:web
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.

## Run Workers

Process queued outbound customer replies:

```powershell
cd backend
python -m qinora.workers.outbound_mailer
```

Run the tracking simulator, which advances in-transit shipments and creates invoice audits:

```powershell
cd backend
python -m qinora.workers.tracking_simulator
```

Escalate stale clarification requests into Control Tower tasks:

```powershell
cd backend
python -m qinora.workers.stale_request_escalator
```

## Run Full Stack With Docker

```powershell
docker compose up --build
```

The containerized frontend is served at `http://127.0.0.1:8080` and proxies `/api` to the
backend service. The backend remains reachable at `http://127.0.0.1:8000`.

To run a local Postgres service for production-style persistence:

```powershell
docker compose --profile postgres up --build
```

Then set `QINORA_PERSISTENCE=postgres` and run the migrations against the compose Postgres URL
before starting the backend against that database.

## API Modules

- `GET /dashboard/summary`
- `GET /requests`
- `GET /contacts`
- `GET /quotes`
- `GET /quotes/{id}`
- `GET /shipments`
- `POST /shipments/{id}/override`
- `GET /carriers`
- `POST /carriers/intelligence`
- `GET /inbox/pending`
- `GET /agents/logs`
- `GET /agents/configs`
- `POST /agents/{key}/config`
- `POST /webhooks/email`
- `GET /auth/me`
- `POST /auth/dev-token`
- `GET /emails/outbound`
- `POST /emails/outbound/process`
- `POST /shipments/tracking-simulator/run`

## Verify

```powershell
cd backend
python -m ruff check .
python -m pytest

cd ..
npm.cmd run typecheck
npm.cmd run build
```
