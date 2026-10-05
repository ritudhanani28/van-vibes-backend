from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_order_creation_phone_validation():
    # 1. Invalid phone number (less than 10 digits)
    res = client.post(
        "/api/v1/orders",
        json={
            "tableId": "T01",
            "token": "dummy",
            "sessionToken": "dummy",
            "customerName": "Test Customer",
            "customerMobile": "987654321",  # 9 digits -> invalid
            "items": [{"menuItemId": "hc-01", "name": "Coffee", "price": 100, "quantity": 1}],
        },
    )
    assert res.status_code == 422
    data = res.json()
    assert data["success"] is False
    assert "Phone number must contain exactly 10 digits" in str(data["errors"])
    assert data["fieldErrors"]["customerMobile"] == "Phone number must contain exactly 10 digits"

    # 2. Invalid phone number (contains letters or symbols)
    res2 = client.post(
        "/api/v1/orders",
        json={
            "tableId": "T01",
            "token": "dummy",
            "sessionToken": "dummy",
            "customerName": "Test Customer",
            "customerMobile": "+9198765432",  # contains '+'
            "items": [{"menuItemId": "hc-01", "name": "Coffee", "price": 100, "quantity": 1}],
        },
    )
    assert res2.status_code == 422
    data2 = res2.json()
    assert data2["success"] is False
    assert data2["fieldErrors"]["customerMobile"] == "Phone number must contain exactly 10 digits"

    # 3. Invalid customer name (< 2 characters)
    res3 = client.post(
        "/api/v1/orders",
        json={
            "tableId": "T01",
            "token": "dummy",
            "sessionToken": "dummy",
            "customerName": "A",
            "customerMobile": "9876543210",
            "items": [{"menuItemId": "hc-01", "name": "Coffee", "price": 100, "quantity": 1}],
        },
    )
    assert res3.status_code == 422
    data3 = res3.json()
    assert data3["success"] is False
    assert "customerName" in data3["fieldErrors"]


def test_chef_creation_phone_validation():
    # Login as admin to test chef creation
    login_res = client.post("/api/v1/auth/login", json={"email": "admin@vaanvibes.in", "password": "admin123"})
    if login_res.status_code == 200:
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt to create chef with invalid contact number (spaces / wrong length)
        res = client.post(
            "/api/v1/auth/chefs",
            headers=headers,
            json={
                "name": "Test Chef",
                "email": "testchef@vaanvibes.in",
                "contact_number": "98765-43210",
                "password": "SecurePass1!",
            },
        )
        assert res.status_code == 422
        data = res.json()
        assert data["success"] is False
        assert data["fieldErrors"]["contact_number"] == "Phone number must contain exactly 10 digits"
