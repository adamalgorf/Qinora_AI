from fastapi import APIRouter, HTTPException, status

from qinora.application import AuthContext, Role
from qinora.interfaces.http.auth import require_roles
from qinora.interfaces.http.container import AppContainer
from qinora.interfaces.http.dependencies import AUTH_CONTEXT, CONTAINER
from qinora.interfaces.http.schemas import RateProfileItem, RateProfilePayload

router = APIRouter()


@router.get("/rate-profiles", response_model=list[RateProfileItem])
async def list_rate_profiles(
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> list[RateProfileItem]:
    require_roles(context, Role.TOWER, Role.ADMIN, Role.SUPERADMIN)
    return [
        RateProfileItem(**item.__dict__)
        for item in await container.rate_profile_repository.list_all()
    ]


@router.post(
    "/rate-profiles",
    response_model=RateProfileItem,
    status_code=status.HTTP_201_CREATED,
)
async def create_rate_profile(
    payload: RateProfilePayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> RateProfileItem:
    require_roles(context, Role.ADMIN, Role.SUPERADMIN)
    created = await container.rate_profile_repository.create(
        mode=payload.mode,
        origin=payload.origin,
        destination=payload.destination,
        base_price=payload.base_price,
        price_per_kg=payload.price_per_kg,
        currency=payload.currency,
    )
    return RateProfileItem(**created.__dict__)


@router.post("/rate-profiles/{rate_profile_id}", response_model=RateProfileItem)
async def update_rate_profile(
    rate_profile_id: str,
    payload: RateProfilePayload,
    container: AppContainer = CONTAINER,
    context: AuthContext = AUTH_CONTEXT,
) -> RateProfileItem:
    require_roles(context, Role.ADMIN, Role.SUPERADMIN)
    try:
        updated = await container.rate_profile_repository.update(
            rate_profile_id,
            mode=payload.mode,
            origin=payload.origin,
            destination=payload.destination,
            base_price=payload.base_price,
            price_per_kg=payload.price_per_kg,
            currency=payload.currency,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return RateProfileItem(**updated.__dict__)
