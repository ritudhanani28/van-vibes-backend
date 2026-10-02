from fastapi import APIRouter
from app.modules.notifications.apis import websocket_orders_endpoint

router = APIRouter(tags=["WebSocket"])

router.add_api_websocket_route("/ws/orders", websocket_orders_endpoint)
