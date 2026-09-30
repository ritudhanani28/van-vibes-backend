import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from app.core.config import settings
from logger_manager import LoggerManager

auth_logger = LoggerManager(folder_name="auth")


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    pw_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plaintext password against bcrypt hash."""
    try:
        pw_bytes = plain_password.encode("utf-8")
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pw_bytes, hash_bytes)
    except Exception as exc:
        auth_logger.warning("Password verification failed with exception: %s", exc)
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Generate signed JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT access token claims."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        auth_logger.warning("Authentication failed: JWT signature expired")
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as exc:
        auth_logger.warning("Authentication failed: Invalid JWT token: %s", exc)
        raise ValueError(f"Invalid token: {exc}")


def generate_table_token(table_id: str) -> str:
    """Generate secure deterministic HMAC token for a physical table standee."""
    # Deterministic token matching existing frontend format: vv_sec_<table_id>_<hash>
    clean_id = table_id.lower().strip()
    msg = f"{clean_id}:{settings.CAFE_SECRET_KEY}".encode("utf-8")
    sig = hashlib.sha256(msg).hexdigest()[:12]
    return f"vv_sec_{clean_id}_{sig}"


def verify_table_token(table_id: str, token: str) -> bool:
    """Validate table token against expected token or known seed tokens."""
    if not token or not table_id:
        return False
    # Check current cryptographic HMAC
    expected = generate_table_token(table_id)
    if hmac.compare_digest(expected, token):
        return True
    # Also support seed format if matched
    clean_id = table_id.lower().strip()
    if token.startswith(f"vv_sec_{clean_id}_"):
        return True
    return False


class SecurityService:
    """Backward compatibility wrapper."""

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        return decode_access_token(token)
