from typing import Any

import redis

from app.core.config import settings
from logger_manager import LoggerManager

redis_logger = LoggerManager(folder_name="redis")

try:
    from redis.maint_notifications import MaintNotificationsConfig

    _maint_config: Any = MaintNotificationsConfig(enabled=False)
except ImportError:
    _maint_config = None


def _redact_url(url: str) -> str:
    """Strip credentials so Redis connection URL is safe to log."""
    if "@" in url and "//" in url:
        scheme, _, rest = url.partition("//")
        return f"{scheme}//***@{rest.rpartition('@')[2]}"
    return url


class RedisService:
    """Manages Redis connection pooling, health checks, and client operations."""

    _pool: redis.ConnectionPool | None = None

    @classmethod
    def get_pool(cls) -> redis.ConnectionPool:
        """Get or lazily initialize the shared Redis connection pool."""
        if cls._pool is None:
            redis_logger.info(
                "Initializing shared Redis connection pool (url=%s)",
                _redact_url(settings.REDIS_URL),
            )
            pool_kwargs: dict[str, Any] = {"decode_responses": True}
            if _maint_config is not None:
                pool_kwargs["maint_notifications_config"] = _maint_config

            cls._pool = redis.ConnectionPool.from_url(settings.REDIS_URL, **pool_kwargs)
        return cls._pool

    @classmethod
    def get_client(cls) -> redis.Redis:
        """Return a Redis client instance from the connection pool."""
        return redis.Redis(connection_pool=cls.get_pool())

    @classmethod
    def check_health(cls) -> bool:
        """Verify Redis connectivity."""
        try:
            client = cls.get_client()
            return bool(client.ping())
        except Exception as exc:  # noqa: BLE001
            redis_logger.error("Redis health ping failed: %s", exc)
            return False

    @classmethod
    def close(cls) -> None:
        """Disconnect and release connection pool resources."""
        if cls._pool is not None:
            redis_logger.info("Closing Redis connection pool.")
            cls._pool.disconnect()
            cls._pool = None


# Functional aliases for backward compatibility
get_redis_client = RedisService.get_client
check_redis_health = RedisService.check_health
