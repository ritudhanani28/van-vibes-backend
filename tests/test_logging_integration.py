"""Integration tests verifying LoggerManager across all application categories."""

import base64
import json
import time

from fastapi.testclient import TestClient

from app.core.redis import RedisService
from app.core.security import SecurityService
from app.db.session import DatabaseService
from app.main import app
from logger_manager import PROJECT_ROOT, LoggerManager

client = TestClient(app)


def test_api_and_system_logging_activity():
    """Verify that requests write into logs/api/activity.log and logs/system/activity.log."""
    response = client.get("/api/v1/health")
    assert response.status_code in (200, 503)

    api_log = PROJECT_ROOT / "logs" / "api" / "activity.log"
    system_log = PROJECT_ROOT / "logs" / "system" / "activity.log"

    assert api_log.exists(), "logs/api/activity.log was not created"
    assert system_log.exists(), "logs/system/activity.log was not created"

    api_content = api_log.read_text(encoding="utf-8")
    assert "/api/v1/health" in api_content

    system_content = system_log.read_text(encoding="utf-8")
    assert "FastAPI" in system_content or "Building FastAPI" in system_content


def test_auth_logging_activity():
    """Verify that failed token validations write into logs/auth/activity.log."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode())
        .decode()
        .rstrip("=")
    )
    # Expired token with sub
    expired_payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "user_expired_42", "exp": 1000000000}).encode()
        )
        .decode()
        .rstrip("=")
    )
    secret_signature = "do_not_log_this_secret_signature"
    raw_token = f"{header}.{expired_payload}.{secret_signature}"

    try:
        SecurityService.decode_token(raw_token)
    except ValueError:
        pass

    # Malformed token
    try:
        SecurityService.decode_token("not-a-token")
    except ValueError:
        pass

    auth_log = PROJECT_ROOT / "logs" / "auth" / "activity.log"
    assert auth_log.exists(), "logs/auth/activity.log was not created"
    auth_content = auth_log.read_text(encoding="utf-8")

    assert "user_expired_42" in auth_content
    assert "Malformed or unparseable JWT token format" in auth_content
    # Ensure sensitive raw secret was NOT logged
    assert secret_signature not in auth_content


def test_database_and_redis_logging_activity():
    """Verify logs/database/activity.log and logs/redis/activity.log exist and log."""
    DatabaseService.check_health()
    RedisService.check_health()

    db_log = PROJECT_ROOT / "logs" / "database" / "activity.log"
    redis_log = PROJECT_ROOT / "logs" / "redis" / "activity.log"

    assert db_log.exists(), "logs/database/activity.log was not created"
    assert redis_log.exists(), "logs/redis/activity.log was not created"


def test_duplicate_handler_prevention_across_modules():
    """Verify repeated LoggerManager initialization does not produce duplicate log entries."""
    logger_a = LoggerManager(folder_name="test_dedup")
    logger_b = LoggerManager(folder_name="test_dedup")

    unique_msg = f"dedup_test_message_{time.time()}"
    logger_a.info(unique_msg)
    logger_b.info(unique_msg)

    test_log = PROJECT_ROOT / "logs" / "test_dedup" / "activity.log"
    content = test_log.read_text(encoding="utf-8")
    assert content.count(unique_msg) == 2, "Duplicate handlers caused redundant records"

    # Cleanup test folder
    import shutil

    shutil.rmtree(PROJECT_ROOT / "logs" / "test_dedup", ignore_errors=True)
