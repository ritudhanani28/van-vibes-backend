import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.modules.sessions.models import DiningSession, SessionStatus
from app.modules.tables.models import Table
from app.db.session import SessionLocal

client = TestClient(app)


def _get_admin_token():
    res = client.post("/api/v1/auth/login", json={"email": "admin@vaanvibes.com", "password": "admin123"})
    assert res.status_code == 200
    return res.json()["access_token"]


def test_full_table_session_multi_order_lifecycle():
    admin_token = _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Reset Table 05 to AVAILABLE and clear any open sessions
    db = SessionLocal()
    tbl = db.query(Table).filter(Table.id == "T05").first()
    assert tbl is not None
    open_sess = db.query(DiningSession).filter(DiningSession.table_id == "T05", DiningSession.status == "OPEN").all()
    for s in open_sess:
        s.status = "CLOSED"
    tbl.status = "AVAILABLE"
    db.commit()
    token = tbl.token
    db.close()

    # Step 1: Customer A scans Table 05 QR
    scan1 = client.post("/api/v1/tables/validate-qr", json={"tableId": "T05", "token": token})
    assert scan1.status_code == 200
    val1 = scan1.json()
    assert val1["valid"] is True
    session_1_id = val1["diningSession"]["id"]
    assert val1["diningSession"]["status"] == "OPEN"

    # Verify physical table is now OCCUPIED
    tbl_chk = client.get("/api/v1/tables/T05").json()
    assert tbl_chk["status"] == "OCCUPIED"

    # Step 2: Customer A places Order 1
    o1_res = client.post("/api/v1/orders", json={
        "tableId": "T05",
        "token": token,
        "diningSessionId": session_1_id,
        "sessionToken": "sess_cust_a",
        "customerName": "Customer A",
        "customerMobile": "9999911111",
        "items": [{"menuItemId": "hc-01", "name": "Espresso", "quantity": 1}],
    })
    assert o1_res.status_code == 201
    o1 = o1_res.json()
    assert o1["diningSessionId"] == session_1_id

    # Step 3: Customer B (Friend) scans Table 05 QR on their phone
    scan2 = client.post("/api/v1/tables/validate-qr", json={"tableId": "T05", "token": token})
    assert scan2.status_code == 200
    val2 = scan2.json()
    assert val2["valid"] is True
    # Joins the same open session!
    assert val2["diningSession"]["id"] == session_1_id
    assert val2["isNewSession"] is False

    # Step 4: Customer B places Order 2
    o2_res = client.post("/api/v1/orders", json={
        "tableId": "T05",
        "token": token,
        "diningSessionId": session_1_id,
        "sessionToken": "sess_cust_b",
        "customerName": "Customer B",
        "customerMobile": "9999922222",
        "items": [{"menuItemId": "hc-03", "name": "Cappuccino", "quantity": 1}],
    })
    assert o2_res.status_code == 201
    o2 = o2_res.json()
    assert o2["diningSessionId"] == session_1_id

    # Step 5: Check session details (Consolidated)
    sess_detail = client.get(f"/api/v1/dining-sessions/{session_1_id}").json()
    assert sess_detail["orderCount"] == 2
    assert sess_detail["status"] == "OPEN"

    # Step 6: Admin generates Final Bill for Session 1 with 10% discount
    bill_gen = client.post(
        f"/api/v1/billing/sessions/{session_1_id}/generate",
        json={"discount_percentage": 10.0},
        headers=headers,
    )
    assert bill_gen.status_code == 200
    bill_data = bill_gen.json()
    assert bill_data["diningSessionId"] == session_1_id
    assert bill_data["discountPercentage"] == 10.0
    assert bill_data["paymentStatus"] == "PENDING"

    # CRITICAL CHECK: Table 05 must IMMEDIATELY become AVAILABLE!
    tbl_after_bill = client.get("/api/v1/tables/T05").json()
    assert tbl_after_bill["status"] == "AVAILABLE"

    # Session status must be BILL_GENERATED
    sess_after_bill = client.get(f"/api/v1/dining-sessions/{session_1_id}").json()
    assert sess_after_bill["status"] == "BILL_GENERATED"

    # Unpaid bill must appear under pending payments
    pending_list = client.get("/api/v1/billing/pending", headers=headers).json()
    assert any(p["diningSessionId"] == session_1_id for p in pending_list)

    # Step 7: A completely new customer arrives and scans Table 05 while Session 1 bill is UNPAID
    scan3 = client.post("/api/v1/tables/validate-qr", json={"tableId": "T05", "token": token})
    assert scan3.status_code == 200
    val3 = scan3.json()
    assert val3["valid"] is True
    session_2_id = val3["diningSession"]["id"]
    # Must NOT attach to old session S1!
    assert session_2_id != session_1_id
    assert val3["diningSession"]["status"] == "OPEN"

    # Physical Table is now OCCUPIED by Session 2
    tbl_s2 = client.get("/api/v1/tables/T05").json()
    assert tbl_s2["status"] == "OCCUPIED"

    # Step 8: New customer places Order 3
    o3_res = client.post("/api/v1/orders", json={
        "tableId": "T05",
        "token": token,
        "diningSessionId": session_2_id,
        "sessionToken": "sess_cust_c",
        "customerName": "Customer C",
        "customerMobile": "9999933333",
        "items": [{"menuItemId": "hc-01", "name": "Espresso", "quantity": 1}],
    })
    assert o3_res.status_code == 201
    assert o3_res.json()["diningSessionId"] == session_2_id

    # Step 9: Old Customer from Session 1 FINALLY pays their bill!
    settle_res = client.post(
        f"/api/v1/billing/sessions/{session_1_id}/settle",
        json={"paymentMethod": "UPI"},
        headers=headers,
    )
    assert settle_res.status_code == 200
    assert settle_res.json()["paymentStatus"] == "PAID"

    # Verify Session 1 is CLOSED
    sess_1_closed = client.get(f"/api/v1/dining-sessions/{session_1_id}").json()
    assert sess_1_closed["status"] == "CLOSED"

    # CRITICAL CHECK: Physical Table 05 MUST REMAIN OCCUPIED because Session 2 is OPEN!
    tbl_during_s2 = client.get("/api/v1/tables/T05").json()
    assert tbl_during_s2["status"] == "OCCUPIED"

    # Session 2 is still OPEN and untouched
    sess_2_status = client.get(f"/api/v1/dining-sessions/{session_2_id}").json()
    assert sess_2_status["status"] == "OPEN"
    assert sess_2_status["orderCount"] == 1

    # Step 10: Session 2 finishes and generates final bill
    bill_gen_s2 = client.post(
        f"/api/v1/billing/sessions/{session_2_id}/generate",
        json={"discount_percentage": 0.0},
        headers=headers,
    )
    assert bill_gen_s2.status_code == 200

    # Physical Table 05 becomes AVAILABLE again
    tbl_after_s2 = client.get("/api/v1/tables/T05").json()
    assert tbl_after_s2["status"] == "AVAILABLE"
