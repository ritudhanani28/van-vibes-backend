import pytest
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _get_admin_token():
    admin_res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "admin123"},
    )
    assert admin_res.status_code == 200, f"Admin login failed: {admin_res.text}"
    return admin_res.json()["access_token"]


def test_order_activity_lifecycle_and_filter():
    admin_token = _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Fetch menu item
    menu_res = client.get("/api/v1/menu")
    assert menu_res.status_code == 200
    item = menu_res.json()[0]

    # Create a fresh unique table to ensure clean isolated session
    import random
    unique_tbl_num = random.randint(7000, 9999)
    tbl_create_res = client.post("/api/v1/tables", json={"table_number": unique_tbl_num}, headers=headers)
    assert tbl_create_res.status_code in [200, 201]
    table = tbl_create_res.json()

    sess_token = f"sess_act_{uuid.uuid4().hex[:8]}"

    # 1. Placed order -> must be ACTIVE
    order_payload = {
        "tableId": table["id"],
        "token": table["token"],
        "sessionToken": sess_token,
        "customerName": "Activity Test Guest",
        "customerMobile": "9876543210",
        "specialInstructions": "Testing active lifecycle",
        "items": [
            {
                "menuItemId": item["id"],
                "name": item["name"],
                "quantity": 1,
            }
        ],
    }
    create_res = client.post("/api/v1/orders", json=order_payload)
    assert create_res.status_code in [200, 201]
    order_data = create_res.json()
    order_id = order_data["id"]

    assert order_data["status"] == "PLACED"
    assert order_data["billGenerated"] is False
    assert order_data["paymentStatus"] == "PENDING"
    assert order_data["activityStatus"] == "ACTIVE"
    assert order_data["isActive"] is True

    # 2. Accepted order -> must remain ACTIVE
    accept_res = client.post(f"/api/v1/orders/{order_id}/accept", headers=headers)
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == "ACCEPTED"
    assert accept_res.json()["activityStatus"] == "ACTIVE"

    # 3. In Kitchen -> must remain ACTIVE
    done_res = client.post(f"/api/v1/orders/{order_id}/done", headers=headers)
    assert done_res.status_code == 200
    assert done_res.json()["status"] == "IN_KITCHEN"
    assert done_res.json()["activityStatus"] == "ACTIVE"

    # 4. Completed order with NO bill generated -> must remain ACTIVE
    complete_res = client.post(f"/api/v1/orders/{order_id}/complete", headers=headers)
    assert complete_res.status_code == 200
    completed_data = complete_res.json()
    assert completed_data["status"] == "COMPLETED"
    assert completed_data["billGenerated"] is False
    assert completed_data["paymentStatus"] == "PENDING"
    assert completed_data["activityStatus"] == "ACTIVE"
    assert completed_data["isActive"] is True

    # 5. Bill generated but payment pending -> must remain ACTIVE
    session_id = completed_data.get("diningSessionId")
    assert session_id is not None

    bill_res = client.post(
        f"/api/v1/billing/sessions/{session_id}/generate",
        json={"discount_percentage": 0.0},
        headers=headers,
    )
    assert bill_res.status_code in [200, 201]

    check_res = client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert check_res.status_code == 200
    bill_pending_data = check_res.json()
    assert bill_pending_data["status"] == "COMPLETED"
    assert bill_pending_data["billGenerated"] is True
    assert bill_pending_data["paymentStatus"] == "PENDING"
    assert bill_pending_data["activityStatus"] == "ACTIVE"
    assert bill_pending_data["isActive"] is True

    # Check API filter with activity_status=ACTIVE
    active_list_res = client.get("/api/v1/orders?activity_status=ACTIVE", headers=headers)
    assert active_list_res.status_code == 200
    active_ids = [o["id"] for o in active_list_res.json()]
    assert order_id in active_ids

    # Check API filter with activity_status=INACTIVE -> should NOT contain order_id yet
    inactive_list_res = client.get("/api/v1/orders?activity_status=INACTIVE", headers=headers)
    assert inactive_list_res.status_code == 200
    inactive_ids = [o["id"] for o in inactive_list_res.json()]
    assert order_id not in inactive_ids

    # 6. Settle payment -> order must now become INACTIVE!
    pay_res = client.post(
        f"/api/v1/billing/sessions/{session_id}/settle",
        json={"payment_method": "CASH"},
        headers=headers,
    )
    assert pay_res.status_code == 200

    # Now verify order has transitioned to INACTIVE
    settled_res = client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert settled_res.status_code == 200
    settled_data = settled_res.json()
    assert settled_data["status"] == "COMPLETED"
    assert settled_data["billGenerated"] is True
    assert settled_data["paymentStatus"] == "PAID"
    assert settled_data["activityStatus"] == "INACTIVE"
    assert settled_data["isActive"] is False

    # Check API filter with activity_status=INACTIVE -> must now contain order_id!
    inactive_list_res2 = client.get("/api/v1/orders?activity_status=INACTIVE", headers=headers)
    assert inactive_list_res2.status_code == 200
    inactive_ids2 = [o["id"] for o in inactive_list_res2.json()]
    assert order_id in inactive_ids2

    # Check API filter with activity_status=ACTIVE -> must NO LONGER contain order_id!
    active_list_res2 = client.get("/api/v1/orders?activity_status=ACTIVE", headers=headers)
    assert active_list_res2.status_code == 200
    active_ids2 = [o["id"] for o in active_list_res2.json()]
    assert order_id not in active_ids2

    # Check API filter with activity_status=ALL -> must contain order_id!
    all_list_res = client.get("/api/v1/orders?activity_status=ALL", headers=headers)
    assert all_list_res.status_code == 200
    all_ids = [o["id"] for o in all_list_res.json()]
    assert order_id in all_ids

    # Clean up table
    client.delete(f"/api/v1/tables/{table['id']}", headers=headers)
