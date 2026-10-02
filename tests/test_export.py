import csv
import io
import zipfile
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _get_admin_token():
    res = client.post("/api/v1/auth/login", json={"email": "admin@vaanvibes.com", "password": "admin123"})
    assert res.status_code == 200
    return res.json()["access_token"]


def _get_chef_token():
    # If chef exists or can login
    res = client.post("/api/v1/auth/login", json={"email": "chef@vaanvibes.com", "password": "chef123"})
    if res.status_code == 200:
        return res.json()["access_token"]
    return None


def test_export_authorization():
    # 1. Unauthenticated request rejected
    res = client.post("/api/v1/export/preview", json={"categories": ["menu_items"], "dateRange": "all_time"})
    assert res.status_code == 401

    # 2. Chef role rejected (Admin only)
    chef_token = _get_chef_token()
    if chef_token:
        res = client.post(
            "/api/v1/export/preview",
            json={"categories": ["menu_items"], "dateRange": "all_time"},
            headers={"Authorization": f"Bearer {chef_token}"},
        )
        assert res.status_code == 403


def test_export_preview():
    admin_token = _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    payload = {
        "categories": ["menu_items", "tables", "staff"],
        "dateRange": "all_time",
    }
    res = client.post("/api/v1/export/preview", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "counts" in data
    assert "menu_items" in data["counts"]
    assert "tables" in data["counts"]
    assert "staff" in data["counts"]
    assert data["total_records"] > 0
    assert data["date_range_label"] == "all-time"


def test_export_single_category_csv():
    admin_token = _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    payload = {
        "categories": ["menu_items"],
        "dateRange": "all_time",
    }
    res = client.post("/api/v1/export/download", json=payload, headers=headers)
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert 'filename="van-vibes-menu-items-all-time.csv"' in res.headers["content-disposition"]

    # Verify CSV format
    csv_text = res.content.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(csv_text)))
    assert len(reader) > 1  # Header + at least one data row
    header = reader[0]
    assert "Item ID" in header
    assert "Name" in header
    assert "Price (₹)" in header


def test_export_multiple_categories_zip():
    admin_token = _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    payload = {
        "categories": ["menu_items", "tables"],
        "dateRange": "all_time",
    }
    res = client.post("/api/v1/export/download", json=payload, headers=headers)
    assert res.status_code == 200
    assert "application/zip" in res.headers["content-type"]
    assert 'filename="van-vibes-export-all-time.zip"' in res.headers["content-disposition"]

    # Verify zip content
    zip_buf = io.BytesIO(res.content)
    with zipfile.ZipFile(zip_buf, "r") as zf:
        file_names = zf.namelist()
        assert any("menu-items" in name for name in file_names)
        assert any("tables" in name for name in file_names)


def test_export_category_filters():
    admin_token = _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Filter menu items by availability = True
    payload = {
        "categories": ["menu_items"],
        "dateRange": "all_time",
        "filters": {"menuAvailability": True},
    }
    res = client.post("/api/v1/export/preview", json=payload, headers=headers)
    assert res.status_code == 200
    avail_count = res.json()["counts"]["menu_items"]

    # Filter tables by status = AVAILABLE
    payload_tbl = {
        "categories": ["tables"],
        "dateRange": "all_time",
        "filters": {"tableStatus": "AVAILABLE"},
    }
    res_tbl = client.post("/api/v1/export/preview", json=payload_tbl, headers=headers)
    assert res_tbl.status_code == 200
    assert res_tbl.json()["counts"]["tables"] > 0


def test_export_custom_date_range_validation():
    admin_token = _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Start date after end date should fail validation
    payload = {
        "categories": ["menu_items"],
        "dateRange": "custom",
        "startDate": "2026-10-10",
        "endDate": "2026-10-01",
    }
    res = client.post("/api/v1/export/preview", json=payload, headers=headers)
    assert res.status_code == 422 or res.status_code == 400


def test_export_formula_injection_and_sensitive_exclusion():
    from app.modules.export.service import sanitize_csv_cell

    # Test formula injection
    assert sanitize_csv_cell("=1+1") == "'=1+1"
    assert sanitize_csv_cell("@SUM(A1)") == "'@SUM(A1)"
    assert sanitize_csv_cell("+cmd") == "'+cmd"
    assert sanitize_csv_cell("-2+3") == "'-2+3"
    assert sanitize_csv_cell("Regular text") == "Regular text"

    # Test staff export excludes password hash
    admin_token = _get_admin_token()
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.post(
        "/api/v1/export/download",
        json={"categories": ["staff"], "dateRange": "all_time"},
        headers=headers,
    )
    assert res.status_code == 200
    csv_text = res.content.decode("utf-8-sig")
    assert "password" not in csv_text.lower()
    assert "hash" not in csv_text.lower()
