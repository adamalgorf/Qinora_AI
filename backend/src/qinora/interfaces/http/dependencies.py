from fastapi import Depends, Request

from qinora.application import AuthContext
from qinora.interfaces.http.auth import get_auth_context
from qinora.interfaces.http.container import AppContainer


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


CONTAINER = Depends(get_container)
AUTH_CONTEXT = Depends(get_auth_context)

ContainerDep = AppContainer
AuthDep = AuthContext
