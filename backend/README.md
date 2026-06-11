# QiNora Backend

Python backend for the QiNora TMS.

## Run

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m uvicorn qinora.interfaces.http.app:create_app --factory --reload
```

## Test

```powershell
cd backend
python -m pytest
```
