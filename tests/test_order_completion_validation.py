import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.modules.sessions.models import DiningSession, SessionStatus
from app.modules.orders.models import Order, OrderStatus
from app.modules.tables.models import Table
from app.modules.menu.models import MenuItem
from app.db.session import get_db

client = TestClient(app)


def _get_admin_headers():
    res = client.post("/api/v1/auth/login", json={"email": "admin@vaanvibes.com", "password": "admin123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_order_completion_validation_scenarios():
    """
    Comprehensive suite verifying:
    1. One order still PLACED -> bill generation blocked (409 Conflict)
    2. Multiple incomplete orders (ACCEPTED + PLACED) -> all appear in incomplete_orders payload
    3. One order SERVED, another ACCEPTED -> blocked with 409
    4. All orders SERVED/COMPLETED -> bill generation succeeds (200 OK)
    5. Direct API requests cannot bypass validation
    6. Payment status remains PENDING and table is released to AVAILABLE
    """
    admin_headers = _get_admin_headers()

    with next(get_db()) as db:
        # Reset table T08
        open_sessions = db.query(DiningSession).filter(DiningSession.table_id == "T08", DiningSession.status == "OPEN").all()
        for s in open_sessions:
            s.status = "CLOSED"
        tbl = db.query(Table).filter(Table.id == "T08").first()
        assert tbl is not None
        tbl.status = "AVAILABLE"
        token = tbl.token

        item = db.query(MenuItem).filter(MenuItem.is_available == True).first()
        item_id = item.id
        item_name = item.name
        item_price = float(item.price)
        db.commit()

    # Step 1: QR scan creates active OPEN dining session
    scan = client.post("/api/v1/tables/validate-qr", json={"tableId": "T08", "token": token})
    assert scan.status_code == 200
    session_id = scan.json()["diningSession"]["id"]

    # Step 2: Customer places Order 1 (PLACED)
    o1_res = client.post("/api/v1/orders", json={
        "tableId": "T08",
        "token": token,
        "diningSessionId": session_id,
        "sessionToken": "sess_t08_1",
        "customerName": "Rohan Patel",
        "customerMobile": "9876500001",
        "items": [{"menuItemId": item_id, "name": item_name, "quantity": 1, "price": item_price}]
    })
    assert o1_res.status_code == 201
    o1_id = o1_res.json()["id"]

    # SCENARIO A: Attempt bill generation while Order 1 is still PLACED -> BLOCKED
    res_placed = client.post(
        f"/api/v1/billing/sessions/{session_id}/generate",
        json={"discountPercentage": 0.0},
        headers=admin_headers
    )
    assert res_placed.status_code == 409
    body_placed = res_placed.json()
    assert body_placed["code"] == "SESSION_ORDERS_INCOMPLETE"
    assert len(body_placed["incomplete_orders"]) == 1
    assert body_placed["incomplete_orders"][0]["order_id"] == o1_id
    assert body_placed["incomplete_orders"][0]["status"] == "PLACED"

    # Step 3: Admin accepts Order 1, Customer places Order 2 (PLACED)
    with next(get_db()) as db:
        ord1 = db.query(Order).filter(Order.id == o1_id).first()
        ord1.status = "ACCEPTED"
        db.commit()

    o2_res = client.post("/api/v1/orders", json={
        "tableId": "T08",
        "token": token,
        "diningSessionId": session_id,
        "sessionToken": "sess_t08_1",
        "customerName": "Rohan Patel",
        "customerMobile": "9876500001",
        "items": [{"menuItemId": item_id, "name": item_name, "quantity": 2, "price": item_price}]
    })
    assert o2_res.status_code == 201
    o2_id = o2_res.json()["id"]

    # SCENARIO B: Multiple incomplete orders (ACCEPTED + PLACED) -> Both returned
    res_multi = client.post(
        f"/api/v1/billing/sessions/{session_id}/generate",
        json={"discountPercentage": 0.0},
        headers=admin_headers
    )
    assert res_multi.status_code == 409
    body_multi = res_multi.json()
    assert body_multi["code"] == "SESSION_ORDERS_INCOMPLETE"
    assert len(body_multi["incomplete_orders"]) == 2
    order_ids = [x["order_id"] for x in body_multi["incomplete_orders"]]
    assert o1_id in order_ids and o2_id in order_ids

    # Step 4: Order 1 is SERVED, Order 2 is ACCEPTED
    with next(get_db()) as db:
        ord1 = db.query(Order).filter(Order.id == o1_id).first()
        ord2 = db.query(Order).filter(Order.id == o2_id).first()
        ord1.status = "SERVED"
        ord2.status = "ACCEPTED"
        db.commit()

    # SCENARIO C: One served, one accepted -> BLOCKED with only Order 2 returned
    res_one_inc = client.post(
        f"/api/v1/billing/sessions/{session_id}/generate",
        json={"discountPercentage": 0.0},
        headers=admin_headers
    )
    assert res_one_inc.status_code == 409
    body_one_inc = res_one_inc.json()
    assert len(body_one_inc["incomplete_orders"]) == 1
    assert body_one_inc["incomplete_orders"][0]["order_id"] == o2_id
    assert body_one_inc["incomplete_orders"][0]["status"] == "ACCEPTED"

    # Step 5: Mark Order 2 as COMPLETED
    with next(get_db()) as db:
        ord2 = db.query(Order).filter(Order.id == o2_id).first()
        ord2.status = "COMPLETED"
        db.commit()

    # SCENARIO D: All orders completed/served -> Bill generation SUCCEEDS
    res_success = client.post(
        f"/api/v1/billing/sessions/{session_id}/generate",
        json={"discountPercentage": 0.0},
        headers=admin_headers
    )
    assert res_success.status_code == 200
    bill = res_success.json()
    assert bill["diningSessionId"] == session_id
    assert bill["sessionStatus"] == "BILL_GENERATED"
    assert bill["paymentStatus"] == "PENDING"
    assert bill["subtotal"] == round(item_price * 3, 2)

    # Table released immediately to AVAILABLE
    tbl_after = client.get("/api/v1/tables/T08").json()
    assert tbl_after["status"] == "AVAILABLE"
