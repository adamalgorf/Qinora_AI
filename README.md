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

## Run Frontend

```powershell
npm install
npm.cmd run dev:web
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`.

## Verify

```powershell
cd backend
python -m ruff check .
python -m pytest

cd ..
npm.cmd run typecheck
npm.cmd run build
```
