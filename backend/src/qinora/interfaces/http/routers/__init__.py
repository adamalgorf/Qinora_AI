from qinora.interfaces.http.routers.agents import router as agents_router
from qinora.interfaces.http.routers.auth import router as auth_router
from qinora.interfaces.http.routers.carriers import router as carriers_router
from qinora.interfaces.http.routers.contacts import router as contacts_router
from qinora.interfaces.http.routers.dashboard import router as dashboard_router
from qinora.interfaces.http.routers.demo import router as demo_router
from qinora.interfaces.http.routers.health import router as health_router
from qinora.interfaces.http.routers.inbox import router as inbox_router
from qinora.interfaces.http.routers.outbound import router as outbound_router
from qinora.interfaces.http.routers.quotes import router as quotes_router
from qinora.interfaces.http.routers.rate_profiles import router as rate_profiles_router
from qinora.interfaces.http.routers.requests import router as requests_router
from qinora.interfaces.http.routers.search import router as search_router
from qinora.interfaces.http.routers.shipments import router as shipments_router
from qinora.interfaces.http.routers.webhooks import router as webhooks_router

routers = [
    health_router,
    auth_router,
    demo_router,
    dashboard_router,
    requests_router,
    search_router,
    quotes_router,
    shipments_router,
    carriers_router,
    contacts_router,
    inbox_router,
    agents_router,
    rate_profiles_router,
    webhooks_router,
    outbound_router,
]
