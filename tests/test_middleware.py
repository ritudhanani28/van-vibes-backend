from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.middleware import RequestContextMiddleware, StandardResponseMiddleware


def _build_test_app() -> FastAPI:
    test_app = FastAPI()

    @test_app.get("/plain-dict")
    def plain_dict():
        return {"item": "apple", "quantity": 5}

    @test_app.get("/already-standard")
    def already_standard():
        return {
            "success": True,
            "statusCode": 200,
            "message": "already wrapped",
            "errors": [],
            "data": {"custom": True},
        }

    @test_app.get("/error-detail")
    def error_detail():
        return JSONResponse(
            status_code=400,
            content={"detail": "Bad input", "extra": "info"},
        )

    @test_app.get("/unhandled-error")
    def unhandled_error():
        raise RuntimeError("Something exploded!")

    # StandardResponse first, RequestContext last (outermost)
    test_app.add_middleware(StandardResponseMiddleware)
    test_app.add_middleware(RequestContextMiddleware)

    return test_app


client = TestClient(_build_test_app(), raise_server_exceptions=False)


def test_standard_response_wrapping():
    response = client.get("/plain-dict")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["statusCode"] == 200
    assert body["message"] == ""
    assert body["errors"] == []
    assert body["data"] == {"item": "apple", "quantity": 5}
    assert "X-Request-ID" in response.headers


def test_already_standardized_response_is_not_double_wrapped():
    response = client.get("/already-standard")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["statusCode"] == 200
    assert body["message"] == "already wrapped"
    assert body["errors"] == []
    assert body["data"] == {"custom": True}


def test_error_detail_standardization():
    response = client.get("/error-detail")
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["statusCode"] == 400
    assert body["message"] == "Bad input"
    assert body["errors"] == []


def test_request_context_incoming_x_request_id():
    custom_id = "test-request-id-12345"
    response = client.get("/plain-dict", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


def test_request_context_unhandled_exception():
    response = client.get("/unhandled-error")
    assert response.status_code == 500
    body = response.json()
    assert body["success"] is False
    assert body["statusCode"] == 500
    assert body["message"] == "Internal server error"
    assert "X-Request-ID" in response.headers


def test_security_service_token_decoding():
    import base64
    import json

    import pytest

    from app.core.security import SecurityService

    # Valid token
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode())
        .decode()
        .rstrip("=")
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "usr_99", "exp": 9999999999}).encode()
        )
        .decode()
        .rstrip("=")
    )
    token = f"{header}.{payload}.sig"

    data = SecurityService.decode_token(token)
    assert data["sub"] == "usr_99"

    # Expired token
    expired_payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "usr_old", "exp": 1000000000}).encode()
        )
        .decode()
        .rstrip("=")
    )
    with pytest.raises(ValueError, match="expired"):
        SecurityService.decode_token(f"{header}.{expired_payload}.sig")

    # Invalid token format
    with pytest.raises(ValueError, match="Invalid JWT token"):
        SecurityService.decode_token("not-a-valid-token")


def test_request_context_bearer_user_id_extraction():
    import base64
    import json

    from app.core.logging_config import user_id_var

    test_app = FastAPI()

    @test_app.get("/me")
    def me():
        return {"user_id": user_id_var.get()}

    test_app.add_middleware(RequestContextMiddleware)
    test_client = TestClient(test_app)

    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode())
        .decode()
        .rstrip("=")
    )
    payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "john_doe", "exp": 9999999999}).encode()
        )
        .decode()
        .rstrip("=")
    )
    token = f"{header}.{payload}.sig"

    res = test_client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["user_id"] == "john_doe"
