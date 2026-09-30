import json
from typing import Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.websocket.manager import ws_manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/orders")
async def websocket_orders_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    table_id: Optional[str] = Query(None),
):
    """
    Real-time WebSocket endpoint for order events and kitchen display notifications.
    Supports authenticated Admin & Chef sockets, as well as table-specific live guest streams.
    """
    role = "GUEST"
    identifier = table_id or "anonymous"

    if token:
        try:
            payload = decode_access_token(token)
            role = payload.get("role", "GUEST").upper()
            identifier = payload.get("sub", identifier)
        except Exception:
            role = "GUEST"
    elif table_id:
        role = "TABLE"
        identifier = table_id

    await ws_manager.connect(websocket, role=role, identifier=identifier)

    try:
        while True:
            # Keep socket alive and receive client messages / pings
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action")
                if action == "PING":
                    await websocket.send_text(json.dumps({"event": "PONG"}))
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)
