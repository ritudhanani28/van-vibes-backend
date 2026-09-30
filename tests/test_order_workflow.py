import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _get_tokens():
    admin_res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "admin123"},
    )
    assert admin_res.status_code == 200, f"Admin login failed: {admin_res.text}"
    admin_token = admin_res.json()["access_token"]

    chef_res = client.post(
        "/api/v1/auth/login",
        json={"email": "chef@vaanvibes.com", "password": "chef123"},
    )
    assert chef_res.status_code == 200, f"Chef login failed: {chef_res.text}"
    chef_token = chef_res.json()["access_token"]
    return admin_token, chef_token


def _create_test_order():
    # Fetch menu items and tables to construct a valid order
    menu_res = client.get("/api/v1/menu")
    assert menu_res.status_code == 200
    items = menu_res.json()
    assert len(items) > 0
    item = items[0]

    tables_res = client.get("/api/v1/tables")
    assert tables_res.status_code == 200
    tables = tables_res.json()
    assert len(tables) > 0
    table = tables[0]

    order_payload = {
        "tableId": table["id"],
        "token": table["token"],
        "sessionToken": f"sess_test_{table['id']}_workflow",
        "customerName": "Ritu Workflow Test",
        "customerMobile": "9876543210",
        "specialInstructions": "Extra spicy",
        "items": [
            {
                "menuItemId": item["id"],
                "name": item["name"],
                "quantity": 2,
            }
        ],
    }
    create_res = client.post("/api/v1/orders", json=order_payload)
    assert create_res.status_code == 201, f"Failed to create order: {create_res.text}"
    return create_res.json()


def test_order_creation_initial_status_placed():
    """Verify order creation sets status to PLACED automatically."""
    order = _create_test_order()
    assert order["status"] == "PLACED"
    assert "id" in order
    assert len(order["items"]) == 1
    assert order["items"][0]["quantity"] == 2


def test_order_valid_workflow_lifecycle():
    """Verify full sequential lifecycle: PLACED -> (Admin Accepts) -> ACCEPTED -> (Chef Done) -> IN_KITCHEN -> (Admin Complete) -> COMPLETED."""
    admin_token, chef_token = _get_tokens()
    order = _create_test_order()
    order_id = order["id"]

    # 1. Chef MUST NOT be able to accept orders
    chef_accept_res = client.post(
        f"/api/v1/orders/{order_id}/accept",
        headers={"Authorization": f"Bearer {chef_token}"},
    )
    assert chef_accept_res.status_code == 403, f"Chef should not be able to accept order, got {chef_accept_res.status_code}"

    # 2. Admin Accepts Order: PLACED -> ACCEPTED
    admin_accept_res = client.post(
        f"/api/v1/orders/{order_id}/accept",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_accept_res.status_code == 200, f"Admin accept failed: {admin_accept_res.text}"
    assert admin_accept_res.json()["status"] == "ACCEPTED"

    # 3. Chef clicks Done: ACCEPTED -> IN_KITCHEN
    done_res = client.post(
        f"/api/v1/orders/{order_id}/done",
        headers={"Authorization": f"Bearer {chef_token}"},
    )
    assert done_res.status_code == 200, f"Chef done failed: {done_res.text}"
    assert done_res.json()["status"] == "IN_KITCHEN"

    # 4. Complete Order: IN_KITCHEN -> COMPLETED (by Admin)
    complete_res = client.post(
        f"/api/v1/orders/{order_id}/complete",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert complete_res.status_code == 200, f"Complete failed: {complete_res.text}"
    assert complete_res.json()["status"] == "COMPLETED"


def test_invalid_status_transitions_rejected():
    """Backend must reject invalid status jumps with 400 Bad Request."""
    admin_token, chef_token = _get_tokens()
    order = _create_test_order()
    order_id = order["id"]
    assert order["status"] == "PLACED"

    # 1. PLACED -> COMPLETED (Invalid jump without accepting)
    res = client.post(
        f"/api/v1/orders/{order_id}/complete",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 400, f"Expected 400 for PLACED -> COMPLETED, got {res.status_code}"

    # Now advance to ACCEPTED
    res_acc = client.post(f"/api/v1/orders/{order_id}/accept", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_acc.status_code == 200

    # 2. ACCEPTED -> SERVED (Invalid transition since SERVED was deprecated)
    res = client.post(
        f"/api/v1/orders/{order_id}/serve",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 400, f"Expected 400 for ACCEPTED -> SERVED, got {res.status_code}"

    # Advance to COMPLETED
    res_comp = client.post(f"/api/v1/orders/{order_id}/complete", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_comp.status_code == 200

    # 3. COMPLETED -> ACCEPTED (Invalid backwards transition)
    res = client.post(
        f"/api/v1/orders/{order_id}/accept",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res.status_code == 400


def test_role_based_order_data_protection():
    """Verify Chef NEVER receives prices/billing, while Admin receives full financial data."""
    admin_token, chef_token = _get_tokens()
    order = _create_test_order()
    order_id = order["id"]

    # 1. Admin GET /orders/{order_id}
    admin_order = client.get(
        f"/api/v1/orders/{order_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()

    assert "subtotal" in admin_order, "Admin should see subtotal"
    assert "tax" in admin_order, "Admin should see tax"
    assert "total" in admin_order, "Admin should see total"
    assert len(admin_order["items"]) > 0
    first_item = admin_order["items"][0]
    assert "unitPrice" in first_item, "Admin should see unitPrice"
    assert "itemTotal" in first_item, "Admin should see itemTotal"

    # 2. Chef GET /orders/{order_id}
    chef_order = client.get(
        f"/api/v1/orders/{order_id}",
        headers={"Authorization": f"Bearer {chef_token}"},
    ).json()

    assert "subtotal" not in chef_order, "Chef must NOT see subtotal"
    assert "tax" not in chef_order, "Chef must NOT see tax"
    assert "total" not in chef_order, "Chef must NOT see total"
    assert "paymentStatus" not in chef_order, "Chef must NOT see paymentStatus"
    
    assert len(chef_order["items"]) > 0
    chef_item = chef_order["items"][0]
    assert "unitPrice" not in chef_item, "Chef must NOT see unitPrice"
    assert "price" not in chef_item, "Chef must NOT see price"
    assert "itemTotal" not in chef_item, "Chef must NOT see itemTotal"
    assert "discountPercentage" not in chef_item, "Chef must NOT see discountPercentage"
    assert chef_item["quantity"] == 2, "Chef must see item quantity"
    assert "name" in chef_item, "Chef must see item name"

    # 3. Chef GET /orders list
    chef_orders_list = client.get(
        "/api/v1/orders",
        headers={"Authorization": f"Bearer {chef_token}"},
    ).json()
    assert len(chef_orders_list) > 0
    for o in chef_orders_list[:5]:
        assert "subtotal" not in o
        assert "total" not in o
        for item in o.get("items", []):
            assert "unitPrice" not in item
            assert "itemTotal" not in item
