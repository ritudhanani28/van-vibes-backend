import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import SessionLocal
from app.core.security import create_access_token
from app.modules.tables.models import Table
from app.modules.menu.models import MenuItem

client = TestClient(app)

from app.modules.accounts.models import User

def _setup_table_and_item():
    db = SessionLocal()
    table = db.query(Table).filter(Table.is_active == True).first()
    item = db.query(MenuItem).filter(MenuItem.is_available == True).first()
    admin = db.query(User).filter(User.role == "ADMIN", User.is_active == True).first()
    db.close()
    return table, item, admin

def test_order_cancellation_flow_end_to_end():
    table, item, admin = _setup_table_and_item()
    assert table is not None
    assert item is not None
    assert admin is not None

    admin_token = create_access_token(data={"sub": admin.id, "role": "ADMIN"})
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Place order
    payload = {
        "tableId": table.id,
        "token": table.token,
        "sessionToken": f"sess_test_{table.id}",
        "customerName": "Test Customer",
        "customerMobile": "9876543210",
        "items": [
            {
                "menuItemId": item.id,
                "name": item.name,
                "price": item.price,
                "quantity": 1,
            }
        ]
    }
    create_res = client.post("/api/v1/orders", json=payload)
    assert create_res.status_code == 201, create_res.text
    order_data = create_res.json()
    order_id = order_data["id"]
    assert order_data["status"] == "PLACED"
    assert order_data["activityStatus"] == "ACTIVE"
    assert order_data.get("cancellationReason") is None

    # 2. Try cancelling without reason -> Must fail
    no_reason_res = client.post(f"/api/v1/orders/{order_id}/cancel", json={})
    assert no_reason_res.status_code == 400
    assert "reason" in no_reason_res.text.lower()

    # 3. Customer cancels successfully with reason
    cancel_res = client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"reason": "Ordered by mistake", "cancelledBy": "customer"}
    )
    assert cancel_res.status_code == 200, cancel_res.text
    cancelled_data = cancel_res.json()["order"]
    assert cancelled_data["status"] == "CANCELLED"
    assert cancelled_data["cancellationReason"] == "Ordered by mistake"
    assert cancelled_data["cancelledBy"] == "customer"
    assert cancelled_data["cancelledAt"] is not None
    assert cancelled_data["activityStatus"] == "INACTIVE"
    assert cancelled_data["isActive"] is False

    # 4. Try cancelling again -> Must fail (already cancelled)
    re_cancel = client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"reason": "Changed my mind"}
    )
    assert re_cancel.status_code == 400
    assert "already been cancelled" in re_cancel.text

    # 5. Place a second order and accept it, then try customer cancel -> Must be rejected!
    create_res2 = client.post("/api/v1/orders", json=payload)
    assert create_res2.status_code == 201
    order2_id = create_res2.json()["id"]

    # Admin accepts order
    accept_res = client.post(f"/api/v1/orders/{order2_id}/accept", headers=admin_headers)
    assert accept_res.status_code == 200, accept_res.text
    assert accept_res.json()["status"] == "ACCEPTED"

    # Attempt to cancel accepted order -> Server-side rejection & race-condition protection!
    cancel_after_accept = client.post(
        f"/api/v1/orders/{order2_id}/cancel",
        json={"reason": "Taking too long", "cancelledBy": "customer"}
    )
    assert cancel_after_accept.status_code == 400
    assert "already been accepted" in cancel_after_accept.text

    # 6. Place a third order and management cancels it with reason
    create_res3 = client.post("/api/v1/orders", json=payload)
    assert create_res3.status_code == 201
    order3_id = create_res3.json()["id"]

    admin_cancel = client.post(
        f"/api/v1/orders/{order3_id}/cancel",
        json={
            "reason": "Item unavailable",
            "cancellationNote": "Kitchen ran out of fresh stock",
            "cancelledBy": "management"
        },
        headers=admin_headers,
    )
    assert admin_cancel.status_code == 200, admin_cancel.text
    cancelled3 = admin_cancel.json()["order"]
    assert cancelled3["status"] == "CANCELLED"
    assert cancelled3["cancellationReason"] == "Item unavailable"
    assert cancelled3["cancellationNote"] == "Kitchen ran out of fresh stock"
    assert cancelled3["cancelledBy"] == "management"
    assert cancelled3["activityStatus"] == "INACTIVE"
