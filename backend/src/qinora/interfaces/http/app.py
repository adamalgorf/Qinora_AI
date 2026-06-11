from fastapi import FastAPI

from qinora.interfaces.http.container import build_container
from qinora.interfaces.http.routers import routers


def create_app() -> FastAPI:
    app = FastAPI(title="QiNora TMS API", version="0.1.0")
    app.state.container = build_container()

    for router in routers:
        app.include_router(router)

    return app
