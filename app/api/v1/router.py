from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    billing,
    categories,
    dashboard,
    dining_sessions,
    health,
    menu,
    orders,
    settings,
    tables,
    ws,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(categories.router)
api_router.include_router(menu.router)
api_router.include_router(tables.router)
api_router.include_router(dining_sessions.router)
api_router.include_router(orders.router)
api_router.include_router(billing.router)
api_router.include_router(dashboard.router)
api_router.include_router(settings.router)
api_router.include_router(ws.router)
