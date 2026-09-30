from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from logger_manager import LoggerManager

database_logger = LoggerManager(folder_name="database")


def _engine_kwargs() -> dict:
    if settings.DATABASE_URL.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {
        "pool_size": max(5, settings.DB_POOL_SIZE),
        "max_overflow": max(0, settings.DB_MAX_OVERFLOW),
        "pool_pre_ping": True,
        "pool_recycle": 1800,
    }


engine = create_engine(settings.DATABASE_URL, **_engine_kwargs())

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class DatabaseService:
    """Manages database engine lifecycle, sessions, and connectivity health checks."""

    engine = engine
    session_factory = SessionLocal

    @classmethod
    def get_session(cls) -> Session:
        """Create a new database session."""
        return cls.session_factory()

    @classmethod
    def check_health(cls) -> bool:
        """Verify database connectivity with a lightweight ping query."""
        try:
            with cls.engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
                return True
        except Exception as exc:  # noqa: BLE001
            database_logger.error("Database connectivity check failed: %s", exc)
            return False

    @classmethod
    def close(cls) -> None:
        """Dispose of the connection pool."""
        database_logger.info("Disposing database connection pool.")
        cls.engine.dispose()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    db = DatabaseService.get_session()
    try:
        yield db
    except Exception:
        database_logger.exception(
            "Database transaction failed during session execution"
        )
        raise
    finally:
        db.close()


check_db_health = DatabaseService.check_health
