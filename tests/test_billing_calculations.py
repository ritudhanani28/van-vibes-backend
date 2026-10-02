import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app
from app.modules.sessions.service import calculate_bill_totals
from app.modules.orders.models import Order
from app.modules.sessions.models import BillingInvoice
from app.db.session import SessionLocal

client = TestClient(app)


def _get_admin_token():
    res = client.post("/api/v1/auth/login", json={"email": "admin@vaanvibes.com", "password": "admin123"})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_unit_calculate_bill_totals():
    # Case 3, 7: Preliminary total requiring positive round-off
    res = calculate_bill_totals(subtotal=455.70, discount_pct=0.0, extra_charge=0.0)
    assert res["subtotal"] == 455.70
    assert res["tax"] == 0.0
    assert res["discount_amount"] == 0.0
    assert res["amount_after_adjustments"] == 455.70
    assert res["round_off"] == 0.30
    assert res["total"] == 456.00

    # Case 8: Preliminary total requiring negative round-off
    res = calculate_bill_totals(subtotal=454.30, discount_pct=0.0, extra_charge=0.0)
    assert res["subtotal"] == 454.30
    assert res["amount_after_adjustments"] == 454.30
    assert res["round_off"] == -0.30
    assert res["total"] == 454.00

    # Case 9: Whole rupee total requiring zero round-off
    res = calculate_bill_totals(subtotal=455.00, discount_pct=0.0, extra_charge=0.0)
    assert res["subtotal"] == 455.00
    assert res["round_off"] == 0.00
    assert res["total"] == 455.00

    # Case 4, 5, 6: Both discount and extra charge
    # Subtotal 790, Discount 10% (79.00), Extra 20.00 -> 731.00
    res = calculate_bill_totals(subtotal=790.00, discount_pct=10.0, extra_charge=20.00)
    assert res["subtotal"] == 790.00
    assert res["discount_amount"] == 79.00
    assert res["extra_charge"] == 20.00
    assert res["amount_after_adjustments"] == 731.00
    assert res["round_off"] == 0.00
    assert res["total"] == 731.00

    # Case 10: Decimal prices and precision sensitivity
    res = calculate_bill_totals(subtotal=249.50, discount_pct=10.0, extra_charge=15.00)
    # 249.50 - 24.95 + 15.00 = 239.55 -> total 240.00, round_off +0.45
    assert res["subtotal"] == 249.50
    assert res["discount_amount"] == 24.95
    assert res["amount_after_adjustments"] == 239.55
    assert res["round_off"] == 0.45
    assert res["total"] == 240.00


def test_session_billing_complete_workflow():
    token = _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Clean previous open sessions for Table 08 to ensure fresh test isolation
    db = SessionLocal()
    from app.modules.tables.models import Table
    from app.modules.sessions.models import DiningSession
    tbl_db = db.query(Table).filter(Table.id == "T08").first()
    for s in db.query(DiningSession).filter(DiningSession.table_id == "T08", DiningSession.status != "CLOSED").all():
        s.status = "CLOSED"
    tbl_db.status = "AVAILABLE"
    db.commit()
    db.close()

    tbl_res = client.get("/api/v1/tables/T08")
    assert tbl_res.status_code == 200
    tbl = tbl_res.json()

    # 2. Place Order 1: 2 x Espresso (140 each = 280)
    order1_payload = {
        "tableId": tbl["id"],
        "token": tbl["token"],
        "sessionToken": "sess_bill_calc_test_t08",
        "customerName": "Alice Smith",
        "customerMobile": "9876543210",
        "items": [{"menuItemId": "hc-01", "name": "Espresso", "quantity": 2}],
    }
    o1_res = client.post("/api/v1/orders", json=order1_payload)
    assert o1_res.status_code == 201
    o1 = o1_res.json()
    assert o1["subtotal"] == 280.0
    assert o1["tax"] == 0.0

    # 3. Place Order 2 in same session: 1 x Cappuccino (160)
    order2_payload = {
        "tableId": tbl["id"],
        "token": tbl["token"],
        "sessionToken": "sess_bill_calc_test_t08",
        "customerName": "Alice Smith",
        "customerMobile": "9876543210",
        "items": [{"menuItemId": "hc-03", "name": "Cappuccino", "quantity": 1}],
    }
    o2_res = client.post("/api/v1/orders", json=order2_payload)
    assert o2_res.status_code == 201
    o2 = o2_res.json()
    assert o2["subtotal"] == 160.0

    sess_id = o1["diningSessionId"]

    # 4. Preview session detail BEFORE billing:
    # Subtotal must be 280 + 160 = 440.00, Tax must be 0.0, Total must be 440.00
    detail_res = client.get(f"/api/v1/dining-sessions/{sess_id}", headers=headers)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["subtotal"] == 440.0
    assert detail["tax"] == 0.0
    assert detail["total"] == 440.0

    # 5. Generate Session Bill with 10% discount and 20.00 extra charge
    # Subtotal = 440.00, Discount 10% = 44.00, Extra = 20.00
    # Amount After Adjustments = 440 - 44 + 20 = 416.00
    # Round Off = 0.00, Total = 416.00
    bill_gen = client.post(
        f"/api/v1/billing/sessions/{sess_id}/generate",
        json={"discountPercentage": 10.0, "extraCharge": 20.0},
        headers=headers,
    )
    assert bill_gen.status_code == 200
    bill = bill_gen.json()
    assert bill["subtotal"] == 440.0
    assert bill["taxAmount"] == 0.0
    assert bill["cgst"] == 0.0
    assert bill["sgst"] == 0.0
    assert bill["discountPercentage"] == 10.0
    assert bill["discountAmount"] == 44.0
    assert bill["extraCharge"] == 20.0
    assert bill["roundOff"] == 0.0
    assert bill["total"] == 416.0

    # Verify items in receipt
    # Espresso: qty 2, unitPrice 140.0, totalPrice 280.0
    # Cappuccino: qty 1, unitPrice 160.0, totalPrice 160.0
    items = bill["items"]
    assert len(items) == 2
    esp = next(i for i in items if i["name"] == "Espresso")
    assert esp["quantity"] == 2
    assert esp["unitPrice"] == 140.0
    assert esp["totalPrice"] == 280.0
    cap = next(i for i in items if i["name"] == "Cappuccino")
    assert cap["quantity"] == 1
    assert cap["unitPrice"] == 160.0
    assert cap["totalPrice"] == 160.0

    # 6. Verify GET /api/v1/billing/sessions/{sess_id} receipt matches generated bill exactly
    get_bill = client.get(f"/api/v1/billing/sessions/{sess_id}", headers=headers)
    assert get_bill.status_code == 200
    g_bill = get_bill.json()
    assert g_bill["subtotal"] == 440.0
    assert g_bill["taxAmount"] == 0.0
    assert g_bill["discountAmount"] == 44.0
    assert g_bill["extraCharge"] == 20.0
    assert g_bill["roundOff"] == 0.0
    assert g_bill["total"] == 416.0

    # 7. Settle payment with UPI
    settle_res = client.post(
        f"/api/v1/billing/sessions/{sess_id}/settle",
        json={"paymentMethod": "UPI"},
        headers=headers,
    )
    assert settle_res.status_code == 200
    settle_data = settle_res.json()
    assert settle_data["paymentStatus"] == "PAID"
    assert settle_data["paymentMethod"] == "UPI"
    assert settle_data["total"] == 416.0
    assert settle_data["taxAmount"] == 0.0
    assert settle_data["roundOff"] == 0.0


def test_order_billing_round_off_and_extra_charge():
    token = _get_admin_token()
    headers = {"Authorization": f"Bearer {token}"}

    tbl_res = client.get("/api/v1/tables/T09")
    assert tbl_res.status_code == 200
    tbl = tbl_res.json()

    # 1 Espresso (140)
    o_res = client.post(
        "/api/v1/orders",
        json={
            "tableId": tbl["id"],
            "token": tbl["token"],
            "sessionToken": "sess_bill_round_off_t09",
            "customerName": "Bob",
            "customerMobile": "9876543211",
            "items": [{"menuItemId": "hc-01", "name": "Espresso", "quantity": 1}],
        },
    )
    assert o_res.status_code == 201
    order = o_res.json()
    order_id = order["id"]

    # Apply 15% discount + 12.30 extra charge
    # Subtotal 140.00
    # Disc 15% = 21.00
    # Extra = 12.30
    # Preliminary = 140 - 21 + 12.30 = 131.30
    # Total = 131.00, Round Off = -0.30
    gen_res = client.post(
        f"/api/v1/billing/{order_id}/generate",
        json={"discountPercentage": 15.0, "extraCharge": 12.30},
        headers=headers,
    )
    assert gen_res.status_code == 200
    gen_bill = gen_res.json()
    assert gen_bill["subtotal"] == 140.0
    assert gen_bill["taxAmount"] == 0.0
    assert gen_bill["discountAmount"] == 21.0
    assert gen_bill["extraCharge"] == 12.30
    assert gen_bill["amountAfterAdjustments"] == 131.30
    assert gen_bill["roundOff"] == -0.30
    assert gen_bill["total"] == 131.00

    # Settle with CASH
    settle_res = client.post(
        f"/api/v1/billing/{order_id}/settle",
        json={"paymentMethod": "CASH"},
        headers=headers,
    )
    assert settle_res.status_code == 200
    settled = settle_res.json()
    assert settled["paymentStatus"] == "PAID"
    assert settled["total"] == 131.00
    assert settled["roundOff"] == -0.30
