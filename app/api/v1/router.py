from fastapi import APIRouter

from app.modules.health.router import router as health_router
from app.modules.accounts.router import router as auth_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.menu.router import categories_router, menu_router
from app.modules.notifications.router import router as ws_router
from app.modules.orders.router import router as orders_router
from app.modules.sessions.router import billing_router, dining_sessions_router
from app.modules.settings.router import router as settings_router
from app.modules.tables.router import router as tables_router
from app.modules.export.router import router as export_router

api_router = APIRouter()

# Health check
api_router.include_router(health_router)

# Domain Modules
api_router.include_router(auth_router)
api_router.include_router(categories_router)
api_router.include_router(menu_router)
api_router.include_router(tables_router)
api_router.include_router(dining_sessions_router)
api_router.include_router(orders_router)
api_router.include_router(billing_router)
api_router.include_router(dashboard_router)
api_router.include_router(settings_router)
api_router.include_router(ws_router)
api_router.include_router(export_router)
