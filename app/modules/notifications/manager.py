import asyncio
import json
from typing import Any, Dict, List, Optional
from fastapi import WebSocket
from logger_manager import LoggerManager

ws_logger = LoggerManager(folder_name="websocket")


class ConnectionManager:
    """Manages active WebSocket connections for Admin, Chef, and Customer Table clients."""

    def __init__(self):
        self.active_connections: Dict[WebSocket, Dict[str, Any]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        role: str = "GUEST",
        identifier: str = "",
    ):
        await websocket.accept()
        self.active_connections[websocket] = {
            "role": role.upper(),
            "identifier": identifier,
        }
        ws_logger.info(
            "WebSocket connected: role=%s, id=%s (Total active: %d)",
            role,
            identifier,
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            meta = self.active_connections.pop(websocket)
            ws_logger.info(
                "WebSocket disconnected: role=%s, id=%s (Remaining: %d)",
                meta.get("role"),
                meta.get("identifier"),
                len(self.active_connections),
            )

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        try:
            await websocket.send_text(json.dumps(message))
        except Exception as exc:
            ws_logger.warning("Failed to send message to socket: %s", exc)
            self.disconnect(websocket)

    async def broadcast_event(
        self,
        event_type: str,
        admin_payload: Dict[str, Any],
        chef_payload: Optional[Dict[str, Any]] = None,
        table_id: Optional[str] = None,
    ):
        """Broadcast events with strict role-specific payload sanitization."""
        if chef_payload is None:
            chef_payload = admin_payload

        dead_connections: List[WebSocket] = []

        for ws, meta in list(self.active_connections.items()):
            role = meta.get("role")
            identifier = meta.get("identifier")

            try:
                if role == "ADMIN":
                    await ws.send_text(
                        json.dumps({"event": event_type, "data": admin_payload})
                    )
                elif role == "CHEF":
                    await ws.send_text(
                        json.dumps({"event": event_type, "data": chef_payload})
                    )
                elif event_type.startswith("MENU_"):
                    await ws.send_text(
                        json.dumps({"event": event_type, "data": chef_payload})
                    )
                elif (role == "TABLE" or role == "GUEST") and (not table_id or identifier in [table_id, "anonymous"]):
                    await ws.send_text(
                        json.dumps({"event": event_type, "data": chef_payload})
                    )
            except Exception as exc:
                ws_logger.warning("Error broadcasting to socket: %s", exc)
                dead_connections.append(ws)

        for ws in dead_connections:
            self.disconnect(ws)

    async def notify_order_placed(
        self,
        admin_order: Dict[str, Any],
        chef_order: Dict[str, Any],
        table_id: Optional[str],
    ):
        await self.broadcast_event(
            event_type="ORDER_PLACED",
            admin_payload=admin_order,
            chef_payload=chef_order,
            table_id=table_id,
        )

    async def notify_order_accepted(
        self,
        order_id: str,
        table_id: Optional[str],
        updated_at: str,
    ):
        payload = {
            "order_id": order_id,
            "orderId": order_id,
            "status": "ACCEPTED",
            "table_id": table_id,
            "tableId": table_id,
            "updated_at": updated_at,
            "updatedAt": updated_at,
        }
        await self.broadcast_event(
            event_type="ORDER_ACCEPTED",
            admin_payload=payload,
            chef_payload=payload,
            table_id=table_id,
        )

    async def notify_order_served(
        self,
        order_id: str,
        table_id: Optional[str],
        updated_at: str,
    ):
        payload = {
            "order_id": order_id,
            "orderId": order_id,
            "status": "SERVED",
            "table_id": table_id,
            "tableId": table_id,
            "updated_at": updated_at,
            "updatedAt": updated_at,
        }
        await self.broadcast_event(
            event_type="ORDER_SERVED",
            admin_payload=payload,
            chef_payload=payload,
            table_id=table_id,
        )

    async def notify_order_completed(
        self,
        order_id: str,
        table_id: Optional[str],
        updated_at: str,
    ):
        payload = {
            "order_id": order_id,
            "orderId": order_id,
            "status": "COMPLETED",
            "table_id": table_id,
            "tableId": table_id,
            "updated_at": updated_at,
            "updatedAt": updated_at,
        }
        await self.broadcast_event(
            event_type="ORDER_COMPLETED",
            admin_payload=payload,
            chef_payload=payload,
            table_id=table_id,
        )

    async def notify_order_status_updated(
        self,
        order_id: str,
        new_status: str,
        table_id: Optional[str],
        updated_at: str,
    ):
        payload = {
            "order_id": order_id,
            "orderId": order_id,
            "status": new_status,
            "table_id": table_id,
            "tableId": table_id,
            "updated_at": updated_at,
            "updatedAt": updated_at,
        }
        await self.broadcast_event(
            event_type="ORDER_STATUS_UPDATED",
            admin_payload=payload,
            chef_payload=payload,
            table_id=table_id,
        )

    async def notify_payment_settled(
        self,
        order_id: str,
        table_id: Optional[str],
        invoice_number: str,
        payment_method: str,
    ):
        payload = {
            "orderId": order_id,
            "tableId": table_id,
            "invoiceNumber": invoice_number,
            "paymentStatus": "PAID",
            "paymentMethod": payment_method,
        }
        await self.broadcast_event(
            event_type="PAYMENT_SETTLED",
            admin_payload=payload,
            chef_payload=payload,
            table_id=table_id,
        )

    async def notify_table_status_updated(self, table_id: str, new_status: str):
        payload = {"tableId": table_id, "status": new_status}
        await self.broadcast_event(
            event_type="TABLE_STATUS_UPDATED",
            admin_payload=payload,
            chef_payload=payload,
            table_id=table_id,
        )

    async def notify_menu_updated(self, item_data: Dict[str, Any]):
        await self.broadcast_event(
            event_type="MENU_ITEM_UPDATED",
            admin_payload=item_data,
            chef_payload=item_data,
        )

    async def notify_menu_availability_changed(self, item_id: str, is_available: bool):
        payload = {"itemId": item_id, "id": item_id, "isAvailable": is_available}
        await self.broadcast_event(
            event_type="MENU_AVAILABILITY_CHANGED",
            admin_payload=payload,
            chef_payload=payload,
        )

    notify_menu_availability = notify_menu_availability_changed

    async def notify_menu_item_deleted(self, item_id: str):
        payload = {"itemId": item_id, "id": item_id}
        await self.broadcast_event(
            event_type="MENU_ITEM_DELETED",
            admin_payload=payload,
            chef_payload=payload,
        )

    async def notify_bill_generated(self, table_id: str, session_id: str):
        payload = {"tableId": table_id, "sessionId": session_id, "status": "BILL_GENERATED"}
        await self.broadcast_event(
            event_type="BILL_GENERATED",
            admin_payload=payload,
            chef_payload=payload,
            table_id=table_id,
        )


ws_manager = ConnectionManager()
