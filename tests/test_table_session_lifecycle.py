import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import get_db
from app.modules.sessions.models import DiningSession, SessionStatus
from app.modules.menu.models import MenuItem
from app.modules.orders.models import Order, OrderStatus
from app.modules.tables.models import Table
from app.modules.sessions.models import BillingInvoice


client = TestClient(app)


def _get_admin_headers():
    res = client.post("/api/v1/auth/login", json={"email": "admin@vaanvibes.com", "password": "admin123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_complete_table_session_lifecycle():
    admin_headers = _get_admin_headers()

    # 0. Clean test table T04 and get valid menu items
    with next(get_db()) as db:
        open_sessions = db.query(DiningSession).filter(DiningSession.table_id == "T04", DiningSession.status == "OPEN").all()
        for s in open_sessions:
            s.status = "CLOSED"
        tbl = db.query(Table).filter(Table.id == "T04").first()
        tbl.status = "AVAILABLE"
        token = tbl.token

        item1 = db.query(MenuItem).filter(MenuItem.is_available == True).first()
        item1_id = item1.id
        item1_name = item1.name
        item1_price = float(item1.price)

        item2 = db.query(MenuItem).filter(MenuItem.is_available == True, MenuItem.id != item1_id).first()
        item2_id = item2.id
        item2_name = item2.name
        item2_price = float(item2.price)

        db.commit()

    # Step 1: John scans Table 4 -> S001 created (OPEN), Table 4 becomes OCCUPIED
    scan_resp = client.post("/api/v1/tables/validate-qr", json={"tableId": "T04", "token": token})
    assert scan_resp.status_code == 200
    scan_data = scan_resp.json()
    assert scan_data["valid"] is True
    assert scan_data["isNewSession"] is True
    s001_id = scan_data["diningSession"]["id"]
    assert scan_data["diningSession"]["status"] == "OPEN"
    assert scan_data["table"]["status"] == "OCCUPIED"

    # Step 2: John places Order 1 in S001
    order1_payload = {
        "tableId": "T04",
        "token": token,
        "diningSessionId": s001_id,
        "sessionToken": "sess_john_1",
        "customerName": "John Doe",
        "customerMobile": "9876543210",
        "items": [
            {
                "menuItemId": item1_id,
                "name": item1_name,
                "quantity": 2,
                "price": item1_price
            }
        ]
    }
    order1_resp = client.post("/api/v1/orders", json=order1_payload)
    assert order1_resp.status_code == 201
    order1_data = order1_resp.json()
    assert order1_data["diningSessionId"] == s001_id
    order1_id = order1_data["id"]

    # Step 3: David scans Table 4 on another phone -> Joins existing S001
    scan2_resp = client.post("/api/v1/tables/validate-qr", json={"tableId": "T04", "token": token})
    assert scan2_resp.status_code == 200
    scan2_data = scan2_resp.json()
    assert scan2_data["isNewSession"] is False
    assert scan2_data["diningSession"]["id"] == s001_id

    # Step 4: David places Order 2 in S001
    order2_payload = {
        "tableId": "T04",
        "token": token,
        "diningSessionId": s001_id,
        "sessionToken": "sess_david_2",
        "customerName": "David Smith",
        "customerMobile": "9876543211",
        "items": [
            {
                "menuItemId": item2_id,
                "name": item2_name,
                "quantity": 1,
                "price": item2_price
            }
        ]
    }
    order2_resp = client.post("/api/v1/orders", json=order2_payload)
    assert order2_resp.status_code == 201
    order2_data = order2_resp.json()
    assert order2_data["diningSessionId"] == s001_id
    order2_id = order2_data["id"]

    # Verify session detail has both orders
    detail_resp = client.get(f"/api/v1/dining-sessions/{s001_id}")
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert detail_data["orderCount"] == 2
    assert detail_data["status"] == "OPEN"

    client.patch(f"/api/v1/orders/{order1_id}/status", json={"status": "ACCEPTED"}, headers=admin_headers)
    client.patch(f"/api/v1/orders/{order1_id}/status", json={"status": "COMPLETED"}, headers=admin_headers)
    client.patch(f"/api/v1/orders/{order2_id}/status", json={"status": "ACCEPTED"}, headers=admin_headers)
    client.patch(f"/api/v1/orders/{order2_id}/status", json={"status": "COMPLETED"}, headers=admin_headers)

    # Step 5: Admin generates final bill for S001 with 10% discount
    # Critical requirement: S001 -> BILL_GENERATED, Table 4 -> AVAILABLE immediately!
    bill_resp = client.post(
        f"/api/v1/billing/sessions/{s001_id}/generate",
        json={"discountPercentage": 10.0},
        headers=admin_headers
    )
    assert bill_resp.status_code == 200
    bill_data = bill_resp.json()
    assert bill_data["diningSessionId"] == s001_id
    assert bill_data["paymentStatus"] == "PENDING"
    assert bill_data["discountPercentage"] == 10.0

    # Verify Table 4 is now AVAILABLE!
    tbl_resp = client.get("/api/v1/tables/T04")
    assert tbl_resp.status_code == 200
    assert tbl_resp.json()["status"] == "AVAILABLE"

    # Step 6: Order submitted after bill generation must NOT append to S001; it must create a new session!
    order_new_session_payload = {
        "tableId": "T04",
        "token": token,
        "diningSessionId": s001_id,
        "sessionToken": "sess_john_1",
        "customerName": "John Doe",
        "customerMobile": "9876543210",
        "items": [{"menuItemId": item1_id, "name": item1_name, "quantity": 1}]
    }
    resp6 = client.post("/api/v1/orders", json=order_new_session_payload)
    assert resp6.status_code == 201
    resp6_data = resp6.json()
    # Must NOT append to S001; assigned to a new session!
    assert resp6_data["diningSessionId"] != s001_id

    # S001 order count remains 2 (Order was NOT appended to S001)
    s001_check = client.get(f"/api/v1/dining-sessions/{s001_id}").json()
    assert s001_check["orderCount"] == 2

    s002_id = resp6_data["diningSessionId"]
    assert s002_id != s001_id

    # Step 7: Another guest arrives at Table 4 while S001 bill is UNPAID!
    # Joins the newly created active OPEN session S002
    new_scan = client.post("/api/v1/tables/validate-qr", json={"tableId": "T04", "token": token})
    assert new_scan.status_code == 200
    new_scan_data = new_scan.json()
    assert new_scan_data["diningSession"]["id"] == s002_id
    assert new_scan_data["table"]["status"] == "OCCUPIED"

    # New customer places Order in S002
    order3_resp = client.post("/api/v1/orders", json={
        "tableId": "T04",
        "token": token,
        "diningSessionId": s002_id,
        "sessionToken": "sess_charlie_3",
        "customerName": "Charlie Brown",
        "customerMobile": "9876543212",
        "items": [{"menuItemId": item1_id, "name": item1_name, "quantity": 1}]
    })
    assert order3_resp.status_code == 201
    assert order3_resp.json()["diningSessionId"] == s002_id
    order3_id = order3_resp.json()["id"]

    # Verify Pending Payments includes S001 unpaid bill, and reflects Table 4 is currently OCCUPIED by S002
    pending_resp = client.get("/api/v1/billing/pending", headers=admin_headers)
    assert pending_resp.status_code == 200
    pending_bills = pending_resp.json()
    s001_pending = next((b for b in pending_bills if b.get("diningSessionId") == s001_id), None)
    assert s001_pending is not None
    assert s001_pending["paymentStatus"] == "PENDING"
    assert s001_pending["tableStatus"] == "OCCUPIED"  # Because S002 is currently using Table 4!

    # Step 8: Previous customer finally pays S001 bill!
    # S001 -> CLOSED, B001 -> PAID.
    # CRITICAL: Table 4 MUST REMAIN OCCUPIED because S002 is still active!
    settle_resp = client.post(
        f"/api/v1/billing/sessions/{s001_id}/settle",
        json={"paymentMethod": "UPI"},
        headers=admin_headers
    )
    assert settle_resp.status_code == 200
    settle_data = settle_resp.json()
    assert settle_data["paymentStatus"] == "PAID"
    assert settle_data["tableStatus"] == "OCCUPIED"

    tbl_check = client.get("/api/v1/tables/T04")
    assert tbl_check.json()["status"] == "OCCUPIED"

    order_new_id = resp6_data["id"]
    client.patch(f"/api/v1/orders/{order_new_id}/status", json={"status": "ACCEPTED"}, headers=admin_headers)
    client.patch(f"/api/v1/orders/{order_new_id}/status", json={"status": "COMPLETED"}, headers=admin_headers)
    client.patch(f"/api/v1/orders/{order3_id}/status", json={"status": "ACCEPTED"}, headers=admin_headers)
    client.patch(f"/api/v1/orders/{order3_id}/status", json={"status": "COMPLETED"}, headers=admin_headers)

    # Step 9: S002 finishes eating -> Final Bill generated -> Table 4 becomes AVAILABLE
    bill2_resp = client.post(f"/api/v1/billing/sessions/{s002_id}/generate", json={}, headers=admin_headers)
    assert bill2_resp.status_code == 200

    tbl_check2 = client.get("/api/v1/tables/T04")
    assert tbl_check2.json()["status"] == "AVAILABLE"

    # Step 10: S002 pays bill -> Table 4 remains AVAILABLE
    settle2_resp = client.post(
        f"/api/v1/billing/sessions/{s002_id}/settle",
        json={"paymentMethod": "CASH"},
        headers=admin_headers
    )
    assert settle2_resp.status_code == 200
    assert settle2_resp.json()["tableStatus"] == "AVAILABLE"
