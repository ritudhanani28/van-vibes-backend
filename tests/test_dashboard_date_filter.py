import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_dashboard_summary_and_orders_date_filter():
    admin_login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@vaanvibes.com", "password": "admin123"},
    )
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Test GET /api/v1/dashboard/summary with all ranges
    for r in ["today", "yesterday", "30_days", "month", "year"]:
        resp = client.get(f"/api/v1/dashboard/summary?range={r}", headers=headers)
        assert resp.status_code == 200, f"Failed for range {r}: {resp.text}"
        data = resp.json()
        assert "totalOrders" in data
        assert "kitchenPending" in data
        assert "occupiedTables" in data
        assert "settledRevenue" in data
        assert "recentOrders" in data
        assert isinstance(data["totalOrders"], int)
        assert isinstance(data["settledRevenue"], (int, float))

    # 2. Test GET /api/v1/orders with date filter ranges
    for r in ["today", "yesterday", "30_days", "month", "year"]:
        resp = client.get(f"/api/v1/orders?range={r}", headers=headers)
        assert resp.status_code == 200, f"Failed for orders range {r}: {resp.text}"
        orders = resp.json()
        assert isinstance(orders, list)
