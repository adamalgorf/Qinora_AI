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

## Test

```powershell
cd backend
python -m pytest
```
