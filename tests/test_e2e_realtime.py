import uuid
import asyncio
import json
import pytest
import websockets
import httpx

BASE_URL = "http://127.0.0.1:8000/api/v1"
WS_URL = "ws://127.0.0.1:8000/api/v1/ws/orders"

@pytest.mark.asyncio
async def test_full_e2e_flow_with_websocket():
    from app.db.session import SessionLocal
    from app.models.table import Table
    from app.models.dining_session import DiningSession
    with SessionLocal() as _db:
        for _s in _db.query(DiningSession).filter(DiningSession.table_id == 'T09').all():
            _s.status = 'CLOSED'
            for _o in _s.orders:
                _o.payment_status = 'PAID'
        for _t in _db.query(Table).filter(Table.id == 'T09').all():
            _t.status = 'AVAILABLE'
        _db.commit()
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        # 1. Login as Admin
        admin_login_res = await client.post(
            "/auth/login",
            json={"email": "admin@vaanvibes.com", "password": "admin123"},
        )
        assert admin_login_res.status_code == 200
        admin_token = admin_login_res.json()["access_token"]

        # 2. Login as Chef
        chef_login_res = await client.post(
            "/auth/login",
            json={"email": "chef@vaanvibes.com", "password": "chef123"},
        )
        assert chef_login_res.status_code == 200
        chef_token = chef_login_res.json()["access_token"]

        # 3. Test Backend QR Code generation
        qr_res = await client.get("/tables/T09/qr")
        assert qr_res.status_code == 200
        assert qr_res.headers["content-type"] == "image/png"
        # Validate PNG header bytes
        assert qr_res.content[:8] == b"\x89PNG\r\n\x1a\n"
        print("\n[OK] Backend QR generation validated (PNG magic bytes verified)")

        # 4. Connect WebSockets for Admin and Chef
        async with websockets.connect(f"{WS_URL}?token={admin_token}") as admin_ws, \
                   websockets.connect(f"{WS_URL}?token={chef_token}") as chef_ws:

            # 5. Place Customer Order for Table T09
            tbl_res = await client.get("/tables/T09")
            assert tbl_res.status_code == 200
            table9 = tbl_res.json()

            order_payload = {
                "tableId": "T09",
                "token": table9["token"],
                "sessionToken": f"sess_e2e_{uuid.uuid4().hex[:8]}",
                "customerName": "Simran Kaur",
                "customerMobile": "9812345678",
                "specialInstructions": "Extra foam",
                "items": [
                    {
                        "menuItemId": "hc-03",
                        "name": "Cappuccino",
                        "quantity": 1,
                    },
                    {
                        "menuItemId": "to-03",
                        "name": "Avocado Toast",
                        "quantity": 1,
                    },
                ],
            }

            create_res = await client.post("/orders", json=order_payload)
            assert create_res.status_code == 201
            order_data = create_res.json()
            order_id = order_data["id"]
            # 160 + 390 = 550 subtotal; Tax removed = 0.0; total = 550.0
            assert order_data["subtotal"] == 550.0
            assert order_data["tax"] == 0.0
            assert order_data["total"] == 550.0
            print(f"[OK] Customer Order placed: {order_id} (Subtotal: 550, Tax: 0.0, Total: 550.0)")

            # 6. Receive WebSocket Event on Admin Socket
            while True:
                admin_msg_raw = await asyncio.wait_for(admin_ws.recv(), timeout=5.0)
                admin_event = json.loads(admin_msg_raw)
                if admin_event["event"] in ["ORDER_PLACED", "ORDER_CREATED"]:
                    break
            assert admin_event["data"]["id"] == order_id
            assert "subtotal" in admin_event["data"]
            assert admin_event["data"]["total"] == 550.0
            print("[OK] Admin WebSocket received ORDER_CREATED with financial details")

            # 7. Receive WebSocket Event on Chef Socket (Sanitized Operational Data)
            while True:
                chef_msg_raw = await asyncio.wait_for(chef_ws.recv(), timeout=5.0)
                chef_event = json.loads(chef_msg_raw)
                if chef_event["event"] in ["ORDER_PLACED", "ORDER_CREATED"]:
                    break
            assert chef_event["data"]["id"] == order_id
            # Prices MUST be sanitized for chef!
            assert "subtotal" not in chef_event["data"]
            assert "total" not in chef_event["data"]
            print("[OK] Chef WebSocket received ORDER_CREATED with sanitized operational data")

            # 8. Admin transitions order: PLACED -> ACCEPTED
            admin_headers = {"Authorization": f"Bearer {admin_token}"}
            chef_headers = {"Authorization": f"Bearer {chef_token}"}
            accept_res = await client.post(
                f"/orders/{order_id}/accept",
                headers=admin_headers,
            )
            assert accept_res.status_code == 200
            print(f"[OK] Admin accepted order: {order_id}")

            # Verify WebSocket notification (ORDER_ACCEPTED or ORDER_STATUS_UPDATED)
            ws_raw = await asyncio.wait_for(admin_ws.recv(), timeout=5.0)
            status_msg = json.loads(ws_raw)
            assert status_msg["event"] in ["ORDER_ACCEPTED", "ORDER_STATUS_UPDATED"]
            assert status_msg["data"]["status"] == "ACCEPTED"
            print(f"[OK] WebSocket broadcasted {status_msg['event']} -> ACCEPTED")

            # 9. Chef transitions order: ACCEPTED -> IN_KITCHEN (Done)
            done_res = await client.post(
                f"/orders/{order_id}/done",
                headers=chef_headers,
            )
            assert done_res.status_code == 200
            print(f"[OK] Chef marked done (IN_KITCHEN): {order_id}")

            # 10. Admin settles bill via UPI
            admin_headers = {"Authorization": f"Bearer {admin_token}"}
            settle_res = await client.post(
                f"/billing/{order_id}/settle",
                headers=admin_headers,
                json={"paymentMethod": "UPI"},
            )
            assert settle_res.status_code == 200
            inv = settle_res.json()
            assert inv["paymentStatus"] == "PAID"
            print(f"[OK] Bill settled: Invoice {inv['invoiceNumber']} marked PAID via UPI")

            # 11. Verify Table T09 is released back to AVAILABLE
            tbl_check = await client.get("/tables/T09")
            assert tbl_check.status_code == 200
            assert tbl_check.json()["status"] == "AVAILABLE"
            print("[OK] Table T09 automatically released back to AVAILABLE")

    print("\n>>> ALL END-TO-END WORKFLOWS PASSED 100%! <<<\n")
