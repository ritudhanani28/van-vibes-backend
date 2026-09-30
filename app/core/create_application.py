from fastapi import FastAPI

from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.logging_config import adopt_foreign_loggers, setup_logging
from app.core.routers import setup_routers
from app.core.setup_middleware import setup_middleware
from logger_manager import LoggerManager

setup_logging()
system_logger = LoggerManager(folder_name="system")


def create_application() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    adopt_foreign_loggers()
    system_logger.info(
        "Building FastAPI application instance (version=%s, env=%s)",
        settings.VERSION,
        settings.ENVIRONMENT,
    )

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Asynchronous Document Processing Service API",
        version=settings.VERSION,
        lifespan=lifespan,
    )

    setup_middleware(app)
    register_exception_handlers(app)
    setup_routers(app)

    return app
