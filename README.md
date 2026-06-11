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
python -m uvicorn qinora.interfaces.http.app:create_app --factory --reload
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

## Run Frontend

```powershell
npm install
npm.cmd run dev:web
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.

## API Modules

- `GET /dashboard/summary`
- `GET /requests`
- `GET /quotes`
- `GET /shipments`
- `GET /carriers`
- `POST /carriers/intelligence`
- `GET /inbox/pending`
- `GET /agents/logs`
- `POST /webhooks/email`

## Verify

```powershell
cd backend
python -m ruff check .
python -m pytest

cd ..
npm.cmd run typecheck
npm.cmd run build
```
