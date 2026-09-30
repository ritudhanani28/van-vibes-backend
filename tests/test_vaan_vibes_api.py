import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_public_categories():
    response = client.get("/api/v1/categories")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 19
    slugs = [c["id"] for c in data]
    assert "hot-coffee" in slugs
    assert "pizza" in slugs


def test_public_menu_search():
    response = client.get("/api/v1/menu?category=hot-coffee")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 5
    for item in items:
        assert item["category"] == "hot-coffee"
        assert item["price"] > 0


def test_public_tables_and_qr():
    # 1. List tables
    response = client.get("/api/v1/tables")
    assert response.status_code == 200
    tables = response.json()
    assert len(tables) >= 12

    # 2. Validate valid QR token
    t1 = tables[0]
    val_res = client.post(
        "/api/v1/tables/validate-qr",
        json={"tableId": t1["id"], "token": t1["token"]},
    )
    assert val_res.status_code == 200
    assert val_res.json()["valid"] is True

    # 3. Validate invalid QR token
    bad_res = client.post(
        "/api/v1/tables/validate-qr",
        json={"tableId": t1["id"], "token": "invalid_fake_token"},
    )
    assert bad_res.status_code == 200
    assert bad_res.json()["valid"] is False

    # 4. Backend QR image generation endpoint
    qr_res = client.get(f"/api/v1/tables/{t1['id']}/qr")
    assert qr_res.status_code == 200
    assert qr_res.headers["content-type"] == "image/png"
    assert len(qr_res.content) > 500


def test_authentication_and_rbac():
    # 1. Admin login
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "admin123"},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    assert admin_login.json()["user"]["role"] == "ADMIN"

    # 2. Chef login
    chef_login = client.post(
        "/api/v1/auth/login",
        json={"email": "chef@vaanvibes.com", "password": "chef123"},
    )
    assert chef_login.status_code == 200
    chef_token = chef_login.json()["access_token"]
    assert chef_login.json()["user"]["role"] == "CHEF"

    # 3. Invalid login credentials
    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # 4. Chef restricted from Admin dashboard summary
    chef_dash = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {chef_token}"},
    )
    assert chef_dash.status_code == 403

    # 5. Admin allowed access to Dashboard summary
    admin_dash = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_dash.status_code == 200
    dash_data = admin_dash.json()
    assert "totalOrders" in dash_data
    assert "kitchenPending" in dash_data
    assert "settledRevenue" in dash_data


def test_order_lifecycle_and_state_machine():
    # 1. Fetch Table 8 token
    tbl_res = client.get("/api/v1/tables/T08")
    assert tbl_res.status_code == 200
    table8 = tbl_res.json()

    # 2. Place order with server-side price validation
    order_payload = {
        "tableId": "T08",
        "token": table8["token"],
        "sessionToken": "sess_test_autotick",
        "customerName": "Test Customer",
        "customerMobile": "9876501234",
        "specialInstructions": "No ice",
        "items": [
            {
                "menuItemId": "hc-01",
                "name": "Espresso",
                "quantity": 1,
            },
            {
                "menuItemId": "hc-03",
                "name": "Cappuccino",
                "quantity": 2,
            },
        ],
    }
    create_res = client.post("/api/v1/orders", json=order_payload)
    assert create_res.status_code == 201
    order = create_res.json()
    order_id = order["id"]
    # 140 + 2*160 = 460 subtotal; Tax removed = 0.0; total = 460.0
    assert order["subtotal"] == 460.0
    assert order["tax"] == 0.0
    assert order["total"] == 460.0
    assert order["status"] == "PLACED"

    # 3. Chef login
    chef_login = client.post(
        "/api/v1/auth/login",
        json={"email": "chef@vaanvibes.com", "password": "chef123"},
    )
    chef_token = chef_login.json()["access_token"]

    # Chef cannot accept order (must be Admin)
    chef_accept_res = client.post(
        f"/api/v1/orders/{order_id}/accept",
        headers={"Authorization": f"Bearer {chef_token}"},
    )
    assert chef_accept_res.status_code == 403

    # Admin login & accepts order
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "admin123"},
    )
    admin_token = admin_login.json()["access_token"]

    # 4. Valid transition: PLACED -> ACCEPTED by Admin
    accept_res = client.post(
        f"/api/v1/orders/{order_id}/accept",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert accept_res.status_code == 200
    assert accept_res.json()["status"] == "ACCEPTED"

    # 5. Valid transition: Chef clicks Done -> IN_KITCHEN
    done_res = client.post(
        f"/api/v1/orders/{order_id}/done",
        headers={"Authorization": f"Bearer {chef_token}"},
    )
    assert done_res.status_code == 200
    assert done_res.json()["status"] == "IN_KITCHEN"

    # 6. Admin completes order
    complete_res = client.post(
        f"/api/v1/orders/{order_id}/complete",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert complete_res.status_code == 200
    assert complete_res.json()["status"] == "COMPLETED"

    # 6. Invalid transition: COMPLETED -> PLACED (must be rejected)
    bad_res = client.patch(
        f"/api/v1/orders/{order_id}/status",
        headers={"Authorization": f"Bearer {chef_token}"},
        json={"status": "PLACED"},
    )
    assert bad_res.status_code == 400

    # 7. Customer cannot cancel once progressed
    cancel_res = client.post(f"/api/v1/orders/{order_id}/cancel")
    assert cancel_res.status_code == 400

    # 8. Complete stages to COMPLETED
    comp_res = client.post(
        f"/api/v1/orders/{order_id}/complete",
        headers={"Authorization": f"Bearer {chef_token}"},
    )
    assert comp_res.status_code == 200
    assert comp_res.json()["status"] == "COMPLETED"


def test_billing_settlement_and_table_release():
    # 1. Admin login
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "admin123"},
    )
    admin_token = admin_login.json()["access_token"]

    # 2. Fetch billing receipt for VV-1001
    rcpt_res = client.get("/api/v1/billing/VV-1001")
    assert rcpt_res.status_code == 200
    receipt = rcpt_res.json()
    assert receipt["orderId"] == "VV-1001"
    assert "cgst" in receipt
    assert "sgst" in receipt
    assert len(receipt["items"]) >= 1

    # 3. Settle payment for VV-1002
    settle_res = client.post(
        "/api/v1/billing/VV-1002/settle",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"paymentMethod": "CARD"},
    )
    assert settle_res.status_code == 200
    assert settle_res.json()["paymentStatus"] == "PAID"
    assert settle_res.json()["paymentMethod"] == "CARD"
