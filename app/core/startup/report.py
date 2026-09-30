"""Startup report: probes dependencies and logs a startup summary."""

from __future__ import annotations

import logging
import os
import platform
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.core.config import settings
from logger_manager import LoggerManager

system_logger = LoggerManager(folder_name="system")

_WIDTH = 80
_LABEL_WIDTH = 22


def _banner(title: str) -> None:
    system_logger.info("=" * _WIDTH)
    system_logger.info(title.center(_WIDTH).rstrip())
    system_logger.info("=" * _WIDTH)


def _section(title: str) -> None:
    system_logger.info("-" * _WIDTH)
    system_logger.info(title)
    system_logger.info("-" * _WIDTH)


def _field(label: str, value: Any) -> None:
    system_logger.info("%s: %s", label.ljust(_LABEL_WIDTH), value)


def _probe(
    label: str,
    fn: Callable[[], str | None],
    *,
    required: bool = True,
    doing: str | None = None,
) -> bool:
    """Run one health probe. Returns True on success."""
    system_logger.info("%s...", doing or f"Connecting to {label}")
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001
        log = system_logger.error if required else system_logger.warning
        log("%s: Failed — %s", label.ljust(_LABEL_WIDTH), exc)
        return False
    system_logger.info("%s: %s", label.ljust(_LABEL_WIDTH), detail or "OK")
    return True


def _check_database() -> str:
    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return f"Connection established ({engine.dialect.name})"


def _check_migrations() -> str:
    """Compare the DB's stamped revision against the newest revision on disk."""
    alembic_log = logging.getLogger("alembic")
    previous_level = alembic_log.level
    alembic_log.setLevel(logging.WARNING)
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        from app.db.session import engine

        project_root = Path(__file__).resolve().parent.parent.parent.parent
        ini_path = project_root / "alembic.ini"
        if not ini_path.exists():
            return "No alembic.ini found"

        cfg = Config(str(ini_path))
        cfg.set_main_option("script_location", str(project_root / "alembic"))

        script = ScriptDirectory.from_config(cfg)
        heads = set(script.get_heads())
        with engine.connect() as conn:
            current = set(MigrationContext.configure(conn).get_current_heads())
    finally:
        alembic_log.setLevel(previous_level)

    if not current and not heads:
        return "Initial state (no migrations created yet)"
    if not current:
        return "No revision recorded — run 'alembic upgrade head'"
    if current == heads:
        return f"Up to date (revision {', '.join(sorted(current))})"
    return (
        f"Update required — database is at {', '.join(sorted(current))}, "
        f"latest is {', '.join(sorted(heads))}. Run 'alembic upgrade head'"
    )


def _check_redis() -> str:
    from app.core.redis import RedisService

    client = RedisService.get_client()
    client.ping()
    return f"Connection established ({_redact_url(settings.REDIS_URL)})"


def _redact_url(url: str) -> str:
    """Strip credentials so a broker/DB URL is safe to print."""
    if "@" in url and "//" in url:
        scheme, _, rest = url.partition("//")
        return f"{scheme}//***@{rest.rpartition('@')[2]}"
    return url


def _argv_option(name: str) -> str | None:
    """Read --name value or --name=value from command line."""
    flag = f"--{name}"
    argv = sys.argv
    for index, arg in enumerate(argv):
        if arg == flag and index + 1 < len(argv):
            return argv[index + 1]
        if arg.startswith(f"{flag}="):
            return arg.split("=", 1)[1]
    return None


def resolve_bind_address() -> tuple[str, int]:
    """Determine host and port the server is listening on."""
    host = _argv_option("host") or os.getenv("HOST") or settings.HOST
    raw_port = _argv_option("port") or os.getenv("PORT")
    try:
        port = int(raw_port) if raw_port else settings.PORT
    except (TypeError, ValueError):
        port = settings.PORT
    return host, port


def _base_url(host: str, port: int) -> str:
    """Build the base URL shown in the report."""
    return f"http://{host}:{port}"


def log_startup_report(
    app: Any, *, host: str | None = None, port: int | None = None
) -> None:
    """Emit the initialization report before normal traffic begins."""
    try:
        detected_host, detected_port = resolve_bind_address()
        _render(app, host or detected_host, port or detected_port)
    except Exception:
        system_logger.exception(
            "Could not render the startup report. This does not affect the application."
        )


def log_ready(started_at: float) -> None:
    """Log the single line that closes startup, once initialization completes."""
    try:
        system_logger.info(
            "%s is ready — startup completed in %.2f seconds.",
            settings.PROJECT_NAME,
            time.perf_counter() - started_at,
        )
    except Exception:
        system_logger.exception("Could not log the ready line.")


def _render(app: Any, host: str, port: int) -> None:
    import fastapi

    _banner(settings.PROJECT_NAME.upper())
    system_logger.info("Starting %s...", settings.PROJECT_NAME)
    _field("Environment", settings.ENVIRONMENT.capitalize())
    _field("Version", f"v{settings.VERSION}")
    _field("Python", platform.python_version())
    _field("FastAPI", fastapi.__version__)
    _field("Host", host)
    _field("Port", port)
    system_logger.info("")

    _section("Database")
    db_ok = _probe("PostgreSQL", _check_database)
    if db_ok:
        _probe(
            "Migrations",
            _check_migrations,
            required=False,
            doing="Checking database migrations",
        )
    else:
        system_logger.warning(
            "%s: Skipped — no database connection to check against",
            "Migrations".ljust(_LABEL_WIDTH),
        )
    system_logger.info("")

    _section("Redis")
    _probe("Redis", _check_redis, required=False)
    system_logger.info("")

    _section("Services")
    _field("Queue", settings.QUEUE_NAME)
    middleware_count = len(getattr(app, "user_middleware", []))
    route_count = len(getattr(app, "routes", []))
    _field("Middleware", f"{middleware_count} registered")
    _field("Routes", f"{route_count} registered")
    system_logger.info("")

    _section("Application")
    base = _base_url(host, port)
    _field("Application URL", base)
    _field("Swagger UI", f"{base}/docs")
    _field("ReDoc", f"{base}/redoc")
    system_logger.info("=" * _WIDTH)
