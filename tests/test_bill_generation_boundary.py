import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.modules.sessions.models import DiningSession, SessionStatus
from app.modules.tables.models import Table
from app.modules.menu.models import MenuItem
from app.db.session import get_db

client = TestClient(app)


def _get_admin_headers():
    res = client.post("/api/v1/auth/login", json={"email": "admin@vaanvibes.com", "password": "admin123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_bill_generation_permanently_closes_order_group():
    """
    Verifies that:
    1. Before bill generation: Orders for the same active dining session are grouped together.
    2. Admin generates bill: Current order/session is CLOSED FOR NEW ORDERS (BILL_GENERATED).
    3. Payment options appear, payment status is PENDING (payment does NOT control order separation).
    4. Next customer uses Table 12: MUST NOT append to billed order. Must create a NEW dining session & NEW order.
    5. Table status remains properly tracked even when old bill is settled via UPI/Cash while new session is running.
    """
    admin_headers = _get_admin_headers()

    # Setup Table T12
    with next(get_db()) as db:
        open_sessions = db.query(DiningSession).filter(DiningSession.table_id == "T12", DiningSession.status == "OPEN").all()
        for s in open_sessions:
            s.status = "CLOSED"
        tbl = db.query(Table).filter(Table.id == "T12").first()
        assert tbl is not None
        tbl.status = "AVAILABLE"
        token = tbl.token

        item = db.query(MenuItem).filter(MenuItem.is_available == True).first()
        item_id = item.id
        item_name = item.name
        item_price = float(item.price)
        db.commit()

    # Step 1: Customer arrives at Table 12 -> QR scan creates Session S001 (OPEN), Table becomes OCCUPIED
    scan1 = client.post("/api/v1/tables/validate-qr", json={"tableId": "T12", "token": token})
    assert scan1.status_code == 200
    s1_id = scan1.json()["diningSession"]["id"]
    assert scan1.json()["diningSession"]["status"] == "OPEN"
    assert scan1.json()["table"]["status"] == "OCCUPIED"

    # Step 2: Customer places Order #1 (1x Espresso)
    o1_res = client.post("/api/v1/orders", json={
        "tableId": "T12",
        "token": token,
        "diningSessionId": s1_id,
        "sessionToken": "sess_cust_1",
        "customerName": "Customer 1",
        "customerMobile": "9876543201",
        "items": [{"menuItemId": item_id, "name": item_name, "quantity": 1, "price": item_price}]
    })
    assert o1_res.status_code == 201
    o1_id = o1_res.json()["id"]
    assert o1_res.json()["diningSessionId"] == s1_id

    # Step 3: Before Bill Generation, customer adds items (Order #2) -> grouped in same session S001
    o2_res = client.post("/api/v1/orders", json={
        "tableId": "T12",
        "token": token,
        "diningSessionId": s1_id,
        "sessionToken": "sess_cust_1",
        "customerName": "Customer 1",
        "customerMobile": "9876543201",
        "items": [{"menuItemId": item_id, "name": item_name, "quantity": 2, "price": item_price}]
    })
    assert o2_res.status_code == 201
    o2_id = o2_res.json()["id"]
    assert o2_res.json()["diningSessionId"] == s1_id

    # Verify session S001 detail has 2 orders
    s1_detail = client.get(f"/api/v1/dining-sessions/{s1_id}").json()
    assert s1_detail["orderCount"] == 2
    assert s1_detail["status"] == "OPEN"

    # Step 4: Admin Generates Final Bill for S001
    # Boundary enforced: S001 transitions to BILL_GENERATED, Table 12 becomes AVAILABLE immediately
    bill_res = client.post(
        f"/api/v1/billing/sessions/{s1_id}/generate",
        json={"discountPercentage": 0.0},
        headers=admin_headers
    )
    assert bill_res.status_code == 200
    bill_data = bill_res.json()
    assert bill_data["diningSessionId"] == s1_id
    assert bill_data["paymentStatus"] == "PENDING"
    assert bill_data["sessionStatus"] == "BILL_GENERATED"

    # Table 12 is freed immediately
    tbl_after_bill = client.get("/api/v1/tables/T12").json()
    assert tbl_after_bill["status"] == "AVAILABLE"

    # Step 5: Next customer uses Table 12 while payment for S001 is still PENDING!
    # Even if client sends old sessionToken or old diningSessionId, backend MUST NOT append to S001!
    o3_res = client.post("/api/v1/orders", json={
        "tableId": "T12",
        "token": token,
        "diningSessionId": s1_id,  # Old session!
        "sessionToken": "sess_cust_2",
        "customerName": "Customer 2",
        "customerMobile": "9876543202",
        "items": [{"menuItemId": item_id, "name": item_name, "quantity": 1, "price": item_price}]
    })
    assert o3_res.status_code == 201
    o3_data = o3_res.json()
    s2_id = o3_data["diningSessionId"]

    # Critical requirement: MUST NOT be appended to S001!
    assert s2_id != s1_id

    # S001 order count remains strictly 2
    s1_check = client.get(f"/api/v1/dining-sessions/{s1_id}").json()
    assert s1_check["orderCount"] == 2
    assert s1_check["status"] == "BILL_GENERATED"

    # S002 order count is 1
    s2_check = client.get(f"/api/v1/dining-sessions/{s2_id}").json()
    assert s2_check["orderCount"] == 1
    assert s2_check["status"] == "OPEN"

    # Step 6: Settle S001 bill via UPI (Scenario B)
    settle1 = client.post(
        f"/api/v1/billing/sessions/{s1_id}/settle",
        json={"paymentMethod": "UPI"},
        headers=admin_headers
    )
    assert settle1.status_code == 200
    assert settle1.json()["paymentStatus"] == "PAID"

    # Table 12 MUST REMAIN OCCUPIED because S002 is actively open!
    tbl_check = client.get("/api/v1/tables/T12").json()
    assert tbl_check["status"] == "OCCUPIED"

    # Step 7: S002 places additional order -> remains in S002
    o4_res = client.post("/api/v1/orders", json={
        "tableId": "T12",
        "token": token,
        "diningSessionId": s2_id,
        "sessionToken": "sess_cust_2",
        "customerName": "Customer 2",
        "customerMobile": "9876543202",
        "items": [{"menuItemId": item_id, "name": item_name, "quantity": 1, "price": item_price}]
    })
    assert o4_res.status_code == 201
    assert o4_res.json()["diningSessionId"] == s2_id

    s2_check2 = client.get(f"/api/v1/dining-sessions/{s2_id}").json()
    assert s2_check2["orderCount"] == 2

    # Step 8: Admin generates bill for S002
    bill2 = client.post(f"/api/v1/billing/sessions/{s2_id}/generate", json={}, headers=admin_headers)
    assert bill2.status_code == 200
    assert bill2.json()["sessionStatus"] == "BILL_GENERATED"

    # S002 settles with CASH (Scenario C)
    settle2 = client.post(
        f"/api/v1/billing/sessions/{s2_id}/settle",
        json={"paymentMethod": "CASH"},
        headers=admin_headers
    )
    assert settle2.status_code == 200
    assert settle2.json()["paymentStatus"] == "PAID"

    # Table is now AVAILABLE again
    tbl_final = client.get("/api/v1/tables/T12").json()
    assert tbl_final["status"] == "AVAILABLE"
