import logging
import sys
import threading
from contextvars import ContextVar

from app.core.config import settings
from logger_manager import LoggerManager

NO_CONTEXT = "-"
LOGGER_NAMESPACE = "docservice"

request_id_var: ContextVar[str] = ContextVar("request_id", default=NO_CONTEXT)
user_id_var: ContextVar[str] = ContextVar("user_id", default=NO_CONTEXT)

_configured = False
_config_lock = threading.Lock()
_FOREIGN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "uvicorn.asgi")


class ContextFilter(logging.Filter):
    """Adds request_id, user_id, and short_name context to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        req_id = request_id_var.get()
        u_id = user_id_var.get()
        record.context = (
            f" [req={req_id} user={u_id}]"
            if (req_id != NO_CONTEXT or u_id != NO_CONTEXT)
            else ""
        )
        prefix = f"{LOGGER_NAMESPACE}."
        record.short_name = record.name.removeprefix(prefix)
        return True


def setup_logging() -> None:
    """Configure root logging for the process."""
    global _configured
    if _configured:
        return

    with _config_lock:
        if _configured:
            return

        log_level = logging.DEBUG if settings.DEBUG else logging.INFO
        handler = logging.StreamHandler(sys.stdout)
        handler.addFilter(ContextFilter())
        handler.setFormatter(
            logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(short_name)s]%(context)s %(message)s"
            )
        )

        root = logging.getLogger()
        root.setLevel(log_level)
        root.handlers.clear()
        root.addHandler(handler)

        # Silence noisy third-party debug loggers in console output
        logging.getLogger("redis").setLevel(logging.INFO)
        logging.getLogger("redis.connection").setLevel(logging.INFO)
        logging.getLogger("asyncio").setLevel(logging.INFO)

        _configured = True


def adopt_foreign_loggers() -> None:
    """Redirect foreign/third-party loggers (like uvicorn) into the unified handler."""
    setup_logging()
    for name in _FOREIGN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True


def get_logger(category: str = "system") -> logging.Logger:
    """Get a centralized rotating logger managed by LoggerManager."""
    manager = LoggerManager(
        folder_name=category or "system",
        logger_name=f"{LOGGER_NAMESPACE}.{category or 'system'}",
    )
    return manager.logger
