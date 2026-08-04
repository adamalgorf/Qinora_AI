from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qinora.interfaces.http.container import build_container
from qinora.interfaces.http.routers import routers


def create_app() -> FastAPI:
    app = FastAPI(title="QiNora TMS API", version="0.1.0")
    container = build_container()
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(container.settings.cors_allowed_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in routers:
        app.include_router(router)

    return app


app = create_app()
