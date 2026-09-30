"""Backward-compatible re-export of app.db.session.

Maintains compatibility with code importing from app.core.database.
"""

from app.db.session import (
    Base,
    DatabaseService,
    SessionLocal,
    check_db_health,
    engine,
    get_db,
)

__all__ = [
    "Base",
    "DatabaseService",
    "SessionLocal",
    "check_db_health",
    "engine",
    "get_db",
]
