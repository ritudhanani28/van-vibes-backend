import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.modules.menu.models import MenuItem
from app.db.session import SessionLocal

client = TestClient(app)


def _get_tokens():
    admin_res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "admin123"},
    )
    assert admin_res.status_code == 200
    admin_token = admin_res.json()["access_token"]

    chef_res = client.post(
        "/api/v1/auth/login",
        json={"email": "chef@vaanvibes.com", "password": "chef123"},
    )
    assert chef_res.status_code == 200
    chef_token = chef_res.json()["access_token"]
    return admin_token, chef_token


def _create_order_for_billing():
    tbl_res = client.get("/api/v1/tables/T07")
    assert tbl_res.status_code == 200
    table = tbl_res.json()

    # 1 Espresso (140) + 2 Cappuccino (160 each = 320) = 460 Subtotal
    payload = {
        "tableId": table["id"],
        "token": table["token"],
        "sessionToken": "sess_bill_discount_test",
        "customerName": "Bill Discount Guest",
        "customerMobile": "9876543210",
        "items": [
            {"menuItemId": "hc-01", "name": "Espresso", "quantity": 1},
            {"menuItemId": "hc-03", "name": "Cappuccino", "quantity": 2},
        ],
    }
    res = client.post("/api/v1/orders", json=payload)
    assert res.status_code == 201, f"Failed to create order: {res.text}"
    return res.json()


def test_menu_item_has_no_discount_fields():
    """Verify menu items contain only normal selling price and no discount fields."""
    admin_token, _ = _get_tokens()
    # 1. Menu item list has no discountPercentage or discountedPrice
    menu_res = client.get("/api/v1/menu")
    assert menu_res.status_code == 200
    for item in menu_res.json()[:5]:
        assert "discount_percentage" not in item
        assert "discountPercentage" not in item
        assert "discounted_price" not in item
        assert "discountedPrice" not in item
        assert "price" in item

    # 2. Creating menu item does not accept or store discount percentage
    create_payload = {
        "name": "Normal Selling Price Espresso",
        "category": "hot-coffee",
        "price": 180.0,
    }
    create_res = client.post(
        "/api/v1/menu",
        json=create_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    try:
        assert create_res.status_code == 201
        created_item = create_res.json()
        assert "discountPercentage" not in created_item
        assert created_item["price"] == 180.0
    finally:
        if create_res.status_code == 201:
            client.delete(f"/api/v1/menu/{create_res.json()['id']}", headers={"Authorization": f"Bearer {admin_token}"})


def test_order_item_price_never_zero_and_stored_historically():
    """Admin portal must see actual item prices (never ₹0) and historical price retention."""
    admin_token, _ = _get_tokens()
    order = _create_order_for_billing()
    order_id = order["id"]

    # Admin fetches orders
    res = client.get(f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    order_data = res.json()
    items = order_data["items"]
    assert len(items) == 2

    # Espresso item (Qty 1)
    espresso = next(i for i in items if i["name"] == "Espresso")
    assert espresso["quantity"] == 1
    assert espresso["price"] == 140.0
    assert espresso["unitPrice"] == 140.0
    assert espresso["itemTotal"] == 140.0

    # Cappuccino item (Qty 2)
    cappuccino = next(i for i in items if i["name"] == "Cappuccino")
    assert cappuccino["quantity"] == 2
    assert cappuccino["price"] == 160.0
    assert cappuccino["unitPrice"] == 160.0
    assert cappuccino["itemTotal"] == 320.0

    # Historical price test: change menu item price to 200.0, existing order item remains 140.0
    db = SessionLocal()
    menu_item = db.query(MenuItem).filter(MenuItem.id == "hc-01").first()
    original_price = float(menu_item.price)
    try:
        menu_item.price = 200.0
        db.commit()

        # Re-fetch order: must retain historical 140.0
        recheck_res = client.get(f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {admin_token}"})
        assert recheck_res.status_code == 200
        recheck_items = recheck_res.json()["items"]
        recheck_espresso = next(i for i in recheck_items if i["name"] == "Espresso")
        assert recheck_espresso["price"] == 140.0
        assert recheck_espresso["unitPrice"] == 140.0
    finally:
        menu_item.price = original_price
        db.commit()
        db.close()


def test_bill_generation_without_discount():
    """Bill without discount and without GST: Total = 460.00."""
    admin_token, _ = _get_tokens()
    order = _create_order_for_billing()
    order_id = order["id"]

    bill_res = client.post(
        f"/api/v1/billing/{order_id}/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"discountPercentage": 0.0},
    )
    assert bill_res.status_code == 200, f"Generate failed: {bill_res.text}"
    bill = bill_res.json()
    assert bill["subtotal"] == 460.0
    assert bill["taxAmount"] == 0.0
    assert bill["discountPercentage"] == 0.0
    assert bill["discountAmount"] == 0.0
    assert bill["total"] == 460.0


def test_bill_generation_with_percentage_discount():
    """Bill with 10% discount without GST: Items 460 - 46 discount = 414.00 Total."""
    admin_token, _ = _get_tokens()
    order = _create_order_for_billing()
    order_id = order["id"]

    bill_res = client.post(
        f"/api/v1/billing/{order_id}/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"discountPercentage": 10.0},
    )
    assert bill_res.status_code == 200, f"Generate with discount failed: {bill_res.text}"
    bill = bill_res.json()
    assert bill["subtotal"] == 460.0
    assert bill["taxAmount"] == 0.0
    assert bill["discountPercentage"] == 10.0
    assert bill["discountAmount"] == 46.0
    assert bill["total"] == 414.0

    # Verify historical retention on subsequent GET /billing/{order_id}
    receipt_res = client.get(f"/api/v1/billing/{order_id}")
    assert receipt_res.status_code == 200
    receipt = receipt_res.json()
    assert receipt["discountPercentage"] == 10.0
    assert receipt["discountAmount"] == 46.0
    assert receipt["total"] == 414.0


def test_bill_percentage_discount_validation():
    """Backend must reject negative percentages and percentages > 100%."""
    admin_token, _ = _get_tokens()
    order = _create_order_for_billing()
    order_id = order["id"]

    # 1. Negative percentage rejected
    neg_res = client.post(
        f"/api/v1/billing/{order_id}/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"discountPercentage": -5.0},
    )
    assert neg_res.status_code == 400
    assert "between 0 and 100" in neg_res.text.lower()

    # 2. > 100% rejected (101%)
    excess_res = client.post(
        f"/api/v1/billing/{order_id}/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"discountPercentage": 101.0},
    )
    assert excess_res.status_code == 400
    assert "between 0 and 100" in excess_res.text.lower()

    # 3. 500% rejected
    excess_500 = client.post(
        f"/api/v1/billing/{order_id}/generate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"discountPercentage": 500.0},
    )
    assert excess_500.status_code == 400


def test_chef_cannot_generate_bill_or_see_discount():
    """Chef must be forbidden from billing and receives zero discount/financial/pricing data."""
    _, chef_token = _get_tokens()
    order = _create_order_for_billing()
    order_id = order["id"]

    # Chef attempts to generate bill
    chef_bill_res = client.post(
        f"/api/v1/billing/{order_id}/generate",
        headers={"Authorization": f"Bearer {chef_token}"},
        json={"discountPercentage": 10.0},
    )
    assert chef_bill_res.status_code in [401, 403]

    # Chef GET order details
    chef_order_res = client.get(
        f"/api/v1/orders/{order_id}",
        headers={"Authorization": f"Bearer {chef_token}"},
    )
    assert chef_order_res.status_code == 200
    chef_data = chef_order_res.json()
    assert "subtotal" not in chef_data
    assert "tax" not in chef_data
    assert "discountPercentage" not in chef_data
    assert "discountAmount" not in chef_data
    assert "total" not in chef_data
    if chef_data.get("items"):
        for item in chef_data["items"]:
            assert "price" not in item
            assert "unitPrice" not in item
            assert "itemTotal" not in item
