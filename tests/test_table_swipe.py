import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _get_admin_token():
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "admin123"},
    )
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    return res.json()["access_token"]


def test_table_swipe_transfer_flow():
    token = _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Reset tables T01 and T02 to AVAILABLE
    client.patch("/api/v1/tables/T01/status", json={"status": "AVAILABLE"}, headers=headers)
    client.patch("/api/v1/tables/T02/status", json={"status": "AVAILABLE"}, headers=headers)

    # 2. Get table details
    t1_res = client.get("/api/v1/tables/T01")
    t1_token = t1_res.json()["token"]

    # Dynamic menu item
    menu_res = client.get("/api/v1/menu")
    assert menu_res.status_code == 200
    menu_item = menu_res.json()[0]

    # 3. Customer scans T01 and places order
    qr_res = client.post("/api/v1/tables/validate-qr", json={"tableId": "T01", "token": t1_token})
    assert qr_res.status_code == 200
    session_id = qr_res.json()["diningSession"]["id"]

    order_payload = {
        "tableId": "T01",
        "token": t1_token,
        "sessionToken": "test_guest_session_swipe",
        "customerName": "Swipe Customer",
        "customerMobile": "9876543210",
        "diningSessionId": session_id,
        "items": [
            {
                "menuItemId": menu_item["id"],
                "name": menu_item["name"],
                "price": float(menu_item["price"]),
                "quantity": 2,
            }
        ],
    }
    ord_res = client.post("/api/v1/orders", json=order_payload)
    assert ord_res.status_code == 201
    order_id = ord_res.json()["id"]

    # Verify T01 is OCCUPIED and T02 is AVAILABLE
    assert client.get("/api/v1/tables/T01").json()["status"] == "OCCUPIED"
    assert client.get("/api/v1/tables/T02").json()["status"] == "AVAILABLE"

    # 4. Attempt invalid transfers:
    # A. Source and destination same
    err_same = client.post(
        "/api/v1/tables/swipe",
        json={"sourceTableId": "T01", "destinationTableId": "T01"},
        headers=headers,
    )
    assert err_same.status_code == 400

    # B. Source table has no active session
    err_nosess = client.post(
        "/api/v1/tables/swipe",
        json={"sourceTableId": "T03", "destinationTableId": "T02"},
        headers=headers,
    )
    assert err_nosess.status_code == 400

    # 5. Perform valid Table Swipe from T01 to T02
    swipe_res = client.post(
        "/api/v1/tables/swipe",
        json={"sourceTableId": "T01", "destinationTableId": "T02"},
        headers=headers,
    )
    assert swipe_res.status_code == 200, swipe_res.text
    swipe_data = swipe_res.json()

    assert swipe_data["sessionId"] == session_id
    assert order_id in swipe_data["orderIds"]
    assert "Successfully swiped" in swipe_data["message"]

    # 6. Verify post-swipe states:
    # T01 should now be AVAILABLE with NO active session
    t1_after = client.get("/api/v1/tables/T01").json()
    assert t1_after["status"] == "AVAILABLE"
    assert t1_after["activeSession"] is None

    # T02 should now be OCCUPIED with the transferred session
    t2_after = client.get("/api/v1/tables/T02").json()
    assert t2_after["status"] == "OCCUPIED"
    assert t2_after["activeSession"] is not None
    assert t2_after["activeSession"]["id"] == session_id

    # Transferred order should now point to T02
    ord_check = client.get(f"/api/v1/orders/{order_id}").json()
    assert ord_check["tableId"] == "T02"

    # Cleanup: settle session on T02
    client.post(f"/api/v1/billing/sessions/{session_id}/generate", headers=headers)
    client.post(f"/api/v1/billing/sessions/{session_id}/settle", json={"paymentMethod": "CASH"}, headers=headers)
