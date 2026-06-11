# QiNora Backend

Python backend for the QiNora TMS.

## Run

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn qinora.interfaces.http.app:app --reload
```

Set `QINORA_AUTH_TOKEN_SECRET` outside local development. Bearer tokens are verified at the HTTP
boundary and converted into the application `AuthContext`.

## Persistence

SQLite is the default local adapter. Set `QINORA_PERSISTENCE=postgres` and `DATABASE_URL` to use
the Postgres adapter behind the same application repository ports.

```powershell
cd backend
$env:DATABASE_URL="postgres://postgres:postgres@localhost:5432/qinora"
python -m qinora.infrastructure.migrations
```

## Test

```powershell
cd backend
python -m pytest
```
