from fastapi import APIRouter, HTTPException, status

from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import CONTAINER

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(container: AppContainer = CONTAINER) -> dict[str, str]:
    try:
        with container.database.connect() as connection:
            cursor = connection.execute("select 1")
            cursor.fetchone()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistence adapter is not ready",
        ) from error

    return {
        "status": "ready",
        "persistence": container.settings.persistence_driver.value,
    }
